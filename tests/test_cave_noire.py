"""CaveNoirePerceiver tests — the fixed-camera, FOREGROUND-motion move signal (numpy only, no ROM).

Cave Noire's camera never scrolls, so the move signal is the camera-compensated RESIDUAL, not best_shift's
shift. These lock the novel logic: a changed frame under a command => a move (pose steps in the commanded
direction); repeated identical frames => no foreground => a wall after _WALL_CONFIRM persistent attempts.
"""
from __future__ import annotations

import numpy as np

from core.perception import PerceptMemory
from games.cave_noire.perceiver import CaveNoirePerceiver, _WALL_CONFIRM


def _rng_frame(seed):
    return np.random.RandomState(seed).randint(0, 255, (144, 160, 3), dtype="uint8")


def test_emits_well_formed_pose():
    p = CaveNoirePerceiver()
    s = p.perceive(np.zeros((144, 160, 3), "uint8"), PerceptMemory(), {"last_action": None})
    assert s.pose["value"] == [0, 0]                      # dead-reckoning starts at the origin
    assert s.spatial_memory["kind"] == "occupancy-grid"
    assert s.context in ("gameplay", "static", "menu", "unknown")
    assert s.screen_text == ""


def test_foreground_motion_steps_the_pose():
    p, mem = CaveNoirePerceiver(), PerceptMemory()
    p.perceive(_rng_frame(1), mem, {"last_action": "right"})    # bootstrap (prev frame)
    s = p.perceive(_rng_frame(2), mem, {"last_action": "right"})  # a DIFFERENT frame -> foreground move
    assert s.last_action["outcome"] == "moved"
    assert s.pose["value"] == [1, 0]                       # stepped in the COMMANDED direction
    assert s.spatial_memory["ego_motion"] == "east"


def test_no_foreground_seals_a_wall_only_after_confirmation():
    p, mem = CaveNoirePerceiver(), PerceptMemory()
    still = _rng_frame(3)
    p.perceive(still, mem, {"last_action": "up"})          # bootstrap
    # identical frames => zero residual => no move; the wall must NOT seal before _WALL_CONFIRM attempts.
    for i in range(_WALL_CONFIRM - 1):
        s = p.perceive(still, mem, {"last_action": "up"})
        assert "up" not in s.spatial_memory["walls_here"], "sealed a phantom wall too early"
    s = p.perceive(still, mem, {"last_action": "up"})      # the confirming attempt
    assert "up" in s.spatial_memory["walls_here"]
