import json
import subprocess
import sys
from pathlib import Path

import eval.score_exam_arc_wa30 as scorer
from eval.score_exam_arc_wa30 import _arc_wa30_success

_REPO_ROOT = Path(scorer.__file__).resolve().parents[1]


def _rows(levels=(0, 0, 1, 1, 2, 3), state_at_end="NOT_FINISHED"):
    rows = []
    for step, lvl in enumerate(levels):
        state = state_at_end if step == len(levels) - 1 else "NOT_FINISHED"
        rows.append({"step": step, "game_id": scorer.GAME_ID, "action": "ACTION1", "args": {},
                     "state": state, "levels_completed": lvl, "win_levels": 9, "frame_count": step})
    return rows


def test_synthetic_reaches_level_3_passes():
    ok, failures = _arc_wa30_success(_rows())
    assert ok, failures


def test_score_wraps_pass():
    result = scorer.score(_rows())
    assert result["overall"] == "PASS"
    assert result["task_id"] == "EX09"


def test_never_reaches_target_fails():
    ok, failures = _arc_wa30_success(_rows(levels=(0, 0, 1, 1, 2, 2)))
    assert not ok
    assert failures == ["arc_level_target_not_reached"]


def test_empty_rows_refused():
    ok, failures = _arc_wa30_success([])
    assert not ok
    assert failures == ["arc_no_rows"]


def test_wrong_game_id_row_refused():
    rows = _rows()
    rows[3]["game_id"] = "ls20"
    ok, failures = _arc_wa30_success(rows)
    assert not ok
    assert "arc_wrong_game_id_row" in failures


def test_bool_levels_completed_is_not_accepted():
    rows = _rows()
    rows[2]["levels_completed"] = True
    ok, failures = _arc_wa30_success(rows)
    assert not ok
    assert "arc_missing_or_invalid_levels_completed" in failures


def test_invalid_state_string_refused():
    rows = _rows()
    rows[2]["state"] = "SOMETHING_ELSE"
    ok, failures = _arc_wa30_success(rows)
    assert not ok
    assert "arc_missing_or_invalid_state" in failures


def test_levels_completed_decreasing_refused():
    # A monotone level counter can never legitimately go backwards -- a decrease is a corrupted or
    # substituted oracle, never a real regression.
    ok, failures = _arc_wa30_success(_rows(levels=(0, 1, 2, 3, 1, 1)))
    assert not ok
    assert "arc_levels_completed_decreased" in failures


def test_level_reached_on_game_over_row_refused():
    ok, failures = _arc_wa30_success(_rows(levels=(0, 1, 2, 3), state_at_end="GAME_OVER"))
    assert not ok
    assert failures == ["arc_level_reached_row_is_game_over"]


def test_cli_subprocess_pass_exits_zero(tmp_path):
    oracle = tmp_path / "oracle.jsonl"
    oracle.write_text("\n".join(json.dumps(r) for r in _rows()), encoding="utf-8")
    proc = subprocess.run([sys.executable, "-m", "eval.score_exam_arc_wa30", str(oracle)],
                          cwd=str(_REPO_ROOT), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["overall"] == "PASS"


def test_cli_subprocess_missing_file_exits_nonzero(tmp_path):
    missing = tmp_path / "nope.jsonl"
    proc = subprocess.run([sys.executable, "-m", "eval.score_exam_arc_wa30", str(missing)],
                          cwd=str(_REPO_ROOT), capture_output=True, text=True)
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["overall"] == "INSUFFICIENT_DATA"
