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

try:
    from adas.config import (
        ARCHIVE_DIR,
        FEEDBACK_FILE,
        META_MAX_CYCLES,
        META_REFLECT_PASSES,
    )
    from adas.meta.loop import run_cycle
except ImportError:
    from config import ARCHIVE_DIR, FEEDBACK_FILE, META_MAX_CYCLES, META_REFLECT_PASSES
    from meta.loop import run_cycle

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stderr,
)
_log = logging.getLogger(__name__)


def main() -> None:
    """Parse CLI args, drive N generate→reflect→evaluate→archive cycles, and
    print the list of CycleResult dicts as JSON to stdout."""
    parser = argparse.ArgumentParser(
        description="Run meta-agent generate→reflect→evaluate→archive cycle(s)."
    )
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
    args = parser.parse_args()

    results = []
    for cycle_num in range(args.cycles):
        _log.info("Starting cycle %d/%d.", cycle_num + 1, args.cycles)
        result = run_cycle(
            cache_path=args.cache,
            archive_dir=args.archive_dir,
            feedback_path=args.feedback,
            design_goal=args.design_goal,
            reflect_passes=args.reflect_passes,
        )
        result_dict = result.to_dict()
        results.append(result_dict)
        _log.info(
            "Cycle %d: outcome=%s skill_id=%s score=%s",
            cycle_num + 1,
            result.outcome,
            result.skill_id,
            result.eval_result.total_score if result.eval_result else None,
        )

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
