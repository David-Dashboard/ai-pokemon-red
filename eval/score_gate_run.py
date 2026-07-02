"""ADR-002 Phase D gate scorer — score a LIVE brain's own HYPOTHESIS about "region R = my life" against
the RAM `hp` oracle, using the exact SS9 arms + threshold `eval/score_hud_grounding.py` pinned offline
(`reports/2026-07-03-adr002-gate-plan.md`): PASS = truth agreement >= 0.90 AND decoy agreement <= 0.50
AND gap >= 0.30.

This is the LIVE-run counterpart: instead of a hand-written `RegionDigitDetector`, the "detector" here is
whatever numeric VALUE the brain itself reported for a region while playing (its own `read_region`/
`whats_changed`-grounded guesses), logged via `remember` in a fixed machine-parseable form:

    HYP region=(x0,y0,x1,y1) step=<n> reading=<value>
    DECLARE life=(x0,y0,x1,y1)
    REJECT region=(x0,y0,x1,y1) reason=<...>

`region` in a HYP/DECLARE/REJECT line is only ever an identifier the brain assigned itself — the oracle
(RAM `hp`, BCD @ 0xC120, see world_mcp.py's GAMES["cave_noire"]["watch"]) is NEVER sent to the brain; it
only ever appears in `world/oracle.jsonl` on disk, read here for scoring only (the no-leak rule, same
discipline as score_hud_grounding.py).

Alignment (transcript reading <-> oracle hp at that moment): by EXACT world-step match ONLY. The
`read_region`/`whats_changed` result text reports `step=<N>` — the plugin's _obs_count for the frame
shown, which is exactly the `step` field of the oracle.jsonl row logged for that frame — and the brain is
briefed to copy that step verbatim into its HYP line. NO wall-clock timestamps anywhere in the verdict
path: the oracle's `t` is written inside the Docker container while the transcript's `timestamp` is
written on the host/WSL, and clock skew between the two was shown to spuriously INFLATE agreement (a
skewed clock can fake a PASS — PR #55 review). HYP lines whose step has no oracle row are counted as
UNMATCHED and reported; if more than UNMATCHED_MAX_FRACTION of all HYP lines are unmatched, the verdict
is INSUFFICIENT_DATA (selective dropping must not be able to inflate agreement).

POST-HOC TIGHTENING AMENDMENT (2026-07-03 — stricter, never looser): the first live Phase-D run
(runs/brain_cn_gate/, 2026-07-02) scored GATE:PASS under the letter of the original threshold but was
INVALIDATED as DEGENERATE — all 11 matched truth readings sat at oracle hp=10 (the brain took zero
damage), so a constant matched a constant; a static "10" box would have scored identically, and arm (a)'s
"tracks the oracle ACROSS a run" was never exercised. This amendment adds, without loosening anything:
  * VARIATION GUARD: the matched truth readings must span >= 2 distinct oracle hp values, with >= 3
    readings at a non-modal value; otherwise verdict = DEGENERATE_CONSTANT (no PASS possible).
  * DECOY EVIDENCE FLAG: the decoy arm's reading count is always reported; a decoy arm resting on < 3
    readings is flagged LOW-EVIDENCE (the verdict is still computed, but printed with the flag).
  * READING NORMALIZATION: trailing punctuation/quote artifacts are stripped from parsed readings;
    non-numeric readings (e.g. a literal '<value>' placeholder) count as MALFORMED and are reported —
    malformed >= 20% of HYP lines = INSUFFICIENT_DATA. Repeated encodings of the same remember call are
    deduped: each unique (region, step) counts ONCE (first occurrence wins; repeats are reported).

Usage:
    uv run python -m eval.score_gate_run runs/brain_cn_gate/transcript.jsonl runs/brain_cn_gate/world/oracle.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys

WRAM0 = 0xC000
HP_ADDR = 0xC120   # ADR-002 gate life oracle -- BCD (see reports/2026-07-03-adr002-gate-plan.md)

# reading= captures ANY non-space token; _normalize_reading then strips quote/punctuation artifacts and
# rejects non-numeric tokens as MALFORMED (2026-07-03 amendment) instead of silently ignoring the line.
_HYP_RE = re.compile(
    r"HYP\s+region=\((-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\)\s+step=(-?\d+)\s+reading=(\S+)"
)
_DECLARE_RE = re.compile(r"DECLARE\s+life=\((-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\)")
_REJECT_RE = re.compile(r"REJECT\s+region=\((-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\)\s+reason=(.*)")

TRUTH_THRESHOLD = 0.90
DECOY_MAX = 0.50
DECOY_GAP_MIN = 0.30
MIN_READINGS = 10           # a declared region with fewer readings than this = insufficient data, no verdict
UNMATCHED_MAX_FRACTION = 0.05   # unmatched HYP steps must stay STRICTLY below this fraction of all lines
# 2026-07-03 amendment thresholds (see the module docstring):
MIN_DISTINCT_ORACLE_VALUES = 2    # matched truth readings must span at least this many oracle hp values
MIN_NON_MODAL_READINGS = 3        # ... with at least this many readings at a non-modal oracle value
DECOY_LOW_EVIDENCE_MIN = 3        # decoy arm resting on fewer readings than this is flagged LOW-EVIDENCE
MALFORMED_MAX_FRACTION = 0.20     # malformed readings at/above this fraction of HYP lines = no verdict


def _bcd(b: int) -> int:
    return (b >> 4) * 10 + (b & 0x0F)


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _region_key(x0, y0, x1, y1) -> tuple[int, int, int, int]:
    return (int(x0), int(y0), int(x1), int(y1))


_READING_STRIP = "'\"`.,;:!?)]}([{"   # quote/punctuation artifacts stripped from a reading token's ends


def _normalize_reading(token: str) -> float | None:
    """Parse a HYP reading token to a float, tolerating quote/punctuation artifacts on the ends
    (e.g. `reading="7"` or `reading=7.` or `reading=7,`). Returns None for a non-numeric token
    (e.g. a literal '<value>' placeholder) — counted by the caller as MALFORMED."""
    token = token.strip(_READING_STRIP)
    try:
        return float(token)
    except ValueError:
        return None


def parse_remember_calls(transcript: list[dict]) -> list[str]:
    """Walk the transcript for `remember` tool calls; return each call's `lesson` text, in transcript
    order, counting only calls whose `tool_result` actually arrived (the call completed)."""
    pending: dict[str, str] = {}   # tool_use_id -> lesson text, awaiting its tool_result
    out: list[str] = []
    for msg in transcript:
        content = (msg.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and str(block.get("name", "")).endswith("__remember"):
                lesson = (block.get("input") or {}).get("lesson", "")
                pending[block["id"]] = lesson
            elif block.get("type") == "tool_result":
                tool_use_id = block.get("tool_use_id")
                if tool_use_id in pending:
                    out.append(pending.pop(tool_use_id))
    return out


def _oracle_hp_by_step(oracle: list[dict]) -> dict[int, int | None]:
    """step -> BCD-decoded hp (None = row exists but hp missing / out-of-range transition garbage)."""
    by_step: dict[int, int | None] = {}
    for rec in oracle:
        step = rec.get("step")
        if step is None:
            continue
        raw = (rec.get("watch") or {}).get("hp")
        if raw is None:
            by_step[int(step)] = None
            continue
        v = _bcd(int(raw))
        by_step[int(step)] = v if 0 <= v <= 10 else None
    return by_step


def parse_transcript(transcript: list[dict], oracle: list[dict]) -> dict:
    """Extract HYP readings (per region), the DECLAREd region, and REJECTed regions + reasons. Each HYP
    reading is aligned to the oracle row with the EXACT same step (matched=False if no such row).

    2026-07-03 amendment: reading tokens are normalized (_normalize_reading); non-numeric readings are
    counted as `malformed` (not silently ignored). Repeated encodings of the same remember call are
    deduped — each unique (region, step) counts ONCE, first occurrence wins; repeats (identical or
    conflicting re-reads of the same step) are counted as `duplicates`."""
    lessons = parse_remember_calls(transcript)
    hp_by_step = _oracle_hp_by_step(oracle)
    readings: dict[tuple, list[dict]] = {}   # region -> [{"step", "reading", "oracle_hp", "matched"}]
    declared: tuple | None = None
    rejected: dict[tuple, str] = {}
    malformed = 0
    duplicates = 0
    seen: set[tuple] = set()   # (region, step) pairs already counted

    for lesson in lessons:
        m = _HYP_RE.search(lesson)
        if m:
            x0, y0, x1, y1, step, reading_tok = m.groups()
            region = _region_key(x0, y0, x1, y1)
            step = int(step)
            reading = _normalize_reading(reading_tok)
            if reading is None:
                malformed += 1
                continue
            if (region, step) in seen:
                duplicates += 1
                continue
            seen.add((region, step))
            matched = step in hp_by_step
            readings.setdefault(region, []).append(
                {"step": step, "reading": reading,
                 "oracle_hp": hp_by_step.get(step), "matched": matched})
            continue
        m = _DECLARE_RE.search(lesson)
        if m:
            declared = _region_key(*m.groups())
            continue
        m = _REJECT_RE.search(lesson)
        if m:
            x0, y0, x1, y1, reason = m.groups()
            rejected[_region_key(x0, y0, x1, y1)] = reason.strip()

    return {"readings": readings, "declared": declared, "rejected": rejected,
            "malformed": malformed, "duplicates": duplicates}


def _agreement(entries: list[dict]) -> tuple[float, int]:
    """Exact-value agreement rate between a region's logged readings and the step-aligned oracle hp, over
    entries whose step matched an oracle row AND whose oracle value is in-range (same discipline as
    score_hud_grounding.py). Unmatched entries never enter the denominator here — the unmatched-fraction
    guard in score() is what prevents that exclusion from inflating agreement."""
    agree = total = 0
    for e in entries:
        if not e["matched"]:
            continue
        oh = e["oracle_hp"]
        if oh is None:
            continue
        total += 1
        if e["reading"] == oh:
            agree += 1
    return (agree / total if total else 0.0), total


def _oracle_variation(entries: list[dict]) -> tuple[int, int]:
    """(distinct oracle hp values, readings at a NON-modal oracle value) over the matched, in-range
    entries — the 2026-07-03 variation guard's inputs. A run where the oracle never moved (or barely
    moved) cannot demonstrate that the detector TRACKS the oracle rather than matching a constant."""
    values = [e["oracle_hp"] for e in entries if e["matched"] and e["oracle_hp"] is not None]
    if not values:
        return 0, 0
    counts: dict[int, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    modal_count = max(counts.values())
    return len(counts), len(values) - modal_count


def score(transcript_path: str, oracle_path: str) -> dict:
    transcript = load_jsonl(transcript_path)
    oracle = load_jsonl(oracle_path)
    parsed = parse_transcript(transcript, oracle)
    readings, declared, rejected = parsed["readings"], parsed["declared"], parsed["rejected"]
    n_malformed, n_duplicates = parsed["malformed"], parsed["duplicates"]

    all_entries = [e for entries in readings.values() for e in entries]
    n_hyp = len(all_entries)
    n_unmatched = sum(1 for e in all_entries if not e["matched"])
    result: dict = {"declared": declared, "rejected": rejected, "regions_seen": sorted(readings),
                    "hyp_lines": n_hyp, "unmatched_lines": n_unmatched,
                    "malformed_lines": n_malformed, "duplicate_lines": n_duplicates}

    if declared is None:
        result["verdict"] = "NO_DECLARE"
        return result

    # 2026-07-03 amendment: too many malformed readings = no verdict. Denominator is unique valid + malformed
    # (duplicates excluded — repeated encodings of one call must not dilute the malformed fraction).
    n_lines = n_hyp + n_malformed
    if n_lines and n_malformed and (n_malformed / n_lines) >= MALFORMED_MAX_FRACTION:
        result["verdict"] = "INSUFFICIENT_DATA"
        result["reason"] = (f"{n_malformed}/{n_lines} HYP lines have a non-numeric reading "
                            f"(>= {MALFORMED_MAX_FRACTION:.0%} — must stay below)")
        return result

    # Anti-gaming guard: if too many HYP lines point at steps with no oracle row, refuse a verdict —
    # excluding unmatched lines from the denominator must not become a way to inflate agreement.
    # Unmatched lines are tolerated (and excluded) only while STRICTLY below the fraction cap.
    if n_hyp and n_unmatched and (n_unmatched / n_hyp) >= UNMATCHED_MAX_FRACTION:
        result["verdict"] = "INSUFFICIENT_DATA"
        result["reason"] = (f"{n_unmatched}/{n_hyp} HYP lines reference steps with no oracle row "
                            f"(>= {UNMATCHED_MAX_FRACTION:.0%} — must stay below)")
        return result

    truth_entries = readings.get(declared, [])
    truth_agree, truth_n = _agreement(truth_entries)
    result["truth_region"] = declared
    result["truth_agreement"] = truth_agree
    result["truth_readings"] = truth_n

    if truth_n < MIN_READINGS:
        result["verdict"] = "INSUFFICIENT_DATA"
        result["reason"] = f"declared region has {truth_n} scoreable readings (< {MIN_READINGS})"
        return result

    # 2026-07-03 VARIATION GUARD: constant-matched-constant is not tracking. The matched truth readings
    # must span >= MIN_DISTINCT_ORACLE_VALUES distinct oracle hp values, with >= MIN_NON_MODAL_READINGS
    # readings at a non-modal value; otherwise no PASS is possible (a static box would score identically —
    # exactly the degenerate 2026-07-02 run this guard exists because of).
    n_distinct, n_non_modal = _oracle_variation(truth_entries)
    result["truth_distinct_oracle_values"] = n_distinct
    result["truth_non_modal_readings"] = n_non_modal
    if n_distinct < MIN_DISTINCT_ORACLE_VALUES or n_non_modal < MIN_NON_MODAL_READINGS:
        result["verdict"] = "DEGENERATE_CONSTANT"
        result["reason"] = (f"matched truth readings span {n_distinct} distinct oracle value(s) with "
                            f"{n_non_modal} non-modal reading(s) — need >= {MIN_DISTINCT_ORACLE_VALUES} "
                            f"distinct and >= {MIN_NON_MODAL_READINGS} non-modal to show TRACKING, not "
                            "constant-matches-constant")
        return result

    # decoy = the best-scoring REJECTED candidate (the hardest case to reject, per SS9's arm (b)).
    decoy_region = None
    decoy_agree = 0.0
    decoy_n = 0
    for region in rejected:
        entries = readings.get(region, [])
        if not entries:
            continue
        agree, n = _agreement(entries)
        if n >= 1 and (decoy_region is None or agree > decoy_agree):
            decoy_region, decoy_agree, decoy_n = region, agree, n

    result["decoy_region"] = decoy_region
    result["decoy_agreement"] = decoy_agree if decoy_region is not None else None
    result["decoy_readings"] = decoy_n
    # 2026-07-03 amendment: a decoy arm resting on very few readings is weak evidence of rejection —
    # the verdict is still computed, but flagged so a reviewer doesn't over-read arm (b).
    result["decoy_low_evidence"] = decoy_region is not None and decoy_n < DECOY_LOW_EVIDENCE_MIN

    arm_a = truth_agree >= TRUTH_THRESHOLD
    if decoy_region is None:
        # No rejected candidate had any readings to score -> arm (b) can't be evaluated.
        result["verdict"] = "PASS" if arm_a else "FAIL"
        result["arm_a"] = arm_a
        result["arm_b"] = None
        return result

    arm_b = decoy_agree <= DECOY_MAX and (truth_agree - decoy_agree) >= DECOY_GAP_MIN
    result["arm_a"] = arm_a
    result["arm_b"] = arm_b
    result["verdict"] = "PASS" if (arm_a and arm_b) else "FAIL"
    return result


def format_report(r: dict) -> str:
    lines = ["=== ADR-002 Phase D gate score ==="]
    if r.get("unmatched_lines"):
        lines.append(f"unmatched HYP lines (step has no oracle row): {r['unmatched_lines']}/{r['hyp_lines']}")
    if r.get("malformed_lines"):
        lines.append(f"malformed HYP lines (non-numeric reading): {r['malformed_lines']}")
    if r.get("duplicate_lines"):
        lines.append(f"duplicate HYP lines (repeat (region, step), first kept): {r['duplicate_lines']}")
    if r.get("declared") is None:
        lines.append("no DECLARE line found in the transcript's `remember` calls.")
        lines.append(f"regions seen (HYP only): {r.get('regions_seen')}")
        lines.append("\nVERDICT: NO_DECLARE (nothing to score)")
        return "\n".join(lines)
    if r["verdict"] == "INSUFFICIENT_DATA" and "truth_region" not in r:
        lines.append(f"\nVERDICT: INSUFFICIENT_DATA ({r.get('reason')})")
        return "\n".join(lines)
    lines.append(f"DECLAREd region (truth): {r['truth_region']}")
    lines.append(f"  truth agreement: {r['truth_agreement']:.3f} ({r['truth_readings']} readings)")
    if "truth_distinct_oracle_values" in r:
        lines.append(f"  oracle variation: {r['truth_distinct_oracle_values']} distinct value(s), "
                     f"{r['truth_non_modal_readings']} non-modal reading(s)")
    if r["verdict"] == "INSUFFICIENT_DATA":
        lines.append(f"\nVERDICT: INSUFFICIENT_DATA ({r.get('reason')})")
        return "\n".join(lines)
    if r["verdict"] == "DEGENERATE_CONSTANT":
        lines.append(f"\nVERDICT: DEGENERATE_CONSTANT ({r.get('reason')})")
        return "\n".join(lines)
    if r.get("decoy_region") is not None:
        lines.append(f"best-scoring REJECTED (decoy): {r['decoy_region']} "
                     f"reason={r['rejected'].get(r['decoy_region'])!r}")
        lines.append(f"  decoy agreement: {r['decoy_agreement']:.3f} ({r['decoy_readings']} readings)"
                     + ("  [LOW-EVIDENCE: fewer than "
                        f"{DECOY_LOW_EVIDENCE_MIN} readings — arm (b) is weakly supported]"
                        if r.get("decoy_low_evidence") else ""))
    else:
        lines.append("no REJECTED region had scoreable readings -- arm (b) not evaluated")
    lines.append(f"\nARM (a) grounds truth  (agreement >= {TRUTH_THRESHOLD}): "
                 f"{'PASS' if r['arm_a'] else 'FAIL'}")
    if r["arm_b"] is not None:
        lines.append(f"ARM (b) rejects decoy  (decoy <= {DECOY_MAX} AND gap >= {DECOY_GAP_MIN}): "
                     f"{'PASS' if r['arm_b'] else 'FAIL'}")
    lines.append(f"\nGATE: {r['verdict']}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("transcript", help="path to transcript.jsonl (stream-json from `claude -p`)")
    ap.add_argument("oracle", help="path to world/oracle.jsonl (the RAM hp oracle; scoring only)")
    args = ap.parse_args(argv)
    result = score(args.transcript, args.oracle)
    print(format_report(result))
    # 0 = a definitive verdict was computed (PASS / FAIL / DEGENERATE_CONSTANT, all decisive outcomes);
    # 1 = the run could not be scored (NO_DECLARE / INSUFFICIENT_DATA).
    return 0 if result.get("verdict") in ("PASS", "FAIL", "DEGENERATE_CONSTANT") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
