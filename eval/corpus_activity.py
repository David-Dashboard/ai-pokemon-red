"""Corpus activity / readiness gate for the cross-game DEV corpus (FREE; numpy+PIL; DEV-only).

For each recorded run it reports how much of the capture is ACTIVE gameplay vs static (title/paused) vs
menu, using the world-agnostic core/modality detector. A capture dominated by static/menu frames is THIN
(the random policy never got into the game); a capture with substantial active gameplay is READY to
develop odometry on.

This is ALSO the honest end-to-end PROOF that --smart-auto works: record the same game from the same
cold boot with and without --smart-auto and compare the active% rows here — smart-auto should reach
gameplay (higher active%) where pure random stays stuck on the title.

  uv run python -m eval.corpus_activity                         # all DEV runs/* with buttons.jsonl
  uv run python -m eval.corpus_activity runs/kirby_auto1 ...    # specific runs
  uv run python -m eval.corpus_activity --max-frames 1500       # cap per run for a fast pass
  uv run python -m eval.corpus_activity --anchor runs/kanto1    # detector vs Pokemon context (oracle.jsonl)

Held-out runs are filtered out (we never tune on them — eval/dataset_split.py).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from collections import Counter, defaultdict

import numpy as np
from PIL import Image

from core.modality import detect_modality
from eval.dataset_split import partition

# Orientation thresholds for the READY/THIN verdict (these gate DATA sufficiency; they do NOT tune the
# detector). A run needs a real chunk of gameplay frames to be worth developing odometry on.
MIN_ACTIVE_FRAMES = 500
MIN_ACTIVE_FRAC = 0.30


def _load_frame(path):
    return np.asarray(Image.open(path).convert("RGB"))


def run_modes(run: str, max_frames: int = 0):
    """Per-step modality labels for a raw run (buttons.jsonl + frames). buttons[i] caused frame i."""
    rows = [json.loads(l) for l in open(os.path.join(run, "buttons.jsonl"), encoding="utf-8")]
    if max_frames:
        rows = rows[:max_frames]
    labels, prev = [], None
    for r in rows:
        f = _load_frame(r["screen_path"])
        lab, _ = detect_modality(prev, f, r.get("buttons"))
        labels.append(lab)
        prev = f
    return labels


def _longest_streak(labels, target="gameplay"):
    best = cur = 0
    for l in labels:
        cur = cur + 1 if l == target else 0
        best = max(best, cur)
    return best


def summarize(run: str, labels):
    n = len(labels)
    c = Counter(labels)
    gp = c.get("gameplay", 0)
    active = gp / n if n else 0.0
    ready = gp >= MIN_ACTIVE_FRAMES and active >= MIN_ACTIVE_FRAC
    return {
        "run": os.path.basename(run), "n": n,
        "active": active,
        "static": c.get("static", 0) / n if n else 0.0,
        "menu": c.get("menu", 0) / n if n else 0.0,
        "streak": _longest_streak(labels),
        "verdict": "READY" if ready else "THIN",
    }


def anchor(run: str, max_frames: int = 0):
    """Validate the world-agnostic detector against the Pokemon perceiver's context (the labeled anchor:
    the one game where we have a per-frame mode label + RAM truth)."""
    rows = [json.loads(l) for l in open(os.path.join(run, "oracle.jsonl"), encoding="utf-8")]
    if max_frames:
        rows = rows[:max_frames]
    prev = None
    ctx_label = defaultdict(Counter)
    ov_moved = Counter()
    for r in rows:
        p = r.get("perceived") or {}
        ctx, outcome, action = p.get("context"), p.get("outcome"), p.get("action")
        f = _load_frame(r["screen_path"])
        lab, _ = detect_modality(prev, f, [action] if action else None)
        prev = f
        if ctx is None:
            continue
        ctx_label[ctx][lab] += 1
        if ctx == "overworld" and outcome == "moved":
            ov_moved[lab] += 1
    print(f"\nanchor: {run}  (world-agnostic detector vs Pokemon perceiver context)")
    for ctx, c in sorted(ctx_label.items(), key=lambda kv: -sum(kv[1].values())):
        tot = sum(c.values())
        notgp = (tot - c.get("gameplay", 0)) / tot if tot else 0.0
        print(f"  {ctx:11s} n={tot:5d}  not-gameplay={notgp:4.0%}  {dict(c)}")
    m = sum(ov_moved.values())
    if m:
        print(f"  overworld+MOVED gameplay-rate={ov_moved.get('gameplay', 0) / m:.0%} (n={m})  "
              f"<- the meaningful agreement: real locomotion reads as gameplay")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*", help="run dirs (default: all DEV runs/* with buttons.jsonl)")
    ap.add_argument("--max-frames", type=int, default=0, help="cap frames per run (0 = all)")
    ap.add_argument("--anchor", default="", help="a Pokemon run with oracle.jsonl: validate detector vs context")
    args = ap.parse_args()

    if args.anchor:
        anchor(args.anchor, args.max_frames)
        return

    runs = args.runs or sorted(os.path.dirname(p) for p in glob.glob("runs/*/buttons.jsonl"))
    runs = [r.replace("\\", "/") for r in runs]
    dev, held = partition(runs)
    if held:
        print(f"(skipping {len(held)} held-out run(s): {[os.path.basename(h) for h in held]})")
    if not dev:
        print("no DEV runs with buttons.jsonl found.")
        return

    print(f"\n{'run':24} {'frames':>7} {'active%':>8} {'static%':>8} {'menu%':>6} {'maxRun':>7}  verdict")
    for run in dev:
        s = summarize(run, run_modes(run, args.max_frames))
        print(f"{s['run']:24} {s['n']:>7} {s['active']:>8.0%} {s['static']:>8.0%} "
              f"{s['menu']:>6.0%} {s['streak']:>7}  {s['verdict']}")
    print("\nREADY = enough ACTIVE gameplay frames to develop odometry on; THIN = stuck on title/menu "
          "(needs --smart-auto or a fallback).\nProof of menu-handling: compare a game's random vs "
          "--smart-auto rows — smart-auto should lift active% from the same cold boot.")


if __name__ == "__main__":
    main()
