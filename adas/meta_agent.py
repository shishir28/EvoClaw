"""Meta-agent CLI: run one or more generate→reflect→evaluate→archive cycles.

Usage:
    python3 adas/meta_agent.py --cache adas/test_sets/video_cache_w1.json
    python3 adas/meta_agent.py --cache <cache> --reflect-passes 2 --design-goal "prefer transcript"
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from adas.config import (
    ARCHIVE_DIR,
    FEEDBACK_FILE,
    META_MAX_CYCLES,
    META_REFLECT_PASSES,
    META_USE_LLM_JUDGING,
    SKILL_PRODUCTION,
)
from adas.meta.loop import run_cycle

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stderr,
)
_log = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for meta-agent cycle and promotion options."""
    parser = argparse.ArgumentParser(
        description="Run meta-agent generate→reflect→evaluate→archive cycle(s)."
    )
    _add_cycle_arguments(parser)
    _add_deployment_arguments(parser)
    return parser


def _add_cycle_arguments(parser: argparse.ArgumentParser) -> None:
    """Register generation, reflection, archive, and feedback cycle arguments."""
    parser.add_argument(
        "--cache",
        required=True,
        metavar="PATH",
        help="Path to the video cache JSON file.",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=META_MAX_CYCLES,
        metavar="N",
        help=f"Number of cycles to run (default: {META_MAX_CYCLES}).",
    )
    parser.add_argument(
        "--design-goal",
        default="",
        metavar="TEXT",
        help="Optional design-goal hint passed to the generator.",
    )
    parser.add_argument(
        "--reflect-passes",
        type=int,
        default=META_REFLECT_PASSES,
        metavar="N",
        help=f"Number of reflection passes per cycle (default: {META_REFLECT_PASSES}).",
    )
    parser.add_argument(
        "--archive-dir",
        default=ARCHIVE_DIR,
        metavar="PATH",
        help="Archive directory (default: adas/archive).",
    )
    parser.add_argument(
        "--feedback",
        default=FEEDBACK_FILE,
        metavar="PATH",
        help="Feedback JSON file (default: adas/test_sets/feedback.json).",
    )
    parser.add_argument(
        "--with-llm-judge",
        dest="use_llm_judging",
        action="store_true",
        default=META_USE_LLM_JUDGING,
        help="Use the configured LLM backend to score relevance, substance, and reasoning.",
    )
    parser.add_argument(
        "--no-llm-judge",
        dest="use_llm_judging",
        action="store_false",
        help="Skip LLM-judged dimensions and leave meta candidates partially scored.",
    )


def _add_deployment_arguments(parser: argparse.ArgumentParser) -> None:
    """Register optional production skill promotion arguments."""
    parser.add_argument(
        "--deploy-best",
        action="store_true",
        help="Promote the archive winner after each successful cycle if it beats the current deployment.",
    )
    parser.add_argument(
        "--production-skill",
        default=SKILL_PRODUCTION,
        metavar="PATH",
        help="Production SKILL.md path used with --deploy-best.",
    )
    parser.add_argument(
        "--deployment-record",
        default=None,
        metavar="PATH",
        help="Optional deployment metadata JSON path. Defaults beside the production skill.",
    )


def _run_cycles(args: argparse.Namespace) -> list[dict[str, object]]:
    """Run all requested cycles and return JSON-safe result dictionaries."""
    results = []
    for cycle_num in range(args.cycles):
        _log.info("Starting cycle %d/%d.", cycle_num + 1, args.cycles)
        result = _run_one_cycle(args)
        result_dict = result.to_dict()
        results.append(result_dict)
        _log.info(
            "Cycle %d: outcome=%s skill_id=%s score=%s",
            cycle_num + 1,
            result.outcome,
            result.skill_id,
            result.eval_result.total_score if result.eval_result else None,
        )
    return results


def _run_one_cycle(args: argparse.Namespace):
    """Forward parsed CLI arguments into one meta-agent cycle."""
    return run_cycle(
        cache_path=args.cache,
        archive_dir=args.archive_dir,
        feedback_path=args.feedback,
        design_goal=args.design_goal,
        reflect_passes=args.reflect_passes,
        use_llm_judging=args.use_llm_judging,
        promote_best=args.deploy_best,
        production_skill_path=args.production_skill,
        deployment_record_path=args.deployment_record,
    )


def main() -> None:
    """Parse CLI args, run cycles, and print CycleResult JSON to stdout."""
    args = _build_parser().parse_args()
    results = _run_cycles(args)
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
