"""Gate 0 Arm R human-baseline capture rig (Pokemon Red, bedroom -> starter -> rival win).

HARD LAW: this script only launches the emulator, times, records, and writes artifacts. It never
presses a button and never decides an action -- the actual playthrough must be performed by a human
(David) on the real keyboard, watching the real PyBoy SDL2 window. That is what makes the resulting
wall_clock_s/primitive_actions numbers a valid human baseline for the R0 "<=2.0x human" bar
(reports/2026-07-13-minimum-north-star-gate-0-design.md "Capability bar"; provenance requirement
from reports/2026-07-18-gate0-prereg.md precondition 6, "who/when").

Reuses, rather than reinvents:
  * games.pokemon_red.memory_map.read_state / world_mcp.GAMES["pokemon_red"]["watch"] for the exact
    RAM addresses the real agent-facing oracle uses (never duplicated/guessed here).
  * eval.score_gate0._red_success -- the SAME frozen end-state predicate the paid scorer will run
    against the agent's own trajectory -- to detect completion live and to score this human run.
    (eval/score_gate0.py landed on `main` via PR #114 on 2026-07-18, merged same day as this rig's
    branch point; earlier readiness/pre-reg drafts describing it as "not yet on main" are stale.)
  * games.pokemon_red.emulator.ensure_sdl_dll_path + PyBoy's own default SDL2 keymap (arrows=d-pad,
    'a'=A, 's'=B, Enter=Start, Backspace=Select -- see human_play.py), same convention as the
    project's other human-play scripts (human_play.py, play_record.py).

Usage (see DAVID_BASELINES.md for the full walkthrough):
    uv run python tools/capture_gate0_baseline_red.py

Writes, on a DETECTED SUCCESS (oracle-only end-state, exactly eval.score_gate0._red_success):
    runs/gate0_human_baseline/red/human_metrics.json   -- schema_version 1, arm=red, role=human,
                                                           mode=readiness_dev, wall_clock_s,
                                                           primitive_actions (+ provenance extras)
    runs/gate0_human_baseline/red/oracle.jsonl          -- append-only watch-row trace (raw data law)

An incomplete/quit/crashed attempt writes a distinctly-named
`human_metrics.INCOMPLETE_<unix-ts>.json` instead of the canonical file, so a botched capture can
never silently masquerade as a banked baseline (see DAVID_BASELINES.md's re-run rule).
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARM = "red"
MODE = "readiness_dev"   # the only mode this rig supports; the paid-seed human replay (if Red ever
                          # needs one -- Red has no held-out seed family, unlike MiniWoB) is out of
                          # scope for this readiness-phase capture rig.
REAL_OUT = os.path.normpath(str(ROOT / "runs" / "gate0_human_baseline" / "red"))
# Rows sampled continuously (not one-per-keypress): the frozen predicate needs 10 CONSECUTIVE watch
# rows showing a sustained battle exit, which idle/movement time must also be able to satisfy.
SAMPLE_EVERY_FRAMES = 15   # ~0.25s at ~60fps


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _under_real_path(out: str) -> bool:
    norm = os.path.normpath(os.path.abspath(out))
    real = os.path.normpath(os.path.abspath(REAL_OUT))
    return norm == real or norm.startswith(real + os.sep)


def run(args, max_frames: int | None = None) -> int:
    """`max_frames` is a Python-only testability seam (never exposed on the CLI, see main()): it caps
    the interactive loop so an in-process test can exercise the full boot/log/write path without a
    real window-close or Ctrl-C. It never presses a button; a capped run with zero human input simply
    writes an INCOMPLETE artifact, exactly like a human closing the window immediately would."""
    if not os.path.exists(args.rom):
        print(f"ROM not found: {args.rom}", file=sys.stderr)
        return 2
    if not os.path.exists(args.state):
        print(f"savestate not found: {args.state} -- see DAVID_BASELINES.md "
              "(and runs/gate0_readiness_2026-07-14/ receipts) for how to obtain it.", file=sys.stderr)
        return 2

    if args.test and _under_real_path(args.out):
        print(f"--test refuses to write under the real baseline path {REAL_OUT!r}; "
              "pass a scratch --out.", file=sys.stderr)
        return 2
    if not args.test and not _under_real_path(args.out):
        print(f"warning: --out {args.out!r} is outside the canonical real baseline path "
              f"{REAL_OUT!r} (fine for a manual dry run; DAVID_BASELINES.md uses the default).",
              file=sys.stderr)

    os.makedirs(args.out, exist_ok=True)
    rom_sha256 = _sha256_file(args.rom)
    state_sha256 = _sha256_file(args.state)

    import world_mcp
    from eval.score_gate0 import _red_success
    from games.pokemon_red.emulator import ensure_sdl_dll_path

    watch_spec = world_mcp.GAMES["pokemon_red"]["watch"]   # single source of truth for RAM addresses

    ensure_sdl_dll_path()
    from pyboy import PyBoy
    import sdl2

    pb = PyBoy(args.rom, window="SDL2")
    pb.set_emulation_speed(1)
    with open(args.state, "rb") as f:
        pb.load_state(f)
    pb.tick(4, render=True)

    rd = lambda a: pb.memory[a]

    def read_watch() -> dict:
        return {name: int(rd(addr)) for name, addr in watch_spec.items()}

    fresh_party = read_watch().get("party")
    if fresh_party != 0:
        print(f"warning: loaded state already has party={fresh_party} (expected a fresh 0) -- "
              "this is not a fresh bedroom baseline start; the predicate will reject it.",
              file=sys.stderr)

    oracle_path = os.path.join(args.out, "oracle.jsonl")
    oracle = open(oracle_path, "a", encoding="utf-8")
    rows: list[dict] = []
    step_n = 0

    def log_row() -> None:
        nonlocal step_n
        row = {"step": step_n, "t": time.time(), "frame": pb.frame_count, "watch": read_watch()}
        rows.append(row)
        oracle.write(json.dumps(row) + "\n")
        oracle.flush()
        step_n += 1

    # PyBoy's default SDL2 keymap (human_play.py), expressed as SCANCODES (physical keys), not
    # KEYCODES: SDL_GetKeyboardState() returns a SCANCODE-indexed array -- indexing it with a KEYCODE
    # (e.g. pyboy.plugins.window_sdl2.KEY_DOWN's SDLK_UP == 1073741906) reads out of bounds and
    # segfaults. play_record.py's own hotkeys() polls the same way, via SDL_SCANCODE_* constants.
    gameplay_scancodes = [
        sdl2.SDL_SCANCODE_UP, sdl2.SDL_SCANCODE_DOWN, sdl2.SDL_SCANCODE_LEFT, sdl2.SDL_SCANCODE_RIGHT,
        sdl2.SDL_SCANCODE_A, sdl2.SDL_SCANCODE_S, sdl2.SDL_SCANCODE_RETURN, sdl2.SDL_SCANCODE_BACKSPACE,
    ]
    held = {sc: False for sc in gameplay_scancodes}
    nkeys = ctypes.c_int(0)

    print(f"Loaded {args.rom} ({rom_sha256[:12]}...) + {args.state} ({state_sha256[:12]}...).")
    print(f"Fresh state party count: {fresh_party}.")
    print("Controls (PyBoy defaults): arrows=move  A=A  S=B  Enter=Start  Backspace=Select.")
    print('Task: "From the fresh bedroom start, obtain your first Pokemon from Professor Oak and '
          'win the first rival battle."')
    print("The timer starts on your FIRST button press. Close the window (or Ctrl-C) when you are "
          "done, or to abort.")

    log_row()   # row 0: the fresh state, before any human input

    first_input_perf: float | None = None
    started_at = None
    press_count = 0
    success = False
    failures: list[str] = ["red_not_fresh_party_zero"] if fresh_party != 0 else ["no_input_yet"]
    frames_since_sample = 0

    try:
        frame_i = 0
        while max_frames is None or frame_i < max_frames:
            frame_i += 1
            if not pb.tick(1, True):
                break
            ks = sdl2.SDL_GetKeyboardState(ctypes.byref(nkeys))
            for scancode in gameplay_scancodes:
                now = bool(ks[scancode])
                if now and not held[scancode]:
                    press_count += 1
                    if first_input_perf is None:
                        first_input_perf = time.perf_counter()
                        started_at = datetime.now(timezone.utc)
                        print("[timer started -- first input detected]")
                held[scancode] = now
            frames_since_sample += 1
            if frames_since_sample >= SAMPLE_EVERY_FRAMES:
                frames_since_sample = 0
                log_row()
                if not success and first_input_perf is not None:
                    ok, failures = _red_success(rows)
                    if ok:
                        success = True
                        elapsed = time.perf_counter() - first_input_perf
                        print(f"[task complete -- presses={press_count} wall_clock={elapsed:.1f}s] "
                              "close the window (or Ctrl-C) to finish and write the baseline.")
    except KeyboardInterrupt:
        pass
    finally:
        log_row()
        oracle.close()
        pb.stop(save=False)

    wall_clock_s = (time.perf_counter() - first_input_perf) if first_input_perf is not None else 0.0
    completed_at = datetime.now(timezone.utc)

    metrics = {
        "schema_version": 1,
        "arm": ARM,
        "role": "human",
        "mode": MODE,
        "wall_clock_s": round(wall_clock_s, 3),
        "primitive_actions": press_count,
        "success": success,
        "failures": failures,
        "player": args.player if not args.test else f"TEST:{args.player}",
        "started_at": started_at.isoformat() if started_at else None,
        "completed_at": completed_at.isoformat(),
        "rom_path": os.path.normpath(args.rom),
        "rom_sha256": rom_sha256,
        "savestate_path": os.path.normpath(args.state),
        "savestate_sha256": state_sha256,
        "oracle_path": os.path.normpath(oracle_path),
        "test_mode": bool(args.test),
    }
    name = "human_metrics.json" if success else f"human_metrics.INCOMPLETE_{int(time.time())}.json"
    metrics_path = os.path.join(args.out, name)
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, sort_keys=True)
        f.write("\n")

    print(("PASS" if success else "INCOMPLETE") + f" -- wrote {metrics_path}")
    print(json.dumps(metrics, sort_keys=True))
    return 0 if success else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rom", default=str(ROOT / "roms" / "PokemonRed.gb"))
    ap.add_argument("--state", default=str(ROOT / "runs" / "red_start.state"))
    ap.add_argument("--out", default=REAL_OUT)
    ap.add_argument("--player", default="David")
    ap.add_argument("--test", action="store_true",
                     help="throwaway smoke-test mode: refuses to write under the real baseline path")
    return run(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
