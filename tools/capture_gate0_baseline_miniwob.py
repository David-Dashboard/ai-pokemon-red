"""Gate 0 Arm W human-baseline capture rig (MiniWoB click-checkboxes).

Two modes, selected with `--mode`:
  * `readiness_dev` (the default) -- DEV seeds 0..4, a readiness estimate only.
  * `paid_gate0` -- the HELD-OUT seeds `eval.score_gate0.MODES["paid_gate0"]` pins (1000..1004),
    the paid gate's actual human denominator for the MiniWoB arm. Sanctioned use is post-Arm-W-only:
    David replays these 5 episodes AFTER the paid agent's Arm W attempt is already banked (never
    before -- see DAVID_BASELINES.md's warning box and reports/2026-07-13-minimum-north-star-
    gate-0-design.md:273-276). `--mode paid_gate0` additionally requires `--i-am-human` (see below)
    -- a scripted stand-in must never be able to produce this artifact.

HARD LAW: this script only launches episodes, times, records, and writes artifacts. It never picks a
click/type/key action -- every action comes from David, typed at the terminal after he has LOOKED AT
the actual rendered screenshot for that step. The rig is a relay, not a player.

Design choice (documented per the build instructions, since the literal "David plays in a real
browser" path was considered and rejected -- see DAVID_BASELINES.md for the fuller writeup): MiniWoB
only ever runs inside the `miniwob-mcp-world` Docker image (miniwob/selenium are intentionally NEVER
installed in the main project env -- Dockerfile.miniwob). Driving a REAL visible browser window
through that container would need either host GUI passthrough or the base image's bundled noVNC, and
correctly detecting a human's native click as an episode-terminating action would require reverse-
engineering the Farama-rewrite's internal JS/webdriver state -- neither of which is inspectable or
testable in this environment (the package is Docker-image-only). Instead this rig reuses the EXACT
same code path the paid agent will use -- `world_mcp.MiniWobSession.call()` -- and asks David to look
at each step's real screenshot (the same pixels the agent would see) and type the click/type/key
action he wants performed. This is the smallest glue that is still screen-pixels-in +
keyboard-mediated-mouse-out, needs zero new dependencies, and is exercised by the SAME
FakeMiniwobEnv-based test seam tests/test_miniwob_world.py already uses -- so it is actually testable
here, unlike the live-browser alternative.

Reuses:
  * world_mcp.MiniWobSession -- identical dispatch/oracle-logging/viewport-rejection the agent gets.
  * eval.score_gate0._miniwob_success / MINIWOB_TASK / MODES["readiness_dev"] -- the SAME frozen
    5/5-non-abandoned-reward-1.0 predicate the paid scorer runs, applied here to score the human run.
  * eval/fixtures/gate0_miniwob_dev_seeds.json -- the frozen DEV seed manifest (0..4), never overridden.

Deployment: MiniWobSession needs the real `miniwob`/`selenium` packages, which only exist inside the
`miniwob-mcp-world` image (docker build -f Dockerfile.miniwob -t miniwob-mcp-world .). Run this
script inside that image by bind-mounting it over the entrypoint (see DAVID_BASELINES.md for the
exact command) -- no Dockerfile change needed.

Writes, on a DETECTED SUCCESS (5/5 non-abandoned reward-1.0 episodes, exactly
eval.score_gate0._miniwob_success):
    <out>/human_metrics.json  -- schema_version 1, arm=miniwob, role=human, mode=<--mode>,
                                  wall_clock_s, primitive_actions (+extras)
    <out>/oracle.jsonl         -- MiniWobSession's own oracle writer
    <out>/ep<N>_step<K>.png    -- what David was shown at each decision

`<out>` defaults per mode (both gitignored under runs/, never committed):
    readiness_dev -> runs/gate0_human_baseline/miniwob/
    paid_gate0    -> runs/gate0_paid_human_baseline/miniwob/  (the exact path
                     eval/fixtures/gate0_paid_source_pins.json's artifact_paths.miniwob_human names)

An incomplete/quit attempt writes `human_metrics.INCOMPLETE_<unix-ts>.json` instead of the canonical
file (see DAVID_BASELINES.md's re-run rule).

HELD-OUT LAW: seeds 1000..1004 must never be exposed to a dev/build process -- this script is
parameterized and CI-tested only against DEV seeds or a mocked env (tests/
test_capture_gate0_baseline_miniwob.py's _FakeEnv), never against the real paid manifest through a
real MiniWoB env. In `--mode paid_gate0`, the task utterance/page text is deliberately NOT printed
to stdout (screenshots are still popped open locally for David to look at and act on -- that is the
whole point of the rig -- but nothing about their content is echoed to a log). Seed cross-
contamination is refused mechanically: the seeds-file content must match
`eval.score_gate0.MODES[<mode>]`'s exact pinned list, so a dev seed file can never satisfy
`--mode paid_gate0` and vice versa.

After a real paid_gate0 capture succeeds, `eval/fixtures/gate0_paid_source_pins.json`'s
`artifact_sha256.miniwob_human` (currently the placeholder
`PENDING_NOT_YET_CAPTURED_paid_seed_human_replay_tool_not_built`) must be frozen from the produced
`human_metrics.json` -- same recipe as this report's dev-mode freeze (§8 of
reports/2026-07-21-gate0-readiness-final-v2.md): `sha256sum` the real file and paste the hex digest
in as a separate, reviewed follow-up. Do NOT freeze a placeholder ahead of the real artifact existing.

One cold attempt per task (the exam law -- see DAVID_BASELINES.md "Re-run rule"): this script
refuses to overwrite an existing canonical `human_metrics.json` unless `--allow-retake "<reason>"`
is passed; the artifact then records `attempt_number` (1 for a first attempt) and `retake_reason`
(empty for a first attempt).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
ARM = "miniwob"
DEFAULT_MODE = "readiness_dev"
GAME = "miniwob_click_checkboxes"
# Same modality the paid agent uses: it also never touches a mouse, it emits a structured
# click/type/key call after receiving screenshot pixels (world_mcp.MiniWobSession.call()). Recorded
# so a future scorer/verdict-writer can see this from the artifact alone, not just doc prose.
CAPTURE_MODALITY = "screenshot_relay_typed_action"

# Per-mode defaults. paid_gate0's real_out is the EXACT path
# eval/fixtures/gate0_paid_source_pins.json's artifact_paths.miniwob_human names -- keep in sync if
# that fixture ever moves. Both live under the repo-wide gitignored runs/ (never committed).
MODE_CONFIG = {
    "readiness_dev": {
        "seeds_file": ROOT / "eval" / "fixtures" / "gate0_miniwob_dev_seeds.json",
        "real_out": os.path.normpath(str(ROOT / "runs" / "gate0_human_baseline" / "miniwob")),
    },
    "paid_gate0": {
        "seeds_file": ROOT / "eval" / "fixtures" / "gate0_miniwob_paid_seeds.json",
        "real_out": os.path.normpath(str(ROOT / "runs" / "gate0_paid_human_baseline" / "miniwob")),
    },
}
# Backward-compatible alias: existing tests/tooling reference the DEV real path as a module constant.
REAL_OUT = MODE_CONFIG[DEFAULT_MODE]["real_out"]


def _under_real_path(out: str, real_out: str = REAL_OUT) -> bool:
    norm = os.path.normpath(os.path.abspath(out))
    real = os.path.normpath(os.path.abspath(real_out))
    return norm == real or norm.startswith(real + os.sep)


def _atomic_write_json(path: str, payload: dict) -> None:
    """temp file + os.replace so a crash mid-write can never leave a truncated/corrupt artifact at
    `path` -- matches the append-only/fail-closed treatment already given to oracle.jsonl and
    INCOMPLETE files. On a crash the temp file itself is also cleaned up, so neither `path` nor a
    stray partial file survives."""
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


def _default_opener(path: str) -> None:
    """Best-effort: pop the screenshot open in the OS default viewer. Never fatal -- David can always
    open the printed path manually."""
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            import webbrowser
            webbrowser.open(f"file://{os.path.abspath(path)}")
    except Exception:
        pass


def _save_screenshot(sess, path: str) -> None:
    from PIL import Image
    Image.fromarray(sess.mw.screenshot).convert("RGB").save(path)


def _prompt_action(prompt: Callable[[str], str]) -> tuple[str, dict]:
    """Loop until David types a well-formed action; return (tool_name, args) or ("quit", {})."""
    while True:
        raw = prompt("action (click X Y | type TEXT | key NAME | quit)> ").strip()
        if not raw:
            continue
        parts = raw.split(None, 1)
        head = parts[0].lower()
        if head == "quit":
            return "quit", {}
        if head == "click" and len(parts) == 2:
            coords = parts[1].split()
            if len(coords) == 2:
                try:
                    return "click", {"x": int(coords[0]), "y": int(coords[1])}
                except ValueError:
                    pass
        elif head == "type" and len(parts) == 2:
            return "type_text", {"text": parts[1]}
        elif head == "key" and len(parts) == 2:
            return "press_key", {"key": parts[1]}
        print("Didn't understand that. Examples: 'click 42 118', 'type hello', 'key Enter', 'quit'.")


def run(args, prompt: Callable[[str], str] = input,
        opener: Callable[[str], None] = _default_opener) -> int:
    mode = getattr(args, "mode", None) or DEFAULT_MODE
    if mode not in MODE_CONFIG:
        print(f"refusing: unknown --mode {mode!r} (must be one of {sorted(MODE_CONFIG)}).",
              file=sys.stderr)
        return 2
    real_out = MODE_CONFIG[mode]["real_out"]
    if args.out is None:
        args.out = real_out
    if args.seeds_file is None:
        args.seeds_file = str(MODE_CONFIG[mode]["seeds_file"])

    # Held-out law, defense in depth: paid_gate0 is the held-out-seed replay (1000..1004) -- a
    # scripted stand-in must never be able to produce it. Require an explicit, un-default-able
    # acknowledgement that a real human is at the keyboard, on top of the TTY check below (which
    # only fires for the real canonical path -- this fires for EVERY paid_gate0 invocation,
    # canonical path or not, since the sensitive part is running the held-out seeds at all, not
    # just where the artifact lands).
    if mode == "paid_gate0" and not getattr(args, "i_am_human", False):
        print("refusing: --mode paid_gate0 requires --i-am-human -- this captures the held-out-seed "
              "(1000..1004) human replay; a scripted invocation must never be able to produce this "
              "artifact. Pass --i-am-human only when a real human is about to play these 5 episodes "
              "interactively, AFTER the paid agent's Arm W attempt is already banked.",
              file=sys.stderr)
        return 2

    if args.test and _under_real_path(args.out, real_out):
        print(f"--test refuses to write under the real baseline path {real_out!r}; "
              "pass a scratch --out.", file=sys.stderr)
        return 2
    if not args.test and not _under_real_path(args.out, real_out):
        print(f"warning: --out {args.out!r} is outside the canonical real baseline path "
              f"{real_out!r} (fine for a manual dry run; DAVID_BASELINES.md uses the default).",
              file=sys.stderr)
    # Defense in depth against the prompt-injection seam (fairness review Minor 1): `run()`'s
    # `prompt` param has no way to prove a live human is answering it. A scripted `prompt` callable
    # writing to the REAL baseline path with no attached TTY is exactly what a hostile/accidental
    # non-interactive invocation looks like -- refuse it. --test mode is exempt (it can never reach
    # the real path anyway, and the test suite's canned-answer seam intentionally has no TTY).
    if not args.test and _under_real_path(args.out, real_out) and not sys.stdin.isatty():
        print("refusing: real baseline capture requires an interactive TTY (stdin is not a tty) -- "
              "this guards against a scripted `prompt` answering for a human and silently writing "
              "to the real baseline path. Use --test for automated/dry runs.", file=sys.stderr)
        return 2

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

    from eval.score_gate0 import MODES, _miniwob_success
    _seed_path, expected_seeds = MODES[mode]
    seeds_on_disk = json.loads(Path(args.seeds_file).read_text(encoding="utf-8"))
    if seeds_on_disk != expected_seeds:
        print(f"refusing: {args.seeds_file} does not match the frozen {mode!r} seed manifest "
              "(seed cross-contamination guard -- a dev seed file can never satisfy --mode "
              f"paid_gate0 and vice versa; got {seeds_on_disk}).", file=sys.stderr)
        return 2

    os.makedirs(args.out, exist_ok=True)

    # world_mcp.MiniWobSession appends terminal rows to <out>/oracle.jsonl incrementally DURING a
    # run (never truncates), and this rig's own success check re-reads that WHOLE file after the
    # run -- so ANY stale trace from an earlier session (a scored attempt legitimately re-taken
    # with --allow-retake, OR a crash/quit after >=1 completed episode but BEFORE the canonical
    # write -- the documented "just re-run" case) would leave 2 terminal rows for those episodes
    # and _miniwob_success would refuse to ever score the new run as success, no matter how clean
    # it was. Archive whenever a prior trace exists at session start, REGARDLESS of whether a
    # canonical artifact exists (PR #119 re-review MAJOR: gating this on the canonical file left
    # the partial-crash free-retry path permanently unscoreable, with --allow-retake a no-op since
    # there was no canonical file to allow retaking). Renamed, never deleted -- same append-only
    # law as INCOMPLETE files -- and never clobbered on same-second name collisions.
    prior_oracle_path = os.path.join(args.out, "oracle.jsonl")
    if os.path.exists(prior_oracle_path):
        base = os.path.join(args.out, f"oracle.attempt{max(attempt_number - 1, 1)}_{int(time.time())}")
        archive_path, n = f"{base}.jsonl", 0
        while os.path.exists(archive_path):
            n += 1
            archive_path = f"{base}_{n}.jsonl"
        os.replace(prior_oracle_path, archive_path)
        print(f"[stale oracle trace from a previous session archived -> {archive_path}]")

    import world_mcp
    sess_args = argparse.Namespace(game=GAME, rom=None, init_state=None, out=args.out, record=False,
                                    with_screenshot=False, keep_frames=False,
                                    seeds_file=args.seeds_file, seed=None)
    sess = world_mcp.MiniWobSession(sess_args)

    # HELD-OUT LAW: never print task/page text for the held-out seeds -- David still gets the exact
    # pixels via the popped-open screenshot (the point of the rig), but nothing about their content
    # is echoed to stdout/logs. readiness_dev keeps the plain utterance print (DEV seeds are not
    # sensitive; this is unchanged from before --mode existed).
    if mode == "paid_gate0":
        print("Task (from the environment): [suppressed in --mode paid_gate0 -- look at the "
              "popped-open screenshot for the real instructions]")
        print(f"5 fresh HELD-OUT episodes. Every screenshot is saved to {args.out}/ and popped "
              "open for you.")
    else:
        print(f'Task (from the environment): "{sess.mw.utterance}"')
        print(f"5 fresh DEV episodes, seeds {expected_seeds}. Every screenshot is saved to {args.out}/ "
              "and popped open for you.")
    print("The timer starts on your FIRST action. Type 'quit' at any prompt to abort.")

    first_action_perf: float | None = None
    started_at = None
    action_count = 0
    step_img = 0
    quit_requested = False
    input_event_times: list[float] = []

    try:
        while not sess._exhausted:
            png_path = os.path.join(args.out, f"ep{sess._episode_idx}_step{step_img}.png")
            _save_screenshot(sess, png_path)
            step_img += 1
            print(f"[episode {sess._episode_idx} -- screenshot -> {png_path}]")
            opener(png_path)

            tool, tool_args = _prompt_action(prompt)
            if tool == "quit":
                quit_requested = True
                break

            sess.call(tool, tool_args)
            action_count += 1
            input_event_times.append(time.time())
            if first_action_perf is None:
                first_action_perf = time.perf_counter()
                started_at = datetime.now(timezone.utc)
                print("[timer started -- first action taken]")

            if sess._episode_over and not sess._exhausted:
                sess.call("reset_episode", {})
                action_count += 1   # bookkeeping call the agent will also have to spend
                input_event_times.append(time.time())
    finally:
        sess.close()

    wall_clock_s = (time.perf_counter() - first_action_perf) if first_action_perf is not None else 0.0
    completed_at = datetime.now(timezone.utc)

    oracle_path = os.path.join(args.out, "oracle.jsonl")
    with open(oracle_path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    success, failures = (False, ["human_quit"]) if quit_requested else _miniwob_success(rows, expected_seeds)

    metrics = {
        "schema_version": 1,
        "arm": ARM,
        "role": "human",
        "mode": mode,
        "wall_clock_s": round(wall_clock_s, 3),
        "primitive_actions": action_count,
        "success": success,
        "failures": failures,
        "player": args.player if not args.test else f"TEST:{args.player}",
        "started_at": started_at.isoformat() if started_at else None,
        "completed_at": completed_at.isoformat(),
        "seeds_file": os.path.normpath(args.seeds_file),
        "expected_seeds": expected_seeds,
        "oracle_path": os.path.normpath(oracle_path),
        "test_mode": bool(args.test),
        "capture_modality": CAPTURE_MODALITY,
        # one-cold-attempt bookkeeping (DAVID_BASELINES.md "Re-run rule"): attempt_number is 1 for a
        # normal first capture; retake_reason is only ever non-empty when --allow-retake overrode an
        # existing canonical human_metrics.json.
        "attempt_number": attempt_number,
        "retake_reason": retake_reason,
        # Per-input-event epoch timestamps (time.time()), independent of the aggregate
        # primitive_actions count -- lets a future auditor check action cadence directly instead of
        # trusting the aggregate alone (fairness review Minor 2).
        "input_event_times": input_event_times,
    }
    name = "human_metrics.json" if success else f"human_metrics.INCOMPLETE_{int(time.time())}.json"
    metrics_path = os.path.join(args.out, name)
    _atomic_write_json(metrics_path, metrics)

    print(("PASS" if success else "INCOMPLETE") + f" -- wrote {metrics_path}")
    print(json.dumps(metrics, sort_keys=True))
    return 0 if success else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", choices=sorted(MODE_CONFIG), default=DEFAULT_MODE,
                     help="readiness_dev (DEV seeds 0-4, the default) or paid_gate0 (the HELD-OUT "
                          "seeds 1000-1004 -- the paid gate's actual MiniWoB human denominator; "
                          "requires --i-am-human, and is only sanctioned AFTER Arm W's paid attempt "
                          "is banked).")
    ap.add_argument("--out", default=None,
                     help="defaults to the canonical real path for --mode (see module docstring).")
    ap.add_argument("--seeds-file", default=None,
                     help="defaults to the frozen seed manifest for --mode.")
    ap.add_argument("--player", default="David")
    ap.add_argument("--i-am-human", action="store_true", dest="i_am_human",
                     help="required for --mode paid_gate0 -- explicit, non-default acknowledgement "
                          "that a real human is about to replay the held-out seeds. A scripted "
                          "invocation cannot satisfy this by accident.")
    ap.add_argument("--allow-retake", metavar="REASON", default=None,
                     help="required to overwrite an existing canonical human_metrics.json -- state "
                          "why this is a legitimate re-take (a botched capture), not a rerun to "
                          "chase a better score.")
    ap.add_argument("--test", action="store_true",
                     help="throwaway smoke-test mode: refuses to write under the real baseline path")
    return run(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
