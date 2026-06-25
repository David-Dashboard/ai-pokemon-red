"""Score + compare MCP brain sessions from their oracle.jsonl (one run dir per model).

Each `world_mcp.py` session logs `<out>/oracle.jsonl` (RAM truth never crosses the wire; it's scoring-only):
per world-step a record with `watch` (x,y + hp) and the perceiver's `perceived` (outcome/pose/...). This
ranks runs on the metrics the project cares about — ground covered, survival, and how much of the activity
was real movement vs wall-bumps — so Opus/Sonnet/Haiku can be compared on the SAME state + task.

  uv run python -m eval.score_mcp_runs runs/mcp_opus runs/mcp_sonnet runs/mcp_haiku
  # optional labels:  ... --labels opus,sonnet,haiku
"""
from __future__ import annotations

import json
import os
import sys


def _wrap(d):
    return ((d + 128) % 256) - 128


def _score(run):
    path = os.path.join(run, "oracle.jsonl")
    if not os.path.exists(path):
        return None
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    cells, hp = set(), []
    moved = blocked = unknown = 0
    prev = None
    real_move = 0
    for r in rows:
        w = r.get("watch") or {}
        if "x" in w and "y" in w:
            cells.add((w["x"], w["y"]))
        if "hp" in w:
            hp.append(w["hp"])
        oc = (r.get("perceived") or {}).get("outcome")
        if oc == "moved":
            moved += 1
            # confirm a "move" against RAM position ONLY when both rows carry x/y — defaulting a missing coord to
            # 0 (e.g. a game whose watch omits position) would fabricate a displacement and count a non-move (B5).
            if prev and {"x", "y"} <= w.keys() and {"x", "y"} <= prev.keys() and \
                    (abs(_wrap(w["x"] - prev["x"])) + abs(_wrap(w["y"] - prev["y"]))) != 0:
                real_move += 1
        elif oc == "blocked":
            blocked += 1
        elif oc == "unknown":
            unknown += 1
        if w:
            prev = w
    # damage = HP decrease between consecutive VALID readings. Filter readings above the display max first (those
    # are the transient transition spikes — see the Phase A report, F3) instead of bounding the delta with a magic
    # number. NOTE: transition-confounded HP drops are NOT separated here — that's the open gate problem (Check 2),
    # deliberately not hidden inside the scorer. _MAX_HP is Cave Noire's displayed max.
    _MAX_HP = 10
    clean = [v for v in hp if v <= _MAX_HP]
    dmg = sum(1 for a, b in zip(clean, clean[1:]) if b < a)
    return {
        "steps": len(rows),
        "cells": len(cells),                 # distinct ground-truth tiles visited (RAM) = exploration coverage
        "moved": moved, "blocked": blocked, "unknown": unknown,
        "move_eff": (real_move / moved) if moved else 0.0,   # of perceiver-"moves", how many were RAM-real
        "wall_rate": (blocked / (moved + blocked)) if (moved + blocked) else 0.0,
        "hp_first": hp[0] if hp else None, "hp_last": hp[-1] if hp else None,
        "hp_min": min(hp) if hp else None, "damage_events": dmg,
    }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    labels = None
    if "--labels" in sys.argv:
        labels = sys.argv[sys.argv.index("--labels") + 1].split(",")
    runs = args
    labels = labels or [os.path.basename(r.rstrip("/\\")) for r in runs]
    print("=== MCP brain-session comparison (same state + task; RAM = scoring oracle, never an input) ===")
    hdr = f"{'model':14s} {'cells':>6s} {'steps':>6s} {'moved':>6s} {'blocked':>8s} {'wall%':>6s} {'real-move%':>11s} {'hp end/min':>11s} {'dmg':>4s}"
    print(hdr); print("-" * len(hdr))
    for run, lab in zip(runs, labels):
        s = _score(run)
        if s is None:
            print(f"{lab:14s}  (no oracle.jsonl at {run})"); continue
        print(f"{lab:14s} {s['cells']:6d} {s['steps']:6d} {s['moved']:6d} {s['blocked']:8d} "
              f"{s['wall_rate']:5.0%} {s['move_eff']:10.0%} {str(s['hp_last'])+'/'+str(s['hp_min']):>11s} {s['damage_events']:4d}")
    print("\ncells = distinct tiles covered (more = better exploration) · wall% = share of move-attempts that")
    print("were walls (lower = less flailing) · real-move% = of perceiver-'moves', how many RAM-confirmed.")
    print("Live cost metric (cells per DECISION/LLM-wake) is shown in-session by the brain; add a decisions")
    print("log to oracle if you want it offline. This table ranks coverage + survival + move-efficiency.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
