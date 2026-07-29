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
import os
import subprocess
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
# The two held-out modes, as a LITERAL. Every test below that needs to enumerate them parametrizes
# over THIS, never over `m.HELD_OUT_MODES`.
#
# Why: a test that parametrizes over the constant it exists to protect cannot fail when that constant
# is emptied -- pytest turns an empty parameter set into a SKIP, not a failure, and a skip is
# invisible in a green report. Demonstrated on this very file (PR #196 review, BLOCKING-for-edit 1):
# with `HELD_OUT_MODES = frozenset()` the full suite was 1699 passed / 20 skipped / ZERO failures,
# while `--mode paid_gate0_v2` WITHOUT `--i-am-human` exited 0 and wrote a paid-mode artifact. The
# literal here plus test_held_out_modes_are_exactly_the_two_paid_modes are what make that mutation
# fail. (Both sibling rigs already carried such a pin and this one did not:
# tests/test_capture_gate0_baseline_miniwob.py::test_v2_is_registered_as_a_held_out_mode and
# tests/test_capture_gate0_baseline_red.py::test_held_out_modes_are_exactly_the_paid_modes.)
PAID_MODES = ["paid_gate0", "paid_gate0_v2"]


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

    artifact = m.reconstruct(FIXTURE_TRACE, incomplete_path, "readiness_dev")

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

    artifact = m.reconstruct(FIXTURE_TRACE, incomplete_path, "readiness_dev")

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
        m.reconstruct(NEVER_COMPLETES_TRACE, incomplete_path, "readiness_dev")


def test_reconstruct_refuses_on_empty_input_event_times(tmp_path):
    incomplete_path = _write_incomplete(tmp_path, input_event_times=[])
    with pytest.raises(SystemExit, match="no input_event_times"):
        m.reconstruct(FIXTURE_TRACE, incomplete_path, "readiness_dev")


def test_reconstruct_refuses_on_clock_inversion(tmp_path):
    # first input strictly AFTER the detected completion row -- physically impossible, must refuse.
    incomplete_path = _write_incomplete(tmp_path, input_event_times=[FIXTURE_T_DONE + 5.0])
    with pytest.raises(SystemExit, match="clock inversion"):
        m.reconstruct(FIXTURE_TRACE, incomplete_path, "readiness_dev")


def test_reconstruct_refuses_on_started_at_mismatch(tmp_path):
    synthetic_events = [1784594079.0, FIXTURE_T_DONE]
    # started_at far from input_event_times[0] -- the cross-check the live rig's own semantics imply.
    incomplete_path = _write_incomplete(tmp_path, input_event_times=synthetic_events,
                                        started_at=_iso(synthetic_events[0] + 30.0))
    with pytest.raises(SystemExit, match="clock-start cross-check failed"):
        m.reconstruct(FIXTURE_TRACE, incomplete_path, "readiness_dev")


def test_reconstruct_allows_missing_started_at_field(tmp_path):
    # Cross-check only fires when the INCOMPLETE artifact actually carries started_at.
    synthetic_events = [1784594079.0, FIXTURE_T_DONE]
    incomplete_path = _write_incomplete(tmp_path, input_event_times=synthetic_events, started_at=None)
    artifact = m.reconstruct(FIXTURE_TRACE, incomplete_path, "readiness_dev")
    assert artifact["completion_row_index"] == FIXTURE_COMPLETION_ROW


def test_reconstruct_refuses_on_empty_trace(tmp_path):
    empty_trace = tmp_path / "empty.jsonl"
    empty_trace.write_text("", encoding="utf-8")
    incomplete_path = _write_incomplete(tmp_path, input_event_times=[1.0], started_at=_iso(1.0))
    with pytest.raises(SystemExit, match="no rows"):
        m.reconstruct(empty_trace, incomplete_path, "readiness_dev")


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
    red_human = m.reconstruct(FIXTURE_TRACE, incomplete_path, "readiness_dev")

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
                                     "--mode", "readiness_dev",
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
                                     "--mode", "readiness_dev",
                                     "--trace", str(FIXTURE_TRACE),
                                     "--incomplete", str(incomplete_path),
                                     "--out", str(out_path)])
    with pytest.raises(SystemExit, match="already exists"):
        m.main()


# ---- --mode: stamp, output directory, held-out gate ----------------------------------------------

def _argv(tmp_path, *extra):
    """Standard argv with a completing trace + a valid INCOMPLETE artifact, plus `extra`."""
    events = [1784594079.0, FIXTURE_T_DONE]
    incomplete_path = _write_incomplete(tmp_path, input_event_times=events,
                                        started_at=_iso(events[0]))
    return ["reconstruct_gate0_red_baseline.py",
            "--trace", str(FIXTURE_TRACE), "--incomplete", str(incomplete_path), *extra]


def test_mode_choices_come_from_the_frozen_scorer():
    """The CLI can never offer a mode eval.score_gate0 cannot score, or miss one it can."""
    assert m.score_gate0_modes() is scorer.MODES
    choices = m.build_arg_parser()._option_string_actions["--mode"].choices
    assert tuple(choices) == tuple(scorer.MODES)
    assert set(m.MODE_CONFIG) == set(scorer.MODES)


def test_mode_is_required_with_no_default():
    """No default: a forgotten --mode must be a parse error, not a silently-readiness_dev artifact
    (the whole defect this argument closes)."""
    action = m.build_arg_parser()._option_string_actions["--mode"]
    assert action.required is True
    assert action.default is None


def test_missing_mode_exits_without_writing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", _argv(tmp_path, "--out", str(tmp_path / "o.json")))
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2
    assert "--mode" in capsys.readouterr().err
    assert not (tmp_path / "o.json").exists()


@pytest.mark.parametrize("mode", sorted(scorer.MODES))
def test_mode_is_stamped_into_the_artifact(tmp_path, mode):
    """`mode` is taken from the argument, never a module constant -- _verify_sources requires it to
    EQUAL the mode being scored."""
    events = [1784594079.0, FIXTURE_T_DONE]
    incomplete_path = _write_incomplete(tmp_path, input_event_times=events,
                                        started_at=_iso(events[0]))
    assert m.reconstruct(FIXTURE_TRACE, incomplete_path, mode)["mode"] == mode


def test_default_out_is_derived_per_mode():
    """Pure-constant check: no I/O, so it can assert the REAL runs/ destinations without going near
    them. The three directories are the ones tools/capture_gate0_baseline_red.py's MODE_CONFIG uses,
    so a reconstruction lands where the scorer looks for that mode's capture."""
    root = m.ROOT
    assert m.MODE_CONFIG["readiness_dev"]["real_out"] == root / "runs" / "gate0_human_baseline" / "red"
    assert m.MODE_CONFIG["paid_gate0"]["real_out"] == root / "runs" / "gate0_paid_human_baseline" / "red"
    assert m.MODE_CONFIG["paid_gate0_v2"]["real_out"] == root / "runs" / "gate0_paid_v2_human_baseline" / "red"


def test_held_out_modes_are_exactly_the_two_paid_modes():
    """Pure constant, no I/O -- the pin that makes `HELD_OUT_MODES` unmutatable.

    Without it, `HELD_OUT_MODES = frozenset()` deletes the entire `--i-am-human` gate and leaves the
    full suite green, because every OTHER test that touches the gate reads the constant back: the two
    tests below would parametrize to nothing (silent skips) and the mode x flag matrix would branch on
    the mutant's own value and assert the mutant's own behaviour. This assertion is the only place in
    the file that states what the value must BE."""
    assert m.HELD_OUT_MODES == frozenset(PAID_MODES)
    assert set(m.MODE_CONFIG) - m.HELD_OUT_MODES == {"readiness_dev"}


@pytest.mark.parametrize("mode", PAID_MODES)
def test_paid_modes_require_i_am_human(tmp_path, monkeypatch, capsys, mode):
    """Refuses BEFORE reading the trace, so nothing is created anywhere."""
    out = tmp_path / "scratch" / "human_metrics.json"
    monkeypatch.setattr("sys.argv", _argv(tmp_path, "--mode", mode, "--out", str(out)))
    assert m.main() == 2
    assert "--i-am-human" in capsys.readouterr().err
    assert not out.exists()


@pytest.mark.parametrize("mode", PAID_MODES)
def test_paid_modes_proceed_with_i_am_human(tmp_path, monkeypatch, mode):
    out = tmp_path / "scratch" / "human_metrics.json"
    monkeypatch.setattr("sys.argv",
                        _argv(tmp_path, "--mode", mode, "--i-am-human", "--out", str(out)))
    assert m.main() == 0
    assert json.loads(out.read_text(encoding="utf-8"))["mode"] == mode


def test_readiness_dev_does_not_require_i_am_human(tmp_path, monkeypatch):
    """The held-out gate must stay scoped to HELD_OUT_MODES -- readiness_dev is not a paid
    denominator and must remain usable without the flag."""
    out = tmp_path / "scratch" / "human_metrics.json"
    monkeypatch.setattr("sys.argv",
                        _argv(tmp_path, "--mode", "readiness_dev", "--out", str(out)))
    assert m.main() == 0
    assert json.loads(out.read_text(encoding="utf-8"))["mode"] == "readiness_dev"


def test_mode_known_to_scorer_but_missing_from_mode_config_refuses(tmp_path, monkeypatch, capsys):
    """--mode's choices come from the SCORER's MODES; if one is added there and not to MODE_CONFIG,
    refuse rather than KeyError. Simulated by removing an entry from MODE_CONFIG."""
    monkeypatch.delitem(m.MODE_CONFIG, "paid_gate0_v2")
    monkeypatch.setattr("sys.argv", _argv(tmp_path, "--mode", "paid_gate0_v2", "--i-am-human",
                                          "--out", str(tmp_path / "o.json")))
    assert m.main() == 2
    assert "unknown --mode" in capsys.readouterr().err
    assert not (tmp_path / "o.json").exists()


# ---- the banked-artifact write guard -------------------------------------------------------------
#
# Deliberately isolated from the one-cold-attempt existence check, so that deleting EITHER guard in
# write_artifact() turns exactly one group red (PR #195's review: an --i-am-human gate could be
# deleted with all 1704 tests still green, because a different guard satisfied the same assertions):
#   * test_banked_dir_is_the_real_banked_baseline_directory -- pure constant, no I/O.
#   * the path-guard tests below -- BANKED_DIR is monkeypatched to an EMPTY tmp dir, so the
#     existence check cannot fire and cannot stand in for the path guard; and if the path guard is
#     removed the stray write lands in tmp_path, never in the real append-only runs/ tree.
#   * test_write_artifact_refuses_existing_file (above) -- a non-banked path, so the path guard
#     cannot fire and cannot stand in for the existence check.

def test_banked_dir_is_the_real_banked_baseline_directory():
    assert m.BANKED_DIR == m.ROOT / "runs" / "gate0_human_baseline" / "red"
    assert m.BANKED_DIR == m.MODE_CONFIG["readiness_dev"]["real_out"]


@pytest.mark.parametrize("name", ["human_metrics.json", "oracle.jsonl", "nested/anything.json"])
def test_write_artifact_refuses_inside_banked_dir(tmp_path, monkeypatch, name):
    """Refuses ANY target at or under BANKED_DIR -- not just human_metrics.json -- and creates
    nothing on the way to refusing."""
    banked = tmp_path / "banked"
    monkeypatch.setattr(m, "BANKED_DIR", banked)
    with pytest.raises(SystemExit, match="inside the banked Red baseline directory"):
        m.write_artifact({"arm": "red"}, banked / name)
    assert not banked.exists()


def test_write_artifact_refuses_banked_dir_itself_as_target(tmp_path, monkeypatch):
    banked = tmp_path / "banked"
    monkeypatch.setattr(m, "BANKED_DIR", banked)
    with pytest.raises(SystemExit, match="inside the banked Red baseline directory"):
        m.write_artifact({"arm": "red"}, banked)


def test_write_artifact_refuses_banked_dir_reached_via_dotdot(tmp_path, monkeypatch):
    """The EFFECTIVE write target is what gets bound, not the string typed: a path that merely
    RESOLVES into BANKED_DIR is refused too."""
    banked = tmp_path / "banked"
    banked.mkdir()
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.setattr(m, "BANKED_DIR", banked)
    sneaky = tmp_path / "elsewhere" / ".." / "banked" / "human_metrics.json"
    with pytest.raises(SystemExit, match="inside the banked Red baseline directory"):
        m.write_artifact({"arm": "red"}, sneaky)


def test_write_artifact_allows_a_sibling_directory_with_the_same_prefix(tmp_path, monkeypatch):
    """Containment is on path COMPONENTS: `.../banked_v2/` is not inside `.../banked/`."""
    monkeypatch.setattr(m, "BANKED_DIR", tmp_path / "banked")
    out = tmp_path / "banked_v2" / "human_metrics.json"
    m.write_artifact({"arm": "red"}, out)
    assert json.loads(out.read_text(encoding="utf-8")) == {"arm": "red"}


@pytest.mark.parametrize("i_am_human", [False, True])
@pytest.mark.parametrize("mode", sorted(scorer.MODES))
def test_no_mode_flag_combination_can_write_into_banked_dir(tmp_path, monkeypatch, mode, i_am_human):
    """The unconditional invariant, checked across EVERY mode x flag combination rather than only
    the interesting one: with --out aimed straight at the banked directory, every cell refuses and
    the directory is never created."""
    banked = tmp_path / "banked"
    monkeypatch.setattr(m, "BANKED_DIR", banked)
    extra = ["--mode", mode, "--out", str(banked / "human_metrics.json")]
    if i_am_human:
        extra.append("--i-am-human")
    monkeypatch.setattr("sys.argv", _argv(tmp_path, *extra))

    # Branches on the LITERAL, not on m.HELD_OUT_MODES: branching on the constant would make this
    # test adapt to a mutated gate and assert the mutant's own behaviour instead of the requirement.
    if mode in PAID_MODES and not i_am_human:
        assert m.main() == 2                       # stopped even earlier, at the held-out gate
    else:
        with pytest.raises(SystemExit, match="inside the banked Red baseline directory"):
            m.main()
    assert not banked.exists()


# ---- the banked guard vs Windows path spellings that name the same file ---------------------------
#
# PR #196's review demonstrated FOUR spellings that evaded the guard and PROVABLY landed the file in
# the protected directory: `Path.resolve()` preserves a caller-supplied `\\?\` prefix, and treats an
# admin share as a distinct root, so both sides of the comparison disagreed while the OS opened the
# same file. Closed by tools/reconstruct_gate0_red_baseline.py::_strip_extended_prefix (the `\\?\`
# family) plus the UNC-vs-drive-letter fail-closed rule in _resolves_inside_banked (the admin-share
# family, which is not decidable by normalisation -- see that docstring).

# The four spellings the review demonstrated reaching the banked directory, plus the device path it
# found already refused (kept so a regression in either direction shows up).
ALIAS_SPELLINGS = ["extended_length", "extended_unc", "admin_share_host", "admin_share_ip",
                   "device_path"]
# Not an alias -- see test_extended_length_dotdot_is_not_writable_at_all. Refused anyway, and listed
# separately so nobody reads it as a demonstrated write vector.
ALL_SPELLINGS = ALIAS_SPELLINGS + ["extended_length_dotdot"]


def _spellings(directory: Path, name: str) -> dict[str, str]:
    r"""Exotic Windows spellings of `<directory>\<name>`. All but the last name the same file."""
    drive, rest = str(directory)[0], str(directory)[3:]
    return {
        "extended_length":        f"\\\\?\\{drive}:\\{rest}\\{name}",
        "extended_unc":           f"\\\\?\\UNC\\localhost\\{drive}$\\{rest}\\{name}",
        "admin_share_host":       f"\\\\localhost\\{drive}$\\{rest}\\{name}",
        "admin_share_ip":         f"\\\\127.0.0.1\\{drive}$\\{rest}\\{name}",
        "device_path":            f"\\\\.\\{drive}:\\{rest}\\{name}",
        "extended_length_dotdot": f"\\\\?\\{drive}:\\{rest}\\..\\{directory.name}\\{name}",
    }


@pytest.mark.skipif(os.name != "nt", reason="Windows-only path spellings")
def test_the_exotic_spellings_really_are_aliases_not_nonsense_paths(tmp_path):
    """Positive control for the refusal test below, which would otherwise pass vacuously if these
    spellings simply did not address anything. Written to an ORDINARY directory (never the banked
    one): each spelling must produce a file readable at the plain path."""
    plain = tmp_path / "not_banked"
    plain.mkdir()
    for label in ALIAS_SPELLINGS:
        Path(_spellings(plain, "probe.json")[label]).write_text(label, encoding="utf-8")
        assert (plain / "probe.json").read_text(encoding="utf-8") == label, label
        (plain / "probe.json").unlink()


@pytest.mark.skipif(os.name != "nt", reason="Windows-only path spellings")
def test_extended_length_dotdot_is_not_writable_at_all(tmp_path):
    r"""`\\?\` switches OFF Windows path normalisation, so a `..` inside one is a literal component,
    not a parent reference -- and the open fails outright. Pinned because it bounds the claim: the
    module strips the prefix BEFORE resolving (so the guard sees the collapsed path and refuses), but
    the reverse order would NOT have been a write vector either. It is a defensiveness difference, not
    a closed hole; the four entries in ALIAS_SPELLINGS are the closed holes."""
    plain = tmp_path / "not_banked"
    plain.mkdir()
    with pytest.raises(OSError):
        Path(_spellings(plain, "probe.json")["extended_length_dotdot"]).write_text("x",
                                                                                  encoding="utf-8")


@pytest.mark.skipif(os.name != "nt", reason="Windows-only path spellings")
@pytest.mark.parametrize("spelling", ALL_SPELLINGS)
def test_write_artifact_refuses_exotic_windows_spellings_of_the_banked_dir(tmp_path, monkeypatch,
                                                                          spelling):
    banked = tmp_path / "banked"
    banked.mkdir()
    monkeypatch.setattr(m, "BANKED_DIR", banked)
    out = Path(_spellings(banked, "human_metrics.json")[spelling])
    with pytest.raises(SystemExit, match="inside the banked Red baseline directory"):
        m.write_artifact({"arm": "red"}, out)
    assert list(banked.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="Windows-only path spellings")
def test_an_extended_length_path_outside_the_banked_dir_is_still_allowed(tmp_path, monkeypatch):
    r"""The `\\?\` handling must not collapse into a blanket refusal of every long path.

    `Path(r"\\?\C:\x").drive` is `\\?\C:`, which starts with `\\`, so the UNC fail-closed rule in
    `_resolves_inside_banked` refuses every extended-length path ON ITS OWN -- it fully subsumes
    `_strip_extended_prefix` for the REFUSAL cases above, which is why deleting that helper leaves the
    rest of the suite green (mutation M15). What the helper actually buys is this: an extended-length
    path aimed somewhere legitimate stays usable. `\\?\` is how Windows addresses anything past
    MAX_PATH, which the deeply nested worktrees this repo runs in get close to, so over-refusing it is
    a real cost. This is the only test that distinguishes the two."""
    banked = tmp_path / "banked"
    monkeypatch.setattr(m, "BANKED_DIR", banked)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    m.write_artifact({"arm": "red"},
                     Path(_spellings(elsewhere, "human_metrics.json")["extended_length"]))
    written = (elsewhere / "human_metrics.json").read_text(encoding="utf-8")
    assert json.loads(written) == {"arm": "red"}
    assert not banked.exists()


# ---- the banked guard vs a junctioned parent ------------------------------------------------------

def _make_junction(link: Path, target: Path) -> None:
    """NTFS junction on Windows (`mklink /J` -- needs no elevation, unlike `/D`), symlink elsewhere."""
    if os.name == "nt":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            pytest.skip(f"mklink /J unavailable: {(r.stdout + r.stderr).strip()}")
    else:
        os.symlink(target, link, target_is_directory=True)


def test_write_artifact_refuses_through_a_junctioned_parent(tmp_path, monkeypatch):
    r"""BANKED_DIR named THROUGH a junction that leaves the tree -- and the same file named through
    the junction's target. Both must refuse.

    Not hypothetical: `runs/` on this machine already holds 26 NTFS junctions pointing at
    `D:\ai_pokemon_runs\` (bulk run data moved to another volume for space), so Gate-0 directories are
    obvious future candidates for the same treatment. The line that makes this work is
    `banked = _strip_extended_prefix(BANKED_DIR).resolve()` -- the `.resolve()` on the REFERENT side.
    Drop it and the whole suite stays green (1703 passed, 18 skipped) while the guard silently fails
    open here, because every OTHER guard test monkeypatches BANKED_DIR to an already-resolved
    `tmp_path`, where that `.resolve()` is a no-op. This test is that mutant's only counterexample."""
    out_of_tree = tmp_path / "other_volume_stand_in"
    (out_of_tree / "red").mkdir(parents=True)
    runs = tmp_path / "runs_stand_in"
    _make_junction(runs, out_of_tree)

    banked = runs / "red"                                  # NAMED through the junction
    monkeypatch.setattr(m, "BANKED_DIR", banked)
    assert banked.resolve() == (out_of_tree / "red").resolve()   # the junction really is followed

    with pytest.raises(SystemExit, match="inside the banked Red baseline directory"):
        m.write_artifact({"arm": "red"}, banked / "human_metrics.json")
    with pytest.raises(SystemExit, match="inside the banked Red baseline directory"):
        m.write_artifact({"arm": "red"}, out_of_tree / "red" / "oracle.jsonl")
    assert list((out_of_tree / "red").iterdir()) == []

    # Containment is still by component, not by prefix, on the far side of the junction.
    sibling = out_of_tree / "red_v2" / "human_metrics.json"
    m.write_artifact({"arm": "red"}, sibling)
    assert json.loads(sibling.read_text(encoding="utf-8")) == {"arm": "red"}


def test_default_out_for_readiness_dev_is_refused_by_the_banked_guard(tmp_path, monkeypatch):
    """The mode-derived DEFAULT for readiness_dev IS the banked directory, so a no---out run
    refuses: the banked artifact is not reachable as a default. (Before this change, the same
    invocation wrote runs/gate0_human_baseline/red/human_metrics.json and exited 0 -- verified on
    origin/main 322499f.) BANKED_DIR and MODE_CONFIG are redirected together, exactly as they are
    wired in the real module."""
    banked = tmp_path / "banked"
    monkeypatch.setitem(m.MODE_CONFIG, "readiness_dev", {"real_out": banked})
    monkeypatch.setattr(m, "BANKED_DIR", banked)
    monkeypatch.setattr("sys.argv", _argv(tmp_path, "--mode", "readiness_dev"))
    with pytest.raises(SystemExit, match="inside the banked Red baseline directory"):
        m.main()
    assert not banked.exists()
