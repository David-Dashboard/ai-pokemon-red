"""PATIENCE tests (2026-07-02 design) — no ROM, no PyBoy.

Covers:
  1. State classification: {gated-static, choice, free-control} from `SymbolicState.context`, incl. on
     REAL recorded frames (eval/fixtures/starter_cutscene_pose/ — a genuine Red dialog frame decoded by
     `detect_mode`), so the classifier is exercised against actual pixels, not just label strings.
  2. Learned-button mechanics: AdvanceLearner tries candidates, locks in whichever one changes the
     gated screen, and never re-tries others afterward — the Emerald-naming-screen case ('a' loops,
     'start' confirms).
  3. Closed-loop FREE proof: PerceptionPlugin.observe() auto-advances a scripted dialog chain to
     completion with ZERO extra brain-visible decisions, waking (stopping) exactly at the first choice.
     Traceability: `patience_advances` on the returned Observation counts the free presses.
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pytest

from core.patience import (
    AdvanceLearner,
    DEFAULT_BUDGET,
    Patience,
    classify,
)
from core.perception import PerceptMemory, SymbolicState
from games.pokemon_red.perceiver import detect_mode
from games.pokemon_red import PokemonRedPlugin
from tests.test_pokemon_red import FakeEmulator

_FIXTURE_DIR = os.path.join("eval", "fixtures", "starter_cutscene_pose")


def _fixture(name: str) -> np.ndarray:
    from PIL import Image
    return np.array(Image.open(os.path.join(_FIXTURE_DIR, name)).convert("RGB"))


# -- 1. classification ---------------------------------------------------------

@pytest.mark.parametrize("context", ["dialog", "battle_text", "static"])
def test_classify_gated_static_contexts(context):
    assert classify(context) == "gated-static"


@pytest.mark.parametrize("context", ["menu", "battle"])
def test_classify_choice_contexts_never_advance(context):
    assert classify(context) == "choice"


@pytest.mark.parametrize("context", ["overworld", "gameplay"])
def test_classify_free_control_contexts(context):
    assert classify(context) == "free-control"


@pytest.mark.parametrize("context", ["unknown", "battle_menu", "something_new_a_future_world_emits"])
def test_classify_unsure_defaults_to_choice_fail_safe(context):
    # The erase-save guard: any context this module doesn't positively recognize must NEVER be
    # auto-advanced, so an unrecognized/novel label is treated as a choice (wake), never gated-static.
    assert classify(context) == "choice"


def test_classify_on_a_real_recorded_dialog_frame():
    """The fixture holds a genuine Oak-cutscene dialog frame (frame_000544.png) — decode it with the
    real detect_mode (pixels only, no RAM) and confirm the resulting context classifies gated-static."""
    frame = _fixture("frame_000544.png")
    assert detect_mode(frame) == "dialog"
    assert classify(detect_mode(frame)) == "gated-static"


def test_classify_on_a_real_recorded_overworld_frame_is_free_control():
    frame = _fixture("frame_000049.png")
    assert detect_mode(frame) == "overworld"
    assert classify(detect_mode(frame)) == "free-control"


# -- 2. learned-button mechanics ------------------------------------------------

def test_advance_learner_locks_in_the_first_candidate_that_changes_the_screen():
    learner = AdvanceLearner(candidates=("a", "start", "b"))
    assert learner.learned is None
    assert learner.next_candidate() == "a"      # tries 'a' first...
    learner.confirm("a")                        # ...and it worked -> lock it in
    assert learner.learned == "a"
    assert learner.next_candidate() == "a"       # never tries 'start'/'b' again
    assert learner.next_candidate() == "a"


def test_advance_learner_emerald_naming_screen_a_loops_start_confirms():
    """The exact live-audit case: 'a' does NOT change the gated naming screen (it loops), so the
    learner must cycle to 'start' and lock THAT in — never getting stuck retrying 'a' forever."""
    learner = AdvanceLearner(candidates=("a", "start", "b"))

    def press(button: str) -> str:
        return "gated-static" if button == "a" else "free-control"   # 'a' loops; 'start' confirms

    context = "gated-static"
    for _ in range(len(learner._candidates) + 1):
        b = learner.next_candidate()
        new_context = press(b)
        if new_context != context and learner.learned is None:
            learner.confirm(b)
        context = new_context
        if context != "gated-static":
            break
    assert learner.learned == "start"
    assert context == "free-control"


def test_advance_learner_cycles_candidates_until_one_confirms():
    learner = AdvanceLearner(candidates=("a", "start", "b"))
    assert [learner.next_candidate() for _ in range(4)] == ["a", "start", "b", "a"]


# -- Patience.advance() unit-level (fake press callback, no plugin) ------------

def test_patience_advance_stops_the_instant_context_leaves_gated_static():
    p = Patience(budget=DEFAULT_BUDGET)
    calls = {"n": 0}

    def press(button: str):
        calls["n"] += 1
        ctx = "dialog" if calls["n"] < 3 else "overworld"
        return ctx, True   # every press visibly changes something (a new line, then a real transition)

    final_context, n = p.advance("dialog", press)
    assert final_context == "overworld"
    assert n == 3
    assert p.total_advanced == 3


def test_patience_advance_never_touches_a_choice_context():
    p = Patience()
    press_called = {"n": 0}

    def press(button: str):
        press_called["n"] += 1
        return "choice", True

    final_context, n = p.advance("choice", press)  # already a choice -> classify() != gated-static
    assert n == 0 and press_called["n"] == 0
    assert final_context == "choice"


def test_patience_advance_respects_the_budget_cap():
    p = Patience(budget=5)

    def press(button: str):
        return "dialog", True   # never resolves — a stuck/never-advanceable screen

    final_context, n = p.advance("dialog", press)
    assert n == 5                       # stopped at the cap, not an infinite loop
    assert final_context == "dialog"   # still gated-static -> the caller (observe()) surfaces it, wakes the brain


def test_patience_advance_learns_the_button_once_and_reuses_it():
    p = Patience(candidates=("a", "start"))
    presses = []

    def press(button: str):
        presses.append(button)
        # 'a' loops (no-op, no visible change); 'start' confirms. Two frames in this scripted chain.
        if button == "a":
            return "dialog", False
        return "overworld", True

    final_context, n = p.advance("dialog", press)
    assert final_context == "overworld"
    assert presses == ["a", "start"]
    assert p.learner.learned == "start"


def test_patience_advance_does_not_confirm_a_no_op_button():
    """A button that produces IDENTICAL output (changed=False) must never be locked in as the advance
    button, even if it happens to be tried — only a button with an OBSERVED effect earns the lock."""
    p = Patience(candidates=("a", "start"))

    def press(button: str):
        # both buttons are no-ops for the first two tries; 'start' only works on its 2nd try (index 3).
        if button == "start" and p.learner._tried_idx >= 3:
            return "overworld", True
        return "dialog", False

    final_context, n = p.advance("dialog", press)
    assert final_context == "overworld"
    assert p.learner.learned == "start"   # locked onto the button that actually worked, not the first tried


# -- 3. closed-loop FREE proof, via the real plugin (no ROM) -------------------

class _ScriptedDialogEmulator(FakeEmulator):
    """A FakeEmulator whose screen advances through a scripted (context) chain as `press()` is called —
    stands in for a real Red dialog-then-choice cutscene without a ROM. `_frame_for` maps a step index
    to a context label; `screen_ndarray()` is monkeypatched per-step by the test via `_ctx_sequence`."""

    def __init__(self, ctx_sequence: list[str]) -> None:
        super().__init__()
        self._ctx_sequence = list(ctx_sequence)   # context BEFORE any press (index 0), then after each press
        self._step = 0
        self._advance_button = "a"   # the world's real (scripted) advance input for this test
        self._screen = np.full((144, 160, 4), self._step, dtype=np.uint8)   # seed to match step 0

    def press(self, button, hold_frames=8, settle_frames=16):
        super().press(button, hold_frames=hold_frames, settle_frames=settle_frames)
        if button == self._advance_button and self._step < len(self._ctx_sequence) - 1:
            self._step += 1   # only the learned/correct button advances the script (others no-op)
        # A pixel keyed to the SCRIPT STEP (not the button tried): only changes when _step actually
        # advances, so a true no-op button (Emerald's 'a' on the naming screen) produces an IDENTICAL
        # frame — exercising the plugin's raw-pixel-diff "changed" fallback for gated-static screens
        # with no decoded text (a generic world's title/naming screen has no screen_text at all).
        self._screen = np.full((144, 160, 4), self._step, dtype=np.uint8)

    def current_context(self) -> str:
        return self._ctx_sequence[self._step]


class _ScriptedPerceiver:
    """Perceiver stand-in that reads the context straight off the ScriptedDialogEmulator's script
    position (via a closure over the emu), so PerceptionPlugin.observe() drives a REAL gated-static ->
    choice transition through the REAL Patience loop without needing pixel decoding or a ROM."""

    def __init__(self, emu: _ScriptedDialogEmulator) -> None:
        self._emu = emu

    def perceive(self, frame, memory: PerceptMemory, context=None) -> SymbolicState:
        ctx_label = self._emu.current_context()
        return SymbolicState(confidence=0.9, context=ctx_label,
                             last_action={"action": (context or {}).get("last_action"), "outcome": "n/a"},
                             screen_text=f"line {self._emu._step}" if ctx_label == "dialog" else "",
                             raw_available=False, raw_ref="")


def test_closed_loop_free_advance_through_a_dialog_chain_wakes_only_at_the_choice(tmp_path):
    """The mandated closed-loop proof (scripted, no ROM/LLM): a chain of N plain dialog frames followed
    by a real choice. A single observe() call must auto-advance the ENTIRE dialog chain for free and
    return an Observation whose context is the CHOICE — the brain wakes exactly once (this one observe
    call), never once per dialog line."""
    n_dialog_lines = 12
    script = ["dialog"] * n_dialog_lines + ["menu"]   # menu = a real YES/NO choice -> must NOT auto-advance
    emu = _ScriptedDialogEmulator(script)
    perceiver = _ScriptedPerceiver(emu)
    plugin = PokemonRedPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=perceiver)

    obs = plugin.observe("agent")

    assert obs.data["context"] == "menu"                     # stopped exactly at the choice
    assert obs.data["patience_advances"] == n_dialog_lines    # every dialog line was advanced for free
    assert plugin.patience.learner.learned == "a"             # learned Red's real advance button: A

    # A second observe() (simulating the brain now waking and deciding) must NOT auto-advance further —
    # 'menu' is a choice context, so classify() keeps it there until the brain itself acts.
    obs2 = plugin.observe("agent")
    assert obs2.data["context"] == "menu"
    assert obs2.data["patience_advances"] == 0


def test_closed_loop_free_advance_learns_start_when_a_loops(tmp_path):
    """The Emerald-naming-screen case reproduced through the real plugin: 'a' is tried first (the
    default candidate ladder) but does not advance the gated screen; 'start' does. Patience must
    discover this live (no hardcoded button) and land on free-control with the full budget unspent."""
    script = ["static"] * 3 + ["overworld"]
    emu = _ScriptedDialogEmulator(script)
    emu._advance_button = "start"   # only 'start' actually confirms this naming screen
    perceiver = _ScriptedPerceiver(emu)
    plugin = PokemonRedPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=perceiver)

    obs = plugin.observe("agent")

    assert obs.data["context"] == "overworld"
    assert plugin.patience.learner.learned == "start"
    # 'a' was tried once (wasted, correctly, on the first static frame), then 'start' locked in and
    # resolved the 3 remaining static->...->overworld script transitions: 1 + 3 = 4 free presses total.
    assert obs.data["patience_advances"] == 4


def test_closed_loop_never_auto_advances_a_choice_even_if_it_looks_static(tmp_path):
    """Fail-safe check: a script that starts life ALREADY at a choice must wake immediately (zero free
    advances), even though the plugin has never seen this world before and has no learned button yet."""
    script = ["menu"]
    emu = _ScriptedDialogEmulator(script)
    perceiver = _ScriptedPerceiver(emu)
    plugin = PokemonRedPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=perceiver)

    obs = plugin.observe("agent")

    assert obs.data["context"] == "menu"
    assert obs.data["patience_advances"] == 0
    assert plugin.patience.learner.learned is None   # never even tried — nothing to learn from a choice


def test_closed_loop_budget_caps_a_never_advancing_screen(tmp_path):
    """A pathological screen that never resolves (bad candidate ladder / genuinely stuck) still stops
    at DEFAULT_BUDGET and surfaces to the brain, rather than hanging the world forever for free."""
    script = ["dialog"] * (DEFAULT_BUDGET + 20)   # never reaches the end within the budget
    emu = _ScriptedDialogEmulator(script)
    emu._advance_button = "__never__"   # no candidate button will ever advance this screen
    perceiver = _ScriptedPerceiver(emu)
    plugin = PokemonRedPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=perceiver)

    obs = plugin.observe("agent")

    assert obs.data["context"] == "dialog"            # still gated-static: the brain gets woken by the caller
    assert obs.data["patience_advances"] == DEFAULT_BUDGET
