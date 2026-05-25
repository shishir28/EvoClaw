"""
Tests for adas/algorithmic_scorer.py

Each test class maps to one public method of AlgorithmicScorer.
"""

from __future__ import annotations

import pytest

from adas.evaluation.scorer import AlgorithmicScorer
from adas.evaluation.models import FeedbackEntry, FeedbackPick
from builders import video, FeedbackFactory, make_request


scorer = AlgorithmicScorer()


# ---------------------------------------------------------------------------
# AlgorithmicScorer.score_freshness
# ---------------------------------------------------------------------------

class TestScoreFreshness:
    def test_video_under_48h_scores_above_9(self):
        v = video().with_id("v1").with_age_hours(10.0).build()
        score, _ = scorer.score_freshness([v])
        assert score > 9.0

    def test_video_exactly_at_48h_scores_6(self):
        v = video().with_id("v1").with_age_hours(48.0).build()
        score, _ = scorer.score_freshness([v])
        assert abs(score - 6.0) < 0.1

    def test_video_between_48h_and_7d_scores_between_0_and_6(self):
        v = video().with_id("v1").with_age_hours(100.0).build()
        score, _ = scorer.score_freshness([v])
        assert 0.0 <= score <= 6.0

    def test_video_over_30_days_scores_zero(self):
        v = video().with_id("v1").with_age_hours(750.0).build()
        score, _ = scorer.score_freshness([v])
        assert score == 0.0

    def test_multiple_videos_score_is_average(self):
        v1 = video().with_id("v1").with_age_hours(10.0).build()
        v2 = video().with_id("v2").with_age_hours(750.0).build()
        s1, _ = scorer.score_freshness([v1])
        s2, _ = scorer.score_freshness([v2])
        avg, _ = scorer.score_freshness([v1, v2])
        assert abs(avg - (s1 + s2) / 2) < 0.001

    def test_score_capped_at_10(self):
        v = video().with_id("v1").with_age_hours(0.5).build()
        score, _ = scorer.score_freshness([v])
        assert score <= 10.0

    def test_future_dated_video_scores_zero(self):
        v = video().with_id("v1").with_age_hours(-4.0).build()
        score, detail = scorer.score_freshness([v])
        assert score == 0.0
        assert "future publish timestamp" in detail

    def test_empty_list_raises_value_error(self):
        with pytest.raises(ValueError):
            scorer.score_freshness([])

    def test_detail_is_non_empty(self):
        v = video().with_id("v1").with_age_hours(24.0).build()
        _, detail = scorer.score_freshness([v])
        assert len(detail) > 0


# ---------------------------------------------------------------------------
# AlgorithmicScorer.score_diversity
# ---------------------------------------------------------------------------

class TestScoreDiversity:
    def test_single_video_returns_10(self):
        score, detail = scorer.score_diversity([video().build()])
        assert score == 10.0
        assert "one" in detail.lower()

    def test_three_different_channels_reported_in_detail(self, three_diverse_videos):
        _, detail = scorer.score_diversity(three_diverse_videos)
        assert "3/3" in detail

    def test_three_same_channel_reduces_channel_score(self, three_same_channel_videos):
        _, detail = scorer.score_diversity(three_same_channel_videos)
        assert "1/3" in detail

    def test_same_channel_score_below_5(self, three_same_channel_videos):
        score, _ = scorer.score_diversity(three_same_channel_videos)
        assert score < 5.0

    def test_score_in_range_0_to_10(self, three_diverse_videos):
        score, _ = scorer.score_diversity(three_diverse_videos)
        assert 0.0 <= score <= 10.0

    def test_topically_diverse_scores_higher_than_identical(self):
        identical = [
            video().with_id(f"i{n}").with_channel(f"ch{n}", f"ch{n}")
                   .with_title("AI startup funding tips")
                   .with_description("How to get venture funding for your AI startup.")
                   .build()
            for n in range(3)
        ]
        diverse = [
            video().with_id("x").with_channel("ch4", "ch4")
                   .with_title("LLM agent deployment at scale").build(),
            video().with_id("y").with_channel("ch5", "ch5")
                   .with_title("SaaS pricing strategy for founders").build(),
            video().with_id("z").with_channel("ch6", "ch6")
                   .with_title("Bootstrapping vs venture funding").build(),
        ]
        assert scorer.score_diversity(diverse)[0] > scorer.score_diversity(identical)[0]

    def test_empty_list_raises_value_error(self):
        with pytest.raises(ValueError):
            scorer.score_diversity([])


# ---------------------------------------------------------------------------
# AlgorithmicScorer.score_alignment
# ---------------------------------------------------------------------------

class TestScoreAlignment:
    def test_no_feedback_returns_neutral_5(self, three_diverse_videos):
        request = make_request(videos=three_diverse_videos, feedback_history=[])
        score, detail = scorer.score_alignment(request, three_diverse_videos)
        assert score == 5.0
        assert "neutral" in detail.lower()

    def test_all_thumbs_up_returns_10(self, three_diverse_videos):
        ids = [v.video_id for v in three_diverse_videos]
        request = make_request(
            videos=three_diverse_videos,
            feedback_history=FeedbackFactory.all_up(ids),
        )
        score, detail = scorer.score_alignment(request, three_diverse_videos)
        assert score == 10.0
        assert "exact historical match" in detail

    def test_all_thumbs_down_returns_0(self, three_diverse_videos):
        ids = [v.video_id for v in three_diverse_videos]
        request = make_request(
            videos=three_diverse_videos,
            feedback_history=FeedbackFactory.all_down(ids),
        )
        score, _ = scorer.score_alignment(request, three_diverse_videos)
        assert score == 0.0

    def test_unrelated_video_gets_neutral_score(self, three_diverse_videos):
        ids = [v.video_id for v in three_diverse_videos]
        unknown = (
            video()
            .with_id("unknown_vid")
            .with_title("Space exploration documentary")
            .with_description("Astronomy and rockets.")
            .with_tags(["space", "mars"])
            .with_query_matched("space documentary")
            .with_channel("SpaceTV", "space_ch")
            .build()
        )
        request = make_request(
            videos=three_diverse_videos + [unknown],
            feedback_history=FeedbackFactory.all_up(ids),
        )
        score, detail = scorer.score_alignment(request, [unknown])
        assert score == 5.0
        assert "neutral" in detail

    def test_mixed_up_down_none_averages_to_5_on_exact_matches(self, three_diverse_videos):
        request = make_request(
            videos=three_diverse_videos,
            feedback_history=FeedbackFactory.mixed({"v1": "up", "v2": "down", "v3": None}),
        )
        score, _ = scorer.score_alignment(request, three_diverse_videos)
        assert abs(score - 5.0) < 0.001

    def test_empty_videos_list_raises_value_error(self):
        request = make_request()
        with pytest.raises(ValueError):
            scorer.score_alignment(request, [])

    def test_topic_and_duration_similarity_to_liked_video_scores_above_neutral(self):
        historical = (
            video()
            .with_id("liked")
            .with_title("AI startup pricing tactics")
            .with_description("Practical founder pricing playbook.")
            .with_channel("FoundersFM", "ch_like")
            .with_duration_seconds(720)
            .build()
        )
        candidate = (
            video()
            .with_id("candidate")
            .with_title("AI startup pricing strategy")
            .with_description("Founder pricing lessons and tactics.")
            .with_channel("NewChannel", "ch_new")
            .with_duration_seconds(780)
            .build()
        )
        request = make_request(
            videos=[historical, candidate],
            feedback_history=FeedbackFactory.all_up(["liked"]),
        )

        score, detail = scorer.score_alignment(request, [candidate])

        assert score > 5.0
        assert "liked precedent" in detail

    def test_channel_match_to_disliked_video_scores_below_neutral(self):
        historical = (
            video()
            .with_id("disliked")
            .with_title("AI hype for founders")
            .with_description("Generic advice.")
            .with_channel("HotTakes", "same_channel")
            .build()
        )
        candidate = (
            video()
            .with_id("candidate")
            .with_title("Another founder hot take")
            .with_description("More generic advice.")
            .with_channel("HotTakes", "same_channel")
            .build()
        )
        request = make_request(
            videos=[historical, candidate],
            feedback_history=FeedbackFactory.all_down(["disliked"]),
        )

        score, detail = scorer.score_alignment(request, [candidate])

        assert score < 5.0
        assert "channel match" in detail

    @pytest.mark.parametrize("reaction,expected", [
        ("up", 10.0), ("thumbs_up", 10.0), ("like", 10.0),
        ("liked", 10.0), ("positive", 10.0), ("👍", 10.0),
        ("down", 0.0), ("thumbs_down", 0.0), ("dislike", 0.0),
        ("disliked", 0.0), ("negative", 0.0), ("👎", 0.0),
    ])
    def test_reaction_string_variants(self, reaction: str, expected: float):
        v = video().with_id("v1").build()
        feedback = [FeedbackEntry(
            date="2026-04-30",
            picks=[FeedbackPick(video_id="v1", reaction=reaction)],
        )]
        request = make_request(videos=[v], feedback_history=feedback)
        score, _ = scorer.score_alignment(request, [v])
        assert score == expected
