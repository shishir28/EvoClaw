"""Orchestrates one generate → reflect → evaluate → archive cycle."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

try:
    from ..archive_runtime.service import ArchiveService
    from ..archive_runtime.store import ArchiveStore
    from ..baseline.models import BaselineEvaluationRecord
    from ..config import (
        ARCHIVE_DIR,
        FEEDBACK_FILE,
        META_CANDIDATE_TEMP_DIR,
        META_REFLECT_PASSES,
    )
    from ..evaluation.service import Evaluator
    from .context import build_context
    from .dedupe import is_duplicate
    from .generator import Generator
    from .models import Candidate, CycleResult, MetaContext
    from .parser import validate_candidate
    from .reflector import Reflector
except ImportError:
    from archive_runtime.service import ArchiveService
    from archive_runtime.store import ArchiveStore
    from baseline.models import BaselineEvaluationRecord
    from config import (
        ARCHIVE_DIR,
        FEEDBACK_FILE,
        META_CANDIDATE_TEMP_DIR,
        META_REFLECT_PASSES,
    )
    from evaluation.service import Evaluator
    from meta.context import build_context
    from meta.dedupe import is_duplicate
    from meta.generator import Generator
    from meta.models import Candidate, CycleResult, MetaContext
    from meta.parser import validate_candidate
    from meta.reflector import Reflector

_log = logging.getLogger(__name__)
_META_SOURCE_TYPE = "meta-agent"


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
) -> dict[str, Any]:
    """Package cycle-level parameters into the context dict stored with each archive entry.
    Stored verbatim so the archive record is self-describing for later inspection."""
    return {
        "cache_path": cache_path,
        "feedback_path": feedback_path,
        "design_goal": design_goal,
        "reflect_passes": reflect_passes,
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


def run_cycle(
    cache_path: str,
    archive_dir: str = ARCHIVE_DIR,
    feedback_path: str = FEEDBACK_FILE,
    design_goal: str = "",
    temp_dir: str = META_CANDIDATE_TEMP_DIR,
    reflect_passes: int = META_REFLECT_PASSES,
    generator: Generator | None = None,
    reflector: Reflector | None = None,
    evaluator: Evaluator | None = None,
    archive_service: ArchiveService | None = None,
    context: MetaContext | None = None,
) -> CycleResult:
    """Run one full generate → reflect → validate → dedupe → evaluate → archive cycle.
    All collaborators are optional so callers can inject fakes for testing."""
    if reflect_passes < 0:
        raise ValueError("reflect_passes must be >= 0.")
    gen = generator or Generator()
    ref = reflector or Reflector()
    ev = evaluator or Evaluator()
    archive_svc = archive_service or ArchiveService(
        store=ArchiveStore(archive_dir=archive_dir)
    )

    # Step 1: Build context.
    try:
        ctx = context or build_context(
            archive_dir=archive_dir,
            feedback_path=feedback_path,
            design_goal=design_goal,
        )
    except Exception as exc:
        _log.error("Context build failed: %s", exc)
        return CycleResult(outcome="parse_failure", error=str(exc))

    # Step 2: Generate candidate.
    try:
        candidate = gen.generate(ctx)
    except Exception as exc:
        _log.error("Generation failed: %s", exc)
        return CycleResult(outcome="parse_failure", error=str(exc))

    # Step 3: Reflect (up to reflect_passes).
    accepted = reflect_passes == 0
    for pass_num in range(reflect_passes):
        try:
            reflection = ref.reflect(candidate, ctx)
        except Exception as exc:
            _log.error("Reflection pass %d failed: %s", pass_num + 1, exc)
            return CycleResult(outcome="parse_failure", candidate=candidate, error=str(exc))

        candidate = reflection.candidate
        if reflection.verdict == "accept":
            accepted = True
            break

    if not accepted:
        _log.warning(
            "Candidate still 'revise' after %d reflection pass(es).", reflect_passes
        )
        return CycleResult(
            outcome="reflect_exhausted",
            candidate=candidate,
            error=f"Candidate still 'revise' after {reflect_passes} reflection pass(es).",
        )

    # Step 4: Local contract validation before evaluation/archive.
    try:
        validate_candidate(candidate)
    except ValueError as exc:
        _log.error("Candidate validation failed: %s", exc)
        return CycleResult(outcome="parse_failure", candidate=candidate, error=str(exc))

    # Step 5: Dedupe check.
    try:
        if is_duplicate(candidate.skill_md, archive_dir):
            _log.info("Candidate is a duplicate; skipping evaluate/archive.")
            return CycleResult(outcome="dedupe", candidate=candidate)
    except Exception as exc:
        _log.warning("Dedupe check failed (continuing): %s", exc)

    # Step 6: Write temp SKILL.md.
    temp_path: Path | None = None
    try:
        temp_path = _write_temp_skill(candidate.skill_md, temp_dir)
    except Exception as exc:
        _log.error("Failed to write temp skill file: %s", exc)
        return CycleResult(outcome="eval_error", candidate=candidate, error=str(exc))

    try:
        # Step 7: Evaluate.
        try:
            eval_result = ev.score(
                skill_path=str(temp_path),
                cache_path=cache_path,
                feedback_path=feedback_path,
            )
        except Exception as exc:
            _log.error("Evaluation failed: %s", exc)
            return CycleResult(outcome="eval_error", candidate=candidate, error=str(exc))

        # Step 8: Archive.
        try:
            record = BaselineEvaluationRecord(
                skill_path=str(temp_path), result=eval_result
            )
            index_dict = archive_svc.archive_records(
                records=[record],
                source_type=_META_SOURCE_TYPE,
                context=_archive_context(
                    cache_path=cache_path,
                    feedback_path=feedback_path,
                    design_goal=design_goal,
                    reflect_passes=reflect_passes,
                ),
            )
        except Exception as exc:
            _log.error("Archive failed: %s", exc)
            return CycleResult(
                outcome="eval_error",
                candidate=candidate,
                eval_result=eval_result,
                error=str(exc),
            )

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
        return CycleResult(
            outcome="success",
            candidate=candidate,
            eval_result=eval_result,
            skill_id=skill_id,
        )

    finally:
        # The archive service copies the skill contents immediately, so the
        # temporary candidate file can always be removed once this function exits.
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
