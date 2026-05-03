"""
pytest fixtures for adas tests.
Builders and factories live in builders.py and are imported here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make builders.py importable from this directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from builders import video, FeedbackFactory
from evaluation.models import VideoRecord


@pytest.fixture
def three_diverse_videos() -> list[VideoRecord]:
    return [
        video().with_id("v1").with_channel("TechTalks", "ch1")
               .with_title("Building LLM agents for SaaS").with_age_hours(10.0).build(),
        video().with_id("v2").with_channel("StartupRadio", "ch2")
               .with_title("Fundraising for AI founders").with_age_hours(20.0).build(),
        video().with_id("v3").with_channel("VentureBytes", "ch3")
               .with_title("GPT product launch playbook").with_age_hours(30.0).build(),
    ]


@pytest.fixture
def three_same_channel_videos() -> list[VideoRecord]:
    return [
        video().with_id(f"s{i}").with_channel("SameChannel", "ch_same")
               .with_title(f"AI startup tips part {i + 1}").with_age_hours(float((i + 1) * 10))
               .build()
        for i in range(3)
    ]
