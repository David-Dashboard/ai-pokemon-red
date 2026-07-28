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

`game_id` matching -- FAMILY, not exact (fixed 2026-07-28; the previous exact `== "wa30"` test
made PASS unreachable on every banked trace, which all carry `"wa30-ee6fef47"`). An ARC-AGI-3
game_id is `<game key><-suffix>`: the docs' worked examples use the full `ls20-016295f7601e`
while the public catalog and this repo's own flags name games by the bare 4-char key
(`runs/arcagi3_probe/PROBE_REPORT.md` "Available game_ids"; `world_mcp.py --arc-game <game_id>
(e.g. ls20)`). The oracle's `game_id` is the literal `--arc-game` flag value, not the API's
response field (`world_mcp.py:2467-2469,2503`), so a run may legitimately be launched with
either form. The suffix is stable per game, not per session -- the session identity is the
separate `guid` (`core/arcagi3_world.py` reset/action), and the SAME `ee6fef47` is pinned in
three launcher configs across two distinct experiments (`runs/brain_{arcagi3,skill_ab_armA,
skill_ab_armB}/.mcp.json`) and appears in all six banked ARC oracle logs. Suffix length is not
fixed (8 hex here vs 12 in the docs' `ls20-` example), so pinning the exact banked string would
break this scorer on the next revision of the same game -- the same defect class being fixed.
Accepted: `wa30` or `wa30-<suffix>`. Rejected: any other family (`ls20-...`), and any near-miss
key (`wa300-...`, `wa3`). Rows must also agree with each other -- a log stitched from two
different `wa30` builds is a substituted oracle, not a run.
Banked game_id across every trace on disk as of 2026-07-28: `wa30-ee6fef47`.

Usage: `uv run python -m eval.score_exam_arc_wa30 <oracle.jsonl>`
"""
from __future__ import annotations

from eval._exam_common import run_cli

TASK_ID = "EX09"
GAME_ID = "wa30"          # the game KEY/family; a full game_id is `wa30` or `wa30-<suffix>`
LEVEL_TARGET = 3
_VALID_STATES = {"NOT_FINISHED", "WIN", "GAME_OVER"}


def _is_game_family(game_id: object) -> bool:
    """True only for the `wa30` family: the bare key or `wa30-<suffix>`. The `-` is required so
    a near-miss key (`wa300-...`) can never be mistaken for a suffixed `wa30`."""
    return isinstance(game_id, str) and (game_id == GAME_ID or game_id.startswith(f"{GAME_ID}-"))


def _arc_wa30_success(rows: list[dict]) -> tuple[bool, list[str]]:
    if not rows:
        return False, ["arc_no_rows"]

    failures: list[str] = []
    if any(not _is_game_family(row.get("game_id")) for row in rows):
        failures.append("arc_wrong_game_id_row")
    elif len({row["game_id"] for row in rows}) != 1:
        failures.append("arc_inconsistent_game_id_rows")

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
