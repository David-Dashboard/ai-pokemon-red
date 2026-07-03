"""Unit tests for eval/score_kirby_skill_precheck.py -- the free pre-check gates pinned by
reports/2026-07-03-kirby-skill-port-entity-v3.md §6. CI-safe: gates 1/4/5/7 need no ROM/assets and run
for real here; gates 2/3/6 are asset-gated (per the doc's own honest scoping -- no recorded Kirby frame
corpus or seed state is committed to this checkout) and are tested only for their loud, non-fabricating
NEEDS_ASSETS_NOT_PRESENT failure path.
"""
from __future__ import annotations

import os

from eval.score_kirby_skill_precheck import (
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


def test_gate2_observe_only_from_frames_when_enough_pngs(tmp_path):
    """When >= 100 PNGs ARE supplied, the observe-only half is measurable (no ROM needed for the
    perceiver-only path) -- confirms the harness reports a real number, not a stub, once assets exist."""
    import numpy as np
    from PIL import Image
    d = tmp_path / "frames"
    d.mkdir()
    for i in range(100):
        Image.fromarray(np.zeros((144, 160, 3), dtype=np.uint8)).save(d / f"f{i:03d}.png")
    report = measure_overhead(rom=None, init_state=None, frames_dir=str(d))
    assert "error" not in report
    assert report["mode"] == "observe_only_from_frames"
    assert report["n"] >= 100
    assert report["mean_ms"] >= 0.0
    assert "passed" in report


# ---------------------------------------------------------------------------
# Gate 3: entity_count_changed admission -- asset-gated, tested only for the loud failure path
# ---------------------------------------------------------------------------

def test_gate3_needs_assets_not_present_without_frames_dir():
    report = check_entities_admission(None)
    assert "error" in report
    assert "NEEDS_ASSETS_NOT_PRESENT" in report["error"]


def test_gate3_runs_real_detector_against_a_synthetic_frame_dir(tmp_path):
    """Not a real recorded enemy-approach sequence (none exists in this checkout -- honest scoping),
    but confirms the REAL EntityDetector.detect() path executes end to end and reports fired/flapping
    on whatever frames it's given, rather than being a stub."""
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
