"""Fresh-boot baseline: boot the ROM cold, punch through the title, play into Stage 1 Green Greens,
and log 0xD03B + the four eliminated candidates the whole way. No RAM writes at all."""
import numpy as np
from PIL import Image, ImageDraw
from pyboy import PyBoy

ROM = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/roms/Kirby's Dream Land (USA, Europe).gb"
OUT = "C:/Users/Succe/AppData/Local/Temp/claude/E--AI-Personas-10-pokemon-and-chess-and-office/671b9313-5a35-40f5-a26e-315d9f7e8f28/scratchpad/stage3check"

D03B = 0xD03B
ELIM = [0xD19F, 0xD3A9, 0xD3BA, 0xD3CD]
HP, LIVES = 0xD086, 0xD089

pb = PyBoy(ROM, window="null", sound_emulated=False)
pb.set_emulation_speed(0)

shots, prev = [], None


def obs(tag, t):
    global prev
    m = pb.memory
    cur = (int(m[D03B]), [int(m[a]) for a in ELIM], int(m[HP]), int(m[LIVES]))
    if cur != prev:
        print(f"  [{tag}] f={t:>6} D03B={cur[0]} elim={cur[1]} hp={cur[2]} lives={cur[3]}",
              flush=True)
        prev = cur


print("=== cold boot, no input ===")
for t in range(0, 900, 10):
    pb.tick(10, render=True)
    obs("boot", pb.frame_count)
shots.append(("after boot idle", np.asarray(pb.screen.ndarray)[:, :, :3].copy()))

print("=== press START to leave title ===")
for i in range(30):
    pb.button_press("start")
    pb.tick(6, render=True)
    pb.button_release("start")
    pb.tick(20, render=True)
    obs("start", pb.frame_count)
shots.append(("after START", np.asarray(pb.screen.ndarray)[:, :, :3].copy()))

print("=== walk right into Green Greens (hold right, occasional a) ===")
for i in range(220):
    acts = ["right"] if i % 5 else ["right", "a"]
    for b in acts:
        pb.button_press(b)
    pb.tick(14, render=True)
    for b in acts:
        pb.button_release(b)
    obs("play", pb.frame_count)
    if i % 40 == 0:
        shots.append((f"play {i}", np.asarray(pb.screen.ndarray)[:, :, :3].copy()))
shots.append(("end", np.asarray(pb.screen.ndarray)[:, :, :3].copy()))

m = pb.memory
print(f"\nFINAL: D03B={m[D03B]} elim={[int(m[a]) for a in ELIM]} "
      f"hp={m[HP]} lives={m[LIVES]}")
with open(f"{OUT}/fresh_greengreens.state", "wb") as f:
    pb.save_state(f)

cols = 5
rows = (len(shots) + cols - 1) // cols
sheet = Image.new("RGB", (160 * cols, (144 + 12) * rows), "black")
d = ImageDraw.Draw(sheet)
for i, (tag, a) in enumerate(shots):
    x, y = 160 * (i % cols), (144 + 12) * (i // cols)
    sheet.paste(Image.fromarray(a), (x, y + 12))
    d.text((x + 2, y + 1), tag, fill="white")
sheet.save(f"{OUT}/freshboot.png")
pb.stop(save=False)
print("montage ->", f"{OUT}/freshboot.png")
