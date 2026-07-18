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


def _under_real_path(out: str) -> bool:
    norm = os.path.normpath(os.path.abspath(out))
    real = os.path.normpath(os.path.abspath(REAL_OUT))
    return norm == real or norm.startswith(real + os.sep)


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

    from eval.score_gate0 import MODES, _miniwob_success
    _seed_path, expected_seeds = MODES[MODE]
    seeds_on_disk = json.loads(Path(args.seeds_file).read_text(encoding="utf-8"))
    if seeds_on_disk != expected_seeds:
        print(f"refusing: {args.seeds_file} does not match the frozen DEV seed manifest "
              f"{expected_seeds} (got {seeds_on_disk}).", file=sys.stderr)
        return 2

    os.makedirs(args.out, exist_ok=True)

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
            if first_action_perf is None:
                first_action_perf = time.perf_counter()
                started_at = datetime.now(timezone.utc)
                print("[timer started -- first action taken]")

            if sess._episode_over and not sess._exhausted:
                sess.call("reset_episode", {})
                action_count += 1   # bookkeeping call the agent will also have to spend
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
    ap.add_argument("--out", default=REAL_OUT)
    ap.add_argument("--seeds-file", default=str(ROOT / "eval" / "fixtures" / "gate0_miniwob_dev_seeds.json"))
    ap.add_argument("--player", default="David")
    ap.add_argument("--test", action="store_true",
                     help="throwaway smoke-test mode: refuses to write under the real baseline path")
    return run(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
