"""Unit tests for NDSTouchNavigator, apply_action, and _parse_nds_action (feat/nds-reachability).

All tests use pure numpy + fake emulators — no py-desmume, no llama-server required.
The litellm.completion call is monkeypatched throughout.

Style mirrors tests/test_nds_touch.py exactly.
"""
from __future__ import annotations

from typing import Optional

import pytest

numpy = pytest.importorskip("numpy")
import numpy as np

# ---------------------------------------------------------------------------
# Fake NDS emulator — records presses, touches, releases, ticks.
# ---------------------------------------------------------------------------

_NDS_BUTTONS = ("a", "b", "x", "y", "l", "r", "start", "select", "up", "down", "left", "right")


class FakeNDSEmu:
    """Minimal NDS emulator stub: records calls, returns blank frames."""

    BUTTONS = _NDS_BUTTONS

    def __init__(self):
        self.presses: list[str] = []
        self.touches: list[tuple[int, int]] = []
        self.releases: int = 0
        self.ticks: int = 0
        self._frame: int = 0

    def press(self, button: str, hold_frames: int = 8, settle_frames: int = 16) -> None:
        self.presses.append(button)

    def tick(self, n: int) -> None:
        self.ticks += n
        self._frame += n

    def touch(self, x: int, y: int) -> None:
        self.touches.append((x, y))

    def touch_release(self) -> None:
        self.releases += 1

    def screen_ndarray(self, screen="both"):
        h = 384 if screen == "both" else 192
        return np.zeros((h, 256, 3), dtype=np.uint8)

    def save_screen(self, path: str) -> None:
        pass

    def read(self, addr: int) -> int:
        return 0

    def load_state(self, path: str) -> None:
        pass

    def save_state(self, path: str) -> None:
        pass

    def close(self) -> None:
        pass

    @property
    def frame(self) -> int:
        return self._frame


# ---------------------------------------------------------------------------
# Fake emulator WITHOUT touch support (for safety tests).
# ---------------------------------------------------------------------------

class FakeEmuNoTouch:
    """Emulator without touch/touch_release methods."""

    def press(self, button: str, **_) -> None:
        pass

    def tick(self, n: int) -> None:
        pass

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fake litellm response.
# ---------------------------------------------------------------------------

class _FakeChoice:
    def __init__(self, text: str):
        self.message = type("M", (), {"content": text})()


class _FakeCompletion:
    def __init__(self, text: str):
        self.choices = [_FakeChoice(text)]


# ---------------------------------------------------------------------------
# Dual-frame factory: top = random, bottom = 3-rectangle UI (reuses pattern
# from test_nds_touch.py::_make_ui_frame).
# ---------------------------------------------------------------------------

def _make_ui_frame(h: int = 192, w: int = 256) -> np.ndarray:
    """Synthetic NDS bottom-screen: light background + three dark rectangles."""
    frame = np.full((h, w, 3), 240, dtype=np.uint8)
    frame[20:60, 20:100, :] = 30    # button 1
    frame[20:60, 150:230, :] = 30   # button 2
    frame[120:160, 80:170, :] = 30  # button 3
    return frame


def _make_dual_ui_frame() -> np.ndarray:
    """(384,256,3) dual frame: random top + 3-rectangle bottom."""
    rng = np.random.RandomState(42)
    top = rng.randint(0, 200, (192, 256, 3), dtype=np.uint8)
    bot = _make_ui_frame()
    return np.concatenate([top, bot], axis=0)


# ---------------------------------------------------------------------------
# Shared imports from the modules under test.
# ---------------------------------------------------------------------------

from core.navigators import (
    BUTTONS,
    NDS_BUTTONS,
    NDSTouchNavigator,
    _TOUCH_HOLD,
    _TOUCH_SETTLE,
    _parse_nds_action,
    apply_action,
)
import core.navigators as _nav_mod


# ---------------------------------------------------------------------------
# Helper: build targets from a dual frame.
# ---------------------------------------------------------------------------

def _targets_from_dual(dual: np.ndarray):
    from core.nds_perceiver import _detect_touch_targets
    bot = dual[192:]
    return _detect_touch_targets(bot)


# ===========================================================================
# Tests 1–9: NDSTouchNavigator.decide() via monkeypatched litellm.completion
# ===========================================================================

def test_touch_index_reply(monkeypatch):
    """1. 'TOUCH 0' → ("touch", cx, cy) of the largest-area target."""
    dual = _make_dual_ui_frame()
    targets = _targets_from_dual(dual)
    assert len(targets) >= 1

    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion("TOUCH 0"))
    nav = NDSTouchNavigator(mode="vlm")
    result = nav.decide(dual)
    expected = ("touch", targets[0]["cx"], targets[0]["cy"])
    assert result == expected, f"expected {expected}, got {result}"


def test_raw_coords_reply(monkeypatch):
    """2. 'TOUCH 130 90' → ("touch", 130, 90)."""
    dual = _make_dual_ui_frame()
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion("TOUCH 130 90"))
    nav = NDSTouchNavigator(mode="vlm")
    assert nav.decide(dual) == ("touch", 130, 90)


def test_button_reply(monkeypatch):
    """3. Button reply 'a' → 'a' (str, not tuple)."""
    dual = _make_dual_ui_frame()
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion("a"))
    nav = NDSTouchNavigator(mode="vlm")
    result = nav.decide(dual)
    assert result == "a"
    assert isinstance(result, str)


def test_nds_only_button_x(monkeypatch):
    """4. NDS-only button 'x' → 'x' (proves 12-button parse)."""
    dual = _make_dual_ui_frame()
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion("x"))
    nav = NDSTouchNavigator(mode="vlm")
    assert nav.decide(dual) == "x"


def test_invalid_reply_fallback(monkeypatch):
    """5. Unrecognised reply 'banana' → 'a' (fallback)."""
    dual = _make_dual_ui_frame()
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion("banana"))
    nav = NDSTouchNavigator(mode="vlm")
    assert nav.decide(dual) == "a"


def test_touch_index_out_of_range(monkeypatch):
    """6. 'TOUCH 99' with <99 targets → 'a' (no bad tuple, no raise)."""
    dual = _make_dual_ui_frame()
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion("TOUCH 99"))
    nav = NDSTouchNavigator(mode="vlm")
    result = nav.decide(dual)
    assert result == "a"


def test_raw_coords_out_of_range(monkeypatch):
    """7. 'TOUCH 300 90' (x > 255) → 'a'."""
    dual = _make_dual_ui_frame()
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion("TOUCH 300 90"))
    nav = NDSTouchNavigator(mode="vlm")
    assert nav.decide(dual) == "a"


def test_ocr_mode_no_image_url(monkeypatch):
    """8a. OCR mode sends NO image_url in messages."""
    dual = _make_dual_ui_frame()
    captured = {}

    def fake_completion(**kw):
        captured["messages"] = kw["messages"]
        return _FakeCompletion("a")

    monkeypatch.setattr(_nav_mod.litellm, "completion", fake_completion)
    nav = NDSTouchNavigator(mode="ocr")
    nav.decide(dual)

    content = captured["messages"][0]["content"]
    types = [c.get("type") for c in content]
    assert "image_url" not in types, f"ocr mode must not send image_url; got types: {types}"


def test_vlm_mode_sends_image_url(monkeypatch):
    """8b. VLM mode DOES include image_url in messages."""
    dual = _make_dual_ui_frame()
    captured = {}

    def fake_completion(**kw):
        captured["messages"] = kw["messages"]
        return _FakeCompletion("a")

    monkeypatch.setattr(_nav_mod.litellm, "completion", fake_completion)
    nav = NDSTouchNavigator(mode="vlm")
    nav.decide(dual)

    content = captured["messages"][0]["content"]
    types = [c.get("type") for c in content]
    assert "image_url" in types, f"vlm mode must send image_url; got types: {types}"


def test_prompt_offers_12_nds_buttons(monkeypatch):
    """9. Prompt text contains NDS-only buttons x, y, l, r."""
    dual = _make_dual_ui_frame()
    captured = {}

    def fake_completion(**kw):
        captured["messages"] = kw["messages"]
        return _FakeCompletion("a")

    monkeypatch.setattr(_nav_mod.litellm, "completion", fake_completion)
    nav = NDSTouchNavigator(mode="ocr")
    nav.decide(dual)

    content = captured["messages"][0]["content"]
    text_parts = " ".join(c["text"] for c in content if c.get("type") == "text")
    for btn in ("x", "y", "l", "r"):
        assert btn in text_parts, f"expected button '{btn}' in prompt text"


# ===========================================================================
# Tests 10–13: apply_action
# ===========================================================================

def test_apply_action_touch(monkeypatch):
    """10. apply_action(emu, ("touch",128,64)) → touches==[(128,64)], releases==1, ticks>=hold+settle."""
    emu = FakeNDSEmu()
    apply_action(emu, ("touch", 128, 64))
    assert emu.touches == [(128, 64)]
    assert emu.releases == 1
    assert emu.ticks >= _TOUCH_HOLD + _TOUCH_SETTLE
    assert emu.presses == []


def test_apply_action_button(monkeypatch):
    """11. apply_action(emu, "a") → presses==["a"], touches==[]."""
    emu = FakeNDSEmu()
    apply_action(emu, "a")
    assert emu.presses == ["a"]
    assert emu.touches == []


def test_apply_action_touch_out_of_range(monkeypatch):
    """12. apply_action(emu, ("touch",999,0)) → no emu.touch, no raise (safe fallback)."""
    emu = FakeNDSEmu()
    apply_action(emu, ("touch", 999, 0))
    assert emu.touches == [], "out-of-range touch must not call emu.touch"
    # fallback presses "a"
    assert emu.presses == ["a"]


def test_apply_action_no_touch_method_no_raise():
    """13. apply_action(FakeEmuNoTouch, ("touch",10,10)) → no raise."""
    emu = FakeEmuNoTouch()
    try:
        apply_action(emu, ("touch", 10, 10))
    except Exception as exc:
        pytest.fail(f"apply_action raised unexpectedly: {exc}")


def test_apply_action_non_int_touch_no_raise():
    """13b. Non-int touch tuple → no raise; falls back to press('a')."""
    emu = FakeNDSEmu()
    for bad in (("touch", None, 0), ("touch", "z", 0)):
        apply_action(emu, bad)
    assert emu.touches == []
    assert emu.presses == ["a", "a"]


# ===========================================================================
# Test 14: _stepper("nds-vlm") integration
# ===========================================================================

def test_stepper_nds_vlm_returns_one_element_list(monkeypatch):
    """14. _stepper('nds-vlm') builds a navigator; step(None, dual, []) returns a one-element list."""
    dual = _make_dual_ui_frame()

    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion("a"))

    from eval.bakeoff import _stepper
    step = _stepper("nds-vlm")
    result = step(None, dual, [])
    assert isinstance(result, list) and len(result) == 1, \
        f"expected a one-element list, got: {result}"


# ===========================================================================
# Test 15: main apply-loop (unit-level, no emulator file I/O)
# ===========================================================================

def test_main_apply_loop():
    """15. Loop over ["a", ("touch",50,60)] → one press + one touch+release."""
    emu = FakeNDSEmu()
    actions = ["a", ("touch", 50, 60)]
    for action in actions:
        apply_action(emu, action)
    assert emu.presses == ["a"]
    assert emu.touches == [(50, 60)]
    assert emu.releases == 1


# ===========================================================================
# Test 16: GB regression — VLMNavigator/MenuPerceiverNavigator use 8-button BUTTONS
# ===========================================================================

def test_gb_navigators_use_8_button_set():
    """16. VLMNavigator and MenuPerceiverNavigator still have buttons==BUTTONS (8); never a tuple."""
    from core.navigators import VLMNavigator, MenuPerceiverNavigator
    assert VLMNavigator().buttons == BUTTONS
    assert MenuPerceiverNavigator().buttons == BUTTONS
    assert len(BUTTONS) == 8


# ===========================================================================
# Test 17: apply_action("right") → exactly one press, no touch
# ===========================================================================

def test_apply_action_right():
    """17. apply_action(emu, "right") → exactly one emu.press("right"), no touch."""
    emu = FakeNDSEmu()
    apply_action(emu, "right")
    assert emu.presses == ["right"]
    assert emu.touches == []


# ===========================================================================
# Test 18: import safety — NDSTouchNavigator() constructs without py-desmume
# ===========================================================================

def test_nds_touch_navigator_import_safe():
    """18. Constructing NDSTouchNavigator() succeeds even without py-desmume."""
    try:
        nav = NDSTouchNavigator()
        assert nav.mode == "vlm"
        assert nav.buttons == NDS_BUTTONS
    except ImportError as exc:
        pytest.fail(f"NDSTouchNavigator() raised ImportError unexpectedly: {exc}")
