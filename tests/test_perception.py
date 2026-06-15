"""Perception seam tests (Iteration 02, Step 1) — no ROM, no PyBoy.

Covers the SymbolicState contract, the StubPerceiver, and the plugin wiring: when a
perceiver is injected the agent sees a SymbolicState (pixels-derived) and RAM is written
ONLY to the oracle side-log — never into Observation.data (the no-leak wall).
"""
from __future__ import annotations

import json

import numpy as np

from core.brains import _call
from core.perception import PerceptMemory, Perceiver, StubPerceiver, SymbolicState
from games.pokemon_red import memory_map as mm
from games.pokemon_red.perceiver import OverworldPerceiver, _dominant_dir
from games.pokemon_red.plugin import PokemonRedPlugin
from tests.test_pokemon_red import FakeEmulator


def _frame(val: int):
    return np.full((144, 160, 4), val, dtype=np.uint8)

ROLE_KEYS = {"confidence", "context", "pose", "spatial_memory",
             "affordances", "last_action", "raw_available", "raw_ref"}


def test_symbolicstate_is_role_named_and_json_able():
    d = SymbolicState(confidence=0.3, context="overworld", raw_ref="f.png").to_dict()
    assert set(d) == ROLE_KEYS
    assert d["confidence"] == 0.3 and d["raw_ref"] == "f.png"
    json.dumps(d)  # must be JSON-serializable (crosses the gateway)


def test_stub_perceiver_points_at_frame_and_is_low_confidence():
    s = StubPerceiver().perceive("frame_0.png", PerceptMemory())
    assert s.confidence == 0.0 and s.raw_available and s.raw_ref == "frame_0.png"


def test_stub_satisfies_the_perceiver_protocol():
    assert isinstance(StubPerceiver(), Perceiver)


def test_plugin_without_perceiver_is_unchanged(tmp_path):
    p = PokemonRedPlugin(emulator=FakeEmulator(), out_dir=str(tmp_path))
    obs = p.observe("a")
    assert "map_id" in obs.data and "screen_path" in obs.data       # legacy RAM obs
    assert not (tmp_path / "oracle.jsonl").exists()                 # no oracle log without perception


def test_plugin_with_perceiver_emits_symbolic_and_does_not_leak_ram(tmp_path):
    emu = FakeEmulator()
    emu.mem[mm.ADDR_MAP_ID] = 38
    emu.mem[mm.ADDR_X] = 3
    emu.mem[mm.ADDR_Y] = 7
    p = PokemonRedPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=StubPerceiver())
    obs = p.observe("a")

    # The agent sees the role-named SymbolicState...
    assert set(obs.data) >= ROLE_KEYS
    assert obs.data["raw_ref"].endswith(".png")
    # ...and RAM is NOT leaked into the agent's input.
    assert "x" not in obs.data and "y" not in obs.data and "map_id" not in obs.data

    # RAM ground-truth lives only in the oracle side-channel, paired with the perceiver's verdict.
    rec = json.loads((tmp_path / "oracle.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert rec["map_id"] == 38 and rec["x"] == 3 and rec["y"] == 7
    assert "perceived" in rec  # the paired (truth ⟂ perceived) record the scorer reads


# -- OverworldPerceiver: odometry + occupancy map (Step 2) --------------------

def test_dominant_dir_takes_net_direction():
    assert _dominant_dir("up+up+up") == "up"
    assert _dominant_dir("right+a") == "right"
    assert _dominant_dir("a") is None and _dominant_dir(None) is None


def test_first_obs_inits_pose_and_is_unknown_outcome():
    s = OverworldPerceiver().perceive(_frame(0), PerceptMemory(),
                                      {"frame_path": "f.png", "last_action": None})
    assert s.context == "overworld" and s.pose["value"] == [0, 0]
    assert s.last_action["outcome"] == "unknown" and s.raw_ref == "f.png"


def test_moved_advances_the_dead_reckoned_cursor():
    per, mem = OverworldPerceiver(move_threshold=4.0, area_threshold=300.0), PerceptMemory()
    per.perceive(_frame(0), mem, {"last_action": None})            # prime prev_frame
    s = per.perceive(_frame(200), mem, {"last_action": "down+down+down"})  # move (< area thr) ⇒ moved
    assert s.last_action["outcome"] == "moved" and s.pose["value"] == [0, 1]


def test_area_change_resets_the_coordinate_frame():
    per, mem = OverworldPerceiver(move_threshold=4.0, area_threshold=100.0), PerceptMemory()
    per.perceive(_frame(0), mem, {"last_action": None})            # prime
    per.perceive(_frame(10), mem, {"last_action": "down+down"})    # diff 10 ⇒ moved within area -> (0,1)
    s = per.perceive(_frame(200), mem, {"last_action": "down+down"})  # big diff (still overworld) ⇒ AREA transition
    assert s.last_action["outcome"] == "moved"
    assert s.pose["value"] == [0, 0] and s.pose["area"] == 1       # fresh frame, area incremented


def test_detect_mode_separates_overworld_menu_dialog_battle():
    from games.pokemon_red.perceiver import detect_mode
    blank = lambda: np.full((144, 160, 3), 60, dtype=np.uint8)  # dark scene, no UI panel
    overworld = blank()
    menu = blank(); menu[:96, 96:] = 255          # white right panel (upper) — the START menu
    dialog = blank(); dialog[96:, :] = 255         # white bottom textbox
    battle = blank(); battle[:58, :] = 255; battle[96:, :] = 255  # white top (HP) + bottom (action)
    assert detect_mode(overworld) == "overworld"
    assert detect_mode(menu) == "menu"
    assert detect_mode(dialog) == "dialog"
    assert detect_mode(battle) == "battle"


def test_detect_mode_uniform_fade_is_not_battle():
    """Regression: a near-uniform fade/flash frame must NOT read as 'battle'. Measured on real
    pixels, an all-white starter-cutscene flash (std 0) tripped the bright-top-AND-bottom battle
    rule; real battle frames have std > 65 (dark sprites on white), so the uniformity guard
    separates them. Both all-white and all-black fades fall back to overworld (a transient blank)."""
    from games.pokemon_red.perceiver import detect_mode
    assert detect_mode(np.full((144, 160, 3), 255, dtype=np.uint8)) == "overworld"  # white flash
    assert detect_mode(np.full((144, 160, 3), 0, dtype=np.uint8)) == "overworld"    # black fade
    # a battle-like frame (white bg + a dark sprite block => high contrast) still reads as battle
    batt = np.full((144, 160, 3), 255, dtype=np.uint8)
    batt[20:50, 90:140] = 30   # enemy sprite patch -> std well above the guard
    batt[60:96, 10:60] = 30    # player sprite patch
    assert detect_mode(batt) == "battle"


def test_perceive_hands_off_non_overworld_and_rebaselines_on_return():
    per, mem = OverworldPerceiver(), PerceptMemory()
    menu = np.full((144, 160, 3), 60, dtype=np.uint8); menu[:96, 96:] = 255
    s = per.perceive(menu, mem, {"frame_path": "f.png", "last_action": "up+up"})
    assert s.context == "menu" and s.last_action["outcome"] == "n/a" and s.raw_ref == "f.png"
    ow = np.full((144, 160, 3), 60, dtype=np.uint8)               # back to overworld
    s2 = per.perceive(ow, mem, {"frame_path": "g.png", "last_action": "up+up"})
    assert s2.context == "overworld" and s2.last_action["outcome"] == "unknown"  # re-baselined, no fake move


def test_blocked_marks_a_wall_and_drops_that_direction():
    per, mem = OverworldPerceiver(move_threshold=4.0), PerceptMemory()
    f = _frame(50)
    per.perceive(f, mem, {"last_action": None})
    s = per.perceive(f.copy(), mem, {"last_action": "up+up+up"})   # identical ⇒ blocked
    assert s.last_action["outcome"] == "blocked"
    assert s.pose["value"] == [0, 0]                                # did not move
    assert "up" in s.spatial_memory["walls_here"]
    assert "up" not in s.affordances                               # the wall direction isn't offered


def test_plugin_perception_run_logs_odometry_and_aliases_screen_path(tmp_path):
    emu = FakeEmulator()
    emu._screen = _frame(10)
    p = PokemonRedPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=OverworldPerceiver())
    obs = p.observe("a")
    assert obs.data["pose"]["value"] == [0, 0]                      # symbolic state surfaced
    assert obs.data["screen_path"].endswith(".png")                # raw_ref aliased for the brain
    assert "Overworld exploration" in obs.text                     # navigation-rich render
    assert "map_id" not in obs.data                                # still no RAM leak


# -- the scorer (Iteration 03, Step 1: the measurement rig) -------------------

def test_scorer_walkability_confusion_and_escape():
    from eval.score_perception import score
    recs = [
        {"step": 1, "map_id": 38, "x": 3, "y": 7, "perceived": {"outcome": "unknown"}},
        {"step": 2, "map_id": 38, "x": 3, "y": 6, "perceived": {"outcome": "moved"}},    # truth moved  -> correct
        {"step": 3, "map_id": 38, "x": 3, "y": 6, "perceived": {"outcome": "blocked"}},  # truth still  -> correct
        {"step": 4, "map_id": 38, "x": 3, "y": 6, "perceived": {"outcome": "moved"}},    # truth still  -> false_moved
        {"step": 5, "map_id": 37, "x": 3, "y": 6, "perceived": {"outcome": "blocked"}},  # map changed  -> missed move
    ]
    m = score(recs)
    assert m["scored_moves"] == 4
    assert abs(m["walkability_accuracy"] - 0.5) < 1e-9             # 2 of 4 correct
    c = m["confusion"]
    assert (c["true_moved"], c["true_blocked"], c["false_moved"], c["false_blocked_missed_move"]) == (1, 1, 1, 1)
    assert m["escaped_start_map"] and m["escape_step"] == 5
    assert m["maps_visited"] == [37, 38]


# -- ExploreBrain: local frontier autopilot (no LLM) --------------------------

def _obs_with_map(pose, cells, frontiers):
    from core.contracts import Observation
    return Observation(
        data={"pose": {"value": list(pose)},
              "spatial_memory": {"map": cells, "frontiers": frontiers}},
        text="", agent_id="a", t=0.0)


def test_explore_steps_into_the_open_unexplored_direction():
    from core.brains import ExploreBrain
    cells = [{"x": 0, "y": 0, "visited": True, "walls": ["up", "left", "right"]}]  # only down open, unknown
    call = ExploreBrain("a").decide(_obs_with_map((0, 0), cells, [[0, 0]]), [], {})
    assert call.tool == "press_sequence" and call.args["buttons"] == ["down", "down"]


def test_explore_bfs_paths_to_a_distant_frontier():
    from core.brains import ExploreBrain
    cells = [
        {"x": 0, "y": 0, "visited": True, "walls": ["up", "down", "left"]},   # only right, to visited (1,0)
        {"x": 1, "y": 0, "visited": True, "walls": ["up", "down"]},
        {"x": 2, "y": 0, "visited": True, "walls": ["up", "left"]},           # down/right unknown => frontier
    ]
    call = ExploreBrain("a").decide(_obs_with_map((0, 0), cells, [[2, 0]]), [], {})
    assert call.tool == "press_sequence" and call.args["buttons"][0] == "right"


def test_explore_returns_none_when_no_frontier_remains():
    from core.brains import ExploreBrain
    cells = [{"x": 0, "y": 0, "visited": True, "walls": ["up", "down", "left", "right"]}]
    assert ExploreBrain("a").decide(_obs_with_map((0, 0), cells, []), [], {}) is None


def test_explore_goto_pathfinds_to_a_named_target_cell():
    from core.brains import ExploreBrain
    cells = [
        {"x": 0, "y": 0, "visited": True, "walls": ["up", "down", "left"]},   # right -> (1,0)
        {"x": 1, "y": 0, "visited": True, "walls": ["up", "down"]},
        {"x": 2, "y": 0, "visited": True, "walls": ["up", "down", "right"]},  # the target
    ]
    obs = _obs_with_map((0, 0), cells, [])                       # no frontiers; only a goto target
    call = ExploreBrain("a").decide(obs, [], {"goto": [2, 0]})
    assert call.tool == "press_sequence" and call.args["buttons"][0] == "right"


# -- HybridBrain: event-driven autopilot + wake-the-LLM router ----------------

class _StubBrain:
    def __init__(self, action, thought=""):
        self._a, self.last_thought = action, thought

    def decide(self, obs, tools, context):
        return self._a


def _ctx_obs(context="overworld"):
    from core.contracts import Observation
    return Observation(data={"context": context}, text="", agent_id="a", t=0.0)


def test_hybrid_uses_free_autopilot_when_it_acts():
    from core.brains import HybridBrain, _call
    ap = _StubBrain(_call("press_sequence", {"buttons": ["down", "down"]}, "a"), "explore")
    h = HybridBrain(ap, _StubBrain(_call("press_button", {"button": "a"}, "a")))
    call = h.decide(_ctx_obs("overworld"), [], {})
    assert call.args.get("buttons") == ["down", "down"] and h.woke == 0  # LLM untouched


def test_hybrid_wakes_llm_when_autopilot_is_stuck():
    from core.brains import HybridBrain, _call
    h = HybridBrain(_StubBrain(None), _StubBrain(_call("press_button", {"button": "a"}, "a"), "llm"))
    call = h.decide(_ctx_obs("overworld"), [], {})
    assert call.args.get("button") == "a" and h.woke == 1 and h.mode == "llm"


def test_hybrid_wakes_llm_on_non_overworld_mode():
    from core.brains import HybridBrain, _call
    ap = _StubBrain(_call("press_button", {"button": "up"}, "a"))  # autopilot WOULD act...
    h = HybridBrain(ap, _StubBrain(_call("press_button", {"button": "a"}, "a")))
    call = h.decide(_ctx_obs("battle"), [], {})                    # ...but mode != overworld wakes the LLM
    assert call.args.get("button") == "a" and h.woke == 1


# -- outcome loop (feature #1: learn from no-effect actions) ------------------

def test_outcome_memory_marks_repeated_no_effect_and_resets_on_effect():
    from core.outcome import OutcomeMemory
    om = OutcomeMemory(dead_after=2)
    sig = ("overworld", 0, (0, 0))
    om.record(sig, "a", effective=False); assert not om.is_dead(sig, "a")
    om.record(sig, "a", effective=False); assert om.is_dead(sig, "a") and "a" in om.dead_actions(sig)
    om.record(sig, "a", effective=True);  assert not om.is_dead(sig, "a")  # any effect resets the streak


def test_state_signature_and_action_key():
    from core.contracts import ToolCall
    from core.outcome import action_key, state_signature
    assert state_signature({"context": "overworld", "pose": {"value": [1, 2], "area": 0}}) == ("overworld", 0, (1, 2))
    c = ToolCall(tool="press_sequence", args={"buttons": ["up", "up"]}, agent_id="a", call_id="1")
    assert action_key(c) == "up+up"


def test_hybrid_surfaces_dead_actions_to_the_fallback():
    from core.brains import HybridBrain, _call

    class _Capturing:
        def __init__(self, call): self._c, self.last_thought, self.seen = call, "", None
        def decide(self, obs, tools, context): self.seen = context.get("avoid"); return self._c

    fb = _Capturing(_call("press_button", {"button": "a"}, "a"))
    h = HybridBrain(_StubBrain(None), fb)        # autopilot always stuck -> fallback every step
    obs = _ctx_obs("overworld")                   # fixed signature -> 'a' never changes anything
    for _ in range(4):
        h.decide(obs, [], {})
    assert "a" in (fb.seen or [])                 # repeated no-effect 'a' became an 'avoid' hint


# -- goto hookup (feature #2: planner names a destination, free autopilot drives there) ----

def test_llm_brain_parses_optional_goto_target():
    from core.brains import LLMButtonBrain
    from core.contracts import Observation
    obs = Observation(data={"screen_path": ""}, text="x", agent_id="a", t=0.0)
    b = LLMButtonBrain("a", use_vision=False,
                       complete_fn=lambda p, i: "THINK: head to the door\nMOVE: right right\nGOTO: 2 0")
    b.decide(obs, [], {})
    assert b.goto == [2, 0]                        # destination parsed only from the GOTO line
    b2 = LLMButtonBrain("a", use_vision=False,
                        complete_fn=lambda p, i: "THINK: go to the stairs\nMOVE: down down")
    b2.decide(obs, [], {})
    assert b2.goto is None                          # 'to the stairs' in prose is NOT a target


def _pose_obs(pose, context="overworld"):
    from core.contracts import Observation
    return Observation(data={"context": context, "pose": {"value": list(pose)}},
                       text="", agent_id="a", t=0.0)


class _GotoCapturingAutopilot:
    """Records the goto handed to it; acts only when a target is present (else 'stuck' -> wake)."""
    def __init__(self):
        self.last_thought, self.seen = "", []
    def decide(self, obs, tools, context):
        g = context.get("goto")
        self.seen.append(g)
        return _call("press_sequence", {"buttons": ["right", "right"]}, "a") if g else None


def test_hybrid_adopts_planner_goto_then_drives_there_for_free():
    from core.brains import HybridBrain, _call

    class _GotoSetter:
        last_thought = "make for the exit"
        goto = [2, 0]
        def decide(self, obs, tools, context):
            return _call("press_button", {"button": "a"}, "a")

    ap = _GotoCapturingAutopilot()
    h = HybridBrain(ap, _GotoSetter())
    h.decide(_pose_obs((0, 0)), [], {})            # autopilot stuck -> wake LLM -> adopt goto [2,0]
    assert h.woke == 1 and h.goto == [2, 0] and ap.seen[-1] is None  # target adopted AFTER this step
    c2 = h.decide(_pose_obs((1, 0)), [], {})       # next step: free autopilot pursues the target
    assert ap.seen[-1] == [2, 0] and c2.args["buttons"] == ["right", "right"] and h.woke == 1


def test_hybrid_clears_goto_on_arrival():
    from core.brains import HybridBrain, _call
    h = HybridBrain(_GotoCapturingAutopilot(),
                    _StubBrain(_call("press_button", {"button": "a"}, "a")))
    h.goto = [1, 1]
    h.decide(_pose_obs((1, 1)), [], {})            # pose == target -> destination consumed
    assert h.goto is None
