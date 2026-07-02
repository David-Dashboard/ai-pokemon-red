"""Patience — a System-1 auto-advance reflex (world-side, free): don't wake the brain for a plain
no-choice dialog/cutscene frame it can't affect anyway.

Concept lifted from `core.brains.HybridBrain(advance_on_dialog=True)` (the pre-seam brain-side
auto-advance: mash the confirm button through 'dialog'/'battle_text', wake on 'menu'/'battle') and
`games/pokemon_red/perceiver.detect_mode` (the upper-right-selection-box heuristic that tells a plain
textbox apart from a YES/NO choice drawn over one) — but moved from the BRAIN to core/ and keyed on
STATE, not a hardcoded button, per the 2026-07-02 design (HANDOFF.md):

  * classify the current SymbolicState.context into {gated-static, choice, free-control}; only
    gated-static may be auto-advanced. Unsure -> choice (fail-safe default-to-wake).
  * the advance button is LEARNED by control-grounding: try candidates until one changes the gated
    screen TWICE, per context label; remember it for the rest of the run (blank every run — no
    cross-run persistence, the learning-boundary law). Emerald's naming screen needs 'start' where
    'a' loops — the exact case this exists for.
  * budget consecutive auto-advances PER GATED EPISODE (persists across observe() calls, so a stuck
    screen can't re-burn the budget every turn — see Patience below).

SAFETY (PR #49 adversarial review, S1): only DECODER-BACKED semantic labels may auto-advance by
default. The generic `core/modality.py` "static" label is a MOTION label ("nothing moved since last
frame"), NOT a semantics label — an idle save-select/naming/menu screen waiting for input is frozen
and reads "static" too, so blind-pressing it violates never-auto-commit (proven on real Kirby
save-screen frames). "static" therefore classifies as "choice" (wake) by default. A world that HAS a
trustworthy gated-static signal can opt in per world via `Patience(extra_gated_contexts=("static",))`
(the plugin's `patience=` kwarg is the config knob; default OFF everywhere).

Game-agnostic: reads only `SymbolicState.context`, which every perceiver already emits. No RAM, no
per-game imports.
"""
from __future__ import annotations

from typing import Callable, Optional

# Contexts positively known to be a plain, no-choice, advanceable screen (never a decision surface).
# DECODER-BACKED labels only: 'dialog'/'battle_text' come from games/pokemon_red/perceiver.py, whose
# detect_mode (choice-box heuristic) and _battle_context/battle_subscreen (positive-ID-for-advance)
# genuinely keep a real choice OUT of these labels. The generic "static" label is deliberately NOT
# here — see the SAFETY note in the module docstring (opt-in per world only).
GATED_STATIC_CONTEXTS = frozenset({"dialog", "battle_text"})

# Contexts that ARE a decision surface — NEVER auto-advance these, no matter how long they persist.
# 'menu'/'battle' come from Pokemon Red (a real menu / the battle action-move menu); a generic world's
# 'menu' (core/grid_perceiver.py -> core/modality.py) is also covered deliberately: that classifier
# cannot distinguish a plain textbox from a YES/NO choice, so its 'menu' must be treated as "might be
# a choice" -> wake. (Everything unrecognized ALSO falls through to "choice" — this set is
# documentation of the known decision labels, not an exhaustive gate.)
CHOICE_CONTEXTS = frozenset({"menu", "battle"})

# Contexts that mean the agent is in free control (mirrors PerceptionPlugin._FREE_MOVEMENT_CONTEXTS).
FREE_CONTROL_CONTEXTS = frozenset({"overworld", "gameplay"})

# Default candidate advance buttons to try, in order, when the world's advance input hasn't been
# learned yet this run. 'a' is the overwhelmingly common confirm button (Gen-1 dialog, most menus);
# 'start' covers Emerald's naming-screen confirm (the live-audit case where 'a' loops); 'b' is a cheap
# third try (some titles use B to skip). Kept short and CHEAP — this is a fallback ladder, not a survey.
DEFAULT_ADVANCE_CANDIDATES = ("a", "start", "b")

# Cap free auto-advances PER GATED EPISODE before waking the brain (a stuck/never-advanceable screen,
# or a mis-classified choice, must not run forever for free). Generous vs. a real dialog chain (Red's
# Oak cutscene is dozens of lines) but still bounded. The counter persists across observe() calls and
# resets only when the state leaves gated-static or the brain issues a DIFFERENT action (PR #49 S2:
# a per-call budget re-armed 40 presses every turn on a stuck screen, forever).
DEFAULT_BUDGET = 40

# Control-grounding thresholds: a candidate button must show an observed effect TWICE IN A ROW before
# it is locked in (PR #49 S3: a single pixel-diff can be a blinking cursor/animation, not the button's
# effect — one success is a hypothesis, a repeat is a confirmation), and a LOCKED button that fails
# this many times in a row is unlocked (the screen type changed / the lock was wrong), resuming the
# candidate ladder.
UNLOCK_FAILS = 3


def classify(context: str, gated: frozenset = GATED_STATIC_CONTEXTS) -> str:
    """SymbolicState.context -> one of {"gated-static", "choice", "free-control"}.

    Fail-safe: any context not positively known to be gated-static or free-control is treated as
    "choice" (never auto-advanced) — the erase-save guard. This covers 'unknown', 'static' (a motion
    label, not a no-choice guarantee — S1), and any per-game context this module hasn't seen.
    `gated` lets a world OPT IN extra contexts it can vouch for (via Patience.extra_gated_contexts).
    """
    if context in gated:
        return "gated-static"
    if context in FREE_CONTROL_CONTEXTS:
        return "free-control"
    return "choice"


class AdvanceLearner:
    """Per-run memory of the world's learned advance button (control-grounding, blank every run).

    Keyed PER CONTEXT LABEL (PR #49 review: one global slot meant a run that locked 'a' on Red's
    'dialog' could never adapt to a later screen type needing 'start' — it burned the whole budget on
    the stale button every encounter). Locking requires the button's effect observed TWICE in a row
    (a single frame diff can be an animation blink, not the button); a locked button that fails
    UNLOCK_FAILS times in a row is unlocked and the candidate ladder resumes."""

    def __init__(self, candidates=DEFAULT_ADVANCE_CANDIDATES) -> None:
        self._candidates = tuple(candidates)
        self._learned: dict[str, str] = {}       # context label -> locked-in advance button
        self._pending: dict[str, str] = {}       # context -> button seen working ONCE (needs a repeat)
        self._tried_idx: dict[str, int] = {}     # context -> candidate-ladder position
        self._locked_fails: dict[str, int] = {}  # context -> consecutive failures of the LOCKED button

    def learned_for(self, context: str) -> Optional[str]:
        return self._learned.get(context)

    def next_candidate(self, context: str) -> str:
        """The button to press next for this context: the locked one if confirmed; else the pending
        one (a button that just worked once — retry it to confirm, don't wander the ladder); else the
        next ladder candidate (wrapping — a persistent screen keeps cycling rather than getting stuck)."""
        b = self._learned.get(context) or self._pending.get(context)
        if b is not None:
            return b
        i = self._tried_idx.get(context, 0)
        self._tried_idx[context] = i + 1
        return self._candidates[i % len(self._candidates)]

    def record(self, context: str, button: str, changed: bool) -> None:
        """Feed back one press's observed outcome (control-grounding)."""
        locked = self._learned.get(context)
        if locked == button:
            if changed:
                self._locked_fails[context] = 0
            else:
                fails = self._locked_fails.get(context, 0) + 1
                self._locked_fails[context] = fails
                if fails >= UNLOCK_FAILS:      # the lock stopped being true — unlearn, resume the ladder
                    del self._learned[context]
                    self._locked_fails[context] = 0
            return
        if changed:
            if self._pending.get(context) == button:   # 2nd consecutive observed effect -> lock it in
                del self._pending[context]
                self._learned[context] = button
                self._locked_fails[context] = 0
            else:
                self._pending[context] = button        # 1st observed effect: a hypothesis, retry next
        elif self._pending.get(context) == button:
            del self._pending[context]   # the effect didn't repeat (an animation blink, not the button)


class Patience:
    """Drives the auto-advance loop for a PerceptionPlugin-family world.

    Injected with a press callback so it stays engine-agnostic; this module is pure decision logic +
    the per-run learned-button memory + the per-episode budget.

    Budget semantics (S2): `_spent` counts presses in the CURRENT gated episode and persists across
    `advance()` calls. It resets only when the observed state leaves gated-static
    (`note_state_class`) or the brain issues a DIFFERENT action than its previous one
    (`note_brain_action`) — so a stuck gated screen costs at most `budget` free presses total, not
    `budget` per observe() forever.
    """

    def __init__(self, budget: int = DEFAULT_BUDGET,
                 candidates=DEFAULT_ADVANCE_CANDIDATES,
                 extra_gated_contexts=()) -> None:
        self.learner = AdvanceLearner(candidates)
        self.budget = budget
        # Opt-in per world (S1): extra contexts this world vouches for as truly gated-static (e.g. a
        # world whose "static" label is decoder/heuristic-backed). Default: decoder-backed labels only.
        self.gated_contexts = GATED_STATIC_CONTEXTS | frozenset(extra_gated_contexts)
        self.total_advanced = 0   # lifetime count across the run, for oracle/traceability
        self._spent = 0           # presses in the current gated EPISODE (persists across observes)
        self._last_brain_action: Optional[str] = None

    def classify(self, context: str) -> str:
        return classify(context, self.gated_contexts)

    def note_state_class(self, state_class: str) -> None:
        """Call once per observe() with the entry frame's class: leaving gated-static ends the episode."""
        if state_class != "gated-static":
            self._spent = 0

    def note_brain_action(self, action: Optional[str]) -> None:
        """Call on every brain-commanded action: a DIFFERENT action than last time re-arms the budget
        (the brain is trying something new — give patience a fresh episode); repeating the same action
        on the same stuck screen does not."""
        if action != self._last_brain_action:
            self._spent = 0
        self._last_brain_action = action

    def advance(self, context: str,
                press: Callable[[str], tuple[str, bool]]) -> tuple[str, int]:
        """`press(button)` must return `(new_context, changed)`: `changed` is True iff the button
        visibly altered the gated screen (a NEW dialog line, a screen that left gated-static, etc — the
        caller's call, since only it can compare e.g. screen_text; the bare context LABEL is too coarse
        — consecutive dialog lines are both just "dialog"). `changed` is what control-grounding needs to
        tell "this button works" apart from "this button is a no-op the game silently absorbed".

        Returns (final_context, presses_this_call). Stops the moment the context leaves gated-static
        OR the episode budget is exhausted — either way the brain's next observe lands on free-control,
        a real choice, or (budget case) the still-gated screen it must now decide about itself."""
        n = 0
        while self.classify(context) == "gated-static" and self._spent < self.budget:
            gated_context = context               # the screen being advanced (the learner's key)
            button = self.learner.next_candidate(gated_context)
            new_context, changed = press(button)
            n += 1
            self._spent += 1
            self.learner.record(gated_context, button, changed)
            context = new_context
        self.total_advanced += n
        return context, n
