"""Architectural fitness function — THE NON-LEAKING-ORACLE WALL (RAM never reaches the agent).

ADR-001 / CLAUDE.md: the perceiver sees only pixels; RAM goes to oracle.jsonl for scoring/nav aids, NEVER
into the agent's Observation. This fails if any oracle/RAM-derived field crosses the seam into what the agent
sees. A red here means a leak was introduced — plug the leak; do NOT relax this test to silence it.
"""
from __future__ import annotations

import pytest

from core.perception import StubPerceiver, SymbolicState
from games.pokemon_red import memory_map as mm
from games.pokemon_red import PokemonRedPlugin
from tests.test_pokemon_red import FakeEmulator

# The role-named keys that ARE allowed to cross the seam (the SymbolicState contract). Derived from the
# contract itself so it tracks legitimate changes; widening it is a deliberate, reviewed act.
ALLOWED_SEAM_KEYS = set(SymbolicState(confidence=0.0, context="overworld").to_dict())

# Substrings that betray an oracle/RAM-derived field having leaked into agent-facing data.
FORBIDDEN_KEY_SUBSTRINGS = ("ram", "wram", "oracle", "map_id", "true_", "gt_", "ground_truth", "watch")

# The lean PokemonRedPlugin's `watch` map (mirrors world_mcp.py's GAMES["pokemon_red"]["watch"]) — RAM
# goes to oracle.jsonl only, never Observation.data (the structural no-leak guarantee this test proves).
WATCH = {"x": mm.ADDR_X, "y": mm.ADDR_Y, "map": mm.ADDR_MAP_ID}

# Distinctive RAM values we plant; none should surface in what the agent sees.
RAM_SENTINELS = {"map": 222, "x": 201, "y": 233}


def _all_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _all_keys(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _all_keys(v)


def _all_values(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _all_values(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _all_values(v)
    else:
        yield obj


@pytest.fixture
def agent_obs(tmp_path):
    """What the agent actually sees, with distinctive RAM sentinels planted in the emulator. The lean
    PerceptionPlugin structurally can't leak RAM into Observation.data — even watched RAM goes only to
    the oracle log (a stronger guarantee than the archived heavy plugin's read_state-based observe)."""
    emu = FakeEmulator()
    emu.mem[mm.ADDR_MAP_ID] = RAM_SENTINELS["map"]
    emu.mem[mm.ADDR_X] = RAM_SENTINELS["x"]
    emu.mem[mm.ADDR_Y] = RAM_SENTINELS["y"]
    plugin = PokemonRedPlugin(emulator=emu, out_dir=str(tmp_path), perceiver=StubPerceiver(), watch=WATCH)
    return plugin.observe("a").data


def test_only_role_named_keys_cross_the_seam(agent_obs):
    # The role-named SymbolicState keys are present...
    assert ALLOWED_SEAM_KEYS <= set(agent_obs), "the seam dropped a role-named field"
    # ...and no obvious RAM keys are at the top level.
    for k in ("x", "y", "map_id", "ram", "watch"):
        assert k not in agent_obs, f"RAM key '{k}' crossed the seam"


def test_no_oracle_field_names_anywhere(agent_obs):
    leaked = sorted(
        k for k in {kk.lower() for kk in _all_keys(agent_obs)}
        if any(s in k for s in FORBIDDEN_KEY_SUBSTRINGS)
    )
    assert not leaked, f"oracle/RAM-named field reached the agent: {leaked}"


def test_ram_sentinel_values_do_not_appear(agent_obs):
    ints = {v for v in _all_values(agent_obs) if isinstance(v, int) and not isinstance(v, bool)}
    leaked = set(RAM_SENTINELS.values()) & ints
    assert not leaked, f"a RAM sentinel value leaked into the agent's Observation: {leaked}"
