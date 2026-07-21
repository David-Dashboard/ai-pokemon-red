"""Tests for tools/capture_gate0_baseline_red.py's pure helpers + real-path safety guard.

The interactive PyBoy/SDL2 loop itself is exercised manually (never in the automated suite -- see
DAVID_BASELINES.md and the PR description): CI machines/agents must never "play" Pokemon Red, per
the HARD LAW that only a human generates the baseline's gameplay. What IS cheap and CI-safe to pin
here is the artifact-path guard, the hash helper, the atomic-write helper, the schema builder, and
the overwrite-refusal/setup-failure guards that fire BEFORE (or instead of) any real PyBoy/SDL2
window -- all pure functions or early-return control flow with no emulator/window involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import types
from datetime import datetime, timezone

import pytest

import eval.score_gate0 as scorer
import tools.capture_gate0_baseline_red as m


def test_under_real_path_guard():
    assert m._under_real_path(m.REAL_OUT)
    assert m._under_real_path(m.REAL_OUT + "/nested")
    assert not m._under_real_path(m.REAL_OUT + "_other")
    assert not m._under_real_path("/tmp/scratch")


def test_sha256_file_matches_hashlib(tmp_path):
    p = tmp_path / "sample.bin"
    p.write_bytes(b"gate0-baseline-rig-sample-bytes")
    assert m._sha256_file(str(p)) == hashlib.sha256(p.read_bytes()).hexdigest()


def _rom_state(tmp_path):
    rom = tmp_path / "rom.gb"
    state = tmp_path / "state.sav"
    rom.write_bytes(b"fake-rom-bytes")
    state.write_bytes(b"fake-state-bytes")
    return str(rom), str(state)


def _args(tmp_path, out=None, allow_retake=None, test=True):
    rom, state = _rom_state(tmp_path)
    return argparse.Namespace(rom=rom, state=state,
                              out=str(out) if out is not None else str(tmp_path / "out"),
                              player="AutomatedSmokeTest", test=test, allow_retake=allow_retake)


@pytest.fixture
def fake_pyboy_raises(monkeypatch):
    """Injects a fake `pyboy` module whose PyBoy.__init__ raises immediately -- exercises run()'s
    setup-failure/INCOMPLETE-artifact path (CODE-REVIEW MINOR 2) WITHOUT ever creating a real
    SDL2 window or touching real Pokemon Red gameplay (the HARD LAW this test file's docstring
    describes). Only `pyboy.PyBoy` is faked; the real `sdl2` import and `ensure_sdl_dll_path()`
    still run (both side-effect-free: no window, no SDL_Init)."""
    class _FakePyBoy:
        def __init__(self, *_a, **_kw):
            raise RuntimeError("simulated PyBoy construction failure (test double, no real window)")

    fake_module = types.ModuleType("pyboy")
    fake_module.PyBoy = _FakePyBoy
    monkeypatch.setitem(sys.modules, "pyboy", fake_module)
    return _FakePyBoy


# ---- _atomic_write_json -----------------------------------------------------------------------

def test_atomic_write_json_happy_path(tmp_path):
    target = tmp_path / "human_metrics.json"
    m._atomic_write_json(str(target), {"schema_version": 1, "arm": "red"})
    assert json.loads(target.read_text(encoding="utf-8")) == {"schema_version": 1, "arm": "red"}
    # no stray temp file left behind
    assert list(tmp_path.glob("human_metrics.json.tmp*")) == []


def test_atomic_write_json_leaves_no_partial_file_on_crash(tmp_path, monkeypatch):
    target = tmp_path / "human_metrics.json"

    def _boom(*_a, **_kw):
        raise RuntimeError("simulated crash mid-write")

    monkeypatch.setattr(m.json, "dump", _boom)
    with pytest.raises(RuntimeError):
        m._atomic_write_json(str(target), {"schema_version": 1})
    assert not target.exists()
    assert list(tmp_path.glob("human_metrics.json.tmp*")) == []


def test_atomic_write_json_does_not_clobber_existing_file_on_crash(tmp_path, monkeypatch):
    target = tmp_path / "human_metrics.json"
    target.write_text(json.dumps({"schema_version": 1, "attempt_number": 1}), encoding="utf-8")

    def _boom(*_a, **_kw):
        raise RuntimeError("simulated crash mid-write")

    monkeypatch.setattr(m.json, "dump", _boom)
    with pytest.raises(RuntimeError):
        m._atomic_write_json(str(target), {"schema_version": 1, "attempt_number": 2})
    assert json.loads(target.read_text(encoding="utf-8"))["attempt_number"] == 1


# ---- _build_metrics schema (mode / attempt_number / retake_reason / input_event_times) --------

def test_build_metrics_schema_has_mode_and_retake_fields(tmp_path):
    rom, state = _rom_state(tmp_path)
    args = argparse.Namespace(rom=rom, state=state, out=str(tmp_path / "out"), player="David",
                              test=False, allow_retake=None)
    metrics = m._build_metrics(
        args, rom_sha256="a" * 64, state_sha256="b" * 64, oracle_path=str(tmp_path / "oracle.jsonl"),
        wall_clock_s=12.5, press_count=42, success=True, failures=[],
        started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
        attempt_number=1, retake_reason="", input_event_times=[1.0, 2.0])
    assert metrics["schema_version"] == 1
    assert metrics["arm"] == "red"
    assert metrics["role"] == "human"
    assert metrics["mode"] == "readiness_dev"
    assert metrics["attempt_number"] == 1
    assert metrics["retake_reason"] == ""
    assert metrics["input_event_times"] == [1.0, 2.0]


def test_build_metrics_artifact_passes_frozen_verify_sources(tmp_path):
    """The superset schema (mode/attempt_number/retake_reason/input_event_times added on top of the
    fields eval.score_gate0._verify_sources actually checks) must stay compatible with the frozen
    loader -- reproduces the same pins/manifest construction as
    tests/test_score_gate0.py::test_frozen_source_pins_load_exact_artifacts, substituting a REAL
    rig-produced red_human artifact for the hand-authored one."""
    rom, state = _rom_state(tmp_path)
    args = argparse.Namespace(rom=rom, state=state, out=str(tmp_path / "out"), player="David",
                              test=False, allow_retake=None)
    red_human = m._build_metrics(
        args, rom_sha256="a" * 64, state_sha256="b" * 64, oracle_path=str(tmp_path / "oracle.jsonl"),
        wall_clock_s=60, press_count=60, success=True, failures=[],
        started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
        attempt_number=1, retake_reason="", input_event_times=list(range(60)))

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
    assert verified["metrics"]["red"]["human_wall_clock_s"] == 60
    assert verified["metrics"]["red"]["human_primitive_actions"] == 60


# ---- overwrite refusal (one cold attempt per task) ---------------------------------------------

def test_overwrite_refused_without_allow_retake(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "human_metrics.json").write_text(
        json.dumps({"schema_version": 1, "attempt_number": 1}), encoding="utf-8")
    args = _args(tmp_path, out=out)
    rc = m.run(args)
    assert rc == 2
    # untouched -- no PyBoy/SDL2 was ever reached
    assert json.loads((out / "human_metrics.json").read_text(encoding="utf-8"))["attempt_number"] == 1


def test_no_refusal_when_canonical_artifact_absent(fake_pyboy_raises, tmp_path):
    """A first attempt (no prior canonical file) must sail past the retake guard -- confirmed by
    checking it reaches (and fails on) the next real step, PyBoy construction, rather than being
    refused at rc==2 by the retake guard itself."""
    args = _args(tmp_path, test=False)
    rc = m.run(args)
    assert rc == 2
    incomplete = list((tmp_path / "out").glob("human_metrics.INCOMPLETE_*.json"))
    assert len(incomplete) == 1
    metrics = json.loads(incomplete[0].read_text(encoding="utf-8"))
    assert metrics["failures"][0].startswith("setup_failed:")
    assert metrics["attempt_number"] == 1
    assert metrics["retake_reason"] == ""


# ---- stale oracle.jsonl archival at session start (same pattern as PR #119's MiniWoB rig) ------

def test_stale_oracle_archived_before_a_fresh_attempt(fake_pyboy_raises, tmp_path):
    """A prior session's oracle.jsonl (left behind by a crash/abort before the canonical write, or
    a legitimate --allow-retake) must be archived -- renamed, never deleted or appended-into --
    before a fresh attempt starts, exactly like MiniWoB's rig (PR #119). Pre-fix, Red had no such
    archival: a re-run's rows would land in the SAME oracle.jsonl as the stale attempt's, corrupting
    _red_success's party/battle/exit index logic on the combined file (this is what David's aborted
    second human-baseline attempt was headed for absent a fix -- see DAVID_BASELINES.md). Uses
    fake_pyboy_raises so this never opens a real SDL2 window: the archival step runs before PyBoy
    construction, so it's exercised even though this run() call fails immediately afterward."""
    out = tmp_path / "out"
    out.mkdir()
    stale_row = {"step": 0, "t": 1.0, "frame": 4, "watch": {"party": 0, "in_battle": 0, "map": 38,
                                                             "x": 3, "y": 7, "party_hp_hi": 0,
                                                             "party_hp_lo": 0}}
    (out / "oracle.jsonl").write_text(json.dumps(stale_row) + "\n", encoding="utf-8")

    args = _args(tmp_path, out=out, test=False)
    rc = m.run(args)
    assert rc == 2   # PyBoy construction still fails (faked) -- only checking the archival ran first

    archived = list(out.glob("oracle.attempt1_*.jsonl"))
    assert len(archived) == 1
    assert json.loads(archived[0].read_text(encoding="utf-8").strip()) == stale_row
    # the stale file is gone from the live path -- a fresh attempt never appends onto it
    assert not (out / "oracle.jsonl").exists()


def test_no_archival_when_no_prior_oracle_exists(fake_pyboy_raises, tmp_path):
    args = _args(tmp_path, test=False)
    rc = m.run(args)
    assert rc == 2
    out = tmp_path / "out"
    assert list(out.glob("oracle.attempt*_*.jsonl")) == []


# ---- setup-failure -> INCOMPLETE artifact, no orphaned window (CODE-REVIEW MINOR 2) ------------

def test_pyboy_setup_failure_writes_incomplete_artifact_with_mode_and_attempt_fields(fake_pyboy_raises, tmp_path):
    """A corrupt/incompatible savestate (or any other PyBoy/SDL2 setup exception) must go through
    the same clean-abort path as a human quitting: no crash with nothing written, an INCOMPLETE
    artifact instead. PyBoy construction is faked to raise (fake_pyboy_raises) so this never opens
    a real SDL2 window."""
    args = _args(tmp_path, test=False)
    rc = m.run(args)
    assert rc == 2
    out = tmp_path / "out"
    assert not (out / "human_metrics.json").exists()
    incomplete = list(out.glob("human_metrics.INCOMPLETE_*.json"))
    assert len(incomplete) == 1
    metrics = json.loads(incomplete[0].read_text(encoding="utf-8"))
    assert metrics["schema_version"] == 1
    assert metrics["mode"] == "readiness_dev"
    assert metrics["success"] is False
    assert metrics["wall_clock_s"] == 0.0
    assert metrics["primitive_actions"] == 0
    assert metrics["input_event_times"] == []
    assert metrics["failures"] == ["setup_failed:RuntimeError"]


def test_retake_allowed_past_setup_failure_records_attempt_2_and_reason(fake_pyboy_raises, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "human_metrics.json").write_text(
        json.dumps({"schema_version": 1, "arm": "red", "role": "human", "mode": "readiness_dev",
                   "attempt_number": 1}), encoding="utf-8")
    args = _args(tmp_path, out=out, allow_retake="Docker died mid-capture, never scored", test=False)
    rc = m.run(args)
    assert rc == 2   # setup still fails (faked PyBoy) -- we're only checking the retake
                     # bookkeeping got past the refusal and was recorded
    incomplete = list(out.glob("human_metrics.INCOMPLETE_*.json"))
    assert len(incomplete) == 1
    metrics = json.loads(incomplete[0].read_text(encoding="utf-8"))
    assert metrics["attempt_number"] == 2
    assert metrics["retake_reason"] == "Docker died mid-capture, never scored"
    # the pre-existing canonical file (a genuinely different attempt) must be untouched
    assert json.loads((out / "human_metrics.json").read_text(encoding="utf-8"))["attempt_number"] == 1
