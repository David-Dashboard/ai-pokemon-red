"""Tests for world_mcp.py's Kirby's Dream Land world entry (--game kirby_dreamland).

This is the entity-grounding gate v2 port target (Cave Noire -> Kirby's Dream Land), per
runs/entity_world_port_findings.md. Mirrors tests/test_world_mcp_gb_generic.py's registry-sanity +
tools/list-freshness pattern (Kirby shares gb_generic's "no game-specific package" shape: PerceptionPlugin
+ FollowCameraPerceiver + the generic-GB sandbox), but with a real oracle (watch={"hp": 0xD086}) and the
foveated region tools (read_region/whats_changed), since this world needs both for the gate protocol.
"""
from __future__ import annotations

import argparse

import pytest

from world_mcp import GAMES, World, _GB_GENERIC_WORLDS, _REGION_TOOL_WORLDS, assert_action_tools_fresh, _static_tools


def _args(game: str, rom: str | None = None, out: str = "runs/test_kirby_dreamland") -> argparse.Namespace:
    return argparse.Namespace(game=game, rom=rom, init_state=None, out=out, record=False,
                              with_screenshot=False, keep_frames=False)


def test_kirby_dreamland_registered_in_games():
    assert "kirby_dreamland" in GAMES
    spec = GAMES["kirby_dreamland"]
    assert spec["pkg"] == "core.perception_plugin"
    assert spec["plugin"] == "PerceptionPlugin"
    assert spec["perceiver_mod"] == "core.grid_perceiver"
    assert spec["perceiver"] == "FollowCameraPerceiver"
    assert spec["rom"] == "roms/Kirby's Dream Land (USA, Europe).gb"


def test_kirby_dreamland_watch_is_hp_and_stage_oracle():
    """hp @ 0xD086 — verified plain-int oracle (0-5, 1 per HUD pip); see runs/entity_world_port_findings.md.
    stage @ 0xD03B — 0-indexed stage selector, established causally then held over 9,000 frames of live
    play; reports/2026-07-26-oracle-kirby-gb-stage3.md (PR #173). Both are plain ints, not BCD."""
    assert GAMES["kirby_dreamland"]["watch"] == {"hp": 0xD086, "stage": 0xD03B}


def test_kirby_dreamland_perceiver_is_zero_arg_constructible():
    import importlib
    spec = GAMES["kirby_dreamland"]
    Perceiver = getattr(importlib.import_module(spec["perceiver_mod"]), spec["perceiver"])
    Perceiver()


def test_kirby_dreamland_rom_is_gb_not_gba_or_nds():
    assert not GAMES["kirby_dreamland"]["rom"].lower().endswith((".gba", ".nds"))


def test_kirby_dreamland_in_gb_generic_worlds_sandbox_dispatch():
    """No game-specific package exists for Kirby -- it must use the same locally-built generic-GB
    sandbox branch as gb_generic (World.__init__ dispatches on this frozenset)."""
    assert "kirby_dreamland" in _GB_GENERIC_WORLDS


def test_kirby_dreamland_gets_region_tools():
    """The gate protocol needs foveation for ENT boxes + NEAR corroboration, same as cave_noire."""
    assert "kirby_dreamland" in _REGION_TOOL_WORLDS


def test_gba_rom_on_kirby_dreamland_fails_loud(tmp_path):
    fake_rom = tmp_path / "x.gba"
    fake_rom.write_bytes(b"\x00" * 16)
    with pytest.raises(SystemExit, match="mismatched"):
        World(_args("kirby_dreamland", rom=str(fake_rom), out=str(tmp_path / "out")))


def test_static_tools_kirby_dreamland_has_region_tools_and_no_touch():
    tools = _static_tools("kirby_dreamland")
    names = [t["name"] for t in tools]
    assert "touch" not in names and "touch_target" not in names
    assert "read_region" in names and "whats_changed" in names


def test_static_tools_kirby_dreamland_uses_gb_button_set():
    tools = _static_tools("kirby_dreamland")
    press = next(t for t in tools if t["name"] == "press_button")
    enum = press["inputSchema"]["properties"]["button"]["enum"]
    assert set(enum) == {"a", "b", "select", "start", "right", "left", "up", "down"}


def test_assert_action_tools_fresh_kirby_dreamland_world(tmp_path):
    """A real PyBoy boot (no emulator injection needed for .gb); skips if no fixture ROM is available
    in this environment (ROMs are gitignored) — mirrors test_world_mcp_gb_generic.py's fallback-ROM
    pattern since the actual Kirby ROM won't be present in CI either."""
    import os
    rom = None
    for candidate in ("roms/Kirby's Dream Land (USA, Europe).gb",
                      "roms/Cave Noire (Japan) [T-En by Aeon Genesis v1.00].gb",
                      "roms/Gauntlet II (USA, Europe).gb"):
        if os.path.exists(candidate):
            rom = candidate
            break
    if rom is None:
        pytest.skip("no GB ROM available in this environment (CI)")
    args = _args("kirby_dreamland", rom=rom, out=str(tmp_path / "out"))
    w = World(args)
    try:
        assert_action_tools_fresh(w.plugin, "kirby_dreamland")
    finally:
        w.plugin.close()


def test_gb_generic_worlds_frozenset_unaffected_for_gb_generic():
    """Adding kirby_dreamland must not remove gb_generic from its own sandbox-dispatch branch."""
    assert "gb_generic" in _GB_GENERIC_WORLDS


def test_other_worlds_tools_unchanged():
    """Adding kirby_dreamland must not perturb any other world's static tool list."""
    cave_noire_tools = [t["name"] for t in _static_tools("cave_noire")]
    assert "read_region" in cave_noire_tools and "whats_changed" in cave_noire_tools
    gauntlet_tools = [t["name"] for t in _static_tools("gauntlet")]
    assert "read_region" in gauntlet_tools and "whats_changed" in gauntlet_tools
    gb_generic_tools = [t["name"] for t in _static_tools("gb_generic")]
    assert "read_region" not in gb_generic_tools and "whats_changed" not in gb_generic_tools
    kirby_gba_tools = [t["name"] for t in _static_tools("kirby_gba")]
    assert "read_region" not in kirby_gba_tools and "whats_changed" not in kirby_gba_tools
