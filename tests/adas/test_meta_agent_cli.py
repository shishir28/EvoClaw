"""CLI tests for adas.meta_agent."""

from __future__ import annotations

import json

from adas.meta.models import Candidate, CycleResult
import adas.meta_agent as meta_agent


_CANDIDATE = Candidate(
    thought="cli test",
    name="cli-skill",
    skill_md="---\nname: cli-skill\nversion: \"1.0\"\nstrategy: recency\ndescription: d\nauthor: adas-meta\nscore: null\n---\n",
)


def test_reflect_passes_forwarded(monkeypatch, capsys):
    calls: list[dict[str, object]] = []

    def _fake_run_cycle(**kwargs):
        calls.append(kwargs)
        return CycleResult(outcome="success", candidate=_CANDIDATE, skill_id="skill_999")

    monkeypatch.setattr(meta_agent, "run_cycle", _fake_run_cycle)
    monkeypatch.setattr(
        "sys.argv",
        [
            "meta_agent.py",
            "--cache",
            "adas/test_sets/video_cache_w1.json",
            "--reflect-passes",
            "2",
        ],
    )

    meta_agent.main()

    assert calls[0]["reflect_passes"] == 2
    assert calls[0]["use_llm_judging"] is True
    output = json.loads(capsys.readouterr().out)
    assert output[0]["outcome"] == "success"


def test_cycles_runs_multiple_times(monkeypatch, capsys):
    call_count = {"count": 0}

    def _fake_run_cycle(**kwargs):
        call_count["count"] += 1
        return CycleResult(outcome="success", candidate=_CANDIDATE)

    monkeypatch.setattr(meta_agent, "run_cycle", _fake_run_cycle)
    monkeypatch.setattr(
        "sys.argv",
        [
            "meta_agent.py",
            "--cache",
            "adas/test_sets/video_cache_w1.json",
            "--cycles",
            "2",
        ],
    )

    meta_agent.main()

    assert call_count["count"] == 2
    output = json.loads(capsys.readouterr().out)
    assert len(output) == 2


def test_deploy_best_flags_forwarded(monkeypatch, capsys):
    calls: list[dict[str, object]] = []

    def _fake_run_cycle(**kwargs):
        calls.append(kwargs)
        return CycleResult(outcome="success", candidate=_CANDIDATE)

    monkeypatch.setattr(meta_agent, "run_cycle", _fake_run_cycle)
    monkeypatch.setattr(
        "sys.argv",
        [
            "meta_agent.py",
            "--cache",
            "adas/test_sets/video_cache_w1.json",
            "--deploy-best",
            "--production-skill",
            "/tmp/youtube-curator/SKILL.md",
            "--deployment-record",
            "/tmp/youtube-curator/deployment.json",
        ],
    )

    meta_agent.main()

    assert calls[0]["promote_best"] is True
    assert calls[0]["production_skill_path"] == "/tmp/youtube-curator/SKILL.md"
    assert calls[0]["deployment_record_path"] == "/tmp/youtube-curator/deployment.json"
    output = json.loads(capsys.readouterr().out)
    assert output[0]["outcome"] == "success"


def test_no_llm_judge_flag_forwarded(monkeypatch, capsys):
    calls: list[dict[str, object]] = []

    def _fake_run_cycle(**kwargs):
        calls.append(kwargs)
        return CycleResult(outcome="success", candidate=_CANDIDATE)

    monkeypatch.setattr(meta_agent, "run_cycle", _fake_run_cycle)
    monkeypatch.setattr(
        "sys.argv",
        [
            "meta_agent.py",
            "--cache",
            "adas/test_sets/video_cache_w1.json",
            "--no-llm-judge",
        ],
    )

    meta_agent.main()

    assert calls[0]["use_llm_judging"] is False
    output = json.loads(capsys.readouterr().out)
    assert output[0]["outcome"] == "success"
