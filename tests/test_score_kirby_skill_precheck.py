"""Unit tests for eval/score_kirby_skill_precheck.py -- the free pre-check gates pinned by
reports/2026-07-03-kirby-skill-port-entity-v3.md §6. CI-safe: gates 1/4/5/7 need no ROM/assets and run
for real here; gates 2/3/6 are asset-gated (per the doc's own honest scoping -- no recorded Kirby frame
corpus or seed state is committed to this checkout) and are tested only for their loud, non-fabricating
NEEDS_ASSETS_NOT_PRESENT failure path.
"""
from __future__ import annotations

import os

from eval.score_kirby_skill_precheck import (
    PER_PRESS_BUDGET_MS,
    _admission_verdict,
    _overhead_report,
    check_entities_admission,
    check_seam_isolation,
    check_seam_physics,
    check_tools_fresh,
    measure_overhead,
    run_dry,
)


# ---------------------------------------------------------------------------
# Gate 1: --dry executor fixture
# ---------------------------------------------------------------------------

def test_gate1_dry_runs_all_four_scenarios_against_the_real_executor(tmp_path, monkeypatch):
    monkeypatch.setenv("KIRBY_SKILLS", "1")
    report = run_dry(str(tmp_path / "out"))
    assert report["auditable"] is True
    assert report["all_scenarios_pass"] is True
    names = {sc["name"] for sc in report["scenarios"]}
    assert names == {"approach_region_changed", "retreat_steps_elapsed", "move_blocked",
                     "max_iters_cap_out"}
    assert report["n_define_skill"] == 4
    assert report["n_run_skill"] == 4


def test_gate1_dry_writes_combined_skills_jsonl_with_expected_stop_reasons(tmp_path, monkeypatch):
    monkeypatch.setenv("KIRBY_SKILLS", "1")
    out = str(tmp_path / "out")
    run_dry(out)
    from eval.score_skill_rung1 import load_jsonl
    rows = load_jsonl(f"{out}/skills.jsonl")
    reasons = [r["stop_reason"] for r in rows if r["event"] == "run_skill"]
    assert any("region_changed" in r for r in reasons)
    assert any("steps_elapsed(8)" in r for r in reasons)
    assert any("move_blocked" in r for r in reasons)
    assert any("reached max_iters=4" in r for r in reasons)


def test_gate1_dry_detects_executor_drift(tmp_path, monkeypatch):
    """The scenario expectations are load-bearing: pins that a WRONG expected_iterations/executed_steps
    would make all_scenarios_pass False, not slide through -- checked by directly corrupting one
    scenario's expectation and confirming the driver catches it."""
    monkeypatch.setenv("KIRBY_SKILLS", "1")
    import eval.score_kirby_skill_precheck as mod

    original = mod._kirby_dry_scenarios
    try:
        def _drifted():
            scenarios = original()
            scenarios[1]["expect_executed_steps"] = 999   # retreat_steps_elapsed should be 8, not 999
            return scenarios
        mod._kirby_dry_scenarios = _drifted
        report = run_dry(str(tmp_path / "out"))
        assert report["all_scenarios_pass"] is False
    finally:
        mod._kirby_dry_scenarios = original


# ---------------------------------------------------------------------------
# Gate 2: per-press overhead -- asset-gated, tested only for the loud non-fabricating failure path
# ---------------------------------------------------------------------------

def test_gate2_needs_assets_not_present_without_rom_or_frames_dir():
    report = measure_overhead(rom=None, init_state=None, frames_dir=None)
    assert "error" in report
    assert "NEEDS_ASSETS_NOT_PRESENT" in report["error"]


def test_gate2_frames_dir_below_minimum_fails_loud(tmp_path):
    # A frames dir with fewer than MIN_FRAMES_FOR_OVERHEAD PNGs must not silently produce a number.
    import numpy as np
    from PIL import Image
    d = tmp_path / "frames"
    d.mkdir()
    for i in range(5):
        Image.fromarray(np.zeros((144, 160, 3), dtype=np.uint8)).save(d / f"f{i:03d}.png")
    report = measure_overhead(rom=None, init_state=None, frames_dir=str(d))
    assert "error" in report
    assert "NEEDS_ASSETS_NOT_PRESENT" in report["error"]


def test_gate2_overhead_from_frames_when_enough_pngs(tmp_path):
    """When >= 100 PNGs ARE supplied, the doc's own measurement (observe + track + predicate check,
    §6 gate 2's parenthetical) runs for real -- observe-only and full overhead reported SEPARATELY
    per residual #3, with the budget verdict keyed on the FULL overhead only."""
    import numpy as np
    from PIL import Image
    d = tmp_path / "frames"
    d.mkdir()
    for i in range(100):
        Image.fromarray(np.zeros((144, 160, 3), dtype=np.uint8)).save(d / f"f{i:03d}.png")
    report = measure_overhead(rom=None, init_state=None, frames_dir=str(d))
    assert "error" not in report
    assert report["mode"] == "overhead_from_frames"
    assert report["n"] >= 100
    assert report["observe_only_mean_ms"] >= 0.0
    assert report["full_overhead_mean_ms"] >= report["observe_only_mean_ms"]   # overhead adds track+predicate
    # residual #3: the two costs are separate keys; the gate verdict rides ONLY on the full overhead,
    # and the observe-only lower bound gets its own non-verdict key (PR #93 SEV-3 finding 5).
    assert "observe_only_under_budget" in report
    assert report["passed"] == (report["full_overhead_mean_ms"] <= PER_PRESS_BUDGET_MS)


def test_gate2_budget_verdict_pure_function_fail_path():
    """PR #93 SEV-2 finding 7: the 150 ms budget must be enforceable in a test, not just documented --
    a mean full overhead 1 ms over budget FAILS; exactly at budget passes (inclusive <=, matching the
    doc's inclusive-comparison convention); observe-only under budget alone never flips the verdict."""
    over = _overhead_report([10.0] * 5, [PER_PRESS_BUDGET_MS + 1.0] * 5, mode="overhead_from_frames")
    assert over["passed"] is False
    assert over["observe_only_under_budget"] is True   # lower bound fine, verdict still FAIL
    at = _overhead_report([10.0] * 5, [PER_PRESS_BUDGET_MS] * 5, mode="overhead_from_frames")
    assert at["passed"] is True
    under = _overhead_report([10.0] * 5, [PER_PRESS_BUDGET_MS - 1.0] * 5, mode="overhead_from_frames")
    assert under["passed"] is True


def test_pinned_gate_constants_literal_values():
    """PR #93 SEV-2 finding 7: the bar constants are PINNED (doc §5.5/§6), not just documented --
    a silent edit to any of them must fail this test."""
    import eval.score_kirby_skill_precheck as mod
    assert mod.PER_PRESS_BUDGET_MS == 150.0
    assert mod.MIN_FRAMES_FOR_OVERHEAD == 100
    assert mod.EXPECTED_WALK_FRAMES_PER_PRESS == 46
    assert mod.EXPECTED_JUMP_FRAMES_PER_PRESS == 36
    assert mod.STATIONARY_MAD_MAX == 2.0


# ---------------------------------------------------------------------------
# Gate 3: entity_count_changed admission -- asset-gated, tested only for the loud failure path
# ---------------------------------------------------------------------------

def test_gate3_needs_assets_not_present_without_frames_dir():
    report = check_entities_admission(None)
    assert "error" in report
    assert "NEEDS_ASSETS_NOT_PRESENT" in report["error"]


def test_gate3_runs_real_detector_against_a_synthetic_frame_dir(tmp_path):
    """Not a real recorded enemy-approach sequence (none exists in this checkout -- honest scoping),
    but confirms the REAL EntityDetector.detect() path executes end to end and reports
    fired/flapping/stationarity on whatever frames it's given, rather than being a stub."""
    import numpy as np
    from PIL import Image
    d = tmp_path / "frames"
    d.mkdir()
    for i in range(6):
        Image.fromarray(np.zeros((144, 160, 3), dtype=np.uint8)).save(d / f"f{i:03d}.png")
    report = check_entities_admission(str(d))
    assert "error" not in report
    assert report["n_frames"] == 6
    assert report["fired"] is False   # blank frames never trigger the foreground detector
    assert report["n_stationary_pairs"] == 5   # identical frames -> every consecutive pair stationary


def test_gate3_period2_flicker_on_stationary_scene_is_flagged():
    """PR #93 MEDIUM finding (executor review 4 / spec review 2): the exact 1,0,1,0 fully-on/fully-off
    alternation -- the most common real GB sprite-flicker signature -- MUST be flagged when the scene
    is stationary. The old adjacent-nonzero check could never see it (a period-2 run has no two
    adjacent nonzero counts)."""
    counts = [1, 0, 1, 0, 1, 0]
    stationary = [False] + [True] * 5   # static scene: every pair stationary (index 0 has no pair)
    verdict = _admission_verdict(counts, stationary)
    assert verdict["flapping_detected"] is True
    assert verdict["passed"] is False
    assert verdict["admitted"] is False
    assert verdict["flapping_pair_indices"] == [1, 2, 3, 4, 5]


def test_gate3_adjacent_nonzero_flap_on_stationary_scene_still_flagged():
    """The case the OLD check did catch (2,1,2 on a static scene) must still be caught."""
    counts = [2, 1, 2, 2]
    stationary = [False, True, True, True]
    verdict = _admission_verdict(counts, stationary)
    assert verdict["flapping_detected"] is True


def test_gate3_genuine_approach_sequence_is_not_flagged():
    """Doc §6 gate 3's scoping ('count stable across consecutive frames of a STATIONARY scene'): a
    genuine enemy approach changes counts WITH scene motion -- those pairs are non-stationary, so the
    legitimate 0 -> 1 -> 2 rise must NOT be read as flapping, and the gate PASSES (detector fired,
    no stationary-pair flap). This is the spec reviewer's misfire case: the old whole-sequence check
    would have failed exactly this evidence."""
    counts = [0, 0, 1, 1, 2, 2]
    #          approach motion on the pairs where counts change; still frames where counts hold
    stationary = [False, True, False, True, False, True]
    verdict = _admission_verdict(counts, stationary)
    assert verdict["flapping_detected"] is False
    assert verdict["fired"] is True
    assert verdict["passed"] is True
    assert verdict["admitted"] is True


def test_gate3_count_change_on_stationary_pair_even_from_zero_is_flapping():
    """A 0 -> 1 jump with NO scene motion is detector noise by definition (nothing moved, yet the
    count changed) -- must be flagged even though one side of the pair is zero."""
    counts = [0, 1, 1, 1]
    stationary = [False, True, True, True]
    verdict = _admission_verdict(counts, stationary)
    assert verdict["flapping_detected"] is True


# ---------------------------------------------------------------------------
# Gate 4: tools/list seam-isolation (pure logic, no ROM) -- runs for real.
# ---------------------------------------------------------------------------

def test_gate4_seam_isolation_passes(monkeypatch):
    monkeypatch.delenv("KIRBY_SKILLS", raising=False)
    report = check_seam_isolation()
    assert report["off_hides_tools"] is True
    assert report["on_shows_tools"] is True
    assert report["other_worlds_clean"] is True
    assert report["leaked_to"] == []
    assert report["passed"] is True


def test_gate4_restores_prior_env_value(monkeypatch):
    monkeypatch.setenv("KIRBY_SKILLS", "1")
    check_seam_isolation()
    assert os.environ.get("KIRBY_SKILLS") == "1"   # unchanged after the gate runs


# ---------------------------------------------------------------------------
# Gate 5: assert_action_tools_fresh -- SKIPPED (not FAIL) without a ROM.
# ---------------------------------------------------------------------------

def test_gate5_skips_cleanly_without_a_rom():
    report = check_tools_fresh(rom="definitely-not-a-real-rom.gb")
    assert report["skipped"] is True


# ---------------------------------------------------------------------------
# Gate 6: seam-press physics -- asset-gated, tested only for the loud failure path.
# ---------------------------------------------------------------------------

def test_gate6_needs_assets_not_present_without_rom_and_init_state():
    report = check_seam_physics(None, None)
    assert "error" in report
    assert "NEEDS_ASSETS_NOT_PRESENT" in report["error"]


def test_gate6_needs_both_rom_and_init_state_not_just_one():
    report = check_seam_physics("some.gb", None)
    assert "error" in report
    assert "NEEDS_ASSETS_NOT_PRESENT" in report["error"]


# ---------------------------------------------------------------------------
# --all aggregation (PR #93 SEV-1): all seven gates, never green with partial coverage.
# ---------------------------------------------------------------------------

def test_all_without_assets_exits_nonzero_with_per_gate_needs_assets_lines(tmp_path, capsys, monkeypatch):
    """The SEV-1 failure mode: `--all` used to run only gates 1/4/5/7 and exit 0 -- indistinguishable
    from a full 7/7 pass. Now gates 2/3/6 are always REQUESTED under --all; without assets they report
    NEEDS_ASSETS and the aggregate exit code is nonzero. Gate 5's ROM-less skip also counts as not
    passed under --all (never green with partial coverage)."""
    monkeypatch.setenv("KIRBY_SKILLS", "1")
    import eval.score_kirby_skill_precheck as mod
    # Force gate 5 down the no-ROM path even if a ROM exists in this checkout, so the test pins the
    # no-assets behavior deterministically in any environment.
    monkeypatch.setattr(mod, "check_tools_fresh",
                        lambda rom: {"skipped": True, "reason": "forced for test"})
    rc = mod.main(["--all", "--out", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert rc == 1
    assert out.count("NEEDS_ASSETS") >= 3          # per-gate lines for 2, 3, and 6
    assert "gate 2 (per-press overhead): NEEDS_ASSETS" in out
    assert "gate 3 (entity admission): NEEDS_ASSETS" in out
    assert "gate 6 (seam physics): NEEDS_ASSETS" in out
    assert "ALL REQUESTED GATES PASS: NO" in out


def test_all_with_assets_covers_all_seven_gates_and_exits_zero(tmp_path, capsys, monkeypatch):
    """With assets supplied (mocked here -- the real invocations need the main tree's ROM/frames),
    --all must actually RUN gates 2/3/6 and aggregate all seven into the exit code."""
    monkeypatch.setenv("KIRBY_SKILLS", "1")
    import eval.score_kirby_skill_precheck as mod
    called = set()

    def fake_overhead(**kw):
        called.add(2)
        return {"mode": "overhead_from_frames", "n": 100, "observe_only_mean_ms": 10.0,
                "full_overhead_mean_ms": 20.0, "budget_ms": 150.0,
                "observe_only_under_budget": True, "passed": True}

    def fake_entities(frames_dir):
        called.add(3)
        return {"fired": True, "flapping_detected": False, "flapping_pair_indices": [],
                "passed": True, "admitted": True, "n_frames": 100, "counts": [], "n_stationary_pairs": 5}

    def fake_seam_physics(rom, init_state):
        called.add(6)
        return {"cadence_46_ok": True, "cadence_36_ok": True, "macro_cadence_ok": True,
                "fires_on_third_blocked_press": True, "passed": True}

    def fake_fresh(rom):
        called.add(5)
        return {"skipped": False, "passed": True}

    monkeypatch.setattr(mod, "measure_overhead", fake_overhead)
    monkeypatch.setattr(mod, "check_entities_admission", fake_entities)
    monkeypatch.setattr(mod, "check_seam_physics", fake_seam_physics)
    monkeypatch.setattr(mod, "check_tools_fresh", fake_fresh)
    rc = mod.main(["--all", "--rom", "fake.gb", "--init-state", "fake.state",
                   "--frames-dir", "fake_frames", "--out", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert rc == 0
    assert called == {2, 3, 5, 6}                  # 1/4/7 ran for real; 2/3/5/6 via the mocks
    for n in (1, 2, 3, 4, 5, 6, 7):
        assert f"gate {n} " in out                  # every gate has a summary line -- 7/7 coverage
    assert "ALL REQUESTED GATES PASS: YES" in out


def test_all_with_one_failing_gate_exits_nonzero(tmp_path, monkeypatch):
    """A single failing gate (here gate 6's cadence) must sink the --all aggregate."""
    monkeypatch.setenv("KIRBY_SKILLS", "1")
    import eval.score_kirby_skill_precheck as mod
    monkeypatch.setattr(mod, "measure_overhead", lambda **kw: {"passed": True, "mode": "x", "n": 1})
    monkeypatch.setattr(mod, "check_entities_admission", lambda fd: {"passed": True, "fired": True,
                                                                     "flapping_detected": False,
                                                                     "counts": []})
    monkeypatch.setattr(mod, "check_seam_physics",
                        lambda rom, st: {"passed": False, "cadence_46_ok": False})
    monkeypatch.setattr(mod, "check_tools_fresh", lambda rom: {"skipped": False, "passed": True})
    rc = mod.main(["--all", "--rom", "fake.gb", "--init-state", "fake.state",
                   "--frames-dir", "fake_frames", "--out", str(tmp_path / "out")])
    assert rc == 1


def test_all_gate3_not_admitted_is_a_decision_not_a_blocker(tmp_path, capsys, monkeypatch):
    """Doc §6 gate 3: 'FAIL costs nothing: the macro's approach half already uses region_changed' --
    a NOT_ADMITTED decision (detector ran, flapping found, entity_count_changed stays demoted) must
    NOT sink the --all aggregate; only NEEDS_ASSETS (no decision made) fails the gate."""
    monkeypatch.setenv("KIRBY_SKILLS", "1")
    import eval.score_kirby_skill_precheck as mod
    monkeypatch.setattr(mod, "measure_overhead", lambda **kw: {"passed": True, "mode": "x", "n": 1})
    monkeypatch.setattr(mod, "check_entities_admission",
                        lambda fd: {"fired": True, "flapping_detected": True,
                                    "flapping_pair_indices": [3], "passed": False, "admitted": False,
                                    "n_frames": 181, "counts": [], "n_stationary_pairs": 69})
    monkeypatch.setattr(mod, "check_seam_physics", lambda rom, st: {"passed": True})
    monkeypatch.setattr(mod, "check_tools_fresh", lambda rom: {"skipped": False, "passed": True})
    rc = mod.main(["--all", "--rom", "fake.gb", "--init-state", "fake.state",
                   "--frames-dir", "fake_frames", "--out", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "NOT_ADMITTED" in out
    assert "ALL REQUESTED GATES PASS: YES" in out


def test_standalone_dry_still_tolerates_gate5_skip(tmp_path, monkeypatch):
    """Standalone --dry keeps the unit-test convention: gate 5 SKIPPED (no ROM) does not fail the
    run -- only --all requires all seven for real."""
    monkeypatch.setenv("KIRBY_SKILLS", "1")
    import eval.score_kirby_skill_precheck as mod
    monkeypatch.setattr(mod, "check_tools_fresh",
                        lambda rom: {"skipped": True, "reason": "forced for test"})
    rc = mod.main(["--dry", "--out", str(tmp_path / "out")])
    assert rc == 0


def test_standalone_measure_overhead_without_assets_exits_nonzero(tmp_path):
    import eval.score_kirby_skill_precheck as mod
    rc = mod.main(["--measure-overhead", "--out", str(tmp_path / "out")])
    assert rc == 1
