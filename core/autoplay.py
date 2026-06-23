"""World-agnostic mode-aware AUTO-PLAY policy for unattended data collection (System-1; no game facts).

Pairs with `core/modality.py` to drive a recorder from a cold boot, through titles/menus, into gameplay
WITHOUT a human nudging it:
  - active GAMEPLAY (the screen is responding to movement) -> the injected random-breadth policy (the
    movement coverage we actually want to record);
  - static / menu / unknown screens -> an ESCAPE ladder (a, start, directions) that advances a title or
    dialog and steps through a simple menu.

KEY DESIGN CHOICE (grounded in the Pokemon anchor + the project's cross-domain-mislabel lesson): menu
HANDLING is BEHAVIORAL, not appearance-based. The modality detector reliably separates static vs active
gameplay, but does NOT reliably classify menus/dialogs by appearance across games (on the anchor they
read as low-confidence 'gameplay'). So we never depend on a 'menu' LABEL to escape a menu — we depend on
PROGRESS (did the screen actually change?). While an escape move keeps changing the screen we REPEAT it
(advancing a multi-box dialog / a title); when it stops changing anything we ROTATE to the next move
(stepping a menu). That escapes UI regardless of how the screen was labeled — and it cannot be fooled
into a confident wrong label the way an appearance classifier can.

(Note: `detect_modality` only returns "gameplay" when the frame actually changed, so a frozen game
screen reads as "static" and is handled by the escape ladder too — pressing a direction resumes motion.)

v1 is deliberately simple (an escape rotation). The world-agnostic OutcomeMemory (dead-action) /
NoveltyMemory (cycle) smarts in core/ are the v2 upgrade IF measurement (corpus_activity) shows the
simple version gets stuck on a specific game.
"""
from __future__ import annotations

import random
from typing import Callable, List, Optional, Sequence, Tuple

from core.modality import STATIC_EPS, detect_modality, modality_signals

# Escape ladder: biased to ADVANCE (a / start dominate — titles, dialogs, confirms) with directions
# interleaved to step a menu cursor. 'b' is included sparingly so we can back out of a dead end without
# routinely undoing progress.
_ESCAPE: Tuple[Tuple[str, ...], ...] = (
    ("a",), ("start",), ("a",), ("down",), ("a",), ("right",), ("up",), ("left",), ("start",), ("b",),
)


class ModalAutoPolicy:
    """Picks one step's buttons from the (prev, curr) frame pair + the buttons that produced curr.

    `gameplay_action(rng) -> list[str]` is INJECTED (the recorder owns its random-breadth policy; this
    module stays decoupled from the recorder and from any one world)."""

    def __init__(self, rng: random.Random, gameplay_action: Callable[[random.Random], List[str]],
                 escape: Sequence[Sequence[str]] = _ESCAPE) -> None:
        self.rng = rng
        self.gameplay_action = gameplay_action
        self._escape = [tuple(e) for e in escape]
        self._esc = 0                # index into the escape ladder (advances while stuck)
        self.stalls = 0              # telemetry: total non-gameplay steps this run

    def decide(self, prev_frame, curr_frame,
               last_buttons: Optional[Sequence[str]] = None) -> Tuple[str, List[str]]:
        """Return (detected_mode, buttons_to_press) for the screen we are currently looking at."""
        mode, _conf = detect_modality(prev_frame, curr_frame, last_buttons)

        # Active gameplay (implies the screen changed): record movement breadth, reset the ladder.
        if mode == "gameplay":
            self._esc = 0
            return mode, list(self.gameplay_action(self.rng))

        # static / menu / unknown -> escape ladder. Repeat a move that is still changing the screen
        # (advancing a dialog/title); rotate to the next move when nothing changed (step a menu).
        self.stalls += 1
        sig = modality_signals(prev_frame, curr_frame)
        # `progressed` reuses the static cutoff (STATIC_EPS) as the "did the last move change the screen?"
        # test; a sub-threshold blink reads as no-progress and so rotates to the next move (intended).
        progressed = sig is not None and sig["frame_diff"] >= STATIC_EPS
        if not progressed:        # last move stopped changing the screen -> rotate to the next move
            self._esc += 1
        # on progress, KEEP self._esc: _escape[_esc] is the last-emitted move, so we repeat exactly the
        # move that is still advancing the screen (the repeat-while-changing design described above).
        return mode, list(self._escape[self._esc % len(self._escape)])
