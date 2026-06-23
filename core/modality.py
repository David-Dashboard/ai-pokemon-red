"""World-agnostic MODALITY detection from pixels (System-1; no game facts, no RAM, no training).

Classifies a screen as one of:
  - "static"   — frozen / near-frozen (a title screen, a paused screen, waiting on input);
  - "menu"     — a UI / menu / dialog panel (the screen responds only LOCALLY to input);
  - "gameplay" — an active scene where movement produces WIDESPREAD change (scroll/locomotion/animation);
  - "unknown"  — first frame / shape mismatch (no previous frame to compare).

WHY this lives in core/ (not games/): it is the GENERALIZABLE replacement for a per-game `detect_mode`.
A new world's perceiver reuses it to set `SymbolicState.context`, and the recorder uses it to drive
AUTONOMOUS data collection (get through titles/menus without a human). It must therefore encode NO game
facts — no tilesets, fonts, memory map, or hardcoded Pokemon UI regions. numpy only; cheap; deterministic.

Signals (all cheap, behaviorally grounded):
  - frame-diff (whole-frame mean abs-diff): a (near-)frozen screen is static; a changing screen is active.
  - change locality (a coarse per-cell diff): widespread change = a scrolling/animating SCENE (gameplay);
    a small local change = a cursor / counter in a menu.
  - flat-panel fraction (a coarse per-cell variance): menus/dialog draw large UNIFORM (low-variance)
    fills (boxes / text rows); textured game scenes are not. This is the principle borrowed from the
    Pokemon `detect_mode` (UI = uniform panel) but generalized to relative cells — NOT its hardcoded
    0.66H/0.6W regions or its near-white assumption.
  - input-response (optional `last_buttons`): a direction press that produced widespread change is strong
    evidence of gameplay (scroll/locomotion). The KNOWN input grounds the label without RAM/GT — the
    same trick the 3D odometry gate used (a known FORWARD action with ~zero angle change proved advance).

The robust, generalizable boundary is GAMEPLAY vs NOT-GAMEPLAY. The static<->menu split is softer (a
blinking title may read as menu; an arcade game with a large uniform background may read as menu). The
mode-aware auto-policy treats static and menu the same (advance / navigate), so that softness is
harmless to collection — and it is reported honestly rather than hidden.
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np

# Tunable defaults — sensible starting points, to be CALIBRATED on the dev captures + the Pokemon
# `detect_mode` anchor (eval/corpus_activity.py). They are deliberately conservative so the
# GAMEPLAY vs NOT boundary (the one that matters for the policy) is the robust one.
STATIC_EPS = 1.2        # whole-frame mean-abs-diff (0..255) below this = frozen / static
CELL_PX = 16            # coarse grid cell size (px); a generic metatile, not a Pokemon fact
CELL_CHANGED = 8.0      # per-cell mean-abs-diff that counts as "changed" (matches saliency's _THRESH)
GAMEPLAY_FRAC = 0.30    # fraction of cells changed at/above which change is "widespread" => gameplay
FLAT_VAR = 12.0         # per-cell stddev below which the cell is a flat/uniform fill (UI panel)
FLAT_FRAC = 0.55        # fraction of flat cells at/above which a UI panel dominates => menu

_DIRECTIONS = ("up", "down", "left", "right")


def _gray(frame) -> np.ndarray:
    """Frame (H,W) | (H,W,3) | (H,W,4) -> float32 grayscale (H,W). Alpha, if present, is ignored."""
    a = np.asarray(frame, dtype=np.float32)
    if a.ndim == 3:
        a = a[..., :3].mean(axis=2)
    return a


def _grid_stats(prev_g: Optional[np.ndarray], cur_g: np.ndarray) -> Tuple[float, float]:
    """Coarse per-cell change + flatness. Returns (frac_changed, frac_flat) in [0,1].

    frac_changed is 0.0 when prev_g is None. The frame is cropped to a whole number of CELL_PX cells;
    a frame smaller than one cell falls back to whole-frame statistics."""
    H, W = cur_g.shape
    gh, gw = H // CELL_PX, W // CELL_PX
    if gh == 0 or gw == 0:  # tiny frame: treat the whole thing as one cell
        flat = 1.0 if float(cur_g.std()) < FLAT_VAR else 0.0
        if prev_g is None:
            return 0.0, flat
        changed = 1.0 if float(np.abs(cur_g - prev_g).mean()) >= CELL_CHANGED else 0.0
        return changed, flat
    Hc, Wc = gh * CELL_PX, gw * CELL_PX
    c = cur_g[:Hc, :Wc].reshape(gh, CELL_PX, gw, CELL_PX)
    cell_std = c.std(axis=(1, 3))                       # (gh, gw)
    frac_flat = float((cell_std < FLAT_VAR).mean())
    if prev_g is None:
        return 0.0, frac_flat
    p = prev_g[:Hc, :Wc].reshape(gh, CELL_PX, gw, CELL_PX)
    cell_diff = np.abs(c - p).mean(axis=(1, 3))         # (gh, gw)
    frac_changed = float((cell_diff >= CELL_CHANGED).mean())
    return frac_changed, frac_flat


def modality_signals(prev_frame, curr_frame) -> Optional[dict]:
    """The raw cheap signals behind a classification (for calibration / debugging), or None if there is
    no comparable previous frame. Keys: frame_diff, frac_changed, frac_flat."""
    if curr_frame is None or prev_frame is None:
        return None
    cur_g = _gray(curr_frame)
    prev_g = _gray(prev_frame)
    if prev_g.shape != cur_g.shape:
        return None
    fd = float(np.abs(cur_g - prev_g).mean())
    fc, ff = _grid_stats(prev_g, cur_g)
    return {"frame_diff": fd, "frac_changed": fc, "frac_flat": ff}


def _clamp(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def detect_modality(prev_frame, curr_frame,
                    last_buttons: Optional[Sequence[str]] = None) -> Tuple[str, float]:
    """Classify the current screen from a (prev, curr) frame pair and the buttons that produced curr.

    Returns (label, confidence) with label in {"static","menu","gameplay","unknown"} and confidence in
    [0,1]. `prev_frame=None` (or a shape mismatch) returns ("unknown", 0.0)."""
    sig = modality_signals(prev_frame, curr_frame)
    if sig is None:
        return ("unknown", 0.0)
    fd, fc, ff = sig["frame_diff"], sig["frac_changed"], sig["frac_flat"]

    # 1) Frozen / near-frozen screen -> static (title, paused, waiting on input).
    if fd < STATIC_EPS:
        return ("static", round(_clamp(0.5 + (STATIC_EPS - fd) / (2.0 * STATIC_EPS)), 2))

    # 2) Active screen: gameplay (widespread / direction-driven change) vs menu (local change under a
    #    dominating flat UI panel).
    pressed_dir = bool(last_buttons) and any(b in _DIRECTIONS for b in last_buttons)
    widespread = fc >= GAMEPLAY_FRAC or (pressed_dir and fc >= 0.66 * GAMEPLAY_FRAC)
    panel = ff >= FLAT_FRAC

    if widespread and not panel:
        return ("gameplay", round(_clamp(0.55 + 0.45 * (fc - GAMEPLAY_FRAC) / (1.0 - GAMEPLAY_FRAC)), 2))
    if panel and not widespread:
        return ("menu", round(_clamp(0.55 + 0.45 * (ff - FLAT_FRAC) / (1.0 - FLAT_FRAC)), 2))
    # Ambiguous (both, or neither): decide by the panel cue at low confidence. "Neither" (a small change
    # with no dominating panel) is typically a static-sprite gameplay screen -> gameplay.
    return ("menu", 0.5) if panel else ("gameplay", 0.5)
