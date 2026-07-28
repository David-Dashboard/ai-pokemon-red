"""Locate the 8-racer lap array in a PRE-FIRST-LAP race state by its STRUCTURAL signature, then
confirm the winner causally by poking it and watching the LAP numerator glyph.

SCOPE LIMIT -- read this before reusing the script. The structural scan requires all eight
slots to read the SAME value `lapval` (see the loop below). That holds only while every racer
is still on the same lap, i.e. before ANY racer completes lap 1. Once the field spreads across
laps the scan returns 0 candidates and the script exits non-zero. It is a start-of-race
locator, NOT a general "find it in any race state" tool. Extending it to mid-race would mean
dropping the all-equal constraint and leaning much harder on the causal stage.

Signature: 8 bytes at stride 0x8C that all read `lapval`, with the 9th at that stride NOT
equal to it (so the run is exactly 8 long, not part of a longer uniform block).
Confirmation: poke candidate slot 0 -> the on-screen LAP numerator must change; poke candidate
slot 1 -> it must not.

Exit code: 0 only when EXACTLY ONE candidate is causally confirmed. 2 = none confirmed,
3 = ambiguous (>1). Callers must check the exit code rather than parse stdout: DeSmuME writes
its own banner to the same stream from C and has been observed fusing mid-line with this
script's output (`DeSmuME version: 0.9.12 sstructural candidates ...`).
"""
from __future__ import annotations
import os, sys, tempfile
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

# ~11 MB scratch savestate. Keep it OUT of the committed probe dir, and remove it on every
# path -- py-desmume has been seen dying silently under exactly this poke + save/load-state +
# screen-read pattern (see the v3 report §8), so a success-only cleanup leaks the file.
_fd, tmp = tempfile.mkstemp(prefix="mkds_find_", suffix=".state")
os.close(_fd)
emu.save_state(tmp)


def numerator():
    return emu.screen_ndarray("top")[NUM_BOX[0], NUM_BOX[1]].copy()


def capture(addr, val):
    emu.load_state(tmp)
    if addr is not None:
        mem.write_byte(addr, val)
    emu.tick(4)
    return numerator()


winners = []
try:
    base = capture(None, 0)
    print("\ncausal confirmation (poke slot0 -> HUD numerator must change; slot1 -> must not):")
    for i in cands.tolist():
        a = RAM_BASE + i
        changed = not np.array_equal(base, capture(a, lapval + 1))
        ctrl_same = np.array_equal(base, capture(a + STRIDE, lapval + 1))
        if changed and ctrl_same:
            winners.append(a)
            print(f"   {a:#010x}  CONFIRMED (slot0 poke changes HUD, slot1 poke does not)")
        elif changed:
            print(f"   {a:#010x}  slot0 poke changes HUD but so does slot1 -- rejected")
finally:
    if os.path.exists(tmp):
        os.remove(tmp)

print(f"\nCONFIRMED lap-array base(s): {[hex(w) for w in winners]}")
if len(winners) == 1:
    raise SystemExit(0)
if not winners:
    print("FAIL: no candidate confirmed. If any racer has already completed a lap, this "
          "script's all-slots-equal scan cannot work -- see the SCOPE LIMIT in the docstring.")
    raise SystemExit(2)
print(f"FAIL: ambiguous -- {len(winners)} candidates confirmed; expected exactly 1.")
raise SystemExit(3)
