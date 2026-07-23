"""STUB scorer for graduation-exam v1 EX02 -- Kirby's Dream Land: clear Stage 3.

ORACLE_PENDING: no stage/level-counter RAM address is known for `kirby_dreamland` yet. The only
oracle currently wired for this world is `hp` (0xD086, `world_mcp.py` GAMES["kirby_dreamland"]
["watch"], `world_mcp.py:220`) -- a plain 0-5 HP int, not a stage counter. Per
reports/2026-07-22-graduation-exam-v1-definition.md EX02: "the stage-counter address is not yet
identified; a $0 RAM hunt (same discipline that found hp@0xD086) is readiness work before freeze."

Do NOT fabricate an address here. This scorer refuses UNCONDITIONALLY -- it takes no oracle rows
and never returns PASS -- until a future oracle-hunt report pins the real address.

TODO(oracle-hunt): once a stage/level-counter address is found and pinned in a
reports/<date>-kirby-dreamland-stage-oracle-hunt.md report, replace this stub with a real
`_kirby_stage3_success(rows)` predicate mirroring `eval/score_gate0.py`'s fail-closed shape (see
`eval/score_exam_red_badge.py` for the pattern on a plain RAM-bit oracle).

Usage: `uv run python -m eval.score_exam_kirby_stage3` (no oracle file -- there is nothing to read yet)
"""
from __future__ import annotations

import json

TASK_ID = "EX02"


def score() -> dict:
    return {"schema_version": 1, "task_id": TASK_ID, "task": "kirby_dreamland_clear_stage_3",
            "overall": "ORACLE_PENDING",
            "failures": ["no_stage_counter_ram_address_known:"
                         "see_module_docstring_TODO_and_graduation-exam-v1-definition.md_EX02"]}


def main() -> int:
    result = score()
    print(json.dumps(result, sort_keys=True))
    return 1   # never PASS


if __name__ == "__main__":
    raise SystemExit(main())
