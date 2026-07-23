"""STUB scorer for graduation-exam v1 EX05 -- MKDS: finish one lap.

ORACLE_PENDING: the only candidate progress byte, `0x022C8090`
(reports/2026-07-04-mkds-continuous-time-build-plan.md), is explicitly UNVERIFIED --
reports/2026-07-13-mkds-ab-verdict.md states this byte "was not present in either run's
oracle.jsonl... do not claim checkpoint/lap progress from RAM for this run." Per
reports/2026-07-22-graduation-exam-v1-definition.md EX05: "Verifying (or replacing) this oracle is
a hard precondition, not optional polish." An MKDS oracle-hunt session is running separately
(worktree `ai-pokemon-red-oracle-mkds`, as of 2026-07-23) -- this scorer intentionally does not
race ahead of that hunt's own report.

Do NOT trust the unverified 0x022C8090 byte here. This scorer refuses UNCONDITIONALLY until a
future oracle-hunt report verifies (or replaces) a lap/checkpoint-progress address.

TODO(oracle-hunt): once a lap/checkpoint-progress address is verified (or a replacement found) and
pinned in that oracle-hunt's report, replace this stub with a real `_mkds_lap_success(rows)`
predicate mirroring `eval/score_gate0.py`'s fail-closed shape.

Usage: `uv run python -m eval.score_exam_mkds_lap` (no oracle file -- there is nothing trustworthy to read yet)
"""
from __future__ import annotations

import json

TASK_ID = "EX05"


def score() -> dict:
    return {"schema_version": 1, "task_id": TASK_ID, "task": "mkds_finish_one_lap",
            "overall": "ORACLE_PENDING",
            "failures": ["mkds_progress_byte_unverified:"
                         "see_module_docstring_TODO_and_graduation-exam-v1-definition.md_EX05"]}


def main() -> int:
    result = score()
    print(json.dumps(result, sort_keys=True))
    return 1   # never PASS


if __name__ == "__main__":
    raise SystemExit(main())
