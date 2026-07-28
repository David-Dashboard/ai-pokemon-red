"""TEST 1 (minimal): un-pause, PROVE Kirby is controllable, then log 0xD03B + the four eliminated
candidates every 30 frames across a long window of ordinary play. No RAM writes anywhere here."""
import json
import random
import sys

import numpy as np
from PIL import Image, ImageDraw
from pyboy import PyBoy

ROM = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/roms/Kirby's Dream Land (USA, Europe).gb"
OUT = "C:/Users/Succe/AppData/Local/Temp/claude/E--AI-Personas-10-pokemon-and-chess-and-office/671b9313-5a35-40f5-a26e-315d9f7e8f28/scratchpad/stage3check"

STATE, TAG = sys.argv[1], sys.argv[2]
PLAY = int(sys.argv[3]) if len(sys.argv) > 3 else 9000

D03B, HP, LIVES, X = 0xD03B, 0xD086, 0xD089, 0xD051
ELIM = [0xD19F, 0xD3A9, 0xD3BA, 0xD3CD]
NAMES = ["D19F", "D3A9", "D3BA", "D3CD"]

pb = PyBoy(ROM, window="null", sound_emulated=False)
pb.set_emulation_speed(0)
with open(STATE, "rb") as f:
    pb.load_state(f)
pb.tick(4, render=True)
print(f"start {STATE}: D03B={pb.memory[D03B]} hp={pb.memory[HP]} lives={pb.memory[LIVES]}")

# un-pause (KDL's START pauses; the CONTINUE mash leaves the game paused)
pb.button_press("start")
pb.tick(6, render=True)
pb.button_release("start")
pb.tick(60, render=True)

# liveness proof: Kirby's x must actually change under input
xs = []
for _ in range(10):
    pb.button_press("right")
    pb.tick(45, render=True)
    pb.button_release("right")
    xs.append(int(pb.memory[X]))
controllable = len(set(xs)) > 1
print(f"LIVENESS: x_trace={xs} controllable={controllable} "
      f"hp={pb.memory[HP]} D03B={pb.memory[D03B]}", flush=True)
assert controllable, "not interactive"

rng = random.Random(11)
POOL = [["right"], ["right"], ["right", "a"], ["a"], ["up"], ["up", "right"], ["b"],
        ["down"], ["left"], ["right", "b"], []]
rows, shots = [], []
for i, t in enumerate(range(0, PLAY, 30)):
    act = rng.choice(POOL)
    for b in act:
        pb.button_press(b)
    pb.tick(30, render=True)
    for b in act:
        pb.button_release(b)
    m = pb.memory
    g = np.asarray(pb.screen.ndarray)[:, :, 0]
    rows.append({"t": t, "frame": int(pb.frame_count), "D03B": int(m[D03B]),
                 **{n: int(m[a]) for n, a in zip(NAMES, ELIM)},
                 "hp": int(m[HP]), "lives": int(m[LIVES]), "x": int(m[X]),
                 "scr_std": round(float(g.std()), 1)})
    if t % 900 == 0:
        shots.append((f"t{t} D={m[D03B]}", np.asarray(pb.screen.ndarray)[:, :, :3].copy()))

print(f"\n=== {len(rows)} samples over {PLAY} frames ===")
for key in ["D03B"] + NAMES:
    v = [r[key] for r in rows]
    tr = [(rows[i]["t"], v[i - 1], v[i]) for i in range(1, len(v)) if v[i] != v[i - 1]]
    print(f"  {key}: set={sorted(set(v))} min={min(v)} max={max(v)} "
          f"transitions={len(tr)} {tr[:6]}")
print(f"  PROOF-OF-LIFE  hp set={sorted({r['hp'] for r in rows})} "
      f"lives set={sorted({r['lives'] for r in rows})} "
      f"x distinct={len({r['x'] for r in rows})} "
      f"scr_std {min(r['scr_std'] for r in rows)}..{max(r['scr_std'] for r in rows)}")

with open(f"{OUT}/test1b_{TAG}.jsonl", "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
cols = 6
rws = (len(shots) + cols - 1) // cols
sheet = Image.new("RGB", (160 * cols, (144 + 12) * rws), "black")
d = ImageDraw.Draw(sheet)
for i, (tag, a) in enumerate(shots):
    x, y = 160 * (i % cols), (144 + 12) * (i // cols)
    sheet.paste(Image.fromarray(a), (x, y + 12))
    d.text((x + 2, y + 1), tag, fill="white")
sheet.save(f"{OUT}/test1b_{TAG}.png")
pb.stop(save=False)
print(f"log -> test1b_{TAG}.jsonl  montage -> test1b_{TAG}.png")
