"""Machine-checked version of the identification evidence for the MKDS lap byte.

Turns the eyeballed poke test into measured assertions:
  1. 0x0236A7F2 reads 1 on a fresh load of the banked race-start savestate.
  2. It survives a save_state -> load_state round trip unchanged.
  3. Poking it to 2 / 3 CHANGES the LAP-numerator glyph box on the top screen, and poking it
     back to 1 restores the ORIGINAL numerator pixels exactly (byte-identical crop).
  4. CONTROL: poking CPU slot 1's byte (0x0236A87E) leaves the player's numerator box
     byte-identical -- so the HUD is reading slot 0 specifically, not "some lap byte".

Numerator box is the LAP digit only (left of the '/'), so a change there cannot be confused
with the constant '/3' denominator.
"""
from __future__ import annotations
import os, sys
import numpy as np

ASSETS = os.environ.get("MKDS_ASSETS",
                        r"E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red")
ROM = os.path.join(ASSETS, "roms", "nds", "Mario Kart DS (USA) (En,Fr,De,Es,It).nds")
STATE = os.path.join(ASSETS, "runs", "nds3d_probe", "mkds_race_start.state")

LAP_P = 0x0236A7F2          # player  (slot 0)
LAP_C = LAP_P + 0x8C        # CPU     (slot 1)
NUM_BOX = (slice(3, 21), slice(212, 228))   # top-screen rows/cols of the LAP numerator digit

sys.path.insert(0, ASSETS)
from core.nds_emulator import DeSmuMEEmulator  # noqa: E402

emu = DeSmuMEEmulator(ROM, headless=True)
emu.load_state(STATE)
mem = emu._emu.memory
ok = True


def chk(cond, msg):
    global ok
    ok = ok and bool(cond)
    print(("PASS  " if cond else "FAIL  ") + msg, flush=True)


def num():
    return emu.screen_ndarray("top")[NUM_BOX[0], NUM_BOX[1]].copy()


chk(mem.unsigned[LAP_P] == 1, f"fresh load: 0x{LAP_P:08X} == 1 (got {mem.unsigned[LAP_P]})")

emu.tick(900)
before = mem.unsigned[LAP_P]
tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_verify.state")
emu.save_state(tmp); emu.load_state(tmp)
chk(mem.unsigned[LAP_P] == before, f"save/load round trip preserves value ({before})")

# The numerator box overlays the live 3D scene, so two captures taken at different frames
# differ in the BACKGROUND regardless of the glyph. Re-run every poke from the SAME savestate
# for the same number of frames, so the background is identical and a byte comparison is
# actually about the glyph.
def capture(addr, value):
    emu.load_state(tmp)
    if addr is not None:
        mem.write_byte(addr, value)
    emu.tick(4)
    return num()


base = capture(None, 0)
n2 = capture(LAP_P, 2)
n3 = capture(LAP_P, 3)
n1 = capture(LAP_P, 1)

chk(not np.array_equal(base, n2), "poke slot0=2 changes the LAP numerator glyph")
chk(not np.array_equal(n2, n3), "poke slot0=3 changes it again (distinct from the =2 glyph)")
chk(np.array_equal(base, n1), "poke slot0 back to 1 reproduces the untouched numerator exactly")

nc = capture(LAP_C, 3)
chk(np.array_equal(base, nc),
    "CONTROL: poking CPU slot1=3 leaves the player's numerator byte-identical")

os.remove(tmp)
print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
raise SystemExit(0 if ok else 1)
