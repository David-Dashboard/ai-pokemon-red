"""Pokémon Red support-module tests — run with NO ROM and NO PyBoy.

`FakeEmulator` is the RAM-backed PyBoy stand-in shared across the pokemon_red test files (and borrowed
by test_cave_noire.py / test_gauntlet.py, which reuse it as a generic fake). Covers the pure memory-map
parsing and the emulator's battle-settle pacing helper (`advance_until_static`). The heavy `GamePlugin`
this file used to test (reward shaping, RAM-observe, POKEMON_SYSTEM) was archived to `_archive/` when Red
was wired into the game-agnostic MCP seam — see tests/test_no_ram_leak.py and tests/test_perception.py
for the lean `PokemonRedPlugin`'s coverage now. (A real-ROM integration test is intentionally omitted —
it needs a copyrighted ROM the project never ships.)
"""

from __future__ import annotations

from games.pokemon_red import memory_map as mm


class FakeEmulator:
    """RAM-backed stand-in for PyBoy. Tests poke `mem` to simulate the game."""

    def __init__(self) -> None:
        self.mem: dict[int, int] = {}
        self._frame = 0
        self._screen = None  # set to an ndarray to drive the perception path
        self.settles = 0     # count of settle() calls (battle-pacing wiring assertion)
        self._faded = False  # set True to simulate a press that crossed a map-warp fade

    def press(self, button, hold_frames=8, settle_frames=16):
        self._frame += hold_frames + settle_frames

    def tick(self, frames):
        self._frame += frames

    def settle(self, max_frames=240):
        self.settles += 1
        return True

    def faded(self):
        return self._faded

    def read(self, addr):
        return self.mem.get(addr, 0)

    def save_screen(self, path):
        with open(path, "wb") as f:
            f.write(b"")  # empty PNG placeholder is enough for the path contract

    def screen_ndarray(self):
        import numpy as np
        return self._screen if self._screen is not None else np.zeros((144, 160, 4), dtype="uint8")

    def load_state(self, path):
        self.loaded = path

    def save_state(self, path):
        self.saved = path

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


# -- battle pacing: settle a battle animation before observing -----------------

def test_advance_until_static_settles_when_animation_stops():
    import numpy as np
    from games.pokemon_red.emulator import advance_until_static
    a = np.zeros((4, 4, 3), dtype=np.uint8)
    b = np.full((4, 4, 3), 200, dtype=np.uint8)
    seq = [a, b, a, b] + [a] * 30            # animating, then static
    it = iter(seq)
    settled, pulled = advance_until_static(lambda: next(it, seq[-1]),
                                           max_frames=200, window=10, eps=2.0)
    assert settled is True
    assert pulled < 200                       # stopped early once it went static


def test_advance_until_static_caps_when_never_static():
    import numpy as np
    from games.pokemon_red.emulator import advance_until_static
    flip = [np.zeros((4, 4, 3), np.uint8), np.full((4, 4, 3), 200, np.uint8)]
    n = {"i": 0}
    def nxt():
        n["i"] += 1
        return flip[n["i"] % 2]               # perpetual animation
    settled, pulled = advance_until_static(nxt, max_frames=50, window=10, eps=2.0)
    assert settled is False and pulled == 50


def test_advance_until_static_tolerates_cursor_blink():
    # A blinking cursor (one tiny tile toggling) must NOT reset the streak — the screen is still
    # "waiting for input". Simulate a sub-eps periodic flicker on an otherwise static screen.
    import numpy as np
    from games.pokemon_red.emulator import advance_until_static
    base = np.full((144, 160, 3), 100, dtype=np.uint8)
    blink = base.copy(); blink[112:120, 8:16] = 130   # one 8x8 tile, small delta
    seq = [base, blink, base, blink, base, base, base, base, base, base, base, base]
    it = iter(seq)
    settled, _ = advance_until_static(lambda: next(it, base), max_frames=100, window=8, eps=2.0)
    assert settled is True


def test_advance_until_static_eps_is_strict_not_inclusive():
    # A diff exactly == eps must NOT count as static (the code uses `< eps`). Guards against a future
    # `<=` typo that would read a constant eps-sized animation as "settled".
    import numpy as np
    from games.pokemon_red.emulator import advance_until_static
    a = np.zeros((4, 4, 3), dtype=np.uint8)
    b = np.full((4, 4, 3), 2, dtype=np.uint8)        # mean abs diff a<->b == 2.0 == eps
    it = iter([a, b] * 40)
    settled, pulled = advance_until_static(lambda: next(it, a), max_frames=40, window=8, eps=2.0)
    assert settled is False and pulled == 40          # never settles: each diff == eps, not < eps


def test_advance_until_static_none_frame_does_not_break_streak():
    # A None frame (emulator returned nothing this tick) skips that diff without resetting the streak
    # and without crashing — the static run resumes across the gap.
    import numpy as np
    from games.pokemon_red.emulator import advance_until_static
    s = np.full((4, 4, 3), 100, dtype=np.uint8)
    seq = [s, s, s, None, s, s, s, s, s, s]           # static, with one None hole partway
    it = iter(seq)
    settled, _ = advance_until_static(lambda: next(it, s), max_frames=50, window=6, eps=2.0)
    assert settled is True


def test_advance_until_static_requires_a_full_window():
    # Exactly `window` sub-eps diffs are needed; the first pulled frame has no predecessor to diff,
    # so settling happens on pull window+1. Pins the `>= window` threshold against an off-by-one.
    import numpy as np
    from games.pokemon_red.emulator import advance_until_static
    base = np.full((8, 8, 3), 70, dtype=np.uint8)
    it = iter([base] * 50)
    settled, pulled = advance_until_static(lambda: next(it, base), max_frames=50, window=5, eps=2.0)
    assert settled is True and pulled == 6            # 1 priming pull + 5 stable diffs


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
