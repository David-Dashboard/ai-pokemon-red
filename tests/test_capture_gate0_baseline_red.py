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


def _args(tmp_path, out=None, allow_retake=None, test=True, mode="readiness_dev",
          i_am_human=False):
    rom, state = _rom_state(tmp_path)
    return argparse.Namespace(rom=rom, state=state,
                              out=str(out) if out is not None else str(tmp_path / "out"),
                              player="AutomatedSmokeTest", test=test, allow_retake=allow_retake,
                              mode=mode, i_am_human=i_am_human)


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
                              test=False, allow_retake=None, mode="readiness_dev",
                              i_am_human=False)
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
                              test=False, allow_retake=None, mode="readiness_dev",
                              i_am_human=False)
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


# ================================================================================================
# --mode: the stamp and the output directory, both derived from ONE required flag.
#
# Until 2026-07-28 this rig hardcoded MODE = "readiness_dev" with no --mode flag at all, so every
# artifact it could produce was stamped readiness_dev. eval/score_gate0.py::_verify_sources requires
# that stamp to EQUAL the mode being scored, so prereg P1c ("a RED human baseline whose mode field
# matches the mode being scored") was not merely undone -- it was unsatisfiable. The failure is
# silent: it surfaces as human_metric_identity:red at SCORING, after a paid run is spent.
# ================================================================================================

import os
from pathlib import Path

import tools.capture_gate0_baseline_red as red


def _parser():
    return red.build_arg_parser()


# ---- the flag itself ---------------------------------------------------------------------------

def test_mode_is_required_and_has_no_default():
    """NO DEFAULT, deliberately. A default of "readiness_dev" preserves exactly the trap being
    fixed: someone capturing the v2 baseline omits the flag and produces an artifact the scorer
    rejects, discovered only after the paid run."""
    assert _parser().get_default("mode") is None
    with pytest.raises(SystemExit):
        _parser().parse_args([])


def test_mode_choices_are_exactly_the_frozen_scorers_modes():
    action = next(a for a in _parser()._actions if a.dest == "mode")
    assert tuple(action.choices) == tuple(scorer.MODES)
    with pytest.raises(SystemExit):
        _parser().parse_args(["--mode", "paid_gate3"])


def test_mode_config_covers_exactly_the_scorers_modes():
    """A mode the scorer knows but this rig has no output directory for would fail at run() with a
    refusal instead of at argparse -- and a mode here the scorer does not know could produce an
    artifact nothing can score. Bind the two sets."""
    assert set(red.MODE_CONFIG) == set(scorer.MODES) == set(red.score_gate0_modes())


def test_score_gate0_modes_reads_the_scorer_never_a_local_copy():
    assert red.score_gate0_modes() is scorer.MODES


# ---- per-mode output directories ----------------------------------------------------------------

def test_readiness_dev_out_dir_is_byte_identical_to_the_removed_hardcode():
    """The old unconditional REAL_OUT literal, written out longhand. readiness_dev's output path
    must not move -- runs/gate0_human_baseline/red/human_metrics.json is banked and three source-pin
    fixtures freeze its digest."""
    removed_hardcode = os.path.normpath(str(red.ROOT / "runs" / "gate0_human_baseline" / "red"))
    assert red.MODE_CONFIG["readiness_dev"]["real_out"] == removed_hardcode
    assert red.REAL_OUT == removed_hardcode


def test_each_mode_writes_its_own_directory_and_never_another_modes():
    outs = {m: cfg["real_out"] for m, cfg in red.MODE_CONFIG.items()}
    assert len(set(outs.values())) == len(outs), f"two modes share an output directory: {outs}"
    as_posix = {m: o.replace("\\", "/") for m, o in outs.items()}
    assert as_posix["readiness_dev"].endswith("runs/gate0_human_baseline/red")
    assert as_posix["paid_gate0"].endswith("runs/gate0_paid_human_baseline/red")
    assert as_posix["paid_gate0_v2"].endswith("runs/gate0_paid_v2_human_baseline/red")


def test_out_defaults_to_the_modes_directory_not_a_hardwired_one(monkeypatch, tmp_path,
                                                                 fake_pyboy_raises):
    """--out is None at the parser and filled in by run() from the mode -- proven by watching where
    a real run() call actually writes, not by reading the constant."""
    target = tmp_path / "v2_out"
    monkeypatch.setitem(red.MODE_CONFIG, "paid_gate0_v2", {"real_out": str(target)})
    monkeypatch.setattr(red, "pinned_red_human_path",
                        lambda mode: (target / "human_metrics.json").resolve())
    args = _args(tmp_path, test=False, mode="paid_gate0_v2", i_am_human=True)
    args.out = None
    assert red.run(args) == 2                      # faked PyBoy still fails, as intended
    assert args.out == str(target)
    assert len(list(target.glob("human_metrics.INCOMPLETE_*.json"))) == 1


# ---- the mode STAMP ------------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["readiness_dev", "paid_gate0", "paid_gate0_v2"])
def test_mode_is_stamped_from_args_never_hardwired(tmp_path, mode):
    args = _args(tmp_path, mode=mode)
    metrics = red._build_metrics(
        args, rom_sha256="a" * 64, state_sha256="b" * 64, oracle_path=str(tmp_path / "o.jsonl"),
        wall_clock_s=1.0, press_count=1, success=True, failures=[],
        started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
        attempt_number=1, retake_reason="", input_event_times=[])
    assert metrics["mode"] == mode


def test_a_v2_stamped_artifact_satisfies_the_frozen_identity_check(tmp_path):
    """The whole point of P1c, pinned end to end: an artifact this rig produces under
    --mode paid_gate0_v2 passes _verify_sources' (schema_version, arm, role, mode) identity check for
    paid_gate0_v2, which the banked readiness_dev artifact does not."""
    args = _args(tmp_path, mode="paid_gate0_v2")
    metrics = red._build_metrics(
        args, rom_sha256="a" * 64, state_sha256="b" * 64, oracle_path=str(tmp_path / "o.jsonl"),
        wall_clock_s=233.288, press_count=271, success=True, failures=[],
        started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
        attempt_number=1, retake_reason="", input_event_times=[])
    identity = (metrics["schema_version"], metrics["arm"], metrics["role"], metrics["mode"])
    assert identity == (1, "red", "human", "paid_gate0_v2")


# ---- held-out gating: a paid mode cannot be entered casually --------------------------------------

@pytest.mark.parametrize("mode", sorted(red.HELD_OUT_MODES))
def test_held_out_mode_refused_without_the_acknowledgement(tmp_path, mode, monkeypatch,
                                                           fake_pyboy_raises):
    """THE gating test. A paid-mode capture produces the human denominator the 2.0x bar is measured
    against; it must never happen by accident or from a script."""
    out = tmp_path / "out"
    monkeypatch.setitem(red.MODE_CONFIG, mode, {"real_out": str(out)})
    args = _args(tmp_path, out=out, test=False, mode=mode, i_am_human=False)
    assert red.run(args) == 2
    # Refused BEFORE anything is created -- not merely refused after writing an artifact.
    assert not out.exists()


def test_held_out_modes_are_exactly_the_paid_modes():
    assert red.HELD_OUT_MODES == frozenset(set(scorer.MODES) - {"readiness_dev"})


def test_readiness_dev_needs_no_acknowledgement(tmp_path, fake_pyboy_raises):
    """The gate must not leak onto the dev mode -- unchanged behaviour is the whole requirement."""
    args = _args(tmp_path, test=False, mode="readiness_dev", i_am_human=False)
    assert red.run(args) == 2                      # reaches (and fails at) faked PyBoy construction
    incomplete = list((tmp_path / "out").glob("human_metrics.INCOMPLETE_*.json"))
    assert len(incomplete) == 1
    assert json.loads(incomplete[0].read_text(encoding="utf-8"))["mode"] == "readiness_dev"


def test_cli_refuses_a_held_out_mode_without_the_acknowledgement():
    """End to end through the real parser, not just run()."""
    parsed = _parser().parse_args(["--mode", "paid_gate0_v2"])
    assert parsed.i_am_human is False
    assert red.run(parsed) == 2


def test_unknown_mode_is_refused_by_run_even_if_argparse_is_bypassed(tmp_path):
    args = _args(tmp_path, mode="paid_gate9")
    assert red.run(args) == 2


# ---- the fixture cross-check: validate and refuse, never derive ------------------------------------

def _pins_pointing_at(tmp_path, mode, red_human_path):
    pins = tmp_path / f"pins_{mode}.json"
    pins.write_text(json.dumps({
        "schema_version": 1, "mode": mode,
        "artifact_paths": {"red_human": str(red_human_path)},
    }), encoding="utf-8")
    return pins


def test_all_three_fixtures_currently_pin_the_same_banked_red_baseline():
    """The finding this PR exists to expose, pinned mechanically rather than asserted in prose.

    Every mode's artifact_paths.red_human resolves to the ONE banked readiness_dev artifact. That is
    why the output directory is NOT derived from the pin (deriving would send a v2 capture straight
    into a banked, triple-digest-frozen, append-only file) and why P1c additionally needs a fixture
    re-point that no change to this rig can supply."""
    resolved = {m: red.pinned_red_human_path(m) for m in scorer.MODES}
    assert len(set(resolved.values())) == 1, resolved
    only = next(iter(resolved.values()))
    assert only.as_posix().endswith("runs/gate0_human_baseline/red/human_metrics.json")
    # ...and it is exactly where readiness_dev writes, which is why readiness_dev is unaffected.
    assert only == Path(red.MODE_CONFIG["readiness_dev"]["real_out"], "human_metrics.json").resolve()


@pytest.mark.parametrize("mode", sorted(red.HELD_OUT_MODES))
def test_held_out_capture_refused_while_the_fixture_points_somewhere_else(tmp_path, mode,
                                                                          monkeypatch,
                                                                          fake_pyboy_raises):
    out = tmp_path / "out"
    monkeypatch.setitem(red.MODE_CONFIG, mode, {"real_out": str(out)})
    monkeypatch.setitem(
        scorer.SOURCE_PIN_FILES, mode,
        _pins_pointing_at(tmp_path, mode, tmp_path / "elsewhere" / "human_metrics.json"))
    args = _args(tmp_path, out=out, test=False, mode=mode, i_am_human=True)
    assert red.run(args) == 2
    assert not out.exists()          # refused before a single byte was written


@pytest.mark.parametrize("mode", sorted(red.HELD_OUT_MODES))
def test_held_out_capture_proceeds_once_the_fixture_points_here(tmp_path, mode, monkeypatch,
                                                                fake_pyboy_raises):
    out = tmp_path / "out"
    monkeypatch.setitem(red.MODE_CONFIG, mode, {"real_out": str(out)})
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, mode,
                        _pins_pointing_at(tmp_path, mode, out / "human_metrics.json"))
    args = _args(tmp_path, out=out, test=False, mode=mode, i_am_human=True)
    assert red.run(args) == 2        # reaches faked PyBoy construction: the guards all passed
    incomplete = list(out.glob("human_metrics.INCOMPLETE_*.json"))
    assert len(incomplete) == 1
    assert json.loads(incomplete[0].read_text(encoding="utf-8"))["mode"] == mode


def test_the_acknowledgement_does_not_bypass_the_fixture_cross_check(tmp_path, monkeypatch):
    """--i-am-human is not a master key: it answers "is a human playing", not "will anything read
    the result"."""
    out = tmp_path / "out"
    monkeypatch.setitem(red.MODE_CONFIG, "paid_gate0_v2", {"real_out": str(out)})
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, "paid_gate0_v2",
                        _pins_pointing_at(tmp_path, "paid_gate0_v2", tmp_path / "nope.json"))
    assert red.require_fixture_points_here("paid_gate0_v2", str(out)) is not None


def test_readiness_dev_is_exempt_from_the_fixture_cross_check(tmp_path, monkeypatch):
    """Scoped to HELD_OUT_MODES on purpose: readiness_dev's baseline is captured, banked and already
    pinned to exactly this file, so re-checking it protects nothing and would add a new way for a
    legitimate --allow-retake to fail. Keeping it exempt is what makes the PR body's differential
    come out IDENTICAL."""
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, "readiness_dev",
                        _pins_pointing_at(tmp_path, "readiness_dev", tmp_path / "wherever.json"))
    assert red.require_fixture_points_here("readiness_dev", red.REAL_OUT) is None


def test_fixture_cross_check_fails_closed_on_an_unreadable_fixture(tmp_path, monkeypatch):
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, "paid_gate0_v2", tmp_path / "does_not_exist.json")
    msg = red.require_fixture_points_here("paid_gate0_v2", str(tmp_path / "out"))
    assert msg is not None and "refusing" in msg


def test_pinned_red_human_path_resolves_relative_entries_like_verify_sources(tmp_path, monkeypatch):
    """_verify_sources resolves a relative artifact_paths entry against the SCORER's ROOT, not the
    cwd. Two different resolutions of one pin is the drift class this workstream removes."""
    monkeypatch.setitem(
        scorer.SOURCE_PIN_FILES, "paid_gate0_v2",
        _pins_pointing_at(tmp_path, "paid_gate0_v2",
                          "runs/gate0_paid_v2_human_baseline/red/human_metrics.json"))
    assert red.pinned_red_human_path("paid_gate0_v2") == (
        scorer.ROOT / "runs" / "gate0_paid_v2_human_baseline" / "red"
        / "human_metrics.json").resolve()


# ---- the real-path guard is now per mode ----------------------------------------------------------

def test_under_real_path_is_evaluated_against_the_modes_own_directory():
    dev = red.MODE_CONFIG["readiness_dev"]["real_out"]
    v2 = red.MODE_CONFIG["paid_gate0_v2"]["real_out"]
    assert red._under_real_path(dev, dev) and not red._under_real_path(dev, v2)
    assert red._under_real_path(v2, v2) and not red._under_real_path(v2, dev)
    # the one-argument form still answers for readiness_dev (backward compatible)
    assert red._under_real_path(dev)


def test_test_mode_still_refuses_to_write_under_a_paid_modes_real_path(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setitem(red.MODE_CONFIG, "paid_gate0_v2", {"real_out": str(out)})
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, "paid_gate0_v2",
                        _pins_pointing_at(tmp_path, "paid_gate0_v2", out / "human_metrics.json"))
    args = _args(tmp_path, out=out, test=True, mode="paid_gate0_v2", i_am_human=True)
    assert red.run(args) == 2
    assert not out.exists()
