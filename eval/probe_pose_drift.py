"""Pose-DRIFT gate (measure-first, NO perceiver yet). Does the TRANSFERABLE pose -- a position
dead-reckoned by ACCUMULATING the ego-motion DIRECTION token (one unit step per move; magnitude is
deferred/unreliable) -- stay aligned with the RAM oracle as it accumulates, or drift? Run BROAD across
the 3 games that have a `--watch` oracle (gauntlet/kirby/metroid).

This is NOT Eval C. Eval C scored ego-motion DIRECTION per single step (79/98/85% camera-scrolled). This
scores ACCUMULATION over windows of growing length, two ways:
  (1) net-direction agreement -- sum the ego unit-steps and the oracle deltas over a window, do their
      dominant axes agree? If accumulation is sound this stays high as the window grows; drift/warps make
      it decay.  (2) drift ratio -- scale-normalized cumulative position error / true path length; ~0 =
      tracks, ~1+ = lost. Surfaces failure modes by camera type: gauntlet (follow,2D) cleanest; kirby
      (1D scroll -> spurious vertical) and metroid (room warps -> jumps) should break, and HOW they break
      is the finding. Per-step deltas are wrap-corrected (safe; small), so window sums never wrap.

  uv run python -m eval.probe_pose_drift
"""
from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image

from core.egomotion import direction
from eval.probe_camera_model import NH, NW, best_shift

RUNS = [   # (name, run-dir, watch->(X,Y), single-byte?)
    ("gauntlet", "2026-06-23_gauntlet_ramplay", lambda w: (w["x"], w["y"]), True),
    ("kirby",    "2026-06-23_kirby_ramplay",    lambda w: (w["scroll_x"], w["scroll_y"]), True),
    ("metroid",  "2026-06-23_metroid_ramplay",  lambda w: (w["x_scr"] * 256 + w["x_px"], w["y_scr"] * 256 + w["y_px"]), False),
]
_DIRVEC = {"east": (1, 0), "west": (-1, 0), "south": (0, 1), "north": (0, -1), "none": (0, 0)}
WINDOWS = [1, 5, 10, 20, 40]
WARP = 100   # |per-step oracle delta| above this = a scene cut / room warp, not locomotion


def _gray(p):
    return np.asarray(Image.open(p).convert("L").resize((NW, NH), Image.BILINEAR), dtype=np.float32)


def _wrapb(d):
    return ((d + 128) % 256) - 128


def _deltas(run, pf, single):
    """Per-step oracle delta (wrap-corrected) and ego unit-direction step, frame-aligned."""
    rows = [json.loads(l) for l in open(os.path.join("runs", run, "oracle.jsonl"), encoding="utf-8")]
    orad, egod = [], []
    for a, b in zip(rows, rows[1:]):
        xa, ya = pf(a["watch"]); xb, yb = pf(b["watch"])
        ddx, ddy = xb - xa, yb - ya
        if single:
            ddx, ddy = _wrapb(ddx), _wrapb(ddy)
        orad.append((ddx, ddy))
        fa = os.path.join("runs", run, f"frame_{a['step']:06d}.png")
        fb = os.path.join("runs", run, f"frame_{b['step']:06d}.png")
        if os.path.exists(fa) and os.path.exists(fb):
            _, _, dx, dy = best_shift(_gray(fa), _gray(fb))
            egod.append(_DIRVEC[direction(dx, dy)])
        else:
            egod.append((0, 0))
    return np.array(orad, float), np.array(egod, float)


def _net_dir_agreement(orad, egod, W):
    """Non-overlapping windows: does the summed ego unit-step agree with the summed oracle delta on the
    dominant oracle axis? (skip windows where the oracle barely moved.)"""
    ok = tot = 0
    for i in range(0, len(orad) - W + 1, W):
        no = orad[i:i + W].sum(0); ne = egod[i:i + W].sum(0)
        if np.abs(no).max() < 1:
            continue
        od, ed = (no[0], ne[0]) if abs(no[0]) >= abs(no[1]) else (no[1], ne[1])
        tot += 1
        ok += int(ed != 0 and (ed > 0) == (od > 0))
    return ok, tot


def main():
    print("=== POSE-DRIFT GATE - accumulated ego-direction pose vs RAM oracle (3 oracle games) ===")
    print("(1) net-direction agreement by window length W (sound accumulation => stays high as W grows)")
    for name, run, pf, single in RUNS:
        if not os.path.exists(os.path.join("runs", run, "oracle.jsonl")):
            print(f"  {name}: (no oracle)"); continue
        orad, egod = _deltas(run, pf, single)
        mags = np.hypot(orad[:, 0], orad[:, 1])
        warps = int((mags > WARP).sum())
        print(f"\n  {name}  (steps={len(orad)}, warp-steps>{WARP}px={warps})")
        cells = []
        for W in WINDOWS:
            ok, tot = _net_dir_agreement(orad, egod, W)
            cells.append(f"W={W}:{ok}/{tot}={ok / tot:.0%}" if tot else f"W={W}:-")
        print("    net-dir: " + "   ".join(cells))
        # (2) drift ratio: scale ego unit-steps to oracle units by median per-move magnitude
        k = np.median(mags[(mags > 0) & (mags <= WARP)]) if np.any((mags > 0) & (mags <= WARP)) else 1.0
        egopos = np.cumsum(egod, 0) * k
        orapos = np.cumsum(orad, 0)
        err = np.hypot(*(egopos - orapos).T)
        path = np.cumsum(mags)
        drr = "  ".join(f"{int(f*100)}%:{err[int((len(err)-1)*f)] / max(path[int((len(path)-1)*f)], 1):.2f}"
                        for f in (0.25, 0.5, 0.75, 1.0))
        print(f"    drift err/path (unit-step pose, k={k:.1f}px/move): {drr}")
    print("\nRead: net-dir HIGH and FLAT across W => accumulated heading tracks truth (transferable pose).")
    print("Decaying net-dir or drift ratio -> ~1 => accumulation breaks (warp/1D/variable-speed) = the finding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
