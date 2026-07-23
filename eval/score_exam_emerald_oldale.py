"""STUB scorer for graduation-exam v1 EX03 -- Emerald: reach Oldale Town.

ORACLE_PENDING: `emerald_gba`'s registry `watch` is `{}` -- no GBA world has an oracle wired yet
(`world_mcp.py:187-191`). Per reports/2026-07-22-graduation-exam-v1-definition.md EX03: "A GBA
memory-map oracle hunt is required readiness work, mirroring Red's `memory_map.py`." A GBA Emerald
oracle-hunt session is running separately (worktree `ai-pokemon-red-oracle-emerald`, as of
2026-07-23) -- this scorer intentionally does not race ahead of that hunt's own report.

Do NOT fabricate a map-ID address here. This scorer refuses UNCONDITIONALLY until a future
oracle-hunt report pins the real address.

TODO(oracle-hunt): once a map-ID (or equivalent town-transition) address is found and pinned in
that oracle-hunt's report, replace this stub with a real `_emerald_oldale_success(rows)` predicate
mirroring `eval/score_gate0.py`'s fail-closed shape.

Usage: `uv run python -m eval.score_exam_emerald_oldale` (no oracle file -- there is nothing to read yet)
"""
from __future__ import annotations

import json

TASK_ID = "EX03"


def score() -> dict:
    return {"schema_version": 1, "task_id": TASK_ID, "task": "emerald_reach_oldale_town",
            "overall": "ORACLE_PENDING",
            "failures": ["no_gba_map_id_oracle_wired:"
                         "see_module_docstring_TODO_and_graduation-exam-v1-definition.md_EX03"]}


def main() -> int:
    result = score()
    print(json.dumps(result, sort_keys=True))
    return 1   # never PASS


if __name__ == "__main__":
    raise SystemExit(main())
