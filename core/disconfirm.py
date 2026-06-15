"""Disconfirm / surprise detector (the 'act -> observe outcome -> learn' spine, agent-agnostic).

Unifies the within-run prediction-error signals into ONE nudge for the planner:
  * stuck / no-progress — the agent keeps acting but the observed situation does not change, and
  * a blocked move — the perceiver reports the last move hit a wall (`SymbolicState.last_action`).
When a disconfirmation PERSISTS (no observable change for `after` consecutive decisions) it emits a
one-line `SURPRISE: ...` note that tells the planner to try something different and record a one-line
`LESSON:`. That lesson lands in the harness-owned per-run LESSON buffer (`LLMButtonBrain`), closing the
loop. World-agnostic: the only expectation encoded is the universal one — a chosen action should change
the observable situation; no change disconfirms it.

This subsumes the earlier ad-hoc loop-breaker (which fired only when the free autopilot ran out of
frontier); the no-progress signal also catches the case the loop-breaker MISSED — flailing inside a
forced dialog/menu (consecutive wakes that change nothing), the live run #2 failure.

Harness-owned, fresh per run, injected at each wake, discarded at run end (the learning boundary): it
holds NO game knowledge and never persists across runs.
"""
from __future__ import annotations

from typing import Optional


class DisconfirmDetector:
    """Counts consecutive decisions with no observable progress; fires a surprise note at `after`."""

    def __init__(self, after: int = 5) -> None:
        if after < 1:
            raise ValueError(f"after must be >= 1 (decisions of no-progress before firing), got {after}")
        self.after = after
        self._streak = 0          # consecutive decisions with NO observable change
        self._last_action = ""    # the action string the perceiver last reported on
        self._last_outcome = ""   # its outcome: 'moved' | 'blocked' | 'unknown' | 'n/a'

    def record(self, progressed: bool, last_action: Optional[dict] = None) -> None:
        """Call once per decision. `progressed` = did the observed situation change since last time;
        `last_action` = the SymbolicState's `last_action` role ({'action','outcome'}), if any."""
        self._streak = 0 if progressed else self._streak + 1
        la = last_action or {}
        self._last_action = str(la.get("action") or "")
        self._last_outcome = str(la.get("outcome") or "")

    @property
    def fired(self) -> bool:
        return self._streak >= self.after

    def note(self) -> Optional[str]:
        """The surprise note to inject at THIS wake, or None. Consuming it resets the streak, so the
        planner is nudged about once per `after` no-progress decisions — not on every single step."""
        if self._streak < self.after:
            return None
        n = self._streak
        if self._last_outcome == "blocked":
            detail = f" Your last move ({self._last_action}) was blocked by a wall."
        elif self._last_action:
            detail = f" Your last action ({self._last_action}) changed nothing."
        else:
            detail = ""
        msg = (f"SURPRISE: {n} decisions in a row with no observable progress.{detail} Something you "
               f"expect to work isn't — do NOT repeat recent actions, try a clearly different "
               f"approach, and record a one-line LESSON: about what is blocking you.")
        self._streak = 0   # consume: reset so we nudge once per `after`, not on every later step
        return msg
