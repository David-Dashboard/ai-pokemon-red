#!/usr/bin/env python
"""tools/smoke_sweep_report.py — render the smoke-sweep JSONL (tools/smoke_sweep.py) as a Markdown table.

Verdicts (infrastructure triage, not science):
  broken   — didn't boot, or died with an exception.
  degraded — booted but the output looks unhealthy: frozen/black screen (screen_variety <= 1),
             no observations, or well under the expected frame count (title never cleared / stalled).
  runnable — boots, screen changes, perceiver observed — a candidate for paid probes.

Stdlib only; CI-safe (no emulator, no ROM).
"""
from __future__ import annotations

import argparse
import json
import sys

# A full run is ~300 mash + ~900 observed frames; anything under the observed phase alone means the
# game stalled early (or a per-game timeout cut it) — degraded, worth a look before paying for it.
MIN_HEALTHY_FRAMES = 900

COLUMNS = ("game", "console", "boot", "frames", "variety", "entities", "verdict", "note")


def load_records(path: str) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def verdict(rec: dict) -> str:
    if rec.get("exception") or not rec.get("boot_ok"):
        return "broken"
    if (rec.get("screen_variety", 0) <= 1 or rec.get("n_observations", 0) == 0
            or rec.get("frames_advanced", 0) < MIN_HEALTHY_FRAMES):
        return "degraded"
    return "runnable"


def _note(rec: dict) -> str:
    if rec.get("exception"):
        e = rec["exception"]
        return f"{e.get('type', '?')}: {e.get('msg', '')[:60]}"
    bits = []
    if rec.get("timeout"):
        bits.append("timeout")
    if rec.get("registered_game"):
        bits.append(f"registered={rec['registered_game']}")
    if verdict(rec) == "degraded" and rec.get("screen_variety", 0) <= 1:
        bits.append("frozen/black screen")
    return "; ".join(bits)


def _row(rec: dict) -> list[str]:
    ents = rec.get("entities_seen_median")
    return [rec.get("game", "?"), rec.get("console", "?"),
            "yes" if rec.get("boot_ok") else "no",
            str(rec.get("frames_advanced", 0)), str(rec.get("screen_variety", 0)),
            "-" if ents is None else f"{ents:g}", verdict(rec), _note(rec)]


def render_markdown(records: list[dict]) -> str:
    rows = [_row(r) for r in sorted(records, key=lambda r: (r.get("console") or "", r.get("game") or ""))]
    lines = ["| " + " | ".join(COLUMNS) + " |",
             "|" + "|".join("---" for _ in COLUMNS) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    counts = {v: sum(1 for r in records if verdict(r) == v) for v in ("runnable", "degraded", "broken")}
    lines.append("")
    lines.append(f"**{len(records)} games: {counts['runnable']} runnable, "
                 f"{counts['degraded']} degraded, {counts['broken']} broken.**")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Markdown report for a smoke-sweep JSONL.")
    ap.add_argument("jsonl", help="path to the sweep's JSONL output")
    ap.add_argument("--out", default=None, help="write the table here (else stdout)")
    args = ap.parse_args()
    md = render_markdown(load_records(args.jsonl))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md + "\n")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
