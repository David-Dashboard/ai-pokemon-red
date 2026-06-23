"""Tests for the world-agnostic modality detector (core/modality.py) — no ROM, no PyBoy, numpy only.

Synthetic frames mirror tests/test_perception.py (_frame / _scene / _scroll): a FROZEN pair is static,
a textured SCROLL is gameplay, and a mostly-flat panel with a small changing region is a menu. Also
pins the no-leak guarantee for this module: it imports numpy only (never games/, torch, PIL, cv2).
"""
from __future__ import annotations

import ast
import pathlib

import numpy as np

from core.modality import (
    FLAT_VAR,
    GAMEPLAY_FRAC,
    detect_modality,
    modality_signals,
)


def _frame(val: int):
    """A uniform (flat) RGBA frame."""
    f = np.full((144, 160, 4), val, dtype=np.uint8)
    f[..., 3] = 255
    return f


def _scene(seed: int = 1):
    """A TEXTURED frame (deterministic) — a 'map' with structure; high per-cell variance (not flat)."""
    g = np.random.RandomState(seed).randint(0, 200, size=(144, 160), dtype=np.uint16).astype(np.uint8)
    f = np.zeros((144, 160, 4), dtype=np.uint8)
    f[..., 0] = f[..., 1] = f[..., 2] = g
    f[..., 3] = 255
    return f


def _scroll(scene, dx_tiles: int = 0, dy_tiles: int = 0):
    """Simulate a camera scroll of (dx,dy) tiles — the widespread change a real same-map move produces."""
    return np.roll(np.roll(scene, -dy_tiles * 16, axis=0), -dx_tiles * 16, axis=1)


def _menu_pair():
    """A mostly-flat panel (one textured 'text row' that CHANGES) — local change under a UI panel."""
    a = _frame(200)
    b = a.copy()
    band_a = np.random.RandomState(7).randint(0, 256, size=(16, 160), dtype=np.uint16).astype(np.uint8)
    band_b = np.random.RandomState(8).randint(0, 256, size=(16, 160), dtype=np.uint16).astype(np.uint8)
    for ch in range(3):
        a[96:112, :, ch] = band_a
        b[96:112, :, ch] = band_b
    return a, b


# ---------- the three modes ----------

def test_frozen_pair_is_static():
    label, conf = detect_modality(_scene(1), _scene(1))
    assert label == "static"
    assert conf >= 0.9  # fd == 0 -> high confidence


def test_flat_frozen_pair_is_static_not_menu():
    # A frozen menu/title is STATIC (not responding), even though it is flat — static is checked first.
    label, _ = detect_modality(_frame(120), _frame(120))
    assert label == "static"


def test_textured_scroll_is_gameplay():
    scene = _scene(2)
    label, conf = detect_modality(scene, _scroll(scene, dx_tiles=2), last_buttons=["right"])
    assert label == "gameplay"
    assert 0.0 <= conf <= 1.0


def test_gameplay_without_buttons_still_classified():
    scene = _scene(3)
    label, _ = detect_modality(scene, _scroll(scene, dy_tiles=1), last_buttons=None)
    assert label == "gameplay"


def test_local_change_under_panel_is_menu():
    a, b = _menu_pair()
    label, conf = detect_modality(a, b, last_buttons=["down"])
    assert label == "menu"
    assert 0.0 <= conf <= 1.0


# ---------- unknown / robustness ----------

def test_first_frame_is_unknown():
    assert detect_modality(None, _scene(1)) == ("unknown", 0.0)


def test_shape_mismatch_is_unknown():
    small = np.zeros((72, 80, 4), dtype=np.uint8)
    assert detect_modality(_scene(1), small) == ("unknown", 0.0)


def test_none_current_is_unknown():
    assert detect_modality(_scene(1), None) == ("unknown", 0.0)


# ---------- signals helper ----------

def test_signals_expose_raw_features():
    scene = _scene(4)
    sig = modality_signals(scene, _scroll(scene, dx_tiles=1))
    assert set(sig) == {"frame_diff", "frac_changed", "frac_flat"}
    assert sig["frame_diff"] > 0 and 0.0 <= sig["frac_changed"] <= 1.0 and 0.0 <= sig["frac_flat"] <= 1.0


def test_signals_none_without_prev():
    assert modality_signals(None, _scene(1)) is None


def test_flat_frame_reads_as_flat_cells():
    # A uniform frame is entirely flat cells; a textured one is not (sanity on the panel cue).
    flat = modality_signals(_frame(100), _frame(100))
    assert flat["frac_flat"] == 1.0
    textured = modality_signals(_scene(5), _scene(5))
    assert textured["frac_flat"] < 0.5


# ---------- the world-agnostic / no-leak guarantee ----------

def test_modality_is_numpy_only_no_games_import():
    src = (pathlib.Path(__file__).resolve().parent.parent / "core" / "modality.py").read_text(encoding="utf-8")
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                mods.add(node.module.split(".")[0])
    forbidden = {"games", "torch", "cv2", "scipy", "skimage", "PIL"}
    assert not (mods & forbidden), f"core/modality.py must stay numpy-only; leaked: {mods & forbidden}"
    assert mods <= {"numpy", "typing", "__future__"}, f"unexpected imports in core/modality.py: {mods}"


def test_constants_are_sane():
    assert 0.0 < GAMEPLAY_FRAC < 1.0 and FLAT_VAR > 0.0
