"""Frame-by-frame trace of the candidate map-identity bytes across a map transition.

Catches the failure mode a recent hunt in this project nearly shipped: a claim resting on a
handful of frames, or a byte that takes a transient/garbage value mid-warp.
"""
import argparse, json, sys

ADDRS = {"mapsec": 0x0203732C, "mapNum": 0x02037359, "mapGroup": 0x0203735A,
         "banked_map_num": 0x0203735C, "banked_map_group": 0x02037340}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", required=True); ap.add_argument("--state-in", required=True)
    ap.add_argument("--hold", default="up"); ap.add_argument("--hold-frames", type=int, default=16)
    ap.add_argument("--frames", type=int, default=300); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    try:
        import mgba.log; mgba.log.silence()
    except Exception:
        pass
    from core.gba_emulator import GBAEmulator, _BITMASK
    emu = GBAEmulator(a.rom); emu.load_state(a.state_in)
    rows = []
    for f in range(a.frames):
        emu._core.set_keys(raw=_BITMASK[a.hold] if f < a.hold_frames else 0)
        emu._core.run_frame()
        rows.append({k: emu.read(v) for k, v in ADDRS.items()})
    with open(a.out, "w") as fh:
        json.dump(rows, fh)
    emu.close()

main()
