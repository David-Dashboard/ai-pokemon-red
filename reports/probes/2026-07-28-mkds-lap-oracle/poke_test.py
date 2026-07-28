"""Identification test for the PLAYER's slot in the per-racer lap array.

Premise under test (stated explicitly, per the hunt's own rule): the lap-number field lives at
LAP0 + k*0x8C for k=0..7, and k=0 (0x0236A7F2) is the human player's slot. That was inferred by
ELIMINATION (the other 7 ticked 1->2->3 as CPUs lapped; slot 0 stayed 1 because the player never
lapped). Elimination is not observation, so this script tests it directly:

  poke a value into slot 0's field  -> does the on-screen "LAP n/3" HUD follow?
  poke the same value into slot 1's -> does the player's HUD stay put? (CONTROL)

A positive on the first and a negative on the second identifies slot 0 as the rendered player.
A negative on the first is INCONCLUSIVE (the HUD could be drawn from a cached copy), not a
disproof -- recorded as such.
"""
import os, sys

ASSETS = os.environ.get("MKDS_ASSETS", r"E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red")
sys.path.insert(0, ASSETS)
ROM = os.path.join(ASSETS, "roms", "nds", "Mario Kart DS (USA) (En,Fr,De,Es,It).nds")
STATE = os.path.join(ASSETS, "runs", "nds3d_probe", "mkds_race_start.state")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poke")
os.makedirs(OUT, exist_ok=True)

LAP0 = 0x0236A7F2          # slot 0, hypothesised player
LAP1 = LAP0 + 0x8C         # slot 1, a CPU (ticked 1->2->3 in the coast run)

from core.nds_emulator import DeSmuMEEmulator
from PIL import Image

emu = DeSmuMEEmulator(ROM, headless=True)
emu.load_state(STATE)
mem = emu._emu.memory
emu.tick(900)   # let the race get going and the HUD render


def shot(tag):
    top = emu.screen_ndarray("top")[2:22, 190:252]
    Image.fromarray(top, "RGB").resize((62 * 8, 20 * 8), Image.NEAREST).save(
        os.path.join(OUT, f"{tag}.png"))
    print(f"{tag}: lap0={mem.unsigned[LAP0]} lap1={mem.unsigned[LAP1]}", flush=True)


shot("00_baseline")
for v in (2, 3):
    mem.write_byte(LAP0, v)
    emu.tick(4)
    shot(f"01_poke_slot0_{v}")

mem.write_byte(LAP0, 1); emu.tick(4)
shot("02_restored_slot0_1")

mem.write_byte(LAP1, 3); emu.tick(4)
shot("03_control_poke_slot1_3")
