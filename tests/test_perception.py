"""Perception seam tests (Iteration 02, Step 1) — no ROM, no PyBoy.

Covers the SymbolicState contract, the StubPerceiver, and the plugin wiring: when a
perceiver is injected the agent sees a SymbolicState (pixels-derived) and RAM is written
ONLY to the oracle side-log — never into Observation.data (the no-leak wall).
"""
from __future__ import annotations

import json

import numpy as np

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
    per, mem = OverworldPerceiver(move_threshold=4.0), PerceptMemory()
    per.perceive(_frame(0), mem, {"last_action": None})            # prime prev_frame
    s = per.perceive(_frame(200), mem, {"last_action": "down+down+down"})  # big diff ⇒ moved
    assert s.last_action["outcome"] == "moved" and s.pose["value"] == [0, 1]


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
