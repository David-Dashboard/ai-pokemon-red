#!/usr/bin/env python
"""tools/probe_report.py — render probe_ledger.jsonl (+ each probe's transcript.jsonl) as a Markdown
table for the sweep report: game, PROBE verdict line, cost, gaps.

Reads the ledger written by tools/run_probe_queue.sh (tools/probe_queue_lib.ledger_row) and, per slug,
its transcript.jsonl at runs/probe_<slug>/transcript.jsonl to pull out the brain's own closing
`PROBE verdict=<...> gaps=<...>` self-report line (tools/make_probe_launcher.py's fixed brief format).

Stdlib only; CI-safe (works over synthetic ledger + transcript fixtures, no docker/ROM/network).
"""
from __future__ import annotations

import argparse
import json
import os
import re

_PROBE_LINE = re.compile(r"PROBE\s+verdict=(\S+)\s+gaps=(.*)")

COLUMNS = ("game", "verdict", "cost_usd", "gaps", "exit", "duration_s")


def load_ledger(path: str) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def parse_probe_line(transcript_path: str) -> tuple[str | None, str | None]:
    """(verdict, gaps) from the LAST `PROBE verdict=... gaps=...` line found in the transcript's
    tool_result/assistant text blocks; (None, None) if the file is missing or no such line was logged."""
    verdict = gaps = None
    try:
        with open(transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return None, None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        for block in (msg.get("message") or {}).get("content") or []:
            text = block.get("text") if isinstance(block, dict) else None
            if not text:
                continue
            m = _PROBE_LINE.search(text)
            if m:
                verdict, gaps = m.group(1).strip(), m.group(2).strip()
    return verdict, gaps


def _row(rec: dict, runs_root: str) -> list[str]:
    slug = rec.get("slug", "?")
    transcript_path = os.path.join(runs_root, f"probe_{slug}", "transcript.jsonl")
    verdict, gaps = parse_probe_line(transcript_path)
    cost = rec.get("cost")
    return [slug, verdict or "-", "-" if cost is None else f"{cost:.2f}", gaps or "-",
            str(rec.get("exit", "-")), str(rec.get("duration", "-"))]


def render_markdown(records: list[dict], runs_root: str) -> str:
    rows = [_row(r, runs_root) for r in sorted(records, key=lambda r: r.get("slug", ""))]
    lines = ["| " + " | ".join(COLUMNS) + " |",
             "|" + "|".join("---" for _ in COLUMNS) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    lines.append("")
    lines.append(f"**{len(records)} probe(s).**")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Markdown report for a probe run's ledger + transcripts.")
    ap.add_argument("ledger", help="path to runs/probe_ledger.jsonl")
    ap.add_argument("--runs-root", default=None,
                    help="dir containing probe_<slug>/ launcher dirs (default: ledger's own dir)")
    ap.add_argument("--out", default=None, help="write the table here (else stdout)")
    args = ap.parse_args()
    runs_root = args.runs_root or os.path.dirname(os.path.abspath(args.ledger))
    md = render_markdown(load_ledger(args.ledger), runs_root)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md + "\n")
        print(f"wrote {args.out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
