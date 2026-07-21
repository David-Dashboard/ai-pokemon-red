"""Offline reconstruction of David's Gate 0 Red human baseline from his archived COLD attempt-1.

Background: `tools/capture_gate0_baseline_red.py` detects task completion LIVE by running
`eval.score_gate0._red_success` after every sampled row and freezing wall_clock_s/primitive_actions
the instant it first returns True. David's attempt 1 (2026-07-21) was a genuinely cold run that, in
fact, completed the task -- but the pre-PR-#121 `_red_success` had a scorer bug (the glitch-row
filter was too narrow) that made it miss the real completion live, so the session was archived as
`human_metrics.INCOMPLETE_*.json` instead of the canonical baseline. David then played a SECOND,
no-longer-cold attempt. PR #121 fixed the detector on `main`.

Option A (David's call, 2026-07-21): reconstruct attempt 1's true completion numbers OFFLINE, using
the now-fixed `_red_success`, rather than bank attempt 2 (which is not a cold attempt) or discard the
cold data. This script does exactly that and nothing else: it never plays, never invents rows.

Logic (mirrors the live rig's own detection loop -- see capture_gate0_baseline_red.run()'s
`if not success and first_input_perf is not None: ok, failures = _red_success(rows)`):
  1. Replay the trace row by row; after each row, call `_red_success` on every row seen so far
     (imported from eval.score_gate0, never copied). The first prefix that succeeds pins the
     completion row index; that row's `t` is t_done.
  2. The live rig starts its clock on the first detected keypress. We mirror that: t_first_input is
     input_event_times[0] from the INCOMPLETE artifact (cross-checked against that artifact's own
     `started_at`, which the rig also sets at first-keypress time).
  3. wall_clock_s = t_done - t_first_input; primitive_actions = count of input_event_times <= t_done
     (matching the rig's "frozen the instant of detection" semantics); input_event_times themselves
     are trimmed to <= t_done so the artifact never carries post-completion presses as if they were
     part of the timed attempt.

Usage:
    uv run python tools/reconstruct_gate0_red_baseline.py --trace <oracle.jsonl> \
        --incomplete <human_metrics.INCOMPLETE_*.json> [--out <path>]

Refuses to overwrite an existing canonical human_metrics.json at --out (default: the real Red
baseline path) -- same one-cold-attempt-per-task law the live rig enforces.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Running this file directly (`uv run python tools/reconstruct_gate0_red_baseline.py`, per this
# repo's convention -- see DAVID_BASELINES.md) makes Python add tools/, not the repo root, to
# sys.path[0], so the root-level `eval` package below would otherwise fail to import. Same shim as
# tools/gate3d_baselines.py.
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from eval.score_gate0 import _red_success

ROOT = _REPO
ARM = "red"
ROLE = "human"
MODE = "readiness_dev"
SCHEMA_VERSION = 1
DEFAULT_OUT = ROOT / "runs" / "gate0_human_baseline" / "red" / "human_metrics.json"
# Clock-start cross-check tolerance: the live rig sets `started_at` and appends
# input_event_times[0] in the same loop iteration (see capture_gate0_baseline_red.run()); any
# larger gap in an archived INCOMPLETE artifact means our clock-start assumption doesn't hold there.
CLOCK_START_TOLERANCE_S = 0.01
RECONSTRUCTION_METHOD = (
    "Replayed the archived attempt-1 oracle trace through eval.score_gate0._red_success "
    "(imported, PR #121 fix included) row by row to find the first prefix that succeeds; "
    "wall_clock_s/primitive_actions/input_event_times are derived against that row's timestamp "
    "exactly as tools/capture_gate0_baseline_red.py freezes them against live detection."
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def find_completion_row(rows: list[dict]) -> int | None:
    """First row index `i` such that `_red_success(rows[:i+1])` is True -- the same growing-prefix
    check the live rig performs after every sampled row once input has started."""
    for i in range(len(rows)):
        ok, _ = _red_success(rows[: i + 1])
        if ok:
            return i
    return None


def reconstruct(trace_path: Path, incomplete_path: Path) -> dict:
    trace_bytes = trace_path.read_bytes()
    incomplete_bytes = incomplete_path.read_bytes()
    rows = _load_jsonl(trace_path)
    incomplete = json.loads(incomplete_bytes.decode("utf-8"))

    if not rows:
        raise SystemExit(f"{trace_path} has no rows -- refusing to reconstruct")

    completion_row_index = find_completion_row(rows)
    if completion_row_index is None:
        _, failures = _red_success(rows)
        raise SystemExit(
            f"{trace_path} never reaches a _red_success completion row "
            f"(final failures={failures}) -- refusing to reconstruct a false completion")
    t_done = rows[completion_row_index]["t"]

    input_event_times = incomplete.get("input_event_times") or []
    if not input_event_times:
        raise SystemExit(f"{incomplete_path} has no input_event_times -- cannot determine clock start")
    t_first_input = input_event_times[0]
    if t_first_input > t_done:
        raise SystemExit("first input event is after the detected completion row -- refusing (clock inversion)")

    started_at_str = incomplete.get("started_at")
    if started_at_str:
        recorded_start = datetime.fromisoformat(started_at_str).timestamp()
        if abs(recorded_start - t_first_input) > CLOCK_START_TOLERANCE_S:
            raise SystemExit(
                f"clock-start cross-check failed: {incomplete_path}'s started_at={recorded_start} "
                f"vs input_event_times[0]={t_first_input} (>{CLOCK_START_TOLERANCE_S}s apart)")

    trimmed_events = [t for t in input_event_times if t <= t_done]

    return {
        "schema_version": SCHEMA_VERSION,
        "arm": ARM,
        "role": ROLE,
        "mode": MODE,
        "wall_clock_s": round(t_done - t_first_input, 3),
        "primitive_actions": len(trimmed_events),
        "success": True,
        "failures": [],
        "player": incomplete.get("player"),
        "started_at": datetime.fromtimestamp(t_first_input, tz=timezone.utc).isoformat(),
        "completed_at": datetime.fromtimestamp(t_done, tz=timezone.utc).isoformat(),
        "rom_path": incomplete.get("rom_path"),
        "rom_sha256": incomplete.get("rom_sha256"),
        "savestate_path": incomplete.get("savestate_path"),
        "savestate_sha256": incomplete.get("savestate_sha256"),
        "oracle_path": str(trace_path),
        "test_mode": incomplete.get("test_mode", False),
        "attempt_number": 1,
        "retake_reason": "",
        "input_event_times": trimmed_events,
        # Reconstruction provenance -- a superset on top of the live rig's schema. The frozen
        # source-pin loader (eval.score_gate0._verify_sources) only reads a named-key allow-list off
        # the human artifact and never rejects extra keys -- see
        # tests/test_score_gate0.py::test_frozen_source_pins_load_exact_artifacts and this file's own
        # test_reconstructed_artifact_passes_frozen_verify_sources.
        "reconstructed": True,
        "reconstruction_method": RECONSTRUCTION_METHOD,
        "reconstruction_source_trace_sha256": _sha256_bytes(trace_bytes),
        "reconstruction_source_incomplete_sha256": _sha256_bytes(incomplete_bytes),
        "reconstructed_at": datetime.now(timezone.utc).isoformat(),
        "completion_row_index": completion_row_index,
    }


def write_artifact(artifact: dict, out_path: Path) -> None:
    if out_path.exists():
        raise SystemExit(
            f"refusing: {out_path} already exists -- one cold attempt per task "
            "(DAVID_BASELINES.md re-run rule); this tool never overwrites a banked baseline")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("--trace", type=Path, required=True, help="attempt-1 oracle.jsonl trace")
    ap.add_argument("--incomplete", type=Path, required=True,
                     help="attempt-1 human_metrics.INCOMPLETE_*.json")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    artifact = reconstruct(args.trace, args.incomplete)
    write_artifact(artifact, args.out)

    print(f"wrote {args.out}")
    print(f"completion_row_index={artifact['completion_row_index']}")
    print(f"wall_clock_s={artifact['wall_clock_s']}")
    print(f"primitive_actions={artifact['primitive_actions']}")
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
