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
"""
from __future__ import annotations

import json
import tempfile

from eval.score_entity_gate_v3 import parse_transcript, score as v3_score
from eval.score_entity_gate_v4 import parse_claims, score as v4_score

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
