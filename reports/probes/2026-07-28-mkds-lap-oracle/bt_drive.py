"""Backtracking driver: best-known-state checkpointing + per-attempt steering bias.

The failure mode that killed every previous MKDS driving attempt (PR #168's manual piloting,
and this session's beam/rollout/unstick attempts) is the same: once the kart ends up wedged or
turned around, every subsequent frame is spent in a bad region and the run never recovers.

This keeps a savestate of the FURTHEST state ever reached (highest 0x022C8094 then 0x022C8090,
the checkpoint pair established by the 2026-07-23 hunt) and, whenever an attempt fails to beat
it, reloads that state and retries with the next steering bias. Progress therefore never goes
backwards.

Same anti-circularity rule as the other drivers here: THE LAP BYTE 0x0236A7F2 IS READ AND
LOGGED BUT NEVER SCORED ON, so a lap-byte tick remains an independent observation.
"""
from __future__ import annotations
import argparse, json, os, struct, sys

ASSETS = os.environ.get("MKDS_ASSETS",
                        r"E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red")
ROM = os.path.join(ASSETS, "roms", "nds", "Mario Kart DS (USA) (En,Fr,De,Es,It).nds")
STATE = os.path.join(ASSETS, "runs", "nds3d_probe", "mkds_race_start.state")

CK90, CK94, SPEED = 0x022C8090, 0x022C8094, 0x0237438C
LAP_P, KCP_P = 0x0236A7F2, 0x0236A806
FAST = 1_500_000        # speed-oracle units; 50cc top speed is ~2.03e6
BIASES = ["none", "pleft", "pright", "left", "right", "hleft", "hright"]


def keyseq(bias, i):
    if bias == "none":   return ("a",)
    if bias == "left":   return ("a", "left")
    if bias == "right":  return ("a", "right")
    if bias == "pleft":  return ("a", "left") if i % 2 == 0 else ("a",)
    if bias == "pright": return ("a", "right") if i % 2 == 0 else ("a",)
    if bias == "hleft":  return ("a", "left") if i % 4 == 0 else ("a",)
    if bias == "hright": return ("a", "right") if i % 4 == 0 else ("a",)
    raise ValueError(bias)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempts", type=int, default=400)
    ap.add_argument("--attempt-frames", type=int, default=600)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    shots = os.path.join(args.out, "shots"); os.makedirs(shots, exist_ok=True)
    best_state = os.path.join(args.out, "best.state")

    sys.path.insert(0, ASSETS)
    from core.nds_emulator import DeSmuMEEmulator
    from desmume.controls import Keys, keymask

    emu = DeSmuMEEmulator(ROM, headless=True)
    emu.load_state(STATE)
    emu.tick(300)                      # clear the standing-start countdown
    emu.save_state(best_state)
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

    fast_frames = 0

    def prog():
        # lexicographic: confirmed checkpoint, tentative checkpoint, key-checkpoint bits, and
        # finally how much of the attempt was spent at racing speed (a pure tiebreak, so that
        # attempts which are level on checkpoints still order sensibly). None of these is the
        # lap byte.
        return (raw[CK94], raw[CK90], bin(raw[KCP_P]).count("1"), fast_frames)

    best, bi, events, laps = prog(), 0, [], raw[LAP_P]
    print(f"start progress={best} lap={laps}", flush=True)
    for a in range(args.attempts):
        emu.load_state(best_state)
        bias = BIASES[bi % len(BIASES)]
        fast_frames = 0
        peak, peak_lap = prog(), laps
        for i in range(args.attempt_frames):
            keys(keyseq(bias, i)); emu.tick(1)
            if struct.unpack("<I", bytes(raw[SPEED:SPEED + 4]))[0] > FAST:
                fast_frames += 1
            p = prog()
            if p > peak:
                peak = p
            nl = raw[LAP_P]
            if nl != peak_lap:
                emu.save_screen(os.path.join(shots, f"a{a:03d}_i{i:04d}_LAP_{peak_lap}to{nl}.png"))
                print(f"*** attempt {a} frame {i}: PLAYER LAP BYTE {peak_lap} -> {nl} "
                      f"(ck94={raw[CK94]} ck90={raw[CK90]}) ***", flush=True)
                events.append(dict(attempt=a, i=i, prev=peak_lap, new=int(nl),
                                   ck90=int(raw[CK90]), ck94=int(raw[CK94])))
                peak_lap = nl
        keys(())
        end = prog()
        if end > best:
            best, laps = end, raw[LAP_P]
            emu.save_state(best_state)
            emu.save_screen(os.path.join(shots, f"a{a:03d}_best_{best[0]}_{best[1]}.png"))
            print(f"a{a:3d} {bias:7s} ADVANCE -> ck94={best[0]} ck90={best[1]} lap={laps}",
                  flush=True)
            bi = 0
        else:
            bi += 1
            if a % 10 == 0:
                print(f"a{a:3d} {bias:7s} no advance (end={end} peak={peak} best={best})",
                      flush=True)
        json.dump(dict(best=list(best), lap_events=events),
                  open(os.path.join(args.out, "result.json"), "w"), indent=1)
    print("FINAL best:", best, "lap byte:", raw[LAP_P], "lap events:", events)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
