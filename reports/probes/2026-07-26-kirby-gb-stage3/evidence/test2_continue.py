"""TEST 2: from a Stage-2 (Castle Lololo) state, force GAME OVER, take CONTINUE, and report what
0xD03B reads on the stage we resume into.

Death is forced by writing 0xD086 (Kirby HP) to 0 -- and ONLY that plus reading. 0xD03B and the four
eliminated candidates are never written. Distinguishes 'stage index' from 'stages cleared counter':
a cleared-counter would keep counting; a stage index should match the stage we resume into.
"""
import sys

import numpy as np
from PIL import Image, ImageDraw
from pyboy import PyBoy

ROM = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/roms/Kirby's Dream Land (USA, Europe).gb"
SRC = "C:/Users/Succe/AppData/Local/Temp/claude/E--AI-Personas-10-pokemon-and-chess-and-office/671b9313-5a35-40f5-a26e-315d9f7e8f28/scratchpad/kirby3"
OUT = "C:/Users/Succe/AppData/Local/Temp/claude/E--AI-Personas-10-pokemon-and-chess-and-office/671b9313-5a35-40f5-a26e-315d9f7e8f28/scratchpad/stage3check"

START = sys.argv[1] if len(sys.argv) > 1 else "boss_fresh"
D03B, HP, LIVES = 0xD03B, 0xD086, 0xD089
ELIM = [0xD19F, 0xD3A9, 0xD3BA, 0xD3CD]

pb = PyBoy(ROM, window="null", sound_emulated=False)
pb.set_emulation_speed(0)
with open(f"{SRC}/{START}.state", "rb") as f:
    pb.load_state(f)
pb.tick(4, render=True)

shots, prev = [], None


def obs(tag):
    global prev
    m = pb.memory
    cur = (int(m[D03B]), tuple(int(m[a]) for a in ELIM), int(m[HP]), int(m[LIVES]))
    if cur != prev:
        print(f"  [{tag}] f={pb.frame_count:>7} D03B={cur[0]} elim={list(cur[1])} "
              f"hp={cur[2]} lives={cur[3]}", flush=True)
        prev = cur


print(f"=== start {START} ===")
obs("start")
shots.append(("start", np.asarray(pb.screen.ndarray)[:, :, :3].copy()))

# Burn every life: zero Kirby's HP, let the death + respawn play out, repeat until GAME OVER.
for life in range(8):
    pb.memory[HP] = 0
    for i in range(90):
        pb.tick(12, render=True)
        obs(f"die{life}")
    shots.append((f"die{life} lv={pb.memory[LIVES]}",
                  np.asarray(pb.screen.ndarray)[:, :, :3].copy()))
    if int(pb.memory[LIVES]) == 0 and int(pb.memory[HP]) == 0:
        print(f"  -> lives exhausted after {life+1} deaths", flush=True)
        break

print("=== should be at GAME OVER / CONTINUE prompt ===")
shots.append(("gameover?", np.asarray(pb.screen.ndarray)[:, :, :3].copy()))

# Take CONTINUE: the prompt defaults to CONTINUE, press START/A to accept.
for i in range(40):
    for b in ("start", "a"):
        pb.button_press(b)
        pb.tick(6, render=True)
        pb.button_release(b)
        pb.tick(14, render=True)
    obs("continue")
shots.append(("after continue", np.asarray(pb.screen.ndarray)[:, :, :3].copy()))

print("=== play a little on whatever stage we resumed into ===")
for i in range(150):
    acts = ["right"] if i % 4 else ["right", "a"]
    for b in acts:
        pb.button_press(b)
    pb.tick(14, render=True)
    for b in acts:
        pb.button_release(b)
    obs("resume")
    if i % 50 == 0:
        shots.append((f"resume {i}", np.asarray(pb.screen.ndarray)[:, :, :3].copy()))
shots.append(("resume end", np.asarray(pb.screen.ndarray)[:, :, :3].copy()))

m = pb.memory
print(f"\nFINAL: D03B={m[D03B]} elim={[int(m[a]) for a in ELIM]} hp={m[HP]} lives={m[LIVES]}")

cols = 5
rows = (len(shots) + cols - 1) // cols
sheet = Image.new("RGB", (160 * cols, (144 + 12) * rows), "black")
d = ImageDraw.Draw(sheet)
for i, (tag, a) in enumerate(shots):
    x, y = 160 * (i % cols), (144 + 12) * (i // cols)
    sheet.paste(Image.fromarray(a), (x, y + 12))
    d.text((x + 2, y + 1), tag, fill="white")
sheet.save(f"{OUT}/test2_{START}.png")
pb.stop(save=False)
print("montage ->", f"{OUT}/test2_{START}.png")
