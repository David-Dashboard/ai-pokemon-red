"""Validate core.localize.AvatarLocalizer against the hand-label dataset, cross-game.

Drives the localizer CONTINUOUSLY over each game's frames (commanded_dir from buttons.jsonl -- the same input
the live agent has), and at every GT-labelled gameplay frame scores its output against the avatar box:
  lock%  -- of labelled frames, how often it returned a position (vs honest None)
  in-box -- of locked frames, how often the estimate falls inside the GT avatar box
  px     -- median pixel error to the GT box centre (on locked frames)
Compare against the motion-centroid baseline in eval/score_localize.py.

  uv run python -m eval.validate_localizer            # all labelled games
  uv run python -m eval.validate_localizer cavenoire  # filter by substring
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np
from PIL import Image

from core.localize import AvatarLocalizer

_DIRS = ("up", "down", "left", "right")


def _dir(bs):
    t = [b for b in (bs or []) if b in _DIRS]
    return t[-1] if t else None


def _ctr(b):
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def _inside(p, b):
    return b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]


def run_game(run):
    labs = {r["frame"]: r for r in json.load(open(os.path.join(run, "frame_labels.json")))
            if r.get("avatar") and r.get("mode") == "gameplay"}
    if len(labs) < 4:
        return None
    btn = [json.loads(l) for l in open(os.path.join(run, "buttons.jsonl"), encoding="utf-8")]
    last = max(labs)
    loc = AvatarLocalizer()
    errs, ins, locked, n = [], 0, 0, 0
    for i in range(last + 1):
        fp = os.path.join(run, f"frame_{i:06d}.png")
        if not os.path.exists(fp):
            break
        d = _dir(btn[i].get("buttons")) if i < len(btn) else None
        out = loc.update(np.asarray(Image.open(fp).convert("RGB")), d)
        if i in labs:
            n += 1
            g = _ctr(labs[i]["avatar"][0])
            if out is not None:
                locked += 1
                errs.append(float(np.hypot(out[0] - g[0], out[1] - g[1])))
                ins += _inside((out[0], out[1]), labs[i]["avatar"][0])
    return dict(n=n, lock=locked / n if n else 0, inbox=ins / locked if locked else 0,
                med=float(np.median(errs)) if errs else -1)


def main():
    filt = sys.argv[1] if len(sys.argv) > 1 else ""
    runs = sorted(d for d in glob.glob("runs/*/") if os.path.exists(os.path.join(d, "frame_labels.json"))
                  and filt in d)
    print("=== AvatarLocalizer vs hand labels (control-grounded acquire + appearance track) ===\n")
    print(f"{'game':16s}{'n':>4}  {'lock%':>6} {'in-box':>7} {'px':>6}")
    for run in runs:
        nm = os.path.basename(os.path.normpath(run)).split("_", 1)[-1][:16]
        r = run_game(run)
        if r is None:
            print(f"{nm:16s}  (too few gameplay-avatar labels)"); continue
        print(f"{nm:16s}{r['n']:>4}  {r['lock']:5.0%} {r['inbox']:6.0%} {r['med']:5.0f}")
    print("\nbaseline (motion-centroid, eval/score_localize): Cave Noire 41% in-box, others ~0-38% accidental.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
