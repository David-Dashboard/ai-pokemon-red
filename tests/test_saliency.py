"""Motion-saliency tests (no ROM, synthetic frames). The detector turns a CAMERA-STATIC frame pair
into NPC/ROI candidates: small off-centre changed clusters (sprite-sized) are entities; the player's
own tile and large animated-terrain regions are rejected. Mirrors the data-first finding in
eval/inspect_motion (lab NPCs survive, Pallet water is filtered)."""
from __future__ import annotations

import numpy as np

from games.pokemon_red.saliency import (GH, GW, PLAYER_TILE, TILE, motion_rois,
                                        roi_offsets)


def _frame(val: int = 120):
    return np.full((GH * TILE, GW * TILE, 4), val, dtype=np.uint8)


def _set_tile(frame, tx: int, ty: int, val: int):
    frame[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE, :3] = val
    return frame


def test_small_offcenter_change_is_an_roi():
    a = _frame()
    b = _set_tile(_frame(), 7, 2, 255)            # one sprite-sized tile changed, off-centre
    assert motion_rois(a, b) == [(7, 2)]


def test_player_tile_change_is_masked():
    a = _frame()
    b = _set_tile(_frame(), PLAYER_TILE[0], PLAYER_TILE[1], 255)   # the player's own bump animation
    assert motion_rois(a, b) == []


def test_large_animated_region_is_rejected_as_terrain():
    # A big connected block (animated water/flowers) exceeds the sprite-sized cluster cap -> dropped.
    a = _frame()
    b = _frame()
    for ty in range(0, 4):
        for tx in range(0, 5):
            _set_tile(b, tx, ty, 200)
    assert motion_rois(b, a) == [] or all(False for _ in motion_rois(a, b))
    assert motion_rois(a, b) == []


def test_two_separate_sprites_both_detected():
    a = _frame()
    b = _set_tile(_set_tile(_frame(), 1, 1, 255), 8, 7, 255)   # two distant 1-tile entities
    assert set(motion_rois(a, b)) == {(1, 1), (8, 7)}


def test_below_threshold_change_ignored():
    a = _frame(120)
    b = _set_tile(_frame(120), 7, 2, 123)         # +3 mean diff < the 8.0 threshold
    assert motion_rois(a, b) == []


def test_mismatched_or_missing_frames_are_empty():
    assert motion_rois(None, _frame()) == []
    assert motion_rois(_frame(), None) == []
    assert motion_rois(_frame(), np.zeros((10, 10, 4), dtype=np.uint8)) == []


def test_roi_offsets_are_relative_to_the_player():
    # (tx,ty) above-and-left and below-and-right of the player -> signed (dx,dy) offsets.
    px, py = PLAYER_TILE
    assert roi_offsets([(px, py - 2), (px + 3, py + 1)]) == [(0, -2), (3, 1)]
