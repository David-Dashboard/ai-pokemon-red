"""The runner — owns TIME and the ReAct loop (invariant 13).

One decision per invocation: the runner calls `brain.decide()` repeatedly,
each call producing at most one ToolCall, which it sends through the gateway.
It never hands the brain a fatter signature to do multi-step turns.

This runner serves both regimes:
  * Replayable sims  → it also calls step() each tick and stops at terminal().
  * Real-world worlds (Pokémon, desktop) → no step/terminal; it runs for a
    bounded number of decisions.
"""

from __future__ import annotations

from typing import Callable, Optional

from core.contracts import Brain, Event, GamePlugin, Observation, Replayable
from core.gateway import Gateway


def run_episode(
    gateway: Gateway,
    plugin: GamePlugin,
    brain: Brain,
    agent_id: str,
    max_steps: int = 200,
    context: Optional[dict] = None,
    on_step: Optional[Callable[[int, Observation, object, list[Event]], None]] = None,
) -> dict:
    context = context or {}
    replayable = isinstance(plugin, Replayable)

    total_reward = 0.0
    n_calls = 0
    event_counts: dict[str, int] = {}
    last_data: dict = {}

    for step in range(max_steps):
        if replayable and plugin.terminal():  # type: ignore[attr-defined]
            break

        obs = plugin.observe(agent_id)
        last_data = obs.data
        tools = plugin.tools(agent_id)
        call = brain.decide(obs, tools, context)
        if call is None:
            break

        result = gateway.execute(call)
        n_calls += 1

        if replayable:
            plugin.step()  # type: ignore[attr-defined]

        events = plugin.drain_events()
        for e in events:
            total_reward += e.reward
            event_counts[e.type] = event_counts.get(e.type, 0) + 1

        if on_step is not None:
            on_step(step, obs, result, events)

    return {
        "steps": n_calls,
        "total_reward": round(total_reward, 3),
        "event_counts": event_counts,
        "final_state": {k: last_data.get(k) for k in
                        ("badges", "party_level_sum", "maps_seen", "map_id", "money")},
    }
