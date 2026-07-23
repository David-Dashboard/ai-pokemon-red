"""Fail-closed OFFLINE oracle scorer for graduation-exam v1 EX09 -- ARC-AGI-3 `wa30`: reach level 3.

Task (reports/2026-07-22-graduation-exam-v1-definition.md EX09, PR #129 -- v1-DRAFT, NOT frozen;
task bars here are pending David's freeze of that PR): no instruction beyond the game's
own on-screen signal -- one level past the banked skill-compilation rung-1 result (2/9 levels).
End state: `levels_completed` from the oracle-only `arcagi3` session log
(`world_mcp.py::ArcAgi3Session._log_oracle`, never on the wire) reaches 3.

Oracle row shape (`world_mcp.py:2502-2505`): `{step, game_id, action, args, state, levels_completed,
win_levels, frame_count}`, `state` in `NOT_FINISHED | WIN | GAME_OVER`
(`core/arcagi3_world.py:70-71`). Reads only these rows -- never the transcript, never a model
self-report. Fail-closed: a wrong/missing `game_id`, a non-int `levels_completed`, an invalid
`state`, or `levels_completed` going backwards between rows (impossible for a monotone level
counter -- a decrease means a corrupted or substituted oracle) is a hard refusal, never a guessed
PASS.

Usage: `uv run python -m eval.score_exam_arc_wa30 <oracle.jsonl>`
"""
from __future__ import annotations

from eval._exam_common import run_cli

TASK_ID = "EX09"
GAME_ID = "wa30"
LEVEL_TARGET = 3
_VALID_STATES = {"NOT_FINISHED", "WIN", "GAME_OVER"}


def _arc_wa30_success(rows: list[dict]) -> tuple[bool, list[str]]:
    if not rows:
        return False, ["arc_no_rows"]

    failures: list[str] = []
    if any(row.get("game_id") != GAME_ID for row in rows):
        failures.append("arc_wrong_game_id_row")

    levels: list[int] = []
    for row in rows:
        lvl, state = row.get("levels_completed"), row.get("state")
        if isinstance(lvl, bool) or not isinstance(lvl, int) or lvl < 0:
            failures.append("arc_missing_or_invalid_levels_completed")
            break
        if state not in _VALID_STATES:
            failures.append("arc_missing_or_invalid_state")
            break
        levels.append(lvl)
    else:
        for prev, cur in zip(levels, levels[1:]):
            if cur < prev:
                failures.append("arc_levels_completed_decreased")
                break

    if failures:
        return False, failures

    target_idx = next((i for i, lvl in enumerate(levels) if lvl >= LEVEL_TARGET), None)
    if target_idx is None:
        return False, ["arc_level_target_not_reached"]
    if rows[target_idx].get("state") == "GAME_OVER":
        # A row that simultaneously claims the target level AND a game-over state is a
        # contradiction (a real completion isn't logged on the same tick as a loss) -- refuse
        # rather than guess which field is right.
        return False, ["arc_level_reached_row_is_game_over"]

    return True, []


def score(rows: list[dict]) -> dict:
    ok, failures = _arc_wa30_success(rows)
    return {"schema_version": 1, "task_id": TASK_ID, "task": f"arcagi3_{GAME_ID}_level_{LEVEL_TARGET}",
            "overall": "PASS" if ok else "FAIL_CAPABILITY", "failures": failures}


def main() -> int:
    return run_cli(TASK_ID, score)


if __name__ == "__main__":
    raise SystemExit(main())
