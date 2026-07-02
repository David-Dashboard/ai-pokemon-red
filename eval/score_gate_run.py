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

_HYP_RE = re.compile(
    r"HYP\s+region=\((-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\)\s+step=(-?\d+)\s+reading=(-?\d+(?:\.\d+)?)"
)
_DECLARE_RE = re.compile(r"DECLARE\s+life=\((-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\)")
_REJECT_RE = re.compile(r"REJECT\s+region=\((-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\)\s+reason=(.*)")

TRUTH_THRESHOLD = 0.90
DECOY_MAX = 0.50
DECOY_GAP_MIN = 0.30
MIN_READINGS = 10           # a declared region with fewer readings than this = insufficient data, no verdict
UNMATCHED_MAX_FRACTION = 0.05   # unmatched HYP steps must stay STRICTLY below this fraction of all lines


def _bcd(b: int) -> int:
    return (b >> 4) * 10 + (b & 0x0F)


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _region_key(x0, y0, x1, y1) -> tuple[int, int, int, int]:
    return (int(x0), int(y0), int(x1), int(y1))


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
    reading is aligned to the oracle row with the EXACT same step (matched=False if no such row)."""
    lessons = parse_remember_calls(transcript)
    hp_by_step = _oracle_hp_by_step(oracle)
    readings: dict[tuple, list[dict]] = {}   # region -> [{"step", "reading", "oracle_hp", "matched"}]
    declared: tuple | None = None
    rejected: dict[tuple, str] = {}

    for lesson in lessons:
        m = _HYP_RE.search(lesson)
        if m:
            x0, y0, x1, y1, step, reading = m.groups()
            region = _region_key(x0, y0, x1, y1)
            step = int(step)
            matched = step in hp_by_step
            readings.setdefault(region, []).append(
                {"step": step, "reading": float(reading),
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

    return {"readings": readings, "declared": declared, "rejected": rejected}


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


def score(transcript_path: str, oracle_path: str) -> dict:
    transcript = load_jsonl(transcript_path)
    oracle = load_jsonl(oracle_path)
    parsed = parse_transcript(transcript, oracle)
    readings, declared, rejected = parsed["readings"], parsed["declared"], parsed["rejected"]

    all_entries = [e for entries in readings.values() for e in entries]
    n_hyp = len(all_entries)
    n_unmatched = sum(1 for e in all_entries if not e["matched"])
    result: dict = {"declared": declared, "rejected": rejected, "regions_seen": sorted(readings),
                    "hyp_lines": n_hyp, "unmatched_lines": n_unmatched}

    if declared is None:
        result["verdict"] = "NO_DECLARE"
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
    if r["verdict"] == "INSUFFICIENT_DATA":
        lines.append(f"\nVERDICT: INSUFFICIENT_DATA ({r.get('reason')})")
        return "\n".join(lines)
    if r.get("decoy_region") is not None:
        lines.append(f"best-scoring REJECTED (decoy): {r['decoy_region']} "
                     f"reason={r['rejected'].get(r['decoy_region'])!r}")
        lines.append(f"  decoy agreement: {r['decoy_agreement']:.3f} ({r['decoy_readings']} readings)")
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
    return 0 if result.get("verdict") in ("PASS", "FAIL") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
