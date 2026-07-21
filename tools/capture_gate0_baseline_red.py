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

Clock/press-count discipline: `wall_clock_s`/`primitive_actions` are FROZEN the instant the oracle
(`_red_success`) first detects the real end-state, not whenever David happens to notice and close
the window. The window then auto-closes itself a few seconds later (COMPLETION_GRACE_SECONDS) as an
unmissable, reaction-time-independent "you're done" signal -- no informal wandering time can leak
into the banked numbers.

One cold attempt per task (the exam law -- see DAVID_BASELINES.md "Re-run rule"): this script
refuses to overwrite an existing canonical `human_metrics.json` unless `--allow-retake "<reason>"`
is passed; the artifact then records `attempt_number` (1 for a first attempt) and `retake_reason`
(empty for a first attempt).
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
# How long the window stays open, purely for cosmetic wind-down, after the oracle detects success
# and the metrics are already frozen -- then it closes itself so "David didn't notice the message"
# can never inflate the banked wall_clock_s/press_count.
COMPLETION_GRACE_SECONDS = 4.0


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


def _atomic_write_json(path: str, payload: dict) -> None:
    """temp file + os.replace so a crash mid-write can never leave a truncated/corrupt artifact at
    `path` -- matches the append-only/fail-closed treatment the rest of the rig already gives
    oracle.jsonl and INCOMPLETE files. On a crash the temp file itself is also cleaned up, so
    neither `path` nor a stray partial file survives."""
    tmp = f"{path}.tmp{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _build_metrics(args, *, rom_sha256: str, state_sha256: str, oracle_path: str,
                    wall_clock_s: float, press_count: int, success: bool, failures: list[str],
                    started_at, completed_at, attempt_number: int, retake_reason: str,
                    input_event_times: list[float]) -> dict:
    """Pure artifact-shape builder, factored out so the schema (mode/attempt_number/retake_reason/
    input_event_times included) is unit-testable without a real PyBoy/SDL2 window -- see
    tests/test_capture_gate0_baseline_red.py."""
    return {
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
        # one-cold-attempt bookkeeping (DAVID_BASELINES.md "Re-run rule"): attempt_number is 1 for a
        # normal first capture; retake_reason is only ever non-empty when --allow-retake overrode an
        # existing canonical human_metrics.json.
        "attempt_number": attempt_number,
        "retake_reason": retake_reason,
        # Per-input-event epoch timestamps (time.time()), independent of the aggregate
        # primitive_actions count -- lets a future auditor check press cadence directly instead of
        # trusting the aggregate alone (fairness review Minor 2). Includes any presses during the
        # post-detection grace window; the first `primitive_actions` entries are the ones the banked
        # wall_clock_s/primitive_actions numbers were frozen against.
        "input_event_times": input_event_times,
    }


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

    # One cold attempt per task (the exam law): refuse to clobber an existing canonical artifact
    # unless David explicitly says this is a legitimate re-take and why.
    allow_retake = (args.allow_retake or "").strip()
    canonical_path = os.path.join(args.out, "human_metrics.json")
    attempt_number = 1
    retake_reason = ""
    if os.path.exists(canonical_path):
        if not allow_retake:
            print(f"refusing: {canonical_path} already exists -- one cold attempt per task (see "
                  "DAVID_BASELINES.md's re-run rule). Pass --allow-retake \"<reason>\" if this is a "
                  "legitimate re-take of a genuinely botched capture, not a rerun to chase a better "
                  "score.", file=sys.stderr)
            return 2
        try:
            prior = json.loads(Path(canonical_path).read_text(encoding="utf-8"))
            attempt_number = int(prior.get("attempt_number") or 1) + 1
        except Exception:
            attempt_number = 2
        retake_reason = allow_retake

    os.makedirs(args.out, exist_ok=True)
    rom_sha256 = _sha256_file(args.rom)
    state_sha256 = _sha256_file(args.state)
    oracle_path = os.path.join(args.out, "oracle.jsonl")

    import world_mcp
    from eval.score_gate0 import _red_success
    from games.pokemon_red.emulator import ensure_sdl_dll_path

    watch_spec = world_mcp.GAMES["pokemon_red"]["watch"]   # single source of truth for RAM addresses

    ensure_sdl_dll_path()
    from pyboy import PyBoy
    import sdl2

    # PyBoy/SDL2 window construction + savestate load, guarded: a corrupt/incompatible savestate or
    # any other setup failure here now goes through the same clean-abort path as the rest of the
    # rig (no orphaned SDL2 window, an INCOMPLETE artifact instead of a bare traceback + nothing).
    pb = None
    try:
        pb = PyBoy(args.rom, window="SDL2")
        pb.set_emulation_speed(1)
        with open(args.state, "rb") as f:
            pb.load_state(f)
        pb.tick(4, render=True)
    except Exception as exc:
        if pb is not None:
            pb.stop(save=False)
        metrics = _build_metrics(
            args, rom_sha256=rom_sha256, state_sha256=state_sha256, oracle_path=oracle_path,
            wall_clock_s=0.0, press_count=0, success=False,
            failures=[f"setup_failed:{type(exc).__name__}"], started_at=None,
            completed_at=datetime.now(timezone.utc), attempt_number=attempt_number,
            retake_reason=retake_reason, input_event_times=[])
        metrics_path = os.path.join(args.out, f"human_metrics.INCOMPLETE_{int(time.time())}.json")
        _atomic_write_json(metrics_path, metrics)
        print(f"ERROR during PyBoy/savestate setup ({type(exc).__name__}: {exc}) -- wrote "
              f"{metrics_path}", file=sys.stderr)
        return 2

    rd = lambda a: pb.memory[a]

    def read_watch() -> dict:
        return {name: int(rd(addr)) for name, addr in watch_spec.items()}

    fresh_party = read_watch().get("party")
    if fresh_party != 0:
        print(f"warning: loaded state already has party={fresh_party} (expected a fresh 0) -- "
              "this is not a fresh bedroom baseline start; the predicate will reject it.",
              file=sys.stderr)

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
    print(f"The timer starts on your FIRST button press. The window auto-closes "
          f"{COMPLETION_GRACE_SECONDS:.0f}s after the task is detected complete -- or close it "
          "yourself (or Ctrl-C) any time to finish early or abort.")

    log_row()   # row 0: the fresh state, before any human input

    first_input_perf: float | None = None
    started_at = None
    press_count = 0
    input_event_times: list[float] = []
    success = False
    failures: list[str] = ["red_not_fresh_party_zero"] if fresh_party != 0 else ["no_input_yet"]
    frames_since_sample = 0
    # Frozen at the instant of oracle-detected completion (fairness review Major 1) -- everything
    # after that is cosmetic wind-down and must never change the banked numbers.
    frozen_wall_clock_s: float | None = None
    frozen_press_count: int | None = None
    grace_deadline: float | None = None

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
                    input_event_times.append(time.time())
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
                        frozen_wall_clock_s = time.perf_counter() - first_input_perf
                        frozen_press_count = press_count
                        grace_deadline = time.perf_counter() + COMPLETION_GRACE_SECONDS
                        print("=" * 60)
                        print(f"[TASK COMPLETE -- presses={frozen_press_count} "
                              f"wall_clock={frozen_wall_clock_s:.1f}s -- metrics frozen]")
                        print(f"[window auto-closes in {COMPLETION_GRACE_SECONDS:.0f}s -- "
                              "or close it now]")
                        print("=" * 60)
            if grace_deadline is not None and time.perf_counter() >= grace_deadline:
                print("[auto-close: grace period elapsed]")
                break
    except KeyboardInterrupt:
        pass
    finally:
        log_row()
        oracle.close()
        pb.stop(save=False)

    if frozen_wall_clock_s is not None:
        wall_clock_s = frozen_wall_clock_s
        final_press_count = frozen_press_count
    else:
        wall_clock_s = (time.perf_counter() - first_input_perf) if first_input_perf is not None else 0.0
        final_press_count = press_count
    completed_at = datetime.now(timezone.utc)

    metrics = _build_metrics(
        args, rom_sha256=rom_sha256, state_sha256=state_sha256, oracle_path=oracle_path,
        wall_clock_s=wall_clock_s, press_count=final_press_count, success=success,
        failures=failures, started_at=started_at, completed_at=completed_at,
        attempt_number=attempt_number, retake_reason=retake_reason,
        input_event_times=input_event_times)
    name = "human_metrics.json" if success else f"human_metrics.INCOMPLETE_{int(time.time())}.json"
    metrics_path = os.path.join(args.out, name)
    _atomic_write_json(metrics_path, metrics)

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
    ap.add_argument("--allow-retake", metavar="REASON", default=None,
                     help="required to overwrite an existing canonical human_metrics.json -- state "
                          "why this is a legitimate re-take (a botched capture), not a rerun to "
                          "chase a better score.")
    return run(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
