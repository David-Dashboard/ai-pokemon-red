"""One test file covering the remaining ORACLE_PENDING stub scorers (EX03/EX04/EX05) -- each stub
is intentionally trivial (no oracle to read yet), so this just pins: always refuses, never PASS,
exits nonzero, and cites its module docstring's TODO rather than a fabricated address.

EX02 (`score_exam_kirby_stage3`) left this list once its `stage` @ 0xD03B oracle was wired and its
predicate written -- it is a real scorer now, covered by tests/test_score_exam_kirby_stage3.py."""
import json
import subprocess
import sys
from pathlib import Path

import eval.score_exam_emerald_oldale as emerald
import eval.score_exam_kirby_gba_level1 as kirby_gba
import eval.score_exam_mkds_lap as mkds

_REPO_ROOT = Path(emerald.__file__).resolve().parents[1]
_STUBS = [
    (emerald, "EX03", "eval.score_exam_emerald_oldale"),
    (kirby_gba, "EX04", "eval.score_exam_kirby_gba_level1"),
    (mkds, "EX05", "eval.score_exam_mkds_lap"),
]


def test_all_stubs_report_oracle_pending():
    for module, task_id, _ in _STUBS:
        result = module.score()
        assert result["overall"] == "ORACLE_PENDING"
        assert result["task_id"] == task_id
        assert result["failures"], f"{task_id} stub must name why it refuses"


def test_all_stubs_cli_exit_nonzero_and_never_pass():
    for _, _, module_name in _STUBS:
        proc = subprocess.run([sys.executable, "-m", module_name],
                              cwd=str(_REPO_ROOT), capture_output=True, text=True)
        assert proc.returncode == 1, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["overall"] == "ORACLE_PENDING"
