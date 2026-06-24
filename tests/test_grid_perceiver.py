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
