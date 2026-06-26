"""SCRATCH (verification of Task #9 step 1 confound): the faced-tile crop assumes the player sits at
screen cell (4,4), true only when the camera is centred. Near MAP BORDERS the camera clamps and the
player goes off-centre, so the cropped 16x16 "faced tile" is the WRONG region -> mislabelled samples.

We (a) quantify per-map the fraction of faced-tile samples likely mis-cropped, using TWO independent
proxies, (b) cross-check them, then (c) re-run leave-one-map-out EXCLUDING flagged samples and report
whether per-map coverage/acc-when-known move materially.

Proxies:
  SCROLL (direct, moved-only): when the player moves 1 RAM tile but the camera scrolls << 1 tile, the
    player is off-centre (camera clamped). Computed from pixels via the perceiver's own _best_shift.
    Cannot judge BLOCKED samples (no motion either way), so it is a lower bound on off-centre.
  BOUND (works for all samples): the camera keeps the player at cell (4,4) only when there are >=4
    cells left / >=4 up / >=5 right (10-4-1) / >=4 down (9-4-1=4) of map. Using per-map observed RAM
    extents as a rough map bound, a sample is "off-centre toward the faced dir" if the player is within
    the clamp margin of the extent on the side it FACES (the side that determines the faced-tile crop).
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np
from PIL import Image

from core.tilemap import TileFunctionMap

RUN_DIRS = sys.argv[1:] or [
    "runs/kanto1", "runs/race1", "runs/race2", "runs/race3", "runs/fix1",
    "runs/fix2", "runs/fix4", "runs/fix5", "runs/novelty_val", "runs/novelty_val3",
]
PLAYER = (4, 4)          # screen cell (col,row) in the 10x9 metatile grid
GRID_W, GRID_H = 10, 9
CELL = 16
OFF = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
SHIFT_RANGE = 32         # +/- px search for camera scroll (>=1 tile)

# Margins for the camera to keep the player centred at (4,4):
LEFT_NEED, UP_NEED = 4, 4
RIGHT_NEED, DOWN_NEED = GRID_W - PLAYER[0] - 1, GRID_H - PLAYER[1] - 1   # 5, 4

MAP_NAMES = {0: "Pallet", 1: "Viridian City", 12: "Route 1", 13: "Route 2",
             37: "house", 38: "bedroom", 39: "rival house", 40: "Oak lab",
             41: "Viridian bldg", 51: "VIRIDIAN FOREST"}


def dir_of(action):
    if not action:
        return None
    a = str(action).split("+")[0].strip().lower()
    return a if a in OFF else None


def label_of(outcome):
    if not outcome:
        return None
    o = str(outcome).lower()
    if o == "moved":
        return "walkable"
    if o in ("blocked", "changed-nothing", "no-move", "stuck", "unchanged"):
        return "blocked"
    return None


def _gray(img):
    return img[..., :3].mean(axis=2)


def _best_shift(a, b):
    """Integer-tile translation aligning b back onto a; returns (best_diff, (dx,dy)). Mirror of the
    perceiver's whole-tile scroll estimator (search step = one tile)."""
    H, W = a.shape
    best_score, best_d, bsx, bsy = 1e9, 255.0, 0, 0
    for dy in range(-SHIFT_RANGE, SHIFT_RANGE + 1, CELL):
        for dx in range(-SHIFT_RANGE, SHIFT_RANGE + 1, CELL):
            ay0, ay1 = max(0, dy), min(H, H + dy)
            ax0, ax1 = max(0, dx), min(W, W + dx)
            by0, by1 = max(0, -dy), min(H, H - dy)
            bx0, bx1 = max(0, -dx), min(W, W - dx)
            oa, ob = a[ay0:ay1, ax0:ax1], b[by0:by1, bx0:bx1]
            if oa.size < 0.4 * H * W:
                continue
            d = float(np.abs(oa - ob).mean())
            score = d + 1e-3 * (abs(dx) + abs(dy))
            if score < best_score:
                best_score, best_d, bsx, bsy = score, d, dx, dy
    return best_d, (bsx, bsy)


def map_extents(run_dirs):
    ext = {}
    for run in run_dirs:
        op = os.path.join(run, "oracle.jsonl")
        if not os.path.exists(op):
            continue
        for l in open(op, encoding="utf-8"):
            r = json.loads(l)
            m, x, y = r.get("map_id"), r.get("x"), r.get("y")
            if m is None or x is None or y is None:
                continue
            e = ext.setdefault(m, [10**9, -10**9, 10**9, -10**9])
            e[0] = min(e[0], x); e[1] = max(e[1], x)
            e[2] = min(e[2], y); e[3] = max(e[3], y)
    return ext


def bound_offcentre(map_id, x, y, direction, ext):
    """True if, per observed map extents, the camera is clamped on the side the player FACES (so the
    faced-tile crop at screen (4,4)+dir is the wrong region). Conservative: also flag if clamped on the
    axis the move is along OR perpendicular, since perpendicular clamp shifts the column/row too."""
    e = ext.get(map_id)
    if e is None:
        return False
    minx, maxx, miny, maxy = e
    # distance from each border (in tiles)
    dl, dr = x - minx, maxx - x
    du, dd = y - miny, maxy - y
    # camera clamps horizontally if not enough map on a side; the faced crop's COLUMN is wrong then.
    clamp_x = (dl < LEFT_NEED) or (dr < RIGHT_NEED)
    clamp_y = (du < UP_NEED) or (dd < DOWN_NEED)
    # The faced tile for up/down depends on the ROW (y-axis clamp) AND its column is the player column
    # (x-axis clamp). For left/right, the COLUMN matters (x clamp) and the row (y clamp). So ANY clamp
    # on EITHER axis can mis-place the faced crop. Use the union (most conservative).
    return clamp_x or clamp_y


def bound_offcentre_strict(map_id, x, y, direction, ext):
    """Stricter: only flag if clamped on the side the player is MOVING toward (the faced direction),
    i.e. the faced cell would fall outside the centred window."""
    e = ext.get(map_id)
    if e is None:
        return False
    minx, maxx, miny, maxy = e
    dl, dr = x - minx, maxx - x
    du, dd = y - miny, maxy - y
    if direction == "left":
        return dl < LEFT_NEED
    if direction == "right":
        return dr < RIGHT_NEED
    if direction == "up":
        return du < UP_NEED
    if direction == "down":
        return dd < DOWN_NEED
    return False


def gather(run_dirs, ext):
    """Faced-tile samples with both proxies' flags.
    Returns list of dicts."""
    samples = []
    for run in run_dirs:
        op = os.path.join(run, "oracle.jsonl")
        if not os.path.exists(op):
            continue
        rows = [json.loads(l) for l in open(op, encoding="utf-8")]
        frames = {}
        for i in range(1, len(rows)):
            cur, prev = rows[i], rows[i - 1]
            p = cur.get("perceived", {})
            if p.get("context") != "overworld" or cur.get("in_battle"):
                continue
            d, lab = dir_of(p.get("action")), label_of(p.get("outcome"))
            if d is None or lab is None:
                continue
            fpath = os.path.join(run, f"frame_{prev['step']:06d}.png")
            cpath = os.path.join(run, f"frame_{cur['step']:06d}.png")
            if not os.path.exists(fpath):
                continue
            cx, cy = PLAYER[0] + OFF[d][0], PLAYER[1] + OFF[d][1]
            img = np.asarray(Image.open(fpath).convert("RGB"))
            tile = img[cy * CELL:(cy + 1) * CELL, cx * CELL:(cx + 1) * CELL]
            if tile.shape[:2] != (CELL, CELL):
                continue
            fp = TileFunctionMap.fingerprint(tile)

            mp = cur.get("map_id")
            px, py = prev.get("x", 0), prev.get("y", 0)
            pmap = prev.get("map_id")

            # SCROLL proxy: only meaningful for 'moved' (walkable) WITHIN same map.
            scroll_offcentre = None
            scroll_px = None
            if lab == "walkable" and os.path.exists(cpath) and pmap == mp:
                a = _gray(img.astype(float))
                b = _gray(np.asarray(Image.open(cpath).convert("RGB")).astype(float))
                _, (sdx, sdy) = _best_shift(a, b)
                mag = max(abs(sdx), abs(sdy))
                scroll_px = mag
                # centred move scrolls ~1 tile; clamped move scrolls 0 tiles
                scroll_offcentre = (mag < CELL // 2)

            bnd = bound_offcentre(pmap, px, py, d, ext)
            bnd_strict = bound_offcentre_strict(pmap, px, py, d, ext)

            samples.append({
                "fp": fp, "lab": lab, "map": mp, "dir": d,
                "scroll_offcentre": scroll_offcentre, "scroll_px": scroll_px,
                "bound": bnd, "bound_strict": bnd_strict,
            })
    return samples


def loo(samples, key_filter=None, label="ALL"):
    """leave-one-map-out on a (possibly filtered) sample list. key_filter(s)->bool keeps a sample."""
    use = samples if key_filter is None else [s for s in samples if key_filter(s)]
    by_map = Counter(s["map"] for s in use)
    res = {}
    for held in by_map:
        test = [s for s in use if s["map"] == held]
        store = [s for s in use if s["map"] != held]
        if len(test) < 20 or len(store) < 20:
            continue
        tmap = TileFunctionMap()
        for s in store:
            tmap.observe(s["fp"], s["lab"])
        known = correct = 0
        for s in test:
            pred = tmap.predict(s["fp"])
            if pred is not None:
                known += 1
                correct += (pred[0] == s["lab"])
        cov = known / len(test)
        acc = (correct / known) if known else float("nan")
        res[held] = (len(test), cov, acc, known)
    return res


def main():
    print(f"runs: {RUN_DIRS}")
    ext = map_extents(RUN_DIRS)
    samples = gather(RUN_DIRS, ext)
    print(f"total faced-tile samples: {len(samples)}  "
          f"labels: {dict(Counter(s['lab'] for s in samples))}")

    # ---- proxy agreement on the moved subset (where both apply) -------------
    moved = [s for s in samples if s["lab"] == "walkable" and s["scroll_offcentre"] is not None]
    sc = sum(s["scroll_offcentre"] for s in moved)
    print(f"\n--- proxy cross-check on MOVED samples ({len(moved)}) ---")
    print(f"  scroll says off-centre: {sc} ({sc/len(moved):.1%})")
    bnd_m = sum(s["bound"] for s in moved)
    bs_m = sum(s["bound_strict"] for s in moved)
    print(f"  bound(union) off-centre: {bnd_m} ({bnd_m/len(moved):.1%})")
    print(f"  bound(strict-facing) off-centre: {bs_m} ({bs_m/len(moved):.1%})")
    # confusion scroll vs bound
    tp = sum(1 for s in moved if s["scroll_offcentre"] and s["bound"])
    fp_ = sum(1 for s in moved if (not s["scroll_offcentre"]) and s["bound"])
    fn = sum(1 for s in moved if s["scroll_offcentre"] and (not s["bound"]))
    print(f"  scroll&bound={tp}  bound-only={fp_}  scroll-only(bound-miss)={fn}")
    # what is the scroll-flagged accuracy of the bound proxy: of scroll-offcentre, how many bound catches
    if sc:
        print(f"  of scroll-flagged, bound(union) catches {tp}/{sc} = {tp/sc:.1%}; "
              f"bound(strict) catches {sum(1 for s in moved if s['scroll_offcentre'] and s['bound_strict'])}/{sc}")

    # ---- per-map off-centre fraction (bound proxy, all samples) -------------
    print(f"\n--- per-map suspected mis-crop fraction (BOUND union, all samples) ---")
    permap = defaultdict(lambda: [0, 0])
    permap_strict = defaultdict(lambda: [0, 0])
    for s in samples:
        permap[s["map"]][0] += 1
        permap[s["map"]][1] += int(s["bound"])
        permap_strict[s["map"]][0] += 1
        permap_strict[s["map"]][1] += int(s["bound_strict"])
    for m in sorted(permap, key=lambda k: -permap[k][0]):
        n, off = permap[m]
        ns, offs = permap_strict[m]
        nm = MAP_NAMES.get(m, "?")
        print(f"  map {m:>2} {nm:<16} n={n:<5} bound-union {off/n:5.1%}  bound-strict {offs/ns:5.1%}")

    # ---- leave-one-map-out: BASELINE vs EXCLUDING flagged -------------------
    base = loo(samples)
    excl_union = loo(samples, key_filter=lambda s: not s["bound"])
    excl_strict = loo(samples, key_filter=lambda s: not s["bound_strict"])
    print(f"\n--- leave-one-map-out: baseline vs excluding flagged edge samples ---")
    print(f"  {'map':<22} {'BASE cov/acc/n':>22}   {'EXCL-union cov/acc/n':>24}   {'EXCL-strict cov/acc/n':>24}")
    for m in sorted(base, key=lambda k: -base[k][0]):
        nm = MAP_NAMES.get(m, "?")
        bn, bcov, bacc, _ = base[m]
        b = f"{bcov:5.1%}/{bacc:5.1%}/{bn}"
        if m in excl_union:
            un, ucov, uacc, _ = excl_union[m]
            u = f"{ucov:5.1%}/{uacc:5.1%}/{un}"
        else:
            u = "(<20 left)"
        if m in excl_strict:
            sn, scov, sacc, _ = excl_strict[m]
            st = f"{scov:5.1%}/{sacc:5.1%}/{sn}"
        else:
            st = "(<20 left)"
        flag = "  <--" if m in (51, 37, 40) else ""
        print(f"  {m:>2} {nm:<18} {b:>22}   {u:>24}   {st:>24}{flag}")


if __name__ == "__main__":
    main()
