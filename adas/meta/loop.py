"""Orchestrates one generate → reflect → evaluate → archive cycle."""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adas.archive_runtime.service import ArchiveService
from adas.archive_runtime.store import ArchiveStore
from adas.baseline.models import BaselineEvaluationRecord
from adas.config import (
    ARCHIVE_DIR,
    FEEDBACK_FILE,
    META_CANDIDATE_TEMP_DIR,
    META_REFLECT_PASSES,
    META_USE_LLM_JUDGING,
)
from adas.deployment.promoter import DeploymentRecordStore, SkillPromoter
from adas.evaluation.service import Evaluator
from adas.meta.context import build_context
from adas.meta.dedupe import is_duplicate
from adas.meta.generator import Generator
from adas.meta.models import Candidate, CycleResult, MetaContext
from adas.meta.parser import validate_candidate
from adas.meta.reflector import Reflector

_log = logging.getLogger(__name__)
_META_SOURCE_TYPE = "meta-agent"


class _CycleStageError(Exception):
    """Internal exception used to map failed stages into CycleResult.

    It keeps the runner methods small while preserving the existing public result shape.
    """

    def __init__(
        self,
        outcome: str,
        message: str,
        candidate: Candidate | None = None,
        eval_result: Any | None = None,
        skill_id: str | None = None,
    ) -> None:
        """Capture the failure state needed to build a CycleResult."""
        super().__init__(message)
        self.outcome = outcome
        self.message = message
        self.candidate = candidate
        self.eval_result = eval_result
        self.skill_id = skill_id

    def to_cycle_result(self) -> CycleResult:
        """Convert the stage failure into the public cycle result contract."""
        return CycleResult(
            outcome=self.outcome,
            candidate=self.candidate,
            eval_result=self.eval_result,
            skill_id=self.skill_id,
            error=self.message,
        )


def _write_temp_skill(skill_md: str, temp_dir: str) -> Path:
    """Write the candidate skill markdown to a named temp file the evaluator can read.
    The caller is responsible for unlinking the file once evaluation finishes."""
    Path(temp_dir).mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".md",
        dir=temp_dir,
        delete=False,
        prefix="meta_candidate_",
    )
    tmp.write(skill_md)
    tmp.close()
    return Path(tmp.name)


def _archive_context(
    cache_path: str,
    feedback_path: str,
    design_goal: str,
    reflect_passes: int,
    use_llm_judging: bool,
) -> dict[str, Any]:
    """Package cycle-level parameters into the context dict stored with each archive entry.
    Stored verbatim so the archive record is self-describing for later inspection."""
    return {
        "cache_path": cache_path,
        "feedback_path": feedback_path,
        "design_goal": design_goal,
        "reflect_passes": reflect_passes,
        "use_llm_judging": use_llm_judging,
    }


def _find_archived_skill_id(
    index_dict: dict[str, Any],
    source_type: str,
    skill_path: Path,
) -> str | None:
    """Scan the returned index dict for the skill_id the archive assigned to this cycle's
    temp file, matching on source_type and the resolved absolute path."""
    resolved_skill_path = str(skill_path.resolve())
    for entry_dict in reversed(index_dict.get("skills", [])):
        if (
            entry_dict.get("source_type") == source_type
            and entry_dict.get("origin_skill_path") == resolved_skill_path
        ):
            return entry_dict.get("skill_id")
    return None


@dataclass(slots=True)
class MetaCycleRunner:
    """Orchestrates one generate -> reflect -> evaluate -> archive cycle.

    The public run_cycle function below stays as a thin compatibility wrapper.
    """

    cache_path: str
    archive_dir: str = ARCHIVE_DIR
    feedback_path: str = FEEDBACK_FILE
    design_goal: str = ""
    temp_dir: str = META_CANDIDATE_TEMP_DIR
    reflect_passes: int = META_REFLECT_PASSES
    use_llm_judging: bool = META_USE_LLM_JUDGING
    generator: Generator | None = None
    reflector: Reflector | None = None
    evaluator: Evaluator | None = None
    archive_service: ArchiveService | None = None
    skill_promoter: SkillPromoter | None = None
    promote_best: bool = False
    production_skill_path: str | None = None
    deployment_record_path: str | None = None
    context: MetaContext | None = None

    def run(self) -> CycleResult:
        """Run the full cycle and translate known stage failures into CycleResult."""
        if self.reflect_passes < 0:
            raise ValueError("reflect_passes must be >= 0.")
        temp_path: Path | None = None
        try:
            ctx = self._build_context()
            candidate = self._generate_candidate(ctx)
            candidate = self._reflect_candidate(candidate, ctx)
            self._validate_candidate(candidate)
            if self._is_duplicate(candidate):
                return CycleResult(outcome="dedupe", candidate=candidate)

            temp_path = self._write_candidate_skill(candidate)
            eval_result = self._evaluate_candidate(candidate, temp_path)
            skill_id = self._archive_candidate(candidate, temp_path, eval_result)
            promotion_result = self._promote_if_requested(
                candidate=candidate,
                eval_result=eval_result,
                skill_id=skill_id,
            )
            return self._success_result(
                candidate=candidate,
                eval_result=eval_result,
                skill_id=skill_id,
                promotion_result=promotion_result,
            )
        except _CycleStageError as exc:
            return exc.to_cycle_result()
        finally:
            self._cleanup_temp_skill(temp_path)

    def _build_context(self) -> MetaContext:
        """Build or reuse the prompt context for this cycle."""
        try:
            return self.context or build_context(
                archive_dir=self.archive_dir,
                feedback_path=self.feedback_path,
                design_goal=self.design_goal,
            )
        except Exception as exc:
            _log.error("Context build failed: %s", exc)
            raise _CycleStageError("parse_failure", str(exc)) from exc

    def _generate_candidate(self, ctx: MetaContext) -> Candidate:
        """Ask the generator for one candidate skill design."""
        try:
            return self._generator().generate(ctx)
        except Exception as exc:
            _log.error("Generation failed: %s", exc)
            raise _CycleStageError("parse_failure", str(exc)) from exc

    def _reflect_candidate(self, candidate: Candidate, ctx: MetaContext) -> Candidate:
        """Run reflection passes and return the accepted candidate."""
        accepted = self.reflect_passes == 0
        for pass_num in range(self.reflect_passes):
            try:
                reflection = self._reflector().reflect(candidate, ctx)
            except Exception as exc:
                _log.error("Reflection pass %d failed: %s", pass_num + 1, exc)
                raise _CycleStageError(
                    "parse_failure",
                    str(exc),
                    candidate=candidate,
                ) from exc

            candidate = reflection.candidate
            if reflection.verdict == "accept":
                accepted = True
                break

        if not accepted:
            message = (
                f"Candidate still 'revise' after {self.reflect_passes} reflection pass(es)."
            )
            _log.warning(message)
            raise _CycleStageError(
                "reflect_exhausted",
                message,
                candidate=candidate,
            )
        return candidate

    @staticmethod
    def _validate_candidate(candidate: Candidate) -> None:
        """Validate candidate JSON/frontmatter before evaluation."""
        try:
            validate_candidate(candidate)
        except ValueError as exc:
            _log.error("Candidate validation failed: %s", exc)
            raise _CycleStageError(
                "parse_failure",
                str(exc),
                candidate=candidate,
            ) from exc

    def _is_duplicate(self, candidate: Candidate) -> bool:
        """Check archive dedupe and continue on non-fatal dedupe errors."""
        try:
            duplicate = is_duplicate(candidate.skill_md, self.archive_dir)
        except Exception as exc:
            _log.warning("Dedupe check failed (continuing): %s", exc)
            return False
        if duplicate:
            _log.info("Candidate is a duplicate; skipping evaluate/archive.")
        return duplicate

    def _write_candidate_skill(self, candidate: Candidate) -> Path:
        """Write the candidate SKILL.md to a temporary evaluator-readable file."""
        try:
            return _write_temp_skill(candidate.skill_md, self.temp_dir)
        except Exception as exc:
            _log.error("Failed to write temp skill file: %s", exc)
            raise _CycleStageError(
                "eval_error",
                str(exc),
                candidate=candidate,
            ) from exc

    def _evaluate_candidate(self, candidate: Candidate, temp_path: Path) -> Any:
        """Score the temporary candidate through the standard evaluator."""
        try:
            return self._evaluator().score(
                skill_path=str(temp_path),
                cache_path=self.cache_path,
                feedback_path=self.feedback_path,
                use_llm_judging=self.use_llm_judging,
            )
        except Exception as exc:
            _log.error("Evaluation failed: %s", exc)
            raise _CycleStageError(
                "eval_error",
                str(exc),
                candidate=candidate,
            ) from exc

    def _archive_candidate(
        self,
        candidate: Candidate,
        temp_path: Path,
        eval_result: Any,
    ) -> str | None:
        """Archive the evaluated candidate and return the assigned skill ID."""
        try:
            record = BaselineEvaluationRecord(skill_path=str(temp_path), result=eval_result)
            index_dict = self._archive_service().archive_records(
                records=[record],
                source_type=_META_SOURCE_TYPE,
                context=_archive_context(
                    cache_path=self.cache_path,
                    feedback_path=self.feedback_path,
                    design_goal=self.design_goal,
                    reflect_passes=self.reflect_passes,
                    use_llm_judging=self.use_llm_judging,
                ),
            )
        except Exception as exc:
            _log.error("Archive failed: %s", exc)
            raise _CycleStageError(
                "eval_error",
                str(exc),
                candidate=candidate,
                eval_result=eval_result,
            ) from exc

        skill_id = _find_archived_skill_id(
            index_dict=index_dict,
            source_type=_META_SOURCE_TYPE,
            skill_path=temp_path,
        )
        _log.info(
            "Cycle complete. skill_id=%s score=%.4f",
            skill_id,
            eval_result.total_score or 0.0,
        )
        return skill_id

    def _promote_if_requested(
        self,
        candidate: Candidate,
        eval_result: Any,
        skill_id: str | None,
    ) -> Any | None:
        """Promote the archive winner when this cycle is configured to deploy."""
        if not self.promote_best:
            return None
        try:
            return self._skill_promoter().promote_best_skill()
        except Exception as exc:
            _log.error("Skill promotion failed: %s", exc)
            raise _CycleStageError(
                "deploy_error",
                str(exc),
                candidate=candidate,
                eval_result=eval_result,
                skill_id=skill_id,
            ) from exc

    @staticmethod
    def _success_result(
        candidate: Candidate,
        eval_result: Any,
        skill_id: str | None,
        promotion_result: Any | None,
    ) -> CycleResult:
        """Build the successful public CycleResult shape."""
        return CycleResult(
            outcome="success",
            candidate=candidate,
            eval_result=eval_result,
            skill_id=skill_id,
            promotion_result=promotion_result,
        )

    @staticmethod
    def _cleanup_temp_skill(temp_path: Path | None) -> None:
        """Remove the temporary skill after archive/evaluation has consumed it."""
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)

    def _generator(self) -> Generator:
        """Return the injected generator or the default implementation."""
        if self.generator is None:
            self.generator = Generator()
        return self.generator

    def _reflector(self) -> Reflector:
        """Return the injected reflector or the default implementation."""
        if self.reflector is None:
            self.reflector = Reflector()
        return self.reflector

    def _evaluator(self) -> Evaluator:
        """Return the injected evaluator or the default implementation."""
        if self.evaluator is None:
            self.evaluator = Evaluator()
        return self.evaluator

    def _archive_service(self) -> ArchiveService:
        """Return the injected archive service or a default archive-backed service."""
        if self.archive_service is None:
            self.archive_service = ArchiveService(
                store=ArchiveStore(archive_dir=self.archive_dir)
            )
        return self.archive_service

    def _skill_promoter(self) -> SkillPromoter:
        """Return the injected promoter or build one from promotion settings."""
        if self.skill_promoter is None:
            promoter_kwargs: dict[str, Any] = {"archive_dir": self.archive_dir}
            if self.production_skill_path is not None:
                promoter_kwargs["production_skill_path"] = self.production_skill_path
            if self.deployment_record_path is not None:
                promoter_kwargs["deployment_store"] = DeploymentRecordStore(
                    self.deployment_record_path
                )
            self.skill_promoter = SkillPromoter(**promoter_kwargs)
        return self.skill_promoter


def run_cycle(
    cache_path: str,
    archive_dir: str = ARCHIVE_DIR,
    feedback_path: str = FEEDBACK_FILE,
    design_goal: str = "",
    temp_dir: str = META_CANDIDATE_TEMP_DIR,
    reflect_passes: int = META_REFLECT_PASSES,
    use_llm_judging: bool = META_USE_LLM_JUDGING,
    generator: Generator | None = None,
    reflector: Reflector | None = None,
    evaluator: Evaluator | None = None,
    archive_service: ArchiveService | None = None,
    skill_promoter: SkillPromoter | None = None,
    promote_best: bool = False,
    production_skill_path: str | None = None,
    deployment_record_path: str | None = None,
    context: MetaContext | None = None,
) -> CycleResult:
    """Run one full generate → reflect → validate → dedupe → evaluate → archive cycle.
    All collaborators are optional so callers can inject fakes for testing."""
    return MetaCycleRunner(
        cache_path=cache_path,
        archive_dir=archive_dir,
        feedback_path=feedback_path,
        design_goal=design_goal,
        temp_dir=temp_dir,
        reflect_passes=reflect_passes,
        use_llm_judging=use_llm_judging,
        generator=generator,
        reflector=reflector,
        evaluator=evaluator,
        archive_service=archive_service,
        skill_promoter=skill_promoter,
        promote_best=promote_best,
        production_skill_path=production_skill_path,
        deployment_record_path=deployment_record_path,
        context=context,
    ).run()
