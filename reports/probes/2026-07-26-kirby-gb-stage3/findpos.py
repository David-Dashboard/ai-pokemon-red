"""Locate Kirby's X/Y position bytes in WRAM so the driver can report progress and detect being
stuck. $0, offline PyBoy, no LLM.

Method: from one state, run three isolated branches -- hold right, hold left, hold nothing -- and
keep only bytes that move UP under right, DOWN under left, and stay PUT under idle. A byte that
merely counts frames or animates passes none of those three at once.
"""
from __future__ import annotations

import os
import sys

PRIMARY = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red"
ROM = PRIMARY + "/roms/Kirby's Dream Land (USA, Europe).gb"
OUT = ("C:/Users/Succe/AppData/Local/Temp/claude/"
       "E--AI-Personas-10-pokemon-and-chess-and-office/"
       "671b9313-5a35-40f5-a26e-315d9f7e8f28/scratchpad/kirby3")
LO, HI = 0xC000, 0xE000


def branch(state_path, button, frames=48):
    from pyboy import PyBoy
    pb = PyBoy(ROM, window="null", sound_emulated=False)
    pb.set_emulation_speed(0)
    with open(state_path, "rb") as f:
        pb.load_state(f)
    pb.tick(1, render=False)
    before = [pb.memory[a] for a in range(LO, HI)]
    if button:
        pb.button_press(button)
    pb.tick(frames, render=False)
    if button:
        pb.button_release(button)
    after = [pb.memory[a] for a in range(LO, HI)]
    scx = pb.memory[0xFF43]
    pb.stop(save=False)
    return before, after, scx


def main() -> int:
    state = sys.argv[1] if len(sys.argv) > 1 else os.path.join(OUT, "r05.state")
    base, right, scx_r = branch(state, "right")
    _, left, scx_l = branch(state, "left")
    _, idle, scx_i = branch(state, None)
    print(f"SCX after right={scx_r} left={scx_l} idle={scx_i}")

    hits = []
    for i in range(HI - LO):
        b, r, l, n = base[i], right[i], left[i], idle[i]
        if r == b or l == b:
            continue
        if n != b:                      # must be still when no input
            continue
        dr, dl = (r - b) & 0xFF, (l - b) & 0xFF
        # signed deltas, small: right increases, left decreases
        sr = dr - 256 if dr > 127 else dr
        sl = dl - 256 if dl > 127 else dl
        if sr > 0 and sl < 0 and abs(sr) < 64 and abs(sl) < 64:
            hits.append((LO + i, b, r, l, sr, sl))

    print(f"{len(hits)} candidate X bytes (right+, left-, idle stable):")
    for addr, b, r, l, sr, sl in hits:
        print(f"  0x{addr:04X}  base={b:3d} right={r:3d}({sr:+d}) left={l:3d}({sl:+d})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
