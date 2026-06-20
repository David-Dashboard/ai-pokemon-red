"""Free movement-mechanics probe (no API): does ONE direction press = exactly ONE tile, even on a
direction change? The run-#15 interior-nav wall was dead-reckoning DRIFT: the autopilot presses
`[d, d]` (the old "turn, then move = net 1 tile" GateWorld assumption), but the REAL emulator absorbs
the turn within the held press, so `[d, d]` moves TWO tiles when open while the perceiver records one
-> the cursor loses ~1 tile per same-direction step -> the interior occupancy map corrupts.

The fix is to drive the autopilot with SINGLE presses (1 tile each). This probe confirms the premise:
a single `[d]` moves exactly one tile when open (incl. immediately after a turn), and zero when walled.
RAM x/y is read ONLY as the ground-truth oracle (never an agent input).

Run: uv run python -m eval.probe_step
"""
from __future__ import annotations

import sys

from games.pokemon_red.emulator import PyBoyEmulator
from games.pokemon_red.memory_map import ADDR_MAP_ID, ADDR_X, ADDR_Y

ROM = sys.argv[1] if len(sys.argv) > 1 else "roms/PokemonRed.gb"
STATE = sys.argv[2] if len(sys.argv) > 2 else "start.state"

# A walk that forces several DIRECTION CHANGES (the case where the GateWorld model says a press only
# turns). Each entry is one single-button press; we read RAM (x,y) before/after to see the true tiles.
SINGLE = ["down", "down", "right", "right", "up", "up", "left", "left", "up", "right", "down", "left"]


def _xy(M):
    return (M[ADDR_X], M[ADDR_Y], M[ADDR_MAP_ID])


def main() -> int:
    emu = PyBoyEmulator(ROM, headless=True)
    emu.load_state(STATE)
    M = emu._pyboy.memory

    print("=== SINGLE presses ([d]) — expect each open move = exactly 1 tile (incl. on a turn) ===")
    print(f"{'press':<7}{'before':>12}{'after':>12}{'dtiles':>8}  note")
    moved_one = walled = overshoot = 0
    prev_dir = None
    for d in SINGLE:
        bx, by, bm = _xy(M)
        emu.press(d)
        ax, ay, am = _xy(M)
        dt = abs(ax - bx) + abs(ay - by)
        turn = prev_dir is not None and d != prev_dir
        note = ("WALL" if dt == 0 else ("OK-1tile" if dt == 1 else f"!! {dt} tiles"))
        if am != bm:
            note = "WARP"
        elif dt == 0:
            walled += 1
        elif dt == 1:
            moved_one += 1
        else:
            overshoot += 1
        print(f"{d:<7}{str((bx,by)):>12}{str((ax,ay)):>12}{dt:>8}  {note}"
              f"{' (after a turn)' if turn else ''}")
        prev_dir = d

    print(f"\nsingle-press summary: moved-exactly-1={moved_one}  walled(0)={walled}  "
          f"OVERSHOT(>1)={overshoot}")
    verdict = "PASS — single press is a clean 1 tile" if overshoot == 0 and moved_one > 0 else \
              "FAIL — single press is NOT a reliable 1-tile move"
    print("VERDICT:", verdict)

    # Contrast: the OLD autopilot pattern [d, d]. Expect 2 tiles when open (the drift source).
    print("\n=== DOUBLE presses ([d, d]) — the OLD autopilot move; expect 2 tiles when open ===")
    print(f"{'press':<7}{'before':>12}{'after':>12}{'dtiles':>8}  note")
    twos = 0
    for d in ["down", "down", "up", "up", "right", "right", "left", "left"]:
        bx, by, bm = _xy(M)
        emu.press(d); emu.press(d)
        ax, ay, am = _xy(M)
        dt = abs(ax - bx) + abs(ay - by)
        if am == bm and dt == 2:
            twos += 1
        note = "WARP" if am != bm else ("WALL" if dt == 0 else f"{dt} tiles")
        print(f"{d:<7}{str((bx,by)):>12}{str((ax,ay)):>12}{dt:>8}  {note}")
    print(f"\ndouble-press: open moves that went a full 2 tiles = {twos} "
          f"(confirms [d,d] is 2 tiles, the drift source)")
    emu.close()
    return 0 if overshoot == 0 and moved_one > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
