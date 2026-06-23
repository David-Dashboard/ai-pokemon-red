"""Tests for the mode-aware auto-play policy (core/autoplay.py) — no ROM, no PyBoy, numpy only.

The policy routes the injected random-breadth action on active gameplay, and otherwise walks an escape
ladder behaviorally: REPEAT a move while it keeps changing the screen, ROTATE when it stops.
"""
from __future__ import annotations

import ast
import pathlib
import random

import numpy as np

from core.autoplay import ModalAutoPolicy

_GP = ["__gameplay__"]  # sentinel returned by the injected gameplay_action


def _gameplay_action(rng):
    return list(_GP)


def _frame(val: int):
    f = np.full((144, 160, 4), val, dtype=np.uint8)
    f[..., 3] = 255
    return f


def _scene(seed: int = 1):
    g = np.random.RandomState(seed).randint(0, 200, size=(144, 160), dtype=np.uint16).astype(np.uint8)
    f = np.zeros((144, 160, 4), dtype=np.uint8)
    f[..., 0] = f[..., 1] = f[..., 2] = g
    f[..., 3] = 255
    return f


def _scroll(scene, dx_tiles=0, dy_tiles=0):
    return np.roll(np.roll(scene, -dy_tiles * 16, axis=0), -dx_tiles * 16, axis=1)


def _menu_frames():
    a = _frame(200)
    b = a.copy()
    band_a = np.random.RandomState(7).randint(0, 256, size=(16, 160), dtype=np.uint16).astype(np.uint8)
    band_b = np.random.RandomState(8).randint(0, 256, size=(16, 160), dtype=np.uint16).astype(np.uint8)
    for ch in range(3):
        a[96:112, :, ch] = band_a
        b[96:112, :, ch] = band_b
    return a, b


def _policy():
    return ModalAutoPolicy(random.Random(0), _gameplay_action)


# ---------- routing ----------

def test_gameplay_routes_to_injected_action():
    p = _policy()
    scene = _scene(2)
    mode, act = p.decide(scene, _scroll(scene, dx_tiles=2), last_buttons=["right"])
    assert mode == "gameplay"
    assert act == _GP


def test_static_screen_uses_escape_ladder_not_gameplay():
    p = _policy()
    mode, act = p.decide(_frame(120), _frame(120))
    assert mode == "static"
    assert act != _GP
    assert act in [list(e) for e in p._escape]


def test_unknown_first_frame_escapes():
    p = _policy()
    mode, act = p.decide(None, _scene(1))
    assert mode == "unknown"
    assert act != _GP and act in [list(e) for e in p._escape]


# ---------- behavioral escape: rotate when stuck, repeat when progressing ----------

def test_frozen_screen_rotates_escape_moves():
    p = _policy()
    seen = set()
    f = _frame(90)
    for _ in range(6):
        _, act = p.decide(f, f)            # nothing ever changes -> must rotate
        seen.add(tuple(act))
    assert len(seen) >= 3, f"escape ladder should rotate while stuck, saw {seen}"


def test_progressing_nongameplay_repeats_the_working_move():
    # A non-gameplay screen that CHANGES every step (e.g. a dialog advancing) -> repeat escape[0].
    p = _policy()
    a, b = _menu_frames()
    outs = []
    for i in range(5):
        prev, cur = (a, b) if i % 2 == 0 else (b, a)
        mode, act = p.decide(prev, cur)
        outs.append(tuple(act))
        assert mode in ("menu", "static")  # appearance class is soft; never 'gameplay' here
    assert set(outs) == {tuple(p._escape[0])}, f"should repeat the progressing move, got {outs}"


def test_stalls_counter_tracks_nongameplay_steps():
    p = _policy()
    f = _frame(50)
    for _ in range(4):
        p.decide(f, f)
    assert p.stalls == 4


def test_deterministic_given_seed_and_inputs():
    scene = _scene(3)
    nxt = _scroll(scene, dx_tiles=1)
    a = ModalAutoPolicy(random.Random(0), _gameplay_action).decide(scene, nxt, ["right"])
    b = ModalAutoPolicy(random.Random(0), _gameplay_action).decide(scene, nxt, ["right"])
    assert a == b


# ---------- world-agnostic guarantee ----------

def test_autoplay_imports_are_world_agnostic():
    src = (pathlib.Path(__file__).resolve().parent.parent / "core" / "autoplay.py").read_text(encoding="utf-8")
    tops = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            for a in node.names:
                tops.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                tops.add(node.module.split(".")[0])
    assert "games" not in tops and "torch" not in tops
    assert tops <= {"core", "random", "typing", "__future__"}, f"unexpected imports: {tops}"
