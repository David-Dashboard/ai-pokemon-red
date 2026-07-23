"""Fail-closed OFFLINE oracle scorer for graduation-exam v1 EX07 -- MiniWoB `focus-text`.

Task (reports/2026-07-22-graduation-exam-v1-definition.md EX07): the on-screen `focus-text`
utterance (a form field to fill and submit). End state: `reward == 1.0` on N fresh episodes,
oracle-side only -- mirrors `eval/score_gate0.py::_miniwob_success` via the shared predicate in
`eval/_exam_miniwob_common.py` (same refuse-on-malformed shape, not re-derived here).

Seed pin: `focus-text` has no `--seeds-file`/`--seed` pinning path in `world_mcp.py` (that flag is
gated on `task == "click-checkboxes"`, `world_mcp.py:2040`) -- left unseeded, `MiniWobSession`
builds `MiniWobWorld(task)` with no seed argument, so `core/miniwob_world.py`'s `_seed_counter`
starts at 0 and increments once per `reset()`: episode i always gets seed i. Five fresh episodes
therefore deterministically produce seeds 0-4 -- this is the harness's only reproducible seed block
for this task (not an arbitrary choice), distinct from Gate 0's `click-checkboxes` dev (0-4) and
paid (1000-1004) blocks only in TASK NAME.

Usage: `uv run python -m eval.score_exam_miniwob_focus_text <oracle.jsonl>`
"""
from __future__ import annotations

from eval._exam_common import run_cli
from eval._exam_miniwob_common import miniwob_task_success

TASK_ID = "EX07"
TASK = "focus-text"
EXPECTED_SEEDS = [0, 1, 2, 3, 4]


def score(rows: list[dict]) -> dict:
    ok, failures = miniwob_task_success(rows, EXPECTED_SEEDS, TASK)
    return {"schema_version": 1, "task_id": TASK_ID, "task": TASK,
            "overall": "PASS" if ok else "FAIL_CAPABILITY", "failures": failures}


def main() -> int:
    return run_cli(TASK_ID, score)


if __name__ == "__main__":
    raise SystemExit(main())
