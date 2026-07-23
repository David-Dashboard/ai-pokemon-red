"""F3 / capability A1 — the survivable-deliberation window, measured offline in Mario Kart DS.

The question (capability-map A1): the world moves while the brain thinks. How long can
System-2 be SILENT — a fixed System-1 reflex holding a default in the gap — before the race is
ruined? That silence-tolerance is the requirements spec for how much reflex A5 must compile
before real-time worlds are attemptable.

Method (OFFLINE, $0, no paid LLM): drive the banked MKDS race savestate
(runs/nds3d_probe/mkds_race_start.state, Figure-8 Circuit, 50cc, standing start) under fixed
open-loop reflexes and under a latency-decimated scripted opener, and label RUIN from a RAM
speed oracle.

Two measurements:
  A. Fixed-reflex open-loop horizon. For each fixed reflex (the whole System-1, no perception),
     drive from GO and record frames-to-ruin. A reflex's horizon = the longest System-2 silence
     it can cover. The BEST fixed reflex's horizon is the survivable-deliberation window for an
     OPEN-LOOP reflex layer.
  B. Latency injection into a scripted opener. A per-frame steering opener that clears turn 1 at
     full authority (decide-every-frame) is re-run refreshing its command only every L frames
     (reflex = hold-last-command in between). L* = the largest latency that still clears turn 1.

RUIN ORACLE (offline labelling only — NEVER on the agent wire; the reflex reads no memory):
  speed = little-endian u32 at 0x0237438C in ARM9 main RAM. Verified 2026-07-23 to read ~22 at
  rest/countdown, plateau at V_TOP≈2,031,638 at 50cc top speed, and collapse toward ~22 when the
  kart grinds a wall. This mirrors perception_plugin's no-leak rule: RAM is a measurement oracle,
  it never reaches Observation.data.

Run (assets — ROM/state/venv — live in the main checkout; roms/ and runs/ are gitignored):
  .venv-win/Scripts/python.exe eval/mkds_latency_window.py --base <repo-with-assets> --out <dir>

Screen-change metric (`top_flow`) is the same per-frame pct_changed used by
runs/nds3d_probe/mkds_vision/race_measure.py and FINDINGS.md — kept only as a corroborating
signal; the speed oracle is the authority.
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys

import numpy as np

# --- constants ----------------------------------------------------------------
ROM_REL = "roms/nds/Mario Kart DS (USA) (En,Fr,De,Es,It).nds"
STATE_REL = "runs/nds3d_probe/mkds_race_start.state"
SPEED_ADDR = 0x0237438C          # LE u32 forward-speed oracle (offline only)
V_TOP = 2_031_638                # measured 50cc top-speed plateau (units of the oracle)
FPS = 59.8261                    # NDS hardware framerate (matches nds_emulator._NDS_FPS)

GO_FRAC = 0.05                   # speed > 5% V_TOP => the kart has launched (GO)
RACING_FRAC = 0.55               # speed >= 55% V_TOP => racing at speed
STALL_FRAC = 0.30                # speed < 30% V_TOP => off-line / walled / stalled
STALL_DWELL = 30                 # sustained frames below STALL_FRAC => ruin (0.5 s), not a dip
HORIZON = 500                    # frames simulated per condition (~8.4 s)
CLEAR_TURN1_FRAME = 250          # racing past this (from GO) without ruin => cleared turn 1


def _speed(emu) -> int:
    b = bytes(emu._emu.memory.unsigned[SPEED_ADDR:SPEED_ADDR + 4])
    return struct.unpack("<I", b)[0]


def _top_flow(a: np.ndarray, b: np.ndarray) -> float:
    d = np.abs(a[:192].astype(np.int16) - b[:192].astype(np.int16)).max(axis=-1)
    return float((d > 8).mean() * 100.0)


def _analyse(speed: list[int]) -> dict:
    """Given a per-frame speed trace, find GO, ruin onset, and whether turn 1 was cleared."""
    go = next((i for i, s in enumerate(speed) if s > GO_FRAC * V_TOP), None)
    if go is None:
        return {"go_frame": None, "ruined": None, "ruin_frame": None,
                "survived_frames": 0, "cleared_turn1": False, "reached_racing": False}
    reached = any(s >= RACING_FRAC * V_TOP for i, s in enumerate(speed) if i >= go)
    ruin_frame = None
    if reached:
        run = 0
        for i in range(go, len(speed)):
            if speed[i] < STALL_FRAC * V_TOP:
                run += 1
                if run >= STALL_DWELL:
                    ruin_frame = i - STALL_DWELL + 1   # first frame of the stall
                    break
            else:
                run = 0
    ruined = ruin_frame is not None
    survived = (ruin_frame - go) if ruined else (len(speed) - go)
    cleared = reached and (not ruined or (ruin_frame - go) >= CLEAR_TURN1_FRAME)
    return {"go_frame": go, "reached_racing": reached, "ruined": ruined,
            "ruin_frame": ruin_frame, "survived_frames": survived,
            "survived_s": round(survived / FPS, 3), "cleared_turn1": cleared}


# --- reflex / command primitives ---------------------------------------------
# A steering command is a set of button names held that frame. The reflex is a pure function
# frame -> commanded buttons; it has NO access to the screen or RAM (open-loop, fixed).

def reflex_null(_f):        return ()
def reflex_accel(_f):       return ("a",)
def reflex_accel_left(_f):  return ("a", "left")
def reflex_accel_right(_f): return ("a", "right")
def reflex_accel_left_pulse(f):   # half-strength left: steer on alternate frames
    return ("a", "left") if f % 2 == 0 else ("a",)

REFLEXES = {
    "null (no input)": reflex_null,
    "accel only (hold straight)": reflex_accel,
    "accel + hold-left": reflex_accel_left,
    "accel + hold-right": reflex_accel_right,
    "accel + pulse-left (half)": reflex_accel_left_pulse,
}


def _drive(emu, state, cmd_fn, frames, out_dir=None, tag=None):
    """Load state, drive `frames` frames issuing cmd_fn(frame) each frame. Returns traces."""
    from desmume.controls import Keys, keymask
    key_of = {b: keymask(getattr(Keys, "KEY_" + b.upper())) for b in
              ("a", "b", "left", "right", "up", "down")}
    emu.load_state(state)
    for m in key_of.values():
        emu._emu.input.keypad_rm_key(m)
    emu.tick(1)
    prev = emu.screen_ndarray()
    speed, flow, held = [], [], set()
    shot_frames = set()
    for f in range(frames):
        want = set(cmd_fn(f))
        for b in want - held:
            emu._emu.input.keypad_add_key(key_of[b])
        for b in held - want:
            emu._emu.input.keypad_rm_key(key_of[b])
        held = want
        emu.tick(1)
        cur = emu.screen_ndarray()
        speed.append(_speed(emu))
        flow.append(round(_top_flow(prev, cur), 2))
        prev = cur
    for m in key_of.values():
        emu._emu.input.keypad_rm_key(m)
    return {"speed": speed, "flow": flow}


def _save_shots(emu, state, cmd_fn, frames_to_shoot, out_dir, tag):
    """Second pass that saves top-screen PNGs at the given frames (for visual ruin confirmation)."""
    from desmume.controls import Keys, keymask
    from PIL import Image
    key_of = {b: keymask(getattr(Keys, "KEY_" + b.upper())) for b in
              ("a", "b", "left", "right", "up", "down")}
    emu.load_state(state)
    for m in key_of.values():
        emu._emu.input.keypad_rm_key(m)
    emu.tick(1)
    held = set()
    fmax = max(frames_to_shoot)
    for f in range(fmax + 1):
        want = set(cmd_fn(f))
        for b in want - held:
            emu._emu.input.keypad_add_key(key_of[b])
        for b in held - want:
            emu._emu.input.keypad_rm_key(key_of[b])
        held = want
        emu.tick(1)
        if f in frames_to_shoot:
            Image.fromarray(emu.screen_ndarray()[:192], "RGB").save(
                os.path.join(out_dir, f"{tag}_f{f:03d}.png"))
    for m in key_of.values():
        emu._emu.input.keypad_rm_key(m)


# --- Measurement B: silence-at-the-turn injection -----------------------------
# The good System-2 policy is the validated half-strength turn reflex (pulse-`dir`, which clears
# turn 1 at full authority — Measurement A). We inject a deliberation SILENCE of N frames right
# after GO: during the silence the System-1 reflex holds the null default (accel, straight); when
# System-2 "returns" the good pulse policy resumes. N* = the largest silence that still clears
# turn 1 = the survivable-deliberation window at the race's first steering demand. GO is anchored
# to a fixed frame because the A-held countdown from this savestate is deterministic.
GO_EST = 108  # measured launch frame (speed leaves rest), stable across runs with A held in countdown


def silenced_policy(turn_dir, n_silence):
    def cmd(f):
        if f < GO_EST + n_silence:
            return ("a",)                                   # countdown + injected silence: straight
        return ("a", turn_dir) if (f - GO_EST) % 2 == 0 else ("a",)   # pulse-`dir` (half strength)
    return cmd


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=".", help="repo root holding roms/ and runs/ (gitignored assets)")
    ap.add_argument("--out", default="runs/mkds_latency", help="output dir for JSON + screenshots")
    ap.add_argument("--shots", action="store_true", help="also save confirmation screenshots")
    args = ap.parse_args()

    base = os.path.abspath(args.base)
    sys.path.insert(0, base)
    from core.nds_emulator import DeSmuMEEmulator  # noqa: E402

    rom = os.path.join(base, ROM_REL)
    state = os.path.join(base, STATE_REL)
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    emu = DeSmuMEEmulator(rom, headless=True)  # single instance (py-desmume is a process singleton)

    # ---- Measurement A ----
    print("=== Measurement A: fixed-reflex open-loop horizon ===", flush=True)
    A = {}
    for name, fn in REFLEXES.items():
        tr = _drive(emu, state, fn, HORIZON)
        res = _analyse(tr["speed"])
        res["speed_peak"] = max(tr["speed"])
        A[name] = {**res, "speed": tr["speed"], "flow": tr["flow"]}
        print(f"  {name:32s} GO@{res['go_frame']}  peak={res['speed_peak']:>8}  "
              f"racing={res['reached_racing']}  ruin@{res['ruin_frame']}  "
              f"survived={res['survived_frames']}f ({res.get('survived_s')}s)  "
              f"cleared_turn1={res['cleared_turn1']}", flush=True)

    # turn-1 direction = whichever hold-bias survives longer than straight
    straight = A["accel only (hold straight)"]["survived_frames"]
    left = A["accel + hold-left"]["survived_frames"]
    right = A["accel + hold-right"]["survived_frames"]
    turn_dir = "left" if left >= right else "right"
    print(f"  -> turn-1 bias: straight={straight}f left={left}f right={right}f => good policy steers {turn_dir}",
          flush=True)

    # ---- Measurement B ----
    print("\n=== Measurement B: silence-at-the-turn injection ===", flush=True)
    # good policy = pulse-`turn_dir` (clears turn 1 at full authority). Inject N frames of straight-hold
    # silence right after GO; find the largest N that still clears turn 1 = survivable deliberation window.
    B = {"good_policy": f"pulse-{turn_dir} from GO", "go_est": GO_EST, "sweep": {}}
    N_star = None
    for N in (0, 10, 20, 30, 40, 50, 60, 70, 80, 100, 120, 150):
        r = _analyse(_drive(emu, state, silenced_policy(turn_dir, N), HORIZON)["speed"])
        B["sweep"][N] = {"cleared_turn1": r["cleared_turn1"], "survived_frames": r["survived_frames"],
                         "survived_s": r.get("survived_s"), "ruin_frame": r["ruin_frame"]}
        if r["cleared_turn1"]:
            N_star = N
        print(f"    silence N={N:>3}f ({N/FPS*1000:6.0f} ms)  cleared_turn1={r['cleared_turn1']}  "
              f"survived={r['survived_frames']}f ({r.get('survived_s')}s)", flush=True)
    B["N_star_frames"] = N_star
    B["N_star_ms"] = round(N_star / FPS * 1000, 1) if N_star is not None else None
    print(f"  -> N* = {N_star}f = {B['N_star_ms']} ms (largest post-GO silence that still clears turn 1)",
          flush=True)

    # optional screenshots for the two headline fixed reflexes
    if args.shots:
        for name, tag in (("accel only (hold straight)", "straight"),
                          ("accel + hold-" + turn_dir, "bias")):
            res = A[name]
            go = res["go_frame"] or 70
            frames = sorted({go + 20, (res["ruin_frame"] or go + 120),
                             min(HORIZON - 1, go + 200), min(HORIZON - 1, go + 350)})
            _save_shots(emu, state, REFLEXES[name], frames, out, tag)
        print(f"  screenshots -> {out}", flush=True)

    emu.close()
    summary = {
        "oracle": {"speed_addr": hex(SPEED_ADDR), "v_top": V_TOP, "fps": FPS,
                   "ruin_def": f"speed<{STALL_FRAC}*Vtop for >={STALL_DWELL}f after reaching {RACING_FRAC}*Vtop"},
        "measurement_A": {k: {kk: vv for kk, vv in v.items() if kk not in ("speed", "flow")}
                          for k, v in A.items()},
        "turn1_dir": turn_dir,
        "measurement_B": B,
    }
    with open(os.path.join(out, "latency_window.json"), "w") as f:
        json.dump({"summary": summary, "traces_A": {k: {"speed": v["speed"], "flow": v["flow"]}
                                                    for k, v in A.items()}}, f, indent=2)
    print(f"\nJSON -> {os.path.join(out, 'latency_window.json')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
