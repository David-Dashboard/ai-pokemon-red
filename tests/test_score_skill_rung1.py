"""Unit tests for eval/score_skill_rung1.py -- the free build-correctness pre-check pinned by
reports/2026-07-03-skill-compilation-design.md §4.0. Covers the pure-stdlib auditor (audit_skill_log)
against synthetic skills.jsonl-shaped row lists, and the --dry mode end to end (no live API -- same
monkeypatch discipline as tests/test_arcagi3_world.py)."""
from __future__ import annotations

import json

from eval.score_skill_rung1 import (DEFAULT_FIXTURE, QUALIFYING_MIN_EXECUTED_STEPS, audit_skill_log,
                                    run_dry)


def _define_row(step=0, name="push", steps=None):
    return {"event": "define_skill", "step": step,
           "definition": {"name": name, "steps": steps or [{"action": "ACTION1"}]}}


def _run_row(step=1, name="push", executed_step_count=3, stop_reason="ok", world_steps_used=3):
    return {"event": "run_skill", "step": step, "name": name, "executed": [],
           "executed_step_count": executed_step_count, "stop_reason": stop_reason,
           "world_steps_used": world_steps_used}


# ---------------------------------------------------------------------------
# audit_skill_log
# ---------------------------------------------------------------------------

def test_audit_passes_on_well_formed_log():
    rows = [_define_row(), _run_row()]
    report = audit_skill_log(rows)
    assert report["auditable"] is True
    assert report["n_define_skill"] == 1
    assert report["n_run_skill"] == 1
    assert report["define_issues"] == []
    assert report["run_issues"] == []


def test_audit_flags_define_skill_missing_definition():
    rows = [{"event": "define_skill", "step": 0}]   # no "definition" key at all
    report = audit_skill_log(rows)
    assert report["auditable"] is False
    assert len(report["define_issues"]) == 1


def test_audit_flags_run_skill_missing_required_fields():
    rows = [{"event": "run_skill", "step": 1, "name": "push"}]   # missing executed/executed_step_count/etc
    report = audit_skill_log(rows)
    assert report["auditable"] is False
    assert len(report["run_issues"]) == 1


def test_audit_counts_qualifying_calls_at_the_pinned_threshold():
    rows = [_run_row(executed_step_count=QUALIFYING_MIN_EXECUTED_STEPS),
           _run_row(step=2, executed_step_count=QUALIFYING_MIN_EXECUTED_STEPS - 1)]
    report = audit_skill_log(rows)
    assert report["n_qualifying_calls"] == 1   # only the >=3 one qualifies
    assert report["insufficient_data_if_paid_run"] is False


def test_audit_flags_insufficient_data_when_zero_qualifying_calls():
    rows = [_run_row(executed_step_count=1)]
    report = audit_skill_log(rows)
    assert report["n_qualifying_calls"] == 0
    assert report["insufficient_data_if_paid_run"] is True


def test_audit_handles_empty_log():
    report = audit_skill_log([])
    assert report["n_define_skill"] == 0
    assert report["n_run_skill"] == 0
    assert report["auditable"] is True   # vacuously -- nothing malformed, just nothing logged
    assert report["insufficient_data_if_paid_run"] is True


# ---------------------------------------------------------------------------
# --dry mode: real executor, canned fixture, no live API (no ARC_API_KEY needed)
# ---------------------------------------------------------------------------

def test_dry_mode_runs_the_real_executor_against_the_canned_fixture(tmp_path):
    report = run_dry(DEFAULT_FIXTURE, str(tmp_path / "out"))
    assert report["auditable"] is True
    assert report["n_define_skill"] == 1
    assert report["n_run_skill"] == 1
    # the fixture is built so the push macro delivers (region change) after exactly 3 pushes -- a
    # qualifying call under the doc's >=3-executed-steps gate rule.
    assert report["n_qualifying_calls"] == 1


def test_dry_mode_writes_skills_jsonl_with_the_expected_stop_reason(tmp_path):
    out = str(tmp_path / "out")
    run_dry(DEFAULT_FIXTURE, out)
    with open(f"{out}/skills.jsonl", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    run_row = [r for r in rows if r["event"] == "run_skill"][0]
    assert run_row["executed_step_count"] == 3
    assert "grid_changed_in_region" in run_row["stop_reason"]


def test_dry_mode_needs_no_arc_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ARC_API_KEY", raising=False)
    report = run_dry(DEFAULT_FIXTURE, str(tmp_path / "out"))
    assert report["auditable"] is True
