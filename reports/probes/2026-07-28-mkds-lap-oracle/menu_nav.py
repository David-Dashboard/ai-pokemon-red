"""Chainable menu navigator, used to re-enter a race from SELECT MODE after quitting, so the
lap array's base address can be checked against a genuinely RE-INITIALISED race.

Steps: button names (a/b/x/y/start/up/down/left/right), 'tNNN,MMM' for a stylus tap at bottom-
screen (x,y), or a bare integer for "tick N frames". Saves a screenshot after every step and
prints the 8 lap slots each time.

Usage: python menu_nav.py --in <state> --out-state <state> --tag <t> a 120 t128,60 ...
"""
import argparse, os, sys

ASSETS = os.environ.get("MKDS_ASSETS",
                        r"E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red")
ROM = os.path.join(ASSETS, "roms", "nds", "Mario Kart DS (USA) (En,Fr,De,Es,It).nds")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "restart")
LAP0, STRIDE = 0x0236A7F2, 0x8C

ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="inp", required=True)
ap.add_argument("--out-state", required=True)
ap.add_argument("--tag", required=True)
ap.add_argument("steps", nargs="*")
args = ap.parse_args()

sys.path.insert(0, ASSETS)
from core.nds_emulator import DeSmuMEEmulator  # noqa: E402

os.makedirs(OUT, exist_ok=True)
emu = DeSmuMEEmulator(ROM, headless=True)
emu.load_state(args.inp)
raw = emu._emu.memory.unsigned
for i, s in enumerate(args.steps, 1):
    if s.isdigit():
        emu.tick(int(s))
    elif s.startswith("t"):
        x, y = (int(v) for v in s[1:].split(","))
        emu.touch(x, y); emu.tick(8); emu.touch_release(); emu.tick(50)
    else:
        emu.press(s, hold_frames=6, settle_frames=45)
    emu.save_screen(os.path.join(OUT, f"{args.tag}_{i:02d}_{s.replace(',', '-')}.png"))
    print(f"{args.tag} {i:02d} {s}: slots={[raw[LAP0 + k * STRIDE] for k in range(8)]}", flush=True)
emu.save_state(args.out_state)
