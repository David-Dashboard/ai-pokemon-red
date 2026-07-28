"""Multi-step $0 offline GBA driver for the EX04 (Kirby: Nightmare in Dreamland) level-oracle hunt.

Throwaway-but-committed probe script (not part of the shipped harness). Imports
`core.gba_emulator.GBAEmulator` UNMODIFIED -- read-only consumer, no edits to core/.

Difference from reports/probes/2026-07-25-gba-exam/gba_drive.py (which this supersedes for this
hunt): that script booted the ROM once per invocation and applied ONE action list. Platforming in
Kirby needs (a) many steps per boot and (b) BUTTON COMBOS (hold right while tapping A to float
rightwards) -- the Emulator Protocol's press() is strictly one button at a time. This driver adds a
`combo` action that drives `emu._core.set_keys(raw=...)` directly with an OR-ed bitmask. Reaching
into the private `_core` is deliberate and confined to this probe: it does NOT change core/, and the
oracle evidence never depends on it (combos only affect WHICH game states we reach, not what the
RAM says once we are there).

Run under the WSL mgba spike (reports/2026-06-29-gba-mgba-recipe.md):
  LD_LIBRARY_PATH=~/gba-spike \
  PYTHONPATH=~/gba-spike/mgba-build/python/lib.linux-x86_64-3.8:<repo_root> \
    ~/gba-spike/.venv/bin/python3 kgba_drive.py --plan plan.json

Plan JSON:
  {"rom": "...", "state_in": "... or null",
   "steps": [{"name": "s1", "actions": "right:20:4, combo:right+a:30:0, wait:60",
              "screenshot": "/abs/p.png", "state_out": "/abs/p.state",
              "watch": {"score": "0x02006020:u32"}}]}

Action tokens (comma separated, `*K` repeats):
  BUTTON | BUTTON:HOLD:SETTLE          single-button press via the Protocol's press()
  combo:B1+B2:HOLD:SETTLE              simultaneous buttons (probe-only, see docstring)
  wait:N                               advance N frames, no keys
"""
from __future__ import annotations

import argparse
import json
import sys

_BITS = {"a": 0x001, "b": 0x002, "select": 0x004, "start": 0x008, "right": 0x010,
         "left": 0x020, "up": 0x040, "down": 0x080, "r": 0x100, "l": 0x200}


def expand(spec: str) -> list[str]:
    out = []
    for raw in (spec or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        if "*" in raw:
            tok, n = raw.rsplit("*", 1)
            out.extend([tok] * int(n))
        else:
            out.append(raw)
    return out


def apply_action(emu, token: str) -> None:
    if token.startswith("wait:"):
        emu.tick(int(token.split(":", 1)[1]))
        return
    if token.startswith("combo:"):
        parts = token.split(":")
        mask = 0
        for b in parts[1].split("+"):
            mask |= _BITS[b.strip().lower()]
        hold = int(parts[2]) if len(parts) > 2 else 8
        settle = int(parts[3]) if len(parts) > 3 else 16
        emu._core.set_keys(raw=mask)          # probe-only; see module docstring
        for _ in range(hold):
            emu._core.run_frame()
        emu._core.set_keys(raw=0)
        for _ in range(max(0, settle)):
            emu._core.run_frame()
        return
    parts = token.split(":")
    emu.press(parts[0],
              hold_frames=int(parts[1]) if len(parts) > 1 else 8,
              settle_frames=int(parts[2]) if len(parts) > 2 else 16)


def read_width(emu, addr: int, width: str) -> int:
    if width == "u8":
        return emu.read(addr)
    n = {"u16": 2, "u32": 4}[width]
    v = 0
    for i in range(n):
        v |= emu.read(addr + i) << (8 * i)
    return v


def run_search(emu, cfg) -> None:
    """Greedy scripted platforming: each iteration tries every macro from the same state and keeps
    whichever maximises `objective` (Kirby's world-X). Purely a way to REACH game states cheaply --
    no oracle claim depends on it. Candidates that make the objective collapse (a death warp) are
    rejected via `max_drop`."""
    import os
    addr_s, width = cfg["objective"].split(":")
    addr = int(addr_s, 0)
    tmp = cfg["scratch"]
    best_path = os.path.join(tmp, "_srch_best.state")
    cand_path = os.path.join(tmp, "_srch_cand.state")
    macros = cfg["macros"]
    stall = 0
    for it in range(cfg.get("iters", 40)):
        emu.save_state(best_path)
        base = read_width(emu, addr, width)
        best_v, best_i = None, None
        for mi, m in enumerate(macros):
            emu.load_state(best_path)
            emu.tick(1)
            for tok in expand(m):
                apply_action(emu, tok)
            v = read_width(emu, addr, width)
            if base - v > cfg.get("max_drop", 150):
                continue                       # death warp / room reset -- not progress
            if best_v is None or v > best_v:
                best_v, best_i = v, mi
                emu.save_state(cand_path)
        if best_i is None:                     # every macro was a death: stay put
            emu.load_state(best_path)
            emu.tick(1)
            print(json.dumps({"iter": it, "obj": base, "macro": None}), flush=True)
            continue
        emu.load_state(cand_path)
        emu.tick(1)
        stall = stall + 1 if best_v <= base else 0
        print(json.dumps({"iter": it, "obj": best_v, "d": best_v - base, "macro": best_i}),
              flush=True)
        if cfg.get("snap_dir"):
            emu.save_screen(os.path.join(cfg["snap_dir"], f"s{it:03d}.png"))
            emu.save_state(os.path.join(cfg["snap_dir"], f"s{it:03d}.state"))
        if stall >= cfg.get("stall_stop", 6):
            print(json.dumps({"iter": it, "stalled": True}), flush=True)
            break


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    args = ap.parse_args()
    plan = json.load(open(args.plan))

    from core.gba_emulator import GBAEmulator
    emu = GBAEmulator(plan["rom"])
    if plan.get("state_in"):
        emu.load_state(plan["state_in"])
        emu.tick(1)                            # framebuffer is not part of the state

    for step in plan["steps"]:
        if step.get("state_in"):          # per-step reload => branch many variants from one boot
            emu.load_state(step["state_in"])
            emu.tick(1)
        if step.get("search"):
            run_search(emu, step["search"])
            continue
        for tok in expand(step.get("actions", "")):
            apply_action(emu, tok)
        rec = {"name": step.get("name"), "frame": emu.frame}
        watch = step.get("watch") or {}
        if watch:
            rec["watch"] = {}
            for name, spec in watch.items():
                addr_s, width = spec.split(":")
                rec["watch"][name] = read_width(emu, int(addr_s, 0), width)
        if step.get("screenshot"):
            emu.save_screen(step["screenshot"])
        if step.get("state_out"):
            emu.save_state(step["state_out"])
        print(json.dumps(rec, sort_keys=True), flush=True)

    emu.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
