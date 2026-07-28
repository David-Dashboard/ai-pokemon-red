"""Render a saved state's screen at 5x with a labelled 16px grid, so geometry can be MEASURED
instead of eyeballed. Eyeballing a 160x144 frame is what made the first dozen navigation guesses
wrong. $0, offline PyBoy, no LLM.

  python grid.py X02.state
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw

PRIMARY = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red"
ROM = PRIMARY + "/roms/Kirby's Dream Land (USA, Europe).gb"
OUT = ("C:/Users/Succe/AppData/Local/Temp/claude/"
       "E--AI-Personas-10-pokemon-and-chess-and-office/"
       "671b9313-5a35-40f5-a26e-315d9f7e8f28/scratchpad/kirby3")
S = 5


def main() -> int:
    name = sys.argv[1]
    path = name if os.path.exists(name) else os.path.join(OUT, name)
    from pyboy import PyBoy
    pb = PyBoy(ROM, window="null", sound_emulated=False)
    pb.set_emulation_speed(0)
    with open(path, "rb") as f:
        pb.load_state(f)
    pb.tick(2, render=True)
    im = pb.screen.image.convert("RGB")
    info = (f"D051={pb.memory[0xD051]} D052={pb.memory[0xD052]} "
            f"hp={pb.memory[0xD086]} lives={pb.memory[0xD089]}")
    pb.stop(save=False)

    big = im.resize((160 * S, 144 * S), Image.NEAREST)
    d = ImageDraw.Draw(big)
    for gx in range(0, 160, 16):
        d.line([(gx * S, 0), (gx * S, 144 * S)], fill=(255, 0, 0))
        d.text((gx * S + 2, 2), str(gx), fill=(255, 0, 0))
    for gy in range(0, 144, 16):
        d.line([(0, gy * S), (160 * S, gy * S)], fill=(0, 120, 255))
        d.text((2, gy * S + 2), str(gy), fill=(0, 120, 255))
    out = os.path.join(OUT, os.path.basename(path).replace(".state", "") + "_grid.png")
    big.save(out)
    print(f"{out}\n{info}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
