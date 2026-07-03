"""Unit tests for eval/score_entity_gate_v3.py -- the repaired-bar / macro-interior-exclusion /
skill-mechanism-guard entity gate (v3). Pre-registered per
reports/2026-07-03-kirby-skill-port-entity-v3.md §5. Mirrors tests/test_score_entity_gate_v2.py's
style for the machinery carried over unchanged, and adds fixtures for the three v3 changes."""
from __future__ import annotations

import json
import tempfile

from eval.score_entity_gate_v3 import (
    B_K_CEILING,
    MACRO_INTERIOR_MAX_FRACTION,
    MARGIN,
    MIN_NEAR,
    MIN_SESSION_DROPS,
    MIN_TOTAL_STEPS,
    QUALIFYING_MIN_EXECUTED_STEPS,
    QUALIFYING_MIN_ITERATIONS,
    Q_K_FLOOR,
    WINDOW,
    _bcd,
    _coverage,
    _drop_steps,
    _grounded,
    is_qualifying_conditional_call,
    macro_spans,
    parse_transcript,
    score,
    skill_guard,
)

SERVER = "mcp__kirby-gate"


def _remember_pair(call_id: str, lesson: str) -> list[dict]:
    return [
        {"message": {"content": [{"type": "tool_use", "id": call_id, "name": f"{SERVER}__remember",
                                  "input": {"lesson": lesson}}]}},
        {"message": {"content": [{"type": "tool_result", "tool_use_id": call_id, "content": "ok"}]}},
    ]


def _reveal_pair(call_id: str, step: int, tool: str = "whats_changed") -> list[dict]:
    return [
        {"message": {"content": [{"type": "tool_use", "id": call_id, "name": f"{SERVER}__{tool}",
                                  "input": {"x0": 0, "y0": 0, "x1": 8, "y1": 8}}]}},
        {"message": {"content": [{"type": "tool_result", "tool_use_id": call_id,
                                  "content": [{"type": "text",
                                               "text": f"[{tool} step={step} (0,0)-(8,8): unchanged]"}]}]}},
    ]


def _raw(hp: int) -> int:
    return ((hp // 10) << 4) | (hp % 10)


def _oracle_rec(step: int, hp_raw: int) -> dict:
    return {"step": step, "t": 1_000_000.0 + step, "watch": {"hp": hp_raw}}


def _write_jsonl(path, records) -> str:
    p = str(path)
    with open(p, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return p


def _run_score(transcript, oracle, skills=None):
    with tempfile.TemporaryDirectory() as d:
        tp = _write_jsonl(f"{d}/transcript.jsonl", transcript)
        op = _write_jsonl(f"{d}/oracle.jsonl", oracle)
        sp = _write_jsonl(f"{d}/skills.jsonl", skills or [])
        return score(tp, op, sp)


def _near_calls(eid: int, steps, prefix: str) -> list[dict]:
    calls = []
    for i, s in enumerate(steps):
        calls += _remember_pair(f"{prefix}{i}", f"NEAR id={eid} step={s}")
    return calls


def _declares() -> list[dict]:
    return (_remember_pair("d1", "DECLARE threat=1")
            + _remember_pair("d2", "REJECT id=2 reason=never near me before a drop"))


def _run_skill_rec(step, world_steps_used, executed_step_count, executed, name="approach_suspect"):
    return {"event": "run_skill", "step": step, "name": name, "executed": executed,
            "executed_step_count": executed_step_count, "stop_reason": executed[-1]["repeat_until_summary"]
            if executed and "repeat_until_summary" in executed[-1] else "all top-level steps executed",
            "world_steps_used": world_steps_used}


def _qualifying_conditional_skill(step=20, world_steps_used=8, iterations=2,
                                   predicate="region_changed(0,0,8,8)"):
    """A run_skill record that satisfies the §5.4 guard: executed_step_count >= 3, stop_when fired
    (not max_iters exhaustion, not steps_elapsed alone), iterations >= 2."""
    executed = [{"button": "right", "hold_frames": 30, "ok": True} for _ in range(world_steps_used)]
    executed.append({"repeat_until_summary": f"stop_when '{predicate}' fired after "
                     f"{world_steps_used} press(es) ({iterations} iteration(s))",
                     "iterations": iterations, "world_steps": world_steps_used})
    return _run_skill_rec(step, world_steps_used, world_steps_used, executed)


# ---------------------------------------------------------------------------
# Shared session fixture -- same shape as v2's tests, 5 drops over 98 steps.
# ---------------------------------------------------------------------------

DROPS_5 = (19, 38, 57, 76, 97)


def _oracle_98(drop_at=DROPS_5):
    oracle = []
    hp = 5   # kirby's plain 0-5 range
    for step in range(1, 99):
        if step in drop_at and hp > 0:
            hp -= 1
        oracle.append(_oracle_rec(step, _raw(hp)))
    return oracle


BENIGN_EARLY = (1, 2, 3)


def _skills_with_qualifying_call():
    return [_qualifying_conditional_skill(step=200, world_steps_used=8)]


# ---------------------------------------------------------------------------
# 1. Carried-over machinery smoke tests (BCD identity, window coverage, drop steps).
# ---------------------------------------------------------------------------

def test_bcd_decode_identity_for_plain_ints():
    """Kirby's hp byte is a plain int 0-5 -- _bcd() must be identity for it (doc §5.1)."""
    assert _bcd(0) == 0
    assert _bcd(5) == 5


def test_window_boundary_near_at_s_minus_window_covers():
    entries = [{"step": 100 - WINDOW, "matched": True}]
    assert _coverage(entries, {100}) == 1


def test_window_boundary_near_at_s_minus_window_minus_one_does_not_cover():
    entries = [{"step": 100 - WINDOW - 1, "matched": True}]
    assert _coverage(entries, {100}) == 0


def test_drop_steps_basic():
    hp_by_step = {1: 5, 2: 5, 3: 4, 4: 4, 5: 3}
    drops, n_with_prior = _drop_steps(hp_by_step)
    assert drops == {3, 5}
    assert n_with_prior == 4


# ---------------------------------------------------------------------------
# 2. The repaired bar (§5.2): floor / margin / ceiling, all four verdict paths.
# ---------------------------------------------------------------------------

def test_bar_pinned_constants():
    assert Q_K_FLOOR == 0.80
    assert MARGIN == 0.15
    assert B_K_CEILING == 0.70
    assert MIN_NEAR == 3


# Drops spaced far enough apart (> WINDOW=15) that each threat NEAR's window ([n, n+15] covering a
# drop step n) does not accidentally spill into a neighboring drop's own window -- same spacing
# discipline v2's tests use (drops 19,38,57,76,97, gap 19).
FAR_DROPS = (20, 40, 60, 80, 100)
FAR_NON_DROP = set(range(1, 121)) - set(FAR_DROPS)   # 115 non-drop steps, 1..120


def test_grounded_worked_probe_from_doc():
    """Doc §5.2 worked probe shape: q_k=0.80, b_k just under the ceiling, margin >= 0.15 ->
    GROUNDED-eligible. NEAR right before 4/5 drops (q_k=0.80); those same NEARs' windows also cover
    some non-drop steps, kept under the ceiling by NOT spamming NEAR elsewhere."""
    drops = set(FAR_DROPS)
    non_drop = FAR_NON_DROP
    # NEAR at step n covers non-drop steps [n, n+15] minus the drop itself, i.e. 15 non-drop steps
    # per NEAR (n..n+15 is 16 steps, one of which -- n+... -- is the drop only if n==drop; here NEAR
    # is logged AT the drop step itself, so its window [n-15, n] covers 15 non-drop steps below it).
    nears = {1: [{"step": s, "matched": True} for s in (20, 40, 60, 80)]}   # covers 4/5 drops -> q=0.80
    result = _grounded(1, nears, drops, non_drop)
    assert abs(result["q_k"] - 0.80) < 1e-9
    assert result["b_k"] <= B_K_CEILING
    assert result["floor_met"] is True
    assert result["margin_met"] is True
    assert result["ceiling_exceeded"] is False
    assert result["grounded"] is True


def test_ceiling_exceeded_triggers_insufficient_before_other_conditions():
    """b_k > 0.70 -> INSUFFICIENT_DATA for that entity BEFORE floor/margin evaluated, even though
    q_k alone would otherwise satisfy floor+margin. Achieved by spamming NEAR near-continuously
    (drives b_k up) while still covering every drop (q_k=1.0)."""
    drops = set(FAR_DROPS)
    non_drop = FAR_NON_DROP
    nears = {1: [{"step": s, "matched": True} for s in range(1, 121)]}   # NEAR at every step
    result = _grounded(1, nears, drops, non_drop)
    assert result["q_k"] == 1.0
    assert result["b_k"] > B_K_CEILING
    assert result["ceiling_exceeded"] is True
    assert result["insufficient"] is True
    assert result["grounded"] is False


def _isolated_near_windows(n: int, spacing: int, start: int = 16) -> list[int]:
    """n NEAR steps spaced `spacing` (== WINDOW+1) apart starting at `start`, so each NEAR's
    [step-15, step] coverage window is disjoint from the others and lands entirely within a
    contiguous non-drop universe starting at step 1 -- lets a test compute exact covered-step
    counts as n * window_width without overlap arithmetic. `start` defaults to WINDOW+1 (16) so
    the first NEAR's window [1, 16] starts at the universe's first step."""
    return [start + i * spacing for i in range(n)]


def test_ceiling_exactly_at_0_70_is_scoreable():
    """Inclusive <=: b_k == 0.70 exactly must NOT trigger the ceiling (doc §5.2 inclusivity pin).
    Non-drop universe sized as an exact multiple of the per-NEAR window width (WINDOW+1=16) so a
    whole number of isolated NEARs covers exactly 70%."""
    window_width = WINDOW + 1   # 16 steps covered per isolated NEAR ([n-15, n])
    non_drop = set(range(1, 10 * window_width + 1))   # 160 non-drop steps
    drops = {10_000}   # far away, no interaction with the non-drop universe
    near_steps = _isolated_near_windows(7, spacing=window_width)   # 7 isolated NEARs -> 112/160 = 0.70
    nears = {1: [{"step": s, "matched": True} for s in near_steps] + [{"step": 10_000, "matched": True}]}
    result = _grounded(1, nears, drops, non_drop)
    assert result["q_k"] == 1.0
    assert abs(result["b_k"] - 0.70) < 1e-9, f"test fixture must hit b_k==0.70 exactly, got {result['b_k']}"
    assert result["ceiling_exceeded"] is False
    assert result["grounded"] is True


def test_margin_fail_below_0_15_does_not_ground():
    """q_k clears the floor (0.80) but q_k - b_k < 0.15 -> not grounded (margin fails, ceiling+floor
    pass). 5 drops spaced 100 apart; NEAR at 4 of them covers q_k=0.80. Dense padding NEARs in the
    safe zones of 3 of the 4 100-blocks (avoiding every drop's own [-15,0] window) push b_k to
    0.6525 -- under the 0.70 ceiling, but close enough to q_k that the margin (0.15) fails
    (0.80 - 0.6525 = 0.1475 < 0.15)."""
    drops = (100, 200, 300, 400, 500)
    non_drop = set(range(1, 501)) - set(drops)
    threat_near_steps = [100, 200, 300, 400]   # covers 4/5 drops -> q_k = 0.80
    padding_near_steps = [base + off for base in (0, 100, 200) for off in range(5, 90, 10)]
    nears = {1: [{"step": s, "matched": True} for s in threat_near_steps + padding_near_steps]}
    result = _grounded(1, nears, set(drops), non_drop)
    assert abs(result["q_k"] - 0.80) < 1e-9
    assert abs(result["b_k"] - 0.6525) < 1e-4
    assert result["floor_met"] is True
    assert result["ceiling_exceeded"] is False
    assert (result["q_k"] - result["b_k"]) < MARGIN
    assert result["margin_met"] is False
    assert result["grounded"] is False


def test_floor_fail_below_0_80_does_not_ground_even_with_huge_margin():
    """q_k < 0.80 -> not grounded even if q_k - b_k comfortably clears the margin (the NEW absolute
    floor v2 lacked -- doc: 'a threat with q_k=0.31, b_k=0.00 would have passed v2's bar, which this
    doc's floor now blocks'). Drops spaced thousands of steps apart so a single NEAR's coverage of
    one drop's window leaves b_k negligible."""
    drops = (20, 1020, 2020, 3020, 4020)
    non_drop = set(range(1, 4021)) - set(drops)
    nears = {1: [{"step": 20, "matched": True}]}   # covers only 1/5 drops -> q_k=0.2; b_k negligible
    result = _grounded(1, nears, set(drops), non_drop)
    assert abs(result["q_k"] - 0.2) < 1e-9
    assert result["q_k"] < Q_K_FLOOR
    assert result["floor_met"] is False
    assert result["ceiling_exceeded"] is False
    assert (result["q_k"] - result["b_k"]) >= MARGIN   # margin clears easily despite the floor failing
    assert result["margin_met"] is True
    assert result["grounded"] is False


def test_bar_satisfiable_property_holds_for_every_b_k_up_to_ceiling():
    """Doc §5.2: 'the new bar is satisfiable for every b_k in [0, 0.70]'. Direct check (the module
    also asserts this at import time)."""
    b = 0.0
    while b <= B_K_CEILING + 1e-9:
        required_q = max(Q_K_FLOOR, b + MARGIN)
        assert required_q <= 1.0
        b += 0.01


def test_score_grounded_and_benign_correctly_rejected_end_to_end():
    """End-to-end PASS: threat NEARs land right before each drop (q_k high, b_k low); benign NEARs
    are early and never near any drop window (q_k=0, correctly rejected). Includes a qualifying
    skill call so the guard also passes."""
    calls = _near_calls(1, (18, 37, 56, 75, 96), "c1_")
    calls += _near_calls(2, BENIGN_EARLY, "c2_")
    calls += _declares()
    result = _run_score(calls, _oracle_98(), _skills_with_qualifying_call())
    assert result["verdict"] == "PASS"
    t = result["threat_scores"][1]
    assert t["q_k"] == 1.0
    assert t["grounded"] is True
    b = result["benign_scores"][2]
    assert b["q_k"] == 0.0


# ---------------------------------------------------------------------------
# 3. Macro-interior exclusion (§5.6): both directions.
# ---------------------------------------------------------------------------

def test_macro_spans_computed_from_step_and_world_steps_used():
    skills = [{"event": "run_skill", "step": 50, "world_steps_used": 8}]
    assert macro_spans(skills) == [(42, 50)]


def test_interior_step_claim_is_excluded():
    """A NEAR naming a step STRICTLY inside (start, end) is macro-interior -- excluded."""
    skills = [{"event": "run_skill", "step": 50, "world_steps_used": 8}]  # span (42, 50)
    transcript = _remember_pair("c1", "NEAR id=1 step=45")   # 42 < 45 < 50: interior
    parsed = parse_transcript(transcript, [_oracle_rec(45, _raw(5))], skills)
    assert parsed["macro_interior"] == 1
    assert 1 not in parsed["nears"]


def test_boundary_steps_are_kept_not_excluded():
    """The exact start step (42) and end step (50) are claimable -- doc §5.6 rule 1/3."""
    skills = [{"event": "run_skill", "step": 50, "world_steps_used": 8}]  # span (42, 50)
    transcript = (_remember_pair("c_start", "NEAR id=1 step=42")
                  + _remember_pair("c_end", "NEAR id=1 step=50"))
    oracle = [_oracle_rec(42, _raw(5)), _oracle_rec(50, _raw(4))]
    parsed = parse_transcript(transcript, oracle, skills)
    assert parsed["macro_interior"] == 0
    assert len(parsed["nears"][1]) == 2
    logged_steps = {e["step"] for e in parsed["nears"][1]}
    assert logged_steps == {42, 50}


def test_macro_interior_fraction_at_or_above_cap_is_insufficient_data():
    """MACRO_INTERIOR_MAX_FRACTION = 0.20 of all NEAR lines -> INSUFFICIENT_DATA. The denominator is
    ALL NEAR lines that reach the check (accepted + macro-interior), same shape as
    RETROACTIVE_MAX_FRACTION -- so this test's ratio must be computed over every NEAR in the
    transcript (both entities), not just the threat's own lines. This check must fire even though a
    qualifying-conditional skill call is ALSO present (isolating which guard actually fired)."""
    run_skill_span = {"event": "run_skill", "step": 50, "world_steps_used": 40}  # span (10, 50)
    # accepted NEARs: 4 (id1, outside span) + 3 (id2, benign, outside span) = 7; + 1 interior -> 1/8 =
    # 12.5%, BELOW the 20% cap -- too few. Use only 3 accepted total (no benign padding NEARs beyond
    # MIN_NEAR) so 1 interior / 4 total = 25% >= 20%.
    calls = _near_calls(1, (60, 65, 70), "c1_")            # 3 accepted (exactly MIN_NEAR)
    calls += _remember_pair("interior", "NEAR id=1 step=30")  # inside (10,50): interior
    calls += _declares()
    oracle = _oracle_98()
    skills = [run_skill_span] + _skills_with_qualifying_call()
    result = _run_score(calls, oracle, skills)
    assert result["macro_interior_lines"] == 1
    assert result["skill_guard"]["guard_pass"] is True   # guard passes -- isolates the macro check
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert "MACRO-INTERIOR" in result["reason"]


def test_macro_interior_fraction_below_cap_verdict_still_computed():
    """A single macro-interior exclusion among many accepted NEARs (well under 20%) is excluded +
    reported, but the verdict from the rest still computes normally."""
    skills = [{"event": "run_skill", "step": 200, "world_steps_used": 8}]  # span (192, 200), far from data
    calls = _near_calls(1, (18, 37, 56, 75, 96), "c1_")
    calls += _near_calls(2, BENIGN_EARLY, "c2_")
    calls += _remember_pair("interior", "NEAR id=1 step=195")   # inside (192,200): interior, isolated
    calls += _declares()
    result = _run_score(calls, _oracle_98(), skills + _skills_with_qualifying_call())
    assert result["macro_interior_lines"] == 1
    assert result["verdict"] == "PASS"


# ---------------------------------------------------------------------------
# 4. Skill-mechanism guard (§5.4).
# ---------------------------------------------------------------------------

def test_qualifying_conditional_call_true_for_predicate_fired_with_two_iterations():
    rec = _qualifying_conditional_skill(iterations=2)
    assert is_qualifying_conditional_call(rec) is True


def test_not_qualifying_when_max_iters_exhausted():
    executed = [{"button": "right", "hold_frames": 30, "ok": True} for _ in range(5)]
    executed.append({"repeat_until_summary": "repeat_until reached max_iters=8 without stop_when firing",
                     "iterations": 8, "world_steps": 5})
    rec = _run_skill_rec(20, 5, 5, executed)
    assert is_qualifying_conditional_call(rec) is False


def test_not_qualifying_when_stop_reason_is_bare_steps_elapsed():
    """steps_elapsed alone does not satisfy the guard -- conditional in name only (doc §5.4)."""
    executed = [{"button": "left", "hold_frames": 30, "ok": True} for _ in range(8)]
    executed.append({"repeat_until_summary": "stop_when 'steps_elapsed(8)' fired after 8 press(es) "
                     "(1 iteration(s))", "iterations": 1, "world_steps": 8})
    rec = _run_skill_rec(30, 8, 8, executed)
    assert is_qualifying_conditional_call(rec) is False


def test_not_qualifying_when_iterations_is_one_single_iteration_laundering_hole():
    """The single-iteration laundering hole (doc §5.4 review finding): a real predicate fires but
    iterations == 1 -- must NOT qualify."""
    rec = _qualifying_conditional_skill(iterations=1)
    assert is_qualifying_conditional_call(rec) is False


def test_not_qualifying_when_executed_step_count_below_three():
    executed = [{"button": "right", "hold_frames": 30, "ok": True} for _ in range(2)]
    executed.append({"repeat_until_summary": "stop_when 'move_blocked' fired after 2 press(es) "
                     "(2 iteration(s))", "iterations": 2, "world_steps": 2})
    rec = _run_skill_rec(10, 2, 2, executed)
    assert is_qualifying_conditional_call(rec) is False


def test_not_qualifying_with_no_repeat_until_block_at_all():
    """A flat press-only skill (no repeat_until) has no loop to have branched -- cannot qualify."""
    executed = [{"button": "right", "hold_frames": 30, "ok": True} for _ in range(4)]
    rec = _run_skill_rec(10, 4, 4, executed)
    assert is_qualifying_conditional_call(rec) is False


def test_skill_guard_zero_qualifying_conditional_calls():
    skills = [_run_skill_rec(10, 4, 4, [{"button": "right", "hold_frames": 30, "ok": True}] * 4)]
    guard = skill_guard(skills)
    assert guard["n_qualifying_conditional_calls"] == 0
    assert guard["guard_pass"] is False


def test_skill_guard_one_qualifying_conditional_call_passes():
    guard = skill_guard(_skills_with_qualifying_call())
    assert guard["n_qualifying_conditional_calls"] == 1
    assert guard["guard_pass"] is True


def test_guard_failure_forces_insufficient_data_even_with_clean_grounding():
    """The guard failing sinks the run to INSUFFICIENT_DATA even though grounding would otherwise
    PASS cleanly (doc §5.4 + §7: 'can independently sink the run... even if the grounding numbers
    would otherwise PASS or FAIL cleanly')."""
    calls = _near_calls(1, (18, 37, 56, 75, 96), "c1_")
    calls += _near_calls(2, BENIGN_EARLY, "c2_")
    calls += _declares()
    # no skills.jsonl rows at all -- 0 qualifying-conditional calls.
    result = _run_score(calls, _oracle_98(), skills=[])
    assert result["skill_guard"]["guard_pass"] is False
    assert result["verdict"] == "INSUFFICIENT_DATA"
    # grounding numbers still reported for audit:
    assert result["threat_scores"][1]["grounded"] is True
    assert "skill-mechanism guard" in result["reason"]


def test_guard_pass_with_clean_grounding_yields_pass():
    calls = _near_calls(1, (18, 37, 56, 75, 96), "c1_")
    calls += _near_calls(2, BENIGN_EARLY, "c2_")
    calls += _declares()
    result = _run_score(calls, _oracle_98(), _skills_with_qualifying_call())
    assert result["skill_guard"]["guard_pass"] is True
    assert result["verdict"] == "PASS"


# ---------------------------------------------------------------------------
# 5. Verdict guards inherited unchanged (NO_DECLARE / INSUFFICIENT_DROPS / malformed / conflicting).
# ---------------------------------------------------------------------------

def test_score_no_declare_without_threat():
    calls = _remember_pair("c", "NEAR id=1 step=1") + _remember_pair("b", "DECLARE benign=2")
    result = _run_score(calls, [_oracle_rec(1, _raw(5))])
    assert result["verdict"] == "NO_DECLARE"


def test_insufficient_drops_below_five():
    four = (19, 38, 57, 76)
    calls = _near_calls(1, (18, 37, 56, 75), "c1_")
    calls += _near_calls(2, BENIGN_EARLY, "c2_")
    calls += _declares()
    result = _run_score(calls, _oracle_98(drop_at=four))
    assert result["session_drop_steps"] == 4
    assert result["verdict"] == "INSUFFICIENT_DROPS"


def test_too_few_total_steps_is_insufficient_data():
    oracle = [_oracle_rec(s, _raw(min(5, 10 - (s // 5)))) for s in range(1, MIN_TOTAL_STEPS)]
    calls = _near_calls(1, (4, 9, 14), "c1_") + _near_calls(2, (1, 2, 3), "c2_") + _declares()
    result = _run_score(calls, oracle)
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert "scoreable oracle steps" in result["reason"]


def test_conflicting_declaration_excluded_from_both_arms():
    calls = _near_calls(1, (18, 37, 56, 75, 96), "c1_")
    calls += _near_calls(2, BENIGN_EARLY, "c2_")
    calls += _near_calls(3, (5, 6, 7), "c3_")
    calls += _declares()
    calls += _remember_pair("d3a", "DECLARE threat=3")
    calls += _remember_pair("d3b", "REJECT id=3 reason=changed my mind")
    result = _run_score(calls, _oracle_98(), _skills_with_qualifying_call())
    assert result["conflicting_declarations"] == [3]
    assert 3 not in result["threat_scores"]
    assert result["verdict"] == "PASS"
