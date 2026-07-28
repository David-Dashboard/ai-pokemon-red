"""Locate doors and Kirby by READING THE TILEMAP, instead of hunting for them with search.

In Castle Lololo's interior tileset a door is a `357|358` arch over a 2x2 block of `380`. Verified
against a door already known to be enterable (`D01.state`, where walking right 12-26px and pressing
up reliably transitions) and against the water room, where it correctly found both the entry door
and the unreachable lower one.

Caveat, learned the hard way: the signature is TILESET-SPECIFIC. `380` is the door body in the
castle interior but the night sky in the battlements, and the post-warp-star area draws neither.
Always sanity-check the reported doors against a screenshot before trusting them.

  python doorscan.py u01.state
"""
from __future__ import annotations

import os
import sys

PRIMARY = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red"
ROM = PRIMARY + "/roms/Kirby's Dream Land (USA, Europe).gb"
OUT = ("C:/Users/Succe/AppData/Local/Temp/claude/"
       "E--AI-Personas-10-pokemon-and-chess-and-office/"
       "671b9313-5a35-40f5-a26e-315d9f7e8f28/scratchpad/kirby3")
ARCH_L, ARCH_R, BODY = 357, 358, 380
KIRBY_TILES = {0, 1, 2, 3, 16, 17, 18, 19, 32, 33, 34, 35, 48, 49, 50, 51}


def scan(state_path, ticks=180):
    from pyboy import PyBoy
    pb = PyBoy(ROM, window="null", sound_emulated=False)
    pb.set_emulation_speed(0)
    with open(state_path, "rb") as f:
        pb.load_state(f)
    pb.tick(ticks, render=True)
    g = pb.game_wrapper.game_area()

    doors = []
    for r in range(len(g) - 1):
        for c in range(len(g[0]) - 1):
            if int(g[r][c]) == ARCH_L and int(g[r][c + 1]) == ARCH_R \
                    and int(g[r + 1][c]) == BODY and int(g[r + 1][c + 1]) == BODY:
                doors.append((r, c))

    kirby = [(s.x, s.y) for s in (pb.get_sprite(i) for i in range(40))
             if s.on_screen and s.tile_identifier in KIRBY_TILES]
    kx = sum(x for x, _ in kirby) / len(kirby) if kirby else None
    ky = sum(y for _, y in kirby) / len(kirby) if kirby else None
    info = {"d051": pb.memory[0xD051], "d052": pb.memory[0xD052],
            "hp": pb.memory[0xD086], "lives": pb.memory[0xD089]}
    pb.stop(save=False)
    return doors, (kx, ky), info


def main() -> int:
    for name in sys.argv[1:]:
        path = name if os.path.exists(name) else os.path.join(OUT, name)
        doors, (kx, ky), info = scan(path)
        print(f"{os.path.basename(path):32s} D051={info['d051']:3d} D052={info['d052']} "
              f"hp={info['hp']} lives={info['lives']}")
        if kx is None:
            print("   kirby: not found on screen")
        else:
            print(f"   kirby at screen ({kx:.0f}, {ky:.0f})")
        if not doors:
            print("   no doors matching the castle-interior signature")
        for r, c in doors:
            # door mouth: the arch spans 2 tiles; Kirby enters standing at its centre
            px, py = c * 8 + 8, r * 8
            dx = (px - kx) if kx is not None else 0
            print(f"   DOOR tile(r{r},c{c}) -> screen x~{px} y~{py}   dx from kirby = {dx:+.0f}px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
