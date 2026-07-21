"""Tests for tools/reconstruct_gate0_red_baseline.py -- pins the completion-row/arithmetic logic
against a committed, CI-safe trace fixture (never the private, gitignored evidence directory under
runs/gate0_human_baseline/red/) plus a synthetic input_event_times array.

Reuses eval/fixtures/gate0_red_human_attempt2_completion.jsonl -- the same fixture
tests/test_score_gate0.py already pins as "a real human completion" (the PR #121 regression fixture)
-- as a stand-in trace shape; the synthetic input_event_times below are constructed against ITS
timestamps, not the real attempt-1 evidence.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import eval.score_gate0 as scorer
import tools.reconstruct_gate0_red_baseline as m

FIXTURE_TRACE = Path("eval/fixtures/gate0_red_human_attempt2_completion.jsonl")
NEVER_COMPLETES_TRACE = Path("eval/fixtures/gate0_red_human_attempt1_no_movement.jsonl")
# Pinned by inspection: eval.score_gate0._red_success first returns True at this row of the fixture.
FIXTURE_COMPLETION_ROW = 821
FIXTURE_T_DONE = 1784594284.2743576


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_incomplete(tmp_path: Path, *, input_event_times, started_at=None, **overrides) -> Path:
    payload = {
        "schema_version": 1, "arm": "red", "role": "human", "mode": "readiness_dev",
        "player": "David",
        "started_at": started_at,
        "completed_at": "2026-07-21T00:32:54.257747+00:00",
        "rom_path": "roms/PokemonRed.gb", "rom_sha256": "a" * 64,
        "savestate_path": "runs/red_start.state", "savestate_sha256": "b" * 64,
        "oracle_path": "irrelevant/for/reconstruction.jsonl",
        "test_mode": False, "attempt_number": 1, "retake_reason": "",
        "input_event_times": input_event_times,
    }
    payload.update(overrides)
    path = tmp_path / "human_metrics.INCOMPLETE_123.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat()


# ---- find_completion_row -----------------------------------------------------------------------

def test_find_completion_row_matches_fixture_index():
    rows = _rows(FIXTURE_TRACE)
    assert m.find_completion_row(rows) == FIXTURE_COMPLETION_ROW
    assert rows[FIXTURE_COMPLETION_ROW]["t"] == FIXTURE_T_DONE


def test_find_completion_row_returns_none_when_trace_never_completes():
    rows = _rows(NEVER_COMPLETES_TRACE)
    assert m.find_completion_row(rows) is None


# ---- reconstruct() arithmetic ------------------------------------------------------------------

def test_reconstruct_pins_wall_clock_primitive_actions_and_trimming(tmp_path):
    synthetic_events = [
        1784594079.0,           # before completion
        1784594100.0,           # before completion
        FIXTURE_T_DONE,         # exactly at t_done -- inclusive boundary
        1784594290.0,           # after completion -- must be trimmed away
    ]
    incomplete_path = _write_incomplete(tmp_path, input_event_times=synthetic_events,
                                        started_at=_iso(synthetic_events[0]))

    artifact = m.reconstruct(FIXTURE_TRACE, incomplete_path)

    assert artifact["completion_row_index"] == FIXTURE_COMPLETION_ROW
    assert artifact["wall_clock_s"] == round(FIXTURE_T_DONE - synthetic_events[0], 3)
    assert artifact["primitive_actions"] == 3
    assert artifact["input_event_times"] == synthetic_events[:3]
    assert artifact["started_at"] == _iso(synthetic_events[0])
    assert artifact["completed_at"] == _iso(FIXTURE_T_DONE)


def test_reconstruct_carries_provenance_fields_and_schema(tmp_path):
    synthetic_events = [1784594079.0, FIXTURE_T_DONE]
    incomplete_path = _write_incomplete(tmp_path, input_event_times=synthetic_events,
                                        started_at=_iso(synthetic_events[0]),
                                        player="David", rom_sha256="c" * 64,
                                        savestate_sha256="d" * 64, test_mode=False)

    artifact = m.reconstruct(FIXTURE_TRACE, incomplete_path)

    assert artifact["schema_version"] == 1
    assert artifact["arm"] == "red"
    assert artifact["role"] == "human"
    assert artifact["mode"] == "readiness_dev"
    assert artifact["success"] is True
    assert artifact["failures"] == []
    assert artifact["player"] == "David"
    assert artifact["rom_sha256"] == "c" * 64
    assert artifact["savestate_sha256"] == "d" * 64
    assert artifact["attempt_number"] == 1
    assert artifact["retake_reason"] == ""
    assert artifact["reconstructed"] is True
    assert isinstance(artifact["reconstruction_method"], str) and artifact["reconstruction_method"]
    assert artifact["reconstruction_source_trace_sha256"] == hashlib.sha256(FIXTURE_TRACE.read_bytes()).hexdigest()
    assert artifact["reconstruction_source_incomplete_sha256"] == hashlib.sha256(incomplete_path.read_bytes()).hexdigest()
    assert artifact["completion_row_index"] == FIXTURE_COMPLETION_ROW
    # reconstructed_at is a real timestamp, not a placeholder
    datetime.fromisoformat(artifact["reconstructed_at"])


# ---- refusals -----------------------------------------------------------------------------------

def test_reconstruct_refuses_when_trace_never_completes(tmp_path):
    incomplete_path = _write_incomplete(tmp_path, input_event_times=[1.0], started_at=_iso(1.0))
    with pytest.raises(SystemExit, match="never reaches a _red_success completion row"):
        m.reconstruct(NEVER_COMPLETES_TRACE, incomplete_path)


def test_reconstruct_refuses_on_empty_input_event_times(tmp_path):
    incomplete_path = _write_incomplete(tmp_path, input_event_times=[])
    with pytest.raises(SystemExit, match="no input_event_times"):
        m.reconstruct(FIXTURE_TRACE, incomplete_path)


def test_reconstruct_refuses_on_clock_inversion(tmp_path):
    # first input strictly AFTER the detected completion row -- physically impossible, must refuse.
    incomplete_path = _write_incomplete(tmp_path, input_event_times=[FIXTURE_T_DONE + 5.0])
    with pytest.raises(SystemExit, match="clock inversion"):
        m.reconstruct(FIXTURE_TRACE, incomplete_path)


def test_reconstruct_refuses_on_started_at_mismatch(tmp_path):
    synthetic_events = [1784594079.0, FIXTURE_T_DONE]
    # started_at far from input_event_times[0] -- the cross-check the live rig's own semantics imply.
    incomplete_path = _write_incomplete(tmp_path, input_event_times=synthetic_events,
                                        started_at=_iso(synthetic_events[0] + 30.0))
    with pytest.raises(SystemExit, match="clock-start cross-check failed"):
        m.reconstruct(FIXTURE_TRACE, incomplete_path)


def test_reconstruct_allows_missing_started_at_field(tmp_path):
    # Cross-check only fires when the INCOMPLETE artifact actually carries started_at.
    synthetic_events = [1784594079.0, FIXTURE_T_DONE]
    incomplete_path = _write_incomplete(tmp_path, input_event_times=synthetic_events, started_at=None)
    artifact = m.reconstruct(FIXTURE_TRACE, incomplete_path)
    assert artifact["completion_row_index"] == FIXTURE_COMPLETION_ROW


def test_reconstruct_refuses_on_empty_trace(tmp_path):
    empty_trace = tmp_path / "empty.jsonl"
    empty_trace.write_text("", encoding="utf-8")
    incomplete_path = _write_incomplete(tmp_path, input_event_times=[1.0], started_at=_iso(1.0))
    with pytest.raises(SystemExit, match="no rows"):
        m.reconstruct(empty_trace, incomplete_path)


# ---- write_artifact: one-cold-attempt-per-task refusal ------------------------------------------

def test_write_artifact_refuses_existing_file(tmp_path):
    out = tmp_path / "human_metrics.json"
    out.write_text(json.dumps({"attempt_number": 1}), encoding="utf-8")
    with pytest.raises(SystemExit, match="already exists"):
        m.write_artifact({"attempt_number": 1, "reconstructed": True}, out)
    assert json.loads(out.read_text(encoding="utf-8")) == {"attempt_number": 1}


def test_write_artifact_happy_path_creates_parents(tmp_path):
    out = tmp_path / "nested" / "human_metrics.json"
    artifact = {"schema_version": 1, "arm": "red"}
    m.write_artifact(artifact, out)
    assert json.loads(out.read_text(encoding="utf-8")) == artifact


# ---- frozen source-pin loader compatibility ------------------------------------------------------

def test_reconstructed_artifact_passes_frozen_verify_sources(tmp_path):
    """The reconstructed artifact's superset schema (reconstructed/reconstruction_method/... on top
    of what eval.score_gate0._verify_sources actually reads) must stay loader-compatible -- mirrors
    tests/test_score_gate0.py::test_frozen_source_pins_load_exact_artifacts and
    tests/test_capture_gate0_baseline_red.py::test_build_metrics_artifact_passes_frozen_verify_sources,
    substituting a REAL reconstruct()-produced red_human artifact for the hand-authored one."""
    synthetic_events = [1784594079.0, FIXTURE_T_DONE]
    incomplete_path = _write_incomplete(tmp_path, input_event_times=synthetic_events,
                                        started_at=_iso(synthetic_events[0]))
    red_human = m.reconstruct(FIXTURE_TRACE, incomplete_path)

    payloads = {
        "red_agent": {"schema_version": 1, "arm": "red", "role": "agent", "mode": "readiness_dev",
                      "wall_clock_s": 100, "primitive_actions": 100, "wakes": 80,
                      "cost_usd": 4.0, "normalized_credits": 100},
        "red_human": red_human,
        "miniwob_agent": {"schema_version": 1, "arm": "miniwob", "role": "agent", "mode": "readiness_dev",
                          "wall_clock_s": 50, "primitive_actions": 20, "wakes": 40,
                          "cost_usd": 1.5, "normalized_credits": 40},
        "miniwob_human": {"schema_version": 1, "arm": "miniwob", "role": "human", "mode": "readiness_dev",
                          "wall_clock_s": 30, "primitive_actions": 12},
        "wake_boundary": {"schema_version": 1, "kind": "exact_wake_boundary", "status": "PASS"},
        "live_breaker": {"schema_version": 1, "kind": "live_credit_breaker", "status": "PASS",
                         "limit_normalized_credits": 250},
    }
    artifacts, hashes = {}, {}
    for key, payload in payloads.items():
        path = tmp_path / f"{key}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        artifacts[key] = str(path)
        hashes[key] = hashlib.sha256(path.read_bytes()).hexdigest()

    seed_path = scorer.MODES["readiness_dev"][0]
    pins = {"schema_version": 1, "mode": "readiness_dev",
            "frozen_seed_sha256": hashlib.sha256(seed_path.read_bytes()).hexdigest(),
            "artifact_paths": artifacts, "artifact_sha256": hashes}
    pins_path = tmp_path / "pins.json"
    pins_path.write_text(json.dumps(pins), encoding="utf-8")

    orig = scorer.SOURCE_PIN_FILES["readiness_dev"]
    scorer.SOURCE_PIN_FILES["readiness_dev"] = pins_path
    try:
        manifest = {"mode": "readiness_dev", "arms": {"red": {}, "miniwob": {}}}
        clean = {"leak_failures": [], "constancy_failures": [], "run_failures": [],
                 "accounting_failures": [], "wake_accounting": "PASS"}
        audits = {"red": {**clean, "wakes": 80}, "miniwob": {**clean, "wakes": 40}}
        verified, failures = scorer._verify_sources(manifest, audits)
    finally:
        scorer.SOURCE_PIN_FILES["readiness_dev"] = orig

    assert failures == []
    assert verified["metrics"]["red"]["human_wall_clock_s"] == red_human["wall_clock_s"]
    assert verified["metrics"]["red"]["human_primitive_actions"] == red_human["primitive_actions"]


# ---- CLI wiring ----------------------------------------------------------------------------------

def test_main_writes_artifact_and_prints_numbers(tmp_path, monkeypatch, capsys):
    synthetic_events = [1784594079.0, FIXTURE_T_DONE]
    incomplete_path = _write_incomplete(tmp_path, input_event_times=synthetic_events,
                                        started_at=_iso(synthetic_events[0]))
    out_path = tmp_path / "human_metrics.json"
    monkeypatch.setattr("sys.argv", ["reconstruct_gate0_red_baseline.py",
                                     "--trace", str(FIXTURE_TRACE),
                                     "--incomplete", str(incomplete_path),
                                     "--out", str(out_path)])
    rc = m.main()
    assert rc == 0
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["completion_row_index"] == FIXTURE_COMPLETION_ROW
    captured = capsys.readouterr()
    assert f"completion_row_index={FIXTURE_COMPLETION_ROW}" in captured.out
    assert "wall_clock_s=" in captured.out
    assert "primitive_actions=" in captured.out


def test_main_refuses_existing_out(tmp_path, monkeypatch):
    synthetic_events = [1784594079.0, FIXTURE_T_DONE]
    incomplete_path = _write_incomplete(tmp_path, input_event_times=synthetic_events,
                                        started_at=_iso(synthetic_events[0]))
    out_path = tmp_path / "human_metrics.json"
    out_path.write_text(json.dumps({"attempt_number": 1}), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["reconstruct_gate0_red_baseline.py",
                                     "--trace", str(FIXTURE_TRACE),
                                     "--incomplete", str(incomplete_path),
                                     "--out", str(out_path)])
    with pytest.raises(SystemExit, match="already exists"):
        m.main()
