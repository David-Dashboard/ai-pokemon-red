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

Three modes, selected with a REQUIRED `--mode` (see "Why --mode has no default" below):
  * `readiness_dev` -- the readiness-phase capture. This is the mode the banked
    `runs/gate0_human_baseline/red/human_metrics.json` was produced under, and its behaviour is
    byte-identical to the pre-`--mode` rig.
  * `paid_gate0` -- Gate 0 v1's paid mode.
  * `paid_gate0_v2` -- Gate 0 v2's paid mode (reports/2026-07-25-gate0-v2-prereg.md P1c).

Unlike Arm W, Red has NO held-out seed family: the design doc's "Red uses the same fixed start for
agent and human" means every mode replays the SAME savestate against the SAME frozen predicate. So
`--mode` here changes exactly two things -- the `mode` field stamped into `human_metrics.json` (which
eval/score_gate0.py::_verify_sources requires to EQUAL the mode being scored) and which directory the
artifact lands in. It does NOT change the task, the seeds, the predicate, or what David is shown.
Both paid modes are still gated behind `--i-am-human`, for the reason in HELD_OUT_MODES' comment.

Usage (see DAVID_BASELINES.md for the full walkthrough):
    uv run python tools/capture_gate0_baseline_red.py --mode readiness_dev
    uv run python tools/capture_gate0_baseline_red.py --mode paid_gate0_v2 --i-am-human

Writes, on a DETECTED SUCCESS (oracle-only end-state, exactly eval.score_gate0._red_success):
    <out>/human_metrics.json   -- schema_version 1, arm=red, role=human, mode=<--mode>,
                                   wall_clock_s, primitive_actions (+ provenance extras)
    <out>/oracle.jsonl          -- append-only watch-row trace (raw data law)

`<out>` defaults per mode (all gitignored under runs/, never committed) -- one directory PER MODE so
a paid capture can never overwrite, or be confused with, the banked readiness_dev one:
    readiness_dev -> runs/gate0_human_baseline/red/          (unchanged; the banked artifact)
    paid_gate0    -> runs/gate0_paid_human_baseline/red/
    paid_gate0_v2 -> runs/gate0_paid_v2_human_baseline/red/
This mirrors tools/capture_gate0_baseline_miniwob.py's MODE_CONFIG exactly. It is NOT derived from
the mode's source-pins fixture, deliberately: all three fixtures currently pin `artifact_paths.
red_human` at the readiness_dev path, so deriving the OUTPUT from the pin would make a v2 capture
overwrite a banked artifact that three fixtures freeze by digest -- precisely what the prereg
(:264-269) forbids when it requires "a FRESH CAPTURE ... producing a new artifact". The pin is used
as a CROSS-CHECK instead (see require_fixture_points_here).

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

Why `--mode` has NO default (same decision as tools/gate0_appserver_arm.py's --mode, PR #192): the
defect this argument closes is a SILENT one. Until 2026-07-28 this rig hardcoded
`MODE = "readiness_dev"`, so every artifact it produced was stamped readiness_dev -- and
`_verify_sources` (score_gate0.py, the `human_metric_identity:<arm>` check) rejects that under any
paid mode, a failure discovered only at SCORING, after the paid run is spent. A default of
`readiness_dev` would preserve exactly that trap for anyone who forgets the flag. The choices are
read from `eval.score_gate0.MODES` itself (score_gate0_modes(), a function-local import matching
tools/capture_gate0_baseline_miniwob.py's existing tools->eval idiom), so this rig can never offer a
mode the scorer cannot score.
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
# Per-mode output directory. Same shape and same purpose as
# tools/capture_gate0_baseline_miniwob.py's MODE_CONFIG -- the two rigs are peers and any divergence
# between them is how the missing `--mode` survived here for a week after it landed there.
# readiness_dev's entry is the exact literal this module used to hold as the unconditional REAL_OUT,
# so that mode's output path is unchanged.
MODE_CONFIG = {
    "readiness_dev": {
        "real_out": os.path.normpath(str(ROOT / "runs" / "gate0_human_baseline" / "red")),
    },
    "paid_gate0": {
        "real_out": os.path.normpath(str(ROOT / "runs" / "gate0_paid_human_baseline" / "red")),
    },
    "paid_gate0_v2": {
        "real_out": os.path.normpath(str(ROOT / "runs" / "gate0_paid_v2_human_baseline" / "red")),
    },
}
# Modes whose artifact becomes a PRE-REGISTERED GATE DENOMINATOR: they require --i-am-human and are
# cross-checked against their own source-pins fixture before a single frame is emulated.
#
# The rationale differs from MiniWoB's and that difference is deliberate, not an oversight. There,
# HELD_OUT_MODES protects held-out SEEDS (the rig also suppresses the task utterance for them). Red
# has no held-out seed family at all -- the task text is public, printed in full, and identical in
# every mode -- so there is nothing here to suppress. What --i-am-human protects on this arm is the
# ARTIFACT: a paid-mode human_metrics.json is the denominator the `agent <= 2.0x human` bar is
# measured against, and it must never be produced by a casual or scripted invocation.
HELD_OUT_MODES = frozenset({"paid_gate0", "paid_gate0_v2"})
# Backward-compatible alias: the DEV real path as a module constant, same as the MiniWoB rig exposes.
REAL_OUT = MODE_CONFIG["readiness_dev"]["real_out"]
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


def _under_real_path(out: str, real_out: str = REAL_OUT) -> bool:
    norm = os.path.normpath(os.path.abspath(out))
    real = os.path.normpath(os.path.abspath(real_out))
    return norm == real or norm.startswith(real + os.sep)


def score_gate0_modes() -> dict:
    """`eval.score_gate0.MODES` -- the frozen scorer's own mode map, read from the scorer and NEVER
    re-declared here, so this rig cannot offer a mode the scorer cannot score.

    Function-local import, matching tools/capture_gate0_baseline_miniwob.py's existing tools->eval
    idiom (`from eval.score_gate0 import MODES` inside run()), so importing this module does not drag
    in eval/."""
    from eval.score_gate0 import MODES
    return MODES


def pinned_red_human_path(mode: str) -> Path:
    """The absolute path `mode`'s source-pins fixture pins for `red_human`, resolved EXACTLY as
    eval/score_gate0.py::_verify_sources resolves it -- relative entries against the scorer's own
    ROOT, absolute ones left alone.

    DUPLICATION, DECLARED: PR #192 adds an identical `pinned_artifact_path(mode, key)` to
    tools/gate0_appserver_arm.py. Reusing it was the intent and is not possible here -- #192 is not
    merged, so the symbol does not exist on `origin/main` (this branch's base), and that file is
    off-limits to this change. Two resolutions of one pin is exactly the drift class this whole
    workstream exists to remove, so this copy is a KNOWN TEMPORARY: once both land, lift one shared
    helper and delete both. Flagged in the PR body, not left for a reader to discover."""
    from eval.score_gate0 import ROOT as SCORER_ROOT, SOURCE_PIN_FILES
    pins = json.loads(SOURCE_PIN_FILES[mode].read_text(encoding="utf-8"))
    path = Path(pins["artifact_paths"]["red_human"])
    return (path if path.is_absolute() else SCORER_ROOT / path).resolve()


def require_fixture_points_here(mode: str, real_out: str) -> str | None:
    """VALIDATE AND REFUSE: does `mode`'s own source-pins fixture actually point at the file this
    capture is about to write? Returns a refusal message, or None if it does.

    Without this the failure is silent and expensive in the way this project keeps getting caught by:
    the capture succeeds, the artifact is perfect, and the scorer reads a DIFFERENT file -- the
    banked readiness_dev one, whose `mode` is wrong -- so the verdict is `human_metric_identity:red`
    -> INSUFFICIENT_DATA anyway, discovered only after the paid run.

    Deriving the output directory from the pin instead would NOT fix that; it would reinstate a worse
    defect (#192's F2 lesson). All three fixtures pin `red_human` at the SAME banked file today, so a
    derived output would send a v2 capture straight into `runs/gate0_human_baseline/red/`, overwriting
    an append-only artifact whose digest all three fixtures freeze -- breaking readiness_dev and
    paid_gate0 scoring at the same time. Validate and refuse; never derive.

    HELD-OUT MODES ONLY, and that scoping is deliberate rather than convenient: readiness_dev's
    baseline is already captured, already banked, and its pin is already frozen to exactly this file,
    so re-checking it at capture time protects nothing and would add a new way for a legitimate
    --allow-retake to fail. It also keeps the readiness_dev path literally untouched by this change,
    which is what the differential in the PR body proves."""
    if mode not in HELD_OUT_MODES:
        return None
    target = Path(os.path.join(real_out, "human_metrics.json")).resolve()
    try:
        pinned = pinned_red_human_path(mode)
    except Exception as exc:
        return (f"refusing: cannot read {mode!r}'s source-pins fixture to confirm where the scorer "
                f"will look for the Red human baseline ({exc}).")
    if pinned != target:
        return (
            f"refusing: eval/score_gate0.py will read the {mode!r} Red human baseline from\n"
            f"    {pinned}\n"
            f"but this capture writes to\n"
            f"    {target}\n"
            f"so the artifact you are about to spend your time producing would never be scored.\n"
            f"Fix the FIXTURE, not this rig, and not the banked artifact: set artifact_paths."
            f"red_human in eval/fixtures/gate0_{'paid_v2' if mode == 'paid_gate0_v2' else 'paid'}"
            f"_source_pins.json to the second path above (leaving artifact_sha256.red_human as its "
            f"PENDING_ placeholder until this capture exists), in its own reviewed commit -- prereg "
            f"P1c. Editing runs/gate0_human_baseline/red/human_metrics.json instead is explicitly "
            f"forbidden (reports/2026-07-25-gate0-v2-prereg.md:264-269): it is append-only raw data "
            f"and three fixtures freeze its digest.")
    return None


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
        # Was the module-level constant MODE = "readiness_dev". eval/score_gate0.py::_verify_sources
        # requires this to EQUAL the mode being scored, so a hardwired stamp makes every paid-mode
        # capture void -- and only at scoring. Prereg P1c.
        "mode": args.mode,
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
    # --- mode resolution + the two mode guards, before any file is touched -----------------------
    # Same order and same shape as tools/capture_gate0_baseline_miniwob.py::run().
    mode = getattr(args, "mode", None)
    if mode not in MODE_CONFIG:
        print(f"refusing: unknown --mode {mode!r} (must be one of {sorted(MODE_CONFIG)}).",
              file=sys.stderr)
        return 2
    real_out = MODE_CONFIG[mode]["real_out"]
    if args.out is None:
        args.out = real_out

    # Held-out law, this arm's version (see HELD_OUT_MODES): an explicit, un-default-able
    # acknowledgement that a real human is about to play. Fires for EVERY paid-mode invocation,
    # canonical path or not -- the sensitive thing is producing a paid-mode denominator at all, not
    # just where it lands.
    if mode in HELD_OUT_MODES and not getattr(args, "i_am_human", False):
        print(f"refusing: --mode {mode} requires --i-am-human -- this captures the human "
              "denominator the paid gate's `agent <= 2.0x human` bar is measured against; a "
              "scripted or absent-minded invocation must never be able to produce it. Pass "
              "--i-am-human only when a real human is about to play this task at the keyboard.",
              file=sys.stderr)
        return 2

    refusal = require_fixture_points_here(mode, real_out)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 2

    if not os.path.exists(args.rom):
        print(f"ROM not found: {args.rom}", file=sys.stderr)
        return 2
    if not os.path.exists(args.state):
        print(f"savestate not found: {args.state} -- see DAVID_BASELINES.md "
              "(and runs/gate0_readiness_2026-07-14/ receipts) for how to obtain it.", file=sys.stderr)
        return 2

    if args.test and _under_real_path(args.out, real_out):
        print(f"--test refuses to write under the real baseline path {real_out!r}; "
              "pass a scratch --out.", file=sys.stderr)
        return 2
    if not args.test and not _under_real_path(args.out, real_out):
        print(f"warning: --out {args.out!r} is outside the canonical real baseline path "
              f"{real_out!r} (fine for a manual dry run; DAVID_BASELINES.md uses the default).",
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

    # This rig appends to <out>/oracle.jsonl and the success check re-reads that WHOLE file, so any
    # stale trace left over from an earlier session (a legitimate --allow-retake, or a crash/abort
    # before the canonical write) would have its rows prepended to the new attempt's, corrupting the
    # party/battle/exit index logic in eval.score_gate0._red_success. Archive whenever a prior trace
    # exists at session start, regardless of whether a canonical human_metrics.json exists -- same
    # pattern as the MiniWoB rig (PR #119). Renamed, never deleted -- append-only law -- and never
    # clobbered on same-second name collisions.
    prior_oracle_path = os.path.join(args.out, "oracle.jsonl")
    if os.path.exists(prior_oracle_path):
        base = os.path.join(args.out, f"oracle.attempt{max(attempt_number - 1, 1)}_{int(time.time())}")
        archive_path, n = f"{base}.jsonl", 0
        while os.path.exists(archive_path):
            n += 1
            archive_path = f"{base}_{n}.jsonl"
        os.replace(prior_oracle_path, archive_path)
        print(f"[stale oracle trace from a previous session archived -> {archive_path}]")

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


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # REQUIRED, NO DEFAULT -- see the module docstring's "Why --mode has no default". Choices come
    # from the frozen scorer's own MODES map, never a list re-declared here.
    ap.add_argument("--mode", required=True, choices=tuple(score_gate0_modes()),
                     help="which pre-registered Gate 0 mode this capture belongs to; stamps "
                          "human_metrics.json's `mode` field (which eval/score_gate0.py requires to "
                          "equal the mode being scored) and selects the output directory. Both paid "
                          "modes additionally require --i-am-human. No default: an unstated mode is "
                          "an artifact the scorer rejects.")
    ap.add_argument("--rom", default=str(ROOT / "roms" / "PokemonRed.gb"))
    ap.add_argument("--state", default=str(ROOT / "runs" / "red_start.state"))
    ap.add_argument("--out", default=None,
                     help="defaults to the canonical real path for --mode (see module docstring).")
    ap.add_argument("--player", default="David")
    ap.add_argument("--i-am-human", action="store_true", dest="i_am_human",
                     help="required for every held-out mode (HELD_OUT_MODES: paid_gate0, "
                          "paid_gate0_v2) -- explicit, non-default acknowledgement that a real human "
                          "is about to play this task. A scripted invocation cannot satisfy this by "
                          "accident.")
    ap.add_argument("--test", action="store_true",
                     help="throwaway smoke-test mode: refuses to write under the real baseline path")
    ap.add_argument("--allow-retake", metavar="REASON", default=None,
                     help="required to overwrite an existing canonical human_metrics.json -- state "
                          "why this is a legitimate re-take (a botched capture), not a rerun to "
                          "chase a better score.")
    return ap


def main() -> int:
    return run(build_arg_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
