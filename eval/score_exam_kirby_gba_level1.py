"""STUB scorer for graduation-exam v1 EX04 -- Kirby (GBA): clear Level 1-1.

ORACLE_PENDING: `kirby_gba`'s registry `watch` is `{}` -- same gap as `emerald_gba`, no GBA world
has an oracle wired yet (`world_mcp.py:182-186`). Per
reports/2026-07-22-graduation-exam-v1-definition.md EX04 (PR #129 -- v1-DRAFT, NOT frozen; task
bars here are pending David's freeze of that PR): "Same gap as EX03 -- kirby_gba also has
watch: {}; needs its own oracle hunt."

Do NOT fabricate a level-complete/door-transition address here. This scorer refuses
UNCONDITIONALLY until a future oracle-hunt report pins the real address.

TODO(oracle-hunt): once a level-complete/door-transition address is found and pinned in a
reports/<date>-kirby-gba-level-oracle-hunt.md report, replace this stub with a real
`_kirby_gba_level1_success(rows)` predicate mirroring `eval/score_gate0.py`'s fail-closed shape.

Usage: `uv run python -m eval.score_exam_kirby_gba_level1` (no oracle file -- there is nothing to read yet)
"""
from __future__ import annotations

import json

TASK_ID = "EX04"


def score() -> dict:
    return {"schema_version": 1, "task_id": TASK_ID, "task": "kirby_gba_clear_level_1_1",
            "overall": "ORACLE_PENDING",
            "failures": ["no_gba_level_complete_oracle_wired:"
                         "see_module_docstring_TODO_and_graduation-exam-v1-definition.md_EX04"]}


def main() -> int:
    result = score()
    print(json.dumps(result, sort_keys=True))
    return 1   # never PASS


if __name__ == "__main__":
    raise SystemExit(main())
