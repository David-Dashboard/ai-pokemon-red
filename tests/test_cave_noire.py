"""Cave Noire tests — the fixed-camera FOREGROUND-motion perceiver + the NON-LEAKING-ORACLE WALL.

Two halves: (1) the novel perceiver logic — a changed frame under a command => a move (pose steps in the
commanded direction); repeated identical frames => no foreground => a wall after _WALL_CONFIRM attempts.
(2) the no-leak wall (RAM never reaches the agent) extended to the third world, mirroring
tests/test_gauntlet.py + tests/test_no_ram_leak.py. numpy only, no ROM.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.perception import PerceptMemory, StubPerceiver, SymbolicState
from games.cave_noire import CaveNoirePlugin
from games.cave_noire.perceiver import CaveNoirePerceiver, _WALL_CONFIRM
from tests.test_pokemon_red import FakeEmulator

ALLOWED_SEAM_KEYS = set(SymbolicState(confidence=0.0, context="gameplay").to_dict())
FORBIDDEN_KEY_SUBSTRINGS = ("ram", "wram", "oracle", "true_", "gt_", "ground_truth", "watch")
WATCH = {"x": 0xC504, "y": 0xC503}            # the finder-found pose registers
RAM_SENTINELS = {"x": 211, "y": 197}          # planted at WATCH addrs; must never reach the agent


def _rng_frame(seed):
    return np.random.RandomState(seed).randint(0, 255, (144, 160, 3), dtype="uint8")


# -- the novel odometry logic (the foreground-motion move signal) --

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


# -- the non-leaking-oracle wall (RAM never reaches the agent), extended to the third world --

def _all(obj, keys):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield (str(k) if keys else None)
            yield from _all(v, keys)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _all(v, keys)
    elif not keys:
        yield obj


@pytest.fixture
def agent_obs(tmp_path):
    emu = FakeEmulator()
    emu.mem[WATCH["x"]] = RAM_SENTINELS["x"]
    emu.mem[WATCH["y"]] = RAM_SENTINELS["y"]
    plugin = CaveNoirePlugin(emulator=emu, out_dir=str(tmp_path), perceiver=StubPerceiver(), watch=WATCH)
    return plugin.observe("a").data


def test_requires_a_perceiver():
    with pytest.raises(ValueError):
        CaveNoirePlugin(emulator=FakeEmulator(), perceiver=None)


def test_only_role_named_keys_cross_the_seam(agent_obs):
    assert ALLOWED_SEAM_KEYS <= set(agent_obs), "the seam dropped a role-named field"
    for k in ("x", "y", "watch", "ram"):
        assert k not in agent_obs, f"RAM key '{k}' crossed the seam"


def test_no_oracle_or_ram_names_anywhere(agent_obs):
    leaked = sorted(k for k in {kk.lower() for kk in _all(agent_obs, True) if kk}
                    if any(s in k for s in FORBIDDEN_KEY_SUBSTRINGS))
    assert not leaked, f"oracle/RAM-named field reached the agent: {leaked}"


def test_ram_sentinel_values_do_not_appear(agent_obs):
    ints = {v for v in _all(agent_obs, False) if isinstance(v, int) and not isinstance(v, bool)}
    leaked = set(RAM_SENTINELS.values()) & ints
    assert not leaked, f"a RAM sentinel value leaked into the agent's Observation: {leaked}"


def test_perceiver_emits_a_well_formed_pose(tmp_path):
    emu = FakeEmulator()
    emu._screen = np.zeros((144, 160, 4), dtype="uint8")
    plugin = CaveNoirePlugin(emulator=emu, out_dir=str(tmp_path), perceiver=CaveNoirePerceiver())
    data = plugin.observe("a").data
    assert data["context"] in ("gameplay", "static", "menu", "unknown")
    assert data["pose"]["value"] == [0, 0]           # dead-reckoning starts at the origin
    assert data["spatial_memory"]["kind"] == "occupancy-grid"
