import json
import subprocess
import sys
from pathlib import Path

import eval.score_exam_miniwob_focus_text as scorer
from eval._exam_miniwob_common import miniwob_task_success

_REPO_ROOT = Path(scorer.__file__).resolve().parents[1]


def _rows(success=True):
    rows = []
    for episode, seed in enumerate(scorer.EXPECTED_SEEDS):
        rows.append({"episode": episode, "seed": seed, "step": 0, "task": scorer.TASK,
                     "reward": 0.0, "done": False, "abandoned": False})
        if success or episode < len(scorer.EXPECTED_SEEDS) - 1:
            rows.append({"episode": episode, "seed": seed, "step": 1, "task": scorer.TASK,
                         "reward": 1.0, "done": True, "abandoned": False})
    return rows


def test_synthetic_five_episode_pass():
    ok, failures = miniwob_task_success(_rows(), scorer.EXPECTED_SEEDS, scorer.TASK)
    assert ok, failures


def test_score_wraps_pass():
    result = scorer.score(_rows())
    assert result["overall"] == "PASS"
    assert result["task_id"] == "EX07"
    assert result["task"] == "focus-text"


def test_last_episode_incomplete_fails():
    result = scorer.score(_rows(False))
    assert result["overall"] == "FAIL_CAPABILITY"
    assert "miniwob_episode_4_terminal_count" in result["failures"]


def test_wrong_task_row_is_refused():
    rows = _rows()
    rows[0]["task"] = "click-checkboxes"
    result = scorer.score(rows)
    assert result["overall"] == "FAIL_CAPABILITY"
    assert "miniwob_wrong_task_row" in result["failures"]


def test_bool_reward_is_not_accepted():
    rows = _rows()
    rows[-1]["reward"] = True
    result = scorer.score(rows)
    assert result["overall"] == "FAIL_CAPABILITY"
    assert "miniwob_episode_4_terminal_not_success" in result["failures"]


def test_seed_mismatch_is_refused():
    rows = _rows()
    rows[0]["seed"] = 999
    result = scorer.score(rows)
    assert result["overall"] == "FAIL_CAPABILITY"
    assert "miniwob_extra_episode_or_seed_conflict" in result["failures"]


def test_cli_subprocess_pass_exits_zero(tmp_path):
    oracle = tmp_path / "oracle.jsonl"
    oracle.write_text("\n".join(json.dumps(r) for r in _rows()), encoding="utf-8")
    proc = subprocess.run([sys.executable, "-m", "eval.score_exam_miniwob_focus_text", str(oracle)],
                          cwd=str(_REPO_ROOT), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["overall"] == "PASS"


def test_cli_subprocess_missing_file_exits_nonzero(tmp_path):
    missing = tmp_path / "nope.jsonl"
    proc = subprocess.run([sys.executable, "-m", "eval.score_exam_miniwob_focus_text", str(missing)],
                          cwd=str(_REPO_ROOT), capture_output=True, text=True)
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["overall"] == "INSUFFICIENT_DATA"
