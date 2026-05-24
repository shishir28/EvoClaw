"""
Tests for adas/skill_executor.py

Each test class covers one executor or one filtering function.
Private helpers (_looks_english, _is_relevant, _subscriber_floor) are tested
directly because they encode the critical filtering rules.
"""

from __future__ import annotations

import pytest

from evaluation.executor import (
    BaselineSkillExecutor,
    EngagementVelocityStrategyExecutor,
    RecencyStrategyExecutor,
    SubstanceProxyStrategyExecutor,
    _is_relevant,
    _looks_english,
    _subscriber_floor,
)
from builders import video, skill


# ---------------------------------------------------------------------------
# _looks_english
# ---------------------------------------------------------------------------

class TestLooksEnglish:
    def test_plain_english_passes(self):
        v = video().with_title("How to Build an AI Startup in 2026").build()
        assert _looks_english(v) is True

    def test_vietnamese_fails(self):
        v = (video().with_title("Học máy và khởi nghiệp AI")
                    .with_description("Hướng dẫn cho người sáng lập.")
                    .with_query_matched("general").build())
        assert _looks_english(v) is False

    def test_arabic_fails(self):
        v = (video().with_title("الذكاء الاصطناعي للشركات الناشئة")
                    .with_description("دليل للمؤسسين.")
                    .with_query_matched("general").build())
        assert _looks_english(v) is False

    def test_hindi_fails(self):
        v = (video().with_title("एआई स्टार्टअप कैसे बनाएं")
                    .with_description("संस्थापकों के लिए मार्गदर्शिका।")
                    .with_query_matched("general").build())
        assert _looks_english(v) is False

    def test_chinese_fails(self):
        v = (video().with_title("如何建立AI创业公司")
                    .with_description("创始人实用指南。")
                    .with_query_matched("general").build())
        assert _looks_english(v) is False

    def test_empty_title_and_description_passes(self):
        v = video().with_title("").with_description("").build()
        assert _looks_english(v) is True

    def test_english_with_punctuation_passes(self):
        v = video().with_title("AI Startup: 10x Growth — What Works").build()
        assert _looks_english(v) is True

    def test_non_english_audio_language_fails(self):
        v = (video().with_title("AI startup founder interview")
                    .with_default_audio_language("te-IN").build())
        assert _looks_english(v) is False

    def test_latin_script_tamil_metadata_fails(self):
        v = (video().with_title("It is Completely About Ai | SINGAM KALAM ERANGIRUCHU")
                    .with_description("StartupSingam TamilStartups Entrepreneurship")
                    .with_tags(["ai", "entrepreneurship", "tamil"]).build())
        assert _looks_english(v) is False

    def test_latin_script_hindi_description_fails(self):
        v = (video().with_title("Google Just KILLED AI Startups")
                    .with_description("Google I/O 2026 ne AI industry ko hila diya. Is video mein maine breakdown kiye.").build())
        assert _looks_english(v) is False


# ---------------------------------------------------------------------------
# _is_relevant
# ---------------------------------------------------------------------------

class TestIsRelevant:
    @pytest.mark.parametrize("title,description", [
        ("Building an AI startup", "Founder tips."),
        ("LLM for SaaS products", "Product tips."),
        ("Using Claude for startup automation", "Entrepreneur workflow."),
        ("AGI and entrepreneurship", "Founder perspective."),
    ])
    def test_relevant_combinations_pass(self, title: str, description: str):
        v = video().with_title(title).with_description(description).build()
        assert _is_relevant(v) is True

    def test_ai_term_only_fails(self):
        v = (video().with_title("New machine learning paper")
                    .with_description("Academic research notes.")
                    .with_query_matched("general").build())
        assert _is_relevant(v) is False

    def test_business_term_only_fails(self):
        v = (video().with_title("How to raise funding")
                    .with_description("Fundraising tips for charities.")
                    .with_query_matched("general").build())
        assert _is_relevant(v) is False

    def test_neither_term_fails(self):
        v = (video().with_title("Cooking tutorial")
                    .with_description("Best pasta recipes.")
                    .with_query_matched("general").build())
        assert _is_relevant(v) is False

    def test_tags_contribute_to_relevance(self):
        v = (video().with_title("Weekly vlog").with_description("My week.")
                    .with_tags(["ai", "founder"]).with_query_matched("general").build())
        assert _is_relevant(v) is True


# ---------------------------------------------------------------------------
# _subscriber_floor
# ---------------------------------------------------------------------------

class TestSubscriberFloor:
    def test_above_threshold_passes(self):
        assert _subscriber_floor(video().with_subscriber_count(50_000).build(), 10_000) is True

    def test_exactly_at_threshold_passes(self):
        assert _subscriber_floor(video().with_subscriber_count(10_000).build(), 10_000) is True

    def test_below_threshold_fails(self):
        assert _subscriber_floor(video().with_subscriber_count(5_000).build(), 10_000) is False

    def test_none_subscriber_count_always_passes(self):
        assert _subscriber_floor(video().with_subscriber_count(None).build(), 10_000) is True


# ---------------------------------------------------------------------------
# RecencyStrategyExecutor
# ---------------------------------------------------------------------------

class TestRecencyStrategyExecutor:
    executor = RecencyStrategyExecutor()

    def _english_relevant_pool(self, count: int, hours_step: float = 8.0) -> list:
        return [
            video().with_id(f"r{i}").with_channel("TechCasts", f"ch{i}")
                   .with_title("AI startup entrepreneur tips")
                   .with_description("Founder guide.")
                   .with_age_hours(hours_step * (i + 1))
                   .with_subscriber_count(5_000)
                   .build()
            for i in range(count)
        ]

    def test_selects_exactly_3_from_48h_window(self):
        pool = self._english_relevant_pool(6, hours_step=6.0)
        result = self.executor.execute(pool)
        assert len(result.selected_video_ids) == 3

    def test_selected_are_the_3_newest_within_48h(self):
        pool = self._english_relevant_pool(6, hours_step=6.0)
        result = self.executor.execute(pool)
        assert set(result.selected_video_ids) == {"r0", "r1", "r2"}

    def test_prefers_videos_at_least_5_minutes_long(self):
        shorts = [
            video().with_id(f"short{i}").with_channel("Shorts", f"sch{i}")
                   .with_title("AI startup entrepreneur tips")
                   .with_description("Founder guide.")
                   .with_age_hours(float(i + 1))
                   .with_duration_seconds(60)
                   .with_subscriber_count(5_000)
                   .build()
            for i in range(3)
        ]
        longer = [
            video().with_id(f"long{i}").with_channel("TechCasts", f"lch{i}")
                   .with_title("AI startup entrepreneur tips")
                   .with_description("Founder guide.")
                   .with_age_hours(float(10 + i))
                   .with_duration_seconds(600)
                   .with_subscriber_count(5_000)
                   .build()
            for i in range(3)
        ]
        result = self.executor.execute(shorts + longer)
        assert set(result.selected_video_ids) == {"long0", "long1", "long2"}
        assert any("at least 5 minutes" in note for note in result.notes)

    def test_duration_preference_falls_back_when_pool_too_sparse(self):
        shorts = [
            video().with_id(f"short{i}").with_channel("Shorts", f"sch{i}")
                   .with_title("AI startup entrepreneur tips")
                   .with_description("Founder guide.")
                   .with_age_hours(float(i + 1))
                   .with_duration_seconds(60)
                   .with_subscriber_count(5_000)
                   .build()
            for i in range(3)
        ]
        longer = [
            video().with_id("long0").with_channel("TechCasts", "lch0")
                   .with_title("AI startup entrepreneur tips")
                   .with_description("Founder guide.")
                   .with_age_hours(10.0)
                   .with_duration_seconds(600)
                   .with_subscriber_count(5_000)
                   .build()
        ]
        result = self.executor.execute(shorts + longer)
        assert len(result.selected_video_ids) == 3
        assert "long0" in result.selected_video_ids
        assert any("Preferred 1 video(s)" in note for note in result.notes)

    def test_falls_back_to_7d_pool_when_under_3_in_48h(self):
        pool = self._english_relevant_pool(5, hours_step=30.0)
        result = self.executor.execute(pool)
        assert len(result.selected_video_ids) == 3
        assert any("fallback" in n.lower() or "7d" in n.lower() for n in result.notes)

    def test_non_english_video_excluded(self):
        foreign = (
            video().with_id("foreign")
                   .with_title("AI стартап новости")
                   .with_description("Советы для основателей.")
                   .with_age_hours(5.0)
                   .build()
        )
        pool = self._english_relevant_pool(3, hours_step=8.0)
        result = self.executor.execute([foreign] + pool)
        assert "foreign" not in result.selected_video_ids

    def test_irrelevant_video_excluded(self):
        irrelevant = (
            video().with_id("cooking")
                   .with_title("Best pasta recipe ever")
                   .with_description("Cook amazing pasta at home.")
                   .with_query_matched("cooking recipes")
                   .with_age_hours(5.0)
                   .build()
        )
        pool = self._english_relevant_pool(3, hours_step=8.0)
        result = self.executor.execute([irrelevant] + pool)
        assert "cooking" not in result.selected_video_ids

    def test_below_subscriber_floor_excluded(self):
        low = (
            video().with_id("lowsubs")
                   .with_title("AI startup entrepreneur tips")
                   .with_description("Founder guide.")
                   .with_age_hours(5.0)
                   .with_subscriber_count(500)
                   .build()
        )
        pool = self._english_relevant_pool(3, hours_step=8.0)
        result = self.executor.execute([low] + pool)
        assert "lowsubs" not in result.selected_video_ids


# ---------------------------------------------------------------------------
# EngagementVelocityStrategyExecutor
# ---------------------------------------------------------------------------

class TestEngagementVelocityStrategyExecutor:
    executor = EngagementVelocityStrategyExecutor()

    def _velocity_pool(self, vphs: list[float], sub_count: int = 50_000) -> list:
        return [
            video().with_id(f"ev{i}").with_channel("TechCasts", f"ch{i}")
                   .with_title("AI startup entrepreneur tips")
                   .with_description("Founder guide to building products.")
                   .with_views_per_hour(vph)
                   .with_subscriber_count(sub_count)
                   .with_age_hours(24.0)
                   .build()
            for i, vph in enumerate(vphs)
        ]

    def test_selects_top_3_by_views_per_hour(self):
        pool = self._velocity_pool([100.0, 200.0, 50.0, 300.0, 150.0])
        result = self.executor.execute(pool)
        assert set(result.selected_video_ids) == {"ev3", "ev1", "ev4"}

    def test_respects_10k_subscriber_floor(self):
        low_subs = (
            video().with_id("low_subs")
                   .with_title("AI startup entrepreneur tips")
                   .with_description("Founder guide.")
                   .with_views_per_hour(9999.0)
                   .with_subscriber_count(5_000)
                   .with_age_hours(24.0)
                   .build()
        )
        pool = self._velocity_pool([10.0, 20.0, 30.0])
        result = self.executor.execute([low_subs] + pool)
        assert "low_subs" not in result.selected_video_ids

    def test_falls_back_to_1k_floor_when_primary_pool_too_small(self):
        fallback_pool = [
            video().with_id(f"fallback{i}").with_channel("TechCasts", f"ch{i}")
                   .with_title("AI startup entrepreneur tips")
                   .with_description("Founder guide.")
                   .with_views_per_hour(float(10 - i))
                   .with_subscriber_count(2_000)
                   .with_age_hours(24.0)
                   .build()
            for i in range(3)
        ]
        result = self.executor.execute(fallback_pool)
        assert len(result.selected_video_ids) == 3
        assert any("fallback" in n.lower() or "1,000" in n for n in result.notes)


# ---------------------------------------------------------------------------
# SubstanceProxyStrategyExecutor
# ---------------------------------------------------------------------------

class TestSubstanceProxyStrategyExecutor:
    executor = SubstanceProxyStrategyExecutor()

    def _substance_pool(self, count: int = 5) -> list:
        return [
            video().with_id(f"sp{i}").with_channel("TechCasts", f"ch{i}")
                   .with_title("AI startup entrepreneur")
                   .with_description("Founder guide." * 5)
                   .with_transcript("Full transcript here." * 20)
                   .with_duration_seconds(900)
                   .with_age_hours(24.0)
                   .build()
            for i in range(count)
        ]

    def test_selects_exactly_3(self):
        result = self.executor.execute(self._substance_pool())
        assert len(result.selected_video_ids) == 3

    def test_prefers_video_with_transcript_over_one_without(self):
        no_tx = (
            video().with_id("no_tx").with_channel("ch_a", "ch_a")
                   .with_title("AI startup entrepreneur")
                   .with_description("Short description.")
                   .with_transcript(None)
                   .with_duration_seconds(900)
                   .with_age_hours(24.0)
                   .build()
        )
        with_tx = (
            video().with_id("with_tx").with_channel("ch_b", "ch_b")
                   .with_title("AI startup entrepreneur")
                   .with_description("Short description.")
                   .with_transcript("x" * 1500)
                   .with_duration_seconds(900)
                   .with_age_hours(24.0)
                   .build()
        )
        filler = [
            video().with_id(f"f{i}").with_channel(f"fc{i}", f"fc{i}")
                   .with_title("AI startup entrepreneur").with_description("Filler.")
                   .with_age_hours(24.0).build()
            for i in range(2)
        ]
        result = self.executor.execute([no_tx, with_tx] + filler)
        assert "with_tx" in result.selected_video_ids

    def test_very_short_video_penalised(self):
        short = (
            video().with_id("short").with_channel("ch_short", "ch_short")
                   .with_title("AI startup entrepreneur")
                   .with_description("x" * 500)
                   .with_duration_seconds(30)
                   .with_age_hours(24.0)
                   .build()
        )
        normal = (
            video().with_id("normal").with_channel("ch_normal", "ch_normal")
                   .with_title("AI startup entrepreneur")
                   .with_description("x" * 500)
                   .with_duration_seconds(900)
                   .with_age_hours(24.0)
                   .build()
        )
        filler = [
            video().with_id(f"f{i}").with_channel(f"fc{i}", f"fc{i}")
                   .with_title("AI startup entrepreneur").with_description("x" * 500)
                   .with_duration_seconds(600).with_age_hours(24.0).build()
            for i in range(2)
        ]
        result = self.executor.execute([short, normal] + filler)
        assert "normal" in result.selected_video_ids


# ---------------------------------------------------------------------------
# BaselineSkillExecutor (registry and routing)
# ---------------------------------------------------------------------------

class TestBaselineSkillExecutor:
    def test_unknown_strategy_raises(self):
        executor = BaselineSkillExecutor()
        s = skill().with_strategy("unknown-strategy").build()
        with pytest.raises(ValueError, match="Unsupported skill strategy"):
            executor.execute(s, [video().build()])

    def test_none_strategy_raises(self):
        executor = BaselineSkillExecutor()
        s = skill().with_strategy(None).build()
        with pytest.raises(ValueError):
            executor.execute(s, [video().build()])

    def test_duplicate_strategy_names_raise_on_construction(self):
        with pytest.raises(ValueError, match="Duplicate strategy executors"):
            BaselineSkillExecutor(strategies=[
                RecencyStrategyExecutor(),
                RecencyStrategyExecutor(),
            ])

    @pytest.mark.parametrize("strategy_name,executor_type", [
        ("recency", RecencyStrategyExecutor),
        ("engagement-velocity", EngagementVelocityStrategyExecutor),
        ("llm-substance-judge", SubstanceProxyStrategyExecutor),
    ])
    def test_routes_to_correct_strategy(self, strategy_name: str, executor_type):
        executor = BaselineSkillExecutor()
        s = skill().with_strategy(strategy_name).build()
        pool = [
            video().with_id(f"v{i}").with_channel("TechCasts", f"ch{i}")
                   .with_title("AI startup entrepreneur tips")
                   .with_description("Founder guide." * 3)
                   .with_subscriber_count(20_000)
                   .with_age_hours(float((i + 1) * 6))
                   .build()
            for i in range(4)
        ]
        result = executor.execute(s, pool)
        assert len(result.selected_video_ids) == 3
