"""STUB scorer for graduation-exam v1 EX02 -- Kirby's Dream Land: clear Stage 3.

ORACLE_PENDING -- but the ADDRESS IS NOW KNOWN; only this scorer's predicate is still unwritten.
The stage oracle was found and wired 2026-07-28: `stage` @ 0xD03B, a 0-indexed stage selector
(0=Green Greens, 1=Castle Lololo, 2=Float Islands, 3=Bubbly Clouds, 4=Mt. Dedede), established
causally then held over 9,000 frames of live play with 0 spurious transitions --
reports/2026-07-26-oracle-kirby-gb-stage3.md (PR #173), wired into GAMES["kirby_dreamland"]["watch"]
alongside the pre-existing `hp` (0xD086, a plain 0-5 HP int). Per
reports/2026-07-22-graduation-exam-v1-definition.md EX02 (PR #129 -- v1-DRAFT, NOT frozen; task
bars here are pending David's freeze of that PR).

This scorer STILL refuses UNCONDITIONALLY -- it takes no oracle rows and never returns PASS --
because writing the predicate is deliberately a separate, reviewed step. Do NOT fabricate one here.

TODO(scorer): replace this stub with a real `_kirby_stage3_success(rows)` predicate over
`row["watch"]["stage"]`, mirroring `eval/score_gate0.py`'s fail-closed shape (see
`eval/score_exam_red_badge.py` for the pattern on a plain RAM oracle).

  HAZARD, read before writing that predicate: `stage == 0` is NOT "reached Green Greens". 0 is also
  the uninitialized boot value AND the post-game-over title-screen value, so it cannot distinguish
  progress from never-having-started. Only `>= 2` is meaningful; Stage 3 is index 2.

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
