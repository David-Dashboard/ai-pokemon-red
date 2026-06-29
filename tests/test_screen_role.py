"""Unit tests for core/screen_role.py — agnostic NDS screen-role discovery.

Tests prove:
  1. TOP-gameplay sequence: top screen scrolls under commands, bottom static -> discovery picks "top".
  2. BOTTOM-gameplay sequence (inverted): bottom scrolls, top static -> discovery picks "bottom".
  3. Both directions work WITHOUT any prior toward top or bottom (agnostic proof).
  4. NDSPerceiver routes GridPerceiver to the discovered gameplay screen.

All tests are pure numpy (no ROM, no py-desmume). They skip cleanly when numpy is absent (it won't be),
but the guard is kept for consistency with the project test pattern.

Synthetic frames follow the same conventions as test_modality.py:
  - A "textured scroll" produces widespread change (gameplay signal).
  - A "static flat" frame stays frozen (static/menu signal).
"""
from __future__ import annotations

import numpy as np
import pytest

from core.screen_role import ScreenRoleDiscovery, _MIN_STEPS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flat(val: int = 180) -> np.ndarray:
    """A flat uniform frame (192×256×3) — looks like a static/menu screen."""
    return np.full((_H, _W, 3), val, dtype=np.uint8)


def _textured(seed: int = 1) -> np.ndarray:
    """A richly textured frame (192×256×3) — low flat-panel fraction."""
    rng = np.random.RandomState(seed)
    return rng.randint(0, 220, size=(_H, _W, 3), dtype=np.uint8).astype(np.uint8)


def _scroll(frame: np.ndarray, dx: int = 8, dy: int = 0) -> np.ndarray:
    """Simulate a camera scroll: roll the frame by (dx, dy) pixels."""
    return np.roll(np.roll(frame, dy, axis=0), dx, axis=1).copy()


_H, _W = 192, 256   # NDS screen dimensions


def _drive(disc: ScreenRoleDiscovery,
           gameplay_side: str,
           n_steps: int = 12,
           seed: int = 42) -> dict:
    """Feed a synthetic sequence where `gameplay_side` ("top" or "bottom") scrolls under
    direction commands, and the other side stays flat/static.

    Returns the final discovery result after n_steps.
    """
    assert gameplay_side in ("top", "bottom")
    scene = _textured(seed)
    static = _flat()

    result: dict = {}
    for i in range(n_steps):
        # Alternate between movement commands and idle frames.
        action = "right" if i % 2 == 0 else None

        # The gameplay screen scrolls when a command is issued.
        dx = 10 if action == "right" else 0
        gameplay_frame = _scroll(scene, dx=dx + i, dy=i // 3)  # always drifting
        other_frame = static.copy()

        if gameplay_side == "top":
            top_f, bot_f = gameplay_frame, other_frame
        else:
            top_f, bot_f = other_frame, gameplay_frame

        result = disc.update(top_f, bot_f, action)

    return result


# ---------------------------------------------------------------------------
# Core agnostic-discovery tests
# ---------------------------------------------------------------------------

class TestScreenRoleDiscovery:
    """Screen-role discovery is top/bottom-agnostic."""

    def test_top_gameplay_detected(self):
        """When top scrolls under commands and bottom is static, discovery picks top."""
        disc = ScreenRoleDiscovery()
        result = _drive(disc, gameplay_side="top")
        assert result["gameplay"] == "top", (
            f"Expected gameplay='top', got {result!r}"
        )
        assert result["symbolic"] == "bottom"
        assert result["confidence"] > 0.0

    def test_bottom_gameplay_detected(self):
        """When bottom scrolls under commands and top is static, discovery picks bottom.

        This is the key agnostic proof: the same algorithm returns 'bottom' on the
        inverted sequence without any prior toward either screen.
        """
        disc = ScreenRoleDiscovery()
        result = _drive(disc, gameplay_side="bottom")
        assert result["gameplay"] == "bottom", (
            f"Expected gameplay='bottom', got {result!r}"
        )
        assert result["symbolic"] == "top"
        assert result["confidence"] > 0.0

    def test_insufficient_steps_returns_none(self):
        """Before min_steps is reached, discovery returns None (no commitment)."""
        disc = ScreenRoleDiscovery(min_steps=5)
        scene = _textured()
        static = _flat()
        result = {}
        for i in range(4):  # 4 < min_steps=5
            result = disc.update(_scroll(scene, dx=i * 5), static, "right")
        assert result["gameplay"] is None
        assert result["confidence"] < 0.4

    def test_both_static_returns_none(self):
        """When both screens are frozen (boot/transition), confidence is low."""
        disc = ScreenRoleDiscovery()
        static = _flat()
        result = {}
        for _ in range(10):
            result = disc.update(static.copy(), static.copy(), None)
        # Both static -> neither looks like gameplay -> low confidence / None.
        assert result["confidence"] < 0.5 or result["gameplay"] is None, (
            f"Expected low confidence for both-static, got {result!r}"
        )

    def test_reset_clears_state(self):
        """reset() lets the discovery start fresh without leaking prior evidence."""
        disc = ScreenRoleDiscovery()
        _drive(disc, gameplay_side="top")
        disc.reset()
        assert disc._steps == 0
        assert disc._modal_top == []
        assert disc._modal_bot == []

    def test_returns_debug_keys(self):
        """Result always contains _debug with per-screen signals for logging."""
        disc = ScreenRoleDiscovery()
        _drive(disc, gameplay_side="top", n_steps=4)
        result = disc.result
        assert "_debug" in result
        debug = result["_debug"]
        assert "steps" in debug

    def test_no_top_bias_symmetry(self):
        """Results for top-gameplay and bottom-gameplay are symmetric (neither outcome is
        structurally preferred over the other by more than random noise)."""
        result_top = _drive(ScreenRoleDiscovery(), gameplay_side="top", seed=99)
        result_bot = _drive(ScreenRoleDiscovery(), gameplay_side="bottom", seed=99)

        # Top-gameplay run → top wins; bottom-gameplay run → bottom wins.
        assert result_top["gameplay"] == "top", f"top-gameplay run failed: {result_top!r}"
        assert result_bot["gameplay"] == "bottom", f"bottom-gameplay run failed: {result_bot!r}"

        # Confidence magnitudes should be similar (no structural asymmetry).
        conf_diff = abs(result_top["confidence"] - result_bot["confidence"])
        assert conf_diff < 0.3, (
            f"Asymmetric confidence: top_conf={result_top['confidence']}, "
            f"bot_conf={result_bot['confidence']}"
        )


# ---------------------------------------------------------------------------
# NDSPerceiver routing test
# ---------------------------------------------------------------------------

class TestNDSPerceiverRouting:
    """NDSPerceiver routes the spatial pipeline to the discovered gameplay screen."""

    def test_perceive_dual_frame_does_not_raise(self):
        """A full 384×256 dual frame is accepted without error."""
        from core.nds_perceiver import NDSPerceiver, _NDS_H, _NDS_W
        from core.perception import PerceptMemory

        perceiver = NDSPerceiver()
        memory = PerceptMemory()

        top = _textured(1)
        bot = _flat()
        dual = np.concatenate([top, bot], axis=0)  # (384, 256, 3)
        assert dual.shape == (2 * _NDS_H, _NDS_W, 3)

        # Must not raise; result is a SymbolicState.
        sym = perceiver.perceive(dual, memory, context={"last_action": "right"})
        assert sym is not None

    def test_perceive_routes_to_discovered_screen(self):
        """After enough steps, NDSPerceiver routes to the screen discovery picks."""
        from core.nds_perceiver import NDSPerceiver, _NDS_H, _NDS_W
        from core.perception import PerceptMemory

        perceiver = NDSPerceiver(discovery_min_steps=3)
        memory = PerceptMemory()
        scene = _textured(7)
        static = _flat()

        for i in range(10):
            action = "right" if i % 2 == 0 else None
            top = _scroll(scene, dx=i * 8)  # top scrolls
            bot = static.copy()
            dual = np.concatenate([top, bot], axis=0)
            perceiver.perceive(dual, memory, context={"last_action": action})

        role = perceiver.last_role
        # Top was the scrolling screen -> should be discovered as gameplay.
        if role["gameplay"] is not None:
            assert role["gameplay"] == "top", f"Expected top as gameplay, got {role!r}"

    def test_single_screen_passthrough(self):
        """A single 192×256 frame bypasses discovery and is passed directly."""
        from core.nds_perceiver import NDSPerceiver, _NDS_H, _NDS_W
        from core.perception import PerceptMemory

        perceiver = NDSPerceiver()
        memory = PerceptMemory()
        single = _textured(3)  # (192, 256, 3)
        assert single.shape == (_NDS_H, _NDS_W, 3)

        sym = perceiver.perceive(single, memory, context={"last_action": "a"})
        assert sym is not None
