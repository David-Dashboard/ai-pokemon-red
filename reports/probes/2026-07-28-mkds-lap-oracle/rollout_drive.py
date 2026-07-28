"""Random-restart rollout driver: get the PLAYER kart around a real lap of Figure-8 Circuit.

Same purpose and same anti-circularity rule as beam_drive.py -- THE LAP BYTE IS READ BUT NEVER
SCORED ON. The objective is built only from the player checkpoint counter 0x022C8090/0x022C8094
(established by the 2026-07-23 hunt) and the per-racer key-checkpoint bitmask. A lap-byte tick
therefore remains an independent observation, not the search's own target.

Each commit: sample N random steering programs (accel always held, random segments of
straight/left/right/pulse), roll each out for --rollout frames from the current savestate, keep
the best-scoring, commit it. One DeSmuME instance, repeated load_state() for backtracking.
"""
from __future__ import annotations
import argparse, json, os, random, sys

ASSETS = os.environ.get("MKDS_ASSETS", r"E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red")
ROM = os.path.join(ASSETS, "roms", "nds", "Mario Kart DS (USA) (En,Fr,De,Es,It).nds")
STATE = os.path.join(ASSETS, "runs", "nds3d_probe", "mkds_race_start.state")

CK90, CK94 = 0x022C8090, 0x022C8094
LAP_P, KCP_P = 0x0236A7F2, 0x0236A806
STEERS = ["none", "left", "right", "pleft", "pright", "hleft", "hright"]


def seg_keys(steer, i):
    if steer == "none":   return ("a",)
    if steer == "left":   return ("a", "left")
    if steer == "right":  return ("a", "right")
    if steer == "pleft":  return ("a", "left") if i % 2 == 0 else ("a",)
    if steer == "pright": return ("a", "right") if i % 2 == 0 else ("a",)
    if steer == "hleft":  return ("a", "left") if i % 4 == 0 else ("a",)
    if steer == "hright": return ("a", "right") if i % 4 == 0 else ("a",)
    raise ValueError(steer)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commits", type=int, default=40)
    ap.add_argument("--rollout", type=int, default=900)
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    os.makedirs(args.out, exist_ok=True)
    shots = os.path.join(args.out, "shots"); os.makedirs(shots, exist_ok=True)
    cur = os.path.join(args.out, "cur.state")

    sys.path.insert(0, ASSETS)
    from core.nds_emulator import DeSmuMEEmulator
    from desmume.controls import Keys, keymask

    emu = DeSmuMEEmulator(ROM, headless=True)
    emu.load_state(STATE)
    emu.save_state(cur)
    raw = emu._emu.memory.unsigned
    held = set()

    def keys(want):
        nonlocal held
        want = set(want)
        for k in want - held:
            emu._emu.input.keypad_add_key(keymask(getattr(Keys, "KEY_" + k.upper())))
        for k in held - want:
            emu._emu.input.keypad_rm_key(keymask(getattr(Keys, "KEY_" + k.upper())))
        held = want

    def rollout(prog):
        """prog = [(steer, nframes), ...]; returns best score seen + final state dict."""
        best = -1
        for steer, n in prog:
            for i in range(n):
                keys(seg_keys(steer, i)); emu.tick(1)
            s = raw[CK94] * 1_000_000 + raw[CK90] * 10_000 + bin(raw[KCP_P]).count("1") * 500
            best = max(best, s)
        keys(())
        return best, dict(ck90=raw[CK90], ck94=raw[CK94], lap=raw[LAP_P],
                          kcp=bin(raw[KCP_P]).count("1"))

    log, prev_lap = [], raw[LAP_P]
    total = 0
    for c in range(args.commits):
        cands = []
        for k in range(args.n):
            prog = ([[("none", args.rollout)]] if k == 0 else [])
            if not prog:
                prog, left = [], args.rollout
                while left > 0:
                    n = min(left, rng.choice([60, 90, 120, 180]))
                    prog.append((rng.choice(STEERS), n)); left -= n
            else:
                prog = prog[0]
            emu.load_state(cur)
            sc, st = rollout(prog)
            cands.append((sc, k, prog, st))
        cands.sort(reverse=True, key=lambda x: (x[0], -x[1]))
        sc, k, prog, st = cands[0]
        emu.load_state(cur)
        rollout(prog)
        emu.save_state(cur)
        total += args.rollout
        emu.save_screen(os.path.join(shots, f"c{c:03d}_f{total:06d}_lap{st['lap']}.png"))
        log.append(dict(commit=c, frames=total, prog=prog, score=sc, **st))
        json.dump(log, open(os.path.join(args.out, "log.json"), "w"), indent=1)
        print(f"c{c:3d} f{total:6d} ck90={st['ck90']:3d} ck94={st['ck94']:3d} "
              f"kcp={st['kcp']} lap={st['lap']}  prog={prog}", flush=True)
        if st["lap"] != prev_lap:
            print(f"*** PLAYER LAP BYTE {prev_lap} -> {st['lap']} at frame ~{total} ***", flush=True)
            prev_lap = st["lap"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
