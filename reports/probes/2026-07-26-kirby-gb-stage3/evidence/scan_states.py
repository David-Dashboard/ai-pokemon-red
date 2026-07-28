"""Scan every savestate in the kirby3 scratchpad: read 0xD03B + the 4 eliminated candidates.

$0, offline, PyBoy-only. Read-only w.r.t. the savestate dir.
"""
import glob
import os
import sys

import numpy as np
from pyboy import PyBoy

ROM = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/roms/Kirby's Dream Land (USA, Europe).gb"
SRC = "C:/Users/Succe/AppData/Local/Temp/claude/E--AI-Personas-10-pokemon-and-chess-and-office/671b9313-5a35-40f5-a26e-315d9f7e8f28/scratchpad/kirby3"

D03B = 0xD03B
ELIM = (0xD19F, 0xD3A9, 0xD3BA, 0xD3CD)
HP, LIVES = 0xD086, 0xD089

pb = PyBoy(ROM, window="null", sound_emulated=False)
pb.set_emulation_speed(0)

rows = []
paths = sorted(glob.glob(os.path.join(SRC, "*.state")))
for p in paths:
    try:
        with open(p, "rb") as f:
            pb.load_state(f)
    except Exception as e:  # noqa: BLE001
        rows.append((os.path.basename(p), "ERR", str(e)[:40], 0, 0, 0, 0, 0, 0))
        continue
    m = pb.memory
    scr = np.asarray(pb.screen.ndarray)
    uniq = len(np.unique(scr[:, :, 0]))
    rows.append((os.path.basename(p), m[D03B], m[HP], m[LIVES],
                 m[ELIM[0]], m[ELIM[1]], m[ELIM[2]], m[ELIM[3]], uniq))

pb.stop(save=False)

# group by d03b value
from collections import defaultdict
g = defaultdict(list)
for r in rows:
    g[r[1]].append(r)

print("d03b_value -> count")
for k in sorted(g, key=lambda x: str(x)):
    print(f"  {k!r:>6} : {len(g[k])}")

print("\n=== states with d03b >= 2 (or non-int) ===")
for k in sorted(g, key=lambda x: str(x)):
    if isinstance(k, int) and k < 2:
        continue
    for r in g[k][:400]:
        print(f"  {r[0]:<45} d03b={r[1]!r:<5} hp={r[2]:<4} lives={r[3]:<4} "
              f"elim={r[4]},{r[5]},{r[6]},{r[7]} screen_uniq={r[8]}")

print(f"\ntotal scanned: {len(rows)}")
