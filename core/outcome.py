"""Outcome memory (feature #1 — the learning spine, agent-agnostic).

The simplest seed of "learn from mistakes / don't repeat / retry": record, per
(situation, action), whether the action produced an OBSERVABLE EFFECT. Actions that
repeatedly do nothing in a situation are "dead" and surfaced so the planner stops
repeating them — generalizing the occupancy map's wall-memory (a blocked *move*) to ANY
action (e.g. pressing A at nothing, choosing a menu option that doesn't apply).

It's deliberately tiny and world-agnostic: it holds no game knowledge, just
(signature, action) → effectiveness tallies. The "signature" + "effective?" judgement are
supplied by the caller from whatever observation it has (here: the SymbolicState).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional

Signature = tuple


def state_signature(data: dict) -> Signature:
    """A coarse 'where/what am I' key from a SymbolicState dict — context (mode) + area + pose.
    Same signature ⇒ 'the same situation' for the purpose of remembering what worked here."""
    pose = (data.get("pose") or {}).get("value")
    area = (data.get("pose") or {}).get("area")
    return (data.get("context", "overworld"), area, tuple(pose) if pose else None)


def action_key(call: Any) -> Optional[str]:
    """A stable string for an action (ToolCall), so repeats of 'the same action' collapse."""
    if call is None:
        return None
    args = getattr(call, "args", {}) or {}
    if "buttons" in args:
        return "+".join(str(b) for b in args["buttons"])
    if "button" in args:
        return str(args["button"])
    return getattr(call, "tool", None)


class OutcomeMemory:
    """(signature, action) → [tries, no_effect]. `dead_after` consecutive-or-total no-effects marks
    an action 'dead' in that situation."""

    def __init__(self, dead_after: int = 2) -> None:
        self.dead_after = dead_after
        self._tally: dict = defaultdict(lambda: [0, 0])

    def record(self, sig: Signature, action: Optional[str], effective: bool) -> None:
        if action is None:
            return
        t = self._tally[(sig, action)]
        t[0] += 1
        t[1] = 0 if effective else t[1] + 1  # consecutive no-effects (resets on any effect)

    def is_dead(self, sig: Signature, action: Optional[str]) -> bool:
        return action is not None and self._tally[(sig, action)][1] >= self.dead_after

    def dead_actions(self, sig: Signature) -> list:
        """Actions that have had no effect `dead_after`+ times in a row in this situation."""
        return sorted({a for (s, a), t in self._tally.items()
                       if s == sig and t[1] >= self.dead_after})
