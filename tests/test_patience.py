"""PATIENCE tests (2026-07-02 design; hardened per the PR #49 adversarial reviews) — no ROM, no PyBoy.

Covers:
  1. State classification: {gated-static, choice, free-control} from `SymbolicState.context`, incl. on
     REAL recorded frames — a genuine Red dialog frame (eval/fixtures/starter_cutscene_pose/) must be
     gated-static, and a REAL Kirby save/menu screen (eval/fixtures/kirby_title_menu/) that reads
     "static" under `detect_modality` must classify as CHOICE (the S1 blocker: "static" is a motion
     label, not a no-choice guarantee — an idle save menu is frozen too and must NEVER be blind-pressed).
  2. Learned-button mechanics: per-context lock, effect-seen-TWICE before locking (S3 animation
     mis-lock), unlock after repeated failures, and the Emerald-naming-screen case ('a' loops,
     'start' confirms) via the per-world OPT-IN path.
  3. Budget: per-EPISODE (persists across observe() calls — S2: a stuck screen burns the budget once,
     not once per turn), re-armed only by leaving gated-static or a NEW brain action.
  4. Closed-loop FREE proof: PerceptionPlugin.observe() auto-advances a scripted dialog chain in one
     call, waking exactly at the first choice; the advanced-past text is surfaced in the render and
     the per-press trail lands in oracle.jsonl (S4).
  5. Attribution (S5): a patience press must not be mistaken for a brain-commanded MOVE by the pose
     machine when the loop exits into the overworld.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pytest

from core.modality import detect_modality
from core.patience import (
    AdvanceLearner,
    DEFAULT_BUDGET,
    Patience,
    classify,
)
from core.perception import PerceptMemory, SymbolicState
from games.pokemon_red.perceiver import OverworldPerceiver, detect_mode
from games.pokemon_red import PokemonRedPlugin
from tests.test_pokemon_red import FakeEmulator

_RED_FIXTURES = os.path.join("eval", "fixtures", "starter_cutscene_pose")
_KIRBY_FIXTURES = os.path.join("eval", "fixtures", "kirby_title_menu")


def _fixture(dirname: str, name: str) -> np.ndarray:
    from PIL import Image
    return np.array(Image.open(os.path.join(dirname, name)).convert("RGB"))


# -- 1. classification ---------------------------------------------------------

@pytest.mark.parametrize("context", ["dialog", "battle_text"])
def test_classify_gated_static_contexts(context):
    assert classify(context) == "gated-static"


@pytest.mark.parametrize("context", ["menu", "battle"])
def test_classify_choice_contexts_never_advance(context):
    assert classify(context) == "choice"


@pytest.mark.parametrize("context", ["overworld", "gameplay"])
def test_classify_free_control_contexts(context):
    assert classify(context) == "free-control"


@pytest.mark.parametrize("context", ["static", "unknown", "battle_menu",
                                     "something_new_a_future_world_emits"])
def test_classify_unsure_defaults_to_choice_fail_safe(context):
    # The erase-save guard: any context not positively KNOWN to be a no-choice screen must NEVER be
    # auto-advanced. This now includes "static" (PR #49 S1): detect_modality's "static" means "nothing
    # moved since last frame" — an idle save-select menu is frozen too, so it is NOT a semantics label.
    assert classify(context) == "choice"


def test_classify_static_can_be_opted_in_per_world():
    """The per-world opt-in knob (S1 fix): a world that vouches for its gated-static signal passes
    Patience(extra_gated_contexts=...); every OTHER world's default stays fail-safe."""
    p = Patience(extra_gated_contexts=("static",))
    assert p.classify("static") == "gated-static"
    assert Patience().classify("static") == "choice"          # the default is OFF
    assert p.classify("menu") == "choice"                     # opting in static does not loosen menu


def test_classify_on_a_real_recorded_dialog_frame():
    """The fixture holds a genuine Oak-cutscene dialog frame (frame_000544.png) — decode it with the
    real detect_mode (pixels only, no RAM) and confirm the resulting context classifies gated-static."""
    frame = _fixture(_RED_FIXTURES, "frame_000544.png")
    assert detect_mode(frame) == "dialog"
    assert classify(detect_mode(frame)) == "gated-static"


def test_classify_on_a_real_recorded_overworld_frame_is_free_control():
    frame = _fixture(_RED_FIXTURES, "frame_000049.png")
    assert detect_mode(frame) == "overworld"
    assert classify(detect_mode(frame)) == "free-control"


@pytest.mark.parametrize("name", ["frame_001_title.png", "frame_008_menu_with_targets.png"])
def test_kirby_static_screens_never_auto_advance(name):
    """S1 regression, pinned on REAL recorded Kirby NDS frames: an idle title/save-menu screen is
    frozen, so detect_modality labels it "static" — and "static" must classify as CHOICE (wake, never
    blind-press). This is the reviewer-reproduced erase-save scenario; if "static" ever returns to
    GATED_STATIC_CONTEXTS this test fails."""
    frame = _fixture(_KIRBY_FIXTURES, name)
    label, _ = detect_modality(frame, frame)   # idle screen: identical consecutive frames -> frozen
    assert label == "static"
    assert classify(label) == "choice"


# -- 2. learned-button mechanics ------------------------------------------------

def test_advance_learner_locks_only_after_two_confirmed_effects():
    """S3: one observed change can be an animation blink, not the button — a single success is a
    hypothesis (retried next), and only a REPEAT locks the button in."""
    learner = AdvanceLearner(candidates=("a", "start", "b"))
    assert learner.next_candidate("dialog") == "a"
    learner.record("dialog", "a", changed=True)         # 1st effect: pending, NOT locked
    assert learner.learned_for("dialog") is None
    assert learner.next_candidate("dialog") == "a"       # retried to confirm, not the ladder's 'start'
    learner.record("dialog", "a", changed=True)          # 2nd consecutive effect -> locked
    assert learner.learned_for("dialog") == "a"
    assert learner.next_candidate("dialog") == "a"


def test_advance_learner_pending_cleared_when_effect_does_not_repeat():
    """The animation mis-lock killer: 'a' appears to work once (a blinking cursor diffed), then does
    nothing on the retry — the hypothesis is dropped and the ladder resumes, never locking 'a'."""
    learner = AdvanceLearner(candidates=("a", "start", "b"))
    assert learner.next_candidate("dialog") == "a"
    learner.record("dialog", "a", changed=True)          # blink false-positive
    assert learner.next_candidate("dialog") == "a"       # retry the hypothesis
    learner.record("dialog", "a", changed=False)         # effect did not repeat -> drop it
    assert learner.learned_for("dialog") is None
    assert learner.next_candidate("dialog") == "start"   # ladder resumes past 'a'


def test_advance_learner_is_keyed_per_context():
    """Review finding: a global lock meant 'a' learned on dialog was reused forever on a later screen
    type needing 'start'. The lock is per context label — a fresh context starts its own ladder."""
    learner = AdvanceLearner(candidates=("a", "start", "b"))
    learner.record("dialog", "a", changed=True)
    learner.record("dialog", "a", changed=True)
    assert learner.learned_for("dialog") == "a"
    # A different context type is untouched by dialog's lock: its ladder starts fresh at 'a'.
    assert learner.learned_for("static") is None
    assert learner.next_candidate("static") == "a"
    learner.record("static", "a", changed=False)
    assert learner.next_candidate("static") == "start"   # adapts, instead of hammering dialog's 'a'


def test_advance_learner_unlocks_after_repeated_failures():
    """A locked button that stops working (the screen type changed under the same label) is unlocked
    after UNLOCK_FAILS consecutive failures, and the candidate ladder resumes."""
    learner = AdvanceLearner(candidates=("a", "start", "b"))
    learner.record("dialog", "a", changed=True)
    learner.record("dialog", "a", changed=True)
    assert learner.learned_for("dialog") == "a"
    for _ in range(3):                                    # UNLOCK_FAILS consecutive no-ops
        learner.record("dialog", "a", changed=False)
    assert learner.learned_for("dialog") is None          # unlocked
    assert learner.next_candidate("dialog") in ("a", "start", "b")   # ladder resumes


def test_advance_learner_emerald_naming_screen_a_loops_start_confirms():
    """The exact live-audit case: 'a' does NOT change the gated naming screen (it loops), so the
    learner must move to 'start', confirm it twice, and lock THAT in."""
    learner = AdvanceLearner(candidates=("a", "start", "b"))
    assert learner.next_candidate("static") == "a"
    learner.record("static", "a", changed=False)
    assert learner.next_candidate("static") == "start"
    learner.record("static", "start", changed=True)
    assert learner.next_candidate("static") == "start"    # retry the working hypothesis
    learner.record("static", "start", changed=True)
    assert learner.learned_for("static") == "start"


# -- 3. budget: per-episode, persistent across calls (S2) -----------------------

def _always_gated_press(button: str):
    return "dialog", True


def test_patience_budget_persists_across_advance_calls():
    """S2: the budget is an EPISODE counter — a stuck gated screen burns it once, and later advance()
    calls on the SAME episode press zero more times (not 40 more per observe, forever)."""
    p = Patience(budget=5)
    _, n1 = p.advance("dialog", _always_gated_press)
    assert n1 == 5
    _, n2 = p.advance("dialog", _always_gated_press)      # same stuck episode: budget stays spent
    assert n2 == 0
    assert p.total_advanced == 5


def test_patience_budget_rearms_when_state_leaves_gated_static():
    p = Patience(budget=5)
    p.advance("dialog", _always_gated_press)              # exhaust the episode
    p.note_state_class("free-control")                    # the world moved on -> episode over
    _, n = p.advance("dialog", _always_gated_press)       # a NEW gated episode gets a fresh budget
    assert n == 5


def test_patience_budget_rearms_only_on_a_different_brain_action():
    p = Patience(budget=5)
    p.note_brain_action("a")
    p.advance("dialog", _always_gated_press)              # exhaust
    p.note_brain_action("a")                              # same action repeated: stays exhausted
    _, n = p.advance("dialog", _always_gated_press)
    assert n == 0
    p.note_brain_action("start")                          # the brain tries something NEW -> re-arm
    _, n = p.advance("dialog", _always_gated_press)
    assert n == 5


def test_patience_advance_stops_the_instant_context_leaves_gated_static():
    p = Patience(budget=DEFAULT_BUDGET)
    calls = {"n": 0}

    def press(button: str):
        calls["n"] += 1
        ctx = "dialog" if calls["n"] < 3 else "overworld"
        return ctx, True

    final_context, n = p.advance("dialog", press)
    assert final_context == "overworld"
    assert n == 3
    assert p.total_advanced == 3


def test_patience_advance_never_touches_a_choice_context():
    p = Patience()
    press_called = {"n": 0}

    def press(button: str):
        press_called["n"] += 1
        return "menu", True

    final_context, n = p.advance("menu", press)  # already a choice -> classify() != gated-static
    assert n == 0 and press_called["n"] == 0
    assert final_context == "menu"


# -- 4. closed-loop FREE proof, via the real plugin (no ROM) -------------------

class _ScriptedDialogEmulator(FakeEmulator):
    """A FakeEmulator whose screen advances through a scripted (context) chain as `press()` is called —
    stands in for a real dialog-then-choice cutscene without a ROM. Only `_advance_button` moves the
    script; other buttons are true no-ops (identical pixels)."""

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
        # with no decoded text (an opted-in world's title/naming screen has no screen_text at all).
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
    assert plugin.patience.learner.learned_for("dialog") == "a"   # learned Red's real advance button: A

    # A second observe() (simulating the brain now waking and deciding) must NOT auto-advance further —
    # 'menu' is a choice context, so classify() keeps it there until the brain itself acts.
    obs2 = plugin.observe("agent")
    assert obs2.data["context"] == "menu"
    assert obs2.data["patience_advances"] == 0


def test_closed_loop_advanced_past_text_reaches_the_brain_and_the_oracle(tmp_path):
    """S4: the auto-advanced dialog content must not be silently discarded — the skipped lines are
    surfaced in the SAME observe's rendered text, and the per-press trail (button + context + text)
    lands on the observe's oracle.jsonl record."""
    script = ["dialog"] * 3 + ["menu"]
    emu = _ScriptedDialogEmulator(script)
    plugin = PokemonRedPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=_ScriptedPerceiver(emu))

    obs = plugin.observe("agent")

    # The render carries the skipped lines (the #41 "brain reads the dialog" intent, preserved).
    assert "auto-advanced past 3 frame(s)" in obs.text
    assert '"line 0"' in obs.text and '"line 2"' in obs.text
    # The oracle record carries the per-press audit trail (what was advanced, with which button).
    rec = json.loads((tmp_path / "oracle.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert rec["patience_advances"] == 3
    trail = rec["patience_trail"]
    assert [t["button"] for t in trail] == ["a", "a", "a"]
    assert [t["text"] for t in trail] == ["line 0", "line 1", "line 2"]
    assert all(t["context"] == "dialog" for t in trail)


def test_closed_loop_free_advance_learns_start_when_a_loops_via_opt_in(tmp_path):
    """The Emerald-naming-screen case reproduced through the real plugin, via the per-world OPT-IN
    (this world vouches for its "static" label): 'a' is tried first but never advances the gated
    screen; 'start' does, is confirmed twice, and is locked. No hardcoded button anywhere."""
    script = ["static"] * 3 + ["overworld"]
    emu = _ScriptedDialogEmulator(script)
    emu._advance_button = "start"   # only 'start' actually confirms this naming screen
    plugin = PokemonRedPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=_ScriptedPerceiver(emu),
                              patience=Patience(extra_gated_contexts=("static",)))

    obs = plugin.observe("agent")

    assert obs.data["context"] == "overworld"
    assert plugin.patience.learner.learned_for("static") == "start"
    # 'a' was tried once (wasted, correctly, on the first static frame), then 'start' worked, was
    # retried to confirm (twice-lock), and resolved the rest: a + start*3 = 4 free presses total.
    assert obs.data["patience_advances"] == 4


def test_closed_loop_static_is_inert_without_the_opt_in(tmp_path):
    """S1 pinned at the plugin level: the SAME static script with the DEFAULT Patience must not press
    anything — a generic world's "static" screen wakes the brain, it is never blind-advanced."""
    script = ["static"] * 3 + ["overworld"]
    emu = _ScriptedDialogEmulator(script)
    plugin = PokemonRedPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=_ScriptedPerceiver(emu))

    obs = plugin.observe("agent")

    assert obs.data["context"] == "static"          # untouched — surfaced to the brain as-is
    assert obs.data["patience_advances"] == 0
    assert emu._step == 0                            # not a single button was pressed


def test_closed_loop_never_auto_advances_a_choice_even_if_it_looks_static(tmp_path):
    """Fail-safe check: a script that starts life ALREADY at a choice must wake immediately (zero free
    advances), even though the plugin has never seen this world before and has no learned button yet."""
    script = ["menu"]
    emu = _ScriptedDialogEmulator(script)
    plugin = PokemonRedPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=_ScriptedPerceiver(emu))

    obs = plugin.observe("agent")

    assert obs.data["context"] == "menu"
    assert obs.data["patience_advances"] == 0
    assert plugin.patience.learner.learned_for("menu") is None   # never tried — nothing to learn


def test_closed_loop_budget_caps_a_never_advancing_screen_once_per_episode(tmp_path):
    """A pathological screen that never resolves stops at DEFAULT_BUDGET and surfaces to the brain —
    and (S2) STAYS quiet on subsequent observes of the same stuck episode instead of re-burning 40
    presses per turn forever. A NEW brain action re-arms one fresh episode."""
    script = ["dialog"] * (3 * DEFAULT_BUDGET)   # never reaches the end within any budget
    emu = _ScriptedDialogEmulator(script)
    emu._advance_button = "__never__"   # no candidate button will ever advance this screen
    plugin = PokemonRedPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=_ScriptedPerceiver(emu))

    obs = plugin.observe("agent")
    assert obs.data["context"] == "dialog"            # still gated-static: surfaced, brain wakes
    assert obs.data["patience_advances"] == DEFAULT_BUDGET

    obs2 = plugin.observe("agent")                    # the driver observes again next turn...
    assert obs2.data["patience_advances"] == 0        # ...but the episode budget is spent: no hammering

    # The brain tries a DIFFERENT action -> one fresh episode is granted.
    from core.contracts import ToolCall
    plugin.handle(ToolCall(call_id="c1", agent_id="agent", tool="press_button", args={"button": "b"}))
    obs3 = plugin.observe("agent")
    assert obs3.data["patience_advances"] == DEFAULT_BUDGET
    # ...and repeating the SAME action does not re-arm.
    plugin.handle(ToolCall(call_id="c2", agent_id="agent", tool="press_button", args={"button": "b"}))
    obs4 = plugin.observe("agent")
    assert obs4.data["patience_advances"] == 0


# -- 5. attribution (S5): patience presses are not brain moves ------------------

class _DialogThenSceneEmulator(FakeEmulator):
    """Shows a REAL recorded Red dialog frame; ANY press dismisses it into a textured overworld scene.
    Drives the REAL OverworldPerceiver (real detect_mode + pose machine) through the patience loop."""

    def __init__(self, dialog_frame: np.ndarray, scene_frame: np.ndarray) -> None:
        super().__init__()
        self._screen = dialog_frame
        self._scene = scene_frame

    def press(self, button, hold_frames=8, settle_frames=16):
        super().press(button, hold_frames=hold_frames, settle_frames=settle_frames)
        self._screen = self._scene


def test_patience_press_is_not_attributed_as_a_brain_move(tmp_path):
    """S5: the patience press that dismisses a dialog into the overworld must not corrupt the pose
    machine — the re-entry frame re-baselines (resync after non-overworld), the non-directional
    auto-press ('a') mints no phantom step, no wall, no pose delta. Uses the REAL OverworldPerceiver
    and a REAL recorded dialog fixture frame end-to-end through observe()."""
    dialog = _fixture(_RED_FIXTURES, "frame_000544.png")
    scene = np.random.RandomState(7).randint(0, 200, size=(144, 160), dtype=np.uint16).astype(np.uint8)
    scene = np.dstack([scene, scene, scene])   # textured, < 230: detect_mode reads it as overworld
    emu = _DialogThenSceneEmulator(dialog, scene)
    plugin = PokemonRedPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=OverworldPerceiver())

    obs = plugin.observe("agent")

    assert obs.data["context"] == "overworld"          # patience dismissed the dialog
    assert obs.data["patience_advances"] == 1
    # The pose machine did NOT treat the auto-press as a commanded move:
    assert obs.data["pose"]["value"] == [0, 0]                       # no phantom step
    assert obs.data["last_action"]["outcome"] != "moved"             # re-baseline, not a move
    assert obs.data["spatial_memory"].get("walls_here", []) == []    # no phantom wall minted
