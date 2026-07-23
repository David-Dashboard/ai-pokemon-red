"""Shared fail-closed plumbing for the graduation-exam v1 scorers (`eval/score_exam_*.py`).

Not a task predicate itself -- each `score_exam_<task>.py` owns its own `_<task>_success(rows)`
mirroring `eval/score_gate0.py`'s pattern (a pure function over oracle.jsonl rows, refuse rather
than guess on anything malformed/missing). This module only holds the two bits that would
otherwise be copy-pasted verbatim across every scorer file: the fail-closed jsonl loader (mirrors
`score_gate0.py::_jsonl`, but returns `None` instead of raising so callers can turn "unreadable"
into an explicit INSUFFICIENT_DATA verdict instead of a crash) and the `python -m eval.score_exam_*
<oracle.jsonl>` CLI wrapper.

See reports/2026-07-23-exam-scorers.md for which EX0n task each scorer covers and
reports/2026-07-22-graduation-exam-v1-definition.md for the task definitions themselves.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable


def load_oracle_jsonl(path: str | Path) -> list[dict] | None:
    """Fail-closed oracle.jsonl reader: returns `None` (never a partial/truncated list) on a
    missing file, unreadable bytes, a malformed JSON line, or any row that isn't a JSON object.
    Callers MUST treat `None` as an unscorable refusal, never as "zero rows, vacuously fine"."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    rows: list[dict] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(row, dict):
            return None
        rows.append(row)
    return rows


def run_cli(task_id: str, score_fn: Callable[[list[dict]], dict], argv: list[str] | None = None) -> int:
    """Shared entrypoint: load `<oracle.jsonl>` fail-closed, hand rows to `score_fn`, print the
    verdict as one JSON line (mirrors score_gate0.main()'s `json.dumps(result, sort_keys=True)`),
    exit 0 only when `overall == "PASS"`."""
    parser = argparse.ArgumentParser()
    parser.add_argument("oracle", type=Path, help="path to the task's oracle.jsonl")
    args = parser.parse_args(argv)
    rows = load_oracle_jsonl(args.oracle)
    if rows is None:
        result = {"schema_version": 1, "task_id": task_id, "overall": "INSUFFICIENT_DATA",
                  "failures": ["oracle_file_missing_or_malformed"]}
    else:
        result = score_fn(rows)
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("overall") == "PASS" else 1
