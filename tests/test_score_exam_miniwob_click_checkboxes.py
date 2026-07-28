import json
import subprocess
import sys
from pathlib import Path

import eval.score_exam_miniwob_click_checkboxes as scorer
import eval.score_gate0 as gate0_scorer
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


def test_exam_seed_block_never_overlaps_gate0_blocks():
    # Quarantine discipline (reports/2026-07-22-graduation-exam-v1-definition.md EX08): the exam's
    # own click-checkboxes seed block must be disjoint from Gate 0's dev (0-4) and paid (1000-1004)
    # blocks it already reads via eval/fixtures/gate0_miniwob_{dev,paid}_seeds.json.
    dev_seeds = json.loads(gate0_scorer.MODES["readiness_dev"][0].read_text(encoding="utf-8"))
    paid_seeds = json.loads(gate0_scorer.MODES["paid_gate0"][0].read_text(encoding="utf-8"))
    assert set(scorer.EXPECTED_SEEDS).isdisjoint(dev_seeds)
    assert set(scorer.EXPECTED_SEEDS).isdisjoint(paid_seeds)


def test_synthetic_five_episode_pass():
    ok, failures = miniwob_task_success(_rows(), scorer.EXPECTED_SEEDS, scorer.TASK)
    assert ok, failures


def test_score_wraps_pass():
    result = scorer.score(_rows())
    assert result["overall"] == "PASS"
    assert result["task_id"] == "EX08"
    assert result["task"] == "click-checkboxes"


def test_one_episode_short_fails():
    result = scorer.score(_rows(False))
    assert result["overall"] == "FAIL_CAPABILITY"


def test_wrong_task_row_is_refused():
    rows = _rows()
    for row in rows:
        row["task"] = "focus-text"
    result = scorer.score(rows)
    assert result["overall"] == "FAIL_CAPABILITY"
    assert "miniwob_wrong_task_row" in result["failures"]


def test_reopened_row_after_success_is_refused():
    rows = _rows()
    rows.insert(2, {"episode": 0, "seed": scorer.EXPECTED_SEEDS[0], "step": 2, "task": scorer.TASK,
                    "reward": 0.0, "done": False, "abandoned": False})
    result = scorer.score(rows)
    assert result["overall"] == "FAIL_CAPABILITY"
    assert "miniwob_episode_0_terminal_not_last_row" in result["failures"]


def test_cli_subprocess_pass_exits_zero(tmp_path):
    oracle = tmp_path / "oracle.jsonl"
    oracle.write_text("\n".join(json.dumps(r) for r in _rows()), encoding="utf-8")
    proc = subprocess.run([sys.executable, "-m", "eval.score_exam_miniwob_click_checkboxes", str(oracle)],
                          cwd=str(_REPO_ROOT), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["overall"] == "PASS"
