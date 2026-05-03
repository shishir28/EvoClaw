"""
Tests for adas/evaluation/models.py
"""

from __future__ import annotations

from builders import video


class TestVideoRecordContentSource:
    def test_transcript_branch_reports_transcript_source(self):
        record = video().with_transcript("Transcript text.").with_description("Description text.").build()

        assert record.has_transcript is True
        assert record.content_source == "transcript"
        assert record.transcript_or_description == "Transcript text."

    def test_description_fallback_reports_description_source(self):
        record = video().with_transcript(None).with_description("Description text.").build()

        assert record.has_transcript is False
        assert record.content_source == "description"
        assert record.transcript_or_description == "Description text."
