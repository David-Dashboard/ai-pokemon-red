"""Unit tests for HybridNavigator (feat/nds-reachability bake-off).

HybridNavigator runs the blind escape ladder until it reaches a real menu, then latches into
UI-TARS grounding (NDS → touch; GB/GBA → grounding bridge). The point of the hybrid is to get
PAST boot splashes / loading screens (nothing to ground) that a pure-touch UI-TARS navigator
gets stuck on.

All tests monkeypatch core.navigators.litellm.completion — no llama-server, no py-desmume.
Style mirrors tests/test_uitars_navigator.py and tests/test_navigator_variants.py.
"""
from __future__ import annotations

import numpy as np

import core.navigators as _nav_mod
from core.navigators import BUTTONS, HybridNavigator


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeChoice:
    def __init__(self, text: str):
        self.message = type("M", (), {"content": text})()


class _FakeCompletion:
    def __init__(self, text: str):
        self.choices = [_FakeChoice(text)]


def _counting_completion(text: str, sink: list):
    def _call(**kw):
        sink.append(kw)
        return _FakeCompletion(text)
    return _call


# ---------------------------------------------------------------------------
# Frame factories
# ---------------------------------------------------------------------------

def _blank_gb(seed: int | None = None) -> np.ndarray:
    """A flat GB frame (no edges → no touch targets, reads as static to the ladder)."""
    if seed is None:
        return np.zeros((144, 160, 3), dtype=np.uint8)
    rng = np.random.RandomState(seed)
    return rng.randint(0, 256, (144, 160, 3), dtype=np.uint8)


def _nds_splash() -> np.ndarray:
    """(384,256,3) NDS dual frame, all flat → bottom screen has NO touch targets."""
    return np.zeros((384, 256, 3), dtype=np.uint8)


def _nds_menu() -> np.ndarray:
    """(384,256,3) NDS dual frame whose BOTTOM screen has three tappable rectangles."""
    top = np.zeros((192, 256, 3), dtype=np.uint8)
    bot = np.full((192, 256, 3), 240, dtype=np.uint8)
    bot[20:60, 20:100, :] = 30
    bot[20:60, 150:230, :] = 30
    bot[120:160, 80:170, :] = 30
    return np.concatenate([top, bot], axis=0)


# ===========================================================================
# NDS: touch-target handoff trigger
# ===========================================================================

def test_nds_splash_ladders_no_grounding(monkeypatch):
    """A splash/loading screen (no touch targets) → ladder runs, UI-TARS is NOT called."""
    calls: list = []
    monkeypatch.setattr(_nav_mod.litellm, "completion", _counting_completion("(500,500)", calls))
    nav = HybridNavigator(console="nds")
    for _ in range(4):
        result = nav.decide(_nds_splash())
        assert isinstance(result, str) and result in BUTTONS, f"expected a ladder button, got {result!r}"
    assert nav.handed_off is False
    assert nav.wakes == 0
    assert calls == [], "UI-TARS must not be queried while still on a splash screen"


def test_nds_menu_hands_off_to_touch(monkeypatch):
    """Once the bottom screen shows tappable targets → hand off → UI-TARS returns a touch tuple."""
    calls: list = []
    monkeypatch.setattr(_nav_mod.litellm, "completion", _counting_completion("(500,500)", calls))
    nav = HybridNavigator(console="nds")
    result = nav.decide(_nds_menu())
    assert nav.handed_off is True
    assert isinstance(result, tuple) and result[0] == "touch", f"expected a touch tuple, got {result!r}"
    assert nav.wakes == 1
    assert len(calls) == 1


def test_nds_ladders_then_hands_off_and_latches(monkeypatch):
    """Ladder through a splash, hand off at the menu, and STAY handed off even if targets vanish."""
    monkeypatch.setattr(_nav_mod.litellm, "completion", _counting_completion("(500,500)", []))
    nav = HybridNavigator(console="nds")
    # Three splash frames → ladder.
    for _ in range(3):
        assert isinstance(nav.decide(_nds_splash()), str)
    assert nav.handed_off is False
    # Menu appears → hand off.
    assert isinstance(nav.decide(_nds_menu()), tuple)
    assert nav.handed_off is True
    # A later splash (no targets) must NOT drop us back to the ladder — grounding is latched.
    result = nav.decide(_nds_splash())
    assert isinstance(result, tuple) and result[0] == "touch"
    assert nav.handed_off is True


# ===========================================================================
# GB/GBA: novelty-stall handoff trigger
# ===========================================================================

def test_gb_changing_screens_never_hands_off(monkeypatch):
    """While the ladder keeps reaching new screens, no stall → no handoff → no UI-TARS call."""
    calls: list = []
    monkeypatch.setattr(_nav_mod.litellm, "completion", _counting_completion("(500,500)", calls))
    nav = HybridNavigator(console="gb")
    for i in range(5):
        result = nav.decide(_blank_gb(seed=i * 97 + 1))   # each frame genuinely different
        assert isinstance(result, str) and result in BUTTONS
    assert nav.handed_off is False
    assert nav.wakes == 0
    assert calls == []


def test_gb_stall_hands_off_to_grounding_bridge(monkeypatch):
    """A screen the ladder can't clear (constant frame) → novelty-stall → UI-TARS grounding bridge."""
    calls: list = []
    # "(500,500)" for both target+cursor queries → aligned → the bridge returns "a".
    monkeypatch.setattr(_nav_mod.litellm, "completion", _counting_completion("(500,500)", calls))
    nav = HybridNavigator(console="gb")
    result = None
    for _ in range(_nav_mod._NOVELTY_WINDOW + 1):
        result = nav.decide(_blank_gb())   # constant frame → fingerprints cycle → stall
    assert nav.handed_off is True
    assert nav.wakes >= 1
    assert len(calls) >= 1
    assert result == "a", f"aligned grounding bridge should select with 'a', got {result!r}"


def test_gba_console_routes_through_bridge(monkeypatch):
    """console='gba' uses the same stall→grounding-bridge path (GBA frames are single-screen)."""
    monkeypatch.setattr(_nav_mod.litellm, "completion", _counting_completion("(500,200)", []))
    nav = HybridNavigator(console="gba")
    for _ in range(_nav_mod._NOVELTY_WINDOW + 1):
        nav.decide(np.zeros((160, 240, 3), dtype=np.uint8))
    assert nav.handed_off is True
    assert nav.wakes >= 1
