"""Unit tests for eval/score_gate_run.py — the ADR-002 Phase D live-run scorer. Builds small synthetic
transcript.jsonl + oracle.jsonl fixtures (no real MCP run needed) to pin the HYP/DECLARE/REJECT parser,
the EXACT-step oracle alignment, and the PASS/FAIL verdict at the pinned threshold (truth >= 0.90 AND
decoy <= 0.50 AND gap >= 0.30; declared region needs >= 10 readings; > 5% unmatched HYP steps = no
verdict).

CLOCK-SKEW REGRESSION (PR #55 sev-1): the first scorer aligned readings to oracle rows by nearest
WALL-CLOCK timestamp — but the oracle's `t` is written inside the Docker container and the transcript's
`timestamp` on the host/WSL, and simulated skew showed specific offsets spuriously INFLATE agreement
toward 1.0 (a skewed clock could fake a PASS). The scorer now aligns by exact step match only; the
fixtures here deliberately give the oracle and the transcript DIFFERENT clock epochs (and a test sweeps
several skews) to pin that clocks cannot influence the verdict."""
from __future__ import annotations

import json
import tempfile

from eval.score_gate_run import (
    DECOY_LOW_EVIDENCE_MIN,
    DECOY_MAX,
    MALFORMED_MAX_FRACTION,
    MIN_NON_MODAL_READINGS,
    MIN_READINGS,
    TRUTH_THRESHOLD,
    UNMATCHED_MAX_FRACTION,
    _bcd,
    _normalize_reading,
    parse_transcript,
    score,
)

SERVER = "mcp__cave-noire-gate"

# Deliberately DIFFERENT clock epochs for the two files (the sev-1's exact failure mode): the oracle's
# `t` pretends to be a container clock near epoch 1_000_000, the transcript's ISO timestamps are real
# 2026 host time. A scorer that touches either clock would mis-align; the step-match scorer must not care.
_ORACLE_EPOCH = 1_000_000.0


def _remember_pair(call_id: str, lesson: str, t_iso: str = "2026-07-02T00:00:00.000Z") -> list[dict]:
    """One tool_use + its tool_result, the shape score_gate_run.parse_remember_calls expects."""
    return [
        {"message": {"content": [{"type": "tool_use", "id": call_id, "name": f"{SERVER}__remember",
                                  "input": {"lesson": lesson}}]}},
        {"message": {"content": [{"type": "tool_result", "tool_use_id": call_id, "content": "ok"}]},
         "timestamp": t_iso},
    ]


def _oracle_rec(step: int, hp_raw: int, t: float | None = None) -> dict:
    """`t` is on a DIFFERENT epoch than the transcript's timestamps (see _ORACLE_EPOCH) — alignment must
    come from `step` alone."""
    return {"step": step, "t": _ORACLE_EPOCH + step if t is None else t, "watch": {"hp": hp_raw}}


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
# 1. Parser: HYP / DECLARE / REJECT line extraction + exact-step oracle alignment.
# ---------------------------------------------------------------------------

def test_parse_hyp_line_extracts_region_step_reading():
    transcript = _remember_pair("t1", "HYP region=(16,128,34,136) step=3 reading=7")
    oracle = [_oracle_rec(3, 0x7)]   # bcd(0x7) = 7, step 3 matches the HYP line's step exactly
    parsed = parse_transcript(transcript, oracle)
    region = (16, 128, 34, 136)
    assert region in parsed["readings"]
    entry = parsed["readings"][region][0]
    assert entry["step"] == 3
    assert entry["reading"] == 7.0
    assert entry["oracle_hp"] == 7
    assert entry["matched"] is True


def test_parse_declare_and_reject_lines():
    transcript = (
        _remember_pair("t1", "DECLARE life=(16,128,34,136)")
        + _remember_pair("t2", "REJECT region=(48,136,66,144) reason=looked like an enemy counter")
    )
    parsed = parse_transcript(transcript, [])
    assert parsed["declared"] == (16, 128, 34, 136)
    assert parsed["rejected"][(48, 136, 66, 144)] == "looked like an enemy counter"


def test_bcd_decode():
    assert _bcd(0x00) == 0
    assert _bcd(0x07) == 7
    assert _bcd(0x10) == 10


def test_step_alignment_is_exact_not_nearest():
    """A HYP step with no oracle row must be UNMATCHED — never silently snapped to a neighbouring step."""
    transcript = _remember_pair("t1", "HYP region=(1,1,2,2) step=5 reading=9")
    oracle = [_oracle_rec(4, 0x9), _oracle_rec(6, 0x9)]   # rows either side, none AT step 5
    parsed = parse_transcript(transcript, oracle)
    entry = parsed["readings"][(1, 1, 2, 2)][0]
    assert entry["matched"] is False
    assert entry["oracle_hp"] is None


def test_orphan_tool_use_without_result_is_not_counted():
    """A remember tool_use whose tool_result never arrived (malformed transcript) -> not counted."""
    transcript = [{"message": {"content": [{"type": "tool_use", "id": "orphan",
                                            "name": f"{SERVER}__remember",
                                            "input": {"lesson": "HYP region=(1,1,2,2) step=0 reading=5"}}]}}]
    parsed = parse_transcript(transcript, [_oracle_rec(0, 0x5)])
    assert parsed["readings"] == {}


# ---------------------------------------------------------------------------
# 2. score(): PASS / FAIL / NO_DECLARE / INSUFFICIENT_DATA verdicts at the pinned threshold.
# ---------------------------------------------------------------------------

def _perfect_run_calls(truth_region, decoy_region, n=10, oracle_skew: float = 0.0):
    """n perfect HYP readings for the truth region (always == oracle hp) and n readings for the decoy
    region that never match (agreement 0), one remember call each. `oracle_skew` shifts every oracle
    row's wall-clock `t` (the sev-1's attack surface) — it must have NO effect on any verdict."""
    calls = []
    oracle = []
    step = 1   # world steps start at 1 (plugin._obs_count pre-increments)
    for i in range(n):
        hp = (i % 10)  # 0..9 cycling; raw byte == BCD value for values < 10
        oracle.append(_oracle_rec(step, hp, t=_ORACLE_EPOCH + step + oracle_skew))
        calls += _remember_pair(f"truth{i}", f"HYP region={truth_region} step={step} reading={hp}")
        step += 1
        oracle.append(_oracle_rec(step, hp, t=_ORACLE_EPOCH + step + oracle_skew))
        # decoy always reads a value that can never equal hp (hp in 0..9, decoy reads 55)
        calls += _remember_pair(f"decoy{i}", f"HYP region={decoy_region} step={step} reading=55")
        step += 1
    calls += _remember_pair("declare", f"DECLARE life={truth_region}")
    calls += _remember_pair("reject", f"REJECT region={decoy_region} reason=looked like an enemy counter")
    return calls, oracle


def test_score_pass_when_truth_grounds_and_decoy_is_rejected():
    calls, oracle = _perfect_run_calls("(16,128,34,136)", "(48,136,66,144)", n=MIN_READINGS)
    result = _run_score(calls, oracle)
    assert result["verdict"] == "PASS"
    assert result["truth_agreement"] >= TRUTH_THRESHOLD
    assert result["decoy_agreement"] <= DECOY_MAX


def test_score_verdict_is_invariant_to_oracle_clock_skew():
    """The sev-1 regression pin: shifting the oracle's wall clock by hours in either direction must not
    change the verdict or any agreement number — clocks are not on the verdict path at all."""
    baseline_calls, baseline_oracle = _perfect_run_calls("(16,128,34,136)", "(48,136,66,144)",
                                                         n=MIN_READINGS, oracle_skew=0.0)
    baseline = _run_score(baseline_calls, baseline_oracle)
    for skew in (-7200.0, -13.7, 13.7, 3600.0, 86400.0):
        calls, oracle = _perfect_run_calls("(16,128,34,136)", "(48,136,66,144)",
                                           n=MIN_READINGS, oracle_skew=skew)
        skewed = _run_score(calls, oracle)
        assert skewed["verdict"] == baseline["verdict"], f"verdict changed under clock skew {skew}"
        assert skewed["truth_agreement"] == baseline["truth_agreement"], f"agreement moved under skew {skew}"
        assert skewed["decoy_agreement"] == baseline["decoy_agreement"], f"decoy moved under skew {skew}"


def test_score_no_declare_when_missing():
    calls = _remember_pair("t1", "HYP region=(1,1,2,2) step=1 reading=5")
    oracle = [_oracle_rec(1, 0x5)]
    result = _run_score(calls, oracle)
    assert result["verdict"] == "NO_DECLARE"


def test_score_insufficient_data_below_min_readings():
    calls, oracle = _perfect_run_calls("(16,128,34,136)", "(48,136,66,144)", n=MIN_READINGS - 1)
    result = _run_score(calls, oracle)
    assert result["verdict"] == "INSUFFICIENT_DATA"


def test_score_fail_when_truth_does_not_ground():
    """Truth region readings never match oracle hp -> arm (a) fails -> overall FAIL."""
    calls = []
    oracle = []
    truth = "(1,1,2,2)"
    for i in range(MIN_READINGS):
        step = i + 1
        oracle.append(_oracle_rec(step, i % 10))
        calls += _remember_pair(f"truth{i}", f"HYP region={truth} step={step} reading=99")
    calls += _remember_pair("declare", f"DECLARE life={truth}")
    result = _run_score(calls, oracle)
    assert result["verdict"] == "FAIL"
    assert result["arm_a"] is False


# ---------------------------------------------------------------------------
# 3. Unmatched-step guard: HYP lines whose step has no oracle row must not inflate agreement.
# ---------------------------------------------------------------------------

def test_too_many_unmatched_steps_is_insufficient_data():
    """A run whose HYP lines mostly point at nonexistent steps gets NO verdict — otherwise dropping
    unmatched lines from the denominator could be gamed into a fake PASS."""
    calls, oracle = _perfect_run_calls("(16,128,34,136)", "(48,136,66,144)", n=MIN_READINGS)
    # add unmatched HYP lines (steps far past any oracle row) — well over 5% of the total
    for i in range(5):
        calls += _remember_pair(f"bad{i}", f"HYP region=(16,128,34,136) step={900 + i} reading=7")
    result = _run_score(calls, oracle)
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert result["unmatched_lines"] == 5
    assert "no oracle row" in result["reason"]


def test_few_unmatched_steps_are_reported_but_tolerated():
    """Strictly below the tolerance (5%), unmatched lines are excluded and reported; the verdict stands."""
    n = 40   # 40 truth + 40 decoy readings = 80 matched HYP lines; +4 unmatched = 4/84 ~ 4.8% < 5%
    calls, oracle = _perfect_run_calls("(16,128,34,136)", "(48,136,66,144)", n=n)
    for i in range(4):
        calls += _remember_pair(f"bad{i}", f"HYP region=(16,128,34,136) step={900 + i} reading=7")
    result = _run_score(calls, oracle)
    assert result["unmatched_lines"] == 4
    assert (result["unmatched_lines"] / result["hyp_lines"]) < UNMATCHED_MAX_FRACTION
    assert result["verdict"] == "PASS"   # the perfect run still passes; unmatched lines just don't count


def test_unmatched_exactly_at_fraction_cap_is_insufficient_data():
    """AT the cap (5% exactly) the verdict is refused — the tolerance is strictly-below."""
    n = 38   # 76 matched HYP lines; +4 unmatched = 4/80 = 5% exactly
    calls, oracle = _perfect_run_calls("(16,128,34,136)", "(48,136,66,144)", n=n)
    for i in range(4):
        calls += _remember_pair(f"bad{i}", f"HYP region=(16,128,34,136) step={900 + i} reading=7")
    result = _run_score(calls, oracle)
    assert result["hyp_lines"] == 80 and result["unmatched_lines"] == 4
    assert result["verdict"] == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# 4. 2026-07-03 amendment: variation guard (DEGENERATE_CONSTANT), reading normalization,
#    malformed guard, dedupe, decoy LOW-EVIDENCE flag. Added after the first live Phase-D run
#    (runs/brain_cn_gate/, 2026-07-02) scored PASS with all 11 matched truth readings at oracle hp=10 —
#    constant matched constant, so a static "10" box would have passed identically.
# ---------------------------------------------------------------------------

def _constant_run_calls(truth_region, n, hp=10):
    """The degenerate 2026-07-02 shape: the oracle never moves; the brain's readings all agree with the
    one constant value. Perfect agreement, zero tracking evidence."""
    calls = []
    oracle = []
    raw = 0x10 if hp == 10 else hp   # BCD encoding for 10 is 0x10; single digits are identity
    for i in range(n):
        step = i + 1
        oracle.append(_oracle_rec(step, raw))
        calls += _remember_pair(f"t{i}", f"HYP region={truth_region} step={step} reading={hp}")
    calls += _remember_pair("declare", f"DECLARE life={truth_region}")
    return calls, oracle


def test_constant_oracle_run_is_degenerate_not_pass():
    """The exact invalidated-run shape: all matched truth readings at oracle hp=10 -> DEGENERATE_CONSTANT,
    even though raw agreement is a perfect 1.0."""
    calls, oracle = _constant_run_calls("(16,128,34,136)", n=11, hp=10)
    result = _run_score(calls, oracle)
    assert result["verdict"] == "DEGENERATE_CONSTANT"
    assert result["truth_agreement"] == 1.0          # the letter of the old threshold WAS met...
    assert result["truth_distinct_oracle_values"] == 1   # ...but the oracle never moved
    assert "constant" in result["reason"]


def test_two_distinct_values_but_too_few_non_modal_is_degenerate():
    """2 distinct oracle values but only 2 non-modal readings (< MIN_NON_MODAL_READINGS) is still
    DEGENERATE_CONSTANT — a couple of outlier samples is not tracking."""
    truth = "(16,128,34,136)"
    calls = []
    oracle = []
    values = [10] * (MIN_READINGS + 2) + [7] * (MIN_NON_MODAL_READINGS - 1)   # 12x hp=10, 2x hp=7
    for i, hp in enumerate(values):
        step = i + 1
        oracle.append(_oracle_rec(step, 0x10 if hp == 10 else hp))
        calls += _remember_pair(f"t{i}", f"HYP region={truth} step={step} reading={hp}")
    calls += _remember_pair("declare", f"DECLARE life={truth}")
    result = _run_score(calls, oracle)
    assert result["verdict"] == "DEGENERATE_CONSTANT"
    assert result["truth_distinct_oracle_values"] == 2
    assert result["truth_non_modal_readings"] == MIN_NON_MODAL_READINGS - 1


def test_varied_oracle_run_still_passes():
    """The variation guard must not block a genuinely varied run (the existing perfect-run fixture cycles
    hp 0..9: 10 distinct values, 9 non-modal readings)."""
    calls, oracle = _perfect_run_calls("(16,128,34,136)", "(48,136,66,144)", n=MIN_READINGS)
    result = _run_score(calls, oracle)
    assert result["verdict"] == "PASS"
    assert result["truth_distinct_oracle_values"] >= 2
    assert result["truth_non_modal_readings"] >= MIN_NON_MODAL_READINGS


def test_reading_normalization_tolerates_quotes_and_trailing_punctuation():
    assert _normalize_reading('"7"') == 7.0
    assert _normalize_reading("7.") == 7.0
    assert _normalize_reading("7,") == 7.0
    assert _normalize_reading("'10'") == 10.0
    assert _normalize_reading("7.5") == 7.5
    assert _normalize_reading("<value>") is None
    assert _normalize_reading("ten") is None


def test_quoted_reading_scores_like_bare_reading():
    transcript = _remember_pair("t1", 'HYP region=(1,1,2,2) step=3 reading="7"')
    parsed = parse_transcript(transcript, [_oracle_rec(3, 0x7)])
    entry = parsed["readings"][(1, 1, 2, 2)][0]
    assert entry["reading"] == 7.0 and entry["oracle_hp"] == 7


def test_malformed_placeholder_readings_are_counted_not_silently_dropped():
    transcript = (
        _remember_pair("t1", "HYP region=(1,1,2,2) step=1 reading=<value>")
        + _remember_pair("t2", "HYP region=(1,1,2,2) step=2 reading=7")
    )
    parsed = parse_transcript(transcript, [_oracle_rec(1, 0x7), _oracle_rec(2, 0x7)])
    assert parsed["malformed"] == 1
    assert len(parsed["readings"][(1, 1, 2, 2)]) == 1


def test_too_many_malformed_readings_is_insufficient_data():
    """Malformed readings at/above 20% of HYP lines -> no verdict."""
    calls, oracle = _perfect_run_calls("(16,128,34,136)", "(48,136,66,144)", n=MIN_READINGS)
    # 20 valid HYP lines; add 5 malformed -> 5/25 = 20% exactly (cap is strictly-below)
    for i in range(5):
        calls += _remember_pair(f"m{i}", f"HYP region=(16,128,34,136) step={i + 1} reading=<value>")
    result = _run_score(calls, oracle)
    assert result["malformed_lines"] == 5
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert "non-numeric" in result["reason"]


def test_few_malformed_readings_are_tolerated():
    """Strictly below 20%, malformed lines are reported but the verdict stands."""
    calls, oracle = _perfect_run_calls("(16,128,34,136)", "(48,136,66,144)", n=MIN_READINGS)
    # 20 valid HYP lines; add 4 malformed -> 4/24 ~ 16.7% < 20%
    for i in range(4):
        calls += _remember_pair(f"m{i}", f"HYP region=(16,128,34,136) step={i + 1} reading=<value>")
    result = _run_score(calls, oracle)
    assert result["malformed_lines"] == 4
    assert (result["malformed_lines"] / (result["malformed_lines"] + result["hyp_lines"])
            ) < MALFORMED_MAX_FRACTION
    assert result["verdict"] == "PASS"


def test_duplicate_step_region_tuples_count_once():
    """Repeated JSON encodings of the same remember call must not multiply a reading's weight: each
    unique (region, step) counts ONCE (identical repeats AND conflicting re-reads both dropped, first
    occurrence wins)."""
    transcript = (
        _remember_pair("t1", "HYP region=(1,1,2,2) step=3 reading=7")
        + _remember_pair("t2", "HYP region=(1,1,2,2) step=3 reading=7")     # identical repeat
        + _remember_pair("t3", "HYP region=(1,1,2,2) step=3 reading=9")     # conflicting re-read, same step
        + _remember_pair("t4", "HYP region=(1,1,2,2) step=4 reading=5")     # different step: counts
    )
    parsed = parse_transcript(transcript, [_oracle_rec(3, 0x7), _oracle_rec(4, 0x5)])
    entries = parsed["readings"][(1, 1, 2, 2)]
    assert len(entries) == 2
    assert entries[0]["step"] == 3 and entries[0]["reading"] == 7.0   # first occurrence won
    assert entries[1]["step"] == 4
    assert parsed["duplicates"] == 2


def test_decoy_low_evidence_flag():
    """A decoy arm resting on fewer than DECOY_LOW_EVIDENCE_MIN readings still gets a verdict, but is
    flagged LOW-EVIDENCE."""
    truth = "(16,128,34,136)"
    decoy = "(48,136,66,144)"
    calls = []
    oracle = []
    for i in range(MIN_READINGS):
        step = i + 1
        hp = i % 10
        oracle.append(_oracle_rec(step, hp))
        calls += _remember_pair(f"t{i}", f"HYP region={truth} step={step} reading={hp}")
    # only 2 decoy readings (< 3) that never agree
    for j in range(DECOY_LOW_EVIDENCE_MIN - 1):
        step = MIN_READINGS + 1 + j
        oracle.append(_oracle_rec(step, j))
        calls += _remember_pair(f"d{j}", f"HYP region={decoy} step={step} reading=55")
    calls += _remember_pair("declare", f"DECLARE life={truth}")
    calls += _remember_pair("reject", f"REJECT region={decoy} reason=never tracked my hits")
    result = _run_score(calls, oracle)
    assert result["verdict"] == "PASS"
    assert result["decoy_readings"] == DECOY_LOW_EVIDENCE_MIN - 1
    assert result["decoy_low_evidence"] is True


def test_decoy_with_enough_readings_is_not_flagged():
    calls, oracle = _perfect_run_calls("(16,128,34,136)", "(48,136,66,144)", n=MIN_READINGS)
    result = _run_score(calls, oracle)
    assert result["decoy_readings"] >= DECOY_LOW_EVIDENCE_MIN
    assert result["decoy_low_evidence"] is False
