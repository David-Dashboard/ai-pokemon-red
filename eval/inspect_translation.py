"""Phase B, data-first: is a MAP TRANSITION detectable by 'no valid translation aligns the two frames'?
Within a map, Pokémon scrolls the background under a centered Red, so frame N+1 is frame N shifted by the
move (a tile multiple); SOME integer-tile shift makes the overlap diff small. Across a warp the whole
scene cuts, so NO shift aligns it. This measures, on run #4's real per-decision frames (labelled by the
RAM oracle's map_id — oracle use only), the BEST-shift overlap mean-abs-diff for same-map pairs vs
transition pairs, to see whether they separate (and what threshold).

Run: uv run python -m eval.inspect_translation
"""
from __future__ import annotations

import json
import os

import numpy as np

try:
    import imageio.v2 as iio
except Exception:
    import imageio as iio

ORACLE = "runs/run4/oracle.jsonl"
RANGE, STEP = 64, 16   # search +/-4 tiles (16px overworld tiles) in each axis


def _gray(path):
    a = np.asarray(iio.imread(path))
    return a[..., :3].mean(axis=2) if a.ndim == 3 else a.astype(float)


def best_overlap(a, b, rng=RANGE, step=STEP):
    """Min over integer-tile shifts of the mean-abs-diff on the overlapping region (>=40% area)."""
    H, W = a.shape
    best, bestshift = 1e9, None
    for dy in range(-rng, rng + 1, step):
        for dx in range(-rng, rng + 1, step):
            ay0, ay1 = max(0, dy), min(H, H + dy)
            ax0, ax1 = max(0, dx), min(W, W + dx)
            by0, by1 = max(0, -dy), min(H, H - dy)
            bx0, bx1 = max(0, -dx), min(W, W - dx)
            oa, ob = a[ay0:ay1, ax0:ax1], b[by0:by1, bx0:bx1]
            if oa.size < 0.4 * H * W:
                continue
            d = float(np.abs(oa - ob).mean())
            if d < best:
                best, bestshift = d, (dx, dy)
    return best, bestshift


def main() -> int:
    rows = [json.loads(l) for l in open(ORACLE, encoding="utf-8")]
    seq = []
    for r in rows:
        p = (r.get("screen_path") or "").replace("\\", "/")
        if p and os.path.exists(p):
            seq.append((r["step"], p, r.get("map_id"), (r.get("perceived") or {}).get("context")))

    same, trans = [], []
    cache: dict[str, np.ndarray] = {}

    def g(p):
        if p not in cache:
            cache[p] = _gray(p)
        return cache[p]

    for (s0, p0, m0, c0), (s1, p1, m1, c1) in zip(seq, seq[1:]):
        if c0 != "overworld" or c1 != "overworld":   # only judge overworld->overworld pairs
            continue
        d, shift = best_overlap(g(p0), g(p1))
        (trans if m1 != m0 else same).append((s1, d, shift, m0, m1))

    def stats(name, xs):
        ds = sorted(d for _, d, *_ in xs)
        if not ds:
            print(f"{name}: (none)")
            return
        q = lambda f: ds[min(len(ds) - 1, int(f * len(ds)))]
        print(f"{name}: n={len(ds)}  min={ds[0]:.2f}  p50={q(.5):.2f}  p90={q(.9):.2f}  max={ds[-1]:.2f}")

    print("=== best-shift overlap mean-abs-diff (lower = a valid translation aligns the frames) ===")
    stats("SAME-map  ", same)
    stats("TRANSITION", trans)
    for thr in (10, 15, 20, 25, 30):
        fp = sum(1 for _, d, *_ in same if d > thr)
        tp = sum(1 for _, d, *_ in trans if d > thr)
        print(f"  threshold {thr:>2}: same-map FALSE-positives {fp}/{len(same)}  |  transitions caught {tp}/{len(trans)}")
    print("\n=== transition pairs (each should have NO good shift => high best diff) ===")
    for s1, d, shift, m0, m1 in trans:
        print(f"  step {s1:>3}: map {m0}->{m1}  best_diff={d:.2f}  best_shift={shift}")
    print("\n=== SAME-map pairs with a HIGH best diff (would false-fire; what are they?) ===")
    for s1, d, shift, m0, m1 in sorted(same, key=lambda r: -r[1])[:10]:
        print(f"  step {s1:>3}: map {m0}      best_diff={d:.2f}  best_shift={shift}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
