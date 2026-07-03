"""Unit tests for eval/score_gate3d.py -- the GATE-3D-A1 scorer
(reports/2026-07-04-vizdoom-3d-floor-design.md AMENDMENT A1 SS A1.4). Synthetic oracle.jsonl +
grounding.jsonl fixtures (no real vizdoom/MCP run needed) pin every verdict
(PASS/FAIL/DEGENERATE/INSUFFICIENT_DATA) and every guard boundary exactly at its pinned constant,
house style (mirrors tests/test_score_entity_gate_v2.py / tests/test_score_gate_run.py)."""
from __future__ import annotations

import json
import tempfile

from eval.score_gate3d import (
    ARM_B_MIN_TURN_STEPS,
    ARM_B_NONE_RATE_MAX,
    ARM_B_SIGN_AGREEMENT_MIN,
    COMPLETION_FLOOR,
    MIN_DISTINCT_KILLCOUNTS,
    N_EPISODES,
    _arm_b,
    _final_killcount_by_episode,
    gate_bar,
    score,
)

SEEDS = list(range(1000, 1030))   # 30 pinned seeds, matching eval/fixtures/gate3d_seeds.json's shape
BASELINES = {"random": {"mean_killcount": 1.0, "std_killcount": 0.5, "killcount_distribution": {}}}
# gate_bar(1.0) = max(1.0+2.0, 1.5*1.0) = 3.0


def _write_jsonl(path, records) -> str:
    p = str(path)
    with open(p, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return p


def _write_json(path, obj) -> str:
    p = str(path)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    return p


def _oracle_row(ep, step, tic, killcount, *, finished=False, abandoned=False) -> dict:
    return {"episode": ep, "seed": SEEDS[ep], "step": step, "tic": tic, "health": 100.0,
            "ammo2": 26.0, "killcount": killcount, "finished": finished, "abandoned": abandoned}


def _grounding_row(ep, step, tic, commanded, direction) -> dict:
    return {"episode": ep, "seed": SEEDS[ep], "step": step, "tic": tic, "commanded": commanded,
            "direction": direction, "dx_px": (40 if direction == "left" else -40 if direction == "right" else 0),
            "confidence": 0.9 if direction is not None else None}


def _episode_rows(ep: int, n_steps: int, final_kc: int, *, tic_per_step: int = 4) -> list[dict]:
    """A minimal completed episode: n_steps oracle rows (killcount 0 until the last, which carries
    final_kc), final row finished=True."""
    rows = []
    for s in range(1, n_steps + 1):
        kc = final_kc if s == n_steps else 0
        rows.append(_oracle_row(ep, s, s * tic_per_step, kc, finished=(s == n_steps)))
    return rows


def _turn_grounding_rows(ep: int, n: int, *, agree: int, none_n: int = 0, wrong_dir: bool = False) -> list[dict]:
    """`n` commanded turn steps for episode `ep`: `agree` of them get a P1 reading matching the
    commanded direction, `none_n` get direction=None, the rest get the WRONG direction (sign
    disagreement). Alternates commanded left/right across steps for variety."""
    rows = []
    wrong = n - agree - none_n
    assert wrong >= 0
    idx = 0
    for i in range(agree):
        commanded = "left" if idx % 2 == 0 else "right"
        rows.append(_grounding_row(ep, idx + 1, (idx + 1) * 4, commanded, commanded))
        idx += 1
    for i in range(none_n):
        commanded = "left" if idx % 2 == 0 else "right"
        rows.append(_grounding_row(ep, idx + 1, (idx + 1) * 4, commanded, None))
        idx += 1
    for i in range(wrong):
        commanded = "left" if idx % 2 == 0 else "right"
        opposite = "right" if commanded == "left" else "left"
        rows.append(_grounding_row(ep, idx + 1, (idx + 1) * 4, commanded, opposite))
        idx += 1
    return rows


def _run_score(oracle_rows, grounding_rows, *, seeds=SEEDS, baselines=BASELINES):
    with tempfile.TemporaryDirectory() as d:
        op = _write_jsonl(f"{d}/oracle.jsonl", oracle_rows)
        gp = _write_jsonl(f"{d}/grounding.jsonl", grounding_rows)
        sp = _write_json(f"{d}/seeds.json", seeds)
        bp = _write_json(f"{d}/baselines.json", baselines)
        return score(op, gp, sp, bp)


# ---------------------------------------------------------------------------
# gate_bar: max(R+2.0, 1.5*R) -- both sides of the max, exactly at the crossover.
# ---------------------------------------------------------------------------

def test_gate_bar_additive_dominates_at_low_r():
    assert gate_bar(1.0) == 3.0          # R+2.0=3.0 vs 1.5*R=1.5 -> additive wins


def test_gate_bar_multiplicative_dominates_at_high_r():
    assert gate_bar(10.0) == 15.0        # R+2.0=12.0 vs 1.5*R=15.0 -> multiplicative wins


def test_gate_bar_crossover_point_is_exactly_4():
    # R+2.0 == 1.5*R  =>  R == 4.0; both sides equal there.
    assert gate_bar(4.0) == 6.0


# ---------------------------------------------------------------------------
# Completion floor: < 25/30 -> INSUFFICIENT_DATA; exactly 25 is the pass-through boundary.
# ---------------------------------------------------------------------------

def _full_run(n_completed: int, killcounts: list[int], *, n_turn_agree=25) -> tuple[list[dict], list[dict]]:
    """Build n_completed episodes (0..n_completed-1) with the given final killcounts (cycled/truncated
    to length), each with enough grounding turn rows to pass ARM (b) comfortably, for tests that only
    care about ARM (a) / the guards."""
    oracle = []
    grounding = []
    for ep in range(n_completed):
        kc = killcounts[ep % len(killcounts)]
        oracle += _episode_rows(ep, n_steps=10 + (ep % 3), final_kc=kc)
    # Spread the required agreeing turn steps across the first couple episodes.
    remaining = n_turn_agree
    ep = 0
    while remaining > 0 and ep < max(n_completed, 1):
        take = min(remaining, 15)
        grounding += _turn_grounding_rows(ep, take, agree=take)
        remaining -= take
        ep += 1
    return oracle, grounding


def test_insufficient_data_below_completion_floor():
    oracle, grounding = _full_run(COMPLETION_FLOOR - 1, [1, 2, 3, 4, 5])
    r = _run_score(oracle, grounding)
    assert r["verdict"] == "INSUFFICIENT_DATA"
    assert str(COMPLETION_FLOOR - 1) in r["reason"]


def test_completion_floor_boundary_exactly_25_proceeds_past_the_guard():
    oracle, grounding = _full_run(COMPLETION_FLOOR, [1, 2, 3, 4, 5])
    r = _run_score(oracle, grounding)
    assert r["verdict"] != "INSUFFICIENT_DATA"
    assert r["n_completed_episodes"] == COMPLETION_FLOOR


# ---------------------------------------------------------------------------
# One-attempt-per-seed: abandoned episode rows are USED (their last row's killcount), not dropped.
# ---------------------------------------------------------------------------

def test_abandoned_episode_counted_at_abandonment_killcount():
    oracle = _episode_rows(0, n_steps=5, final_kc=2)
    # episode 0 is abandoned mid-flight (new_episode fired early): last row has abandoned=True and a
    # killcount frozen at whatever it was the instant abandonment was logged.
    oracle[-1]["finished"] = True
    oracle[-1]["abandoned"] = True
    final = _final_killcount_by_episode(oracle, SEEDS)
    assert final[0] == 2.0


def test_final_killcount_falls_back_past_a_null_terminal_row():
    """KNOWN ADAPTER LIMITATION (core.vizdoom_world.VizdoomWorld.game_variables(), documented in
    tools/gate3d_baselines.py + this scorer): it returns None once is_episode_finished() is True,
    INCLUDING on the very step that caused it -- so a natural (non-abandoned) episode end can log a
    terminal oracle row with killcount=None even though the row immediately before it has a real
    value. The scorer must fall back to the latest NON-NULL killcount, not treat the episode as
    unscoreable just because its literal last row is null."""
    rows = [
        _oracle_row(0, 1, 4, 1),
        _oracle_row(0, 2, 8, 2),
        _oracle_row(0, 3, 12, 3),
    ]
    rows[-1]["killcount"] = None   # the terminal row's read failed per the adapter guard
    rows[-1]["finished"] = True
    final = _final_killcount_by_episode(rows, SEEDS)
    assert final[0] == 2.0   # falls back to step 2's real reading, not dropped/zeroed


def test_final_killcount_takes_last_row_by_step_order_not_file_order():
    rows = [
        _oracle_row(0, 3, 12, 5, finished=True),
        _oracle_row(0, 1, 4, 0),
        _oracle_row(0, 2, 8, 1),
    ]
    final = _final_killcount_by_episode(rows, SEEDS)
    assert final[0] == 5.0


# ---------------------------------------------------------------------------
# Variation guard: >= 3 distinct killcounts AND >= 2 distinct episode lengths, else DEGENERATE.
# ---------------------------------------------------------------------------

def test_degenerate_when_killcounts_all_identical():
    oracle, grounding = _full_run(COMPLETION_FLOOR, [3])   # every episode ends with killcount 3
    r = _run_score(oracle, grounding)
    assert r["verdict"] == "DEGENERATE"
    assert r["n_distinct_killcounts"] == 1


def test_degenerate_with_only_two_distinct_killcounts_below_min():
    assert MIN_DISTINCT_KILLCOUNTS == 3
    oracle, grounding = _full_run(COMPLETION_FLOOR, [1, 2])   # only 2 distinct values, still < 3
    r = _run_score(oracle, grounding)
    assert r["verdict"] == "DEGENERATE"
    assert r["n_distinct_killcounts"] == 2


def test_degenerate_when_episode_lengths_all_identical_even_with_killcount_variation():
    oracle = []
    grounding = []
    kcs = [1, 2, 3, 1, 2] * 5   # >= 3 distinct killcounts
    for ep in range(COMPLETION_FLOOR):
        oracle += _episode_rows(ep, n_steps=10, final_kc=kcs[ep])   # SAME n_steps every episode
    grounding += _turn_grounding_rows(0, 25, agree=25)
    r = _run_score(oracle, grounding)
    assert r["verdict"] == "DEGENERATE"
    assert r["n_distinct_episode_lengths"] == 1


def test_variation_guard_passes_with_3_distinct_killcounts_and_2_distinct_lengths():
    oracle = []
    grounding = []
    kcs = [1, 2, 3, 1, 2] * 5
    for ep in range(COMPLETION_FLOOR):
        oracle += _episode_rows(ep, n_steps=10 + (ep % 2), final_kc=kcs[ep])
    grounding += _turn_grounding_rows(0, 25, agree=25)
    r = _run_score(oracle, grounding)
    assert r["verdict"] != "DEGENERATE"


# ---------------------------------------------------------------------------
# ARM (a): K = mean final killcount vs max(R+2.0, 1.5*R).
# ---------------------------------------------------------------------------

def test_arm_a_pass_when_k_meets_bar():
    # R=1.0 -> bar=3.0. Mean killcount exactly 3.0 across enough variation to clear other guards.
    kcs = [3, 3, 2, 4, 3] * 5
    oracle = []
    for ep in range(COMPLETION_FLOOR):
        oracle += _episode_rows(ep, n_steps=10 + (ep % 2), final_kc=kcs[ep])
    grounding = _turn_grounding_rows(0, 25, agree=25)
    r = _run_score(oracle, grounding)
    assert abs(r["K"] - 3.0) < 1e-9
    assert r["arm_a"] is True


def test_arm_a_fail_when_k_below_bar():
    kcs = [1, 1, 2, 1, 3] * 5   # 3 distinct values (clears variation guard), mean 1.6 well under bar=3.0
    oracle = []
    for ep in range(COMPLETION_FLOOR):
        oracle += _episode_rows(ep, n_steps=10 + (ep % 2), final_kc=kcs[ep])
    grounding = _turn_grounding_rows(0, 25, agree=25)
    r = _run_score(oracle, grounding)
    assert r["arm_a"] is False
    assert r["verdict"] == "FAIL"


# ---------------------------------------------------------------------------
# ARM (b): sign-agreement >= 0.90, none-rate <= 0.50, >= 20 SCORED turn steps.
# ---------------------------------------------------------------------------

def _base_oracle():
    kcs = [1, 2, 3, 1, 2] * 5
    oracle = []
    for ep in range(COMPLETION_FLOOR):
        oracle += _episode_rows(ep, n_steps=10 + (ep % 2), final_kc=kcs[ep])
    return oracle


def test_arm_b_fails_below_min_turn_steps_no_vacuous_pass():
    assert ARM_B_MIN_TURN_STEPS == 20
    grounding = _turn_grounding_rows(0, ARM_B_MIN_TURN_STEPS - 1, agree=ARM_B_MIN_TURN_STEPS - 1)
    detail = _arm_b(grounding)
    assert detail["passed"] is False
    assert detail["n_scored_turn_steps"] == ARM_B_MIN_TURN_STEPS - 1


def test_arm_b_passes_at_exactly_min_turn_steps_boundary():
    grounding = _turn_grounding_rows(0, ARM_B_MIN_TURN_STEPS, agree=ARM_B_MIN_TURN_STEPS)
    detail = _arm_b(grounding)
    assert detail["n_scored_turn_steps"] == ARM_B_MIN_TURN_STEPS
    assert detail["sign_agreement"] == 1.0
    assert detail["passed"] is True


def test_arm_b_sign_agreement_boundary_exactly_at_threshold():
    # 18/20 = 0.90 exactly -> should PASS (>=).
    n = 20
    agree = 18
    grounding = _turn_grounding_rows(0, n, agree=agree, none_n=0)
    detail = _arm_b(grounding)
    assert abs(detail["sign_agreement"] - ARM_B_SIGN_AGREEMENT_MIN) < 1e-9
    assert detail["passed"] is True


def test_arm_b_sign_agreement_just_below_threshold_fails():
    # 17/20 = 0.85 < 0.90 -> FAIL.
    grounding = _turn_grounding_rows(0, 20, agree=17)
    detail = _arm_b(grounding)
    assert detail["sign_agreement"] < ARM_B_SIGN_AGREEMENT_MIN
    assert detail["passed"] is False


def test_arm_b_none_rate_boundary_exactly_at_threshold_passes():
    # 20 turn steps total, 10 are None (none_rate = 0.50 exactly, <= is the pinned bar), the other 10
    # all agree (scored sign-agreement 1.0 among the 10 scored steps) -- but n_scored=10 < 20, so this
    # actually fails the min-scored-steps bar. Use a larger pool: 40 turn steps, 20 None (0.50 exactly),
    # 20 scored & agreeing (>= 20 scored, sign-agreement 1.0).
    grounding = _turn_grounding_rows(0, 40, agree=20, none_n=20)
    detail = _arm_b(grounding)
    assert abs(detail["none_rate"] - ARM_B_NONE_RATE_MAX) < 1e-9
    assert detail["n_scored_turn_steps"] == 20
    assert detail["passed"] is True


def test_arm_b_none_rate_just_above_threshold_fails():
    # 40 turn steps, 21 None (0.525 > 0.50), 19 scored & agreeing.
    grounding = _turn_grounding_rows(0, 40, agree=19, none_n=21)
    detail = _arm_b(grounding)
    assert detail["none_rate"] > ARM_B_NONE_RATE_MAX
    assert detail["passed"] is False


def test_arm_b_excludes_attack_steps_commanded_none():
    """ATTACK rows (commanded=None) must not count toward turn-step denominators at all."""
    grounding = _turn_grounding_rows(0, ARM_B_MIN_TURN_STEPS, agree=ARM_B_MIN_TURN_STEPS)
    grounding += [_grounding_row(0, 100 + i, (100 + i) * 4, None, None) for i in range(50)]
    detail = _arm_b(grounding)
    assert detail["n_turn_steps"] == ARM_B_MIN_TURN_STEPS
    assert detail["n_scored_turn_steps"] == ARM_B_MIN_TURN_STEPS


# ---------------------------------------------------------------------------
# Full PASS / FAIL end-to-end.
# ---------------------------------------------------------------------------

def test_full_pass_both_arms_clear():
    kcs = [3, 4, 3, 5, 3] * 5   # mean 3.6 >= bar 3.0
    oracle = []
    for ep in range(COMPLETION_FLOOR):
        oracle += _episode_rows(ep, n_steps=10 + (ep % 2), final_kc=kcs[ep])
    grounding = _turn_grounding_rows(0, 25, agree=25)
    r = _run_score(oracle, grounding)
    assert r["arm_a"] is True
    assert r["arm_b"] is True
    assert r["verdict"] == "PASS"


def test_fail_arm_a_only():
    kcs = [1, 1, 2, 1, 3] * 5   # 3 distinct values, mean 1.6 < bar 3.0
    oracle = []
    for ep in range(COMPLETION_FLOOR):
        oracle += _episode_rows(ep, n_steps=10 + (ep % 2), final_kc=kcs[ep])
    grounding = _turn_grounding_rows(0, 25, agree=25)
    r = _run_score(oracle, grounding)
    assert r["arm_a"] is False
    assert r["arm_b"] is True
    assert r["verdict"] == "FAIL"


def test_fail_arm_b_only():
    kcs = [3, 4, 3, 5, 3] * 5
    oracle = []
    for ep in range(COMPLETION_FLOOR):
        oracle += _episode_rows(ep, n_steps=10 + (ep % 2), final_kc=kcs[ep])
    grounding = _turn_grounding_rows(0, 20, agree=10)   # sign-agreement 0.50, below 0.90
    r = _run_score(oracle, grounding)
    assert r["arm_a"] is True
    assert r["arm_b"] is False
    assert r["verdict"] == "FAIL"


def test_fail_both_arms():
    kcs = [1, 1, 2, 1, 3] * 5   # 3 distinct values, mean 1.6 < bar 3.0
    oracle = []
    for ep in range(COMPLETION_FLOOR):
        oracle += _episode_rows(ep, n_steps=10 + (ep % 2), final_kc=kcs[ep])
    grounding = _turn_grounding_rows(0, 20, agree=5)
    r = _run_score(oracle, grounding)
    assert r["arm_a"] is False
    assert r["arm_b"] is False
    assert r["verdict"] == "FAIL"
