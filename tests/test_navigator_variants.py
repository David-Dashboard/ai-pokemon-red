"""Unit tests for the three new navigator variants (feat/nds-reachability bake-off).

LadderLLMNavigator  — kinds ladder-llm
MemNavigator        — kinds vlm-mem
VLMNavigator(primed=True)  / MenuPerceiverNavigator(primed=True)  — kinds vlm-prime / ocr-prime

All tests monkeypatch core.navigators.litellm.completion; no real llama-server, no py-desmume.
Style mirrors tests/test_nds_touch_navigator.py.
"""
from __future__ import annotations

import numpy as np
import pytest

import core.navigators as _nav_mod
from core.navigators import (
    BUTTONS,
    LadderLLMNavigator,
    MemNavigator,
    MenuPerceiverNavigator,
    VLMNavigator,
    _FALLBACK_CYCLE,
    _PROMPT_PRIMED,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeChoice:
    def __init__(self, text: str):
        self.message = type("M", (), {"content": text})()


class _FakeCompletion:
    def __init__(self, text: str):
        self.choices = [_FakeChoice(text)]


def _blank_frame(h: int = 144, w: int = 160) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def _random_frame(seed: int = 0, h: int = 144, w: int = 160) -> np.ndarray:
    rng = np.random.RandomState(seed)
    return rng.randint(0, 256, (h, w, 3), dtype=np.uint8)


# ===========================================================================
# LadderLLMNavigator tests
# ===========================================================================

def test_ladder_llm_returns_ladder_button_when_not_stalled():
    """When the screen keeps changing, no LLM call should be made; ladder button is returned."""
    nav = LadderLLMNavigator()
    calls = []
    # Each call to decide() gets a genuinely different frame → never stalls.
    for i in range(5):
        frame = _random_frame(seed=i * 100)
        result = nav.decide(frame)
        calls.append(result)
    assert nav.wakes == 0, f"Expected 0 LLM wakes, got {nav.wakes}"
    assert all(r in BUTTONS for r in calls)


def test_ladder_llm_wakes_llm_on_cycle_stall(monkeypatch):
    """When the same set of frames repeats for _NOVELTY_WINDOW steps, LLM is woken once."""
    nav = LadderLLMNavigator()
    llm_calls = []

    def fake_completion(**kw):
        llm_calls.append(kw)
        return _FakeCompletion("ACTION: start")

    monkeypatch.setattr(_nav_mod.litellm, "completion", fake_completion)

    # Feed the exact same frame _NOVELTY_WINDOW + 1 times so the ring fills with
    # fingerprints all seen before → triggers stall.
    frame = _blank_frame()  # constant → all fingerprints identical
    for _ in range(_nav_mod._NOVELTY_WINDOW + 2):
        nav.decide(frame)

    assert nav.wakes >= 1, "LLM should have been woken at least once on a cycling screen"
    assert len(llm_calls) >= 1


def test_ladder_llm_wakes_return_parsed_button(monkeypatch):
    """On stall, the parsed LLM button is returned, not the ladder's default."""
    nav = LadderLLMNavigator()

    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion("ACTION: b"))

    frame = _blank_frame()
    result = None
    for _ in range(_nav_mod._NOVELTY_WINDOW + 2):
        result = nav.decide(frame)

    # After stall triggers, last result should be "b" (the LLM's answer).
    assert result == "b", f"Expected 'b' from stalled LLM, got {result!r}"


# ===========================================================================
# MemNavigator tests
# ===========================================================================

def test_mem_navigator_overrides_dead_button(monkeypatch):
    """After recording a button as no-effect twice on the same screen, decide() must not return it."""
    nav = MemNavigator(mode="vlm")

    # LLM always wants to press "a" — we'll make "a" dead.
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion("Thought: try a\nAction: a"))

    frame = _blank_frame()
    same_frame = _blank_frame()  # identical → no change → effective=False

    # First call: sets up self._prev, records nothing (no _last_btn yet).
    nav.decide(frame)
    # Second call: records ("a", effective=False) for the blank-frame key.
    nav.decide(same_frame)
    # Third call: records ("a", effective=False) again → "a" now dead (dead_after=2).
    nav.decide(same_frame)
    # Fourth call: "a" is dead; override must kick in.
    result = nav.decide(same_frame)
    assert result != "a", (
        f"MemNavigator should have overridden dead 'a' but returned {result!r}"
    )
    assert result in BUTTONS


def test_mem_navigator_parses_and_retains_lesson(monkeypatch):
    """A 'Lesson: ...' line in the model reply is parsed and stored in self._lessons."""
    nav = MemNavigator(mode="vlm")

    raw_with_lesson = "Thought: stuck\nAction: start\nLesson: Press start to finish name entry"
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion(raw_with_lesson))

    nav.decide(_random_frame(0))
    nav.decide(_random_frame(1))

    assert len(nav._lessons) == 1
    assert "start" in nav._lessons[0].lower() or "name" in nav._lessons[0].lower()


def test_mem_navigator_lesson_survives_trim(monkeypatch):
    """Lessons stored in self._lessons are not in the trimmed conversation tail."""
    nav = MemNavigator(mode="vlm", keep_turns=2)

    lesson_text = "Always press start on name grids"
    call_count = [0]

    def fake_completion(**kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return _FakeCompletion(f"Thought: ok\nAction: start\nLesson: {lesson_text}")
        return _FakeCompletion("Thought: continue\nAction: a")

    monkeypatch.setattr(_nav_mod.litellm, "completion", fake_completion)

    # Drive enough turns to trigger trim (keep_turns=2 → trims at 5 messages).
    for i in range(6):
        nav.decide(_random_frame(i))

    # Lesson must still be in nav._lessons even after trimming.
    assert any(lesson_text in l for l in nav._lessons), (
        f"Lesson was lost after trim; nav._lessons = {nav._lessons}"
    )


def test_mem_navigator_lesson_dedup(monkeypatch):
    """Duplicate lessons are not appended twice."""
    nav = MemNavigator(mode="vlm")

    same_lesson = "Never press b on title screen"
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion(f"Thought: x\nAction: a\nLesson: {same_lesson}"))

    for i in range(4):
        nav.decide(_random_frame(i))

    assert nav._lessons.count(same_lesson) == 1, "Duplicate lesson should not be stored twice"


# ===========================================================================
# Regression tests for two logged variant bugs (2026-07-01 HANDOFF block)
# ===========================================================================

def test_mem_navigator_appends_recent_once_per_step(monkeypatch):
    """MemNavigator must grow _recent by exactly 1 per decide().

    Previously it called _stalled() itself AND super().decide() called it again, so _recent
    grew by 2 per step → the ~6-frame stall window fired at ~3. The fix routes MemNavigator
    through the non-mutating _stall_peek()."""
    nav = MemNavigator(mode="vlm")
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion("Thought: x\nAction: a"))
    for i in range(5):
        nav.decide(_random_frame(seed=i))
    assert len(nav._recent) == 5, (
        f"_recent should grow 1/step (got {len(nav._recent)} after 5 steps — double-append bug)"
    )


def test_ladder_llm_resets_esc_after_wake(monkeypatch):
    """After an LLM wake the escape ladder must restart from the top (_esc == 0).

    Without the reset the ladder resumes mid-rotation on the post-wake screen and presses a
    stale move, derailing a screen the fresh ladder would have cleared."""
    nav = LadderLLMNavigator()
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion("ACTION: b"))
    # Constant frame → ladder advances _esc while not yet stalled, then a novelty-stall wakes
    # the LLM; the wake must reset _esc back to 0.
    for _ in range(_nav_mod._NOVELTY_WINDOW + 2):
        nav.decide(_blank_frame())
    assert nav.wakes >= 1, "the constant frame should have triggered at least one wake"
    assert nav._policy._esc == 0, f"_esc should be reset to 0 after a wake, got {nav._policy._esc}"


# ===========================================================================
# Primed navigator tests
# ===========================================================================

def test_vlm_prime_uses_prompt_primed(monkeypatch):
    """VLMNavigator(primed=True) sends _PROMPT_PRIMED, not _PROMPT."""
    captured = {}

    def fake_completion(**kw):
        captured["messages"] = kw["messages"]
        return _FakeCompletion("a")

    monkeypatch.setattr(_nav_mod.litellm, "completion", fake_completion)
    nav = VLMNavigator(primed=True)
    nav.decide(_blank_frame())

    content = captured["messages"][0]["content"]
    text = " ".join(c["text"] for c in content if c.get("type") == "text")
    assert "name-entry" in text or "letter grid" in text, (
        "vlm-prime must use _PROMPT_PRIMED; 'name-entry' / 'letter grid' hint missing"
    )


def test_ocr_prime_uses_prompt_primed(monkeypatch):
    """MenuPerceiverNavigator(primed=True) prompt includes the name-entry rule."""
    captured = {}

    def fake_completion(**kw):
        captured["messages"] = kw["messages"]
        return _FakeCompletion("a")

    # Stub out RapidOCR so no heavy dep needed.
    class _FakeOCR:
        def __call__(self, img):
            return None, None

    monkeypatch.setattr(_nav_mod.litellm, "completion", fake_completion)
    nav = MenuPerceiverNavigator(primed=True)
    nav._ocr = _FakeOCR()
    nav.decide(_blank_frame())

    msg_text = str(captured["messages"])
    assert "name-entry" in msg_text or "letter grid" in msg_text, (
        "ocr-prime must use _PROMPT_PRIMED"
    )


def test_vlm_prime_fallback_rotates(monkeypatch):
    """VLMNavigator(primed=True) rotates through _FALLBACK_CYCLE on unparseable replies."""
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion("banana"))

    nav = VLMNavigator(primed=True)
    results = [nav.decide(_blank_frame()) for _ in range(len(_FALLBACK_CYCLE) + 2)]

    for i, r in enumerate(results[:len(_FALLBACK_CYCLE)]):
        assert r == _FALLBACK_CYCLE[i], f"step {i}: expected {_FALLBACK_CYCLE[i]}, got {r}"
    # Wraps around.
    assert results[len(_FALLBACK_CYCLE)] == _FALLBACK_CYCLE[0]


def test_ocr_prime_fallback_rotates(monkeypatch):
    """MenuPerceiverNavigator(primed=True) rotates through _FALLBACK_CYCLE on bad replies."""
    class _FakeOCR:
        def __call__(self, img):
            return None, None

    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion("banana"))

    nav = MenuPerceiverNavigator(primed=True)
    nav._ocr = _FakeOCR()
    results = [nav.decide(_blank_frame()) for _ in range(len(_FALLBACK_CYCLE) + 1)]

    for i, r in enumerate(results[:len(_FALLBACK_CYCLE)]):
        assert r == _FALLBACK_CYCLE[i], f"step {i}: expected {_FALLBACK_CYCLE[i]}, got {r}"


def test_vlm_unprimed_fallback_is_a(monkeypatch):
    """VLMNavigator(primed=False, default) still falls back to 'a' on bad reply."""
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion("banana"))
    nav = VLMNavigator()
    assert nav.decide(_blank_frame()) == "a"


# ===========================================================================
# bakeoff._stepper integration
# ===========================================================================

def test_stepper_ladder_llm(monkeypatch):
    """_stepper('ladder-llm') builds and calls LadderLLMNavigator; returns one-element list."""
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion("a"))
    from eval.bakeoff import _stepper
    step = _stepper("ladder-llm")
    result = step(None, _random_frame(0), [])
    assert isinstance(result, list) and len(result) == 1
    assert result[0] in BUTTONS


def test_stepper_vlm_prime(monkeypatch):
    """_stepper('vlm-prime') returns one-element list."""
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion("start"))
    from eval.bakeoff import _stepper
    step = _stepper("vlm-prime")
    result = step(None, _blank_frame(), [])
    assert isinstance(result, list) and len(result) == 1 and result[0] in BUTTONS


def test_stepper_vlm_mem(monkeypatch):
    """_stepper('vlm-mem') returns one-element list."""
    monkeypatch.setattr(_nav_mod.litellm, "completion",
                        lambda **kw: _FakeCompletion("Thought: ok\nAction: a"))
    from eval.bakeoff import _stepper
    step = _stepper("vlm-mem")
    result = step(None, _blank_frame(), [])
    assert isinstance(result, list) and len(result) == 1 and result[0] in BUTTONS


# ===========================================================================
# Regression: existing navigators unchanged
# ===========================================================================

def test_vlm_unprimed_uses_8_button_set():
    """VLMNavigator() (no primed arg) retains 8-button BUTTONS."""
    assert VLMNavigator().buttons == BUTTONS
    assert len(BUTTONS) == 8


def test_menu_perceiver_unprimed_uses_8_button_set():
    assert MenuPerceiverNavigator().buttons == BUTTONS
