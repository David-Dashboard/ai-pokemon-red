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

Alignment (transcript reading <-> oracle hp at that moment): every `remember` tool call triggers exactly
one `plugin.observe()` inside world_mcp.py (see World.call's "elif name == remember" branch), which is
IMMEDIATELY followed by that observe's own oracle.jsonl append — so the ground truth for a HYP/DECLARE/
REJECT `remember` call is the oracle record whose wall-clock timestamp is closest to that tool call's own
`tool_result` timestamp (both processes share the same host clock; oracle.jsonl logs `time.time()`,
the transcript logs an ISO `timestamp` on the tool_result message).

Usage:
    uv run python -m eval.score_gate_run runs/brain_cn_gate/transcript.jsonl runs/brain_cn_gate/world/oracle.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone

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
MIN_READINGS = 10   # a declared region with fewer readings than this = insufficient data, no verdict


def _bcd(b: int) -> int:
    return (b >> 4) * 10 + (b & 0x0F)


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _region_key(x0, y0, x1, y1) -> tuple[int, int, int, int]:
    return (int(x0), int(y0), int(x1), int(y1))


def _parse_iso(ts: str) -> float:
    # Claude's stream-json timestamps are ISO-8601 UTC with a trailing 'Z'.
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def parse_remember_calls(transcript: list[dict]) -> list[dict]:
    """Walk the transcript for `remember` tool calls; pair each `tool_use` (the `lesson` text) with its
    `tool_result`'s timestamp (when world_mcp.py answered — right after logging that observe's oracle
    record). Returns entries in transcript order: {"lesson": str, "t": float | None}."""
    pending: dict[str, str] = {}   # tool_use_id -> lesson text, awaiting its tool_result's timestamp
    out: list[dict] = []
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
                    ts = msg.get("timestamp")
                    t = _parse_iso(ts) if ts else None
                    out.append({"lesson": pending.pop(tool_use_id), "t": t})
    return out


def _nearest_oracle_hp(oracle: list[dict], t: float | None) -> int | None:
    """BCD-decoded hp of the oracle record whose wall-clock `t` is closest to the given timestamp.
    None if there's no timestamp to align on, or no oracle record carries an hp watch value."""
    if t is None:
        return None
    best = None
    best_dt = None
    for rec in oracle:
        raw = (rec.get("watch") or {}).get("hp")
        rt = rec.get("t")
        if raw is None or rt is None:
            continue
        dt = abs(rt - t)
        if best_dt is None or dt < best_dt:
            best_dt, best = dt, raw
    if best is None:
        return None
    v = _bcd(int(best))
    return v if 0 <= v <= 10 else None


def parse_transcript(transcript: list[dict], oracle: list[dict]) -> dict:
    """Extract HYP readings (per region), the DECLAREd region, and REJECTed regions + reasons, each HYP
    reading paired with the oracle hp value nearest its `remember` call's timestamp."""
    calls = parse_remember_calls(transcript)
    readings: dict[tuple, list[dict]] = {}   # region -> [{"step": n, "reading": v, "oracle_hp": h|None}]
    declared: tuple | None = None
    rejected: dict[tuple, str] = {}

    for c in calls:
        lesson = c["lesson"]
        m = _HYP_RE.search(lesson)
        if m:
            x0, y0, x1, y1, step, reading = m.groups()
            region = _region_key(x0, y0, x1, y1)
            oracle_hp = _nearest_oracle_hp(oracle, c["t"])
            readings.setdefault(region, []).append(
                {"step": int(step), "reading": float(reading), "oracle_hp": oracle_hp})
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
    """Exact-value agreement rate between a region's logged readings and the aligned oracle hp, over
    entries where the oracle value is known and in-range (same discipline as score_hud_grounding.py)."""
    agree = total = 0
    for e in entries:
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

    result: dict = {"declared": declared, "rejected": rejected, "regions_seen": sorted(readings)}

    if declared is None:
        result["verdict"] = "NO_DECLARE"
        return result

    truth_entries = readings.get(declared, [])
    truth_agree, truth_n = _agreement(truth_entries)
    result["truth_region"] = declared
    result["truth_agreement"] = truth_agree
    result["truth_readings"] = truth_n

    if truth_n < MIN_READINGS:
        result["verdict"] = "INSUFFICIENT_DATA"
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
    if r.get("declared") is None:
        lines.append("no DECLARE line found in the transcript's `remember` calls.")
        lines.append(f"regions seen (HYP only): {r.get('regions_seen')}")
        lines.append("\nVERDICT: NO_DECLARE (nothing to score)")
        return "\n".join(lines)
    lines.append(f"DECLAREd region (truth): {r['truth_region']}")
    lines.append(f"  truth agreement: {r['truth_agreement']:.3f} ({r['truth_readings']} readings)")
    if r["verdict"] == "INSUFFICIENT_DATA":
        lines.append(f"\nVERDICT: INSUFFICIENT_DATA (< {MIN_READINGS} readings for the declared region)")
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
