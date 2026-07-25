"""MKDS lap oracle hunt v2 -- headless full-lap drive, $0 offline.

Builds on the f3 open-loop spine (reports/2026-07-23-f3-latency-window.md): default reflex
is accel + pulse-LEFT (half strength), which cleared turn 1 and held top speed for >500f in
that probe. This script extends that spine with a closed-loop RECOVERY layer driven only by
RAM oracles (no vision, no LLM) so it can survive turns/collisions the fixed reflex alone
cannot, over a long enough drive to complete a full lap:

  - speed oracle 0x0237438C (u32): sustained low speed after having reached racing speed
    triggers a reverse+steer-out recovery maneuver (alternating direction each attempt).
  - checkpoint oracle 0x022C8090 (u8, "checkpoint-within-lap", confirmed BIDIRECTIONAL by
    reports/2026-07-23-oracle-mkds-lap.md): logged every frame, purely for telemetry --
    a drop with its companion 0x022C8094 UNCHANGED is flagged WRONG_WAY (matches that
    report's finding); a drop with 0x022C8094 CHANGED is flagged LAP_WRAP_CANDIDATE, the
    signal this script is hunting for.

Single py-desmume instance for the whole process (the documented SIGSEGV-on-second-instance
gotcha) -- one drive per process invocation. Deterministic: same command sequence from the
same savestate reproduces byte-identical traces (confirmed by the prior session's fresh-
process replay), so re-running this script from scratch with a bigger --frames budget is
always safe, and its logged command sequence (commands.json) can be replayed frame-for-frame
by replay_and_shoot.py to capture screenshots/RAM without re-deriving any decision.

Usage:
  <venv>/python.exe drive_lap.py --assets <primary-checkout> --out <dir> --frames 20000
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys

ROM_REL = "roms/nds/Mario Kart DS (USA) (En,Fr,De,Es,It).nds"
STATE_REL = "runs/nds3d_probe/mkds_race_start.state"

SPEED_ADDR = 0x0237438C   # LE u32, forward-speed oracle (eval/mkds_latency_window.py)
V_TOP = 2_031_638
CKPT90_ADDR = 0x022C8090  # u8, checkpoint-within-lap, bidirectional (2026-07-23 report)
CKPT94_ADDR = 0x022C8094  # u8, companion, did not decrement on a confirmed wrong-way event

RACING_FRAC = 0.55
STALL_FRAC = 0.30
STALL_DWELL = 30           # frames (0.5s) of sustained low speed after racing => stuck
REV_FRAMES = 45
STEER_FRAMES = 25
MAX_RECOVERIES = 400


def _speed(emu) -> int:
    b = bytes(emu._emu.memory.unsigned[SPEED_ADDR:SPEED_ADDR + 4])
    return struct.unpack("<I", b)[0]


class Driver:
    """Pure function of (frame, speed, ckpt90, ckpt94) -> command. No vision, no screen access."""

    def __init__(self):
        self.mode = "forward"
        self.mode_frame = 0
        self.stall_run = 0
        self.reached_racing = False
        self.recover_dir = "right"
        self.recovery_count = 0
        self.events: list[dict] = []
        self._prev_ckpt90 = None
        self._prev_ckpt94 = None

    def _log_checkpoint(self, f, ckpt90, ckpt94):
        if self._prev_ckpt90 is not None and ckpt90 != self._prev_ckpt90:
            kind = "tick_up" if ckpt90 > self._prev_ckpt90 else "drop"
            if kind == "drop":
                if ckpt94 != self._prev_ckpt94:
                    kind = "LAP_WRAP_CANDIDATE"
                else:
                    kind = "WRONG_WAY"
            self.events.append({"frame": f, "kind": kind,
                                 "ckpt90": [self._prev_ckpt90, ckpt90],
                                 "ckpt94": [self._prev_ckpt94, ckpt94]})
        if self._prev_ckpt94 is not None and ckpt94 != self._prev_ckpt94 and ckpt90 == self._prev_ckpt90:
            # ckpt94 alone moved (shouldn't normally happen going by the prior report, but log it)
            self.events.append({"frame": f, "kind": "ckpt94_only_change",
                                 "ckpt90": [self._prev_ckpt90, ckpt90],
                                 "ckpt94": [self._prev_ckpt94, ckpt94]})
        self._prev_ckpt90, self._prev_ckpt94 = ckpt90, ckpt94

    def command(self, f, speed_now, ckpt90, ckpt94):
        self._log_checkpoint(f, ckpt90, ckpt94)

        if speed_now >= RACING_FRAC * V_TOP:
            self.reached_racing = True
        if self.reached_racing and speed_now < STALL_FRAC * V_TOP:
            self.stall_run += 1
        else:
            self.stall_run = 0

        if (self.mode == "forward" and self.stall_run >= STALL_DWELL
                and self.recovery_count < MAX_RECOVERIES):
            self.mode = "reverse"
            self.mode_frame = 0
            self.recovery_count += 1
            self.stall_run = 0
            self.reached_racing = False
            self.recover_dir = "left" if self.recover_dir == "right" else "right"
            self.events.append({"frame": f, "kind": "recovery_start", "dir": self.recover_dir,
                                 "count": self.recovery_count})

        if self.mode == "reverse":
            cmd = ("b", self.recover_dir)
            self.mode_frame += 1
            if self.mode_frame >= REV_FRAMES:
                self.mode, self.mode_frame = "steer_out", 0
            return cmd
        if self.mode == "steer_out":
            cmd = ("a", self.recover_dir)
            self.mode_frame += 1
            if self.mode_frame >= STEER_FRAMES:
                self.mode, self.mode_frame = "forward", 0
            return cmd
        return ("a", "left") if f % 2 == 0 else ("a",)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assets", required=True, help="primary checkout holding roms/ and runs/")
    ap.add_argument("--repo", default=None, help="repo root for core/ import (defaults to --assets)")
    ap.add_argument("--out", required=True, help="output dir for JSON trace + command log")
    ap.add_argument("--frames", type=int, default=20000)
    ap.add_argument("--log-every", type=int, default=10, help="decimation for the speed/ckpt trace")
    args = ap.parse_args()

    assets = os.path.abspath(args.assets)
    repo = os.path.abspath(args.repo) if args.repo else assets
    sys.path.insert(0, repo)
    from core.nds_emulator import DeSmuMEEmulator  # noqa: E402
    from desmume.controls import Keys, keymask  # noqa: E402

    rom = os.path.join(assets, ROM_REL)
    state = os.path.join(assets, STATE_REL)
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    emu = DeSmuMEEmulator(rom, headless=True)
    key_of = {b: keymask(getattr(Keys, "KEY_" + b.upper())) for b in
              ("a", "b", "left", "right", "up", "down")}

    emu.load_state(state)
    for m in key_of.values():
        emu._emu.input.keypad_rm_key(m)
    emu.tick(1)

    driver = Driver()
    trace = []
    commands: list[list[str]] = []
    held: set[str] = set()

    for f in range(args.frames):
        speed_now = _speed(emu)
        ckpt90 = emu.read(CKPT90_ADDR)
        ckpt94 = emu.read(CKPT94_ADDR)
        want = set(driver.command(f, speed_now, ckpt90, ckpt94))
        for b in want - held:
            emu._emu.input.keypad_add_key(key_of[b])
        for b in held - want:
            emu._emu.input.keypad_rm_key(key_of[b])
        held = want
        commands.append(sorted(want))
        emu.tick(1)
        if f % args.log_every == 0:
            trace.append({"f": f, "speed": speed_now, "ckpt90": ckpt90, "ckpt94": ckpt94,
                          "mode": driver.mode})
        if f % 1000 == 0:
            print(f"  f={f:6d} speed={speed_now:>9} ckpt90={ckpt90} ckpt94={ckpt94} "
                  f"mode={driver.mode} recoveries={driver.recovery_count}", flush=True)

    for m in key_of.values():
        emu._emu.input.keypad_rm_key(m)
    emu.close()

    with open(os.path.join(out, "trace.json"), "w") as fh:
        json.dump({"frames": args.frames, "trace": trace, "events": driver.events,
                   "recoveries": driver.recovery_count}, fh, indent=2)
    with open(os.path.join(out, "commands.json"), "w") as fh:
        json.dump(commands, fh)

    print(f"\nDone. {driver.recovery_count} recoveries. {len(driver.events)} checkpoint events.")
    for e in driver.events:
        print(" ", e)
    print(f"trace.json / commands.json -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
