"""Unit tests for eval/score_a3_precheck.py -- GATE-3D-A3-PC's pinned onset-rule scorer
(reports/2026-07-05-p1-clutter-redesign.md S3.1). Synthetic grounding-shaped row lists pin every
run_pos boundary exactly (run_pos<=1 excluded / run_pos>=2 included, a run broken by ATTACK / a
direction change / an episode boundary, and the >=20-scored-steps minimum applied AFTER exclusion).

Also includes a real-data regression pin against the shipped run3 grounding.jsonl copy (if present --
gitignored under runs/, so this test SKIPS rather than fails when the data isn't checked out locally),
matching the design doc's own S1.5/S3.1 numbers: raw 0.7741 (956 scored), onset-excluded 0.8559
(708 scored)."""
from __future__ import annotations

import json
import os

import pytest

from eval.score_a3_precheck import ARM_B_MIN_TURN_STEPS, arm_b_a3, run_positions

RUN3_GROUNDING = os.path.join(os.path.dirname(__file__), "..", "runs", "brain_gate3d",
                              "run3_v_FAIL", "world", "grounding.jsonl")


def _row(ep, step, commanded, direction, dx=1):
    return {"episode": ep, "seed": 1000 + ep, "step": step, "tic": step * 4, "commanded": commanded,
            "direction": direction, "dx_px": dx, "confidence": 0.5}


# ── run_positions boundaries ─────────────────────────────────────────────────

def test_run_pos_increments_within_a_held_same_direction_run():
    rows = [_row(0, 0, "left", "left"), _row(0, 1, "left", "left"), _row(0, 2, "left", "left")]
    assert run_positions(rows) == [0, 1, 2]


def test_run_pos_resets_on_a_non_turn_row():
    rows = [_row(0, 0, "left", "left"), _row(0, 1, None, "none"), _row(0, 2, "left", "left")]
    assert run_positions(rows) == [0, -1, 0]


def test_run_pos_resets_on_a_direction_change():
    rows = [_row(0, 0, "left", "left"), _row(0, 1, "left", "left"), _row(0, 2, "right", "right")]
    assert run_positions(rows) == [0, 1, 0]


def test_run_pos_resets_on_an_episode_boundary():
    rows = [_row(0, 5, "left", "left"), _row(0, 6, "left", "left"), _row(1, 0, "left", "left")]
    assert run_positions(rows) == [0, 1, 0]


def test_run_pos_is_sentinel_minus_one_for_non_turn_rows():
    rows = [_row(0, 0, None, "none"), _row(0, 1, None, None)]
    assert run_positions(rows) == [-1, -1]


# ── arm_b_a3: exclusion boundary (run_pos<=1 excluded, run_pos>=2 included) ──

def test_onset_exclusion_drops_run_pos_0_and_1_but_keeps_run_pos_2():
    rows = [
        _row(0, 0, "left", "right"),   # run_pos 0 -- a DISAGREEMENT, but excluded regardless
        _row(0, 1, "left", "right"),   # run_pos 1 -- a DISAGREEMENT, but excluded regardless
        *[_row(0, i, "left", "left") for i in range(2, 22)],   # run_pos 2..21, all agree
    ]
    excl = arm_b_a3(rows, exclude_onset=True)
    assert excl["n_scored_turn_steps"] == 20         # only run_pos>=2 rows counted
    assert excl["sign_agreement"] == 1.0             # both disagreements were excluded
    assert excl["none_rate"] == 0.0

    raw = arm_b_a3(rows, exclude_onset=False)
    assert raw["n_scored_turn_steps"] == 22
    assert raw["sign_agreement"] == pytest.approx(20 / 22)


def test_onset_exclusion_also_drops_run_pos_0_1_from_none_rate_denominator():
    # run_pos 0/1 rows below are UNSCORED (direction=None) -- without the exclusion they inflate the
    # None-rate; with it, they must not appear in the None-rate computation AT ALL (S3.1: "excluded ...
    # AND from the None-rate computation"), not merely excluded from the numerator.
    rows = [
        _row(0, 0, "left", None),   # run_pos 0, unscored
        _row(0, 1, "left", None),   # run_pos 1, unscored
        *[_row(0, i, "left", "left") for i in range(2, 22)],   # run_pos 2..21, all scored + agree
    ]
    excl = arm_b_a3(rows, exclude_onset=True)
    assert excl["n_turn_steps"] == 20
    assert excl["none_rate"] == 0.0

    raw = arm_b_a3(rows, exclude_onset=False)
    assert raw["n_turn_steps"] == 22
    assert raw["none_rate"] == pytest.approx(2 / 22)


# ── the >=20-scored minimum applies AFTER exclusion (no vacuous pass) ────────

def test_min_scored_steps_applies_after_onset_exclusion():
    # 21 total turn rows, but only 19 survive the run_pos>=2 exclusion -- must NOT pass even though the
    # sign-agreement and none-rate on the surviving rows are perfect.
    rows = [
        _row(0, 0, "left", "left"),   # run_pos 0, excluded
        _row(0, 1, "left", "left"),   # run_pos 1, excluded
        *[_row(0, i, "left", "left") for i in range(2, 21)],   # run_pos 2..20 -> 19 rows
    ]
    excl = arm_b_a3(rows, exclude_onset=True)
    assert excl["n_scored_turn_steps"] == 19
    assert excl["n_scored_turn_steps"] < ARM_B_MIN_TURN_STEPS
    assert excl["enough_steps"] is False
    assert excl["passed"] is False


def test_passes_at_exactly_the_bars_with_enough_post_exclusion_steps():
    rows = [_row(0, 0, "left", "left"), _row(0, 1, "left", "left")]   # excluded onset rows
    rows += [_row(0, i, "left", "left") for i in range(2, 22)]        # 20 agreeing, scored rows
    excl = arm_b_a3(rows, exclude_onset=True)
    assert excl["n_scored_turn_steps"] == 20
    assert excl["sign_agreement"] == 1.0
    assert excl["none_rate"] == 0.0
    assert excl["passed"] is True


# ── real-data regression pin (skips if runs/ isn't checked out locally -- gitignored) ────────────────

@pytest.mark.skipif(not os.path.exists(RUN3_GROUNDING), reason="runs/ is gitignored; run3 data not present")
def test_run3_grounding_reproduces_the_design_docs_pinned_numbers():
    with open(RUN3_GROUNDING, encoding="utf-8") as f:
        grounding = [json.loads(line) for line in f if line.strip()]

    raw = arm_b_a3(grounding, exclude_onset=False)
    assert raw["n_scored_turn_steps"] == 956
    assert raw["sign_agreement"] == pytest.approx(0.7741, abs=1e-4)
    assert raw["none_rate"] == pytest.approx(0.3554, abs=1e-4)

    excl = arm_b_a3(grounding, exclude_onset=True)
    assert excl["n_scored_turn_steps"] == 708
    assert excl["sign_agreement"] == pytest.approx(0.8559, abs=1e-4)
