"""Pose-DRIFT gate (measure-first, NO perceiver yet). Does the TRANSFERABLE pose -- a position
dead-reckoned by ACCUMULATING the ego-motion DIRECTION token (one unit step per move; magnitude is
deferred/unreliable) -- stay aligned with the RAM oracle as it accumulates, or drift? Run BROAD across
the 3 games that have a `--watch` oracle (gauntlet/kirby/metroid), with POKEMON as the positive control.

This is NOT Eval C. Eval C scored ego-motion DIRECTION per single step. This scores ACCUMULATION two ways:
  (1) net-direction agreement -- sum the ego unit-steps and the oracle deltas over a window, do their
      dominant axes agree? Sound accumulation stays high as the window grows; drift/warps make it decay.
      (ok/tot printed: at W=40 there are few non-overlapping windows -- read the counts, not just %.)
  (2) drift ratio -- scale-normalized cumulative position error / path length, WITHIN warp-bounded
      SEGMENTS. The scale `k` (px per move) is BORROWED from the oracle, so this is a relative
      direction-tracking check GIVEN a scale, NOT self-contained metric odometry (magnitude is deferred).
      Accumulation is RESET at every `|oracle delta|>WARP` step: at a scene cut/room-warp the oracle
      position jumps AND best_shift can't follow, so both terms corrupt -- segmenting keeps the column
      interpretable (the un-segmented version was meaningless for warp games like Metroid).

Per-step oracle deltas are wrap-corrected (safe; small), so window sums never wrap. Failure modes surface
by camera type: gauntlet (follow,2D) cleanest; kirby (1D scroll -> spurious vertical) and metroid (warps)
break, and HOW is the finding. Pokemon (always-centered camera) is the best-case anchor.

  uv run python -m eval.probe_pose_drift
"""
from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image

from core.egomotion import direction
from eval.probe_camera_model import NH, NW, best_shift

CROSS = [   # (name, run-dir, watch->(X,Y), single-byte?)
    ("gauntlet", "2026-06-23_gauntlet_ramplay", lambda w: (w["x"], w["y"]), True),
    ("kirby",    "2026-06-23_kirby_ramplay",    lambda w: (w["scroll_x"], w["scroll_y"]), True),
    ("metroid",  "2026-06-23_metroid_ramplay",  lambda w: (w["x_scr"] * 256 + w["x_px"], w["y_scr"] * 256 + w["y_px"]), False),
]
POKEMON = ["fix1", "fix2", "fix4", "fix5"]   # positive control: top-level x/y oracle, segment by map_id
_DIRVEC = {"east": (1, 0), "west": (-1, 0), "south": (0, 1), "north": (0, -1), "none": (0, 0)}
WINDOWS = [1, 5, 10, 20, 40]
WARP = 100   # |per-step oracle delta| above this = a scene cut / room warp, not locomotion


def _gray(p):
    return np.asarray(Image.open(p).convert("L").resize((NW, NH), Image.BILINEAR), dtype=np.float32)


def _wrapb(d):
    return ((d + 128) % 256) - 128


def _frame(run, step):
    return os.path.join("runs", run, f"frame_{step:06d}.png")


def _ego_step(fa, fb):
    if os.path.exists(fa) and os.path.exists(fb):
        _, _, dx, dy = best_shift(_gray(fa), _gray(fb))
        return _DIRVEC[direction(dx, dy)]
    return (0, 0)


def _cross_deltas(run, pf, single):
    rows = [json.loads(l) for l in open(os.path.join("runs", run, "oracle.jsonl"), encoding="utf-8")]
    orad, egod = [], []
    for a, b in zip(rows, rows[1:]):
        xa, ya = pf(a["watch"]); xb, yb = pf(b["watch"])
        ddx, ddy = xb - xa, yb - ya
        if single:
            ddx, ddy = _wrapb(ddx), _wrapb(ddy)
        orad.append((ddx, ddy))
        egod.append(_ego_step(_frame(run, a["step"]), _frame(run, b["step"])))
    return np.array(orad, float), np.array(egod, float)


def _pokemon_deltas(run):
    """Positive control: Pokemon's top-level x/y oracle over the LONGEST contiguous same-map,
    non-battle segment (always-centered camera = the recipe's best case)."""
    rows = [json.loads(l) for l in open(os.path.join("runs", run, "oracle.jsonl"), encoding="utf-8")]
    best, cur = [], []
    for r in rows:
        if r.get("in_battle") or (cur and r.get("map_id") != cur[-1].get("map_id")):
            if len(cur) > len(best):
                best = cur
            cur = [] if r.get("in_battle") else [r]
            continue
        cur.append(r)
    if len(cur) > len(best):
        best = cur
    orad, egod = [], []
    for a, b in zip(best, best[1:]):
        orad.append((b["x"] - a["x"], b["y"] - a["y"]))
        fa = os.path.join("runs", run, os.path.basename(a["screen_path"].replace("\\", "/")))
        fb = os.path.join("runs", run, os.path.basename(b["screen_path"].replace("\\", "/")))
        egod.append(_ego_step(fa, fb))
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


def _drift_segmented(orad, egod):
    """Cumulative position error / path length WITHIN warp-bounded segments (reset at |oracle|>WARP).
    Scale k (px/move) borrowed from the oracle => a relative tracking check, not metric odometry.
    Returns (k, path-weighted drift, n_segments, worst-segment drift) or None."""
    mags = np.hypot(orad[:, 0], orad[:, 1])
    nonwarp = mags[(mags > 0) & (mags <= WARP)]
    k = float(np.median(nonwarp)) if nonwarp.size else 1.0
    seg_err, seg_path = [], []
    e = np.zeros(2); o = np.zeros(2); path = 0.0
    for i in range(len(orad)):
        if mags[i] > WARP:                       # warp: close the segment, reset accumulation
            if path > 0:
                seg_err.append(float(np.hypot(*(e - o)))); seg_path.append(path)
            e[:] = 0; o[:] = 0; path = 0.0
            continue
        e = e + egod[i] * k; o = o + orad[i]; path += mags[i]
    if path > 0:
        seg_err.append(float(np.hypot(*(e - o)))); seg_path.append(path)
    if not seg_path:
        return None
    drift = sum(seg_err) / sum(seg_path)
    worst = max(er / pa for er, pa in zip(seg_err, seg_path))
    return k, drift, len(seg_path), worst


def _score(name, orad, egod):
    if len(orad) < 2:
        print(f"  {name}: (too few steps)"); return
    warps = int((np.hypot(orad[:, 0], orad[:, 1]) > WARP).sum())
    cells = []
    for W in WINDOWS:
        ok, tot = _net_dir_agreement(orad, egod, W)
        cells.append(f"W={W}:{ok}/{tot}={ok / tot:.0%}" if tot else f"W={W}:-")
    print(f"  {name:9s} (steps={len(orad)}, warps={warps})  net-dir: " + "  ".join(cells))
    d = _drift_segmented(orad, egod)
    if d:
        k, drift, nseg, worst = d
        print(f"    drift (warp-segmented, k={k:.1f}px/move borrowed): {drift:.2f} weighted over {nseg} seg(s) (worst {worst:.2f})")


def main():
    print("=== POSE-DRIFT GATE - accumulated ego-direction pose vs RAM oracle ===")
    print("(1) net-dir agreement by window W (read ok/tot; few windows at W=40). (2) drift = err/path WITHIN")
    print("    warp-segments, scale k BORROWED from the oracle (relative tracking, NOT metric odometry).")
    print("\n  -- positive control: Pokemon (always-centered camera; longest same-map non-battle segment) --")
    for run in POKEMON:
        if os.path.exists(os.path.join("runs", run, "oracle.jsonl")):
            o, e = _pokemon_deltas(run); _score(run, o, e)
    print("\n  -- cross-game (--watch oracle) --")
    for name, run, pf, single in CROSS:
        if os.path.exists(os.path.join("runs", run, "oracle.jsonl")):
            o, e = _cross_deltas(run, pf, single); _score(name, o, e)
    print("\nRead: net-dir HIGH and FLAT across W => accumulated heading tracks truth (transferable pose).")
    print("Decaying net-dir or high segment-drift => accumulation breaks (1D / variable-speed) = the finding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
