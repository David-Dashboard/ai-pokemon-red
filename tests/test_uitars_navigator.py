"""Unit tests for UITARSNavigator (feat/nds-reachability bake-off).

All tests use monkeypatched litellm.completion — no live UI-TARS server required.
Style mirrors tests/test_nds_touch_navigator.py.
"""
from __future__ import annotations

import pytest

numpy = pytest.importorskip("numpy")
import numpy as np

import core.navigators as _nav_mod
from core.navigators import UITARSNavigator, _parse_uitars_coords


# ---------------------------------------------------------------------------
# Fake litellm response helpers (mirror test_nds_touch_navigator.py).
# ---------------------------------------------------------------------------

class _FakeChoice:
    def __init__(self, text: str):
        self.message = type("M", (), {"content": text})()


class _FakeCompletion:
    def __init__(self, text: str):
        self.choices = [_FakeChoice(text)]


def _fake_completion(text: str):
    return lambda **kw: _FakeCompletion(text)


def _side_effect_completion(replies: list):
    """Return a fake completion that yields successive replies from a list."""
    it = iter(replies)

    def _call(**kw):
        return _FakeCompletion(next(it))

    return _call


# ---------------------------------------------------------------------------
# Frame factories.
# ---------------------------------------------------------------------------

def _nds_frame() -> np.ndarray:
    """(384, 256, 3) dual-screen NDS frame filled with zeros."""
    return np.zeros((384, 256, 3), dtype=np.uint8)


def _gb_frame() -> np.ndarray:
    """(144, 160, 3) blank GB frame."""
    return np.zeros((144, 160, 3), dtype=np.uint8)


# ===========================================================================
# _parse_uitars_coords unit tests
# ===========================================================================

def test_parse_bare_pair():
    """'(500,500)' → (500, 500)."""
    assert _parse_uitars_coords("(500,500)") == (500, 500)


def test_parse_with_spaces():
    """'( 499 , 637 )' → (499, 637)."""
    assert _parse_uitars_coords("( 499 , 637 )") == (499, 637)


def test_parse_action_wrapped():
    """'click(point=\'(499,637)\')' → (499, 637) — real UI-TARS output format."""
    assert _parse_uitars_coords("click(point='(499,637)')") == (499, 637)


def test_parse_plain_text_two_numbers():
    """Reply with two bare numbers → (first, second)."""
    assert _parse_uitars_coords("The point is at 200 300 on screen") == (200, 300)


def test_parse_empty_returns_none():
    assert _parse_uitars_coords("") is None


def test_parse_no_numbers_returns_none():
    assert _parse_uitars_coords("no coords here") is None


def test_parse_one_number_returns_none():
    """Only one digit run → not enough for a coordinate pair."""
    assert _parse_uitars_coords("42") is None


# ===========================================================================
# NDS path tests
# ===========================================================================

def test_nds_center_coordinate(monkeypatch):
    """Reply '(500,500)' on a (384,256,3) frame → ("touch", 128, 96) (center of 256×192)."""
    monkeypatch.setattr(_nav_mod.litellm, "completion", _fake_completion("(500,500)"))
    nav = UITARSNavigator(console="nds")
    result = nav.decide(_nds_frame())
    assert result == ("touch", 128, 96), f"got {result}"


def test_nds_scales_correctly(monkeypatch):
    """Reply '(250,750)' → x=round(250/1000*256)=64, y=round(750/1000*192)=144."""
    monkeypatch.setattr(_nav_mod.litellm, "completion", _fake_completion("(250,750)"))
    nav = UITARSNavigator(console="nds")
    result = nav.decide(_nds_frame())
    assert result == ("touch", 64, 144), f"got {result}"


def test_nds_coords_clamped_max(monkeypatch):
    """Reply '(1000,1000)' → ("touch", 255, 191) (clamped to W-1, H-1 of bottom screen)."""
    monkeypatch.setattr(_nav_mod.litellm, "completion", _fake_completion("(1000,1000)"))
    nav = UITARSNavigator(console="nds")
    result = nav.decide(_nds_frame())
    assert result == ("touch", 255, 191), f"got {result}"


def test_nds_coords_clamped_min(monkeypatch):
    """Reply '(0,0)' → ("touch", 0, 0)."""
    monkeypatch.setattr(_nav_mod.litellm, "completion", _fake_completion("(0,0)"))
    nav = UITARSNavigator(console="nds")
    result = nav.decide(_nds_frame())
    assert result == ("touch", 0, 0), f"got {result}"


def test_nds_parse_fail_returns_a(monkeypatch):
    """Unparseable reply → 'a' fallback."""
    monkeypatch.setattr(_nav_mod.litellm, "completion", _fake_completion("I cannot determine"))
    nav = UITARSNavigator(console="nds")
    result = nav.decide(_nds_frame())
    assert result == "a"


def test_nds_action_wrapped_reply(monkeypatch):
    """Real UI-TARS-style 'click(point=\'(499,637)\')' still parses correctly."""
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        _fake_completion("click(point='(499,637)')"))
    nav = UITARSNavigator(console="nds")
    result = nav.decide(_nds_frame())
    # bottom screen 256×192: x=round(499/1000*256)=128, y=round(637/1000*192)=122
    assert result == ("touch", 128, 122), f"got {result}"


def test_nds_sends_only_bottom_screen(monkeypatch):
    """The image sent to UI-TARS must be the bottom half of the dual frame only,
    as a user message with only an image (no text); system message carries the task."""
    captured = {}

    def fake_completion(**kw):
        captured["messages"] = kw["messages"]
        return _FakeCompletion("(500,500)")

    monkeypatch.setattr(_nav_mod.litellm, "completion", fake_completion)

    # Build a dual frame where top is all-white and bottom is all-black.
    frame = np.zeros((384, 256, 3), dtype=np.uint8)
    frame[:192, :, :] = 255   # top screen white
    frame[192:, :, :] = 0     # bottom screen black

    nav = UITARSNavigator(console="nds")
    nav.decide(frame)

    msgs = captured["messages"]
    # system message contains "GUI agent" + task text
    assert msgs[0]["role"] == "system"
    assert "GUI agent" in msgs[0]["content"]
    assert _nav_mod._UITARS_PROMPT_TOUCH in msgs[0]["content"]
    # user message is image-only
    assert msgs[1]["role"] == "user"
    content = msgs[1]["content"]
    types = [c.get("type") for c in content]
    assert "image_url" in types
    assert "text" not in types


def test_nds_returns_tuple_not_str(monkeypatch):
    """NDS path must return a tuple, not a string."""
    monkeypatch.setattr(_nav_mod.litellm, "completion", _fake_completion("(500,500)"))
    nav = UITARSNavigator(console="nds")
    result = nav.decide(_nds_frame())
    assert isinstance(result, tuple), f"expected tuple, got {type(result)}"


# ===========================================================================
# GB path tests (experimental grounding bridge)
# ===========================================================================

def test_gb_target_above_cursor_returns_up(monkeypatch):
    """target y=200, cursor y=700 (normalized) → target is above cursor → 'up'."""
    # Query order: first call = target, second call = cursor.
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        _side_effect_completion(["(500,200)", "(500,700)"]))
    nav = UITARSNavigator(console="gb")
    result = nav.decide(_gb_frame())
    assert result == "up", f"got {result!r}"


def test_gb_target_below_cursor_returns_down(monkeypatch):
    """target y=700, cursor y=200 → 'down'."""
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        _side_effect_completion(["(500,700)", "(500,200)"]))
    nav = UITARSNavigator(console="gb")
    result = nav.decide(_gb_frame())
    assert result == "down", f"got {result!r}"


def test_gb_aligned_returns_a(monkeypatch):
    """target and cursor at same y (within 8% threshold) → 'a'."""
    # Both at y=500: diff = 0, well within threshold.
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        _side_effect_completion(["(500,500)", "(500,500)"]))
    nav = UITARSNavigator(console="gb")
    result = nav.decide(_gb_frame())
    assert result == "a", f"got {result!r}"


def test_gb_aligned_within_threshold_returns_a(monkeypatch):
    """target y=500, cursor y=510 (1% diff on 144px frame = 1.44px < 11.52px thresh) → 'a'."""
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        _side_effect_completion(["(500,500)", "(500,510)"]))
    nav = UITARSNavigator(console="gb")
    result = nav.decide(_gb_frame())
    assert result == "a", f"got {result!r}"


def test_gb_query_fail_returns_fallback(monkeypatch):
    """If first query fails (returns 'no coord'), fall back to 'start'."""
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        _fake_completion("I cannot determine the position"))
    nav = UITARSNavigator(console="gb")
    result = nav.decide(_gb_frame())
    assert result in ("start",) + _nav_mod._FALLBACK_CYCLE, f"unexpected fallback {result!r}"


def test_gb_exception_in_query_no_raise(monkeypatch):
    """If litellm raises, decide() must not raise — returns a fallback."""
    def _raise(**kw):
        raise RuntimeError("network error")

    monkeypatch.setattr(_nav_mod.litellm, "completion", _raise)
    nav = UITARSNavigator(console="gb")
    try:
        result = nav.decide(_gb_frame())
    except Exception as exc:
        pytest.fail(f"UITARSNavigator.decide() raised unexpectedly: {exc}")
    assert isinstance(result, str)


def test_gba_console_behaves_like_gb(monkeypatch):
    """console='gba' uses the same grounding bridge; 'up' is returned for target-above-cursor."""
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        _side_effect_completion(["(500,100)", "(500,900)"]))
    nav = UITARSNavigator(console="gba")
    result = nav.decide(_gb_frame())
    assert result == "up", f"got {result!r}"


# ===========================================================================
# Import safety
# ===========================================================================

def test_uitars_navigator_constructs_default():
    """UITARSNavigator() with default args constructs without importing any unavailable dep."""
    try:
        nav = UITARSNavigator()
        assert nav.console == "nds"
        assert nav.model == "openai/uitars"
        assert nav.api_base == "http://localhost:8080/v1"
        assert nav.upscale == 3
    except ImportError as exc:
        pytest.fail(f"UITARSNavigator() raised ImportError: {exc}")


def test_uitars_navigator_constructs_gb():
    nav = UITARSNavigator(console="gb")
    assert nav.console == "gb"


# ===========================================================================
# bakeoff._stepper integration
# ===========================================================================

def test_stepper_uitars_nds(monkeypatch):
    """_stepper('uitars-nds') returns a one-element list containing a touch tuple or 'a'."""
    monkeypatch.setattr(_nav_mod.litellm, "completion", _fake_completion("(500,500)"))
    from eval.bakeoff import _stepper
    step = _stepper("uitars-nds")
    result = step(None, _nds_frame(), [])
    assert isinstance(result, list) and len(result) == 1
    action = result[0]
    assert isinstance(action, tuple) or action == "a", f"got {action!r}"


def test_stepper_uitars_gb(monkeypatch):
    """_stepper('uitars-gb') returns a one-element list with a string button."""
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        _side_effect_completion(["(500,200)", "(500,700)"]))
    from eval.bakeoff import _stepper
    step = _stepper("uitars-gb")
    result = step(None, _gb_frame(), [])
    assert isinstance(result, list) and len(result) == 1
    assert isinstance(result[0], str)


def test_stepper_uitars_gba(monkeypatch):
    """_stepper('uitars-gba') returns a one-element list with a string button."""
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        _side_effect_completion(["(500,700)", "(500,200)"]))
    from eval.bakeoff import _stepper
    step = _stepper("uitars-gba")
    result = step(None, _gb_frame(), [])
    assert isinstance(result, list) and len(result) == 1
    assert isinstance(result[0], str)


# ===========================================================================
# FIX #1 — GB-bridge fallback rotation
# ===========================================================================

def test_gb_fallback_rotates_on_repeated_parse_failure(monkeypatch):
    """_decide_gb must ROTATE through _FALLBACK_CYCLE when _query returns None.

    Both queries return an unparseable string, so target and cursor are None.
    The first call must return "start" (the initial rotation position) and the
    second call must return a DIFFERENT button, proving _next_fallback() is live.
    """
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        _fake_completion("no coordinates here"))
    nav = UITARSNavigator(console="gb")

    first = nav.decide(_gb_frame())
    second = nav.decide(_gb_frame())

    assert first == "start", f"expected 'start' first, got {first!r}"
    assert second != "start", f"second call should advance beyond 'start', got {second!r}"
    assert second in _nav_mod._FALLBACK_CYCLE, f"unexpected button {second!r}"


# ===========================================================================
# FIX #5 — _parse_uitars_coords handles both v1 and doubao formats
# ===========================================================================

def test_parse_v1_start_box_format():
    """v1 start_box='<|box_start|>(235,512)<|box_end|>' → (235, 512)."""
    text = "Action: click(start_box='<|box_start|>(235,512)<|box_end|>')"
    assert _parse_uitars_coords(text) == (235, 512)


def test_parse_doubao_point_format():
    """doubao <point>235 512</point> → (235, 512)."""
    text = "<point>235 512</point>"
    assert _parse_uitars_coords(text) == (235, 512)


def test_parse_doubao_point_with_whitespace():
    """<point> with extra whitespace around numbers still parses."""
    text = "Action: <point>  100  200  </point>"
    assert _parse_uitars_coords(text) == (100, 200)
