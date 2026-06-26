"""Avatar-localization probe (the open-loop gate for the drift-free pose fix).

Dead-reckoning integrates a noisy binary move signal -> the pose desyncs from the world within ~25 steps
(phantom moves + missed moves; RAM-proven). The fix: read the avatar's ABSOLUTE on-screen position from
pixels each frame and quantize to a cell -> no integration, no drift. Cave Noire's RAM (x=0xC504, y=0xC503)
is ALREADY a cell index (x 0..8, y 0..6 on a 9x7 board), so we can score predicted-cell vs RAM-cell EXACTLY.

This measures, BEFORE wiring anything: can a cheap pixel localizer track the RAM cell, and does it stay
LOCKED (bounded error) rather than DRIFT (cumulative)? It compares a few candidate localizers so the data
picks the winner. The screen->cell map is fit by least squares (one global affine per axis: the playfield
occupies the same screen region in every room, so one map serves all rooms). RAM is the SCORER, never input.

  uv run python -m eval.probe_avatar_localize

PASS BAR (the winner must clear all): median cell-error <= 1, 90th-pct <= 2, |error-vs-frame slope| ~ 0
(bounded, not cumulative), lock rate >= 70% of gameplay frames.
"""
from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image

_NW, _NH = 128, 112
_BG_W = 6                     # rolling-median background window (frames) -- static scene + flicker average out
_HUD_FRAC = 0.78              # Cave Noire's status bar is the bottom band; the playfield is the top ~78%
_RUN = "runs/2026-06-23_cavenoire_explore"
_DIRS = ("up", "down", "left", "right")


def _btn_dir(bs):
    """Last cardinal in a recorded button list -> the commanded_dir the live agent would pass."""
    t = [b for b in (bs or []) if b in _DIRS]
    return t[-1] if t else None


def _gray(p):
    return np.asarray(Image.open(p).convert("L").resize((_NW, _NH), Image.BILINEAR), np.float32)


def _wrap(d):
    return ((d + 128) % 256) - 128


def _centroid(fg):
    s = fg.sum()
    if s < 1e-6:
        return None
    ys, xs = np.mgrid[0:fg.shape[0], 0:fg.shape[1]]
    return np.array([float((xs * fg).sum() / s), float((ys * fg).sum() / s)])


def _load():
    """(frame_path, ram_x, ram_y, room_cut) per step. room_cut = RAM jumped >1 cell (a transition)."""
    ram = np.fromfile(os.path.join(_RUN, "ram.bin"), dtype=np.uint8)
    n = ram.size // 8192
    ram = ram[:n * 8192].reshape(n, 8192)
    x, y = ram[:, 0x504].astype(int), ram[:, 0x503].astype(int)
    out = []
    for i in range(n):
        cut = i > 0 and (abs(_wrap(x[i] - x[i - 1])) > 1 or abs(_wrap(y[i] - y[i - 1])) > 1)
        out.append((os.path.join(_RUN, f"frame_{i:06d}.png"), int(x[i]), int(y[i]), cut))
    return out


# -- candidate localizers: each maps (cur, rolling-median bg) -> a screen (col,row) or None ----------------

def _cand_full(cur, bg):
    return _centroid(np.abs(cur - bg))


def _cand_roi(cur, bg):
    """Exclude the bottom HUD band: its digit counters change and would drag the centroid off the avatar."""
    fg = np.abs(cur - bg).copy()
    fg[int(_HUD_FRAC * _NH):, :] = 0.0
    return _centroid(fg)


CANDS = {"full_frame": _cand_full, "playfield_roi": _cand_roi}

_TRACK_R = 22.0    # local search radius (px on the 128x112 frame; ~1.4 cells) for the nearest-blob tracker
_MASS_FLOOR = 60.0  # min local foreground mass to accept a move; below it the player is stationary -> hold


_TPL_H = 7      # template half-size (px) -> 15x15 patch of the avatar sprite
_WIN = 12       # NCC search half-window (px) around the previous position


def _patch(a, cx, cy, h):
    r0, r1, c0, c1 = int(cy - h), int(cy + h + 1), int(cx - h), int(cx + h + 1)
    if r0 < 0 or c0 < 0 or r1 > a.shape[0] or c1 > a.shape[1]:
        return None
    return a[r0:r1, c0:c1]


def _ncc_at(cur, tpl, cx, cy):
    p = _patch(cur, cx, cy, (tpl.shape[0] - 1) // 2)
    if p is None or p.shape != tpl.shape:
        return -2.0
    p = p - p.mean(); t = tpl - tpl.mean()
    d = float(np.sqrt((p * p).sum() * (t * t).sum()))
    return float((p * t).sum() / d) if d > 1e-6 else -2.0


def _ncc_track(cur, tpl, pos):
    """Normalized cross-correlation search in a +-_WIN window; returns (new_pos, peak_ncc)."""
    best, bxy = -2.0, (pos[0], pos[1])
    for dy in range(-_WIN, _WIN + 1, 2):
        for dx in range(-_WIN, _WIN + 1, 2):
            v = _ncc_at(cur, tpl, pos[0] + dx, pos[1] + dy)
            if v > best:
                best, bxy = v, (pos[0] + dx, pos[1] + dy)
    return np.array([float(bxy[0]), float(bxy[1])]), best


def _local_centroid(fg, pos, r):
    """Centroid of foreground mass within radius r of `pos` (col,row). Returns (centroid, mass)."""
    ys, xs = np.mgrid[0:fg.shape[0], 0:fg.shape[1]]
    near = ((xs - pos[0]) ** 2 + (ys - pos[1]) ** 2) <= r * r
    w = fg * near
    s = w.sum()
    if s < 1e-6:
        return None, 0.0
    return np.array([float((xs * w).sum() / s), float((ys * w).sum() / s)]), float(s)


def _fit_eval(name, samples):
    """samples = list of (cx, cy, ram_x, ram_y). Fit one affine per axis (col->x, row->y), report cell error."""
    a = np.array(samples, float)
    if len(a) < 20:
        print(f"  {name:14s}: (insufficient samples: {len(a)})"); return None, None
    cx, cy, rx, ry = a[:, 0], a[:, 1], a[:, 2], a[:, 3]
    # least-squares affine ram = m*centroid + b, per axis (the fixed screen->cell geometry)
    mx, bx = np.polyfit(cx, rx, 1)
    my, by = np.polyfit(cy, ry, 1)
    px, py = mx * cx + bx, my * cy + by                 # predicted (continuous) cell
    err = np.abs(np.round(px) - rx) + np.abs(np.round(py) - ry)   # L1 cell error (quantized prediction)
    idx = np.arange(len(err))
    slope = float(np.polyfit(idx, err, 1)[0]) if len(err) > 1 else 0.0
    print(f"  {name:14s}: median={np.median(err):.2f}  90th={np.percentile(err, 90):.2f}  "
          f"mean={err.mean():.2f}  slope/1000fr={slope * 1000:+.2f}  (n={len(err)})  "
          f"pitch=({1/mx:.1f},{1/my:.1f})px/cell")
    return err, (mx, bx, my, by)


def eval_avatarlocalizer(steps):
    """THE GATE: drive the SHIPPED core.localize.AvatarLocalizer continuously (commanded_dir from
    buttons.jsonl -- the same input the live agent has), score predicted cell vs RAM cell. Unlike the
    candidates above (RAM-blind centroid/NCC), this is the localizer we'd actually wire. The fitted affine
    is the per-world screen->cell geometry constant (calibrated once here; the runtime uses pixels only).

    RAM-cell is only a VALID screen target on gameplay frames (menu/transition/title hold a stale x,y the
    sprite isn't at -- the documented 'loose proxy'). So we score three regimes: all frames, GAMEPLAY-only
    (detect_modality, the same gate the live perceiver applies), and gameplay+MOVING (RAM is exact on a
    confirmed within-room step). The middle one is the live-relevant gate."""
    from core.localize import AvatarLocalizer
    from core.modality import detect_modality
    bp = os.path.join(_RUN, "buttons.jsonl")
    btn = [json.loads(l) for l in open(bp, encoding="utf-8")] if os.path.exists(bp) else []
    loc = AvatarLocalizer()
    all_s, play_s, move_s, lock, eligible = [], [], [], 0, 0
    prev_full, prev_rxy = None, None
    for i, (fp, rx, ry, cut) in enumerate(steps):
        if cut:
            loc.reset()                                  # room changed -> drop the heatmap, re-acquire
            prev_full = None
        bs = btn[i].get("buttons") if i < len(btn) else None
        rgb = np.asarray(Image.open(fp).convert("RGB"), np.float32) if os.path.exists(fp) else None
        out = loc.update(rgb, _btn_dir(bs)) if rgb is not None else None
        full = rgb[..., :3].mean(2) if rgb is not None else None
        label = "gameplay" if prev_full is None or full is None else \
            detect_modality(prev_full, full, [t for t in (bs or []) if t])[0]
        moved = prev_rxy is not None and 0 < abs(_wrap(rx - prev_rxy[0])) + abs(_wrap(ry - prev_rxy[1])) <= 1
        prev_full, prev_rxy = full, (rx, ry)
        if cut:
            continue                                     # don't score the cut frame; let it re-lock first
        eligible += 1
        if out is not None:
            lock += 1
            s = (out[0], out[1], rx, ry)
            all_s.append(s)
            if label == "gameplay":
                play_s.append(s)
                if moved:
                    move_s.append(s)
    print(f"\n[AvatarLocalizer] lock rate: {lock / eligible:.0%}  (eligible {eligible})")
    _fit_eval("all-frames", all_s)
    err, _ = _fit_eval("gameplay", play_s)               # <- the live-relevant gate
    _, coef = _fit_eval("gameplay+moving", move_s)        # <- clean regime (RAM exact) -> the geometry constant
    if coef:
        mx, bx, my, by = coef
        print(f"  AFFINE (160x144 px -> cell, from MOVING frames; wire as the per-world constant):")
        print(f"    cell_x = round({mx:.6f} * col + {bx:.4f})")
        print(f"    cell_y = round({my:.6f} * row + {by:.4f})")
    return err


def main():
    import sys
    print("=== AVATAR-LOCALIZATION PROBE - predicted cell vs RAM cell (exact); does pixel pose stay LOCKED? ===")
    steps = _load()
    if "--gate-only" in sys.argv:                        # skip the 3-min RAM-blind candidate sweep
        eval_avatarlocalizer(steps)
        print("\nPASS = median<=1, 90th<=2, slope~0 (bounded, not cumulative), lock>=70%. Clear it before wiring.")
        return 0
    cache = {}
    def g(p):
        if p not in cache:
            cache[p] = _gray(p) if os.path.exists(p) else None
        return cache[p]

    # collect per-candidate samples over gameplay frames (skip the _BG_W frames after a room cut: stale bg)
    samples = {k: [] for k in CANDS}
    samples["nn_track"] = []
    samples["tpl_ceiling"] = []
    samples["argmax_track"] = []
    lock = {k: 0 for k in CANDS}
    lock["nn_track"] = 0
    lock["tpl_ceiling"] = 0
    lock["argmax_track"] = 0
    amx_pos = [None]
    eligible = 0
    since_cut = 999
    track_pos = None                                    # stateful: the local nearest-blob tracker
    tpl, tpl_pos = None, None                           # stateful: the NCC template tracker (ceiling test)
    prev_rxy = None
    for i, (fp, rx, ry, cut) in enumerate(steps):
        if cut:
            since_cut = 0
            track_pos = None                            # room changed -> drop the track, re-bootstrap
            tpl, tpl_pos = None, None
            amx_pos[0] = None
        else:
            since_cut += 1
        cur = g(fp)
        if cur is None or since_cut < _BG_W:
            continue
        hist = [g(steps[j][0]) for j in range(i - _BG_W, i)]
        hist = [h for h in hist if h is not None]
        if len(hist) < 3:
            continue
        bg = np.median(np.stack(hist), axis=0)
        eligible += 1
        for k, fn in CANDS.items():
            c = fn(cur, bg)
            if c is not None:
                lock[k] += 1
                samples[k].append((c[0], c[1], rx, ry))
        # local nearest-blob tracker: hold position when no foreground is near (stationary), else follow it
        fg = np.abs(cur - bg).copy()
        fg[int(_HUD_FRAC * _NH):, :] = 0.0
        if track_pos is None:
            track_pos = _centroid(fg)                   # bootstrap from the global playfield foreground
        else:
            c, mass = _local_centroid(fg, track_pos, _TRACK_R)
            if c is not None and mass >= _MASS_FLOOR:
                track_pos = c
        if track_pos is not None:
            lock["nn_track"] += 1
            samples["nn_track"].append((track_pos[0], track_pos[1], rx, ry))
        # NCC template tracker (CEILING test): acquire the avatar patch where it ARRIVES on a confirmed move
        # (RAM only gates the acquisition timing; the patch location is pixels-derived), then match appearance
        # every frame -- works even when the avatar is stationary. Tests whether the avatar is trackable AT ALL.
        moved1 = prev_rxy is not None and 0 < abs(_wrap(rx - prev_rxy[0])) + abs(_wrap(ry - prev_rxy[1])) <= 1
        prevf = g(steps[i - 1][0])
        if tpl is None:
            if moved1 and prevf is not None:
                arr = _centroid(fg * (np.abs(cur - prevf)))      # arrival lobe = where the avatar moved TO
                if arr is not None:
                    p = _patch(cur, arr[0], arr[1], _TPL_H)
                    if p is not None:
                        tpl, tpl_pos = p, arr
        else:
            tpl_pos, peak = _ncc_track(cur, tpl, tpl_pos)
            if moved1 and prevf is not None:                     # refresh the template on a fresh confirmed move
                p = _patch(cur, tpl_pos[0], tpl_pos[1], _TPL_H)
                if p is not None:
                    tpl = p
            lock["tpl_ceiling"] += 1
            samples["tpl_ceiling"].append((tpl_pos[0], tpl_pos[1], rx, ry))
        prev_rxy = (rx, ry)
        # argmax_track: the cell of biggest PER-STEP change (|cur-prev|, the grid_max signal that scores AUC 0.99
        # for move-vs-stuck) IS where the sprite just moved. Update pos to it on a strong change; else hold.
        if prevf is not None:
            d = np.abs(cur - prevf)
            ch, cw = _NH // 8, _NW // 8
            cellm = d[:ch * 8, :cw * 8].reshape(8, ch, 8, cw).mean(axis=(1, 3))
            if cellm.max() >= 12.0:                          # a localized change happened (grid_max ~ move)
                r, c = np.unravel_index(int(cellm.argmax()), cellm.shape)
                amx = np.array([(c + 0.5) * cw, (r + 0.5) * ch])
                amx_pos[0] = amx
        if amx_pos[0] is not None:
            lock["argmax_track"] += 1
            samples["argmax_track"].append((amx_pos[0][0], amx_pos[0][1], rx, ry))

    print(f"\neligible gameplay frames: {eligible} (of {len(steps)})\n")
    for k in samples:
        print(f"  [{k}] lock rate: {lock[k] / eligible:.0%}")
    print()
    for k in samples:
        _fit_eval(k, samples[k])
    print("\n--- THE GATE: the shipped control-grounded AvatarLocalizer (the one we'd wire) ---")
    eval_avatarlocalizer(steps)
    print("\nPASS = median<=1, 90th<=2, slope~0 (bounded, not cumulative), lock>=70%. Clear it before wiring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
