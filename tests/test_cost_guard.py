"""Cost-breaker tests (S1) — the shared halt predicates + an end-to-end run_episode halt.

Two layers:
  * unit — the pure halt-reason helpers both drivers call (core.cost_guard).
  * integration — drive the REAL run_episode loop with a real HybridBrain whose LLM meters escalating
    cost, and a should_continue built from spend_halt_reason; assert the run halts at the right wake.
This validates the cost-breaker WITHOUT any API/ROM (free), which is the whole point — a paid run can't
be the only way to know the breaker works.
"""

import types

import pytest

from core.cost_guard import spend_halt_reason, wake_stall_halt_reason


def _brain(cost=0.0, last_prompt=0):
    return types.SimpleNamespace(total_cost_usd=cost, last_prompt_tokens=last_prompt)


# -- spend_halt_reason ---------------------------------------------------------

def test_spend_no_halt_under_thresholds():
    assert spend_halt_reason(_brain(0.4, 1000), max_cost_usd=1.0, max_prompt_tokens=32000) is None


def test_spend_cost_breaker_trips_at_ceiling():
    r = spend_halt_reason(_brain(1.0, 0), max_cost_usd=1.0, max_prompt_tokens=0)
    assert r and "cost breaker" in r            # >= is the trip (reached, not just exceeded)
    assert spend_halt_reason(_brain(0.99, 0), max_cost_usd=1.0, max_prompt_tokens=0) is None


def test_spend_prompt_token_cap_trips_strictly_above():
    assert spend_halt_reason(_brain(0, 32001), max_cost_usd=0, max_prompt_tokens=32000)  # over -> trip
    assert spend_halt_reason(_brain(0, 32000), max_cost_usd=0, max_prompt_tokens=32000) is None  # at cap ok


def test_spend_zero_thresholds_disable_each_check():
    assert spend_halt_reason(_brain(999.0, 999999), max_cost_usd=0, max_prompt_tokens=0) is None


def test_spend_cost_checked_before_prompt_tokens():
    # both would trip; the cost reason wins (it's the dollar ceiling, the headline guard)
    r = spend_halt_reason(_brain(2.0, 99999), max_cost_usd=1.0, max_prompt_tokens=32000)
    assert "cost breaker" in r


def test_spend_defensive_on_a_brain_without_meters():
    # a ScriptedBrain / bare autopilot has no spend meters -> getattr defaults to 0 -> never trips
    assert spend_halt_reason(object(), max_cost_usd=1.0, max_prompt_tokens=32000) is None


# -- wake_stall_halt_reason ----------------------------------------------------

def test_wake_stall_trips_at_threshold():
    assert wake_stall_halt_reason(woke=30, woke_at_progress=0, stuck_wakes=30)        # 30 stalled -> trip
    assert wake_stall_halt_reason(woke=29, woke_at_progress=0, stuck_wakes=30) is None  # 29 -> ok


def test_wake_stall_counts_from_the_progress_baseline():
    # progress reset the baseline to 50; 20 wakes since is under the 30 cap
    assert wake_stall_halt_reason(woke=70, woke_at_progress=50, stuck_wakes=30) is None
    assert wake_stall_halt_reason(woke=80, woke_at_progress=50, stuck_wakes=30)        # 30 since -> trip


def test_wake_stall_zero_disables():
    assert wake_stall_halt_reason(woke=999, woke_at_progress=0, stuck_wakes=0) is None


# -- end-to-end: the breaker actually halts a real run_episode loop -------------

def test_cost_breaker_halts_run_episode_end_to_end():
    from core.brains import HybridBrain, LLMButtonBrain
    from core.contracts import Observation
    from core.runner import run_episode

    class _P:  # minimal GamePlugin: an empty overworld observation, no tools, no events
        def observe(self, aid):
            return Observation(data={}, text="", agent_id=aid, t=0.0)
        def tools(self, aid):
            return []
        def drain_events(self):
            return []

    class _G:
        def execute(self, call):
            return type("R", (), {"data": {}})()

    class _NullAutopilot:  # always "stuck" so HybridBrain wakes the LLM every step
        agent_id = "a"
        last_thought = ""
        def decide(self, obs, tools, ctx):
            return None

    # Each wake meters 1000 prompt tokens = $0.001 (Haiku input rate), 0 output. Halt at $0.005.
    llm = LLMButtonBrain("a", complete_fn=lambda p, i: ("MOVE: a",
                                                        {"prompt_tokens": 1000, "completion_tokens": 0}))
    brain = HybridBrain(_NullAutopilot(), llm)
    summary = run_episode(
        _G(), _P(), brain, "a", max_steps=100,
        should_continue=lambda step: spend_halt_reason(
            brain, max_cost_usd=0.005, max_prompt_tokens=0) is None,
    )
    # should_continue runs BEFORE each decide: 5 wakes accrue $0.005, then the 6th check halts.
    assert brain.woke == 5 and summary["steps"] == 5
    assert brain.total_cost_usd == pytest.approx(0.005)


def test_prompt_token_cap_halts_run_episode_on_a_single_bloated_wake():
    from core.brains import HybridBrain, LLMButtonBrain
    from core.contracts import Observation
    from core.runner import run_episode

    class _P:
        def observe(self, aid):
            return Observation(data={}, text="", agent_id=aid, t=0.0)
        def tools(self, aid):
            return []
        def drain_events(self):
            return []

    class _G:
        def execute(self, call):
            return type("R", (), {"data": {}})()

    class _NullAutopilot:
        agent_id = "a"
        last_thought = ""
        def decide(self, obs, tools, ctx):
            return None

    # One lean wake, then a bloated one (50k prompt) that must trip the per-wake cap on the next check.
    replies = iter([
        ("MOVE: a", {"prompt_tokens": 1000, "completion_tokens": 0}),
        ("MOVE: a", {"prompt_tokens": 50000, "completion_tokens": 0}),
    ])
    llm = LLMButtonBrain("a", complete_fn=lambda p, i: next(replies))
    brain = HybridBrain(_NullAutopilot(), llm)
    summary = run_episode(
        _G(), _P(), brain, "a", max_steps=100,
        should_continue=lambda step: spend_halt_reason(
            brain, max_cost_usd=0, max_prompt_tokens=32000) is None,
    )
    assert summary["steps"] == 2 and brain.last_prompt_tokens == 50000
