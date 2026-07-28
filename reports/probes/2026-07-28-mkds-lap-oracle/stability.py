"""Address-stability check: does the 8-racer lap array sit at the SAME base in a race entered
independently of the banked mkds_race_start.state?

The whole hunt was measured from one savestate. If this region is dynamically allocated, the
base can move between races and a hard-coded oracle address would silently read garbage. This
loads other savestates from runs/nds3d_probe/mkds_vision/ (menu/track-intro states captured by
an earlier session), advances into the race, and reports the 8 slot values.

Expected at a standing start: all eight slots read 1 (every racer on LAP 1/3).

Usage: python stability.py <state-path> [frames]
"""
from __future__ import annotations
import os, sys

ASSETS = os.environ.get("MKDS_ASSETS",
                        r"E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red")
ROM = os.path.join(ASSETS, "roms", "nds", "Mario Kart DS (USA) (En,Fr,De,Es,It).nds")
LAP0, STRIDE = 0x0236A7F2, 0x8C

sys.path.insert(0, ASSETS)
from core.nds_emulator import DeSmuMEEmulator  # noqa: E402

state = sys.argv[1]
frames = int(sys.argv[2]) if len(sys.argv) > 2 else 1200
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stability")
os.makedirs(out, exist_ok=True)
tag = os.path.splitext(os.path.basename(state))[0]

emu = DeSmuMEEmulator(ROM, headless=True)
emu.load_state(state)
raw = emu._emu.memory.unsigned
for chunk in range(0, frames, 300):
    emu.tick(min(300, frames - chunk))
    vals = [raw[LAP0 + k * STRIDE] for k in range(8)]
    print(f"{tag} f={chunk + 300:5d}  slots={vals}", flush=True)
emu.save_screen(os.path.join(out, f"{tag}_f{frames}.png"))
print(f"{tag}: FINAL slots = {[raw[LAP0 + k * STRIDE] for k in range(8)]}")
