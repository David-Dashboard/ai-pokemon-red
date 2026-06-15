"""GateWorld (gating probe) tests — no ROM, no API, all $0.

Covers the world mechanics (turn-then-move / blocked / pickup / gate / goal), the role-named
SymbolicState it emits (so the existing brains run on it unchanged), and the two integration
claims the probe rests on:
  * the free autopilot ALONE cannot open the gate (it only moves, never interacts) — so class-2
    reasoning is genuinely required, and
  * the SAME HybridBrain(ExploreBrain, reasoner) loop solves BOTH skins with the scripted oracle.
"""
from __future__ import annotations

import uuid

from core.contracts import GamePlugin, ToolCall
from core.brains import ExploreBrain, HybridBrain
from core.gateway import Gateway
from core.permissions import GATEWORLD_SANDBOX
from core.runner import run_episode
from games.gateworld import FAMILIAR, GateWorld, NOVEL, ScriptedReasoner


def _press(world: GateWorld, button: str):
    call = ToolCall(tool="press_button", args={"button": button}, agent_id="a", call_id="c")
    return world.handle(call)


def _outcome(world, button) -> str:
    return _press(world, button).data["outcome"]


def test_gateworld_satisfies_the_gameplugin_protocol():
    assert isinstance(GateWorld(), GamePlugin)


def test_press_in_a_new_direction_turns_first_then_steps():
    w = GateWorld(["S."])           # (0,0)=start facing 'down'; (1,0) is floor
    assert _outcome(w, "right") == "turned" and w.pos == (0, 0)   # only turned
    assert _outcome(w, "right") == "moved" and w.pos == (1, 0)    # now steps


def test_walking_into_a_wall_is_blocked_and_does_not_move():
    w = GateWorld(["S#"])           # wall to the right
    _press(w, "right")              # turn to face the wall
    assert _outcome(w, "right") == "blocked" and w.pos == (0, 0)


def test_pick_up_item_with_A_on_its_tile():
    w = GateWorld(["SK"])           # item at (1,0)
    _press(w, "right"); _press(w, "right")     # turn+step onto the item tile
    assert w.pos == (1, 0)
    assert _outcome(w, "a") == "picked" and w.has_item and w.item is None


def test_gate_needs_the_item_then_opens_and_lets_you_through_to_the_goal():
    w = GateWorld(["SKGX"])         # start, item, gate, goal in a line
    # adjacent to the gate WITHOUT the item -> it won't open
    _press(w, "right"); _press(w, "right")     # step onto item tile (1,0)
    # try the gate before having the item: move to be adjacent (already at (1,0), gate at (2,0))
    assert _outcome(w, "a") == "picked"        # first A here picks the item up
    assert _outcome(w, "a") == "unlocked" and w.gate_open   # now adjacent+carrying -> opens
    # walk through the opened gate to the goal
    _press(w, "right")                          # already facing right -> step to gate (2,0)
    assert w.pos == (2, 0)
    _press(w, "right")                          # step to goal (3,0)
    assert w.pos == (3, 0) and w.solved


def test_gate_without_item_reports_needs_item():
    w = GateWorld(["SG"])           # adjacent to a gate, no item anywhere
    _press(w, "right")              # face the gate
    assert _outcome(w, "a") == "needs_item" and not w.gate_open


def test_reaching_goal_emits_reward_event():
    w = GateWorld(["SKGX"])
    _press(w, "right"); _press(w, "right"); _press(w, "a"); _press(w, "a")  # get item, open gate
    _press(w, "right"); _press(w, "right")                                  # to (2,0) then (3,0)
    events = w.drain_events()
    assert any(e.type == "goal_reached" and e.reward == 1.0 for e in events)


def test_observe_emits_role_named_symbolic_state_for_the_same_brains():
    w = GateWorld()
    obs = w.observe("a")
    for k in ("context", "pose", "spatial_memory", "affordances", "last_action", "confidence"):
        assert k in obs.data
    assert obs.data["context"] == "overworld"
    sm = obs.data["spatial_memory"]
    assert sm["kind"] == "occupancy-grid" and isinstance(sm["map"], list)
    cell = sm["map"][0]
    assert {"x", "y", "visited", "walls"} <= set(cell)


def test_autopilot_alone_cannot_open_the_gate():
    """ExploreBrain only moves — it never presses A — so it explores the reachable side and gets
    stuck. Class-2 reasoning is genuinely required; the gate is never opened by exploration."""
    aid = f"agent-{uuid.uuid4()}"
    w = GateWorld()
    gw = Gateway(w, GATEWORLD_SANDBOX)
    run_episode(gw, w, ExploreBrain(aid), aid, max_steps=120)
    assert not w.solved and not w.gate_open and not w.has_item


def test_hybrid_loop_solves_both_skins_with_the_scripted_reasoner():
    for theme in (FAMILIAR, NOVEL):
        aid = f"agent-{uuid.uuid4()}"
        w = GateWorld(theme=theme)
        brain = HybridBrain(ExploreBrain(aid), ScriptedReasoner(aid))
        gw = Gateway(w, GATEWORLD_SANDBOX)
        run_episode(gw, w, brain, aid, max_steps=120)
        assert w.solved, f"scripted oracle should solve the {theme.name} skin"
        assert brain.woke > 0  # the reasoner was genuinely needed (autopilot got stuck at the gate)
