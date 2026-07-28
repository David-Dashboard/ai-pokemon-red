"""Reactive unstick driver -- the cheapest thing that might get the PLAYER kart around a lap.

Both prior MKDS hunts (and this session's beam/rollout searches) failed on the same thing: a
fixed open-loop policy wedges the kart against a guardrail and never recovers, so no lap
boundary is ever reached. This is a single-rollout closed-loop controller instead of a search:

  DRIVE  hold A (+ a steering bias that rotates when progress stalls)
  STUCK  detected from the speed oracle 0x0237438C; reverse + full-steer, direction alternating
         each attempt, then resume DRIVE

Progress is judged ONLY from the checkpoint counter 0x022C8090 and the speed oracle -- both
established by earlier hunts. THE LAP BYTE IS READ AND LOGGED BUT NEVER STEERS THE CONTROLLER,
so a lap-byte tick stays an independent observation instead of the controller's own objective.
"""
from __future__ import annotations
import argparse, json, os, struct, sys

ASSETS = os.environ.get("MKDS_ASSETS", r"E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red")
ROM = os.path.join(ASSETS, "roms", "nds", "Mario Kart DS (USA) (En,Fr,De,Es,It).nds")
STATE = os.path.join(ASSETS, "runs", "nds3d_probe", "mkds_race_start.state")

CK90, CK94, SPEED = 0x022C8090, 0x022C8094, 0x0237438C
LAP_P, KCP_P = 0x0236A7F2, 0x0236A806
MOVING = 300_000          # speed-oracle units; top speed at 50cc is ~2.03e6, at-rest is 22


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=40000)
    ap.add_argument("--bias", default="none",
                    choices=["none", "left", "right", "pleft", "pright"])
    ap.add_argument("--warmup", type=int, default=400,
                    help="frames to ignore the stuck detector for (pre-race countdown)")
    ap.add_argument("--stall-window", type=int, default=2400)
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
    held = set()

    def keys(want):
        nonlocal held
        want = set(want)
        for k in want - held:
            emu._emu.input.keypad_add_key(keymask(getattr(Keys, "KEY_" + k.upper())))
        for k in held - want:
            emu._emu.input.keypad_rm_key(keymask(getattr(Keys, "KEY_" + k.upper())))
        held = want

    def speed():
        return struct.unpack("<I", bytes(raw[SPEED:SPEED + 4]))[0]

    BIASES = ["none", "left", "right", "pleft", "pright"]
    bias = args.bias
    recent, mode, mode_left, rec_dir, attempts = [], "DRIVE", 0, 1, 0
    last_ck90, last_ck90_f = raw[CK90], 0
    lap = raw[LAP_P]
    events = [dict(frame=0, lap=lap, ck90=raw[CK90], ck94=raw[CK94], note="start")]
    emu.save_screen(os.path.join(shots, f"f{0:06d}_lap{lap}.png"))

    for f in range(1, args.frames + 1):
        if mode == "DRIVE":
            if bias == "none":     k = ("a",)
            elif bias == "left":   k = ("a", "left")
            elif bias == "right":  k = ("a", "right")
            elif bias == "pleft":  k = ("a", "left") if f % 3 == 0 else ("a",)
            else:                  k = ("a", "right") if f % 3 == 0 else ("a",)
        elif mode == "REV":
            k = ("b", "left") if rec_dir > 0 else ("b", "right")
        else:  # TURN
            k = ("a", "left") if rec_dir > 0 else ("a", "right")
        keys(k)
        emu.tick(1)

        if mode == "DRIVE":          # only DRIVE frames count toward the stuck test
            recent.append(speed())
            if len(recent) > 90:
                recent.pop(0)

        if mode == "DRIVE":
            if f > args.warmup and len(recent) == 90 and sum(recent) / 90 < MOVING:
                mode, mode_left = "REV", 50
                attempts += 1
                rec_dir = 1 if attempts % 2 else -1
                recent.clear()
        else:
            mode_left -= 1
            if mode_left <= 0:
                if mode == "REV":
                    mode, mode_left = "TURN", 60
                else:
                    mode = "DRIVE"; recent.clear()

        c90 = raw[CK90]
        if c90 > last_ck90:
            last_ck90, last_ck90_f = c90, f
        elif f - last_ck90_f > args.stall_window:
            bias = BIASES[(BIASES.index(bias) + 1) % len(BIASES)]
            last_ck90_f = f
            events.append(dict(frame=f, lap=raw[LAP_P], ck90=c90, ck94=raw[CK94],
                               note=f"stall -> bias={bias}"))
            print(f"f{f:6d} stall, bias -> {bias} (ck90={c90})", flush=True)

        nl = raw[LAP_P]
        if nl != lap:
            for d in (0, 3, 30, 300, 1200):
                pass
            emu.save_screen(os.path.join(shots, f"f{f:06d}_LAPCHANGE_{lap}to{nl}.png"))
            events.append(dict(frame=f, lap=nl, prev_lap=lap, ck90=c90, ck94=raw[CK94],
                               note="LAP BYTE CHANGED"))
            print(f"*** f{f}: PLAYER LAP BYTE {lap} -> {nl}  (ck90={c90} ck94={raw[CK94]}) ***",
                  flush=True)
            lap = nl
        if f % 1500 == 0:
            emu.save_screen(os.path.join(shots, f"f{f:06d}_lap{lap}.png"))
            print(f"f{f:6d} mode={mode} bias={bias} ck90={raw[CK90]} ck94={raw[CK94]} "
                  f"lap={lap} kcp={raw[KCP_P]:08b} sp={speed()}", flush=True)
            json.dump(events, open(os.path.join(args.out, "events.json"), "w"), indent=1)

    json.dump(events, open(os.path.join(args.out, "events.json"), "w"), indent=1)
    print("final lap byte:", raw[LAP_P], "ck90:", raw[CK90], "attempts:", attempts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
