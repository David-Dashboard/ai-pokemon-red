"""Pass 2: deterministic replay of the same coast, recording a dense trace of a RAM WINDOW
(default 0x0236A700-0x0236AC80, the candidate per-racer struct array) every --every frames,
plus periodic screenshots. Produces window.npy (n_samples x width uint8) + frames.npy.

Usage: python pass2_window.py --frames 30000 --every 30 --base 0x0236A700 --width 0x600 --out <dir>
"""
from __future__ import annotations
import argparse, os, sys, time
import numpy as np

ASSETS = os.environ.get("MKDS_ASSETS", r"E:\AI_Personas\10_pokemon_and_chess_and_office\ai-pokemon-red")
ROM = os.path.join(ASSETS, "roms", "nds", "Mario Kart DS (USA) (En,Fr,De,Es,It).nds")
STATE = os.path.join(ASSETS, "runs", "nds3d_probe", "mkds_race_start.state")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=30000)
    ap.add_argument("--every", type=int, default=30)
    ap.add_argument("--base", type=lambda s: int(s, 0), default=0x0236A700)
    ap.add_argument("--width", type=lambda s: int(s, 0), default=0x600)
    ap.add_argument("--shot-every", type=int, default=300)
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
    b, w = args.base, args.width

    rows, frames, huds = [], [], []
    held = set()
    t0 = time.time()
    for f in range(0, args.frames + 1):
        if f:
            want = {"a"} if args.policy == "accel" else set()
            for k in want - held:
                emu._emu.input.keypad_add_key(keymask(getattr(Keys, "KEY_" + k.upper())))
            for k in held - want:
                emu._emu.input.keypad_rm_key(keymask(getattr(Keys, "KEY_" + k.upper())))
            held = want
            emu.tick(1)
        if f % args.every == 0:
            rows.append(np.frombuffer(bytes(raw[b:b + w]), dtype=np.uint8))
            frames.append(f)
            # LAP HUD numerator+denominator crop, top screen (x 196..250, y 2..22)
            huds.append(emu.screen_ndarray("top")[2:22, 196:250].copy())
        if f % args.shot_every == 0:
            emu.save_screen(os.path.join(shots, f"f{f:06d}.png"))
            if f % 3000 == 0:
                print(f"f={f} t={time.time()-t0:.0f}s", flush=True)

    np.save(os.path.join(args.out, "window.npy"), np.array(rows))
    np.save(os.path.join(args.out, "frames.npy"), np.array(frames))
    np.save(os.path.join(args.out, "hud.npy"), np.array(huds))
    print("saved", len(rows), "samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
