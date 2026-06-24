"""GauntletPlugin tests — extends the NON-LEAKING-ORACLE WALL (RAM never reaches the agent) to the
second world, and checks the perception-only contract. Mirrors tests/test_no_ram_leak.py; reuses the
RAM-backed FakeEmulator (a test helper, not a game sibling, so importing it is allowed).
"""
from __future__ import annotations

import numpy as np
import pytest

from core.perception import StubPerceiver, SymbolicState
from games.gauntlet.plugin import GauntletPlugin
from games.gauntlet.perceiver import GauntletPerceiver
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


def test_perceiver_emits_a_well_formed_pose():
    emu = FakeEmulator()
    emu._screen = np.zeros((144, 160, 4), dtype="uint8")
    plugin = GauntletPlugin(emulator=emu, out_dir="runs/_t", perceiver=GauntletPerceiver())
    data = plugin.observe("a").data
    assert data["context"] in ("gameplay", "static", "menu", "unknown")
    assert data["pose"]["value"] == [0, 0]           # dead-reckoning starts at the origin
    assert data["spatial_memory"]["kind"] == "occupancy-grid"
