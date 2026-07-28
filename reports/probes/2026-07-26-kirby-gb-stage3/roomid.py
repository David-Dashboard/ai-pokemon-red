"""Find a RAM byte that identifies the current room, so navigation has a real signal instead of a
guessed position byte. $0, offline PyBoy, no LLM.

Keep bytes that are IDENTICAL across states known to be in the same room and DIFFERENT across
states known to be in different rooms. Group membership is supplied on the command line as
`--group name=state1,state2` so the ground truth stays eyes-on and explicit.

  python roomid.py --group corridor=r15.state,r17.state --group water=r11.state,r12.state \
                   --group brick=r14.state
"""
from __future__ import annotations

import argparse
import os
from collections import defaultdict

PRIMARY = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red"
ROM = PRIMARY + "/roms/Kirby's Dream Land (USA, Europe).gb"
OUT = ("C:/Users/Succe/AppData/Local/Temp/claude/"
       "E--AI-Personas-10-pokemon-and-chess-and-office/"
       "671b9313-5a35-40f5-a26e-315d9f7e8f28/scratchpad/kirby3")
LO, HI = 0xC000, 0xE000


def wram(state_path):
    from pyboy import PyBoy
    pb = PyBoy(ROM, window="null", sound_emulated=False)
    pb.set_emulation_speed(0)
    with open(state_path, "rb") as f:
        pb.load_state(f)
    pb.tick(1, render=False)
    data = [pb.memory[a] for a in range(LO, HI)]
    pb.stop(save=False)
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", action="append", required=True,
                    help="name=state1,state2,... (states are paths or names under OUT)")
    args = ap.parse_args()

    groups = {}
    for spec in args.group:
        name, _, states = spec.partition("=")
        paths = []
        for s in states.split(","):
            s = s.strip()
            paths.append(s if os.path.exists(s) else os.path.join(OUT, s))
        groups[name] = [wram(p) for p in paths]
        print(f"loaded group {name}: {len(paths)} state(s)")

    survivors = []
    for i in range(HI - LO):
        per_group = {}
        ok = True
        for name, dumps in groups.items():
            vals = {d[i] for d in dumps}
            if len(vals) != 1:          # must be stable inside a room
                ok = False
                break
            per_group[name] = vals.pop()
        if not ok:
            continue
        if len(set(per_group.values())) != len(per_group):   # must differ between rooms
            continue
        survivors.append((LO + i, per_group))

    print(f"\n{len(survivors)} byte(s) stable within each room and distinct across rooms:")
    by_sig = defaultdict(list)
    for addr, per_group in survivors:
        by_sig[tuple(sorted(per_group.items()))].append(addr)
    for sig, addrs in sorted(by_sig.items(), key=lambda kv: -len(kv[1])):
        shown = ", ".join(f"0x{a:04X}" for a in addrs[:14])
        more = f" (+{len(addrs) - 14} more)" if len(addrs) > 14 else ""
        print(f"  {dict(sig)}  <- {shown}{more}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
