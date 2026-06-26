"""Cross-game avatar-localization scoring against HAND LABELS (ground truth) -- the North Eye discipline:
a primitive must prove itself across worlds, vs truth, before it ships.

For every recording with a frame_labels.json, run cheap pixel localizers over the labelled frames and score
their estimate against the human-marked `avatar` box. Reports per game:
  * full_ctr  -- per-frame whole-frame motion-centroid (rolling-median bg subtract)
  * track     -- the STATEFUL localizer we'd ship: local nearest-blob track + HOLD-when-stationary, warmed up
                 over the frames leading into each labelled frame (this is core/localize.AvatarLocalizer in spirit)
plus diagnostics: avatar on-screen SPREAD (low => follow/centred camera => screen-pos != world-pos, a different
primitive) and the fraction of motion-foreground that IS the avatar (low => avatar often stationary => motion
localization needs the hold).

  uv run python -m eval.score_localize
"""
from __future__ import annotations

import glob
import json
import os

import numpy as np
from PIL import Image

_BG, _WARM, _R, _FLOOR = 6, 16, 22.0, 60.0    # bg window, warmup frames, local-track radius, min mass to move


def _gray(p):
    return np.asarray(Image.open(p).convert("L"), np.float32) if os.path.exists(p) else None


def _centroid(fg):
    s = fg.sum()
    if s < 1e-6:
        return None
    ys, xs = np.mgrid[0:fg.shape[0], 0:fg.shape[1]]
    return np.array([float((xs * fg).sum() / s), float((ys * fg).sum() / s)])


def _local_centroid(fg, pos, r):
    ys, xs = np.mgrid[0:fg.shape[0], 0:fg.shape[1]]
    near = ((xs - pos[0]) ** 2 + (ys - pos[1]) ** 2) <= r * r
    w = fg * near
    s = w.sum()
    return (_centroid(w), float(s)) if s > 1e-6 else (None, 0.0)


def _bg_fg(frames, i):
    cur = _gray(frames[i])
    hist = [_gray(frames[j]) for j in range(max(0, i - _BG), i)]
    hist = [h for h in hist if h is not None]
    if cur is None or len(hist) < 3:
        return None, None
    return cur, np.abs(cur - np.median(np.stack(hist), axis=0))


def _full_ctr(frames, i):
    _, fg = _bg_fg(frames, i)
    return _centroid(fg) if fg is not None else None


def _track(frames, i):
    """Stateful localizer warmed up over [i-_WARM, i]: nearest-blob track, hold when no local motion."""
    pos = None
    for t in range(max(0, i - _WARM), i + 1):
        _, fg = _bg_fg(frames, t)
        if fg is None:
            continue
        if pos is None:
            pos = _centroid(fg)
        else:
            c, mass = _local_centroid(fg, pos, _R)
            if c is not None and mass >= _FLOOR:
                pos = c
    return pos


def _ctr(b):
    return np.array([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2])


def _inside(p, b):
    return b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]


def main():
    runs = sorted(d for d in glob.glob("runs/*/") if os.path.exists(os.path.join(d, "frame_labels.json")))
    print("=== avatar localization vs HAND LABELS, per game (px on 160x144; 'in-box' = estimate hits the GT box) ===\n")
    print(f"{'game':16s}{'n':>4}  {'full_ctr px':>12} {'in':>4}  {'track px':>10} {'in':>4}  "
          f"{'spread':>7}  {'avatar=mover':>12}")
    for run in runs:
        labs = [r for r in json.load(open(os.path.join(run, "frame_labels.json")))
                if r.get("avatar") and r.get("mode") == "gameplay"]
        frames = sorted(glob.glob(os.path.join(run, "frame_*.png")))
        nm = os.path.basename(os.path.normpath(run)).split("_", 1)[-1][:16]
        if not frames or len(labs) < 4:
            print(f"{nm:16s}{len(labs):>4}  (too few gameplay-avatar labels)")
            continue
        ef, et, ins_f, ins_t, fgfrac, centers = [], [], 0, 0, [], []
        for r in labs:
            i = r["frame"]
            if i >= len(frames):
                continue
            b = r["avatar"][0]
            g = _ctr(b)
            centers.append(g)
            pf, pt = _full_ctr(frames, i), _track(frames, i)
            cur, fg = _bg_fg(frames, i)
            if fg is not None:
                x0, y0, x1, y1 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
                fgfrac.append(fg[y0:y1, x0:x1].sum() / (fg.sum() + 1e-6))
            if pf is not None:
                ef.append(float(np.hypot(*(pf - g)))); ins_f += _inside(pf, b)
            if pt is not None:
                et.append(float(np.hypot(*(pt - g)))); ins_t += _inside(pt, b)
        spread = float(np.std(np.array(centers), axis=0).mean()) if centers else 0.0
        print(f"{nm:16s}{len(labs):>4}  {np.median(ef) if ef else -1:11.0f}  {ins_f/max(1,len(ef)):3.0%}  "
              f"{np.median(et) if et else -1:9.0f}  {ins_t/max(1,len(et)):3.0%}  "
              f"{spread:6.0f}  {np.median(fgfrac) if fgfrac else 0:11.0%}")
    print("\nspread = std of avatar screen-pos (LOW => follow/centred camera: localization != world-pos there).")
    print("avatar=mover = median fraction of motion-foreground inside the avatar box (LOW => often stationary).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
