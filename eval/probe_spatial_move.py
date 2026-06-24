"""Spatial-move probe (adversarial test of David's grid/CNN idea for the false-MOVE fix).

The whole-frame residual can't separate a real move from a stuck-flicker (they overlap in MAGNITUDE).
Hypothesis (David): don't measure how MUCH the screen changed, measure WHERE — a real move shifts the
player sprite to an adjacent location; idle flicker (torches/enemies) toggles in place. So test signals
that localize change instead of averaging it:
  (A) grid max-cell change   -- a sprite move spikes ONE cell even if the whole-frame mean is tiny
  (B) foreground-centroid SHIFT projected on the commanded direction -- background-subtract (rolling
      median kills static scene + averages flicker), take the moving-stuff centroid, ask "did it move
      the way I pressed?" This is cheap sprite-tracking (no CNN). If even this can't separate real from
      stuck, no appearance signal can (the repetitive-corridor case is an information limit), and the
      fix is behavioral. RAM is the oracle (label only), never an input.

  uv run python -m eval.probe_spatial_move
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from eval.probe_phantom_move import corridor, human

_NW, _NH = 128, 112
_GRID = 8                          # cells per axis
_BG_W = 6                          # rolling background window (frames)
_DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


def _gray(p):
    return np.asarray(Image.open(p).convert("L").resize((_NW, _NH), Image.BILINEAR), np.float32)


def _grid_max(prev, cur):
    """Max per-cell mean-abs change: localizes a sprite move the whole-frame mean would wash out."""
    d = np.abs(cur - prev)
    ch, cw = _NH // _GRID, _NW // _GRID
    cells = d[:ch * _GRID, :cw * _GRID].reshape(_GRID, ch, _GRID, cw).mean(axis=(1, 3))
    return float(cells.max())


def _centroid(fg):
    s = fg.sum()
    if s < 1e-6:
        return None
    ys, xs = np.mgrid[0:fg.shape[0], 0:fg.shape[1]]
    return np.array([float((xs * fg).sum() / s), float((ys * fg).sum() / s)])


def _score(name, steps):
    cache = {}
    def g(i):
        p = steps[i][2]
        if p not in cache:
            try:
                cache[p] = _gray(p)
            except FileNotFoundError:
                cache[p] = None
        return cache[p]
    feats = {"whole": ([], []), "grid_max": ([], []), "centroid_dir": ([], [])}
    for i, (d, moved, _) in enumerate(steps):
        if d is None or moved is None or i < _BG_W:
            continue
        cur, prev = g(i), g(i - 1)
        if cur is None or prev is None:
            continue
        hist = [g(j) for j in range(i - _BG_W, i)]
        hist = [h for h in hist if h is not None]
        if len(hist) < 3:
            continue
        bg = np.median(np.stack(hist), axis=0)
        # foreground = moving stuff vs the rolling background (static scene + averaged flicker drop out)
        c_cur, c_prev = _centroid(np.abs(cur - bg)), _centroid(np.abs(prev - bg))
        dirproj = 0.0
        if c_cur is not None and c_prev is not None:
            shift = c_cur - c_prev
            dx, dy = _DELTA[d]
            dirproj = float(shift[0] * dx + shift[1] * dy)   # >0 => moved-stuff went the commanded way
        sel = 0 if moved else 1
        feats["whole"][sel].append(float(np.abs(cur - prev).mean()))
        feats["grid_max"][sel].append(_grid_max(prev, cur))
        feats["centroid_dir"][sel].append(dirproj)
    print(f"  {name}")
    for sig, (real, stuck) in feats.items():
        if not real or not stuck:
            print(f"    {sig:13s}: (insufficient)"); continue
        a = np.array(real)[:, None]; b = np.array(stuck)[None, :]
        auc = float(((a > b).sum() + 0.5 * (a == b).sum()) / (a.size * b.size))
        print(f"    {sig:13s}: REAL med={np.median(real):6.2f}  STUCK med={np.median(stuck):6.2f}  "
              f"AUC(real>stuck)={auc:.2f}  (n_real={len(real)} n_stuck={len(stuck)})")


def main():
    print("=== SPATIAL-MOVE PROBE - does localizing change (grid / sprite centroid) beat whole-frame? ===")
    print("(AUC 1.0 = the signal tells a real move from a stuck-flicker; 0.5 = useless. whole = the baseline)")
    _score("corridor (runaway)", corridor())
    _score("human-recording (real moves + wall-bumps)", human())
    print("\nIf centroid_dir AUC >> whole on BOTH, cheap sprite-tracking separates them (build it, no CNN).")
    print("If it stays ~whole, the repetitive-corridor case is an information limit -> behavioral fix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
