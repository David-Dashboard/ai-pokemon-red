"""Novelty memory — the seen-states signal (agent-agnostic, System-1, harness-owned).

*Progress = reaching NOVEL states; stuck = REVISITING states already seen (a cycle).* This is the
unifying principle behind three signals the harness already builds piecemeal — the occupancy map
("seen this *pose*?"), `OutcomeMemory` ("did this *(situation, action)* do nothing?"), and the
disconfirm detector ("how long since anything *new*?"). All three track revisiting, but none sees
the SCREEN/dialog state (`state_signature` in `outcome.py` deliberately excludes `screen_text`).
`NoveltyMemory` closes that gap: it counts VISITS to whatever state-key the caller supplies (here:
`state_signature` + `screen_text`), so the cheap loop can tell "advancing through new states" from
"cycling back to states it has already seen" — e.g. Oak's "which POKéMON?" prompt, a textbox the
confirm button cannot dismiss, which the harness would otherwise auto-mash forever.

VISITS, not raw occurrences: a state held across consecutive observations (a settled textbox that
hasn't advanced yet) is ONE visit. Only a key that DIFFERS from the immediately-preceding one — a
rising edge — counts as a new visit. So a normal dialog held for a few frames is never mistaken for
a loop; a cycle is the same state RETURNED TO after leaving it.

The caller builds the key, so the key-derivation is the single seam a future semantic version would
swap (the exact tuple → a locality hash / embedding bucket, for novelty that tolerates perception
noise) without touching this class.
"""
from __future__ import annotations

from collections import Counter
from typing import Hashable, Optional


class NoveltyMemory:
    """Counts VISITS to caller-supplied state keys (rising-edge), fresh per run."""

    def __init__(self) -> None:
        self._counts: Counter = Counter()
        self._last: Optional[Hashable] = None

    def observe(self, key: Optional[Hashable]) -> int:
        """Register the current state; return how many VISITS it has had (including this one).

        Call once per decision. `key` is whatever hashable identifies "the same state", or None for
        a transition/empty frame that carries no state. A None key still BREAKS a held run (so a
        state seen, then left, then seen again counts as two visits). A held frame (key == the
        previous key) does NOT add a visit. Returns 0 for a None key.
        """
        if key is None:
            self._last = None
            return 0
        if key != self._last:          # rising edge = a new visit (held frames don't recount)
            self._counts[key] += 1
        self._last = key
        return self._counts[key]

    def visits(self, key: Optional[Hashable]) -> int:
        """How many visits `key` has had so far (0 if never / None), WITHOUT registering one."""
        return self._counts[key] if key is not None else 0
