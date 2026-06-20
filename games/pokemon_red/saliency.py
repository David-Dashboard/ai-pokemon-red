"""Motion-saliency: a FREE, pixels-only NPC/ROI signal for guided search. The overworld camera centres
the player, so when the player does NOT move (a blocked move, or an A-press) the camera is static and
two consecutive frames are pixel-aligned — any region that still CHANGES is a MOVING entity (an
idle-animating NPC). This is the cheap "where is there something to interact with" prior that the
geometry-only occupancy map lacks (it knows walls, not what's on them).

Data-first finding (eval/inspect_motion on run #16): the raw signal also fires on ANIMATED TERRAIN
(Pallet's water/flowers) — but terrain animates as a LARGE connected region (events of 14-77 tiles)
while an NPC is one sprite-sized 16px metatile (clusters of 1-2 tiles). So we keep only SMALL
off-centre clusters: that cleanly separates the lab's NPCs (Oak/the rival — indoor, no terrain) from
Pallet's water. The player's own bump animation at screen-centre is masked out.

No RAM, no model, world-agnostic in spirit (it encodes no Pokémon facts — just "small moving thing on
a still camera = entity"). Returns SCREEN-tile coordinates; the perceiver maps them to world cells.
"""
from __future__ import annotations

import numpy as np

TILE = 16              # overworld metatile (px)
GW, GH = 10, 9         # 160x144 -> 10 wide x 9 tall metatiles
PLAYER_TILE = (4, 4)   # the player's fixed screen metatile (col, row), 0-indexed — masked (self-animation)
_THRESH = 8.0          # per-tile mean abs-diff that counts as "changed" (data: walls ~0, sprites >> 8)
_MAX_CLUSTER = 2       # keep clusters this small (NPC = 1 sprite tile, +1 for bleed); bigger = terrain


def _tile_diff_grid(prev, frame) -> np.ndarray:
    """Per-metatile mean abs-diff between two camera-aligned frames -> (GH, GW) float grid."""
    a = np.asarray(prev)[..., :3].mean(2)
    b = np.asarray(frame)[..., :3].mean(2)
    g = np.zeros((GH, GW))
    for ty in range(GH):
        for tx in range(GW):
            pa = a[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE]
            pb = b[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE]
            g[ty, tx] = float(np.abs(pa - pb).mean())
    return g


def _clusters(tiles: set) -> list:
    """4-connected components of a set of (tx, ty) tiles -> list of components (each a set)."""
    seen, out = set(), []
    for t in tiles:
        if t in seen:
            continue
        comp, stack = set(), [t]
        while stack:
            c = stack.pop()
            if c in comp or c not in tiles:
                continue
            comp.add(c)
            seen.add(c)
            cx, cy = c
            stack += [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)]
        out.append(comp)
    return out


def motion_rois(prev, frame, *, thresh: float = _THRESH, max_cluster: int = _MAX_CLUSTER) -> list:
    """NPC/ROI candidates from a CAMERA-STATIC frame pair. Returns a list of (tx, ty) SCREEN metatiles
    that changed, off-centre, in a SMALL connected cluster (sprite-sized) — i.e. likely a moving NPC,
    not the player (masked) and not a large animated-terrain region (rejected). Empty if either frame
    is missing or nothing qualifies. The CALLER must only pass camera-aligned frames (player didn't
    scroll) — a scrolled pair changes everywhere and is meaningless here."""
    if prev is None or frame is None:
        return []
    a = np.asarray(prev)
    b = np.asarray(frame)
    if a.shape != b.shape:
        return []
    g = _tile_diff_grid(a, b)
    changed = {(tx, ty) for ty in range(GH) for tx in range(GW)
               if g[ty, tx] >= thresh and (tx, ty) != PLAYER_TILE}
    rois = []
    for comp in _clusters(changed):
        if len(comp) <= max_cluster:                      # sprite-sized; bigger = terrain, drop it
            # the cluster's hottest tile is the entity's centre
            tx, ty = max(comp, key=lambda c: g[c[1], c[0]])
            rois.append((tx, ty))
    return rois


def roi_offsets(rois: list) -> list:
    """Map screen-tile ROIs to TILE OFFSETS from the player (dx, dy): +x right, +y down. The perceiver
    adds these to its dead-reckoned cursor to place the entity in world coordinates."""
    px, py = PLAYER_TILE
    return [(tx - px, ty - py) for (tx, ty) in rois]
