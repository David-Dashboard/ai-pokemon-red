"""Unit tests for eval/score_gate3d.py -- the GATE-3D-A1 scorer as re-pinned by AMENDMENT A2
(reports/2026-07-04-vizdoom-3d-floor-design.md SS A2.2). Synthetic oracle.jsonl + grounding.jsonl
fixtures (no real vizdoom/MCP run needed) pin every verdict (PASS/FAIL/DEGENERATE/INSUFFICIENT_DATA)
and every guard boundary exactly at its pinned constant, house style (mirrors
tests/test_score_entity_gate_v2.py / tests/test_score_gate_run.py). A2.4's required boundary set is
covered explicitly: K at bar-epsilon vs bar, KPS just below vs at 1.5x, total shots at 9 vs 10, and
the ammo2-increase exclusion."""
from __future__ import annotations

import json
import tempfile

from eval.score_gate3d import (
    ARM_A2_KPS_FACTOR,
    ARM_A2_MIN_SHOTS,
    ARM_B_MIN_TURN_STEPS,
    ARM_B_NONE_RATE_MAX,
    ARM_B_SIGN_AGREEMENT_MIN,
    COMPLETION_FLOOR,
    MIN_DISTINCT_KILLCOUNTS,
    N_EPISODES,
    _arm_b,
    _brain_kps,
    _final_killcount_by_episode,
    d_from_baselines,
    gate_bar,
    kps_spinner_from_baselines,
    score,
)

SEEDS = list(range(1000, 1030))   # 30 pinned seeds, matching eval/fixtures/gate3d_seeds.json's shape

# Test baselines fixture (SS A2.3 file shape): four measured policies + underscore-prefixed metadata.
# D = 4.0 (spinner_multihot, the max mean) -> (a-1) bar = max(4.0+1.5, 1.15*4.0) = 5.5.
# KPS_spinner = the STRONGEST-K spinner variant's kps = spinner_multihot's 0.16 (NOT alternating's
# higher 0.20 -- A2.2 pins the strongest-K variant, not the best-KPS one) -> (a-2) bar = 0.24.
BASELINES = {
    "_comment": "test fixture",
    "random": {"mean_killcount": 1.0, "std_killcount": 0.9, "kps": 0.05},
    "attack_only": {"mean_killcount": 1.2, "std_killcount": 0.6, "kps": 0.06},
    "spinner_multihot": {"mean_killcount": 4.0, "std_killcount": 1.6, "kps": 0.16},
    "spinner_alternating": {"mean_killcount": 3.0, "std_killcount": 1.5, "kps": 0.20},
}
BAR = 5.5           # gate_bar(4.0)
KPS_BAR = 0.24      # 1.5 * 0.16

# A second baselines fixture whose bar (D=3.5 -> max(5.0, 4.025) = 5.0) is hittable EXACTLY by an
# integer-killcount mean over 25 episodes (sum 125) -- used for the K-at-the-boundary tests.
BASELINES_B = dict(BASELINES, spinner_multihot={"mean_killcount": 3.5, "std_killcount": 1.6, "kps": 0.16})
BAR_B = 5.0


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


def _oracle_row(ep, step, tic, killcount, *, ammo2=26.0, finished=False, abandoned=False) -> dict:
    return {"episode": ep, "seed": SEEDS[ep], "step": step, "tic": tic, "health": 100.0,
            "ammo2": ammo2, "killcount": killcount, "finished": finished, "abandoned": abandoned}


def _grounding_row(ep, step, tic, commanded, direction) -> dict:
    return {"episode": ep, "seed": SEEDS[ep], "step": step, "tic": tic, "commanded": commanded,
            "direction": direction, "dx_px": (40 if direction == "left" else -40 if direction == "right" else 0),
            "confidence": 0.9 if direction is not None else None}


def _episode_rows(ep: int, n_steps: int, final_kc: int, *, shots: int = 5, tic_per_step: int = 4) -> list[dict]:
    """A minimal completed episode: n_steps oracle rows (killcount 0 until the last, which carries
    final_kc), ammo2 starting at 26.0 and decreasing by 1/step until exactly `shots` rounds are spent
    (so ammo2_first - ammo2_last == shots), final row finished=True. Requires n_steps > shots."""
    assert n_steps > shots, "need enough steps to spend the requested shots"
    rows = []
    for s in range(1, n_steps + 1):
        kc = final_kc if s == n_steps else 0
        ammo2 = 26.0 - min(s - 1, shots)
        rows.append(_oracle_row(ep, s, s * tic_per_step, kc, ammo2=ammo2, finished=(s == n_steps)))
    return rows


def _turn_grounding_rows(ep: int, n: int, *, agree: int, none_n: int = 0) -> list[dict]:
    """`n` commanded turn steps for episode `ep`: `agree` of them get a P1 reading matching the
    commanded direction, `none_n` get direction=None, the rest get the WRONG direction (sign
    disagreement). Alternates commanded left/right across steps for variety."""
    rows = []
    wrong = n - agree - none_n
    assert wrong >= 0
    idx = 0
    for _ in range(agree):
        commanded = "left" if idx % 2 == 0 else "right"
        rows.append(_grounding_row(ep, idx + 1, (idx + 1) * 4, commanded, commanded))
        idx += 1
    for _ in range(none_n):
        commanded = "left" if idx % 2 == 0 else "right"
        rows.append(_grounding_row(ep, idx + 1, (idx + 1) * 4, commanded, None))
        idx += 1
    for _ in range(wrong):
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


def _oracle_for(kcs: list[int], *, n_eps: int = COMPLETION_FLOOR, shots: int = 8) -> list[dict]:
    """n_eps completed episodes with the given final killcounts (cycled), varying episode lengths
    (clears the tic-variation guard) and `shots` rounds spent per episode."""
    oracle = []
    base_steps = max(10, shots + 2)   # long enough to actually spend the requested shots
    for ep in range(n_eps):
        oracle += _episode_rows(ep, n_steps=base_steps + (ep % 2), final_kc=kcs[ep % len(kcs)], shots=shots)
    return oracle


def _good_grounding(n: int = 25) -> list[dict]:
    return _turn_grounding_rows(0, n, agree=n)


# ---------------------------------------------------------------------------
# gate_bar (a-1): max(D+1.5, 1.15*D) -- both sides of the max, exactly at the crossover.
# ---------------------------------------------------------------------------

def test_gate_bar_additive_dominates_at_low_d():
    assert gate_bar(4.0) == 5.5          # D+1.5=5.5 vs 1.15*D=4.6 -> additive wins


def test_gate_bar_multiplicative_dominates_at_high_d():
    assert gate_bar(20.0) == 23.0        # D+1.5=21.5 vs 1.15*D=23.0 -> multiplicative wins


def test_gate_bar_crossover_point_is_exactly_10():
    # D+1.5 == 1.15*D  =>  0.15*D == 1.5  =>  D == 10; both sides equal there.
    assert gate_bar(10.0) == 11.5


# ---------------------------------------------------------------------------
# D and KPS_spinner extraction from the baselines file (SS A2.3: the file is the only source).
# ---------------------------------------------------------------------------

def test_d_is_the_max_mean_over_all_policy_entries():
    d, policy = d_from_baselines(BASELINES)
    assert d == 4.0
    assert policy == "spinner_multihot"


def test_d_set_is_add_only_a_new_stronger_decoy_raises_d():
    stronger = dict(BASELINES, reviewer_decoy={"mean_killcount": 6.0, "kps": 0.1})
    d, policy = d_from_baselines(stronger)
    assert d == 6.0
    assert policy == "reviewer_decoy"


def test_underscore_metadata_keys_are_not_policies():
    with_meta = dict(BASELINES, _amendment_note="text", _gate_bar_at_this_d=5.5)
    d, _ = d_from_baselines(with_meta)
    assert d == 4.0


def test_kps_spinner_is_the_strongest_k_spinner_variant_not_the_best_kps_one():
    # multihot: mean 4.0 / kps 0.16; alternating: mean 3.0 / kps 0.20. A2.2 pins the STRONGEST-K
    # variant's kps -> 0.16, even though alternating's kps is higher.
    kps, policy = kps_spinner_from_baselines(BASELINES)
    assert kps == 0.16
    assert policy == "spinner_multihot"


# ---------------------------------------------------------------------------
# Completion floor: < 25/30 -> INSUFFICIENT_DATA; exactly 25 is the pass-through boundary.
# ---------------------------------------------------------------------------

def test_insufficient_data_below_completion_floor():
    oracle = _oracle_for([1, 2, 3, 4, 5], n_eps=COMPLETION_FLOOR - 1)
    r = _run_score(oracle, _good_grounding())
    assert r["verdict"] == "INSUFFICIENT_DATA"
    assert str(COMPLETION_FLOOR - 1) in r["reason"]


def test_completion_floor_boundary_exactly_25_proceeds_past_the_guard():
    oracle = _oracle_for([1, 2, 3, 4, 5], n_eps=COMPLETION_FLOOR)
    r = _run_score(oracle, _good_grounding())
    assert r["verdict"] != "INSUFFICIENT_DATA"
    assert r["n_completed_episodes"] == COMPLETION_FLOOR


# ---------------------------------------------------------------------------
# One-attempt-per-seed: abandoned episode rows are USED (their last row's killcount), not dropped.
# ---------------------------------------------------------------------------

def test_abandoned_episode_counted_at_abandonment_killcount():
    oracle = _episode_rows(0, n_steps=6, final_kc=2)
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
    oracle = _oracle_for([3])   # every episode ends with killcount 3
    r = _run_score(oracle, _good_grounding())
    assert r["verdict"] == "DEGENERATE"
    assert r["n_distinct_killcounts"] == 1


def test_degenerate_with_only_two_distinct_killcounts_below_min():
    assert MIN_DISTINCT_KILLCOUNTS == 3
    oracle = _oracle_for([1, 2])   # only 2 distinct values, still < 3
    r = _run_score(oracle, _good_grounding())
    assert r["verdict"] == "DEGENERATE"
    assert r["n_distinct_killcounts"] == 2


def test_degenerate_when_episode_lengths_all_identical_even_with_killcount_variation():
    kcs = [1, 2, 3, 1, 2] * 5   # >= 3 distinct killcounts
    oracle = []
    for ep in range(COMPLETION_FLOOR):
        oracle += _episode_rows(ep, n_steps=10, final_kc=kcs[ep])   # SAME n_steps every episode
    r = _run_score(oracle, _good_grounding())
    assert r["verdict"] == "DEGENERATE"
    assert r["n_distinct_episode_lengths"] == 1


def test_variation_guard_passes_with_3_distinct_killcounts_and_2_distinct_lengths():
    oracle = _oracle_for([1, 2, 3, 1, 2])
    r = _run_score(oracle, _good_grounding())
    assert r["verdict"] != "DEGENERATE"


# ---------------------------------------------------------------------------
# ARM (a-1): K vs max(D+1.5, 1.15*D), exactly at the boundary (A2.4's K at bar-epsilon / bar).
# ---------------------------------------------------------------------------

def test_arm_a1_pass_when_k_exactly_at_bar():
    # BASELINES_B: D=3.5 -> bar=5.0. 25 episodes summing 125 -> K = 5.0 exactly; >= passes.
    kcs = [4, 5, 6, 5, 5] * 5   # sum 125 over 25, distinct {4,5,6}
    oracle = _oracle_for(kcs)
    r = _run_score(oracle, _good_grounding(), baselines=BASELINES_B)
    assert abs(r["K"] - BAR_B) < 1e-9
    assert r["arm_a1"] is True


def test_arm_a1_fail_when_k_just_below_bar():
    # Same as above with one killcount lowered by 1: K = 124/25 = 4.96 < 5.0 -> (a-1) FAIL.
    kcs = [4, 5, 6, 5, 5] * 4 + [4, 5, 6, 5, 4]
    oracle = _oracle_for(kcs)
    r = _run_score(oracle, _good_grounding(), baselines=BASELINES_B)
    assert r["K"] < BAR_B
    assert r["arm_a1"] is False
    assert r["verdict"] == "FAIL"


# ---------------------------------------------------------------------------
# ARM (a-2): KPS_brain vs 1.5 * KPS_spinner, exactly at the boundary; the >= 10-shots guard at 9/10;
# the ammo2-increase exclusion.
# ---------------------------------------------------------------------------

def test_arm_a2_pass_at_exactly_1_5x_kps_spinner():
    # KPS bar = 1.5 * 0.16 = 0.24. 25 episodes, 10 shots each (250 total), killcounts summing 60
    # -> KPS_brain = 60/250 = 0.24 exactly; >= passes.
    kcs = [4, 2, 3, 2, 1] * 5   # sum 60, distinct {1,2,3,4}
    oracle = _oracle_for(kcs, shots=10)
    r = _run_score(oracle, _good_grounding())
    assert abs(r["arm_a2_detail"]["kps_brain"] - KPS_BAR) < 1e-9
    assert r["arm_a2"] == "PASS"


def test_arm_a2_fail_just_below_1_5x_kps_spinner():
    # Killcounts summing 59 over the same 250 shots -> KPS_brain = 0.236 < 0.24 -> (a-2) FAIL.
    kcs = [4, 2, 3, 2, 1] * 4 + [4, 2, 3, 2, 0]   # sum 59
    oracle = _oracle_for(kcs, shots=10)
    r = _run_score(oracle, _good_grounding())
    assert r["arm_a2_detail"]["kps_brain"] < KPS_BAR
    assert r["arm_a2"] == "FAIL"
    assert r["verdict"] == "FAIL"


def test_arm_a2_insufficient_data_at_9_total_shots():
    assert ARM_A2_MIN_SHOTS == 10
    # Episode 0 fires 9 shots; every other episode fires none -> 9 total, one below the guard.
    oracle = _episode_rows(0, n_steps=12, final_kc=1, shots=9)
    for ep in range(1, COMPLETION_FLOOR):
        oracle += _episode_rows(ep, n_steps=10 + (ep % 2), final_kc=[2, 3, 1][ep % 3], shots=0)
    r = _run_score(oracle, _good_grounding())
    assert r["arm_a2_detail"]["total_shots"] == 9
    assert r["arm_a2"] == "INSUFFICIENT_DATA"
    assert r["arm_a"] is False          # "not a pass" (SS A2.2)
    assert r["verdict"] == "FAIL"


def test_arm_a2_computed_at_exactly_10_total_shots():
    oracle = _episode_rows(0, n_steps=12, final_kc=1, shots=10)
    for ep in range(1, COMPLETION_FLOOR):
        oracle += _episode_rows(ep, n_steps=10 + (ep % 2), final_kc=[2, 3, 1][ep % 3], shots=0)
    r = _run_score(oracle, _good_grounding())
    assert r["arm_a2_detail"]["total_shots"] == 10
    assert r["arm_a2"] in ("PASS", "FAIL")   # computed, not INSUFFICIENT_DATA


def test_ammo2_increase_excludes_the_episode_from_both_kps_sums_loudly():
    # Episode 0: clean, 5 shots, 2 kills. Episode 1: ammo2 INCREASES mid-episode (26 -> 24 -> 25) --
    # dtc has no ammo pickups, so the episode is excluded from BOTH sums and reported.
    ep0 = _episode_rows(0, n_steps=8, final_kc=2, shots=5)
    ep1 = [
        _oracle_row(1, 1, 4, 0, ammo2=26.0),
        _oracle_row(1, 2, 8, 0, ammo2=24.0),
        _oracle_row(1, 3, 12, 3, ammo2=25.0, finished=True),   # the increase
    ]
    final_kc = _final_killcount_by_episode(ep0 + ep1, SEEDS)
    detail = _brain_kps(ep0 + ep1, SEEDS, final_kc)
    assert detail["total_shots"] == 5.0        # ep1's shots NOT counted
    assert detail["total_kills"] == 2.0        # ep1's 3 kills NOT counted either
    assert [e["episode"] for e in detail["excluded_episodes"]] == [1]
    assert "INCREASED" in detail["excluded_episodes"][0]["reason"]


# ---------------------------------------------------------------------------
# ARM (b): sign-agreement >= 0.90, none-rate <= 0.50, >= 20 SCORED turn steps (A1.4, carried over).
# ---------------------------------------------------------------------------

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
    grounding = _turn_grounding_rows(0, 20, agree=18, none_n=0)
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
    # 40 turn steps, 20 None (0.50 exactly, <= is the pinned bar), 20 scored & agreeing
    # (>= 20 scored, sign-agreement 1.0).
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
# Full PASS / FAIL end-to-end: PASS requires (a-1) AND (a-2) AND (b).
# ---------------------------------------------------------------------------

def test_full_pass_all_three_clear():
    # K: [5,6,5,7,6]*5 -> mean 5.8 >= bar 5.5. KPS: sum kills 145 / (25*9=225 shots) = 0.644 >= 0.24.
    kcs = [5, 6, 5, 7, 6] * 5
    oracle = _oracle_for(kcs, shots=9)
    r = _run_score(oracle, _good_grounding())
    assert r["arm_a1"] is True
    assert r["arm_a2"] == "PASS"
    assert r["arm_a"] is True
    assert r["arm_b"] is True
    assert r["verdict"] == "PASS"


def test_fail_arm_a1_only():
    # K low ([1,1,2,1,3] mean 1.6 < 5.5) but KPS high (sum 40 kills / 50 shots = 0.8 >= 0.24):
    # (a-1) FAIL alone must sink ARM (a) -- a frugal sharpshooter that can't clear the kill margin
    # cannot pass on efficiency alone (SS A2.2's rationale).
    kcs = [1, 1, 2, 1, 3] * 5   # sum 40
    oracle = _oracle_for(kcs, shots=2)
    r = _run_score(oracle, _good_grounding())
    assert r["arm_a1"] is False
    assert r["arm_a2"] == "PASS"
    assert r["arm_a"] is False
    assert r["verdict"] == "FAIL"


def test_fail_arm_a2_only():
    # K high ([5,6,5,7,6] mean 5.8 >= 5.5) but sprayed: 25 shots/episode -> KPS = 145/625 = 0.232
    # < 0.24: a lucky high-K spinner-like spray fails the efficiency test (SS A2.2's rationale).
    kcs = [5, 6, 5, 7, 6] * 5
    oracle = []
    for ep in range(COMPLETION_FLOOR):
        oracle += _episode_rows(ep, n_steps=27 + (ep % 2), final_kc=kcs[ep], shots=25)
    r = _run_score(oracle, _good_grounding())
    assert r["arm_a1"] is True
    assert r["arm_a2"] == "FAIL"
    assert r["arm_a"] is False
    assert r["verdict"] == "FAIL"


def test_fail_arm_b_only():
    kcs = [5, 6, 5, 7, 6] * 5
    oracle = _oracle_for(kcs, shots=9)
    grounding = _turn_grounding_rows(0, 20, agree=10)   # sign-agreement 0.50, below 0.90
    r = _run_score(oracle, grounding)
    assert r["arm_a"] is True
    assert r["arm_b"] is False
    assert r["verdict"] == "FAIL"


def test_fail_everything():
    kcs = [1, 1, 2, 1, 3] * 5
    oracle = _oracle_for(kcs, shots=9)   # KPS = 40/225 = 0.178 < 0.24
    grounding = _turn_grounding_rows(0, 20, agree=5)
    r = _run_score(oracle, grounding)
    assert r["arm_a1"] is False
    assert r["arm_a2"] == "FAIL"
    assert r["arm_b"] is False
    assert r["verdict"] == "FAIL"
