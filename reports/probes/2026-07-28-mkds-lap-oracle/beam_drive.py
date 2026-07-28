"""RAM-guided greedy beam driver: get the PLAYER kart around a real lap of Figure-8 Circuit.

Both prior MKDS oracle hunts (PR #168 and its predecessor) failed for one reason -- nobody could
drive a lap, so no lap boundary was ever observed. This replaces vision-guided manual piloting
with a savestate-backtracking greedy search: from the current state, run every candidate policy
for BURST frames, score the resulting state, commit the best, repeat.

SCORING DELIBERATELY EXCLUDES THE LAP BYTE. The objective is built only from the checkpoint
counter 0x022C8090 (established by earlier hunts), the per-racer key-checkpoint bitmask, and
speed. That keeps a lap-byte tick an INDEPENDENT observation rather than the thing the search
was optimising -- otherwise the search would launder the hypothesis into its own evidence.

py-desmume SIGSEGVs on a second DeSmuME instance per process, so this runs ONE instance and
uses repeated load_state() for backtracking (same technique as the 2026-07-25 auto_recover.py).
"""
from __future__ import annotations
import argparse, json, os, struct, sys

ASSETS = os.environ.get("MKDS_ASSETS", r"E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red")
ROM = os.path.join(ASSETS, "roms", "nds", "Mario Kart DS (USA) (En,Fr,De,Es,It).nds")
STATE = os.path.join(ASSETS, "runs", "nds3d_probe", "mkds_race_start.state")

CK90 = 0x022C8090
CK94 = 0x022C8094
SPEED = 0x0237438C
LAP_P = 0x0236A7F2       # player lap byte (observed, NOT scored on)
KCP_P = 0x0236A806       # player key-checkpoint bitmask

POLICIES = {
    "straight":   lambda f: ("a",),
    "left":       lambda f: ("a", "left"),
    "right":      lambda f: ("a", "right"),
    "pleft":      lambda f: ("a", "left") if f % 2 == 0 else ("a",),
    "pright":     lambda f: ("a", "right") if f % 2 == 0 else ("a",),
    "qleft":      lambda f: ("a", "left") if f % 4 == 0 else ("a",),
    "qright":     lambda f: ("a", "right") if f % 4 == 0 else ("a",),
    "lead_left":  lambda f: ("a", "left") if f < 45 else ("a",),
    "lead_right": lambda f: ("a", "right") if f < 45 else ("a",),
    "drift_left": lambda f: ("a", "r", "left"),
    "drift_right": lambda f: ("a", "r", "right"),
    "rev":        lambda f: ("b",),
    "rev_left":   lambda f: ("b", "left"),
    "rev_right":  lambda f: ("b", "right"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=220)
    ap.add_argument("--burst", type=int, default=150)
    ap.add_argument("--out", required=True)
    ap.add_argument("--start-state", default=STATE)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    shots = os.path.join(args.out, "shots"); os.makedirs(shots, exist_ok=True)
    cur = os.path.join(args.out, "cur.state")
    trial = os.path.join(args.out, "trial.state")

    sys.path.insert(0, ASSETS)
    from core.nds_emulator import DeSmuMEEmulator
    from desmume.controls import Keys, keymask

    emu = DeSmuMEEmulator(ROM, headless=True)
    emu.load_state(args.start_state)
    emu.save_state(cur)
    raw = emu._emu.memory.unsigned

    def rd():
        sp = struct.unpack("<I", bytes(raw[SPEED:SPEED + 4]))[0]
        return dict(ck90=raw[CK90], ck94=raw[CK94], lap=raw[LAP_P],
                    kcp=bin(raw[KCP_P]).count("1"), speed=sp)

    def run(pol, n):
        fn = POLICIES[pol]
        held, spd = set(), 0
        for f in range(n):
            want = set(fn(f))
            for k in want - held:
                emu._emu.input.keypad_add_key(keymask(getattr(Keys, "KEY_" + k.upper())))
            for k in held - want:
                emu._emu.input.keypad_rm_key(keymask(getattr(Keys, "KEY_" + k.upper())))
            held = want
            emu.tick(1)
            spd += struct.unpack("<I", bytes(raw[SPEED:SPEED + 4]))[0]
        for k in held:
            emu._emu.input.keypad_rm_key(keymask(getattr(Keys, "KEY_" + k.upper())))
        return spd / n

    log, chosen = [], []
    prev = rd()
    total_frames = 0
    print(f"start {prev}", flush=True)
    for step in range(args.steps):
        results = []
        for pol in POLICIES:
            emu.load_state(cur)
            mean_sp = run(pol, args.burst)
            st = rd()
            # objective: checkpoints first, then key-checkpoint bits, then how fast we moved.
            # NOTE: st['lap'] is read but NEVER enters the score.
            score = st["ck94"] * 1_000_000 + st["ck90"] * 10_000 + st["kcp"] * 500 + mean_sp / 1e5
            results.append((score, pol, st, mean_sp))
        results.sort(reverse=True, key=lambda r: r[0])
        # prefer a candidate that does not regress the checkpoint counter
        pick = next((r for r in results if r[2]["ck90"] >= prev["ck90"]
                     and r[2]["ck94"] >= prev["ck94"]), results[0])
        _, pol, st, mean_sp = pick
        emu.load_state(cur)
        run(pol, args.burst)
        emu.save_state(cur)
        total_frames += args.burst
        chosen.append(pol)
        log.append(dict(step=step, frames=total_frames, policy=pol, mean_speed=round(mean_sp), **st))
        if st["lap"] != prev["lap"] or step % 10 == 0:
            emu.save_screen(os.path.join(shots, f"s{step:04d}_f{total_frames:06d}_lap{st['lap']}.png"))
        if st["lap"] != prev["lap"]:
            print(f"*** LAP BYTE {prev['lap']} -> {st['lap']} at step {step} "
                  f"(frame {total_frames}) ***", flush=True)
        if step % 5 == 0:
            print(f"s{step:3d} f{total_frames:6d} {pol:11s} ck90={st['ck90']:3d} ck94={st['ck94']:3d} "
                  f"kcp={st['kcp']} lap={st['lap']} sp={mean_sp/1e5:.1f}", flush=True)
        prev = st
        json.dump(log, open(os.path.join(args.out, "log.json"), "w"), indent=1)
    print("chosen:", " ".join(chosen))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
