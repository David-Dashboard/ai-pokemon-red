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
import os
import shutil
import subprocess
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

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


@pytest.fixture
def fake_pyboy_boots(monkeypatch):
    """A PyBoy stub that BOOTS, unlike `fake_pyboy_raises` -- the only way to reach the code AFTER
    the interactive loop, which is where the canonical-vs-INCOMPLETE artifact NAME is chosen.

    Still no real gameplay and no window (the HARD LAW in this file's docstring): the fake ticks
    frames, reports all-zero RAM, and `run(max_frames=...)` -- the Python-only seam -- ends the loop.
    `sdl2` stays REAL, including the scancode constants; only `SDL_GetKeyboardState` is replaced, by
    a plain array the test drives, so no SDL_Init and no keyboard is ever touched. Returns that
    array: setting `keys[sdl2.SDL_SCANCODE_A] = 1` makes the rig see a held button, which is what
    starts the timer and lets the oracle be consulted at all."""
    import sdl2

    class _AllZeroRAM:
        def __getitem__(self, _addr):
            return 0

    class _FakePyBoy:
        def __init__(self, *_a, **_kw):
            self.frame_count = 0
            self.memory = _AllZeroRAM()

        def set_emulation_speed(self, *_a):
            pass

        def load_state(self, _f):
            pass

        def tick(self, n=1, _render=False, **_kw):
            self.frame_count += n
            return True

        def stop(self, save=False):
            assert save is False, "the rig must never let PyBoy write cartridge RAM"

    fake_module = types.ModuleType("pyboy")
    fake_module.PyBoy = _FakePyBoy
    monkeypatch.setitem(sys.modules, "pyboy", fake_module)
    keys = [0] * 512
    monkeypatch.setattr(sdl2, "SDL_GetKeyboardState", lambda _n: keys)
    return keys


@pytest.mark.parametrize("succeeds, expected_glob, forbidden", [
    (False, "human_metrics.INCOMPLETE_*.json", "human_metrics.json"),
    (True, "human_metrics.json", "human_metrics.INCOMPLETE_*.json"),
])
def test_a_botched_capture_is_named_incomplete_and_a_real_one_is_not(tmp_path, monkeypatch,
                                                                     fake_pyboy_boots, succeeds,
                                                                     expected_glob, forbidden):
    """REVIEW E4: `name = "human_metrics.json" if success else f"...INCOMPLETE_{...}.json"` survived
    the FULL 1732-test suite as an unkilled mutant. Every other test that asserts on an INCOMPLETE
    artifact reaches it through the SETUP-FAILURE path, which hardcodes the INCOMPLETE name
    separately -- so the one line the module docstring points at when it claims "a botched capture
    can never silently masquerade as a banked baseline" had no test at all.

    Both directions are pinned, so neither half of the ternary can be collapsed to a constant."""
    import sdl2
    if succeeds:
        # A held button is what sets first_input_perf, without which the oracle is never consulted.
        fake_pyboy_boots[sdl2.SDL_SCANCODE_A] = 1
        monkeypatch.setattr(scorer, "_red_success", lambda rows: (True, []))
    out = tmp_path / "out"
    # 40 frames: past SAMPLE_EVERY_FRAMES (15) so the oracle IS consulted, and far short of
    # COMPLETION_GRACE_SECONDS so a success exits on the frame cap rather than sleeping.
    rc = red.run(_args(tmp_path, out=out, test=False, mode="readiness_dev"), max_frames=40)

    assert rc == (0 if succeeds else 1)
    assert list(out.glob(expected_glob)), sorted(p.name for p in out.iterdir())
    assert not list(out.glob(forbidden)), sorted(p.name for p in out.iterdir())
    written = json.loads(next(iter(out.glob(expected_glob))).read_text(encoding="utf-8"))
    assert written["success"] is succeeds


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

def test_overwrite_refused_without_allow_retake(tmp_path, capsys):
    """The one-cold-attempt law, pinned so that DELETING it goes red.

    Review D4/M21: the previous version of this test asserted only `rc == 2` and that the existing
    artifact's attempt_number was still 1, and `if not allow_retake:` -> `if False:` SURVIVED the
    whole suite. With the guard gone, control simply falls through to the PyBoy setup failure, which
    also returns 2 and writes a DIFFERENTLY-named file (human_metrics.INCOMPLETE_*.json), leaving
    both of the old assertions true. Vacuous in exactly the shape review B4 had already caught once.

    What actually distinguishes "refused" from "fell through" is (a) the refusal message and (b) that
    the refusal writes NOTHING AT ALL -- no INCOMPLETE artifact, no oracle.jsonl, no directory churn.
    This is the last line of defence behind the write-path guard, so it is pinned on both."""
    out = tmp_path / "out"
    out.mkdir()
    (out / "human_metrics.json").write_text(
        json.dumps({"schema_version": 1, "attempt_number": 1}), encoding="utf-8")
    args = _args(tmp_path, out=out)
    rc = m.run(args)
    assert rc == 2
    assert "one cold attempt per task" in capsys.readouterr().err
    # untouched -- no PyBoy/SDL2 was ever reached, and nothing new appeared beside it
    assert json.loads((out / "human_metrics.json").read_text(encoding="utf-8"))["attempt_number"] == 1
    assert sorted(p.name for p in out.iterdir()) == ["human_metrics.json"]


def test_the_retake_law_holds_for_every_mode_and_flag_combination(tmp_path, monkeypatch,
                                                                   fake_pyboy_raises):
    """M21 again, from the other side: no --mode/--i-am-human/--test combination may walk past the
    one-cold-attempt law. Cross-check neutralised so the retake guard alone is what holds."""
    monkeypatch.setattr(m, "require_fixture_points_here", lambda mode, out_dir: None)
    for mode in sorted(m.MODE_CONFIG):
        for i_am_human in (False, True):
            for test in (False, True):
                out = tmp_path / f"out_{mode}_{i_am_human}_{test}"
                out.mkdir()
                (out / "human_metrics.json").write_text(
                    json.dumps({"schema_version": 1, "attempt_number": 1}), encoding="utf-8")
                rc = m.run(_args(tmp_path, out=out, test=test, mode=mode, i_am_human=i_am_human))
                assert rc == 2, (mode, i_am_human, test)
                assert sorted(p.name for p in out.iterdir()) == ["human_metrics.json"], \
                    (mode, i_am_human, test)


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

import tools.capture_gate0_baseline_red as red


def _parser():
    return red.build_arg_parser()


# ---- the DOCUMENTED invocation actually runs -----------------------------------------------------

def _direct_script(tmp_path, *argv):
    """`python tools/capture_gate0_baseline_red.py ...` as a real subprocess, from an unrelated cwd
    and with PYTHONPATH scrubbed. Both matter: the shim must key off __file__ rather than the
    working directory, and an inherited PYTHONPATH would make this test pass without any shim at
    all."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run([sys.executable, str(Path(red.__file__)), *argv], cwd=tmp_path,
                          capture_output=True, text=True, env=env)


def test_the_documented_invocation_runs_as_a_direct_script(tmp_path):
    """Review B1, and the deliverable: DAVID_BASELINES.md hands David
    `uv run python tools/capture_gate0_baseline_red.py --mode paid_gate0_v2 --i-am-human` to close
    P1c step 2. Running a file in tools/ directly puts tools/ -- not the repo root -- on
    sys.path[0], so build_arg_parser()'s read of the scorer's MODES died with
    `ModuleNotFoundError: No module named 'eval'` on the very first line. `--help` regressed the
    same way (it exits 0 on origin/main `322499f`), so anyone debugging would have blamed --mode.

    Nothing tested the tool as a SCRIPT, which is the only way it is ever actually invoked."""
    r = _direct_script(tmp_path, "--help")
    assert r.returncode == 0, r.stderr
    assert "ModuleNotFoundError" not in r.stderr
    for mode in ("readiness_dev", "paid_gate0", "paid_gate0_v2"):
        assert mode in r.stdout


def test_the_documented_invocation_reaches_the_real_guards_not_an_import_error(tmp_path):
    """--help alone would pass with a lazily-imported parser, so go further: a real capture
    invocation must get past parser construction and reach run()'s own checks. An explicit missing
    --rom makes the expected stopping point deterministic wherever this runs."""
    r = _direct_script(tmp_path, "--mode", "readiness_dev", "--test",
                       "--rom", str(tmp_path / "no_such.gb"), "--out", str(tmp_path / "scratch"))
    assert r.returncode == 2
    assert "ModuleNotFoundError" not in r.stderr and "Traceback" not in r.stderr
    assert "ROM not found" in r.stderr


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


def test_the_parser_reads_the_scorers_modes_at_build_time_not_a_hardcoded_tuple(monkeypatch):
    """Mutation-driven (review B4/M5): the two tests above compare VALUES that happen to coincide
    today, so replacing `choices=tuple(score_gate0_modes())` with a hardcoded
    ("readiness_dev", "paid_gate0", "paid_gate0_v2") left the whole suite green -- i.e. the headline
    "this rig can never offer a mode the scorer cannot score" was not enforced at the parser, which
    is where it has to hold.

    Move the scorer's map and the parser must move with it. A hardcoded tuple cannot."""
    monkeypatch.setattr(scorer, "MODES", dict(scorer.MODES, synthetic_probe_mode=None))
    action = next(a for a in _parser()._actions if a.dest == "mode")
    assert "synthetic_probe_mode" in action.choices
    assert _parser().parse_args(["--mode", "synthetic_probe_mode"]).mode == "synthetic_probe_mode"


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
def test_held_out_mode_refused_without_the_acknowledgement(tmp_path, mode, monkeypatch, capsys,
                                                           fake_pyboy_raises):
    """THE gating test. A paid-mode capture produces the human denominator the 2.0x bar is measured
    against; it must never happen by accident or from a script.

    ISOLATED, after review found this test could not tell the two guards apart. `exit == 2` and
    `not out.exists()` are satisfied *equally well* by the fixture cross-check, so deleting the
    --i-am-human gate outright left this test green. Two changes fix that: the mode's pins are
    re-pointed at `out` so the cross-check WOULD pass (the post-step-1 world, in which the
    acknowledgement is the only remaining protection -- the exact configuration nothing tested), and
    the assertion is on the refusal's own text. Delete the gate now and control falls through to a
    successful cross-check, the faked PyBoy, and an INCOMPLETE artifact in `out` -- three failures."""
    out = tmp_path / "out"
    monkeypatch.setitem(red.MODE_CONFIG, mode, {"real_out": str(out)})
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, mode,
                        _pins_pointing_at(tmp_path, mode, out / "human_metrics.json"))
    args = _args(tmp_path, out=out, test=False, mode=mode, i_am_human=False)
    assert red.run(args) == 2
    assert "--i-am-human" in capsys.readouterr().err
    # Refused BEFORE anything is created -- not merely refused after writing an artifact.
    assert not out.exists()


@pytest.mark.parametrize("mode", sorted(red.HELD_OUT_MODES))
def test_the_acknowledgement_is_the_only_guard_left_once_the_fixture_points_here(
        tmp_path, mode, monkeypatch, fake_pyboy_raises):
    """The companion to the test above, stated as a positive: with the pins re-pointed, the ONLY
    difference between refusal and a real capture is --i-am-human. If this passes and the one above
    passes, the gate is load-bearing and independently observable."""
    out = tmp_path / "out"
    monkeypatch.setitem(red.MODE_CONFIG, mode, {"real_out": str(out)})
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, mode,
                        _pins_pointing_at(tmp_path, mode, out / "human_metrics.json"))
    args = _args(tmp_path, out=out, test=False, mode=mode, i_am_human=True)
    assert red.run(args) == 2                      # reaches (and fails at) faked PyBoy
    assert len(list(out.glob("human_metrics.INCOMPLETE_*.json"))) == 1


def test_held_out_modes_are_exactly_the_paid_modes():
    assert red.HELD_OUT_MODES == frozenset(set(scorer.MODES) - {"readiness_dev"})


def test_readiness_dev_needs_no_acknowledgement(tmp_path, fake_pyboy_raises):
    """The gate must not leak onto the dev mode -- unchanged behaviour is the whole requirement."""
    args = _args(tmp_path, test=False, mode="readiness_dev", i_am_human=False)
    assert red.run(args) == 2                      # reaches (and fails at) faked PyBoy construction
    incomplete = list((tmp_path / "out").glob("human_metrics.INCOMPLETE_*.json"))
    assert len(incomplete) == 1
    assert json.loads(incomplete[0].read_text(encoding="utf-8"))["mode"] == "readiness_dev"


def test_cli_refuses_a_held_out_mode_without_the_acknowledgement(tmp_path, monkeypatch, capsys):
    """End to end through the real parser, not just run(). Same isolation as the test above: the
    pins are re-pointed so only the acknowledgement can be doing the refusing."""
    out = tmp_path / "out"
    monkeypatch.setitem(red.MODE_CONFIG, "paid_gate0_v2", {"real_out": str(out)})
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, "paid_gate0_v2",
                        _pins_pointing_at(tmp_path, "paid_gate0_v2", out / "human_metrics.json"))
    parsed = _parser().parse_args(["--mode", "paid_gate0_v2"])
    assert parsed.i_am_human is False
    assert red.run(parsed) == 2
    assert "--i-am-human" in capsys.readouterr().err
    assert not out.exists()


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
                                                                          monkeypatch, capsys,
                                                                          fake_pyboy_raises):
    """The mirror image of the gating test: --i-am-human IS passed, so only the cross-check can be
    refusing, and the message is asserted so it cannot be confused with any other guard."""
    out = tmp_path / "out"
    monkeypatch.setitem(red.MODE_CONFIG, mode, {"real_out": str(out)})
    monkeypatch.setitem(
        scorer.SOURCE_PIN_FILES, mode,
        _pins_pointing_at(tmp_path, mode, tmp_path / "elsewhere" / "human_metrics.json"))
    args = _args(tmp_path, out=out, test=False, mode=mode, i_am_human=True)
    assert red.run(args) == 2
    err = capsys.readouterr().err
    assert "will read the" in err and "would never be scored" in err
    assert not out.exists()          # refused before a single byte was written


@pytest.mark.parametrize("mode", sorted(red.HELD_OUT_MODES))
def test_an_explicit_out_cannot_walk_past_the_fixture_cross_check(tmp_path, mode, monkeypatch,
                                                                   capsys, fake_pyboy_raises):
    """REGRESSION (review B2): the cross-check used to validate MODE_CONFIG's `real_out` -- the
    directory the mode would write BY DEFAULT -- while run() went on to write `args.out`. With the
    v2 fixture re-pointed (step 1 of P1c, simulated here), `--out <the banked readiness_dev
    directory>` therefore validated a directory it was not about to touch, returned None, and
    proceeded: the banked human_metrics.json was overwritten with a paid-mode stamp and the banked
    append-only oracle.jsonl renamed away. `args.out != real_out` under a held-out mode was
    exercised by no test at all.

    Here the fixture legitimately points at the mode's own real_out (so nothing about the FIXTURE is
    wrong), --i-am-human is passed, and only `--out` differs -- the exact configuration that used to
    pass."""
    real_out = tmp_path / "v2_real_out"
    elsewhere = tmp_path / "banked_stand_in"
    elsewhere.mkdir()
    (elsewhere / "oracle.jsonl").write_text('{"BANKED_SENTINEL": true}\n', encoding="utf-8")
    monkeypatch.setitem(red.MODE_CONFIG, mode, {"real_out": str(real_out)})
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, mode,
                        _pins_pointing_at(tmp_path, mode, real_out / "human_metrics.json"))
    args = _args(tmp_path, out=elsewhere, test=False, mode=mode, i_am_human=True,
                 allow_retake="simulating the hazard")
    assert red.run(args) == 2
    assert "would never be scored" in capsys.readouterr().err
    # Nothing written, and the append-only trace not renamed away.
    assert sorted(p.name for p in elsewhere.iterdir()) == ["oracle.jsonl"]
    assert not real_out.exists()


def test_the_cross_check_binds_the_effective_write_target_not_the_modes_default(tmp_path,
                                                                                 monkeypatch):
    """Stated directly on the guard, independent of run(): its verdict follows the directory it is
    handed, so run() passing `args.out` is what makes it answer the question its docstring asks."""
    real_out = tmp_path / "v2_real_out"
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, "paid_gate0_v2",
                        _pins_pointing_at(tmp_path, "paid_gate0_v2",
                                          real_out / "human_metrics.json"))
    assert red.require_fixture_points_here("paid_gate0_v2", str(real_out)) is None
    assert red.require_fixture_points_here("paid_gate0_v2", str(tmp_path / "anywhere_else")) is not None


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
    cwd. Two different resolutions of one pin is the drift class this workstream removes.

    Runs from a DIFFERENT cwd deliberately. Without the chdir this test was vacuous: pytest runs
    from the repo root, where cwd == scorer.ROOT, so replacing the whole resolution with a bare
    `path.resolve()` passed anyway (a third surviving mutant, found this round -- the reviewer's
    mutation set reported two). The scorer resolves against its own ROOT from any cwd; so must
    this."""
    monkeypatch.setitem(
        scorer.SOURCE_PIN_FILES, "paid_gate0_v2",
        _pins_pointing_at(tmp_path, "paid_gate0_v2",
                          "runs/gate0_paid_v2_human_baseline/red/human_metrics.json"))
    monkeypatch.chdir(tmp_path)
    assert red.pinned_red_human_path("paid_gate0_v2") == (
        scorer.ROOT / "runs" / "gate0_paid_v2_human_baseline" / "red" / "human_metrics.json")


def test_pinned_red_human_path_does_not_symlink_resolve_because_the_scorer_does_not(tmp_path,
                                                                                     monkeypatch):
    """Kept in step with PR #192, whose own review removed the trailing `.resolve()` from
    `pinned_artifact_path` on the grounds that `_verify_sources` applies none, so a second
    resolution here would itself be the drift. `require_fixture_points_here` resolves at the
    comparison instead. Asserted as an exact identity against the scorer's literal expression --
    re-adding `.resolve()` breaks this on any path where the two differ."""
    monkeypatch.setitem(
        scorer.SOURCE_PIN_FILES, "paid_gate0_v2",
        _pins_pointing_at(tmp_path, "paid_gate0_v2", "runs/./../runs/x/../red/human_metrics.json"))
    got = red.pinned_red_human_path("paid_gate0_v2")
    expected = scorer.ROOT / "runs/./../runs/x/../red/human_metrics.json"
    assert got == expected
    assert ".." in str(got), "an un-normalised pin must survive un-normalised, exactly as the scorer sees it"


def test_the_cross_check_resolves_the_pin_at_the_comparison(tmp_path, monkeypatch):
    """Review D4/M2: `pinned.resolve() != target` -> `pinned != target` survived every test.

    The resolve-at-the-comparison split is the design property `pinned_red_human_path`'s docstring
    spends five lines justifying -- the pin is REPORTED unresolved (as the scorer opens it) but
    COMPARED resolved -- and nothing pinned it. A pin that names the very directory being written,
    spelled with a `..` round-trip, must be accepted: without the `.resolve()` on `pinned` it reads
    as a different path and manufactures a false refusal."""
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, "paid_gate0_v2",
                        _pins_pointing_at(tmp_path, "paid_gate0_v2",
                                          str(out / ".." / out.name / "human_metrics.json")))
    assert red.require_fixture_points_here("paid_gate0_v2", str(out)) is None


def test_the_cross_check_resolves_the_write_target_at_the_comparison(tmp_path, monkeypatch):
    """Review D4/M3: dropping `.resolve()` from `target` instead also survived. Same invariant, other
    side -- an `--out` spelled with a `..` round-trip is the same directory and must not be refused
    against a pin that names it plainly."""
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, "paid_gate0_v2",
                        _pins_pointing_at(tmp_path, "paid_gate0_v2", out / "human_metrics.json"))
    assert red.require_fixture_points_here(
        "paid_gate0_v2", str(out / ".." / out.name)) is None


def test_the_pin_helper_matches_192s_pinned_artifact_path(tmp_path, monkeypatch):
    """DECLARED DUPLICATION, bound rather than asserted. #192's `pinned_artifact_path(mode, key)` is
    the symbol this helper temporarily duplicates; the two must agree ON THE RESOLUTION OF A
    WELL-FORMED PIN until one is deleted. They deliberately DIVERGE elsewhere: review B5 made
    `pinned_red_human_path` raise on `schema_version != 1` / a `mode` mismatch, which #192's does not,
    and `_pins_pointing_at` only ever writes well-formed fixtures, so no spelling below reaches that
    divergence (review D5 -- the previous docstring's flat "the two must agree" overclaimed).

    #192's body is re-implemented here verbatim (it cannot be imported -- #192 is unmerged and its
    file is off-limits to this PR) and compared over a matrix of pin spellings including the ones
    that used to diverge before #192 dropped `.resolve()`."""
    def pinned_artifact_path_192(mode, key):                     # verbatim from #192 @ 6ca6b38
        pins = json.loads(scorer.SOURCE_PIN_FILES[mode].read_text(encoding="utf-8"))
        path = Path(pins["artifact_paths"][key])
        return path if path.is_absolute() else scorer.ROOT / path

    spellings = [
        "runs/gate0_paid_v2_human_baseline/red/human_metrics.json",
        "runs\\gate0_paid_v2_human_baseline\\red\\human_metrics.json",
        "./runs/gate0_paid_v2_human_baseline/red/human_metrics.json",
        "runs/../runs/gate0_paid_v2_human_baseline/red/human_metrics.json",
        str(tmp_path / "absolute" / "human_metrics.json"),
        str(tmp_path / "absolute" / ".." / "absolute" / "human_metrics.json"),
    ]
    for spelling in spellings:
        monkeypatch.setitem(scorer.SOURCE_PIN_FILES, "paid_gate0_v2",
                            _pins_pointing_at(tmp_path, "paid_gate0_v2", spelling))
        assert red.pinned_red_human_path("paid_gate0_v2") == \
            pinned_artifact_path_192("paid_gate0_v2", "red_human"), spelling


# ---- the cross-check validates the fixture's SHAPE, exactly as the scorer does ---------------------

@pytest.mark.parametrize("broken, why", [
    ({"schema_version": 2}, "schema_version != 1"),
    ({"mode": "readiness_dev"}, "pins['mode'] != the mode being captured"),
    ({"schema_version": None, "mode": None}, "neither key present"),
])
def test_cross_check_rejects_the_fixtures_the_scorer_would_reject(tmp_path, monkeypatch, broken,
                                                                   why):
    """Review B5: require_fixture_points_here read `artifact_paths.red_human` and nothing else, while
    eval/score_gate0.py::_verify_sources additionally requires `schema_version == 1` and
    `pins["mode"] == mode` (its `source_pins_schema_or_mode` failure). A fixture with the right path
    but the wrong mode/schema was ALLOWED by the rig and REJECTED by the scorer -- discovered only
    at scoring, which is precisely the failure class this guard exists to pre-empt. Aligned."""
    out = tmp_path / "out"
    pins = tmp_path / "pins_broken.json"
    payload = {"schema_version": 1, "mode": "paid_gate0_v2",
               "artifact_paths": {"red_human": str(out / "human_metrics.json")}}
    payload.update(broken)
    payload = {k: v for k, v in payload.items() if v is not None}
    pins.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, "paid_gate0_v2", pins)
    msg = red.require_fixture_points_here("paid_gate0_v2", str(out))
    assert msg is not None and "source_pins_schema_or_mode" in msg, why


def test_cross_check_agrees_with_the_scorers_own_schema_and_mode_predicate(tmp_path, monkeypatch):
    """Bind the two, rather than asserting the rule twice: for a matrix of fixtures, the rig's
    verdict must agree with the scorer's literal `schema_version != 1 or mode != <mode>` predicate.
    A divergence here is the drift this whole workstream removes."""
    out = tmp_path / "out"
    for schema in (1, 2, None):
        for pin_mode in ("paid_gate0_v2", "paid_gate0", None):
            payload = {"artifact_paths": {"red_human": str(out / "human_metrics.json")}}
            if schema is not None:
                payload["schema_version"] = schema
            if pin_mode is not None:
                payload["mode"] = pin_mode
            pins = tmp_path / "pins_matrix.json"
            pins.write_text(json.dumps(payload), encoding="utf-8")
            monkeypatch.setitem(scorer.SOURCE_PIN_FILES, "paid_gate0_v2", pins)
            scorer_rejects = schema != 1 or pin_mode != "paid_gate0_v2"
            rig_rejects = red.require_fixture_points_here("paid_gate0_v2", str(out)) is not None
            assert rig_rejects == scorer_rejects, (schema, pin_mode)


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


def _redirect_all_modes(monkeypatch, tmp_path):
    """Every mode's real_out redirected into tmp. NOTHING in this file may write under the actual
    runs/ tree -- these tests are about a guard that protects append-only banked evidence, so the
    tests themselves must not be the thing that damages it."""
    dirs = {}
    for mode in red.MODE_CONFIG:
        d = tmp_path / f"real_{mode}"
        dirs[mode] = d
        monkeypatch.setitem(red.MODE_CONFIG, mode, {"real_out": str(d)})
    return dirs


def _bank(d: Path) -> None:
    """Populate a stand-in real baseline directory with the two append-only files that matter: the
    canonical artifact three fixtures freeze by digest, and the oracle trace its numbers came from."""
    d.mkdir(parents=True, exist_ok=True)
    (d / "human_metrics.json").write_text(
        json.dumps({"schema_version": 1, "mode": "readiness_dev", "attempt_number": 1}),
        encoding="utf-8")
    (d / "oracle.jsonl").write_text('{"BANKED_SENTINEL": true}\n', encoding="utf-8")


def _intact(d: Path) -> bool:
    return (sorted(p.name for p in d.iterdir()) == ["human_metrics.json", "oracle.jsonl"]
            and (d / "oracle.jsonl").read_text(encoding="utf-8") == '{"BANKED_SENTINEL": true}\n')


# The spelling-attack tests marked below probe Win32 PATH SEMANTICS: a case-insensitive filesystem,
# trailing dot/space stripping (GetFullPathNameW), `mklink /J` junctions, 8.3 short names, and the
# UNC / extended-length / device namespaces. None of these exist on POSIX -- `FOO` and `foo` are
# DIFFERENT directories there (`str(tmp_path).upper()` even lands on an uncreatable `/TMP/...`),
# `red.` is a different name from `red`, and a `\\?\...` string is just a funny filename -- so those
# tests run only where the rig itself runs (David's Windows machine; same reasoning as
# test_run_gate0_codex_launcher.py's requires_windows_powershell). The guard logic that IS
# platform-independent stays exercised on the Linux CI runner: the foreign-mode clause, --test's
# clause, refuse-before-mkdir, directory-wideness and the relative/`..`/trailing-sep spellings all
# run everywhere, and _spellings() swaps the junction row for an os.symlink row off-Windows so the
# realpath link-resolution axis is proven there too.
requires_win32_path_semantics = pytest.mark.skipif(
    os.name != "nt",
    reason="probes Win32 path semantics (case-insensitive filesystem, trailing dot/space "
           "stripping, junctions, 8.3 short names, UNC/device namespaces) that POSIX does not "
           "have; the platform-independent guard clauses stay covered by the unmarked tests",
)


def _hostile_spellings(d: Path):
    r"""Review E1/E2: the spellings that walked past the `normcase`+`realpath`-ONLY form that D3
    introduced. Kept SEPARATE from `_spellings` below on purpose -- these are spellings a legitimate
    capture may never use, so unlike D3's they cannot double as the write-side controls that
    test_test_mode_refuses_under_every_modes_real_path_for_every_flag_and_spelling counts.

    Two families, closed by two different mechanisms, and the labels say which:

    * TRAILING DOT / SPACE (E2, a regression D3 introduced) -- Win32 strips both from the leaf, so
      `...\red.` opens `...\red`. `abspath` strips them; `realpath` does not. Closed by comparing the
      UNION of both normalisations, which is why D3's REPLACEMENT of one with the other was the bug.
    * EXTENDED-LENGTH / UNC / DEVICE (E1, pre-existing, present on `322499f` too) -- `realpath` and
      `abspath` both return these VERBATIM. `\\?\<drive>` is closed by stripping the prefix; the
      share and device forms cannot be closed by normalisation at all (unbounded host aliases) and
      are refused outright by the guard's clause (a0).
    * DEVICE NAMESPACE BEHIND AN EXTENDED-LENGTH PREFIX (E6, pre-existing on all three heads) --
      `\\?\Volume{GUID}\...` and `\\?\GLOBALROOT\GLOBAL??\C:\...`. These escaped *because* of the
      strip: it leaves a remainder that is neither `\\`-prefixed nor drive-rooted, so (a0) saw a
      non-separator first character and `_under_real_path` resolved the remainder as RELATIVE. Both
      renamed a stand-in banked `oracle.jsonl` away under `--test`. Closed by (a0)'s second clause.

    No junction/8.3 row here: those are D3's and `_spellings` already carries them."""
    s = str(d)
    assert os.path.splitdrive(s)[0].endswith(":"), f"expected a drive-rooted tmp path, got {s!r}"
    drive = os.path.splitdrive(s)[0].rstrip(":")
    unc_tail = "\\" + drive + "$" + s[2:]
    return [("trailing dot", s + "."),
            ("trailing space", s + " "),
            ("trailing dot + sep", s + "." + os.sep),
            (r"\\?\ extended-length", "\\\\?\\" + s),
            (r"\\?\ extended-length + trailing dot", "\\\\?\\" + s + "."),
            (r"\\?\UNC\ admin share", "\\\\?\\UNC\\localhost" + unc_tail),
            (r"\\localhost\ admin share", "\\\\localhost" + unc_tail),
            (r"\\127.0.0.1\ admin share", "\\\\127.0.0.1" + unc_tail),
            (r"\\.\ device namespace", "\\\\.\\" + s),
            (r"\\?\Volume{GUID}\ device namespace", _volume_guid_spelling(s)),
            (r"\\?\GLOBALROOT\ device namespace", _globalroot_spelling(s))]


def _volume_guid_spelling(s: str) -> str:
    r"""`C:\x\y` -> `\\?\Volume{GUID}\x\y`, the volume-GUID spelling of the same object. ASSERTS
    rather than skipping: a fabricated GUID would make every row that uses it pass vacuously, which
    is precisely the failure mode these tests exist to prevent. Any user can obtain this -- `mountvol
    C: /L` prints it, no admin and no setup -- so there is no legitimate reason for it to be absent.
    """
    import ctypes
    mount_point = os.path.splitdrive(s)[0] + "\\"
    buf = ctypes.create_unicode_buffer(64)
    assert ctypes.windll.kernel32.GetVolumeNameForVolumeMountPointW(mount_point, buf, 64), \
        f"GetVolumeNameForVolumeMountPointW failed for {mount_point!r}"
    return buf.value.rstrip("\\") + s[2:]


def _globalroot_spelling(s: str) -> str:
    r"""`C:\x\y` -> `\\?\GLOBALROOT\GLOBAL??\C:\x\y`, the object-manager spelling of the same object.
    Structural (no lookup), available to any user."""
    return "\\\\?\\GLOBALROOT\\GLOBAL??\\" + s


# The vacuity floor for a _spellings() matrix. Windows carries all of D3's rows; POSIX carries the
# platform-independent five (plain, trailing sep, forward slashes, dotdot round-trip, symlink) --
# the case rows would name genuinely DIFFERENT directories on a case-sensitive filesystem, so
# carrying them there would prove nothing about the guard. On Windows this stays 8, exactly the
# literal it replaces.
SPELLING_FLOOR = 8 if os.name == "nt" else 5


def _spellings(d: Path):
    """Every way of naming the SAME directory `d` that review D3 attacked, plus the ones already
    caught. Returns (label, spelling) pairs; the junction and 8.3 rows are skipped rather than faked
    if the platform will not produce them. Off-Windows the case rows are dropped (different
    directories there, not different spellings of one) and the junction row becomes an `os.symlink`
    row -- the analogous POSIX escape, which `realpath` exists to close -- so the link-resolution
    axis still runs on the Linux CI runner."""
    out = [("plain", str(d)),
           ("trailing sep", str(d) + os.sep),
           ("forward slashes", str(d).replace("\\", "/")),
           ("dotdot round-trip", str(d / ".." / d.name))]
    if os.name == "nt":
        out += [("UPPER", str(d).upper()),
                ("lower", str(d).lower()),
                ("mixed-case leaf", str(d.parent / d.name.upper()))]
    junction = d.parent / (d.name + "_junc")
    if os.name != "nt":
        os.symlink(str(d), str(junction), target_is_directory=True)
        out.append(("symlink", str(junction)))
    elif subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(d)],
                        capture_output=True, text=True).returncode == 0:
        out.append(("junction", str(junction)))
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(str(d), buf, 1024) and buf.value != str(d):
            out.append(("8.3 short name", buf.value))
    except Exception:                                                       # pragma: no cover
        pass
    return out


# ---- D1/D2: a mode may never write under ANOTHER mode's real baseline path -------------------------

def test_a_foreign_modes_baseline_directory_is_refused_for_every_flag_combination(
        tmp_path, monkeypatch, fake_pyboy_raises):
    """REGRESSION (review D1/D2), and the one this fix round itself introduced.

    `a4e5969` refused `--mode paid_gate0_v2 --i-am-human --out <banked readiness_dev dir>
    --allow-retake "..."` BY ACCIDENT: the cross-check was comparing the mode's default directory
    against the pin, and those differ today. Binding the cross-check to `args.out` (review B2) made
    the comparison honest and thereby made it `pinned == target` -- and all three fixtures currently
    pin `red_human` AT the banked directory, so the only thing blocking that write became a blessing.
    Measured at `06820ab`: the banked `oracle.jsonl` was RENAMED away and an INCOMPLETE artifact
    written in its place.

    The replacement is not a comparison against anything fixture-derived. `args.out` is this rig's
    single write choke point, and no mode may name a DIFFERENT mode's real path there, whatever
    --test/--i-am-human/--allow-retake say. Proven over mode x foreign-target x --i-am-human x
    --allow-retake x --test = 3*2*2*2*2 = 48 run() calls, with the cross-check neutralised so this
    guard alone is what holds."""
    dirs = _redirect_all_modes(monkeypatch, tmp_path)
    monkeypatch.setattr(red, "require_fixture_points_here", lambda mode, out_dir: None)
    for d in dirs.values():
        _bank(d)

    violations = []
    for mode in sorted(red.MODE_CONFIG):
        for target_mode, target in sorted(dirs.items()):
            if target_mode == mode:
                continue
            for i_am_human in (False, True):
                for allow_retake in (None, "a stated reason"):
                    for test in (False, True):
                        rc = red.run(_args(tmp_path, out=target, test=test, mode=mode,
                                           i_am_human=i_am_human, allow_retake=allow_retake))
                        if rc != 2 or not _intact(target):
                            violations.append((mode, target_mode, i_am_human, bool(allow_retake),
                                               test, rc, sorted(p.name for p in target.iterdir())))
    assert violations == [], f"wrote under a foreign mode's baseline path: {violations}"


def test_the_reviewers_d1_invocation_is_refused_against_todays_fixture_state(tmp_path, monkeypatch,
                                                                              capsys,
                                                                              fake_pyboy_raises):
    """Review D1 verbatim, with the fixture state that actually exists today rather than a
    neutralised cross-check: ALL THREE fixtures pin `artifact_paths.red_human` at the banked
    readiness_dev artifact (this file's own
    test_all_three_fixtures_currently_pin_the_same_banked_red_baseline asserts that of the real
    ones). The cross-check therefore BLESSES this invocation -- asserted below, so the test cannot
    quietly start passing for the wrong reason -- and the write-path guard is the only thing left."""
    dirs = _redirect_all_modes(monkeypatch, tmp_path)
    banked = dirs["readiness_dev"]
    _bank(banked)
    for mode in red.MODE_CONFIG:
        monkeypatch.setitem(scorer.SOURCE_PIN_FILES, mode,
                            _pins_pointing_at(tmp_path, mode, banked / "human_metrics.json"))
    assert red.require_fixture_points_here("paid_gate0_v2", str(banked)) is None   # it blesses it

    rc = red.run(_args(tmp_path, out=banked, test=False, mode="paid_gate0_v2", i_am_human=True,
                       allow_retake="a stated reason"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "under another mode's real baseline path" in err and "No flag overrides this" in err
    assert _intact(banked), "the banked directory was modified"


def test_readiness_dev_cannot_write_into_a_paid_modes_directory(tmp_path, monkeypatch, capsys,
                                                                 fake_pyboy_raises):
    """Review D2. readiness_dev is exempt from the fixture cross-check (deliberately -- its own
    baseline is banked and its pin frozen), so with `--out` pointed at a paid directory there was NO
    guard at all: measured at `06820ab` it wrote `human_metrics.INCOMPLETE_*.json` into
    `runs/gate0_paid_v2_human_baseline/red/` and renamed that directory's `oracle.jsonl` away, with
    only a `warning:` on stderr. A readiness_dev-stamped artifact sitting at the v2 pin is
    `human_metric_identity:red` at scoring -- the failure class this rig exists to pre-empt."""
    dirs = _redirect_all_modes(monkeypatch, tmp_path)
    paid_v2 = dirs["paid_gate0_v2"]
    _bank(paid_v2)
    rc = red.run(_args(tmp_path, out=paid_v2, test=False, mode="readiness_dev"))
    assert rc == 2
    assert "under another mode's real baseline path" in capsys.readouterr().err
    assert _intact(paid_v2)


def test_the_write_guard_refuses_before_exists_and_before_any_mkdir(tmp_path, monkeypatch,
                                                                     fake_pyboy_raises):
    """Ported property from PR #196's write_artifact(): the guard runs BEFORE the existence test and
    before any mkdir, so a refusal creates NOTHING on disk. The existence check alone protects only
    files that happen to already be there -- in a fresh checkout, container or worktree it protects
    nothing at all."""
    dirs = _redirect_all_modes(monkeypatch, tmp_path)
    monkeypatch.setattr(red, "require_fixture_points_here", lambda mode, out_dir: None)
    banked = dirs["readiness_dev"]
    assert not banked.exists()
    assert red.run(_args(tmp_path, out=banked, test=False, mode="paid_gate0_v2",
                         i_am_human=True)) == 2
    assert not banked.exists(), "a refusal created the directory it refused to write"


def test_the_write_guard_is_directory_wide_not_just_the_canonical_artifact(tmp_path, monkeypatch,
                                                                            fake_pyboy_raises):
    """Ported property from PR #196: the guard binds the DIRECTORY, so it covers the append-only
    `oracle.jsonl` (which run() RENAMES on any fresh attempt) and every subdirectory, not only
    `human_metrics.json`. A directory holding only the oracle trace -- no canonical artifact, so the
    retake guard cannot fire -- must still be untouchable."""
    dirs = _redirect_all_modes(monkeypatch, tmp_path)
    monkeypatch.setattr(red, "require_fixture_points_here", lambda mode, out_dir: None)
    banked = dirs["readiness_dev"]
    banked.mkdir(parents=True)
    (banked / "oracle.jsonl").write_text('{"BANKED_SENTINEL": true}\n', encoding="utf-8")
    for out in (banked, banked / "nested" / "deeper"):
        assert red.run(_args(tmp_path, out=out, test=False, mode="paid_gate0_v2",
                             i_am_human=True)) == 2, out
    assert sorted(p.name for p in banked.iterdir()) == ["oracle.jsonl"]
    assert (banked / "oracle.jsonl").read_text(encoding="utf-8") == '{"BANKED_SENTINEL": true}\n'


def test_a_mode_may_still_write_its_own_baseline_directory(tmp_path, monkeypatch, fake_pyboy_raises):
    """The guard must not be a blanket ban -- unlike PR #196's tool, this rig legitimately writes
    into a real baseline directory: that is what a capture IS. Control for the two tests above; if
    this ever fails the guard has stopped being "no FOREIGN mode's path" and become "no path"."""
    dirs = _redirect_all_modes(monkeypatch, tmp_path)
    monkeypatch.setattr(red, "require_fixture_points_here", lambda mode, out_dir: None)
    for mode, target in sorted(dirs.items()):
        rc = red.run(_args(tmp_path, out=target, test=False, mode=mode, i_am_human=True))
        assert rc == 2                                   # the FAKED PyBoy failure, not a refusal
        assert list(target.glob("human_metrics.INCOMPLETE_*.json")), mode


# ---- D3: the guard must survive a path-SPELLING attack, not just a flag matrix ---------------------

def test_the_write_guard_survives_every_spelling_of_a_foreign_baseline_directory(
        tmp_path, monkeypatch, fake_pyboy_raises):
    """Review D3: the 36-combination matrix varied FLAGS only, never path spelling, and
    `_under_real_path`'s `normpath`/`abspath` form let five different spellings of one directory
    through -- `UPPER`, `lower`, a mixed-case leaf, a `mklink /J` junction (no admin required) and an
    8.3 short name -- each writing an INCOMPLETE artifact into a stand-in banked directory and
    renaming its `oracle.jsonl` away. `normcase` + `realpath` closes all five (and keeps the seven
    already-caught spellings caught; the negative controls below are what keeps it from
    over-matching)."""
    dirs = _redirect_all_modes(monkeypatch, tmp_path)
    monkeypatch.setattr(red, "require_fixture_points_here", lambda mode, out_dir: None)
    banked = dirs["readiness_dev"]
    _bank(banked)

    spellings = _spellings(banked)
    assert len(spellings) >= SPELLING_FLOOR, f"spelling matrix too thin to prove anything: {spellings}"
    violations = []
    for label, spelling in spellings:
        for test in (False, True):
            rc = red.run(_args(tmp_path, out=spelling, test=test, mode="paid_gate0_v2",
                               i_am_human=True, allow_retake="a stated reason"))
            if rc != 2 or not _intact(banked):
                violations.append((label, test, rc, sorted(p.name for p in banked.iterdir())))
    assert violations == [], f"a path spelling walked past the write guard: {violations}"

    # negative controls: the hardening must not start swallowing unrelated directories
    for label, other in (("unrelated", tmp_path / "somewhere_else"),
                         ("sibling sharing the prefix", Path(str(banked) + "_other"))):
        assert not red._under_real_path(str(other), str(banked)), label


@requires_win32_path_semantics
def test_the_write_guard_survives_spelling_when_the_directory_does_not_exist_yet(
        tmp_path, monkeypatch, fake_pyboy_raises):
    """The same spelling attack in a FRESH CHECKOUT -- and the reason `normcase` is not redundant
    beside `realpath`.

    `os.path.realpath` canonicalises the on-disk case only for a path that ALREADY EXISTS (it asks
    the filesystem); for one that does not, the case the caller typed survives verbatim. So
    `realpath` alone closes the junction and the 8.3 escapes but leaves UPPER/lower/mixed-case open
    in exactly the situation PR #196's guard comment singles out -- a fresh checkout, container or
    worktree, where `runs/` has not been populated yet and an existence check protects nothing.
    Caught as a surviving mutant (realpath without normcase); `normcase` is what closes it.

    Nothing may be created under ANY spelling: the assertion is on the parent directory, so a run
    that quietly created `.../REAL_PAID_GATE0_V2/` beside the expected path fails too."""
    dirs = _redirect_all_modes(monkeypatch, tmp_path)
    monkeypatch.setattr(red, "require_fixture_points_here", lambda mode, out_dir: None)
    paid_v2 = dirs["paid_gate0_v2"]
    assert not paid_v2.exists(), "this test is about the not-yet-created case"

    violations = []
    for label, spelling in (("plain", str(paid_v2)),
                            ("UPPER", str(paid_v2).upper()),
                            ("lower", str(paid_v2).lower()),
                            ("mixed-case leaf", str(paid_v2.parent / paid_v2.name.upper()))):
        rc = red.run(_args(tmp_path, out=spelling, test=False, mode="readiness_dev"))
        created = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
        if rc != 2 or created:
            violations.append((label, rc, created))
    assert violations == [], f"a spelling walked past the guard in a fresh checkout: {violations}"


def test_test_mode_refuses_under_every_modes_real_path_for_every_flag_and_spelling(
        tmp_path, monkeypatch, fake_pyboy_raises):
    """REGRESSION (review B3), the one true regression against origin/main.

    On `322499f` `_under_real_path(out)` had a single referent, so `--test` could NEVER write under
    `runs/gate0_human_baseline/red`, whatever else was passed. `a4e5969` scoped the check to the
    SELECTED mode's directory (inherited verbatim from the MiniWoB sibling -- the one place copying
    it weakened this rig), and the reviewer got `--test --mode paid_gate0_v2 --out
    runs/gate0_human_baseline/red` to write an INCOMPLETE artifact into the banked directory and
    rename the banked append-only oracle.jsonl away.

    The invariant is restored and proven over mode x target-directory x --i-am-human x
    --allow-retake x SPELLING. The spelling axis is review D3's: the previous version of this test
    varied flags only, so it certified as "unconditional" a helper that five different spellings of
    one path walked straight past.

    The cross-check is neutralised throughout so that --test alone is what holds -- the guarantee
    must not depend on another guard happening to fire first."""
    dirs = _redirect_all_modes(monkeypatch, tmp_path)
    monkeypatch.setattr(red, "require_fixture_points_here", lambda mode, out_dir: None)
    # Computed ONCE per directory, up front: _spellings() creates a junction, so calling it twice for
    # the same target silently yields a shorter list the second time -- which would quietly shrink
    # the matrix instead of failing.
    spellings = {}
    for target in dirs.values():
        target.mkdir(parents=True, exist_ok=True)
        spellings[target] = _spellings(target)
        assert len(spellings[target]) >= SPELLING_FLOOR, f"spelling matrix too thin: {spellings[target]}"

    violations, controls = [], []
    for mode in sorted(red.MODE_CONFIG):
        for target_mode, target in sorted(dirs.items()):
            for label, spelling in spellings[target]:
                for i_am_human in (False, True):
                    for allow_retake in (None, "a stated reason"):
                        combo = (mode, target_mode, label, i_am_human, bool(allow_retake))
                        rc = red.run(_args(tmp_path, out=spelling, test=True, mode=mode,
                                           i_am_human=i_am_human, allow_retake=allow_retake))
                        wrote = [p.name for p in target.iterdir()]
                        if rc != 2 or wrote:
                            violations.append((combo, rc, wrote))
                        # control: the SAME combination without --test, into the mode's OWN
                        # directory, must be able to reach the emulator (and so write), otherwise
                        # the matrix above proves nothing. Contents are cleared rather than the
                        # directory removed -- rmtree would invalidate this target's junction and
                        # 8.3 spellings for every later iteration.
                        if target_mode == mode:
                            red.run(_args(tmp_path, out=spelling, test=False, mode=mode,
                                          i_am_human=i_am_human, allow_retake=allow_retake))
                            written = list(target.iterdir())
                            if written:
                                controls.append(combo)
                                for p in written:
                                    p.unlink()

    assert violations == [], f"--test wrote under a real baseline path: {violations}"
    # Own-directory controls only: a FOREIGN directory is now refused with or without --test (review
    # D1/D2), so it can no longer serve as a control for --test specifically. Four (mode,
    # --i-am-human) pairs get past the acknowledgement gate -- readiness_dev with the flag either
    # way, and each paid mode with it -- times 2 --allow-retake values times that mode's own spelling
    # matrix. Everything the matrix blocked at a mode's OWN directory, it blocked BECAUSE of --test.
    expected = sum(2 * (2 if mode == "readiness_dev" else 1) * len(spellings[dirs[mode]])
                   for mode in red.MODE_CONFIG)
    assert len(controls) == expected, \
        f"matrix is vacuous -- only {len(controls)} of {expected} combinations wrote"


# ---- E1/E2: the spellings the D3 form was blind to ------------------------------------------------

@requires_win32_path_semantics
def test_the_write_guard_survives_the_e1_e2_spellings_when_the_target_exists(
        tmp_path, monkeypatch, fake_pyboy_raises):
    r"""REGRESSION (review E1). `--test --mode readiness_dev --allow-retake "x" --out "\\?\<banked>"`
    renamed a stand-in banked `oracle.jsonl` away and wrote an INCOMPLETE artifact in, at `d8cbe00`
    AND at `322499f`. Same via `\\localhost\<drive>$\...`. The plain spelling of the same command was
    correctly refused, so it was purely the spelling.

    Driven against a FOREIGN mode, both `--test` values, cross-check neutralised so the write-path
    guard alone holds."""
    dirs = _redirect_all_modes(monkeypatch, tmp_path)
    monkeypatch.setattr(red, "require_fixture_points_here", lambda mode, out_dir: None)
    banked = dirs["readiness_dev"]
    _bank(banked)

    violations = []
    for label, spelling in _hostile_spellings(banked):
        for test in (False, True):
            rc = red.run(_args(tmp_path, out=spelling, test=test, mode="paid_gate0_v2",
                               i_am_human=True, allow_retake="a stated reason"))
            if rc != 2 or not _intact(banked):
                violations.append((label, test, rc, sorted(p.name for p in banked.iterdir())))
    assert violations == [], f"an E1/E2 spelling walked past the write guard: {violations}"


@requires_win32_path_semantics
def test_the_write_guard_survives_the_e1_e2_spellings_when_the_target_does_not_exist_yet(
        tmp_path, monkeypatch, fake_pyboy_raises):
    r"""REGRESSION (review E2) -- the one this PR itself introduced, and the reason the guard now
    takes the UNION of two normalisations instead of swapping one for the other.

    `322499f`'s `normpath`+`abspath` form CAUGHT `<dir>.` and `<dir> ` (Win32 `GetFullPathNameW`
    strips a trailing dot or space from the leaf). `d8cbe00`'s `normcase`+`realpath` form does not,
    for a path that does not exist yet -- and `--mode readiness_dev --out "<paid_v2 dir>."` duly wrote
    an INCOMPLETE artifact into the paid v2 directory.

    THE NOT-YET-CREATED STATE IS THE LIVE ONE: `runs/gate0_paid_human_baseline/red` and
    `runs/gate0_paid_v2_human_baseline/red` do not exist on this checkout, which is exactly the
    condition the escape needs. Nothing may be created under ANY spelling -- the assertion is on the
    parent, so a run that quietly created a sibling directory fails too."""
    dirs = _redirect_all_modes(monkeypatch, tmp_path)
    monkeypatch.setattr(red, "require_fixture_points_here", lambda mode, out_dir: None)
    paid_v2 = dirs["paid_gate0_v2"]
    assert not paid_v2.exists(), "this test is about the not-yet-created case"

    violations = []
    for label, spelling in _hostile_spellings(paid_v2):
        rc = red.run(_args(tmp_path, out=spelling, test=False, mode="readiness_dev"))
        created = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
        if rc != 2 or created:
            violations.append((label, rc, created))
    assert violations == [], f"an E1/E2 spelling walked past the guard in a fresh checkout: {violations}"


@requires_win32_path_semantics
def test_test_mode_refuses_the_e1_e2_spellings_of_a_modes_own_real_path(
        tmp_path, monkeypatch, fake_pyboy_raises):
    r"""Review E1's demonstration verbatim: the escape was reached with `--mode readiness_dev`, whose
    OWN directory the foreign-path clause permits and which is exempt from the fixture cross-check --
    so `--test`'s clause was the only thing behind it, and there was nothing behind that.

    `--test` may never write under ANY mode's real path, in ANY spelling."""
    dirs = _redirect_all_modes(monkeypatch, tmp_path)
    monkeypatch.setattr(red, "require_fixture_points_here", lambda mode, out_dir: None)
    violations = []
    for mode, target in sorted(dirs.items()):
        _bank(target)
        for label, spelling in _hostile_spellings(target):
            rc = red.run(_args(tmp_path, out=spelling, test=True, mode=mode, i_am_human=True,
                               allow_retake="a stated reason"))
            if rc != 2 or not _intact(target):
                violations.append((mode, label, rc, sorted(p.name for p in target.iterdir())))
    assert violations == [], f"--test wrote under a real baseline path via a spelling: {violations}"


@requires_win32_path_semantics
def test_a_unc_or_device_out_is_refused_outright_with_its_own_message(tmp_path, monkeypatch, capsys,
                                                                       fake_pyboy_raises):
    r"""Clause (a0). Unlike every other spelling, the share forms are refused because they CANNOT be
    compared, not because the comparison caught them -- `\\localhost\C$\x`, `\\127.0.0.1\C$\x` and
    the machine name are unboundedly many spellings of one directory and no normalisation maps them
    back to `C:\x`. The distinct message is asserted so a future refactor cannot fold this into the
    foreign-path clause and silently make it depend on a comparison that does not work."""
    _redirect_all_modes(monkeypatch, tmp_path)
    monkeypatch.setattr(red, "require_fixture_points_here", lambda mode, out_dir: None)
    unrelated = tmp_path / "nowhere_near_a_baseline"
    drive = os.path.splitdrive(str(unrelated))[0].rstrip(":")
    for spelling in ("\\\\localhost\\" + drive + "$" + str(unrelated)[2:],
                     "\\\\?\\UNC\\localhost\\" + drive + "$" + str(unrelated)[2:],
                     "\\\\.\\" + str(unrelated)):
        assert red.run(_args(tmp_path, out=spelling, test=False, mode="readiness_dev")) == 2
        assert "UNC share or device path" in capsys.readouterr().err, spelling
        assert not unrelated.exists()

    # the predicate itself, including the extended-length forms it must see THROUGH rather than trip on
    assert red._is_unc_or_device_path(r"\\localhost\C$\x")
    assert red._is_unc_or_device_path(r"\\?\UNC\localhost\C$\x")
    assert red._is_unc_or_device_path(r"\\.\C:\x")
    assert red._is_unc_or_device_path("//localhost/C$/x")           # forward slashes are separators too
    # E6: a prefix strip that reveals NO drive letter is a device-namespace path, and it is the strip
    # itself that hides it -- see _is_unc_or_device_path's second clause.
    assert red._is_unc_or_device_path(_volume_guid_spelling(str(tmp_path)))
    assert red._is_unc_or_device_path(_globalroot_spelling(str(tmp_path)))
    assert red._is_unc_or_device_path(r"\\?\globalroot\GLOBAL??\C:\x")   # prefix match is case-blind
    assert not red._is_unc_or_device_path(r"\\?\C:\x")              # extended-length DRIVE path: fine
    assert not red._is_unc_or_device_path(r"C:\x")
    assert not red._is_unc_or_device_path(str(tmp_path))
    assert not red._is_unc_or_device_path(r"runs\scratch")          # relative: not a device path
    assert not red._is_unc_or_device_path(r"..\scratch")
    assert not red._is_unc_or_device_path(r"C:scratch")             # drive-relative


def test_the_extended_prefix_strip_maps_both_families_back_to_their_plain_spelling():
    r"""The UNC branch of `_strip_extended_prefix` is pinned HERE, directly, rather than through a
    refusal -- and the reason is a mutation-coverage regression the E6 fix ITSELF caused.

    Before E6, deleting that branch was killed by the refusal tests: `\\?\UNC\...` then stopped
    looking like a UNC path and clause (a0) let it through. After E6 the new clause catches
    `\\?\UNC\...` regardless (stripping `\\?\` leaves a remainder with no drive letter), so no
    refusal test can tell the branch is gone any more -- it survived a re-run that killed 18 of 20.

    The branch is still load-bearing, on precisely the checkout (a0) deliberately does NOT fire for:
    a share-hosted one, where every referent is UNC, (a0) switches itself off, and this strip is the
    only thing that makes `\\?\UNC\host\share\x` compare equal to `\\host\share\x`."""
    assert red._strip_extended_prefix(r"\\?\UNC\localhost\C$\x") == r"\\localhost\C$\x"
    assert red._strip_extended_prefix(r"\\?\unc\localhost\C$\x") == r"\\localhost\C$\x"
    assert red._strip_extended_prefix(r"\\?\C:\x") == r"C:\x"
    assert red._strip_extended_prefix(r"C:\x") == r"C:\x"
    # the share-checkout comparison the UNC branch exists for, which (a0) is off for by design
    assert red._under_real_path(r"\\?\UNC\server\share\runs\red", r"\\server\share\runs\red")


@requires_win32_path_semantics
def test_the_two_device_namespace_spellings_really_do_open_the_same_directory(tmp_path):
    r"""NON-VACUITY for the two E6 rows `_hostile_spellings` now carries.

    Every other test that uses them asserts a REFUSAL, so a spelling that quietly did not name the
    referent at all would make those rows pass for the wrong reason -- the exact shape review E1/E2
    kept finding. Ground truth, therefore: write THROUGH each device spelling and confirm the bytes
    land in the drive-letter directory. This is what makes `\\?\Volume{GUID}\...` and
    `\\?\GLOBALROOT\GLOBAL??\...` a real escape rather than a plausible-looking one."""
    referent = tmp_path / "referent"
    referent.mkdir()
    for label, spelling in (("volume GUID", _volume_guid_spelling(str(referent))),
                            ("GLOBALROOT", _globalroot_spelling(str(referent)))):
        Path(os.path.join(spelling, f"{label}.probe")).write_text("landed", encoding="utf-8")
        landed = referent / f"{label}.probe"
        assert landed.is_file() and landed.read_text(encoding="utf-8") == "landed", \
            f"{label} spelling {spelling!r} did not open {referent!r} -- the E6 rows would be vacuous"


def test_a_plain_scratch_out_is_still_allowed_through(tmp_path, monkeypatch, fake_pyboy_raises):
    """The negative control the E1/E2 hardening needs: a union of two normalisations can only ever
    refuse MORE, so the risk it carries is a FALSE POSITIVE -- a legitimate dry-run `--out` that the
    guard starts swallowing. It must still reach the emulator (here: the faked failure)."""
    _redirect_all_modes(monkeypatch, tmp_path)
    monkeypatch.setattr(red, "require_fixture_points_here", lambda mode, out_dir: None)
    scratch = tmp_path / "scratch_dry_run"
    assert red.run(_args(tmp_path, out=scratch, test=False, mode="paid_gate0_v2",
                         i_am_human=True)) == 2          # the FAKED PyBoy failure, not a refusal
    assert list(scratch.glob("human_metrics.INCOMPLETE_*.json"))


@requires_win32_path_semantics
def test_both_normalisations_are_load_bearing_and_neither_dominates(tmp_path):
    r"""The invariant the fix round exists to protect, stated as an executable claim rather than a
    comment: `realpath` and `abspath` each catch a spelling the other misses, so the guard must
    compare the UNION. Replacing either with the other reopens a hole -- which is precisely what
    happened between `322499f` and `d8cbe00`.

    Also pins the SYMMETRY invariant: `_under_real_path` normalises the REFERENT as well as the
    candidate, which is what makes it immune to a junction on a shared prefix (`runs/` already holds
    26 of them). A guard that resolves only the candidate escapes on every spelling there."""
    existing = tmp_path / "exists" / "red"
    existing.mkdir(parents=True)
    absent = tmp_path / "absent" / "red"

    for d in (existing, absent):
        # abspath-only territory: realpath leaves a trailing dot/space on the leaf verbatim
        assert red._under_real_path(str(d) + ".", str(d)), d
        assert red._under_real_path(str(d) + " ", str(d)), d
        # neither normalisation touches an extended-length prefix; stripping it is what closes this
        assert red._under_real_path("\\\\?\\" + str(d), str(d)), d
        # ... and the guard must not over-match while doing it
        assert not red._under_real_path(str(d) + "2.", str(d)), d
        assert not red._under_real_path(str(d.parent), str(d)), d

    # realpath-only territory, and the symmetry: a junction is seen through from EITHER side
    junction = tmp_path / "exists" / "red_junc"
    if subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(existing)],
                      capture_output=True, text=True).returncode == 0:
        assert red._under_real_path(str(junction), str(existing))
        assert red._under_real_path(str(existing), str(junction))     # SYMMETRY: referent resolved too
        assert red._under_real_path(str(junction) + ".", str(existing))   # both, at once


def test_test_mode_refuses_even_when_the_fixture_blesses_the_banked_directory(tmp_path, monkeypatch,
                                                                              capsys,
                                                                              fake_pyboy_raises):
    """The reviewer's exact B3 shape, with the cross-check deliberately made permissive: a hostile
    (or simply stale) v2 fixture that points at the banked readiness_dev directory. The cross-check
    then PASSES and the path guards are all that stand between a smoke test and the banked artifact.
    On `a4e5969` this wrote; it must refuse.

    Since review D1 the FOREIGN-path clause catches this one first (it is unconditional, so it does
    not wait for --test), which is the point: --test is no longer load-bearing here. --test's own
    clause is what stops the same thing at a mode's OWN directory, pinned in the sibling test
    below."""
    dirs = _redirect_all_modes(monkeypatch, tmp_path)
    banked = dirs["readiness_dev"]
    banked.mkdir(parents=True)
    (banked / "oracle.jsonl").write_text('{"BANKED_SENTINEL": true}\n', encoding="utf-8")
    monkeypatch.setitem(scorer.SOURCE_PIN_FILES, "paid_gate0_v2",
                        _pins_pointing_at(tmp_path, "paid_gate0_v2",
                                          banked / "human_metrics.json"))
    assert red.require_fixture_points_here("paid_gate0_v2", str(banked)) is None   # it blesses it
    args = _args(tmp_path, out=banked, test=True, mode="paid_gate0_v2", i_am_human=True,
                 allow_retake="simulating the hazard")
    assert red.run(args) == 2
    assert "under another mode's real baseline path" in capsys.readouterr().err
    assert sorted(p.name for p in banked.iterdir()) == ["oracle.jsonl"]
    assert '{"BANKED_SENTINEL": true}\n' == (banked / "oracle.jsonl").read_text(encoding="utf-8")


def test_test_mode_still_refuses_a_modes_own_real_path(tmp_path, monkeypatch, capsys,
                                                        fake_pyboy_raises):
    """--test's OWN clause, isolated from the foreign-path clause: writing into the selected mode's
    own real directory is legitimate WITHOUT --test (that is what a capture is), and refused WITH
    it. Nothing else in this file can fail if this clause is deleted, since every other --test
    scenario now trips the unconditional foreign-path guard first."""
    dirs = _redirect_all_modes(monkeypatch, tmp_path)
    monkeypatch.setattr(red, "require_fixture_points_here", lambda mode, out_dir: None)
    banked = dirs["readiness_dev"]
    banked.mkdir(parents=True)
    (banked / "oracle.jsonl").write_text('{"BANKED_SENTINEL": true}\n', encoding="utf-8")
    assert red.run(_args(tmp_path, out=banked, test=True, mode="readiness_dev",
                         allow_retake="simulating the hazard")) == 2
    assert "ANY mode's real baseline path" in capsys.readouterr().err
    assert sorted(p.name for p in banked.iterdir()) == ["oracle.jsonl"]
