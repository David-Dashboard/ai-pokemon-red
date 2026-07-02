"""Unit tests for world_mcp.py's emulator dispatch (feat/world-mcp-gba-nds-emulators).

Bug being fixed: World.__init__ never passed `emulator=` to the plugin, so `--game nds` fell through
to PerceptionPlugin's PyBoyEmulator default and crashed feeding it a .nds ROM ("Cartridge header
checksum mismatch!"). This file proves:

  1. ROM-extension dispatch selects the right emulator class (.nds -> DeSmuMEEmulator, .gba ->
     GBAEmulator, else -> PyBoy/default) WITHOUT importing/booting the heavy deps — the lazy imports
     inside World.__init__ are monkeypatched with fakes so no py-desmume/mgba install is required.
  2. A regression test that `--game nds` World construction attempts DeSmuME (skips cleanly if
     py-desmume is not installed in this environment — it happens to be installed out-of-band here).
  3. GAMES-entry sanity for the two new GBA worlds (kirby_gba, emerald_gba): rom path exists,
     perceiver is zero-arg constructible, sandbox/static-tools wiring is consistent.
  4. The existing tools/list <-> live-plugin freshness invariant (assert_action_tools_fresh) stays
     green for the NDS and the two new GBA worlds.

Most tests monkeypatch the lazy import points inside World.__init__ so no py-desmume/mgba install is
required. ROMs are gitignored (roms/.gitignore excludes everything), so any test needing a real ROM
file — including booting a real PyBoy — skips when the ROM is absent (CI has no ROMs).
"""
from __future__ import annotations

import argparse
import os

import pytest

import world_mcp
from world_mcp import GAMES, World, _GBA_WORLDS, _NDS_WORLDS, assert_action_tools_fresh, _static_tools


def _args(game: str, rom: str | None = None, out: str = "runs/test_mcp_dispatch") -> argparse.Namespace:
    return argparse.Namespace(game=game, rom=rom, init_state=None, out=out, record=False,
                              with_screenshot=False, keep_frames=False)


# ---------------------------------------------------------------------------
# 1. Dispatch selects the right emulator class (fakes injected, no real ROM/deps).
# ---------------------------------------------------------------------------

class _FakeEmu:
    """Minimal stand-in that satisfies the bits World.__init__ / PerceptionPlugin touch at construction."""
    BUTTONS = ("a", "b", "select", "start", "right", "left", "up", "down")

    def __init__(self, rom_path: str, headless: bool = True):
        self.rom_path = rom_path
        self.headless = headless

    def load_state(self, path):
        pass

    def close(self):
        pass


def test_nds_rom_dispatches_to_desmume_emulator(monkeypatch, tmp_path):
    """A .nds ROM path must build a DeSmuMEEmulator (not fall through to PyBoy)."""
    calls: list[str] = []

    class _FakeDeSmuME(_FakeEmu):
        def __init__(self, rom_path, headless=True):
            calls.append(rom_path)
            super().__init__(rom_path, headless=headless)

    monkeypatch.setattr("core.nds_emulator.DeSmuMEEmulator", _FakeDeSmuME)
    fake_rom = tmp_path / "game.nds"
    fake_rom.write_bytes(b"\x00" * 16)
    args = _args("nds", rom=str(fake_rom), out=str(tmp_path / "out"))
    w = World(args)
    try:
        assert calls == [str(fake_rom)], f"expected DeSmuMEEmulator constructed with {fake_rom}, got {calls}"
        assert isinstance(w.plugin.emu, _FakeDeSmuME)
    finally:
        w.plugin.close()


def test_gba_rom_dispatches_to_gba_emulator(monkeypatch, tmp_path):
    """A .gba ROM path must build a GBAEmulator (not fall through to PyBoy)."""
    calls: list[str] = []

    class _FakeGBA(_FakeEmu):
        BUTTONS = ("a", "b", "select", "start", "right", "left", "up", "down", "r", "l")

        def __init__(self, rom_path):
            calls.append(rom_path)
            super().__init__(rom_path)

    monkeypatch.setattr("core.gba_emulator.GBAEmulator", _FakeGBA)
    fake_rom = tmp_path / "game.gba"
    fake_rom.write_bytes(b"\x00" * 16)
    args = _args("kirby_gba", rom=str(fake_rom), out=str(tmp_path / "out"))
    w = World(args)
    try:
        assert calls == [str(fake_rom)], f"expected GBAEmulator constructed with {fake_rom}, got {calls}"
        assert isinstance(w.plugin.emu, _FakeGBA)
    finally:
        w.plugin.close()


def test_gb_rom_does_not_touch_nds_or_gba_lazy_imports(monkeypatch, tmp_path):
    """A .gb ROM must NOT construct DeSmuMEEmulator or GBAEmulator (the default PyBoy path is unchanged)."""
    def _boom_nds(*a, **k):
        raise AssertionError("DeSmuMEEmulator must not be constructed for a .gb ROM")

    def _boom_gba(*a, **k):
        raise AssertionError("GBAEmulator must not be constructed for a .gb ROM")

    monkeypatch.setattr("core.nds_emulator.DeSmuMEEmulator", _boom_nds)
    monkeypatch.setattr("core.gba_emulator.GBAEmulator", _boom_gba)
    # Boots a real PyBoy with cave_noire's ROM — gitignored, so skip where ROMs aren't present (CI).
    if not os.path.exists(GAMES["cave_noire"]["rom"]):
        pytest.skip("cave_noire ROM not available in this environment")
    args = _args("cave_noire", out=str(tmp_path / "out"))
    w = World(args)
    w.plugin.close()


# ---------------------------------------------------------------------------
# 2. Regression: `--game nds` World construction attempts DeSmuME construction
#    (skips cleanly if py-desmume is not installed in this environment).
# ---------------------------------------------------------------------------

def _first_nds_rom() -> str | None:
    d = "roms/nds"
    if not os.path.isdir(d):
        return None
    for name in sorted(os.listdir(d)):
        if name.lower().endswith(".nds"):
            return os.path.join(d, name)
    return None


def test_game_nds_world_construction_uses_desmume_not_pyboy(tmp_path):
    """End-to-end (no monkeypatch): --game nds must attempt DeSmuME, never PyBoy, for a .nds ROM.
    This is the exact bug from the findings — World.__init__ never passed emulator= to the plugin,
    so it silently built a PyBoyEmulator and crashed feeding it a .nds ROM."""
    pytest.importorskip("desmume", reason="py-desmume not installed in this environment")
    rom = _first_nds_rom()
    if rom is None:
        pytest.skip("no .nds ROM available in roms/nds in this environment")
    args = _args("nds", rom=rom, out=str(tmp_path / "out"))
    w = World(args)
    try:
        from core.nds_emulator import DeSmuMEEmulator
        assert isinstance(w.plugin.emu, DeSmuMEEmulator), (
            f"--game nds must build a DeSmuMEEmulator, got {type(w.plugin.emu)}")
    finally:
        w.plugin.close()


# ---------------------------------------------------------------------------
# 3. GAMES-entry sanity for the two new GBA worlds.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("game", sorted(_GBA_WORLDS))
def test_gba_world_rom_path_exists(game):
    rom = GAMES[game]["rom"]
    assert rom.lower().endswith(".gba")   # entry shape is checkable everywhere
    if not os.path.isdir("roms/gba"):
        pytest.skip("roms are gitignored and absent in this environment (CI)")
    assert os.path.exists(rom), f"{game}'s ROM does not exist: {rom}"


@pytest.mark.parametrize("game", sorted(_GBA_WORLDS))
def test_gba_world_perceiver_is_zero_arg_constructible(game):
    import importlib
    spec = GAMES[game]
    Perceiver = getattr(importlib.import_module(spec["perceiver_mod"]), spec["perceiver"])
    Perceiver()  # must not raise / must not require args


@pytest.mark.parametrize("game", sorted(_GBA_WORLDS))
def test_gba_world_watch_is_empty(game):
    """GBA worlds carry no RAM oracle (no-leak rule stays trivially satisfied: nothing to leak)."""
    assert GAMES[game]["watch"] == {}


def test_gba_worlds_registered_in_games():
    assert "kirby_gba" in GAMES
    assert "emerald_gba" in GAMES


def test_mismatched_rom_and_game_family_fails_loud(tmp_path):
    """A .gba ROM on a GB world must die at startup with a clear message, not later via a misleading
    "static tools are STALE" SystemExit from assert_action_tools_fresh."""
    fake_rom = tmp_path / "x.gba"
    fake_rom.write_bytes(b"\x00" * 16)
    with pytest.raises(SystemExit, match="mismatched"):
        World(_args("cave_noire", rom=str(fake_rom), out=str(tmp_path / "out")))


def test_record_rejected_for_injected_emulator_worlds(tmp_path):
    """--record only threads through the default PyBoy path; GBA/NDS worlds must reject it loudly
    instead of silently writing no session.mp4."""
    fake_rom = tmp_path / "x.gba"
    fake_rom.write_bytes(b"\x00" * 16)
    args = _args("kirby_gba", rom=str(fake_rom), out=str(tmp_path / "out"))
    args.record = True
    with pytest.raises(SystemExit, match="--record is not supported"):
        World(args)


# ---------------------------------------------------------------------------
# 4. tools/list freshness invariant holds for NDS + the new GBA worlds.
# ---------------------------------------------------------------------------

def test_static_tools_gba_world_has_no_touch():
    tools = _static_tools("kirby_gba")
    names = [t["name"] for t in tools]
    assert "touch" not in names and "touch_target" not in names


def test_static_tools_gba_world_has_lr_buttons():
    """GBA worlds must advertise l/r shoulder buttons (item 4 of the plan: wire GBAEmulator.BUTTONS
    through properly, not the GB 8-button fallback)."""
    tools = _static_tools("kirby_gba")
    press = next(t for t in tools if t["name"] == "press_button")
    enum = press["inputSchema"]["properties"]["button"]["enum"]
    assert "l" in enum and "r" in enum, f"expected l/r in GBA button enum, got {enum}"


def test_assert_action_tools_fresh_gba_world(monkeypatch, tmp_path):
    """The live GBAEmulator-backed plugin's tools() must exactly match _static_tools('kirby_gba')."""
    class _FakeGBA(_FakeEmu):
        BUTTONS = ("a", "b", "select", "start", "right", "left", "up", "down", "r", "l")

        def __init__(self, rom_path):
            super().__init__(rom_path)

    monkeypatch.setattr("core.gba_emulator.GBAEmulator", _FakeGBA)
    fake_rom = tmp_path / "game.gba"
    fake_rom.write_bytes(b"\x00" * 16)
    args = _args("kirby_gba", rom=str(fake_rom), out=str(tmp_path / "out"))
    w = World(args)
    try:
        assert_action_tools_fresh(w.plugin, "kirby_gba")  # must not raise
    finally:
        w.plugin.close()


def test_assert_action_tools_fresh_nds_world_still_green(monkeypatch, tmp_path):
    """Existing NDS freshness check stays green now that emulator= is actually injected."""
    class _FakeDeSmuME(_FakeEmu):
        BUTTONS = ("a", "b", "x", "y", "l", "r", "start", "select", "up", "down", "left", "right")

        def __init__(self, rom_path, headless=True):
            super().__init__(rom_path, headless=headless)

    monkeypatch.setattr("core.nds_emulator.DeSmuMEEmulator", _FakeDeSmuME)
    fake_rom = tmp_path / "game.nds"
    fake_rom.write_bytes(b"\x00" * 16)
    args = _args("nds", rom=str(fake_rom), out=str(tmp_path / "out"))
    w = World(args)
    try:
        assert_action_tools_fresh(w.plugin, "nds")  # must not raise
    finally:
        w.plugin.close()
