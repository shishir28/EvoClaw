"""Tests for cron/runner.py utility functions."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Add cron/ to path so runner.py is importable directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cron"))

from runner import (
    _check_required_env,
    _expand_args,
    _find_job,
    _load_env,
    _python_executable,
)


# ---------------------------------------------------------------------------
# _load_env
# ---------------------------------------------------------------------------

class TestLoadEnv:
    def test_loads_key_value_pairs_from_env_file(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_KEY_RUNNER=hello\nANOTHER_KEY=world\n")
        monkeypatch.delenv("TEST_KEY_RUNNER", raising=False)
        monkeypatch.delenv("ANOTHER_KEY", raising=False)

        # Patch ENV_FILE inside runner module
        import runner
        original = runner.ENV_FILE
        runner.ENV_FILE = env_file
        try:
            _load_env()
        finally:
            runner.ENV_FILE = original

        assert os.environ.get("TEST_KEY_RUNNER") == "hello"
        assert os.environ.get("ANOTHER_KEY") == "world"

    def test_does_not_overwrite_existing_env_vars(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING_VAR=from_file\n")
        monkeypatch.setenv("EXISTING_VAR", "already_set")

        import runner
        original = runner.ENV_FILE
        runner.ENV_FILE = env_file
        try:
            _load_env()
        finally:
            runner.ENV_FILE = original

        assert os.environ["EXISTING_VAR"] == "already_set"

    def test_skips_comments_and_blank_lines(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("# this is a comment\n\nVALID_KEY=42\n")
        monkeypatch.delenv("VALID_KEY", raising=False)

        import runner
        original = runner.ENV_FILE
        runner.ENV_FILE = env_file
        try:
            _load_env()
        finally:
            runner.ENV_FILE = original

        assert os.environ.get("VALID_KEY") == "42"

    def test_does_nothing_when_env_file_missing(self, tmp_path):
        import runner
        original = runner.ENV_FILE
        runner.ENV_FILE = tmp_path / "nonexistent.env"
        try:
            _load_env()  # should not raise
        finally:
            runner.ENV_FILE = original


# ---------------------------------------------------------------------------
# _find_job
# ---------------------------------------------------------------------------

class TestFindJob:
    def _jobs(self):
        return [
            {"name": "morning-digest", "schedule": "0 7 * * *"},
            {"name": "adas-evolution", "schedule": "0 2 * * *"},
        ]

    def test_returns_matching_job(self):
        job = _find_job(self._jobs(), "morning-digest")
        assert job["name"] == "morning-digest"

    def test_returns_second_job(self):
        job = _find_job(self._jobs(), "adas-evolution")
        assert job["schedule"] == "0 2 * * *"

    def test_exits_with_code_1_for_unknown_job(self):
        with pytest.raises(SystemExit) as exc_info:
            _find_job(self._jobs(), "nonexistent-job")
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# _check_required_env
# ---------------------------------------------------------------------------

class TestCheckRequiredEnv:
    def test_returns_empty_when_all_vars_present(self, monkeypatch):
        monkeypatch.setenv("TOKEN_A", "abc")
        monkeypatch.setenv("TOKEN_B", "xyz")
        job = {"required_env": ["TOKEN_A", "TOKEN_B"]}

        assert _check_required_env(job) == []

    def test_returns_missing_var_names(self, monkeypatch):
        monkeypatch.delenv("MISSING_TOKEN", raising=False)
        job = {"required_env": ["MISSING_TOKEN"]}

        assert _check_required_env(job) == ["MISSING_TOKEN"]

    def test_treats_empty_string_as_missing(self, monkeypatch):
        monkeypatch.setenv("EMPTY_TOKEN", "   ")
        job = {"required_env": ["EMPTY_TOKEN"]}

        assert _check_required_env(job) == ["EMPTY_TOKEN"]

    def test_returns_empty_when_no_required_env_key(self):
        job = {"name": "my-job"}  # no required_env key
        assert _check_required_env(job) == []

    def test_returns_empty_when_required_env_is_empty_list(self):
        job = {"required_env": []}
        assert _check_required_env(job) == []

    def test_returns_all_missing_vars(self, monkeypatch):
        monkeypatch.delenv("VAR_X", raising=False)
        monkeypatch.delenv("VAR_Y", raising=False)
        job = {"required_env": ["VAR_X", "VAR_Y"]}

        missing = _check_required_env(job)
        assert set(missing) == {"VAR_X", "VAR_Y"}


# ---------------------------------------------------------------------------
# _python_executable
# ---------------------------------------------------------------------------

class TestPythonExecutable:
    def test_uses_explicit_env_override(self, monkeypatch):
        monkeypatch.setenv("EVOCLAW_PYTHON", "/usr/local/bin/python")

        assert _python_executable() == "/usr/local/bin/python"

    def test_falls_back_to_current_interpreter_when_venv_missing(self, monkeypatch, tmp_path):
        import runner
        original = runner.VENV_PYTHON
        runner.VENV_PYTHON = tmp_path / ".venv" / "bin" / "python"
        monkeypatch.delenv("EVOCLAW_PYTHON", raising=False)
        try:
            assert _python_executable() == sys.executable
        finally:
            runner.VENV_PYTHON = original


# ---------------------------------------------------------------------------
# _expand_args
# ---------------------------------------------------------------------------

class TestExpandArgs:
    def test_expands_project_root_placeholder(self, tmp_path):
        args = ["--cache", "{PROJECT_ROOT}/adas/test_sets/cache.json"]
        result = _expand_args(args, tmp_path)
        assert result[1] == f"{tmp_path}/adas/test_sets/cache.json"

    def test_leaves_flags_untouched(self, tmp_path):
        args = ["--send", "--reflect-passes", "2"]
        result = _expand_args(args, tmp_path)
        assert result == ["--send", "--reflect-passes", "2"]

    def test_leaves_numeric_strings_untouched(self, tmp_path):
        args = ["--cycles", "3"]
        result = _expand_args(args, tmp_path)
        assert result == ["--cycles", "3"]

    def test_resolves_existing_relative_path_to_absolute(self, tmp_path):
        cache_dir = tmp_path / "adas" / "test_sets"
        cache_dir.mkdir(parents=True)
        cache_file = cache_dir / "cache.json"
        cache_file.write_text("{}")
        args = ["--cache", "adas/test_sets/cache.json"]
        result = _expand_args(args, tmp_path)
        assert result[1] == str(cache_file.resolve())

    def test_multiple_placeholders_all_expanded(self, tmp_path):
        args = [
            "{PROJECT_ROOT}/skills/youtube-curator/delivery_log.json",
            "{PROJECT_ROOT}/adas/test_sets/feedback.json",
        ]
        result = _expand_args(args, tmp_path)
        assert all(str(tmp_path) in r for r in result)
        assert "{PROJECT_ROOT}" not in result[0]
        assert "{PROJECT_ROOT}" not in result[1]
