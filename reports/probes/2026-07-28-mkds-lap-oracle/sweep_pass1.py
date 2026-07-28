"""Pass 1: full 4MB NDS main-RAM sweep for MONOTONE SMALL COUNTERS during a long MKDS race.

Runs the banked race-start savestate forward under a fixed policy, sampling the ENTIRE
main-RAM region (0x02000000-0x023FFFFF) every --sample-every frames, and keeping incremental
per-address statistics only (no 4MB-per-sample storage):
    first, last, min, max, n_changes, monotone-non-decreasing, max single step

The lap counter must be: monotone non-decreasing, few changes, small span. Everything that
survives that filter is reported, so the UNIQUENESS COUNT is a real number, not a claim.

Usage: python sweep_pass1.py --frames 30000 --sample-every 300 --policy coast --out <dir>
"""
from __future__ import annotations

import argparse, json, os, sys, time

import numpy as np

ASSETS = os.environ.get("MKDS_ASSETS", r"E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red")
ROM = os.path.join(ASSETS, "roms", "nds", "Mario Kart DS (USA) (En,Fr,De,Es,It).nds")
STATE = os.path.join(ASSETS, "runs", "nds3d_probe", "mkds_race_start.state")
RAM_BASE = 0x02000000
RAM_SIZE = 0x00400000


def policy_fn(name):
    if name == "coast":
        return lambda f: ()
    if name == "accel":
        return lambda f: ("a",)
    raise ValueError(name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=30000)
    ap.add_argument("--sample-every", type=int, default=300)
    ap.add_argument("--policy", default="coast")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    shots = os.path.join(args.out, "shots"); os.makedirs(shots, exist_ok=True)

    sys.path.insert(0, ASSETS)
    from core.nds_emulator import DeSmuMEEmulator
    from desmume.controls import Keys, keymask

    emu = DeSmuMEEmulator(ROM, headless=True)
    emu.load_state(STATE)
    raw = emu._emu.memory.unsigned
    pol = policy_fn(args.policy)

    def snap():
        return np.frombuffer(bytes(raw[RAM_BASE:RAM_BASE + RAM_SIZE]), dtype=np.uint8)

    first = snap().copy()
    prev = first.copy()
    vmin = first.copy(); vmax = first.copy()
    nchg = np.zeros(RAM_SIZE, dtype=np.uint16)
    nondec = np.ones(RAM_SIZE, dtype=bool)     # never observed to decrease
    maxstep = np.zeros(RAM_SIZE, dtype=np.uint8)
    samples = [(0, "start")]

    t0 = time.time()
    held = set()
    for f in range(1, args.frames + 1):
        want = set(pol(f))
        for b in want - held:
            emu._emu.input.keypad_add_key(keymask(getattr(Keys, "KEY_" + b.upper())))
        for b in held - want:
            emu._emu.input.keypad_rm_key(keymask(getattr(Keys, "KEY_" + b.upper())))
        held = want
        emu.tick(1)
        if f % args.sample_every == 0:
            cur = snap()
            diff = cur != prev
            nchg[diff] += 1
            dec = cur < prev
            nondec[dec] = False
            step = np.where(cur >= prev, cur - prev, 0).astype(np.uint8)
            np.maximum(maxstep, step, out=maxstep)
            np.minimum(vmin, cur, out=vmin)
            np.maximum(vmax, cur, out=vmax)
            prev = cur.copy()
            samples.append((f, "s"))
            emu.save_screen(os.path.join(shots, f"f{f:06d}.png"))
            el = time.time() - t0
            print(f"f={f:6d} t={el:6.1f}s  eta={el/f*(args.frames-f):5.0f}s  "
                  f"ck90={raw[0x022C8090]} ck94={raw[0x022C8094]}", flush=True)

    last = prev
    np.savez_compressed(os.path.join(args.out, "stats.npz"),
                        first=first, last=last, vmin=vmin, vmax=vmax,
                        nchg=nchg, nondec=nondec, maxstep=maxstep)
    print(f"saved stats; {time.time()-t0:.0f}s total, {len(samples)} samples")

    # --- report tiers -------------------------------------------------------
    span = vmax.astype(np.int16) - vmin.astype(np.int16)
    grew = last.astype(np.int16) - first.astype(np.int16)

    def tier(name, mask):
        idx = np.nonzero(mask)[0]
        print(f"\n### {name}: {len(idx)} addresses")
        return idx

    # A counter that ticked >=2 times, never decreased, always by exactly +1, span<=8
    m = nondec & (nchg >= 2) & (nchg <= 10) & (maxstep == 1) & (span <= 8) & (grew >= 2)
    idx = tier("TIER-A  strict +1-step monotone counter (>=2 ticks, span<=8)", m)
    out = []
    for i in idx.tolist():
        out.append({"addr": RAM_BASE + i, "first": int(first[i]), "last": int(last[i]),
                    "min": int(vmin[i]), "max": int(vmax[i]), "nchg": int(nchg[i])})
        print(f"  {RAM_BASE+i:#010x}  {first[i]}->{last[i]}  min={vmin[i]} max={vmax[i]} nchg={nchg[i]}")

    m2 = nondec & (nchg >= 2) & (nchg <= 20) & (maxstep <= 3) & (span <= 12) & (grew >= 2)
    idx2 = tier("TIER-B  loose monotone counter (step<=3, span<=12)", m2)
    for i in idx2.tolist()[:400]:
        print(f"  {RAM_BASE+i:#010x}  {first[i]}->{last[i]}  min={vmin[i]} max={vmax[i]} nchg={nchg[i]}")

    json.dump(out, open(os.path.join(args.out, "tier_a.json"), "w"), indent=1)
    json.dump([{"addr": RAM_BASE + int(i), "first": int(first[i]), "last": int(last[i]),
                "min": int(vmin[i]), "max": int(vmax[i]), "nchg": int(nchg[i])} for i in idx2.tolist()],
              open(os.path.join(args.out, "tier_b.json"), "w"), indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
