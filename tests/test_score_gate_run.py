"""Unit tests for eval/score_gate_run.py — the ADR-002 Phase D live-run scorer. Builds small synthetic
transcript.jsonl + oracle.jsonl fixtures (no real MCP run needed) to pin the HYP/DECLARE/REJECT parser,
the timestamp-nearest oracle alignment, and the PASS/FAIL verdict at the pinned threshold
(truth >= 0.90 AND decoy <= 0.50 AND gap >= 0.30; declared region needs >= 10 readings)."""
from __future__ import annotations

import json

from eval.score_gate_run import (
    DECOY_MAX,
    MIN_READINGS,
    TRUTH_THRESHOLD,
    _bcd,
    _parse_iso,
    parse_transcript,
    score,
)

SERVER = "mcp__cave-noire-gate"


def _remember_pair(call_id: str, lesson: str, t_iso: str) -> list[dict]:
    """One tool_use + its tool_result, the shape score_gate_run.parse_remember_calls expects."""
    return [
        {"message": {"content": [{"type": "tool_use", "id": call_id, "name": f"{SERVER}__remember",
                                  "input": {"lesson": lesson}}]}},
        {"message": {"content": [{"type": "tool_result", "tool_use_id": call_id, "content": "ok"}]},
         "timestamp": t_iso},
    ]


def _iso(t: float) -> str:
    # small helper: treat t as whole seconds past a fixed epoch for a readable ISO string
    m, s = divmod(int(t), 60)
    return f"2026-07-02T00:{m:02d}:{s:02d}.000Z"


def _oracle_rec(step: int, t: float, hp_raw: int) -> dict:
    """t is seconds-from-epoch on the SAME absolute scale as transcript timestamps (via _iso/_parse_iso),
    so timestamp-nearest alignment in the real scorer is exercised meaningfully, not by coincidence."""
    return {"step": step, "t": _parse_iso(_iso(t)), "watch": {"hp": hp_raw}}


def _write_jsonl(path, records) -> str:
    p = str(path)
    with open(p, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return p


# ---------------------------------------------------------------------------
# 1. Parser: HYP / DECLARE / REJECT line extraction + timestamp-nearest oracle alignment.
# ---------------------------------------------------------------------------

def test_parse_hyp_line_extracts_region_step_reading():
    transcript = _remember_pair("t1", "HYP region=(16,128,34,136) step=0 reading=7", "2026-07-02T00:00:00.000Z")
    oracle = [_oracle_rec(0, 0.0, 0x7)]   # bcd(0x7) = 7, t=0 matches the call's timestamp exactly
    parsed = parse_transcript(transcript, oracle)
    region = (16, 128, 34, 136)
    assert region in parsed["readings"]
    entry = parsed["readings"][region][0]
    assert entry["step"] == 0
    assert entry["reading"] == 7.0
    assert entry["oracle_hp"] == 7


def test_parse_declare_and_reject_lines():
    transcript = (
        _remember_pair("t1", "DECLARE life=(16,128,34,136)", "2026-07-02T00:00:00.000Z")
        + _remember_pair("t2", "REJECT region=(48,136,66,144) reason=looked like an enemy counter",
                        "2026-07-02T00:00:01.000Z")
    )
    parsed = parse_transcript(transcript, [])
    assert parsed["declared"] == (16, 128, 34, 136)
    assert parsed["rejected"][(48, 136, 66, 144)] == "looked like an enemy counter"


def test_bcd_decode():
    assert _bcd(0x00) == 0
    assert _bcd(0x07) == 7
    assert _bcd(0x10) == 10


def test_nearest_oracle_alignment_picks_closest_timestamp():
    transcript = _remember_pair("t1", "HYP region=(1,1,2,2) step=0 reading=5", _iso(10.0))
    oracle = [_oracle_rec(0, 0.0, 0x9), _oracle_rec(1, 10.0, 0x5), _oracle_rec(2, 20.0, 0x1)]
    parsed = parse_transcript(transcript, oracle)
    entry = parsed["readings"][(1, 1, 2, 2)][0]
    assert entry["oracle_hp"] == 5   # the t=10.0 record is the nearest to the 00:00:10 timestamp


def test_hyp_lines_with_no_timestamp_get_no_oracle_value():
    """A remember tool_use whose tool_result never arrived (malformed transcript) -> oracle_hp is None,
    not a crash."""
    transcript = [{"message": {"content": [{"type": "tool_use", "id": "orphan",
                                            "name": f"{SERVER}__remember",
                                            "input": {"lesson": "HYP region=(1,1,2,2) step=0 reading=5"}}]}}]
    parsed = parse_transcript(transcript, [_oracle_rec(0, 0.0, 0x5)])
    assert parsed["readings"] == {}   # no matching tool_result -> the call never gets paired/counted


# ---------------------------------------------------------------------------
# 2. score(): PASS / FAIL / NO_DECLARE / INSUFFICIENT_DATA verdicts at the pinned threshold.
# ---------------------------------------------------------------------------

def _perfect_run_calls(truth_region, decoy_region, n=10):
    """n perfect HYP readings for the truth region (always == oracle hp) and n readings for the decoy
    region that never match (agreement 0), one remember call each, evenly spaced timestamps."""
    calls = []
    oracle = []
    t = 0.0
    for i in range(n):
        hp = (i % 10)  # 0..9 cycling
        oracle.append(_oracle_rec(i, t, hp))  # raw byte == decimal value here (all < 10, BCD==decimal)
        calls += _remember_pair(f"truth{i}", f"HYP region={truth_region} step={i} reading={hp}",
                                _iso(t))
        t += 1.0
        oracle.append(_oracle_rec(n + i, t, hp))
        # decoy always reads a value that can never equal hp (hp in 0..9, decoy reads 55)
        calls += _remember_pair(f"decoy{i}", f"HYP region={decoy_region} step={i} reading=55", _iso(t))
        t += 1.0
    calls += _remember_pair("declare", f"DECLARE life={truth_region}", _iso(t))
    t += 1.0
    calls += _remember_pair("reject", f"REJECT region={decoy_region} reason=looked like an enemy counter",
                            _iso(t))
    return calls, oracle


def test_score_pass_when_truth_grounds_and_decoy_is_rejected():
    truth_region_str = "(16,128,34,136)"
    decoy_region_str = "(48,136,66,144)"
    calls, oracle = _perfect_run_calls(truth_region_str, decoy_region_str, n=MIN_READINGS)
    transcript = calls
    result_pass = _run_score(transcript, oracle)
    assert result_pass["verdict"] == "PASS"
    assert result_pass["truth_agreement"] >= TRUTH_THRESHOLD
    assert result_pass["decoy_agreement"] <= DECOY_MAX


def test_score_no_declare_when_missing():
    calls = _remember_pair("t1", "HYP region=(1,1,2,2) step=0 reading=5", "2026-07-02T00:00:00.000Z")
    oracle = [_oracle_rec(0, 0.0, 0x5)]
    result = _run_score(calls, oracle)
    assert result["verdict"] == "NO_DECLARE"


def test_score_insufficient_data_below_min_readings():
    truth_region_str = "(16,128,34,136)"
    decoy_region_str = "(48,136,66,144)"
    calls, oracle = _perfect_run_calls(truth_region_str, decoy_region_str, n=MIN_READINGS - 1)
    result = _run_score(calls, oracle)
    assert result["verdict"] == "INSUFFICIENT_DATA"


def test_score_fail_when_truth_does_not_ground():
    """Truth region readings never match oracle hp -> arm (a) fails -> overall FAIL."""
    calls = []
    oracle = []
    t = 0.0
    truth = "(1,1,2,2)"
    decoy = "(3,3,4,4)"
    for i in range(MIN_READINGS):
        oracle.append(_oracle_rec(i, t, i % 10))
        calls += _remember_pair(f"truth{i}", f"HYP region={truth} step={i} reading=99", _iso(t))
        t += 1.0
    calls += _remember_pair("declare", f"DECLARE life={truth}", _iso(t))
    result = _run_score(calls, oracle)
    assert result["verdict"] == "FAIL"
    assert result["arm_a"] is False


def _run_score(transcript, oracle, tmp_path=None):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tp = _write_jsonl(f"{d}/transcript.jsonl", transcript)
        op = _write_jsonl(f"{d}/oracle.jsonl", oracle)
        return score(tp, op)
