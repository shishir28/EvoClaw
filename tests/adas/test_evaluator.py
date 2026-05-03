"""
Tests for adas/evaluator.py

Each test class maps to one public method of Evaluator.
Dependencies (loader, executor, scorer, judge) are injected via their
Protocol interfaces — tests use lightweight stubs, not the real
implementations, to keep scope focused on Evaluator orchestration.
"""

from __future__ import annotations

from typing import Protocol

import pytest

from evaluator import Evaluator
from evaluator_models import DimensionScore, EvaluationResult, SkillDocument, VideoRecord
from skill_executor import SkillExecutionResult
from config import SCORE_WEIGHTS
from builders import video, skill, make_request, make_result


ALL_DIMENSIONS = list(SCORE_WEIGHTS.keys())


# ---------------------------------------------------------------------------
# Stub implementations (Dependency Inversion)
# ---------------------------------------------------------------------------

class _StubExecutor:
    """Returns a fixed set of selected video IDs without running real strategy logic."""

    def __init__(self, selected_ids: list[str]) -> None:
        self._selected_ids = selected_ids

    def execute(self, skill_doc: SkillDocument, videos: list[VideoRecord]) -> SkillExecutionResult:
        return SkillExecutionResult(selected_video_ids=self._selected_ids, notes=["stub"])


# ---------------------------------------------------------------------------
# Evaluator.resolve_selected_videos
# ---------------------------------------------------------------------------

class TestResolveSelectedVideos:
    evaluator = Evaluator()

    def test_returns_videos_in_requested_order(self):
        videos = [video().with_id(f"v{i}").build() for i in range(3)]
        request = make_request(videos=videos)
        resolved = self.evaluator.resolve_selected_videos(request, ["v2", "v0", "v1"])
        assert [v.video_id for v in resolved] == ["v2", "v0", "v1"]

    def test_raises_for_unknown_video_id(self):
        request = make_request(videos=[video().with_id("v1").build()])
        with pytest.raises(ValueError, match="not found in cache"):
            self.evaluator.resolve_selected_videos(request, ["v1", "unknown"])

    def test_raises_for_duplicate_ids(self):
        request = make_request(videos=[video().with_id("v1").build()])
        with pytest.raises(ValueError, match="duplicates"):
            self.evaluator.resolve_selected_videos(request, ["v1", "v1"])

    def test_raises_for_empty_list(self):
        request = make_request()
        with pytest.raises(ValueError):
            self.evaluator.resolve_selected_videos(request, [])


# ---------------------------------------------------------------------------
# Evaluator.apply_dimension_scores
# ---------------------------------------------------------------------------

class TestApplyDimensionScores:
    evaluator = Evaluator()

    def test_applies_valid_scores(self):
        result = make_result()
        self.evaluator.apply_dimension_scores(result, {"freshness": 8.0, "diversity": 7.5})
        dm = result.dimension_map()
        assert dm["freshness"].score == 8.0
        assert dm["diversity"].score == 7.5

    def test_score_rounded_to_4_decimal_places(self):
        result = make_result()
        self.evaluator.apply_dimension_scores(result, {"freshness": 7.123456789})
        assert result.dimension_map()["freshness"].score == 7.1235

    def test_detail_stored_correctly(self):
        result = make_result()
        self.evaluator.apply_dimension_scores(
            result, {"freshness": 8.0}, details={"freshness": "very fresh"}
        )
        assert result.dimension_map()["freshness"].detail == "very fresh"

    @pytest.mark.parametrize("score", [0.0, 10.0])
    def test_boundary_scores_accepted(self, score: float):
        result = make_result()
        self.evaluator.apply_dimension_scores(result, {"freshness": score})
        assert result.dimension_map()["freshness"].score == score

    def test_score_above_10_raises(self):
        result = make_result()
        with pytest.raises(ValueError, match="between 0 and 10"):
            self.evaluator.apply_dimension_scores(result, {"freshness": 10.001})

    def test_negative_score_raises(self):
        result = make_result()
        with pytest.raises(ValueError, match="between 0 and 10"):
            self.evaluator.apply_dimension_scores(result, {"freshness": -0.001})

    def test_unknown_dimension_in_scores_raises(self):
        result = make_result()
        with pytest.raises(ValueError, match="Unknown dimension"):
            self.evaluator.apply_dimension_scores(result, {"nonexistent": 5.0})

    def test_unknown_dimension_in_details_raises(self):
        result = make_result()
        with pytest.raises(ValueError, match="Unknown dimension"):
            self.evaluator.apply_dimension_scores(result, {}, details={"nonexistent": "x"})


# ---------------------------------------------------------------------------
# Evaluator.aggregate_weighted_score
# ---------------------------------------------------------------------------

class TestAggregateWeightedScore:
    evaluator = Evaluator()

    def _fully_scored(self, scores: dict[str, float] | None = None) -> EvaluationResult:
        defaults = {dim: 8.0 for dim in ALL_DIMENSIONS}
        result = make_result()
        self.evaluator.apply_dimension_scores(result, {**defaults, **(scores or {})})
        return result

    def test_correct_weighted_sum(self):
        scores = {dim: float(i + 1) for i, dim in enumerate(SCORE_WEIGHTS)}
        result = self._fully_scored(scores)
        self.evaluator.aggregate_weighted_score(result)
        expected = round(sum(SCORE_WEIGHTS[d] * scores[d] for d in SCORE_WEIGHTS), 4)
        assert abs(result.total_score - expected) < 0.0001

    def test_all_tens_gives_10(self):
        result = self._fully_scored({dim: 10.0 for dim in ALL_DIMENSIONS})
        self.evaluator.aggregate_weighted_score(result)
        assert abs(result.total_score - 10.0) < 0.001

    def test_all_zeros_gives_0(self):
        result = self._fully_scored({dim: 0.0 for dim in ALL_DIMENSIONS})
        self.evaluator.aggregate_weighted_score(result)
        assert result.total_score == 0.0

    def test_status_set_to_scored(self):
        result = self._fully_scored()
        self.evaluator.aggregate_weighted_score(result)
        assert result.status == "scored"

    def test_missing_score_raises(self):
        result = make_result()
        self.evaluator.apply_dimension_scores(result, {"freshness": 8.0})
        with pytest.raises(ValueError, match="without values for"):
            self.evaluator.aggregate_weighted_score(result)

    def test_weights_not_summing_to_1_raises(self):
        bad_weights = {dim: 0.1 for dim in ALL_DIMENSIONS}  # sums to 0.6
        ev = Evaluator(score_weights=bad_weights)
        result = EvaluationResult(
            skill_name="test", strategy="recency", cache_path="/fake",
            video_count=3,
            dimensions=[DimensionScore(name=d, weight=w, score=8.0)
                        for d, w in bad_weights.items()],
        )
        with pytest.raises(ValueError, match="sum to 1.0"):
            ev.aggregate_weighted_score(result)


# ---------------------------------------------------------------------------
# Evaluator.build_result_template
# ---------------------------------------------------------------------------

class TestBuildResultTemplate:
    evaluator = Evaluator()

    def test_dimension_names_match_score_weights(self):
        result = self.evaluator.build_result_template(make_request())
        assert {d.name for d in result.dimensions} == set(SCORE_WEIGHTS)

    def test_dimension_weights_match_config(self):
        result = self.evaluator.build_result_template(make_request())
        for dim in result.dimensions:
            assert dim.weight == SCORE_WEIGHTS[dim.name]

    def test_all_dimension_scores_start_none(self):
        result = self.evaluator.build_result_template(make_request())
        assert all(d.score is None for d in result.dimensions)

    def test_skill_name_from_skill_document(self):
        s = skill().with_name("my-skill").build()
        result = self.evaluator.build_result_template(make_request(skill_doc=s))
        assert result.skill_name == "my-skill"

    def test_video_count_from_request(self):
        videos = [video().with_id(f"v{i}").build() for i in range(5)]
        result = self.evaluator.build_result_template(make_request(videos=videos))
        assert result.video_count == 5


# ---------------------------------------------------------------------------
# Evaluator.pending_dimension_names
# ---------------------------------------------------------------------------

class TestPendingDimensionNames:
    evaluator = Evaluator()

    def test_all_pending_before_scoring(self):
        result = make_result()
        assert set(self.evaluator.pending_dimension_names(result)) == set(ALL_DIMENSIONS)

    def test_scored_dimensions_removed_from_pending(self):
        result = make_result()
        self.evaluator.apply_dimension_scores(result, {"freshness": 8.0, "diversity": 7.0})
        pending = self.evaluator.pending_dimension_names(result)
        assert "freshness" not in pending
        assert "diversity" not in pending

    def test_empty_when_all_scored(self):
        result = make_result()
        self.evaluator.apply_dimension_scores(result, {dim: 8.0 for dim in ALL_DIMENSIONS})
        assert self.evaluator.pending_dimension_names(result) == []


# ---------------------------------------------------------------------------
# Evaluator.score_algorithmic_dimensions (integration with AlgorithmicScorer)
# ---------------------------------------------------------------------------

class TestScoreAlgorithmicDimensions:
    evaluator = Evaluator()

    def test_freshness_diversity_alignment_are_scored(self):
        videos = [video().with_id(f"v{i}").with_channel("TechCasts", f"ch{i}").build()
                  for i in range(3)]
        request = make_request(videos=videos)
        result = self.evaluator.score_algorithmic_dimensions(
            request, ["v0", "v1", "v2"]
        )
        dm = result.dimension_map()
        assert dm["freshness"].score is not None
        assert dm["diversity"].score is not None
        assert dm["alignment"].score is not None

    def test_llm_dimensions_remain_pending(self):
        videos = [video().with_id(f"v{i}").with_channel("TechCasts", f"ch{i}").build()
                  for i in range(3)]
        request = make_request(videos=videos)
        result = self.evaluator.score_algorithmic_dimensions(
            request, ["v0", "v1", "v2"]
        )
        dm = result.dimension_map()
        assert dm["relevance"].score is None
        assert dm["substance"].score is None
        assert dm["reasoning"].score is None

    def test_status_is_partially_scored(self):
        videos = [video().with_id(f"v{i}").with_channel("TechCasts", f"ch{i}").build()
                  for i in range(3)]
        request = make_request(videos=videos)
        result = self.evaluator.score_algorithmic_dimensions(
            request, ["v0", "v1", "v2"]
        )
        assert result.status == "partially_scored"

    def test_selected_video_ids_stored_on_result(self):
        videos = [video().with_id(f"v{i}").with_channel("TechCasts", f"ch{i}").build()
                  for i in range(3)]
        request = make_request(videos=videos)
        result = self.evaluator.score_algorithmic_dimensions(
            request, ["v0", "v1", "v2"]
        )
        assert result.selected_video_ids == ["v0", "v1", "v2"]

    def test_missing_video_id_raises(self):
        videos = [video().with_id("v1").build()]
        request = make_request(videos=videos)
        with pytest.raises(ValueError, match="not found in cache"):
            self.evaluator.score_algorithmic_dimensions(request, ["v1", "missing"])
