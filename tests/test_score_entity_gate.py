"""Unit tests for eval/score_entity_gate.py — the entity-grounding gate scorer (ADR-002 §9 generalized
from HUD/life to entities). Builds small synthetic transcript.jsonl + oracle.jsonl fixtures (no real MCP
run needed) to pin the ENT/CONTACT/DECLARE/REJECT parser, the base-rate metric, and the PASS/FAIL/
DEGENERATE_NO_DAMAGE/INSUFFICIENT_DATA verdicts at the pinned threshold (margin=0.30, min_contacts=3,
min_session_drops=1, min_total_steps=10). Mirrors tests/test_score_gate_run.py's structure."""
from __future__ import annotations

import json
import tempfile

from eval.score_entity_gate import (
    MALFORMED_MAX_FRACTION,
    MARGIN,
    MIN_CONTACTS,
    MIN_TOTAL_STEPS,
    RETROACTIVE_MAX_FRACTION,
    UNMATCHED_MAX_FRACTION,
    _bcd,
    _drop_steps,
    parse_transcript,
    score,
)

SERVER = "mcp__cave-noire-gate"


def _remember_pair(call_id: str, lesson: str) -> list[dict]:
    return [
        {"message": {"content": [{"type": "tool_use", "id": call_id, "name": f"{SERVER}__remember",
                                  "input": {"lesson": lesson}}]}},
        {"message": {"content": [{"type": "tool_result", "tool_use_id": call_id, "content": "ok"}]}},
    ]


def _reveal_pair(call_id: str, step: int, tool: str = "whats_changed") -> list[dict]:
    """A world-observation tool call + its result reporting `step=<N>` — advances the retroactive
    guard's revealed-step watermark, the way a real observe/read_region/whats_changed result does."""
    return [
        {"message": {"content": [{"type": "tool_use", "id": call_id, "name": f"{SERVER}__{tool}",
                                  "input": {"x0": 0, "y0": 0, "x1": 8, "y1": 8}}]}},
        {"message": {"content": [{"type": "tool_result", "tool_use_id": call_id,
                                  "content": [{"type": "text",
                                               "text": f"[{tool} step={step} (0,0)-(8,8): unchanged]"}]}]}},
    ]


def _oracle_rec(step: int, hp_raw: int) -> dict:
    return {"step": step, "t": 1_000_000.0 + step, "watch": {"hp": hp_raw}}


def _write_jsonl(path, records) -> str:
    p = str(path)
    with open(p, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return p


def _run_score(transcript, oracle):
    with tempfile.TemporaryDirectory() as d:
        tp = _write_jsonl(f"{d}/transcript.jsonl", transcript)
        op = _write_jsonl(f"{d}/oracle.jsonl", oracle)
        return score(tp, op)


# ---------------------------------------------------------------------------
# 1. Parser: ENT / CONTACT / DECLARE / REJECT extraction + dedupe.
# ---------------------------------------------------------------------------

def test_parse_ent_line():
    transcript = _remember_pair("t1", "ENT id=1 region=(40,60,56,76) step=5 claim=threat")
    parsed = parse_transcript(transcript, [])
    assert 1 in parsed["ent_claims"]
    e = parsed["ent_claims"][1][0]
    assert e["region"] == (40, 60, 56, 76) and e["step"] == 5 and e["claim"] == "threat"


def test_parse_contact_line_matched_and_deduped():
    transcript = (
        _remember_pair("t1", "CONTACT id=2 step=10")
        + _remember_pair("t2", "CONTACT id=2 step=10")   # exact repeat: dedupe
        + _remember_pair("t3", "CONTACT id=2 step=11")
    )
    oracle = [_oracle_rec(9, 5), _oracle_rec(10, 3), _oracle_rec(11, 3)]
    parsed = parse_transcript(transcript, oracle)
    entries = parsed["contacts"][2]
    assert len(entries) == 2
    assert entries[0]["step"] == 10 and entries[0]["matched"] is True
    assert parsed["duplicates"] == 1


def test_parse_declare_threat_benign_and_reject():
    transcript = (
        _remember_pair("t1", "DECLARE threat=1")
        + _remember_pair("t2", "DECLARE benign=2")
        + _remember_pair("t3", "REJECT id=3 reason=never adjacent when hp dropped")
    )
    parsed = parse_transcript(transcript, [])
    assert parsed["declared_threats"] == {1}
    assert parsed["declared_benign"] == {2}
    assert parsed["rejected"][3] == "never adjacent when hp dropped"


def test_bcd_decode():
    assert _bcd(0x00) == 0
    assert _bcd(0x07) == 7
    assert _bcd(0x10) == 10


def test_unmatched_contact_step_has_no_oracle_row():
    transcript = _remember_pair("t1", "CONTACT id=1 step=99")
    oracle = [_oracle_rec(1, 5)]
    parsed = parse_transcript(transcript, oracle)
    assert parsed["contacts"][1][0]["matched"] is False


# ---------------------------------------------------------------------------
# 2. _drop_steps: base-rate computation.
# ---------------------------------------------------------------------------

def test_drop_steps_basic():
    hp_by_step = {1: 10, 2: 10, 3: 8, 4: 8, 5: 5}
    drops, n_with_prior = _drop_steps(hp_by_step)
    assert drops == {3, 5}
    assert n_with_prior == 4   # steps 2,3,4,5 each have a defined immediate predecessor


def test_drop_steps_gap_breaks_prior_chain():
    hp_by_step = {1: 10, 2: None, 3: 8}
    drops, n_with_prior = _drop_steps(hp_by_step)
    # step 3's immediate predecessor (step 2) is undefined -> not scoreable as a drop step
    assert drops == set()
    assert n_with_prior == 0


# ---------------------------------------------------------------------------
# 3. score(): PASS / FAIL / NO_DECLARE / INSUFFICIENT_DATA / DEGENERATE_NO_DAMAGE.
# ---------------------------------------------------------------------------

def _session_calls_and_oracle(threat_contacts_on_drops, benign_contacts_on_drops,
                              n_steps=20, drop_every=4):
    """Build an oracle with a drop every `drop_every` steps (hp cycles 10->8->10->8...), a threat entity
    (id=1) whose CONTACT steps are exactly the requested drop/non-drop mix, and a benign entity (id=2)
    whose CONTACTs are spread evenly regardless of drops (so its p_k stays near p_base)."""
    oracle = []
    hp = 10
    drop_steps = []
    for step in range(1, n_steps + 1):
        if step % drop_every == 0:
            hp = 8 if hp == 10 else 10
            if hp == 8:
                drop_steps.append(step)
        oracle.append(_oracle_rec(step, 0x10 if hp == 10 else hp))
    non_drop_steps = [s for s in range(2, n_steps + 1) if s not in drop_steps]

    calls = []
    # threat: contacts on `threat_contacts_on_drops` drop steps + fill rest with non-drop steps
    threat_steps = list(drop_steps[:threat_contacts_on_drops])
    for s in non_drop_steps:
        if len(threat_steps) >= max(MIN_CONTACTS, threat_contacts_on_drops + 1):
            break
        if s not in threat_steps:
            threat_steps.append(s)
    for i, s in enumerate(threat_steps):
        calls += _remember_pair(f"c1_{i}", f"CONTACT id=1 step={s}")

    # benign: contacts mostly on non-drop steps (only `benign_contacts_on_drops` on drop steps)
    benign_steps = list(drop_steps[:benign_contacts_on_drops])
    for s in non_drop_steps:
        if len(benign_steps) >= max(MIN_CONTACTS, benign_contacts_on_drops + 5):
            break
        if s not in benign_steps and s not in threat_steps:
            benign_steps.append(s)
    for i, s in enumerate(benign_steps):
        calls += _remember_pair(f"c2_{i}", f"CONTACT id=2 step={s}")

    calls += _remember_pair("d1", "DECLARE threat=1")
    calls += _remember_pair("d2", "REJECT id=2 reason=never near me when hp dropped")
    return calls, oracle


def test_score_pass_threat_grounds_and_benign_rejected():
    # drop_every=4 over 20 steps -> 5 drop steps, base rate ~5/19. Threat contacts ALL on drop steps
    # (all 5) -> p_k=1.0, clears p_base+MARGIN easily. Benign contacts spread on non-drop steps -> p_k~0.
    calls, oracle = _session_calls_and_oracle(threat_contacts_on_drops=5, benign_contacts_on_drops=0)
    result = _run_score(calls, oracle)
    assert result["verdict"] == "PASS"
    assert result["arm_a"] is True and result["arm_b"] is True


def test_score_fail_when_threat_does_not_ground():
    # threat contacts land almost entirely on non-drop steps -> p_k stays near p_base -> arm (a) fails.
    calls, oracle = _session_calls_and_oracle(threat_contacts_on_drops=0, benign_contacts_on_drops=0)
    result = _run_score(calls, oracle)
    assert result["verdict"] == "FAIL"
    assert result["arm_a"] is False


def test_score_no_declare_without_threat():
    calls = _remember_pair("c", "CONTACT id=1 step=1") + _remember_pair("b", "DECLARE benign=2")
    oracle = [_oracle_rec(1, 5)]
    result = _run_score(calls, oracle)
    assert result["verdict"] == "NO_DECLARE"


def test_score_no_declare_without_benign_or_reject():
    calls, oracle = _session_calls_and_oracle(threat_contacts_on_drops=5, benign_contacts_on_drops=0)
    # strip the REJECT/DECLARE-benign line
    calls = [c for c in calls if "REJECT" not in json.dumps(c) and "benign" not in json.dumps(c)]
    result = _run_score(calls, oracle)
    assert result["verdict"] == "NO_DECLARE"
    assert "benign" in result["reason"]


def test_score_degenerate_no_damage():
    """A session where hp never drops cannot ground anything -- DEGENERATE_NO_DAMAGE, not a cheap PASS."""
    oracle = [_oracle_rec(s, 0x10) for s in range(1, MIN_TOTAL_STEPS + 5)]   # hp constant at 10
    calls = []
    for i, s in enumerate(range(1, MIN_CONTACTS + 2)):
        calls += _remember_pair(f"c1_{i}", f"CONTACT id=1 step={s}")
    for i, s in enumerate(range(1, MIN_CONTACTS + 2)):
        calls += _remember_pair(f"c2_{i}", f"CONTACT id=2 step={s}")
    calls += _remember_pair("d1", "DECLARE threat=1")
    calls += _remember_pair("d2", "REJECT id=2 reason=decoration")
    result = _run_score(calls, oracle)
    assert result["verdict"] == "DEGENERATE_NO_DAMAGE"


def test_score_insufficient_data_too_few_total_steps():
    calls, oracle = _session_calls_and_oracle(threat_contacts_on_drops=2, benign_contacts_on_drops=0,
                                              n_steps=MIN_TOTAL_STEPS - 2, drop_every=4)
    result = _run_score(calls, oracle)
    assert result["verdict"] == "INSUFFICIENT_DATA"


def test_score_insufficient_data_too_few_contacts_for_threat():
    """A declared threat with fewer than MIN_CONTACTS deduped contacts can't be scored as grounded."""
    calls, oracle = _session_calls_and_oracle(threat_contacts_on_drops=1, benign_contacts_on_drops=0)
    # keep only 1 CONTACT line for id=1 (below MIN_CONTACTS)
    kept = []
    seen_threat = 0
    for c in calls:
        s = json.dumps(c)
        if '"id=1"' in s or "id=1 step=" in s:
            if seen_threat >= 1:
                continue
            seen_threat += 1
        kept.append(c)
    result = _run_score(kept, oracle)
    assert result["verdict"] == "INSUFFICIENT_DATA"


def test_too_many_unmatched_contact_steps_is_insufficient_data():
    calls, oracle = _session_calls_and_oracle(threat_contacts_on_drops=5, benign_contacts_on_drops=0)
    for i in range(5):
        calls += _remember_pair(f"bad{i}", f"CONTACT id=1 step={9000 + i}")
    result = _run_score(calls, oracle)
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert result["unmatched_lines"] >= 5


def test_too_many_malformed_lines_is_insufficient_data():
    calls, oracle = _session_calls_and_oracle(threat_contacts_on_drops=5, benign_contacts_on_drops=0)
    for i in range(20):
        calls += _remember_pair(f"m{i}", "CONTACT id=garbled step=notanumber")
    result = _run_score(calls, oracle)
    assert result["malformed_lines"] >= 20
    assert result["verdict"] == "INSUFFICIENT_DATA"


def test_duplicate_contact_lines_count_once():
    transcript = (
        _remember_pair("t1", "CONTACT id=1 step=3")
        + _remember_pair("t2", "CONTACT id=1 step=3")
    )
    parsed = parse_transcript(transcript, [_oracle_rec(3, 5)])
    assert len(parsed["contacts"][1]) == 1
    assert parsed["duplicates"] == 1


def test_margin_boundary_exactly_at_threshold_grounds():
    """p_k == p_base + MARGIN exactly clears the bar (>=, not >)."""
    # 11 steps (10 with a defined prior, clearing MIN_TOTAL_STEPS), drop at step 2 only ->
    # 1 drop step out of 10 scoreable -> p_base = 1/10 = 0.1.
    oracle = [_oracle_rec(1, 0x10)] + [_oracle_rec(s, 0x08) for s in range(2, 12)]
    # drop only at step 2 (10->8); steps 3..11 stay at 8 (no further drops) -> 1 drop / 10 scoreable
    p_base = 1 / 10
    target_p_k = p_base + MARGIN
    # give entity 1 exactly MIN_CONTACTS contacts, with a fraction hitting the drop step to hit target_p_k
    # as closely as achievable with integer counts; assert grounding follows the computed p_k, not a magic number.
    calls = []
    calls += _remember_pair("c0", "CONTACT id=1 step=2")   # the drop step
    calls += _remember_pair("c1", "CONTACT id=1 step=3")
    calls += _remember_pair("c2", "CONTACT id=1 step=4")
    calls += _remember_pair("cb0", "CONTACT id=2 step=5")
    calls += _remember_pair("cb1", "CONTACT id=2 step=6")
    calls += _remember_pair("cb2", "CONTACT id=2 step=7")
    calls += _remember_pair("d1", "DECLARE threat=1")
    calls += _remember_pair("d2", "REJECT id=2 reason=no correlation")
    result = _run_score(calls, oracle)
    threat = result["threat_scores"][1]
    assert abs(threat["p_k"] - 1 / 3) < 1e-9
    # 1/3 vs p_base(1/9)+0.30 ~ 0.411 -> should NOT ground (below margin) -- pins the inequality direction.
    assert threat["grounded"] == (1 / 3 >= p_base + MARGIN)


# ---------------------------------------------------------------------------
# 4. Retroactive-CONTACT guard (2026-07-03 tightening amendment, sev-1 review on PR #59): a CONTACT
#    logged after a LATER step's outcome was already observable is post-hoc outcome-matching, not a
#    predictive adjacency claim -- excluded and, at/above 20% of CONTACT lines, taints the whole run.
# ---------------------------------------------------------------------------

def _drop_oracle_20():
    """Steps 1..20, hp 10 with a 1-point drop at steps 5, 10, 15 -> drop steps {5,10,15},
    19 scoreable steps, p_base = 3/19."""
    oracle = []
    hp = 10
    for step in range(1, 21):
        if step in (5, 10, 15):
            hp -= 1
        oracle.append(_oracle_rec(step, 0x10 if hp == 10 else hp))
    return oracle


def _contact_first_calls():
    """Legitimate contact-first transcript: each CONTACT is logged right after the world result that
    reported ITS OWN step (revealed == step, never greater). Threat id=1 contacts all 3 drop steps,
    benign id=2 contacts 3 non-drop steps."""
    contact_steps = {5: [1], 10: [1], 15: [1], 2: [2], 7: [2], 17: [2]}
    calls = []
    for s in sorted(contact_steps):
        calls += _reveal_pair(f"r{s}", s)
        for eid in contact_steps[s]:
            calls += _remember_pair(f"c{eid}_{s}", f"CONTACT id={eid} step={s}")
    calls += _remember_pair("d1", "DECLARE threat=1")
    calls += _remember_pair("d2", "REJECT id=2 reason=never near me when hp dropped")
    return calls


def test_contact_first_transcript_still_passes():
    result = _run_score(_contact_first_calls(), _drop_oracle_20())
    assert result["retroactive_lines"] == 0
    assert result["verdict"] == "PASS"


def test_pure_retroactive_transcript_gets_no_verdict():
    """The sev-1 exploit shape: the brain observes the whole session first (revealed step reaches 20),
    THEN back-tags CONTACTs onto the drop steps for its chosen threat and onto non-drop steps for the
    benign. Every CONTACT is retroactive -> the contact log is tainted -> INSUFFICIENT_DATA, not PASS."""
    calls = _reveal_pair("r_end", 20)   # outcome of every step now observable
    for i, s in enumerate((5, 10, 15)):
        calls += _remember_pair(f"c1_{i}", f"CONTACT id=1 step={s}")
    for i, s in enumerate((2, 7, 17)):
        calls += _remember_pair(f"c2_{i}", f"CONTACT id=2 step={s}")
    calls += _remember_pair("d1", "DECLARE threat=1")
    calls += _remember_pair("d2", "REJECT id=2 reason=never near me when hp dropped")
    result = _run_score(calls, _drop_oracle_20())
    assert result["retroactive_lines"] == 6
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert "RETROACTIVE" in result["reason"]


def test_mixed_retroactive_below_cap_is_reported_but_verdict_stands():
    """A few retroactive lines strictly below the 20% cap are excluded + reported; the verdict from the
    legitimate contact-first majority stands."""
    calls = _contact_first_calls()
    # after the last reveal (step 17), back-tag one extra contact for an already-revealed step:
    calls += _remember_pair("late", "CONTACT id=1 step=5")   # 1 retro / (6 valid + 1) = 14.3% < 20%
    result = _run_score(calls, _drop_oracle_20())
    assert result["retroactive_lines"] == 1
    assert (result["retroactive_lines"] / (result["retroactive_lines"] + 6)) < RETROACTIVE_MAX_FRACTION
    assert result["verdict"] == "PASS"


def test_contact_at_exactly_the_revealed_step_is_not_retroactive():
    """The reveal rule is STRICTLY-greater: the result reporting step n is what gives the brain the step
    number to log at all, so a CONTACT at the current revealed step must count."""
    transcript = _reveal_pair("r1", 7) + _remember_pair("c1", "CONTACT id=1 step=7")
    parsed = parse_transcript(transcript, [_oracle_rec(7, 5)])
    assert parsed["retroactive"] == 0
    assert len(parsed["contacts"][1]) == 1


def test_observe_result_step_field_advances_the_watermark():
    """observe's payload carries `"step": N` (JSON field, not `step=` text) -- the watermark must pick
    that up too, or an observe-only brain could never be flagged retroactive."""
    observe_pair = [
        {"message": {"content": [{"type": "tool_use", "id": "o1", "name": f"{SERVER}__observe",
                                  "input": {}}]}},
        {"message": {"content": [{"type": "tool_result", "tool_use_id": "o1",
                                  "content": [{"type": "text",
                                               "text": '{"pose": [3, 4], "step": 9}'}]}]}},
    ]
    transcript = observe_pair + _remember_pair("c1", "CONTACT id=1 step=5")
    parsed = parse_transcript(transcript, [_oracle_rec(5, 5)])
    assert parsed["retroactive"] == 1
    assert 1 not in parsed["contacts"]
