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


def _scene(seed: int = 1):
    """A TEXTURED frame (deterministic) — a 'map' with structure so a translation can align it. Values
    stay < 230 so detect_mode reads it as overworld (no near-white UI panel)."""
    g = np.random.RandomState(seed).randint(0, 200, size=(144, 160), dtype=np.uint16).astype(np.uint8)
    f = np.zeros((144, 160, 4), dtype=np.uint8)
    f[..., 0] = f[..., 1] = f[..., 2] = g
    f[..., 3] = 255
    return f


def _scroll(scene, dx_tiles: int = 0, dy_tiles: int = 0):
    """Simulate the camera scrolling when the player moves (dx_tiles, dy_tiles): the overlap then
    aligns at a +N-tile shift, exactly as a real same-map move does (vs an unrelated _scene = a warp)."""
    return np.roll(np.roll(scene, -dy_tiles * 16, axis=0), -dx_tiles * 16, axis=1)

ROLE_KEYS = {"confidence", "context", "pose", "spatial_memory",
             "affordances", "last_action", "screen_text", "raw_available", "raw_ref"}


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
    per, mem = OverworldPerceiver(), PerceptMemory()
    scene = _scene()
    per.perceive(scene, mem, {"last_action": None})                # prime prev_frame
    s = per.perceive(_scroll(scene, dy_tiles=1), mem, {"last_action": "down+down"})  # scrolled 1 tile down
    assert s.last_action["outcome"] == "moved" and s.pose["value"] == [0, 1]


def test_odometry_records_measured_distance_and_marks_traversed_cells():
    # Measured-distance odometry (the run-#15 interior-DRIFT fix): a multi-tile scroll advances the
    # cursor by the TRUE tiles moved (best-shift magnitude), not a capped 1. Capping at one was the
    # drift: [d,d] moved two tiles but recorded one, so the occupancy map corrupted in the lab room.
    # Every cell stepped THROUGH is marked visited (no phantom mid-path frontier).
    per, mem = OverworldPerceiver(), PerceptMemory()
    scene = _scene()
    per.perceive(scene, mem, {"last_action": None})
    s = per.perceive(_scroll(scene, dx_tiles=3), mem, {"last_action": "right+right+right"})
    assert s.last_action["outcome"] == "moved" and s.pose["value"] == [3, 0]
    assert s.last_action["tiles"] == 3
    cells = {(c["x"], c["y"]): c for c in s.spatial_memory["map"]}
    assert all((cx, 0) in cells and cells[(cx, 0)]["visited"] for cx in (1, 2, 3))  # traversed cells


def test_odometry_clamps_a_mis_measured_scroll_to_the_search_range():
    # A defensive clamp: a wildly large best-shift magnitude can't fling the cursor beyond the
    # +/- search range (4 tiles), so a single bad measurement degrades gracefully, never explodes.
    per, mem = OverworldPerceiver(), PerceptMemory()
    scene = _scene()
    per.perceive(scene, mem, {"last_action": None})
    s = per.perceive(_scroll(scene, dy_tiles=4), mem, {"last_action": "down+down"})
    assert s.last_action["outcome"] == "moved" and abs(s.pose["value"][1]) <= 4


def test_perceiver_surfaces_a_motion_roi_for_a_moving_sprite():
    # Motion-saliency wiring: on a CAMERA-STATIC step (no scroll) a changed off-centre tile is a moving
    # entity -> recorded as an ROI at its world cell (player cell + the on-screen offset from centre).
    per, mem = OverworldPerceiver(), PerceptMemory()
    scene = _scene()
    per.perceive(scene, mem, {"last_action": None})        # prime prev_frame (first=True, no odometry)
    moved = scene.copy()
    moved[0:16, 0:16, :3] = 255 - moved[0:16, 0:16, :3]    # invert one off-centre tile = a 'sprite' moved
    s = per.perceive(moved, mem, {"last_action": "up+up"})  # blocked (no scroll) -> camera static
    rois = s.spatial_memory.get("rois")
    assert rois and [-4, -4] in rois        # screen tile (0,0) is 4 left & 4 up of the centred player


def test_perceiver_no_roi_when_camera_scrolled():
    # A real MOVE scrolls the whole frame; that is not camera-static, so a frame diff is meaningless and
    # no ROI is recorded (the detector must only run on aligned frames).
    per, mem = OverworldPerceiver(), PerceptMemory()
    scene = _scene()
    per.perceive(scene, mem, {"last_action": None})
    s = per.perceive(_scroll(scene, dy_tiles=1), mem, {"last_action": "down+down"})  # camera scrolled 1 tile
    assert not s.spatial_memory.get("rois")


def test_area_change_resets_the_coordinate_frame():
    per, mem = OverworldPerceiver(move_threshold=4.0, area_threshold=100.0), PerceptMemory()
    per.perceive(_frame(0), mem, {"last_action": None})            # prime
    per.perceive(_frame(10), mem, {"last_action": "down+down"})    # diff 10 ⇒ moved within area -> (0,1)
    s = per.perceive(_frame(200), mem, {"last_action": "down+down"})  # big diff (still overworld) ⇒ AREA transition
    assert s.last_action["outcome"] == "moved"
    assert s.pose["value"] == [0, 0] and s.pose["area"] == 1       # fresh frame, area incremented


def test_place_graph_round_trip_returns_to_the_known_place():
    """Place-graph (the run-#4 lab fix): a WARP (no translation aligns the frames) mints a NEW place;
    taking the door BACK returns to the SAME place with its accumulated map restored — not a freshly
    minted place 2 — and the door we left by is sealed as a portal (walkable, not a frontier), so the
    autopilot can't ping-pong the seam (the old door-oscillation bug)."""
    per, mem = OverworldPerceiver(), PerceptMemory()
    a, b = _scene(1), _scene(2)                                    # two unrelated 'maps' (no shift aligns)
    per.perceive(a, mem, {"last_action": None})                    # place 0, (0,0)
    per.perceive(_scroll(a, dy_tiles=1), mem, {"last_action": "down+down"})   # -> (0,1) in place 0
    s1 = per.perceive(b, mem, {"last_action": "down+down"})        # scene cut => WARP to a new place
    assert s1.pose["area"] == 1 and s1.pose["value"] == [0, 0]
    # door-back: a real door warp FADES, so the fade flag fires through the post-warp re-baseline and
    # the reverse edge restores place 0 (the translation path alone is suppressed for that one frame).
    s2 = per.perceive(a, mem, {"last_action": "up+up", "transition": True})
    assert s2.pose["area"] == 0                                    # the KNOWN place, restored (not place 2)
    cells = {(c["x"], c["y"]): c for c in s2.spatial_memory["map"]}
    assert (0, 1) in cells                                         # place 0's accumulated map is back
    assert any(c.get("portal") == 1 for c in s2.spatial_memory["map"])   # the door out is sealed
    assert s2.spatial_memory["places_known"] == 2                  # exactly two places, no spurious mint


def test_warp_seals_both_doors_but_keeps_the_arrival_explorable():
    # Anti-ping-pong (the house-door oscillation the closed-loop autopilot hit): BOTH ends of a door are
    # sealed as portals (not frontiers) — the source cell AND the cell BEHIND the arrival — while the
    # arrival cell itself stays a frontier so the frontier-only autopilot can still explore the new place.
    per, mem = OverworldPerceiver(), PerceptMemory()
    a, b = _scene(1), _scene(2)
    per.perceive(a, mem, {"last_action": None})
    per.perceive(_scroll(a, dy_tiles=1), mem, {"last_action": "down+down"})   # -> (0,1) in place 0
    s = per.perceive(b, mem, {"last_action": "down+down"})        # warp into place 1 (entered moving down)
    cells = {(c["x"], c["y"]): c for c in s.spatial_memory["map"]}
    assert s.pose["value"] == [0, 0]
    assert cells[(0, 0)].get("portal") is None                   # arrival stays explorable
    assert cells[(0, -1)].get("portal") == 0                     # the way back is sealed
    assert [0, 0] in s.spatial_memory["frontiers"]               # ...so the new place IS explorable
    assert [0, -1] not in s.spatial_memory["frontiers"]          # ...but the door-back isn't a target


def test_fade_flag_triggers_transition_even_right_after_a_menu():
    # The run-#4 DOMINANT miss: a warp right after a (mis)classified menu frame. The translation has no
    # valid overworld `prev` to compare (first/resync), but the emulator's pixels-only FADE flag still
    # forces the place transition — which the old diff path suppressed.
    per, mem = OverworldPerceiver(), PerceptMemory()
    per.perceive(_scene(1), mem, {"last_action": None})                       # place 0
    menu = np.full((144, 160, 3), 60, dtype=np.uint8); menu[:96, 96:] = 255
    per.perceive(menu, mem, {"last_action": "up+up"})                         # menu => resync (next is first)
    s = per.perceive(_scene(2), mem, {"last_action": "up+up", "transition": True})  # fade flag set
    assert s.pose["area"] == 1                                                # transitioned despite first


def test_scene_cut_without_a_fade_flag_still_warps():
    # A warp that does NOT fade (interior stairs) is still caught: no translation aligns the frames, so
    # the scene-cut residual exceeds the threshold => a new place. No emulator fade flag needed.
    per, mem = OverworldPerceiver(), PerceptMemory()
    per.perceive(_scene(1), mem, {"last_action": None})
    per.perceive(_scroll(_scene(1), dx_tiles=1), mem, {"last_action": "right+right"})   # a real move
    s = per.perceive(_scene(7), mem, {"last_action": "right+right"})          # scene cut, no fade flag
    assert s.pose["area"] == 1


def test_plugin_threads_emulator_fade_into_perceiver_context(tmp_path):
    # Wiring: the plugin must hand the emulator's fade flag to the perceiver as context['transition'],
    # so a warp resets the dead-reckoning frame. Verified with a spy perceiver.
    from core.contracts import ToolCall
    seen: dict = {}

    class Spy:
        def perceive(self, frame, memory, context=None):
            seen.update(context or {})
            return SymbolicState(confidence=0.4, context="overworld", raw_ref="")

    emu = FakeEmulator()
    emu._faded = True
    p = PokemonRedPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=Spy())
    p.handle(ToolCall(tool="press_button", args={"button": "up"}, agent_id="a", call_id="c"))
    p.observe("a")
    assert seen.get("transition") is True


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


def test_detect_mode_choice_box_over_textbox_is_menu():
    """A bottom textbox that ALSO carries a small selection box (a YES/NO) in the upper-right is a
    CHOICE, not plain text — it must read as 'menu' (wake the LLM), so it is never auto-advanced.
    Grounded on real frames: plain dialog scores ~0 in that region, a real YES/NO box ~0.33."""
    from games.pokemon_red.perceiver import detect_mode
    choice = np.full((144, 160, 3), 60, dtype=np.uint8)
    choice[96:, :] = 255          # the bottom textbox ("give a nickname to ...?")
    choice[32:72, 120:156] = 255  # a YES/NO selection box in the upper-right
    assert detect_mode(choice) == "menu"


def test_detect_mode_choice_box_low_above_textbox_still_menu():
    # A choice box sitting LOW (rows ~78-88, just above the textbox) must still read 'menu' — the
    # region reaches down to ~row 89 so such a box isn't missed and then auto-advanced as a choice.
    from games.pokemon_red.perceiver import detect_mode
    low = np.full((144, 160, 3), 60, dtype=np.uint8)
    low[96:, :] = 255
    low[52:88, 120:156] = 255     # a normal-height selection box, positioned low (ends just above textbox)
    assert detect_mode(low) == "menu"


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


def test_detect_mode_bright_overworld_is_not_menu():
    # Regression (run #4): a bright OUTDOOR scene (Pallet's white roofs/paths) pushes a region into the
    # 0.15-0.3 band but is NOT a UI panel. It must read 'overworld', not 'menu' — the old catch-all
    # mislabeled it, forcing a resync that masked the very next map warp (the 0<->39 lumping).
    from games.pokemon_red.perceiver import detect_mode
    bright = np.full((144, 160, 3), 100, dtype=np.uint8)
    bright[100:, :40] = 255       # near-white strip along the bottom (~0.22 of the bottom region)
    bright[:30, 110:] = 255       # bright building roof, upper-right (well under the 0.35 menu bar)
    assert detect_mode(bright) == "overworld"


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

def _obs_with_map(pose, cells, frontiers, rois=None, area=None, portals=None, place_frontiers=None):
    from core.contracts import Observation
    return Observation(
        data={"pose": {"value": list(pose), "area": area},
              "spatial_memory": {"map": cells, "frontiers": frontiers, "rois": rois or [],
                                 "place_portals": portals or [],
                                 "place_frontiers": place_frontiers or []}},
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


def test_explore_single_step_presses_one_button_per_tile():
    # The run-#15 drift fix: with single_step the autopilot presses the direction ONCE ([d]) so a move
    # is exactly one tile on the real emulator (the held press absorbs the turn). The agnostic default
    # stays [d, d]. Same map/frontier, only the press encoding differs.
    from core.brains import ExploreBrain
    cells = [{"x": 0, "y": 0, "visited": True, "walls": ["up", "left", "right"]}]  # only down open
    obs = _obs_with_map((0, 0), cells, [[0, 0]])
    assert ExploreBrain("a", single_step=True).decide(obs, [], {}).args["buttons"] == ["down"]
    assert ExploreBrain("a").decide(obs, [], {}).args["buttons"] == ["down", "down"]  # default unchanged


def test_explore_single_step_goto_first_step_is_one_press():
    from core.brains import ExploreBrain
    cells = [
        {"x": 0, "y": 0, "visited": True, "walls": ["up", "down", "left"]},   # right -> (1,0)
        {"x": 1, "y": 0, "visited": True, "walls": ["up", "down"]},
        {"x": 2, "y": 0, "visited": True, "walls": ["up", "down", "right"]},
    ]
    obs = _obs_with_map((0, 0), cells, [])
    call = ExploreBrain("a", single_step=True).decide(obs, [], {"goto": [2, 0]})
    assert call.args["buttons"] == ["right"]   # one press toward the target, not [right, right]


def test_explore_returns_none_when_no_frontier_remains():
    from core.brains import ExploreBrain
    cells = [{"x": 0, "y": 0, "visited": True, "walls": ["up", "down", "left", "right"]}]
    assert ExploreBrain("a").decide(_obs_with_map((0, 0), cells, []), [], {}) is None


def test_explore_crosses_to_a_place_that_still_has_frontiers():
    # Cross-place exploration: this room (area 1, 'the lab') is fully explored, but place 0 ('Pallet')
    # still has a frontier — so route to the door back to it instead of getting stuck (the lab trap).
    from core.brains import ExploreBrain
    cells = [{"x": 0, "y": 0, "visited": True, "walls": ["up", "left", "right"]},       # only down is open
             {"x": 0, "y": 1, "visited": True, "walls": ["left", "right", "down"], "portal": 0}]  # the door
    portals = [[1, [0, 1], "down", 0], [0, [3, 3], "up", 1]]   # lab<->Pallet door edges (with cross dir)
    obs = _obs_with_map((0, 0), cells, [], area=1, portals=portals, place_frontiers=[0])
    call = ExploreBrain("a").decide(obs, [], {})
    assert call is not None and call.args["buttons"][0] == "down"   # heads to the door back to Pallet


def test_explore_on_a_portal_steps_through_it_to_cross():
    from core.brains import ExploreBrain
    cells = [{"x": 0, "y": 0, "visited": True, "walls": ["up", "left", "right"]},      # interior -> door below
             {"x": 0, "y": 1, "visited": True, "walls": ["left", "right", "down"], "portal": 0}]  # the door
    portals = [[1, [0, 1], "down", 0]]
    obs = _obs_with_map((0, 1), cells, [], area=1, portals=portals, place_frontiers=[0])
    call = ExploreBrain("a").decide(obs, [], {})       # on the door, no local frontier -> use the cross dir
    assert call.args["buttons"] == ["down", "down"]


def test_explore_no_cross_when_no_place_has_a_frontier():
    # If NO place has a frontier anywhere, cross-place must not fire (else it would ping-pong rooms).
    from core.brains import ExploreBrain
    cells = [{"x": 0, "y": 0, "visited": True, "walls": ["up", "down", "left", "right"]}]
    portals = [[1, [0, 1], "down", 0]]
    obs = _obs_with_map((0, 0), cells, [], area=1, portals=portals, place_frontiers=[])
    assert ExploreBrain("a").decide(obs, [], {}) is None         # nothing to explore anywhere -> give up


def test_explore_probes_a_wall_for_an_interactable_when_out_of_frontiers():
    # Affordance discovery: boxed in (no frontier), the default brain gives up (wakes the LLM); with
    # probe_interactables it faces a wall and presses A — an interactable (NPC/object) reads as a wall.
    from core.brains import ExploreBrain
    cells = [{"x": 0, "y": 0, "visited": True, "walls": ["up", "down", "left", "right"]}]
    obs = _obs_with_map((0, 0), cells, [])
    assert ExploreBrain("a").decide(obs, [], {}) is None                       # default: give up
    call = ExploreBrain("a", probe_interactables=True).decide(obs, [], {})
    assert call.tool == "press_sequence" and call.args["buttons"][-1] == "a"   # face a wall + press A
    assert call.args["buttons"][0] in ("up", "down", "left", "right")


def test_explore_probe_prioritizes_a_motion_roi_direction():
    # Guided search: a motion-detected ROI above us -> probe UP first (face the NPC + A), not a random wall.
    from core.brains import ExploreBrain
    cells = [{"x": 0, "y": 0, "visited": True, "walls": ["up", "down", "left", "right"]}]
    obs = _obs_with_map((0, 0), cells, [], rois=[[0, -1]])      # ROI in the cell directly above
    call = ExploreBrain("a", probe_interactables=True).decide(obs, [], {})
    assert call.args["buttons"] == ["up", "a"]


def test_explore_probe_tries_each_wall_once_then_gives_up():
    from core.brains import ExploreBrain
    cells = [{"x": 0, "y": 0, "visited": True, "walls": ["up", "down", "left", "right"]}]
    obs = _obs_with_map((0, 0), cells, [])
    b = ExploreBrain("a", probe_interactables=True)
    tried = set()
    for _ in range(4):
        call = b.decide(obs, [], {})
        assert call is not None and call.args["buttons"][-1] == "a"
        tried.add(call.args["buttons"][0])
    assert tried == {"up", "down", "left", "right"}            # each wall probed exactly once
    assert b.decide(obs, [], {}) is None                       # exhausted -> wake the LLM


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


def _dlg_obs(text, context="dialog"):
    """A dialog/battle_text Observation carrying decoded screen_text (for the seen-states cycle gate).
    No pose -> state_signature is constant per context, so the same text reads as the same state."""
    from core.contracts import Observation
    return Observation(data={"context": context, "screen_text": text}, text="", agent_id="a", t=0.0)


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


def test_hybrid_auto_advances_plain_dialog_for_free():
    """feature #4: with auto-advance on, a PLAIN 'dialog' context presses A for free (no LLM wake)."""
    from core.brains import HybridBrain, _call
    fb = _StubBrain(_call("press_button", {"button": "x"}, "a"), "llm")  # would be obvious if woken
    h = HybridBrain(_StubBrain(None), fb, advance_on_dialog=True)
    call = h.decide(_ctx_obs("dialog"), [], {})
    assert call.tool == "press_button" and call.args["button"] == "a"   # advanced, not the LLM's 'x'
    assert h.woke == 0 and h.advanced == 1 and h.mode == "advance"


def test_hybrid_wakes_on_choice_even_with_auto_advance_on():
    """A choice reads as 'menu' (not 'dialog'), so it WAKES the LLM — never auto-mashed."""
    from core.brains import HybridBrain, _call
    fb = _StubBrain(_call("press_button", {"button": "a"}, "a"), "llm")
    h = HybridBrain(_StubBrain(None), fb, advance_on_dialog=True)
    h.decide(_ctx_obs("menu"), [], {})
    assert h.woke == 1 and h.advanced == 0


def test_hybrid_battle_does_not_mark_confirm_dead_or_fire_surprise():
    """In battle the pose signature is frozen, but pressing A repeatedly (advance text / pick FIGHT /
    choose a move) must NOT be flagged as a dead 'avoid' action, and must NOT raise a spurious
    SURPRISE — battle progress is invisible to the signature, like an auto-advanced dialog. (Contrast
    test_hybrid_surfaces_dead_actions_to_the_fallback, where a frozen OVERWORLD signature does.)"""
    from core.brains import HybridBrain, _call

    class _Capturing:
        def __init__(self, call):
            self._c, self.last_thought, self.avoids, self.surprises = call, "", [], []
        def decide(self, obs, tools, context):
            self.avoids.append(context.get("avoid"))
            self.surprises.append(context.get("surprise_note"))
            return self._c

    fb = _Capturing(_call("press_button", {"button": "a"}, "a"))
    h = HybridBrain(_StubBrain(None), fb, replan_after=2)   # low threshold so a bug would fire fast
    for _ in range(6):
        h.decide(_ctx_obs("battle"), [], {})
    assert h.woke == 6
    assert all("a" not in (av or []) for av in fb.avoids)   # confirm button never marked dead in battle
    assert all(s is None for s in fb.surprises)             # no spurious 'stuck' nudge during battle


def test_hybrid_dialog_wakes_when_auto_advance_disabled():
    """Default (off) preserves the prior behavior: a 'dialog' context wakes the LLM."""
    from core.brains import HybridBrain, _call
    fb = _StubBrain(_call("press_button", {"button": "a"}, "a"), "llm")
    h = HybridBrain(_StubBrain(None), fb)                          # advance_on_dialog defaults False
    h.decide(_ctx_obs("dialog"), [], {})
    assert h.woke == 1 and h.advanced == 0


def test_hybrid_auto_advance_does_not_accrue_a_stuck_streak():
    """Auto-advancing a dialog is progress the signature can't see, so it must reset the no-progress
    streak — otherwise a long dialog would fire a spurious SURPRISE on the next real wake."""
    from core.brains import HybridBrain, _call
    fb = _StubBrain(_call("press_button", {"button": "a"}, "a"), "llm")
    h = HybridBrain(_StubBrain(None), fb, replan_after=2, advance_on_dialog=True)
    for _ in range(5):
        h.decide(_ctx_obs("dialog"), [], {})                      # 5 auto-advances, same signature
    assert h.advanced == 5 and h.woke == 0 and h.disconfirm.fired is False


def test_hybrid_forwards_consec_api_errors_for_the_circuit_breaker():
    """The driver's circuit breaker reads brain.consec_api_errors, but only the wrapped fallback calls
    the model — so HybridBrain must forward the fallback's count (and reset when it heals)."""
    from core.brains import HybridBrain, LLMButtonBrain
    replies = iter(["ModelHTTPError: status_code: 400 credit balance is too low", "MOVE: a"])
    fb = LLMButtonBrain("a", complete_fn=lambda p, i: next(replies))
    h = HybridBrain(_StubBrain(None), fb)            # autopilot stuck -> always wakes the fallback
    h.decide(_ctx_obs("overworld"), [], {})
    assert h.consec_api_errors == 1 and "credit balance" in h.last_api_error
    h.decide(_ctx_obs("overworld"), [], {})
    assert h.consec_api_errors == 0                  # a real reply healed it, forwarded through


def test_hybrid_auto_advances_battle_text_for_free():
    """Battle auto-advance: narration ('battle_text') presses A for free like plain dialog — run #12
    spent ~68 of 73 wakes inside ONE battle, most on advanceable narration it couldn't act on."""
    from core.brains import HybridBrain, _call
    fb = _StubBrain(_call("press_button", {"button": "x"}, "a"), "llm")   # obvious if the LLM were woken
    h = HybridBrain(_StubBrain(None), fb, advance_on_dialog=True)
    call = h.decide(_ctx_obs("battle_text"), [], {})
    assert call.tool == "press_button" and call.args["button"] == "a"     # advanced, not the LLM's 'x'
    assert h.woke == 0 and h.advanced == 1 and h.mode == "advance"


def test_hybrid_wakes_on_battle_menu_even_with_auto_advance_on():
    """The safety contract: the action/move menu stays context=='battle' -> WAKES (a move pick is a
    decision, never auto-mashed). Only narration ('battle_text') auto-advances."""
    from core.brains import HybridBrain, _call
    fb = _StubBrain(_call("press_button", {"button": "a"}, "a"), "llm")
    h = HybridBrain(_StubBrain(None), fb, advance_on_dialog=True)
    h.decide(_ctx_obs("battle"), [], {})
    assert h.woke == 1 and h.advanced == 0


def test_hybrid_battle_text_does_not_accrue_a_stuck_streak():
    """Auto-advancing battle narration is invisible progress, so it resets the no-progress streak —
    no spurious SURPRISE on the next menu wake (mirrors the plain-dialog guarantee)."""
    from core.brains import HybridBrain
    h = HybridBrain(_StubBrain(None), _StubBrain(None, "llm"), replan_after=2, advance_on_dialog=True)
    for _ in range(5):
        h.decide(_ctx_obs("battle_text"), [], {})
    assert h.advanced == 5 and h.woke == 0 and h.disconfirm.fired is False


def test_hybrid_battle_text_wakes_when_auto_advance_disabled():
    """Agnostic default (off): 'battle_text' is just another non-overworld context -> wakes. A world
    that never emits the label is wholly unaffected (no Pokémon-specific behavior leaks into core)."""
    from core.brains import HybridBrain, _call
    fb = _StubBrain(_call("press_button", {"button": "a"}, "a"), "llm")
    h = HybridBrain(_StubBrain(None), fb)                          # advance_on_dialog defaults False
    h.decide(_ctx_obs("battle_text"), [], {})
    assert h.woke == 1 and h.advanced == 0


def test_hybrid_advance_fuse_forces_a_wake():
    """Safety fuse: after _ADVANCE_FUSE consecutive free advances the next one forces ONE LLM wake (so
    a pathological never-terminating advanceable loop can't run forever for free), then resets."""
    from core.brains import HybridBrain, _ADVANCE_FUSE
    h = HybridBrain(_StubBrain(None), _StubBrain(None, "llm"), advance_on_dialog=True)
    for _ in range(_ADVANCE_FUSE):
        h.decide(_ctx_obs("battle_text"), [], {})
    assert h.advanced == _ADVANCE_FUSE and h.woke == 0            # all free so far
    h.decide(_ctx_obs("battle_text"), [], {})                    # the (cap+1)th: fuse trips -> wake
    assert h.woke == 1 and h._consec_advance == 0


# -- seen-states / novelty cycle gate (the Oak "which POKEMON?" trap) ----------

def test_hybrid_cycle_gate_wakes_on_a_revisited_dialog_state():
    """Seen-states gate: auto-advancing back to the SAME dialog text in SEPARATE visits (Oak's
    'which POKEMON?' reopening, a textbox A can't dismiss) is a cycle — after _CYCLE_REVISITS visits,
    stop mashing and WAKE, handing System 2 the bare cycle_note fact (no suggested response)."""
    from core.brains import HybridBrain, _call, _CYCLE_REVISITS

    class _Capturing:
        def __init__(self, call):
            self._c, self.last_thought, self.cycle_notes, self.goto = call, "", [], None
        def decide(self, obs, tools, context):
            self.cycle_notes.append(context.get("cycle_note"))
            return self._c

    fb = _Capturing(_call("press_button", {"button": "a"}, "a"))
    h = HybridBrain(_StubBrain(None), fb, advance_on_dialog=True)
    a, b = _dlg_obs("which POKEMON?"), _dlg_obs("OAK: Now, ASH,")
    seq = [a, b] * (_CYCLE_REVISITS - 1) + [a]      # 'a' visited _CYCLE_REVISITS times (interleaved)
    for o in seq[:-1]:
        h.decide(o, [], {})
    assert h.woke == 0 and h.advanced == len(seq) - 1     # every visit so far auto-advanced for free
    h.decide(seq[-1], [], {})                             # the _CYCLE_REVISITS-th VISIT to 'a' -> trips
    assert h.woke == 1 and h.mode == "llm" and h.advanced == len(seq) - 1
    assert fb.cycle_notes[-1] and "already seen" in fb.cycle_notes[-1]


def test_hybrid_cycle_gate_ignores_a_held_textbox():
    """A settled textbox HELD across consecutive observations (pose frozen, box not yet advanced) is
    ONE visit, never a cycle — the step-300 'Don't go out!' guard. Auto-advance keeps mashing free."""
    from core.brains import HybridBrain
    h = HybridBrain(_StubBrain(None), _StubBrain(None, "llm"), advance_on_dialog=True)
    held = _dlg_obs("Don't go out!")
    for _ in range(6):
        h.decide(held, [], {})                  # same key, consecutive -> stays 1 visit
    assert h.woke == 0 and h.advanced == 6


def test_hybrid_cycle_gate_passes_a_unique_monologue():
    """A normal monologue of DISTINCT lines (Oak's lab intro) is all-novel -> auto-advances fully,
    never trips the cycle gate."""
    from core.brains import HybridBrain
    h = HybridBrain(_StubBrain(None), _StubBrain(None, "llm"), advance_on_dialog=True)
    for i in range(12):
        h.decide(_dlg_obs(f"line {i}"), [], {})
    assert h.woke == 0 and h.advanced == 12


def test_hybrid_cycle_gate_dormant_on_empty_text():
    """Empty screen_text carries no state key -> the cycle gate never engages (only _ADVANCE_FUSE
    backstops). Repeated blank dialog stays free, well past _CYCLE_REVISITS."""
    from core.brains import HybridBrain, _CYCLE_REVISITS
    h = HybridBrain(_StubBrain(None), _StubBrain(None, "llm"), advance_on_dialog=True)
    for _ in range(_CYCLE_REVISITS + 5):
        h.decide(_ctx_obs("dialog"), [], {})        # empty screen_text
    assert h.woke == 0 and h.advanced == _CYCLE_REVISITS + 5


def test_hybrid_cycle_gate_off_when_auto_advance_disabled():
    """With auto-advance off, a 'dialog' already wakes every time; the cycle gate stays dormant — no
    'cycle' wake reason, no cycle_note — even on a repeated state (agnostic default unaffected)."""
    from core.brains import HybridBrain, _call, _CYCLE_REVISITS

    class _Capturing:
        def __init__(self, call):
            self._c, self.last_thought, self.cycle_notes, self.goto = call, "", [], None
        def decide(self, obs, tools, context):
            self.cycle_notes.append(context.get("cycle_note"))
            return self._c

    fb = _Capturing(_call("press_button", {"button": "a"}, "a"))
    h = HybridBrain(_StubBrain(None), fb)                         # advance_on_dialog defaults False
    a = _dlg_obs("which POKEMON?")
    for _ in range(_CYCLE_REVISITS + 2):
        h.decide(a, [], {})
    assert h.woke == _CYCLE_REVISITS + 2 and h.advanced == 0      # every dialog wakes (normal off path)
    assert all(n is None for n in fb.cycle_notes)                # never the cycle channel


# -- general stuck-breaker (no-novelty): the HELD-screen case the cycle gate misses ----------------

class _StuckCapture:
    def __init__(self, call=None):
        self._c, self.last_thought, self.stuck_notes, self.goto = call, "", [], None
    def decide(self, obs, tools, context):
        self.stuck_notes.append(context.get("stuck_note"))
        return self._c


def test_hybrid_stuck_breaker_fires_on_a_held_screen():
    """Persisting on ONE non-overworld screen with no new state — the held name-entry keyboard (run 3:
    44 identical `battle` frames, all 1 'visit' so the cycle gate stays silent) — hands System 2 a
    pure-fact stuck_note once `_STUCK_STALE` decisions pass with nothing new."""
    from core.brains import HybridBrain, _STUCK_STALE
    fb = _StuckCapture()
    h = HybridBrain(_StubBrain(None), fb, advance_on_dialog=True)
    for _ in range(_STUCK_STALE + 1):            # same battle screen, empty text -> held; wakes each time
        h.decide(_ctx_obs("battle"), [], {})
    assert fb.stuck_notes[0] is None             # early frames: not yet stuck
    assert fb.stuck_notes[-1] and "stuck" in fb.stuck_notes[-1].lower()   # after _STUCK_STALE: the fact


def test_hybrid_stuck_breaker_resets_on_new_battle_narration():
    """A real fight keeps producing NOVEL narration, which resets the count — so the stuck-breaker
    never false-fires mid-battle (the property that lets it ignore the mode label)."""
    from core.brains import HybridBrain, _STUCK_STALE
    fb = _StuckCapture()
    h = HybridBrain(_StubBrain(None), fb, advance_on_dialog=True)
    for i in range(_STUCK_STALE * 2):
        h.decide(_ctx_obs("battle"), [], {})                               # action menu (a wake)
        h.decide(_dlg_obs(f"enemy used move {i}", context="battle_text"), [], {})  # novel narration -> reset
    assert all(n is None for n in fb.stuck_notes)        # never trips while the fight is progressing


def test_hybrid_stuck_breaker_resets_in_overworld():
    """Overworld 'stuck' is the autopilot/frontier's job, so the breaker only watches non-overworld
    screens and resets the moment the agent is back in the overworld."""
    from core.brains import HybridBrain, _STUCK_STALE
    h = HybridBrain(_StubBrain(None), _StubBrain(None, "llm"), advance_on_dialog=True)
    for _ in range(_STUCK_STALE + 1):
        h.decide(_ctx_obs("battle"), [], {})
    assert h._stuck is True
    h.decide(_ctx_obs("overworld"), [], {})              # back in the overworld
    assert h._since_novel == 0 and h._stuck is False


def test_hybrid_stuck_breaker_silent_when_cycle_note_covers_it():
    """When the dialog cycle gate already fires (`why=='cycle'`), the stuck channel stays quiet — the
    cycle_note covers that case; no double-noting."""
    from core.brains import HybridBrain, _call, _CYCLE_REVISITS

    class _Both:
        def __init__(self, call):
            self._c, self.last_thought, self.goto = call, "", None
            self.cyc, self.stk = [], []
        def decide(self, obs, tools, context):
            self.cyc.append(context.get("cycle_note")); self.stk.append(context.get("stuck_note"))
            return self._c

    fb = _Both(_call("press_button", {"button": "a"}, "a"))
    h = HybridBrain(_StubBrain(None), fb, advance_on_dialog=True)
    a, b = _dlg_obs("which POKEMON?"), _dlg_obs("OAK: Now, ASH,")
    for o in ([a, b] * (_CYCLE_REVISITS - 1) + [a]):
        h.decide(o, [], {})
    assert fb.cyc[-1] and fb.stk[-1] is None             # cycle fired; stuck channel silent


def test_hybrid_battle_text_when_woken_is_not_marked_dead_or_surprising():
    """Predicate-widen guard (the disconfirm/outcome skip): even when 'battle_text' WAKES (auto-advance
    off), the confirm button is never marked a dead 'avoid' action and no SURPRISE fires — battle
    progress is invisible to the frozen pose signature whether the label is 'battle' or 'battle_text'."""
    from core.brains import HybridBrain, _call

    class _Capturing:
        def __init__(self, call):
            self._c, self.last_thought, self.avoids, self.surprises = call, "", [], []
        def decide(self, obs, tools, context):
            self.avoids.append(context.get("avoid")); self.surprises.append(context.get("surprise_note"))
            return self._c

    fb = _Capturing(_call("press_button", {"button": "a"}, "a"))
    h = HybridBrain(_StubBrain(None), fb, replan_after=2)          # auto-advance off -> battle_text wakes
    for _ in range(6):
        h.decide(_ctx_obs("battle_text"), [], {})
    assert h.woke == 6
    assert all("a" not in (av or []) for av in fb.avoids)         # confirm button never marked dead
    assert all(s is None for s in fb.surprises)                   # no spurious 'stuck' nudge


def _battle_frame():
    """A synthetic battle-shaped frame: white HP boxes (top) + white action/text box (bottom) over a
    dark middle, so detect_mode reads 'battle' (the contrast keeps std above the fade guard)."""
    b = np.full((144, 160, 3), 60, dtype=np.uint8)
    b[:58, :] = 255
    b[96:, :] = 255
    return b


def test_perceive_emits_battle_text_for_narration(monkeypatch):
    """Wiring: in a battle frame the perceiver splits the SETTLED screen via battle_subscreen and
    passes its verdict through as the context the brain routes on."""
    import games.pokemon_red.textbox as tbx
    monkeypatch.setattr(tbx, "battle_subscreen", lambda frame, table: "battle_text")
    per, mem = OverworldPerceiver(), PerceptMemory()
    per._font_loaded, per._font = True, object()                  # pretend the glyph asset is loaded
    s = per.perceive(_battle_frame(), mem, {"last_action": "a"})
    assert s.context == "battle_text"


def test_perceive_emits_battle_for_a_menu(monkeypatch):
    import games.pokemon_red.textbox as tbx
    monkeypatch.setattr(tbx, "battle_subscreen", lambda frame, table: "battle_menu")
    per, mem = OverworldPerceiver(), PerceptMemory()
    per._font_loaded, per._font = True, object()
    s = per.perceive(_battle_frame(), mem, {"last_action": "a"})
    assert s.context == "battle"                                  # a menu -> the wake label


def test_perceive_battle_without_font_defaults_to_battle():
    """No glyph asset -> can't positively identify narration -> default to 'battle' (wake), never a
    silent auto-advance."""
    per, mem = OverworldPerceiver(), PerceptMemory()
    per._font_loaded, per._font = True, None                      # asset absent/unloadable
    s = per.perceive(_battle_frame(), mem, {"last_action": "a"})
    assert s.context == "battle"


def test_detect_mode_unchanged_for_battle_frame():
    """Regression: the battle split lives in perceive(), NOT detect_mode — detect_mode still returns
    'battle' for a battle frame, so _settle_if_battle (which keys on detect_mode) keeps firing."""
    from games.pokemon_red.perceiver import detect_mode
    assert detect_mode(_battle_frame()) == "battle"


def test_hybrid_injects_surprise_nudge_after_repeated_no_progress():
    """Disconfirm detector: once the agent has made no observable progress for `replan_after`
    consecutive decisions (here the autopilot is always stuck -> waking every step with a fixed
    signature), the LLM gets a SURPRISE note in context asking for a lesson, instead of being woken
    to flail silently (run #1 woke the LLM 351x with no such signal)."""
    from core.brains import HybridBrain, _call

    class _Capturing:
        def __init__(self, call): self._c, self.last_thought, self.seen = call, "", []
        def decide(self, obs, tools, context): self.seen.append(context.get("surprise_note")); return self._c

    fb = _Capturing(_call("press_button", {"button": "a"}, "a"))
    h = HybridBrain(_StubBrain(None), fb, replan_after=3)          # autopilot always stuck -> wake every step
    obs = _ctx_obs("overworld")
    for _ in range(3):
        h.decide(obs, [], {})
    assert fb.seen[0] is None and fb.seen[1] is None              # early wakes: no nudge yet
    assert fb.seen[2] and "SURPRISE" in fb.seen[2]                # 3rd no-progress decision -> surprise nudge
    assert "remember what is blocking you" in fb.seen[2]          # channel-neutral wording (S3 beta)


def test_hybrid_surprise_fires_during_dialog_flail():
    """The NEW capability over the old loop-breaker: a mode-wake (dialog/menu) with no situation
    change also grows the no-progress streak, so flailing inside a forced dialog (the run-#2 wall)
    eventually raises a SURPRISE — even though the autopilot never reports 'stuck' here."""
    from core.brains import HybridBrain, _call

    class _Capturing:
        def __init__(self, call): self._c, self.last_thought, self.seen = call, "", []
        def decide(self, obs, tools, context): self.seen.append(context.get("surprise_note")); return self._c

    fb = _Capturing(_call("press_button", {"button": "a"}, "a"))
    ap = _StubBrain(_call("press_button", {"button": "up"}, "a"))  # autopilot WOULD act, but mode wakes
    h = HybridBrain(ap, fb, replan_after=2)
    for _ in range(2):
        h.decide(_ctx_obs("dialog"), [], {})       # stuck in dialog: same signature each step
    assert h.woke == 2 and fb.seen[0] is None
    assert fb.seen[1] and "SURPRISE" in fb.seen[1]


def test_hybrid_surprise_to_lesson_closes_the_loop():
    """Steps 1+2 together: a SURPRISE nudge prompts the LLM for a LESSON, which the harness captures
    into its per-run buffer — the 'act -> observe -> learn' loop closing with no aria/persistence."""
    from core.brains import HybridBrain, LLMButtonBrain
    from core.contracts import Observation

    def complete(prompt, image):
        return "MOVE: a\nLESSON: this door is locked, find another way" if "SURPRISE" in prompt else "MOVE: a"

    fb = LLMButtonBrain("a", use_vision=False, complete_fn=complete)
    h = HybridBrain(_StubBrain(None), fb, replan_after=2)          # always stuck -> wake every step
    obs = Observation(data={"context": "overworld"}, text="stuck here", agent_id="a", t=0.0)
    for _ in range(2):
        h.decide(obs, [], {})
    assert fb.lessons == ["this door is locked, find another way"]  # surprise -> lesson -> buffered


def test_hybrid_surprise_resets_on_real_progress():
    """A genuine progress step (the observed signature changes) resets the no-progress streak, so a
    short stuck spell afterwards does NOT fire a premature SURPRISE (no false alarms while exploring)."""
    from core.brains import HybridBrain, _call

    class _Capturing:
        def __init__(self, call): self._c, self.last_thought, self.seen = call, "", []
        def decide(self, obs, tools, context): self.seen.append(context.get("surprise_note")); return self._c

    fb = _Capturing(_call("press_button", {"button": "a"}, "a"))
    h = HybridBrain(_StubBrain(None), fb, replan_after=2)          # always stuck -> wake every step
    for p in [(0, 0), (0, 1), (0, 1), (0, 1)]:                     # progress at step 2, then frozen
        h.decide(_pose_obs(p), [], {})
    assert fb.seen[0] is None and fb.seen[1] is None and fb.seen[2] is None  # step-2 progress reset the streak
    assert fb.seen[3] and "SURPRISE" in fb.seen[3]                 # fires only after 2 no-progress steps post-reset


def test_hybrid_streak_survives_free_steps_and_fires_only_at_wake():
    """The no-progress streak accumulates across FREE autopilot steps (no wake), and the SURPRISE is
    injected ONLY at an actual wake — never into the free autopilot's own context."""
    from core.brains import HybridBrain, _call

    class _ActsThenStuck:                                          # acts (free) `acts` times, then stuck
        def __init__(self, acts, call):
            self._left, self._c, self.last_thought, self.seen = acts, call, "", []
        def decide(self, obs, tools, context):
            self.seen.append(context.get("surprise_note"))
            if self._left > 0:
                self._left -= 1
                return self._c
            return None

    class _Capturing:
        def __init__(self, call): self._c, self.last_thought, self.seen = call, "", []
        def decide(self, obs, tools, context): self.seen.append(context.get("surprise_note")); return self._c

    ap = _ActsThenStuck(2, _call("press_sequence", {"buttons": ["up", "up"]}, "a"))
    fb = _Capturing(_call("press_button", {"button": "a"}, "a"))
    h = HybridBrain(ap, fb, replan_after=2)
    for _ in range(3):
        h.decide(_pose_obs((0, 0)), [], {})                       # frozen pose: no progress on any step
    assert all(s is None for s in ap.seen)                        # free autopilot never sees a surprise note
    assert h.woke == 1 and fb.seen and "SURPRISE" in fb.seen[-1]  # streak survived 2 free steps -> fired at the wake


def test_hybrid_accumulates_dialog_transcript_and_injects_at_next_wake():
    """Auto-advanced dialog text is captured into a per-run transcript (deduped) and handed to the LLM
    at the next wake (the 'text since your last decision' the user asked for), then cleared."""
    from core.brains import HybridBrain, _call
    from core.contracts import Observation

    class _Capturing:
        def __init__(self, call): self._c, self.last_thought, self.seen = call, "", []
        def decide(self, obs, tools, context): self.seen.append(context.get("transcript")); return self._c

    fb = _Capturing(_call("press_button", {"button": "a"}, "a"))
    h = HybridBrain(_StubBrain(None), fb, advance_on_dialog=True)
    dlg = lambda txt: Observation(data={"context": "dialog", "screen_text": txt}, text="", agent_id="a", t=0.0)
    menu = Observation(data={"context": "menu"}, text="", agent_id="a", t=0.0)
    h.decide(dlg("HELLO"), [], {})        # auto-advance -> capture
    h.decide(dlg("HELLO"), [], {})        # same text -> not duplicated
    h.decide(dlg("WORLD"), [], {})        # capture
    assert h.advanced == 3 and h.woke == 0
    h.decide(menu, [], {})                # a choice wakes the LLM -> transcript injected + cleared
    assert h.woke == 1 and fb.seen[-1] == "HELLO / WORLD" and h.transcript == []


def test_hybrid_transcript_caps_to_most_recent():
    from core.brains import HybridBrain, _TRANSCRIPT_CAP, _call
    from core.contracts import Observation
    h = HybridBrain(_StubBrain(None), _StubBrain(_call("press_button", {"button": "a"}, "a")),
                    advance_on_dialog=True)
    for i in range(_TRANSCRIPT_CAP + 5):
        obs = Observation(data={"context": "dialog", "screen_text": f"line{i}"}, text="", agent_id="a", t=0.0)
        h.decide(obs, [], {})
    assert len(h.transcript) == _TRANSCRIPT_CAP                      # capped
    assert h.transcript[-1] == f"line{_TRANSCRIPT_CAP + 4}"          # most-recent kept


# -- outcome loop (feature #1: learn from no-effect actions) ------------------

def test_outcome_memory_marks_repeated_no_effect_and_resets_on_effect():
    from core.outcome import OutcomeMemory
    om = OutcomeMemory(dead_after=2)
    sig = ("overworld", 0, (0, 0))
    om.record(sig, "a", effective=False); assert not om.is_dead(sig, "a")
    om.record(sig, "a", effective=False); assert om.is_dead(sig, "a") and "a" in om.dead_actions(sig)
    om.record(sig, "a", effective=True);  assert not om.is_dead(sig, "a")  # any effect resets the streak


def test_state_signature_ignores_screen_text():
    # on-screen text must NOT be part of the 'situation' key — else every changing dialog frame would
    # look like a new situation / churn the outcome+disconfirm memories.
    from core.outcome import state_signature
    base = {"context": "dialog", "pose": {"value": [1, 1], "area": 0}}
    assert state_signature({**base, "screen_text": "HELLO"}) == state_signature({**base, "screen_text": "WORLD"})


def test_perceiver_read_text_rejects_glyph_poor_region():
    # the quality guard: a region with <3 recognizable chars (e.g. a non-textbox screen) -> "" not junk.
    per = OverworldPerceiver()
    f = np.full((144, 160, 3), 255, dtype=np.uint8)      # white (textbox bg)
    f[112:120, 8:16] = 20                                 # one solid-dark cell -> '?' (no real glyph)
    f[112:120, 16:24] = 20                                # another -> '?'
    assert per._read_text(f) == ""


def test_perceive_overworld_leaves_screen_text_empty():
    per = OverworldPerceiver()
    mem = PerceptMemory()
    per.perceive(_frame(0), mem, {"last_action": None})
    s = per.perceive(_frame(60), mem, {"last_action": "down+down"})   # plain dark scene -> overworld
    assert s.context == "overworld" and s.screen_text == ""


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


# -- runner: optional progress-watchdog halt hook (cost guardrail) ------------

def test_run_episode_should_continue_halts_early():
    """The runner's optional should_continue(step) predicate stops an episode before max_steps — the
    hook a driver's progress watchdog uses (the guardrail play_pokemon.py lacked in live-run #1)."""
    from core.brains import _call
    from core.contracts import Observation
    from core.runner import run_episode

    class _P:
        def observe(self, aid): return Observation(data={}, text="", agent_id=aid, t=0.0)
        def tools(self, aid): return []
        def drain_events(self): return []

    class _G:
        def execute(self, call): return type("R", (), {"data": {}})()

    class _B:
        def decide(self, obs, tools, ctx): return _call("press_button", {"button": "a"}, "a")

    summary = run_episode(_G(), _P(), _B(), "a", max_steps=10,
                          should_continue=lambda step: step < 3)
    assert summary["steps"] == 3                    # halted after steps 0,1,2 (step 3 fails the predicate)
