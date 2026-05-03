"""
CLI entrypoint and compatibility wrapper for evaluator orchestration.
"""

try:
    from adas.evaluation.judge import LLMJudge as LLMJudge
    from adas.evaluation.service import (
        Evaluator as _BaseEvaluator,
        _build_cli_output,
        _parse_cli_selected_ids,
        main,
    )
except ModuleNotFoundError:
    from evaluation.judge import LLMJudge as LLMJudge  # type: ignore
    from evaluation.service import (  # type: ignore
        Evaluator as _BaseEvaluator,
        _build_cli_output,
        _parse_cli_selected_ids,
        main,
    )


class Evaluator(_BaseEvaluator):
    def _get_llm_judge(self) -> LLMJudge:  # type: ignore[override]
        if self._llm_judge is None:
            self._llm_judge = LLMJudge()
        return self._llm_judge


if __name__ == "__main__":
    main()
