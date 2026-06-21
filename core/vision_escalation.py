"""Perception escalation — a strong vision model grounds a confusing screen at STUCK moments.

System-1 perception is cheap by default (template decode, pixels-only). When the cheap loop reports the
agent is STUCK (the cycle gate / stuck-breaker), the fixed-schema perceiver has clearly failed to surface
what matters — so we ESCALATE: call a strong VLM to DESCRIBE the screen (what it is, its elements, the
plausible ways to finish/exit it) and hand that grounding to the cheap agent, which still DECIDES and acts.

This is the dual-process escalation TIER applied to perception (ADR-001's "perception is the watched
bottleneck"): cheap perception by default, a general VLM escape hatch only when the cheap signal says
"stuck". Pixels only — never RAM, still "plan from the screen". World-agnostic: the model call is an
injected `describe_fn` and the prompt asks for a DESCRIPTION, not a decision (that stays with the agent).

Cost is bounded two ways so a healthy run (never stuck) makes ZERO calls: the description is CACHED per
state (one call per stuck screen, not per wake — a 44-frame held keyboard costs ONE call), and total
calls are capped per run.
"""
from __future__ import annotations

from typing import Callable, Hashable, Optional

# Asks for GROUNDING (what is this / how is it operated), NOT a single committed action — the cheap agent
# owns the decision. Deliberately world-agnostic (no game names): it must read any screen, any world.
_DEFAULT_QUESTION = (
    "You are looking at a single video-game screen. In 2-4 sentences, ground it for another agent: "
    "(1) what this screen IS, (2) its interactive elements and the current selection/cursor, and "
    "(3) the plausible button(s) to FINISH or EXIT it (A / B / START / SELECT / a d-pad direction). "
    "Be concrete; if you are unsure of the exact button, list the options to try."
)


class VisionEscalator:
    """Grounds a stuck screen via a strong VLM — ONLY when the cheap loop is stuck, at most `max_calls`
    times per run, and at most ONCE per distinct state (cached)."""

    def __init__(self, describe_fn: Callable[[str, Optional[str]], object],
                 question: str = _DEFAULT_QUESTION, max_calls: int = 8) -> None:
        self.describe_fn = describe_fn   # (prompt, image_path) -> text  OR  (text, usage); both tolerated
        self.question = question
        self.max_calls = max_calls
        self.calls = 0
        self._cache: dict = {}           # state_key -> description (or None); ONE attempt per state

    def ground(self, image_path: Optional[str], state_key: Hashable) -> Optional[str]:
        """Return a grounding description for the current (stuck) screen, or None.

        None when: there is no image, the per-run cap is hit, or the VLM call failed. Cached by
        `state_key` (so the same stuck screen costs exactly one call, success or failure)."""
        if not image_path:
            return None
        if state_key in self._cache:          # already grounded this state -> reuse, no new call
            return self._cache[state_key]
        if self.calls >= self.max_calls:      # per-run budget spent -> degrade gracefully
            return None
        self.calls += 1
        try:
            out = self.describe_fn(self.question, image_path)
            text = out[0] if isinstance(out, tuple) else out
            text = (text or "").strip() or None
        except Exception:                     # a failed VLM call must NEVER break the run
            text = None
        self._cache[state_key] = text         # cache even None: one attempt per distinct state
        return text
