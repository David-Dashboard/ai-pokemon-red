"""Scaffold a per-run report from a run's OWN artifacts — so the numbers are oracle-grounded and a
report skeleton ALWAYS exists after a run (no hand-counting, nothing to forget).

It reads `runs/run<ID>/oracle.jsonl` (the RAM oracle — control/scoring only, never an agent input) and
the sibling `runs/run<ID>_console.log`, computes the verified facts (battle outcome incl. a sustained-
win check, map trajectory, wake / auto-advance / error counts, the episode-summary line), and writes
`reports/<date>-live-run-<ID>[-<slug>].md` pre-filled with those facts + `TODO:` placeholders for the
narrative. Then it prints the per-run Definition-of-Done (the other md files to update).

Usage:
    uv run python -m eval.report_run runs/run13 --title "battle auto-advance" --cost "~$0.18"
    uv run python -m eval.report_run runs/run6b              # title/slug optional

Pure helpers (`extract_facts`, `render_report`) are unit-tested in tests/test_report_run.py.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
from typing import Optional

# --- pure fact extraction (unit-tested; no I/O) ------------------------------------------------

def _battle_outcome(in_battle: list, hold: int = 10):
    """('won', exit_idx) if in_battle goes nonzero->0 and STAYS 0 for >= `hold` rows (a real clear,
    not a 1-frame RAM blip — the run #8 over-claim); ('in-battle-at-cap', None) if it ends mid-fight;
    ('no-battle', None) if no battle ever started."""
    started = any(v not in (0, None) for v in in_battle)
    if not started:
        return ("no-battle", None)
    i = len(in_battle)
    while i > 0 and in_battle[i - 1] == 0:   # walk back over the trailing run of zeros
        i -= 1
    trailing = len(in_battle) - i
    if trailing >= hold and i > 0:
        return ("won", i)                    # exit at index i (where in_battle became 0), sustained
    return ("in-battle-at-cap", None)


def _trajectory(maps: list) -> list:
    out: list = []
    for m in maps:
        if m is not None and (not out or out[-1] != m):
            out.append(m)
    return out


def extract_facts(oracle_rows: Optional[list], log_text: Optional[str]) -> dict:
    """Compute the verified per-run facts from the oracle rows + console-log text. Both optional."""
    f: dict = {"has_oracle": bool(oracle_rows), "has_log": log_text is not None}

    if oracle_rows:
        ib = [r.get("in_battle") for r in oracle_rows]
        maps = [r.get("map_id") for r in oracle_rows]
        lvl = [r.get("party_level_sum") for r in oracle_rows]
        bdg = [r.get("badges") for r in oracle_rows]
        outcome, exit_idx = _battle_outcome(ib)
        f.update(
            rows=len(oracle_rows),
            in_battle_start=ib[0] if ib else None,
            in_battle_values=sorted({v for v in ib if v is not None}),
            outcome=outcome,
            exit_step=exit_idx,
            maps_seen=sorted({m for m in maps if m is not None}),
            trajectory=_trajectory(maps),
            level_start=lvl[0] if lvl else None,
            level_end=lvl[-1] if lvl else None,
            badges_start=bdg[0] if bdg else None,
            badges_end=bdg[-1] if bdg else None,
        )

    if log_text is not None:
        wakes = advs = 0
        wake_steps: list = []
        cur = None
        for line in log_text.splitlines():
            m = re.match(r"\s*\[(\d+)\]", line)
            if m:
                cur = int(m.group(1))
            if "think: [wake" in line:
                wakes += 1
                wake_steps.append(cur)
            elif "think: [auto-advance" in line:
                advs += 1
        f["wakes"] = wakes
        f["auto_advances"] = advs
        f["errors"] = len(re.findall(r"credit balance|Traceback|\b400\b", log_text))
        # battle wakes = wakes before the sustained battle exit (the headline cost metric)
        ex = f.get("exit_step")
        if ex is not None and wake_steps:
            f["battle_wakes"] = sum(1 for s in wake_steps if s is not None and s < ex)
        # the play_pokemon.py episode-summary line, if the run ended cleanly
        m = re.search(r"llm_woke:\s*(\d+)/(\d+)\s*steps\s*\(([\d.]+)%\)", log_text)
        if m:
            f["summary_woke"], f["summary_steps"], f["summary_wake_pct"] = (
                int(m.group(1)), int(m.group(2)), float(m.group(3)))
        m = re.search(r"total_reward:\s*([\-\d.]+)", log_text)
        if m:
            f["total_reward"] = float(m.group(1))
    return f


# --- rendering (unit-tested) -------------------------------------------------------------------

_OUTCOME_TXT = {
    "won": "**WON** — `in_battle` 2→0 sustained",
    "in-battle-at-cap": "did NOT win — ended mid-battle (cap/halt/crash)",
    "no-battle": "no battle this run",
}


def render_report(facts: dict, meta: dict) -> str:
    """Compose the markdown report (verified facts filled; narrative left as TODO)."""
    rid = meta["run_id"]
    title = meta.get("title") or "TODO one-line title"
    out = _OUTCOME_TXT.get(facts.get("outcome", ""), "TODO")
    if facts.get("outcome") == "won" and facts.get("exit_step") is not None:
        out += f" at step {facts['exit_step']}"

    def row(k, v):
        return f"| {k} | {v} |"

    traj = "→".join(str(m) for m in facts.get("trajectory", [])) or "TODO"
    bw = facts.get("battle_wakes")
    wakes_cell = str(facts.get("wakes", "TODO"))
    if bw is not None:
        wakes_cell += f" ({bw} in battle)"
    lines = [
        f"# Live run #{rid} — {title} ({meta['date']})",
        "",
        "_TODO: one-line companion note (what this run tested, what it follows from)._",
        "",
        "**TL;DR — TODO.**",
        "",
        "## Config",
        "```",
        meta.get("config") or "TODO: the play_pokemon.py / play_loop.py command + flags",
        "```",
        f"Clean start: `reset_aria_memory.py --yes` (archive `{meta.get('archive', 'iter-???')}`).",
        "",
        "## Results (oracle-verified — auto-extracted; do not hand-edit the numbers)",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        row("Outcome", out),
    ]
    if facts.get("has_oracle"):
        lines += [
            row("`in_battle`", f"start {facts.get('in_battle_start')}, values {facts.get('in_battle_values')}, "
                              f"sustained-exit @ {facts.get('exit_step') if facts.get('exit_step') is not None else '—'}"),
            row("Maps (trajectory)", traj),
            row("Maps seen", facts.get("maps_seen")),
            row("Oracle rows (steps)", facts.get("rows")),
            row("Party level (start/end)", f"{facts.get('level_start')} / {facts.get('level_end')}"),
            row("Badges (start/end)", f"{facts.get('badges_start')} / {facts.get('badges_end')}"),
        ]
    else:
        lines.append(row("Oracle", "(none found — fill manually)"))
    if facts.get("has_log"):
        lines += [
            row("LLM wakes", wakes_cell),
            row("Auto-advances (free)", facts.get("auto_advances")),
            row("Errors (400 / crash / credit)", facts.get("errors")),
        ]
        if "summary_woke" in facts:
            lines.append(row("Episode summary", f"{facts['summary_woke']}/{facts['summary_steps']} wakes "
                                                f"({facts['summary_wake_pct']}%)"
                                                + (f", reward {facts['total_reward']}" if 'total_reward' in facts else "")))
    else:
        lines.append(row("Console log", "(none found — fill manually)"))
    lines += [
        row("Cost", meta.get("cost") or "TODO"),
        "",
        "## What worked — TODO",
        "",
        "## What broke / the new bottleneck — TODO",
        "",
        "## Next — TODO",
        "",
        "---",
        f"_Artifacts: video `runs/run{rid}.mp4`; oracle `runs/run{rid}/oracle.jsonl`; "
        f"archive `{meta.get('archive', 'iter-???')}`._",
        "",
        "<!-- DEFINITION OF DONE — after filling the TODOs above, also update: (2) reports/LEARNINGS.md "
        "(a dated bullet), (3) HANDOFF.md §2 status + NEXT, (4) memory/current-status.md. -->",
        "",
    ]
    return "\n".join(lines)


# --- CLI ---------------------------------------------------------------------------------------

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def _read_oracle(run_dir: str):
    p = os.path.join(run_dir, "oracle.jsonl")
    if not os.path.exists(p):
        return None
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def _read_log(path: str):
    if not path or not os.path.exists(path):
        return None
    return open(path, encoding="utf-8", errors="replace").read()   # logs carry the odd cp1252 byte


def main() -> int:
    ap = argparse.ArgumentParser(description="Scaffold a per-run report from the run's own artifacts.")
    ap.add_argument("run_dir", help="the run's output dir, e.g. runs/run13")
    ap.add_argument("--run-id", default=None, help="override the run id (default: trailing chars of run_dir)")
    ap.add_argument("--log", default=None, help="console log path (default: <run_dir>_console.log)")
    ap.add_argument("--title", default="", help="short title for the report header + filename slug")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument("--config", default=None, help="the command/flags used (filled into the report)")
    ap.add_argument("--cost", default=None, help="cost estimate, e.g. '~$0.18'")
    ap.add_argument("--archive", default=None, help="memory archive name, e.g. iter-013_2026-06-20.zip")
    ap.add_argument("--out", default=None, help="output path (default: reports/<date>-live-run-<id>[-<slug>].md)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing report")
    args = ap.parse_args()

    run_dir = args.run_dir.rstrip("/\\")
    base = os.path.basename(run_dir)
    rid = args.run_id or (re.search(r"(\d+\w*)$", base).group(1) if re.search(r"(\d+\w*)$", base) else base)
    log_path = args.log or f"{run_dir}_console.log"
    date = args.date or datetime.date.today().isoformat()

    facts = extract_facts(_read_oracle(run_dir), _read_log(log_path))
    meta = {"run_id": rid, "title": args.title, "date": date, "config": args.config,
            "cost": args.cost, "archive": args.archive}
    report = render_report(facts, meta)

    out = args.out
    if out is None:
        slug = _slug(args.title)
        out = os.path.join("reports", f"{date}-live-run-{rid}" + (f"-{slug}" if slug else "") + ".md")
    if os.path.exists(out) and not args.force:
        print(f"[report_run] {out} already exists — pass --force to overwrite. Facts:\n")
        print(report)
        return 1
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(report)

    print(f"[report_run] wrote {out}")
    print(f"[report_run] outcome={facts.get('outcome')} wakes={facts.get('wakes')} "
          f"battle_wakes={facts.get('battle_wakes')} advances={facts.get('auto_advances')} "
          f"errors={facts.get('errors')} rows={facts.get('rows')}")
    print("\n[report_run] DEFINITION OF DONE — now finish the iteration's docs:")
    print(f"  1. Fill the TODO sections in {out} (TL;DR / what worked / broke / next).")
    print("  2. Add a dated bullet to reports/LEARNINGS.md.")
    print("  3. Update HANDOFF.md §2 (LATEST status + NEXT).")
    print("  4. Update the memory/current-status.md pointer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
