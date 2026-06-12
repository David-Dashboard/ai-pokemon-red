"""Pokémon Red plugin tests — run with NO ROM and NO PyBoy.

The emulator is dependency-injected, so a tiny in-memory FakeEmulator exercises
every code path: state parsing, error-as-observation, reward shaping, the
gateway's permission veto, and a full runner episode. (A real-ROM integration
test is intentionally omitted — it needs a copyrighted ROM the project never
ships.)
"""

from __future__ import annotations

import pytest

from core.brains import ScriptedBrain
from core.gateway import Gateway
from core.permissions import Allowlist, POKEMON_SANDBOX
from core.runner import run_episode
from games.pokemon_red import memory_map as mm
from games.pokemon_red.plugin import PokemonRedPlugin


class FakeEmulator:
    """RAM-backed stand-in for PyBoy. Tests poke `mem` to simulate the game."""

    def __init__(self) -> None:
        self.mem: dict[int, int] = {}
        self._frame = 0

    def press(self, button, hold_frames=8, settle_frames=16):
        self._frame += hold_frames + settle_frames

    def tick(self, frames):
        self._frame += frames

    def read(self, addr):
        return self.mem.get(addr, 0)

    def save_screen(self, path):
        with open(path, "wb") as f:
            f.write(b"")  # empty PNG placeholder is enough for the path contract

    @property
    def frame(self):
        return self._frame

    def close(self):
        pass


def _seed_party_mon1(emu: FakeEmulator):
    emu.mem[mm.ADDR_PARTY_COUNT] = 1
    base = mm.ADDR_PARTY_MON1
    emu.mem[base + mm.OFF_SPECIES] = 153
    emu.mem[base + mm.OFF_CUR_HP] = 0x00
    emu.mem[base + mm.OFF_CUR_HP + 1] = 0x14  # 20
    emu.mem[base + mm.OFF_LEVEL] = 12
    emu.mem[base + mm.OFF_MAX_HP] = 0x00
    emu.mem[base + mm.OFF_MAX_HP + 1] = 0x18  # 24


# -- memory map ---------------------------------------------------------------

def test_bcd_and_popcount():
    assert mm.bcd3_to_int(0x00, 0x30, 0x00) == 3000
    assert mm.bcd3_to_int(0x01, 0x23, 0x45) == 12345
    assert mm.popcount(0b00000011) == 2
    assert mm.popcount(0xFF) == 8


def test_read_state_parses_party_and_fields():
    emu = FakeEmulator()
    _seed_party_mon1(emu)
    emu.mem[mm.ADDR_MAP_ID] = 12
    emu.mem[mm.ADDR_X] = 4
    emu.mem[mm.ADDR_Y] = 7
    emu.mem[mm.ADDR_BADGES] = 0b00000001  # 1 badge
    emu.mem[mm.ADDR_MONEY] = 0x00
    emu.mem[mm.ADDR_MONEY + 1] = 0x30
    emu.mem[mm.ADDR_MONEY + 2] = 0x00

    s = mm.read_state(emu.read)
    assert s["map_id"] == 12 and s["x"] == 4 and s["y"] == 7
    assert s["badges"] == 1 and s["money"] == 3000
    assert s["party_count"] == 1
    assert s["party"][0] == {"species_id": 153, "level": 12, "hp": 20,
                             "max_hp": 24, "status": 0}
    assert s["party_level_sum"] == 12 and s["party_hp_sum"] == 20


# -- plugin: errors are observations -----------------------------------------

def _plugin(tmp_path):
    emu = FakeEmulator()
    p = PokemonRedPlugin(emulator=emu, out_dir=str(tmp_path))
    return p, emu


def test_invalid_button_is_observation_not_exception(tmp_path):
    p, _ = _plugin(tmp_path)
    res = p.handle(_tc("press_button", {"button": "z"}))
    assert res.ok is False
    assert "invalid button" in res.error
    assert set(res.data["valid_buttons"]) >= {"a", "b", "up", "down"}


def test_unknown_tool_is_observation(tmp_path):
    p, _ = _plugin(tmp_path)
    res = p.handle(_tc("teleport", {}))
    assert res.ok is False and "unknown tool" in res.error


def test_valid_press_returns_ok_and_emits_event(tmp_path):
    p, _ = _plugin(tmp_path)
    res = p.handle(_tc("press_button", {"button": "a"}))
    assert res.ok is True and res.data["action"] == "a"
    types = [e.type for e in p.drain_events()]
    assert "tool_called" in types


def test_observe_writes_screen_path_and_text(tmp_path):
    p, emu = _plugin(tmp_path)
    _seed_party_mon1(emu)
    obs = p.observe("agent-x")
    assert obs.data["screen_path"].endswith(".png")
    assert "Pokémon Red" in obs.text
    assert obs.data["party"][0]["level"] == 12


# -- reward shaping -----------------------------------------------------------

def test_badge_gain_rewards_and_emits_badge_event(tmp_path):
    p, emu = _plugin(tmp_path)  # baseline: 0 badges
    emu.mem[mm.ADDR_BADGES] = 0b00000001  # earn one
    res = p.handle(_tc("press_button", {"button": "a"}))
    assert res.data["reward"] == pytest.approx(10.0)
    assert "badge_earned" in [e.type for e in p.drain_events()]


def test_new_map_gives_exploration_reward(tmp_path):
    p, emu = _plugin(tmp_path)  # baseline map 0
    emu.mem[mm.ADDR_MAP_ID] = 5
    res = p.handle(_tc("press_button", {"button": "up"}))
    assert res.data["reward"] == pytest.approx(1.0)


# -- gateway ------------------------------------------------------------------

def test_gateway_rejects_unknown_tool(tmp_path):
    p, _ = _plugin(tmp_path)
    gw = Gateway(p, POKEMON_SANDBOX)
    res = gw.execute(_tc("fly_away", {}))
    assert res.ok is False and "unknown tool" in res.error


def test_gateway_permission_denies_out_of_sandbox(tmp_path):
    p, _ = _plugin(tmp_path)
    gw = Gateway(p, Allowlist({"wait"}))  # press_button NOT allowed
    res = gw.execute(_tc("press_button", {"button": "a"}))
    assert res.ok is False and "denied" in res.error


def test_gateway_passes_allowed_call(tmp_path):
    p, _ = _plugin(tmp_path)
    gw = Gateway(p, POKEMON_SANDBOX)
    res = gw.execute(_tc("press_button", {"button": "a"}))
    assert res.ok is True and res.cost_charged == 1


# -- runner episode -----------------------------------------------------------

def test_full_episode_runs_with_scripted_brain(tmp_path):
    p, _ = _plugin(tmp_path)
    gw = Gateway(p, POKEMON_SANDBOX)
    brain = ScriptedBrain("agent-1", seed=42)
    summary = run_episode(gw, p, brain, "agent-1", max_steps=8)
    assert summary["steps"] == 8
    assert summary["event_counts"].get("tool_called") == 8


# -- helpers ------------------------------------------------------------------

def _tc(tool, args):
    from core.contracts import ToolCall
    return ToolCall(tool=tool, args=args, agent_id="agent-1", call_id="call-1")
