"""Gate 0 Arm W human-baseline capture rig (MiniWoB click-checkboxes, DEV seeds 0..4).

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
    runs/gate0_human_baseline/miniwob/human_metrics.json  -- schema_version 1, arm=miniwob,
                                                              role=human, mode=readiness_dev,
                                                              wall_clock_s, primitive_actions (+extras)
    runs/gate0_human_baseline/miniwob/oracle.jsonl         -- MiniWobSession's own oracle writer
    runs/gate0_human_baseline/miniwob/ep<N>_step<K>.png    -- what David was shown at each decision

An incomplete/quit attempt writes `human_metrics.INCOMPLETE_<unix-ts>.json` instead of the canonical
file (see DAVID_BASELINES.md's re-run rule).

DEV vs paid: `mode` is hard-pinned to "readiness_dev" (module constant, never CLI-overridable) --
this rig can never produce a `paid_gate0`-mode artifact. The DEV-seed numbers here are a readiness
estimate only, NEVER the paid gate's human denominator (see DAVID_BASELINES.md's warning box); the
paid-mode human replay against the held-out seeds (1000..1004) is a separate, not-yet-built tool.

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
MODE = "readiness_dev"
REAL_OUT = os.path.normpath(str(ROOT / "runs" / "gate0_human_baseline" / "miniwob"))
GAME = "miniwob_click_checkboxes"
# Same modality the paid agent uses: it also never touches a mouse, it emits a structured
# click/type/key call after receiving screenshot pixels (world_mcp.MiniWobSession.call()). Recorded
# so a future scorer/verdict-writer can see this from the artifact alone, not just doc prose.
CAPTURE_MODALITY = "screenshot_relay_typed_action"


def _under_real_path(out: str) -> bool:
    norm = os.path.normpath(os.path.abspath(out))
    real = os.path.normpath(os.path.abspath(REAL_OUT))
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
    if args.test and _under_real_path(args.out):
        print(f"--test refuses to write under the real baseline path {REAL_OUT!r}; "
              "pass a scratch --out.", file=sys.stderr)
        return 2
    if not args.test and not _under_real_path(args.out):
        print(f"warning: --out {args.out!r} is outside the canonical real baseline path "
              f"{REAL_OUT!r} (fine for a manual dry run; DAVID_BASELINES.md uses the default).",
              file=sys.stderr)
    # Defense in depth against the prompt-injection seam (fairness review Minor 1): `run()`'s
    # `prompt` param has no way to prove a live human is answering it. A scripted `prompt` callable
    # writing to the REAL baseline path with no attached TTY is exactly what a hostile/accidental
    # non-interactive invocation looks like -- refuse it. --test mode is exempt (it can never reach
    # the real path anyway, and the test suite's canned-answer seam intentionally has no TTY).
    if not args.test and _under_real_path(args.out) and not sys.stdin.isatty():
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
    _seed_path, expected_seeds = MODES[MODE]
    seeds_on_disk = json.loads(Path(args.seeds_file).read_text(encoding="utf-8"))
    if seeds_on_disk != expected_seeds:
        print(f"refusing: {args.seeds_file} does not match the frozen DEV seed manifest "
              f"{expected_seeds} (got {seeds_on_disk}).", file=sys.stderr)
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
        "mode": MODE,
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
    ap.add_argument("--out", default=REAL_OUT)
    ap.add_argument("--seeds-file", default=str(ROOT / "eval" / "fixtures" / "gate0_miniwob_dev_seeds.json"))
    ap.add_argument("--player", default="David")
    ap.add_argument("--allow-retake", metavar="REASON", default=None,
                     help="required to overwrite an existing canonical human_metrics.json -- state "
                          "why this is a legitimate re-take (a botched capture), not a rerun to "
                          "chase a better score.")
    ap.add_argument("--test", action="store_true",
                     help="throwaway smoke-test mode: refuses to write under the real baseline path")
    return run(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
