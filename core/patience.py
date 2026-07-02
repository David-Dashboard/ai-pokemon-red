"""Patience — a System-1 auto-advance reflex (world-side, free): don't wake the brain for a plain
no-choice dialog/cutscene frame it can't affect anyway.

Concept lifted from `core.brains.HybridBrain(advance_on_dialog=True)` (the pre-seam brain-side
auto-advance: mash the confirm button through 'dialog'/'battle_text', wake on 'menu'/'battle') and
`games/pokemon_red/perceiver.detect_mode` (the upper-right-selection-box heuristic that tells a plain
textbox apart from a YES/NO choice drawn over one) — but moved from the BRAIN to core/ and keyed on
STATE, not a hardcoded button, per the 2026-07-02 design (HANDOFF.md):

  * classify the current SymbolicState.context into {gated-static, choice, free-control}; only
    gated-static may be auto-advanced. Unsure -> choice (fail-safe default-to-wake).
  * the advance button is LEARNED by control-grounding: try candidates in order until one changes the
    gated screen; remember it for the rest of the run (blank every run — no cross-run persistence,
    the learning-boundary law). Emerald's naming screen needs 'start' where 'a' loops — the exact case
    this exists for.
  * cap consecutive auto-advances (a runaway/never-advanceable screen must still surface to the brain).

Game-agnostic: reads only `SymbolicState.context` (+ optionally `screen_text` for logging), which every
perceiver already emits (`core/grid_perceiver.py`'s generic static/menu/gameplay, or a richer per-game
split like Pokemon Red's dialog/menu/battle/battle_text). No RAM, no per-game imports.
"""
from __future__ import annotations

from typing import Callable, Optional

# Contexts positively known to be a plain, no-choice, advanceable screen (never a decision surface).
# 'dialog'/'battle_text' come from games/pokemon_red/perceiver.py (its detect_mode already keeps a real
# YES/NO choice OUT of these labels — see the module docstring above). 'static' comes from the generic
# core/grid_perceiver.py modality classifier (a frozen title/splash/"press any button" screen).
GATED_STATIC_CONTEXTS = frozenset({"dialog", "battle_text", "static"})

# Contexts that ARE a decision surface — NEVER auto-advance these, no matter how long they persist.
# 'menu'/'battle' come from Pokemon Red (a real menu / the battle action-move menu); a generic world's
# 'menu' from core/grid_perceiver.py is also included here deliberately: that classifier does not (and,
# being game-agnostic, cannot) distinguish a plain textbox from a YES/NO choice the way Red's
# upper-right-box heuristic does, so its 'menu' must be treated as "might be a choice" -> wake.
CHOICE_CONTEXTS = frozenset({"menu", "battle"})

# Default candidate advance buttons to try, in order, when the world's advance input hasn't been
# learned yet this run. 'a' is the overwhelmingly common confirm button (Gen-1 dialog, most menus);
# 'start' covers Emerald's naming-screen confirm (the live-audit case where 'a' loops); 'b' is a cheap
# third try (some titles use B to skip). Kept short and CHEAP — this is a fallback ladder, not a survey.
DEFAULT_ADVANCE_CANDIDATES = ("a", "start", "b")

# Cap consecutive free auto-advances before waking the brain anyway (a stuck/never-advanceable screen,
# or a mis-classified choice, must not run forever for free). Generous vs. a real dialog chain (Red's
# Oak cutscene is dozens of lines) but still bounded.
DEFAULT_BUDGET = 40


def classify(context: str) -> str:
    """SymbolicState.context -> one of {"gated-static", "choice", "free-control"}.

    Fail-safe: any context not positively known to be gated-static or free-control is treated as
    "choice" (never auto-advanced) — the erase-save guard. This also covers 'unknown' (grid_perceiver's
    first-frame label) and any per-game context this module hasn't been told about yet.
    """
    if context in GATED_STATIC_CONTEXTS:
        return "gated-static"
    if context in CHOICE_CONTEXTS:
        return "choice"
    if context in ("overworld", "gameplay"):
        return "free-control"
    return "choice"


class AdvanceLearner:
    """Per-run memory of the world's learned advance button (control-grounding, blank every run).

    Usage: while a gated-static screen persists, call `next_candidate()` for the next button to try
    (cycles the candidate ladder until `confirm(button)` locks one in); once confirmed, `button()`
    always returns the learned button without re-trying others."""

    def __init__(self, candidates=DEFAULT_ADVANCE_CANDIDATES) -> None:
        self._candidates = tuple(candidates)
        self._learned: Optional[str] = None
        self._tried_idx = 0

    @property
    def learned(self) -> Optional[str]:
        return self._learned

    def next_candidate(self) -> str:
        """The button to press next: the learned one if already confirmed, else the next untried
        candidate (wrapping — a persistent screen keeps cycling the ladder rather than getting stuck)."""
        if self._learned is not None:
            return self._learned
        b = self._candidates[self._tried_idx % len(self._candidates)]
        self._tried_idx += 1
        return b

    def confirm(self, button: str) -> None:
        """Lock in `button` as the world's advance input for the rest of this run."""
        self._learned = button


class Patience:
    """Drives the auto-advance loop for a PerceptionPlugin-family world.

    Injected with two callbacks so it stays engine-agnostic:
      * `press(button) -> context_after`: press `button`, settle, and return the NEW SymbolicState
        context (the caller's own settle-to-stable + perceive, reused rather than duplicated).
      * nothing else touches the emulator directly here — this module is pure decision logic + the
        per-run learned-button memory.

    `advance(context) -> (final_context, frames_advanced_count)`: while `classify(context)` is
    "gated-static" and the budget isn't spent, press a candidate/learned button and re-check. Stops
    (returns to the caller, which then perceives normally) the moment the context leaves gated-static
    OR the budget is exhausted — either way the brain's NEXT observe lands on free-control or a real
    choice, never on a stale gated-static frame.
    """

    def __init__(self, budget: int = DEFAULT_BUDGET,
                 candidates=DEFAULT_ADVANCE_CANDIDATES) -> None:
        self.learner = AdvanceLearner(candidates)
        self.budget = budget
        self.total_advanced = 0   # lifetime count across the run, for oracle/traceability

    def advance(self, context: str, press: Callable[[str], tuple[str, bool]]) -> tuple[str, int]:
        """`press(button)` must return `(new_context, changed)`: `changed` is True iff the button
        visibly altered the gated screen (a NEW dialog line, a screen that left gated-static, etc — the
        caller's call, since only it can compare e.g. screen_text; the bare context LABEL is too coarse
        — consecutive dialog lines are both just "dialog"). `changed` is what control-grounding needs to
        tell "this button works" apart from "this button is a no-op the game silently absorbed"."""
        n = 0
        while classify(context) == "gated-static" and n < self.budget:
            button = self.learner.next_candidate()
            new_context, changed = press(button)
            n += 1
            if changed and self.learner.learned is None:
                # This button visibly changed the gated screen -> it's the world's advance input. Lock
                # it in (control-grounding: the button that reliably changes the screen IS the input).
                self.learner.confirm(button)
            context = new_context
        self.total_advanced += n
        return context, n
