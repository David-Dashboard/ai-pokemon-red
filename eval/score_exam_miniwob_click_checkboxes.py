"""Fail-closed OFFLINE oracle scorer for graduation-exam v1 EX08 -- MiniWoB `click-checkboxes`,
exam-own seeds.

Task (reports/2026-07-22-graduation-exam-v1-definition.md EX08): the on-screen checkbox-selection
utterance -- same task TYPE Gate 0 uses, but on a fresh, exam-only seed block (5000-5004), distinct
from Gate 0's dev block (0-4, `eval/fixtures/gate0_miniwob_dev_seeds.json`) and paid held-out block
(1000-1004, `eval/fixtures/gate0_miniwob_paid_seeds.json`) -- never overlapping, same quarantine
discipline as those two files. `world_mcp.py`'s `--seeds-file`/`--seed` flags (gated on
`task == "click-checkboxes"`) already support an arbitrary seed block, so no harness change is
needed to produce this trace.

End state: `reward == 1.0` on all 5 pinned episodes, oracle-side only -- mirrors
`eval/score_gate0.py::_miniwob_success` via the shared predicate in
`eval/_exam_miniwob_common.py` (same refuse-on-malformed shape, not re-derived here).

Usage: `uv run python -m eval.score_exam_miniwob_click_checkboxes <oracle.jsonl>`
"""
from __future__ import annotations

from eval._exam_common import run_cli
from eval._exam_miniwob_common import miniwob_task_success

TASK_ID = "EX08"
TASK = "click-checkboxes"
EXPECTED_SEEDS = [5000, 5001, 5002, 5003, 5004]


def score(rows: list[dict]) -> dict:
    ok, failures = miniwob_task_success(rows, EXPECTED_SEEDS, TASK)
    return {"schema_version": 1, "task_id": TASK_ID, "task": TASK,
            "overall": "PASS" if ok else "FAIL_CAPABILITY", "failures": failures}


def main() -> int:
    return run_cli(TASK_ID, score)


if __name__ == "__main__":
    raise SystemExit(main())
