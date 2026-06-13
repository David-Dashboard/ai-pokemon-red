"""Perception seam tests (Iteration 02, Step 1) — no ROM, no PyBoy.

Covers the SymbolicState contract, the StubPerceiver, and the plugin wiring: when a
perceiver is injected the agent sees a SymbolicState (pixels-derived) and RAM is written
ONLY to the oracle side-log — never into Observation.data (the no-leak wall).
"""
from __future__ import annotations

import json

from core.perception import PerceptMemory, Perceiver, StubPerceiver, SymbolicState
from games.pokemon_red import memory_map as mm
from games.pokemon_red.plugin import PokemonRedPlugin
from tests.test_pokemon_red import FakeEmulator

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

    # RAM ground-truth lives only in the oracle side-channel.
    rec = json.loads((tmp_path / "oracle.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert rec["map_id"] == 38 and rec["x"] == 3 and rec["y"] == 7
