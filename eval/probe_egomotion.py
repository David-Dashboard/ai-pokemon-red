"""P1 — 2D EGO-MOTION probe: does the game-agnostic `best_shift` recover SELF-MOTION DIRECTION from pixels only
(no RAM at inference)? This is the measure-first step for the generalizable ego-motion estimator (the System-1
"how did I move" sense). Two evals, both direction-recovery (sign), not metric distance (which the camera-model
probe showed is unreliable):

  A. RAM GROUND-TRUTH (Pokemon Gen-1 overworld; the only corpus with a position oracle): on same-map, non-battle
     steps where RAM (x,y) actually moved, does best_shift's (dx,dy) point the way the avatar moved?
     Camera-follow convention: east(+x) -> +dx, south(+y) -> +dy. RAM is the oracle, never an input.
  B. BUTTON-GROUNDING (cross-game 2D-scroll camera runs, NO RAM): does each pressed direction produce the
     expected, consistent camera shift? right->+dx, left->-dx, down->+dy, up->-dy. (Generalization signal.)

numpy+PIL, main uv env.  uv run python -m eval.probe_egomotion
"""
from __future__ import annotations

import glob
import json
import os

import numpy as np
from PIL import Image

from eval.probe_camera_model import NH, NW, MOVE_EPS, _GB_DIR, best_shift, load_run

ORACLE_RUNS = ["fix1", "fix2", "fix3", "fix4", "fix5", "explore_bench"]   # Pokemon Gen-1: RAM x/y/map_id oracle
SCROLL_RUNS = [   # 2D-scroll camera-corpus dev runs (button-grounded; no position oracle)
    ("2026-06-23_gold_explore", "follow_scroll"),
    ("2026-06-23_gauntlet_play", "follow_scroll"),
    ("2026-06-23_kirby_play", "scroll_side"),
    ("2026-06-23_metroid_play", "scroll_side"),
]


def _gray(path):
    return np.asarray(Image.open(path).convert("L").resize((NW, NH), Image.BILINEAR), dtype=np.float32)


def _oracle_frame(run, row):
    return os.path.join("runs", run, os.path.basename(row["screen_path"].replace("\\", "/")))


def ram_truth():
    print("=== A. RAM GROUND-TRUTH (Pokemon Gen-1 overworld; est. camera-shift direction vs RAM (x,y) move) ===")
    print("  east(+x)->+dx, south(+y)->+dy.  miss includes 'camera pinned' (RAM moved but best_shift=0).")
    tot_ok = tot = 0
    for run in ORACLE_RUNS:
        path = os.path.join("runs", run, "oracle.jsonl")
        if not os.path.exists(path):
            continue
        rows = [json.loads(l) for l in open(path, encoding="utf-8")]
        ok = n = 0
        for a, b in zip(rows, rows[1:]):
            if a.get("map_id") != b.get("map_id") or a.get("in_battle") or b.get("in_battle"):
                continue
            ddx, ddy = b.get("x", 0) - a.get("x", 0), b.get("y", 0) - a.get("y", 0)
            if ddx == 0 and ddy == 0:
                continue
            fa, fb = _oracle_frame(run, a), _oracle_frame(run, b)
            if not (os.path.exists(fa) and os.path.exists(fb)):
                continue
            _, _, dx, dy = best_shift(_gray(fa), _gray(fb))
            # Score the DOMINANT RAM axis only (overworld moves are ~cardinal); a near-diagonal whose MINOR
            # axis sign is wrong still counts correct -- fine for 4-directional movement, stated for honesty.
            if abs(ddx) >= abs(ddy):                       # dominant axis = horizontal
                correct = dx != 0 and (dx > 0) == (ddx > 0)
            else:                                          # vertical
                correct = dy != 0 and (dy > 0) == (ddy > 0)
            ok += int(correct)
            n += 1
        if n:
            print(f"  {run:13s} n={n:4d}  direction-recovery={ok / n:.0%}")
            tot_ok += ok
            tot += n
    if tot:
        print(f"  AGGREGATE: {tot_ok}/{tot} = {tot_ok / tot:.0%}  (camera-shift direction matches RAM movement)")


def button_grounding():
    print("\n=== B. BUTTON-GROUNDING (cross-game 2D-scroll; NO RAM; CLEAN scrolls only, residual<0.7) ===")
    print("  per pressed direction: mean (dx,dy). recover = right->+dx left->-dx down->+dy up->-dy.")
    print("  side-scrollers are scored on LEFT/RIGHT only (vertical is not camera motion in a side-scroller).")
    exp = {"right": ("x", 1), "left": ("x", -1), "down": ("y", 1), "up": ("y", -1)}
    scored = {"follow_scroll": ["right", "left", "down", "up"], "scroll_side": ["right", "left"]}
    for run, cls in SCROLL_RUNS:
        if not glob.glob(os.path.join("runs", run, "frame_*.png")):
            continue
        trans = load_run(run, "gb")
        per = {d: [] for d in _GB_DIR}
        for t in trans:
            f = t["feats"]
            if f["frame_diff"] <= MOVE_EPS or f["residual"] >= 0.7:   # only CLEAN rigid scrolls (a real pan)
                continue
            for d in _GB_DIR:
                if d in t["buttons"]:
                    per[d].append((f["shift_x"], f["shift_y"]))
        rec = ndir = 0
        cells = []
        for d in scored.get(cls, list(exp)):
            axis, sgn = exp[d]
            v = per[d]
            if len(v) < 5:
                cells.append(f"{d}:n<5")
                continue
            mx, my = float(np.mean([s[0] for s in v])), float(np.mean([s[1] for s in v]))
            val, other = (mx, my) if axis == "x" else (my, mx)
            good = (val > 0) == (sgn > 0) and abs(val) > abs(other)
            rec += int(good)
            ndir += 1
            cells.append(f"{d}:({mx:+.1f},{my:+.1f}){'OK' if good else 'X'}")
        score = f"{rec}/{ndir}" if ndir else "n/a (too few clean scrolls)"
        print(f"  {run.split('_')[1]:9s} [{cls:13s}] recover {score}   " + "  ".join(cells))


def main():
    ram_truth()
    button_grounding()
    print("\nReads: A = true odometry direction accuracy (RAM-grounded, Pokemon); B = cross-game generalization")
    print("of the same cue with no RAM. Both are DIRECTION (sign), not metric distance (deferred).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
