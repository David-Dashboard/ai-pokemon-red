"""Cost guardrails — world-agnostic halt predicates for paid LLM runs (S1 cost-breaker).

These are PURE functions over the brain's spend meters (`total_cost_usd`, `last_prompt_tokens`, set by
`LLMButtonBrain` from each call's `usage` block) plus, for the wake watchdog, two integers the DRIVER
supplies. Both `play_pokemon.py` and `play_loop.py` call them, so the halt logic lives in ONE tested
place instead of being duplicated inline in two driver closures.

No-leak posture: these read only token/cost/wake counters — never RAM. The wake watchdog's
oracle-progress baseline is computed in the driver (from the RAM oracle) and passed in as a plain int,
so the guardrails themselves stay world-agnostic and the oracle never reaches the agent.

Each function returns a short human-readable HALT REASON string when a ceiling is breached, or None to
continue — so a driver can do `if (r := spend_halt_reason(...)): halt(r)`. A threshold of 0 disables
its check.
"""

from __future__ import annotations

from typing import Optional


def spend_halt_reason(brain, *, max_cost_usd: float, max_prompt_tokens: int) -> Optional[str]:
    """Halt reason if a SPEND ceiling is breached, else None. Two independent checks:

      * estimated-spend circuit breaker — the running cost ESTIMATE (`brain.total_cost_usd`, accrued
        from real usage x model pricing) has reached `max_cost_usd`. The true cost ceiling that a
        wake-COUNT cap only approximates (a bloated wake costs many times a lean one).
      * per-wake prompt-token cap — the most recent wake's prompt (`brain.last_prompt_tokens`) exceeded
        `max_prompt_tokens`. A runaway-bloat tripwire (e.g. a transcript/lesson buffer blowing up).

    Read defensively via getattr so a brain without meters (ScriptedBrain, a bare autopilot) never
    trips these (it just reads 0)."""
    cost = getattr(brain, "total_cost_usd", 0.0)
    if max_cost_usd > 0 and cost >= max_cost_usd:
        return f"estimated spend ~${cost:.2f} reached the ${max_cost_usd:.2f} cost cap (cost breaker)"
    pt = getattr(brain, "last_prompt_tokens", 0)
    if max_prompt_tokens > 0 and pt > max_prompt_tokens:
        return f"a wake's prompt was {pt} tokens > the {max_prompt_tokens} per-wake cap (prompt-bloat tripwire)"
    return None


def wake_stall_halt_reason(woke: int, woke_at_progress: int, stuck_wakes: int) -> Optional[str]:
    """Halt reason if the agent has been WOKEN `stuck_wakes` times with no real progress since the last
    checkpoint, else None. The wake-denominated complement to a step watchdog: once free auto-advance
    inflates the step count between wakes, "no progress for N steps" is fooled by aimless-but-real
    wandering (run #15), but "no progress across N paid wakes" bills the agent for *flailing that costs
    money*, not for moving. `woke_at_progress` is the driver's wake count at the last oracle-progress
    checkpoint (RAM-derived, driver-side). `stuck_wakes <= 0` disables it."""
    if stuck_wakes <= 0:
        return None
    stalled = woke - woke_at_progress
    if stalled >= stuck_wakes:
        return f"no progress across {stalled} LLM wakes (wake watchdog)"
    return None
