"""GauntletPlugin tests — extends the NON-LEAKING-ORACLE WALL (RAM never reaches the agent) to the
second world, and checks the perception-only contract. Mirrors tests/test_no_ram_leak.py; reuses the
RAM-backed FakeEmulator (a test helper, not a game sibling, so importing it is allowed).
"""
from __future__ import annotations

import numpy as np
import pytest

from core.perception import PerceptMemory, StubPerceiver, SymbolicState
from games.gauntlet import GauntletPlugin
from games.gauntlet.perceiver import GauntletPerceiver, _WALL_CONFIRM
from tests.test_pokemon_red import FakeEmulator

ALLOWED_SEAM_KEYS = set(SymbolicState(confidence=0.0, context="gameplay").to_dict())
FORBIDDEN_KEY_SUBSTRINGS = ("ram", "wram", "oracle", "true_", "gt_", "ground_truth", "watch")
WATCH = {"x": 0xC286, "y": 0xC2C6}            # the finder-found pose registers
RAM_SENTINELS = {"x": 201, "y": 233}          # planted at WATCH addrs; must never reach the agent


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
    plugin = GauntletPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=StubPerceiver(), watch=WATCH)
    return plugin.observe("a").data


def test_requires_a_perceiver():
    with pytest.raises(ValueError):
        GauntletPlugin(emulator=FakeEmulator(), perceiver=None)


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
    plugin = GauntletPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=GauntletPerceiver())
    data = plugin.observe("a").data
    assert data["context"] in ("gameplay", "static", "menu", "unknown")
    assert data["pose"]["value"] == [0, 0]           # dead-reckoning starts at the origin
    assert data["spatial_memory"]["kind"] == "occupancy-grid"


# -- the novel odometry logic (the dead-zone wall-confirmation), driven by synthetic frames so it runs in
# CI (the headline drift/coverage numbers are validated off-repo against gitignored corpora). --

def _shifted_canvas():
    """A textured canvas + two 144x160 windows offset 16px horizontally: a detectable camera scroll."""
    c = np.random.RandomState(7).randint(0, 255, (144, 176, 3), dtype="uint8")
    return c[:, :160], c[:, 16:176]     # (still, scrolled)


def test_camera_scroll_is_a_move_and_steps_the_pose_one_cell():
    p, mem = GauntletPerceiver(), PerceptMemory()
    still, scrolled = _shifted_canvas()
    p.perceive(still, mem, {"last_action": "right"})        # bootstrap (prev frame)
    s = p.perceive(scrolled, mem, {"last_action": "right"})  # a real shift -> moved
    assert s.last_action["outcome"] == "moved"
    x, y = s.pose["value"]
    assert abs(x) + abs(y) == 1                              # advanced exactly one cell


def test_no_scroll_seals_a_wall_only_after_persistent_confirmation():
    p, mem = GauntletPerceiver(), PerceptMemory()
    still, _ = _shifted_canvas()
    p.perceive(still, mem, {"last_action": "up"})           # bootstrap
    for _ in range(_WALL_CONFIRM - 1):                      # identical frames => no scroll, but TENTATIVE
        s = p.perceive(still, mem, {"last_action": "up"})
        assert s.last_action["outcome"] == "unknown"
        assert "up" not in s.spatial_memory["walls_here"], "sealed a phantom wall before confirmation"
    s = p.perceive(still, mem, {"last_action": "up"})       # the confirming attempt seals it
    assert s.last_action["outcome"] == "blocked"
    assert "up" in s.spatial_memory["walls_here"]


def test_a_confirmed_move_clears_a_pending_no_scroll_count():
    p, mem = GauntletPerceiver(), PerceptMemory()
    still, scrolled = _shifted_canvas()
    p.perceive(still, mem, {"last_action": "right"})        # bootstrap
    for _ in range(_WALL_CONFIRM - 1):                      # build a tentative count (no wall yet)
        p.perceive(still, mem, {"last_action": "right"})
    assert mem.data["blocked_attempts"].get(((0, 0), "right")) == _WALL_CONFIRM - 1
    s = p.perceive(scrolled, mem, {"last_action": "right"})  # a real move clears the pending count
    assert s.last_action["outcome"] == "moved"
    assert ((0, 0), "right") not in mem.data["blocked_attempts"]
