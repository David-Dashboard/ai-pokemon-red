"""Drift-guard tests for eval/score_entity_gate_v4.py, per reports/2026-07-05-entity-v4-design.md's
"MANDATORY drift-guard tests" instruction. v3 (eval/score_entity_gate_v3.py) and its own test suite
(tests/test_score_entity_gate_v3.py) are FROZEN -- untouched by this file.

Pins exactly the two properties the design doc calls out:
  1. v4 imports v3's bar math BYTE-IDENTICAL: feeding v3 and v4 equivalent inputs (same oracle, same
     skills, same underlying NEAR/DECLARE/REJECT facts -- one shaped as v3's freeform `remember` text,
     the other as v4's typed claims.jsonl records) must yield an IDENTICAL verdict and identical
     per-entity q_k/b_k numbers.
  2. the step/revealed_at semantics: a late claim_near (brain-supplied `step` < server-stamped
     `revealed_at`) is counted RETROACTIVE by v4's parse_claims exactly as v3's watermark rule would
     flag the equivalent freeform NEAR line.

Plus two post-review additions (R2's BLOCK + MAJOR 2, PR #102):
  3. the REAL tool path (World.call, a FakeEmulator, the same builder tests/test_kirby_skill_port.py
     uses) must NOT manufacture a false RETROACTIVE exclusion when a session makes more than one claim
     call about a single already-observed frame -- the exact reproduced PASS(v3)->INSUFFICIENT_DATA(v4)
     divergence R2 flagged BLOCK on. The two earlier drift-guard tests above hard-code
     `revealed_at == step` for every synthetic record, which never exercises the claim tool's OWN
     bookkeeping across back-to-back calls -- this test does, through the real handlers.
  4. MALFORMED_MAX_FRACTION must be reachable: parse_claims must count unrecognized/garbage records the
     same way v3's catch-all counts unparseable ENT/NEAR/DECLARE/REJECT-shaped `remember` lines.
"""
from __future__ import annotations

import json
import tempfile

from eval.score_entity_gate_v3 import parse_transcript, score as v3_score
from eval.score_entity_gate_v4 import parse_claims, score as v4_score
from tests.test_kirby_skill_port import _make_world

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


def _oracle_98(drop_at=(19, 38, 57, 76, 97)) -> list[dict]:
    oracle = []
    hp = 5
    for step in range(1, 99):
        if step in drop_at and hp > 0:
            hp -= 1
        oracle.append(_oracle_rec(step, _raw(hp)))
    return oracle


def _qualifying_conditional_skill(step=200, world_steps_used=8, iterations=2,
                                   predicate="region_changed(0,0,8,8)") -> dict:
    executed = [{"button": "right", "hold_frames": 30, "ok": True} for _ in range(world_steps_used)]
    executed.append({"repeat_until_summary": f"stop_when '{predicate}' fired after "
                     f"{world_steps_used} press(es) ({iterations} iteration(s))",
                     "iterations": iterations, "world_steps": world_steps_used})
    return {"event": "run_skill", "step": step, "name": "approach_suspect", "executed": executed,
            "executed_step_count": world_steps_used, "stop_reason": executed[-1]["repeat_until_summary"],
            "world_steps_used": world_steps_used}


def _write_jsonl(path, records) -> str:
    p = str(path)
    with open(p, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return p


# ---------------------------------------------------------------------------
# 1. v4 imports v3's bar math byte-identical: equivalent v3 (freeform) and v4 (typed) inputs must
#    produce an IDENTICAL verdict + identical per-entity q_k/b_k.
# ---------------------------------------------------------------------------

def test_v3_and_v4_agree_on_equivalent_inputs():
    THREAT_NEARS = (18, 37, 56, 75, 96)   # each just before a drop in DROPS_5 -> q_k=1.0
    BENIGN_EARLY = (1, 2, 3)              # never near a drop -> q_k=0.0, correctly rejected
    oracle = _oracle_98()
    skills = [_qualifying_conditional_skill()]

    # -- v3 shape: freeform `remember` lines, scored via regex.
    v3_transcript: list[dict] = []
    for i, s in enumerate(THREAT_NEARS):
        v3_transcript += _remember_pair(f"t{i}", f"NEAR id=1 step={s}")
    for i, s in enumerate(BENIGN_EARLY):
        v3_transcript += _remember_pair(f"b{i}", f"NEAR id=2 step={s}")
    v3_transcript += _remember_pair("d1", "DECLARE threat=1")
    v3_transcript += _remember_pair("d2", "REJECT id=2 reason=never near me before a drop")

    # -- v4 shape: the SAME underlying facts, as typed claims records. step == revealed_at throughout
    # (the brain claimed NEAR right after observing that exact step -- not retroactive).
    v4_claims: list[dict] = []
    for s in THREAT_NEARS:
        v4_claims.append({"event": "claim_near", "id": 1, "step": s, "revealed_at": s})
    for s in BENIGN_EARLY:
        v4_claims.append({"event": "claim_near", "id": 2, "step": s, "revealed_at": s})
    v4_claims.append({"event": "declare", "id": 1, "kind": "threat"})
    v4_claims.append({"event": "reject", "id": 2, "reason": "never near me before a drop"})

    with tempfile.TemporaryDirectory() as d:
        v3_result = v3_score(
            _write_jsonl(f"{d}/transcript.jsonl", v3_transcript),
            _write_jsonl(f"{d}/oracle.jsonl", oracle),
            _write_jsonl(f"{d}/skills.jsonl", skills),
        )
        v4_result = v4_score(
            _write_jsonl(f"{d}/claims.jsonl", v4_claims),
            f"{d}/oracle.jsonl",
            f"{d}/skills.jsonl",
        )

    assert v3_result["verdict"] == v4_result["verdict"] == "PASS"
    assert v3_result["threat_scores"][1]["q_k"] == v4_result["threat_scores"][1]["q_k"]
    assert v3_result["threat_scores"][1]["b_k"] == v4_result["threat_scores"][1]["b_k"]
    assert v3_result["threat_scores"][1]["grounded"] == v4_result["threat_scores"][1]["grounded"] is True
    assert v3_result["benign_scores"][2]["q_k"] == v4_result["benign_scores"][2]["q_k"]
    assert v3_result["benign_scores"][2]["b_k"] == v4_result["benign_scores"][2]["b_k"]
    assert v3_result["arm_a"] == v4_result["arm_a"] is True
    assert v3_result["arm_b"] == v4_result["arm_b"] is True


# ---------------------------------------------------------------------------
# 2. Step semantics drift-guard: a late claim_near (server-stamped revealed_at > brain-supplied step)
#    is RETROACTIVE in v4, matching v3's watermark rule on the equivalent freeform scenario.
# ---------------------------------------------------------------------------

def test_late_claim_near_is_retroactive_exactly_as_v3_watermark_rule():
    oracle = [_oracle_rec(2, _raw(5)), _oracle_rec(5, _raw(5))]

    # v3: a revealing tool call (whats_changed) shows step=5 BEFORE the brain remembers "NEAR id=1
    # step=2" -- v3's watermark rule (revealed_at_log > step) flags this as retroactive.
    v3_transcript = _reveal_pair("r1", step=5) + _remember_pair("c1", "NEAR id=1 step=2")
    v3_parsed = parse_transcript(v3_transcript, oracle, skills=[])
    assert v3_parsed["retroactive"] == 1
    assert 1 not in v3_parsed["nears"]

    # v4: the SAME fact, as a typed claim_near record -- brain-supplied step=2, server-stamped
    # revealed_at=5 (the world had already advanced to _obs_count=5 by the time the tool fired).
    v4_claims = [{"event": "claim_near", "id": 1, "step": 2, "revealed_at": 5}]
    v4_parsed = parse_claims(v4_claims, oracle, skills=[])
    assert v4_parsed["retroactive"] == 1
    assert 1 not in v4_parsed["nears"]

    # exact parity: both scorers exclude exactly one retroactive NEAR line, none accepted.
    assert v3_parsed["retroactive"] == v4_parsed["retroactive"]
    assert v3_parsed["nears"] == v4_parsed["nears"] == {}

    # non-retroactive boundary, same claim: revealed_at == step (claimed at the exact step just shown)
    # must NOT be flagged -- only a strict revealed_at > step is retroactive (v3:361's
    # `revealed_at_log > step`, byte-identical inclusivity carried into v4's `revealed_at > step`).
    boundary_parsed = parse_claims([{"event": "claim_near", "id": 1, "step": 5, "revealed_at": 5}],
                                    oracle, skills=[])
    assert boundary_parsed["retroactive"] == 0
    assert boundary_parsed["nears"][1] == [{"step": 5, "matched": True}]


# ---------------------------------------------------------------------------
# 3. R2 MAJOR 1 (the BLOCK): the REAL tool path must not manufacture a false RETROACTIVE exclusion
#    when a session claims more than one thing about a single already-observed frame. Drives
#    world_mcp.World.call directly (FakeEmulator, no PyBoy) through claim_entity/claim_near/declare/
#    reject/note_reading, exactly the sequence the reviewer showed breaks parity: two (or more) claim
#    calls back-to-back about ONE frame the brain was shown exactly once.
# ---------------------------------------------------------------------------

def test_real_tool_path_multiple_claims_per_frame_are_not_retroactive(tmp_path, monkeypatch):
    monkeypatch.setenv("KIRBY_CLAIMS", "1")
    monkeypatch.delenv("KIRBY_SKILLS", raising=False)
    out = str(tmp_path / "out")
    w = _make_world(out)

    # ONE real reveal -- the only thing that may legitimately advance plugin._obs_count here.
    w.call("observe", {})
    step = w.plugin._obs_count
    assert step >= 1

    # THREE claim calls about that SAME already-observed frame, back-to-back, no new reveal in
    # between -- the natural way a brain reports "I see two things near me in this frame" (R2's exact
    # reproduction scenario). None of these may bump plugin._obs_count.
    r1 = w.call("claim_near", {"id": 1, "step": step})
    r2 = w.call("claim_near", {"id": 2, "step": step})
    r3 = w.call("claim_entity", {"id": 3, "x0": 0, "y0": 0, "x1": 8, "y1": 8,
                                 "step": step, "kind": "benign"})
    assert w.plugin._obs_count == step, "a claim ack must never advance the reveal watermark"

    # acks are bare "Noted." -- no re-rendered screen content riding along.
    for r in (r1, r2, r3):
        texts = [c["text"] for c in r if c.get("type") == "text"]
        assert any(t == "Noted." for t in texts)
        assert not any("screen_path" in t or "step=" in t for t in texts if t != "Noted.")

    with open(w._claims_log_path, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    assert len(records) == 3
    for rec in records:
        assert rec["step"] == step
        if "revealed_at" in rec:
            assert rec["revealed_at"] == step, (
                "second/third claim about the same frame got a different revealed_at than the "
                "first -- exactly the R2 MAJOR 1 bug (own trailing observe polluting the watermark)")

    parsed = parse_claims(records, oracle=[], skills=[])
    assert parsed["retroactive"] == 0
    assert parsed["nears"][1][0]["step"] == step
    assert parsed["nears"][2][0]["step"] == step
    assert 3 in parsed["ent_claims"]


# ---------------------------------------------------------------------------
# 4. R2 MAJOR 2: MALFORMED_MAX_FRACTION must be reachable -- unrecognized/garbage claims.jsonl records
#    count as malformed exactly like v3's catch-all counts unparseable ENT/NEAR/DECLARE/REJECT-shaped
#    `remember` lines (mirrors the reviewer's reproduced 8-garbage/2-valid scenario).
# ---------------------------------------------------------------------------

def test_malformed_fraction_guard_is_live():
    garbage = [{"event": "clam_near", "id": 1, "step": 1}] * 4 + [{"event": "delcare", "id": 9}] * 4
    valid = [{"event": "claim_near", "id": 1, "step": s, "revealed_at": s} for s in (1, 2)]

    parsed = parse_claims(garbage + valid, oracle=[], skills=[])
    assert parsed["malformed"] == 8
    assert parsed["n_lines"] == 10
    assert (parsed["malformed"] / parsed["n_lines"]) >= 0.20

    with tempfile.TemporaryDirectory() as d:
        claims_path = _write_jsonl(f"{d}/claims.jsonl", garbage + valid)
        oracle_path = _write_jsonl(f"{d}/oracle.jsonl", [_oracle_rec(1, _raw(5)), _oracle_rec(2, _raw(5))])
        skills_path = _write_jsonl(f"{d}/skills.jsonl", [])
        result = v4_score(claims_path, oracle_path, skills_path)
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert "malformed" in result["reason"]


def test_malformed_fraction_guard_ignores_note_reading_and_recognized_events():
    # note_reading is deliberately audit-only -- must NOT count toward malformed or n_lines.
    records = [{"event": "note_reading", "step": 1, "hud_life": 5, "drop_believed": False, "text": "x"}] * 5
    records += [{"event": "claim_near", "id": 1, "step": 1, "revealed_at": 1}]
    parsed = parse_claims(records, oracle=[], skills=[])
    assert parsed["malformed"] == 0
    assert parsed["n_lines"] == 1
    assert parsed["nears"][1] == [{"step": 1, "matched": False}]

    # a recognized event with a corrupted field must count as malformed, not crash the scorer.
    corrupted = [{"event": "claim_near", "id": 1}]   # missing required "step"/"revealed_at"
    parsed2 = parse_claims(corrupted, oracle=[], skills=[])
    assert parsed2["malformed"] == 1
    assert parsed2["n_lines"] == 1
