"""Causal mapping of 0xD03B -> which stage the game LOADS.

From Castle Lololo (0xD03B==1) write 0xD03B=V, force GAME OVER, take CONTINUE, and screenshot the
stage that loads. If the loaded stage tracks V, 0xD03B is the stage selector the game itself reads.
Writes only 0xD03B (the value under test) and 0xD086 (HP, to force the deaths). The four eliminated
candidates are never written -- we watch what they do across a real stage load.
Saves the resumed state so sustained play can be measured from it.
"""
import sys

import numpy as np
from PIL import Image, ImageDraw
from pyboy import PyBoy

ROM = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/roms/Kirby's Dream Land (USA, Europe).gb"
SRC = "C:/Users/Succe/AppData/Local/Temp/claude/E--AI-Personas-10-pokemon-and-chess-and-office/671b9313-5a35-40f5-a26e-315d9f7e8f28/scratchpad/kirby3"
OUT = "C:/Users/Succe/AppData/Local/Temp/claude/E--AI-Personas-10-pokemon-and-chess-and-office/671b9313-5a35-40f5-a26e-315d9f7e8f28/scratchpad/stage3check"

D03B, HP, LIVES = 0xD03B, 0xD086, 0xD089
ELIM = [0xD19F, 0xD3A9, 0xD3BA, 0xD3CD]
VALUES = [int(v) for v in sys.argv[1].split(",")]

shots = []
for V in VALUES:
    pb = PyBoy(ROM, window="null", sound_emulated=False)
    pb.set_emulation_speed(0)
    with open(f"{SRC}/s2_start.state", "rb") as f:
        pb.load_state(f)
    pb.tick(4, render=True)
    before = int(pb.memory[D03B])
    if V >= 0:
        pb.memory[D03B] = V
    for life in range(8):
        pb.memory[HP] = 0
        for i in range(90):
            pb.tick(12, render=True)
        if int(pb.memory[LIVES]) == 0 and int(pb.memory[HP]) == 0:
            break
    if V >= 0:
        pb.memory[D03B] = V                       # re-assert at the CONTINUE prompt
    for i in range(40):
        for b in ("start", "a"):
            pb.button_press(b)
            pb.tick(6, render=True)
            pb.button_release(b)
            pb.tick(14, render=True)
    # settle into the level
    for i in range(60):
        pb.button_press("right")
        pb.tick(14, render=True)
        pb.button_release("right")
    m = pb.memory
    print(f"D03B written={V if V >= 0 else 'NONE (control, was ' + str(before) + ')'}  "
          f"-> after resume: D03B={m[D03B]} elim={[int(m[a]) for a in ELIM]} "
          f"hp={m[HP]} lives={m[LIVES]}", flush=True)
    shots.append((f"wrote {V} -> D03B={m[D03B]}",
                  np.asarray(pb.screen.ndarray)[:, :, :3].copy()))
    tag = "ctl" if V < 0 else str(V)
    with open(f"{OUT}/resumed_D03B_{tag}.state", "wb") as f:
        pb.save_state(f)
    pb.stop(save=False)

cols = len(shots)
sheet = Image.new("RGB", (160 * cols, 144 + 12), "black")
d = ImageDraw.Draw(sheet)
for i, (tag, a) in enumerate(shots):
    sheet.paste(Image.fromarray(a), (160 * i, 12))
    d.text((160 * i + 2, 1), tag, fill="white")
sheet.save(f"{OUT}/causal_map.png")
print("montage -> causal_map.png")
