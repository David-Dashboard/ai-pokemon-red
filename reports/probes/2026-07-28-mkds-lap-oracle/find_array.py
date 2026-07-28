"""Locate the 8-racer lap array in an arbitrary race state by its STRUCTURAL signature, then
confirm the winner causally by poking it and watching the LAP numerator glyph.

Signature: 8 bytes at stride 0x8C that all read the same plausible lap value, whose immediate
stride-neighbours one step outside the array do NOT (so the run is exactly 8 long).
Confirmation: poke candidate slot 0 -> the on-screen LAP numerator must change; poke candidate
slot 1 -> it must not.
"""
from __future__ import annotations
import os, sys
import numpy as np

ASSETS = os.environ.get("MKDS_ASSETS",
                        r"E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red")
ROM = os.path.join(ASSETS, "roms", "nds", "Mario Kart DS (USA) (En,Fr,De,Es,It).nds")
RAM_BASE, RAM_SIZE, STRIDE = 0x02000000, 0x00400000, 0x8C
NUM_BOX = (slice(3, 21), slice(212, 228))

sys.path.insert(0, ASSETS)
from core.nds_emulator import DeSmuMEEmulator  # noqa: E402

state = sys.argv[1]
lapval = int(sys.argv[2]) if len(sys.argv) > 2 else 1
emu = DeSmuMEEmulator(ROM, headless=True)
emu.load_state(state)
mem = emu._emu.memory
raw = mem.unsigned
ram = np.frombuffer(bytes(raw[RAM_BASE:RAM_BASE + RAM_SIZE]), dtype=np.uint8)

n = RAM_SIZE - 9 * STRIDE
ok = np.ones(n, dtype=bool)
for k in range(8):
    ok &= ram[k * STRIDE: k * STRIDE + n] == lapval
# require the run to be exactly 8 long, not part of a longer uniform block
ok &= ram[8 * STRIDE: 8 * STRIDE + n] != lapval
cands = np.nonzero(ok)[0]
print(f"structural candidates (8x stride-0x8C == {lapval}, 9th != ): {len(cands)}")
for i in cands.tolist()[:40]:
    print(f"   {RAM_BASE + i:#010x}")

tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_find.state")
emu.save_state(tmp)


def numerator():
    return emu.screen_ndarray("top")[NUM_BOX[0], NUM_BOX[1]].copy()


def capture(addr, val):
    emu.load_state(tmp)
    if addr is not None:
        mem.write_byte(addr, val)
    emu.tick(4)
    return numerator()


base = capture(None, 0)
print("\ncausal confirmation (poke slot0 -> HUD numerator must change; slot1 -> must not):")
winners = []
for i in cands.tolist():
    a = RAM_BASE + i
    changed = not np.array_equal(base, capture(a, lapval + 1))
    ctrl_same = np.array_equal(base, capture(a + STRIDE, lapval + 1))
    if changed and ctrl_same:
        winners.append(a)
        print(f"   {a:#010x}  CONFIRMED (slot0 poke changes HUD, slot1 poke does not)")
    elif changed:
        print(f"   {a:#010x}  slot0 poke changes HUD but so does slot1 -- rejected")
print(f"\nCONFIRMED lap-array base(s): {[hex(w) for w in winners]}")
os.remove(tmp)
