"""GridPerceiver tests — the shared occupancy-grid base + both MoveSignal strategies (numpy only, no ROM).

Locks the seam between the base (grid/walls/frontiers/SymbolicState) and the per-world move signal:
the camera-scroll strategy (a real shift => moved) and the foreground strategy (a changed frame =>
moved), and the persistent-wall confirmation the base owns for both.
"""
from __future__ import annotations

import numpy as np

from core.grid_perceiver import (CameraScrollSignal, ForegroundSignal, GridPerceiver, WALL_CONFIRM)
from core.perception import PerceptMemory


def _rng_frame(seed):
    return np.random.RandomState(seed).randint(0, 255, (144, 160, 3), dtype="uint8")


def _shifted_canvas():
    """A textured canvas + two 144x160 windows offset 16px horizontally: a detectable camera scroll."""
    c = np.random.RandomState(7).randint(0, 255, (144, 176, 3), dtype="uint8")
    return c[:, :160], c[:, 16:176]     # (still, scrolled)


def test_emits_well_formed_pose():
    p = GridPerceiver(CameraScrollSignal())
    s = p.perceive(np.zeros((144, 160, 3), "uint8"), PerceptMemory(), {"last_action": None})
    assert s.pose["value"] == [0, 0]                      # dead-reckoning starts at the origin
    assert s.spatial_memory["kind"] == "occupancy-grid"
    assert s.context in ("gameplay", "static", "menu", "unknown")
    assert s.screen_text == ""


def test_camera_scroll_steps_the_pose_one_cell():
    p, mem = GridPerceiver(CameraScrollSignal()), PerceptMemory()
    still, scrolled = _shifted_canvas()
    p.perceive(still, mem, {"last_action": "right"})        # bootstrap (prev frame)
    s = p.perceive(scrolled, mem, {"last_action": "right"})  # a real shift -> moved
    assert s.last_action["outcome"] == "moved"
    x, y = s.pose["value"]
    assert abs(x) + abs(y) == 1                             # advanced exactly one cell


def test_no_scroll_seals_a_wall_only_after_confirmation():
    p, mem = GridPerceiver(CameraScrollSignal()), PerceptMemory()
    still, _ = _shifted_canvas()
    p.perceive(still, mem, {"last_action": "up"})           # bootstrap
    for _ in range(WALL_CONFIRM - 1):                       # identical frames => no scroll, but TENTATIVE
        s = p.perceive(still, mem, {"last_action": "up"})
        assert s.last_action["outcome"] == "unknown"
        assert "up" not in s.spatial_memory["walls_here"], "sealed a phantom wall before confirmation"
    s = p.perceive(still, mem, {"last_action": "up"})       # the confirming attempt seals it
    assert s.last_action["outcome"] == "blocked"
    assert "up" in s.spatial_memory["walls_here"]


def test_foreground_motion_steps_the_pose():
    p, mem = GridPerceiver(ForegroundSignal()), PerceptMemory()
    p.perceive(_rng_frame(1), mem, {"last_action": "right"})    # bootstrap (prev frame)
    s = p.perceive(_rng_frame(2), mem, {"last_action": "right"})  # a DIFFERENT frame -> foreground move
    assert s.last_action["outcome"] == "moved"
    assert s.pose["value"] == [1, 0]                       # stepped in the COMMANDED direction
    assert s.spatial_memory["ego_motion"] == "east"


def test_no_foreground_seals_a_wall_only_after_confirmation():
    p, mem = GridPerceiver(ForegroundSignal()), PerceptMemory()
    still = _rng_frame(3)
    p.perceive(still, mem, {"last_action": "up"})           # bootstrap
    for _ in range(WALL_CONFIRM - 1):                       # identical frames => zero residual => no move
        s = p.perceive(still, mem, {"last_action": "up"})
        assert "up" not in s.spatial_memory["walls_here"], "sealed a phantom wall too early"
    s = p.perceive(still, mem, {"last_action": "up"})       # the confirming attempt
    assert "up" in s.spatial_memory["walls_here"]


# -- the MoveSignal strategies as units (pin the thresholds + the combined branch the perceiver tests
# can't easily drive). The grid-max numbers come from eval/probe_spatial_move (real med 91 / stuck med 20). --

def test_foreground_grid_threshold_brackets_the_probe_medians():
    sig = ForegroundSignal(move_px=2.0, fg_grid=58.0)   # 58 sits between STUCK~20 and MOVED~91 (grid-max)
    no_cam = dict(commanded_dir="up", ego_token="none", sdx=0, sdy=0, best_diff=0.0)
    assert sig(grid_max=91.0, **no_cam).moved is True, "a MOVED-magnitude cell spike must step"
    assert sig(grid_max=20.0, **no_cam).moved is False, "a STUCK-magnitude cell spike must not step"
    assert sig(grid_max=58.0, **no_cam).moved is True, "the threshold itself is inclusive"
    assert sig(grid_max=57.9, **no_cam).moved is False


def test_foreground_combined_scroll_steps_by_ego_not_command():
    # When the camera ALSO scrolled (follow-ish frame), the ego axis wins over the commanded button.
    sig = ForegroundSignal(move_px=2.0, fg_grid=58.0)
    r = sig(commanded_dir="up", ego_token="east", sdx=16, sdy=0, best_diff=0.0, grid_max=0.0)
    assert r.moved is True
    assert r.step_dir == "right", "scrolled => step by the ego (scrolled) axis, not the commanded 'up'"
    assert r.ego_motion == "east"


def test_camera_scroll_below_threshold_does_not_move_but_surfaces_ego():
    sig = CameraScrollSignal(move_px=2.0)
    r = sig(commanded_dir="up", ego_token="none", sdx=1, sdy=0, best_diff=4.0)  # sub-threshold drift
    assert r.moved is False and r.step_dir is None
    assert r.ego_motion == "none"   # the raw ego token is surfaced regardless of the move decision
