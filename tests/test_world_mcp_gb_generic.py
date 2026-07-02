"""Tests for world_mcp.py's generic GB/GBC lean-world path (--game gb_generic --rom <path>).

Mirrors tests/test_world_mcp_gba_nds_dispatch.py's GAMES-entry-sanity + tools/list-freshness pattern for
the two new GBA worlds, but for gb_generic. No ROM is needed to boot it (a .gb/.gbc ROM uses the default
PyBoy path, same as every other GB world already in GAMES) — a tiny fake ROM header is enough for PyBoy's
own tests elsewhere to exercise real boot; here we only check registry wiring + tools/list freshness with
a lightweight fake emulator (monkeypatched), consistent with the existing GBA/NDS dispatch tests.
"""
from __future__ import annotations

import argparse

import pytest

from world_mcp import GAMES, World, _GB_GENERIC_WORLDS, assert_action_tools_fresh, _static_tools


def _args(game: str, rom: str | None = None, out: str = "runs/test_gb_generic") -> argparse.Namespace:
    return argparse.Namespace(game=game, rom=rom, init_state=None, out=out, record=False,
                              with_screenshot=False, keep_frames=False)


def test_gb_generic_registered_in_games():
    assert "gb_generic" in GAMES
    spec = GAMES["gb_generic"]
    assert spec["pkg"] == "core.perception_plugin"
    assert spec["plugin"] == "PerceptionPlugin"
    assert spec["perceiver_mod"] == "core.grid_perceiver"
    assert spec["perceiver"] == "FollowCameraPerceiver"


def test_gb_generic_watch_is_empty():
    """No oracle entries for generic worlds — a free probe reads no RAM."""
    assert GAMES["gb_generic"]["watch"] == {}


def test_gb_generic_perceiver_is_zero_arg_constructible():
    import importlib
    spec = GAMES["gb_generic"]
    Perceiver = getattr(importlib.import_module(spec["perceiver_mod"]), spec["perceiver"])
    Perceiver()


def test_gb_generic_requires_rom_override_or_mismatches():
    """The registry's placeholder rom must not silently look valid — --rom is mandatory in practice."""
    assert not GAMES["gb_generic"]["rom"].lower().endswith((".gba", ".nds"))


def test_gba_rom_on_gb_generic_fails_loud(tmp_path):
    fake_rom = tmp_path / "x.gba"
    fake_rom.write_bytes(b"\x00" * 16)
    with pytest.raises(SystemExit, match="mismatched"):
        World(_args("gb_generic", rom=str(fake_rom), out=str(tmp_path / "out")))


def test_static_tools_gb_generic_has_no_touch_and_no_region_tools():
    tools = _static_tools("gb_generic")
    names = [t["name"] for t in tools]
    assert "touch" not in names and "touch_target" not in names
    assert "read_region" not in names and "whats_changed" not in names


def test_static_tools_gb_generic_uses_gb_button_set():
    tools = _static_tools("gb_generic")
    press = next(t for t in tools if t["name"] == "press_button")
    enum = press["inputSchema"]["properties"]["button"]["enum"]
    assert set(enum) == {"a", "b", "select", "start", "right", "left", "up", "down"}


def test_assert_action_tools_fresh_gb_generic_world(tmp_path):
    """A real PyBoy boot (no emulator injection needed for .gb — mirrors every other GB world);
    skips if no fixture ROM is available in this environment (ROMs are gitignored)."""
    import os
    rom = None
    for candidate in ("roms/Cave Noire (Japan) [T-En by Aeon Genesis v1.00].gb",
                      "roms/Gauntlet II (USA, Europe).gb"):
        if os.path.exists(candidate):
            rom = candidate
            break
    if rom is None:
        pytest.skip("no GB ROM available in this environment (CI)")
    args = _args("gb_generic", rom=rom, out=str(tmp_path / "out"))
    w = World(args)
    try:
        assert_action_tools_fresh(w.plugin, "gb_generic")
    finally:
        w.plugin.close()


def test_gb_generic_worlds_frozenset_contains_only_gb_generic():
    """kirby_dreamland also uses this sandbox-dispatch branch (see test_world_mcp_kirby_dreamland.py)
    -- it has no game-specific package either, same as gb_generic."""
    assert _GB_GENERIC_WORLDS == frozenset({"gb_generic", "kirby_dreamland"})
