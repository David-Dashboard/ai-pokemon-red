"""Uniqueness sweep: replay a driving trajectory deterministically, snapshot the ENTIRE 4MB
NDS main-RAM region at a list of ANCHOR FRAMES, and count how many addresses in the whole
region reproduce a given expected value pattern exactly.

This is the "is my candidate actually distinguished, or do 2,000 bytes do the same thing?"
check. It reports the exact number, and lists every matching address.

Trajectory is either --coast (no input, matches sweep_pass1/pass2) or --policies
<log.json from beam_drive.py> + --burst, replayed frame-for-frame.

Usage:
  python uniqueness.py --coast --anchors 3000,4050,4110,8250,8310,11000,20000,30000 \
      --pattern 1,1,2,2,3,3,3,3 --out uniq_cpu1
"""
from __future__ import annotations
import argparse, json, os, sys
import numpy as np

ASSETS = os.environ.get("MKDS_ASSETS", r"E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red")
ROM = os.path.join(ASSETS, "roms", "nds", "Mario Kart DS (USA) (En,Fr,De,Es,It).nds")
STATE = os.path.join(ASSETS, "runs", "nds3d_probe", "mkds_race_start.state")
RAM_BASE, RAM_SIZE = 0x02000000, 0x00400000

POLICIES = {
    "straight": lambda f: ("a",), "left": lambda f: ("a", "left"),
    "right": lambda f: ("a", "right"),
    "pleft": lambda f: ("a", "left") if f % 2 == 0 else ("a",),
    "pright": lambda f: ("a", "right") if f % 2 == 0 else ("a",),
    "qleft": lambda f: ("a", "left") if f % 4 == 0 else ("a",),
    "qright": lambda f: ("a", "right") if f % 4 == 0 else ("a",),
    "lead_left": lambda f: ("a", "left") if f < 45 else ("a",),
    "lead_right": lambda f: ("a", "right") if f < 45 else ("a",),
    "drift_left": lambda f: ("a", "r", "left"), "drift_right": lambda f: ("a", "r", "right"),
    "rev": lambda f: ("b",), "rev_left": lambda f: ("b", "left"),
    "rev_right": lambda f: ("b", "right"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coast", action="store_true")
    ap.add_argument("--policies", default=None, help="beam_drive log.json")
    ap.add_argument("--burst", type=int, default=150)
    ap.add_argument("--anchors", required=True)
    ap.add_argument("--pattern", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    anchors = [int(x) for x in args.anchors.split(",")]
    pattern = [int(x) for x in args.pattern.split(",")]
    assert len(anchors) == len(pattern)

    sys.path.insert(0, ASSETS)
    from core.nds_emulator import DeSmuMEEmulator
    from desmume.controls import Keys, keymask

    emu = DeSmuMEEmulator(ROM, headless=True)
    emu.load_state(STATE)
    raw = emu._emu.memory.unsigned

    if args.coast:
        seq = None
    else:
        seq = [e["policy"] for e in json.load(open(args.policies))]

    held = set()

    def set_keys(want):
        nonlocal held
        for k in want - held:
            emu._emu.input.keypad_add_key(keymask(getattr(Keys, "KEY_" + k.upper())))
        for k in held - want:
            emu._emu.input.keypad_rm_key(keymask(getattr(Keys, "KEY_" + k.upper())))
        held = want

    snaps, mask = {}, np.ones(RAM_SIZE, dtype=bool)
    maxf = max(anchors)
    f = 0
    shots = os.path.join(args.out, "shots"); os.makedirs(shots, exist_ok=True)

    def maybe_snap():
        if f in anchors:
            cur = np.frombuffer(bytes(raw[RAM_BASE:RAM_BASE + RAM_SIZE]), dtype=np.uint8)
            snaps[f] = cur
            np.logical_and(mask, cur == pattern[anchors.index(f)], out=mask)
            emu.save_screen(os.path.join(shots, f"anchor_f{f:06d}.png"))
            print(f"anchor f={f}: survivors so far = {int(mask.sum())}", flush=True)

    maybe_snap()
    if seq is None:
        while f < maxf:
            set_keys(set()); emu.tick(1); f += 1
            maybe_snap()
    else:
        for pol in seq:
            fn = POLICIES[pol]
            for i in range(args.burst):
                set_keys(set(fn(i))); emu.tick(1); f += 1
                maybe_snap()
            if f >= maxf:
                break

    idx = np.nonzero(mask)[0]
    print(f"\nUNIQUENESS: {len(idx)} of {RAM_SIZE} addresses match pattern "
          f"{pattern} at frames {anchors}")
    for i in idx.tolist():
        print(f"   {RAM_BASE + i:#010x}")
    json.dump({"anchors": anchors, "pattern": pattern,
               "matches": [RAM_BASE + int(i) for i in idx]},
              open(os.path.join(args.out, "result.json"), "w"), indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
