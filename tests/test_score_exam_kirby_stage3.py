import json
import subprocess
import sys
from pathlib import Path

import eval.score_exam_kirby_stage3 as scorer
from eval.score_exam_kirby_stage3 import _kirby_stage3_success

_REPO_ROOT = Path(scorer.__file__).resolve().parents[1]


def _row(stage, hp=5):
    return {"step": 0, "frame": 0, "watch": {"hp": hp, "stage": stage}}


def _rows(stages, hp=5):
    return [_row(s, hp) for s in stages]


def test_reaching_float_islands_passes():
    # Green Greens -> Castle Lololo -> Float Islands (index 2), held for several samples.
    ok, failures = _kirby_stage3_success(_rows([0, 0, 1, 1, 1, 2, 2, 2, 2]))
    assert ok, failures
    assert failures == []


def test_score_wraps_pass():
    result = scorer.score(_rows([1, 1, 2, 2]))
    assert result["overall"] == "PASS"
    assert result["task_id"] == "EX02"


def test_never_leaving_stage_2_fails():
    ok, failures = _kirby_stage3_success(_rows([0, 0, 1, 1, 1, 1]))
    assert not ok
    assert failures == ["kirby_stage3_never_reached_stage_3"]


def test_boot_only_all_zero_rows_never_passes():
    # Cold boot reads stage=0, hp=0 -- indistinguishable from the PyBoy all-fields-zero glitch, and
    # from "never started". `== 0` must never be read as "reached Green Greens".
    rows = _rows([0, 0, 0, 0], hp=0)
    ok, failures = _kirby_stage3_success(rows)
    assert not ok
    assert failures == ["kirby_stage3_all_rows_corrupt_glitch"]
    assert scorer.score(rows)["overall"] == "FAIL_CAPABILITY"


def test_reached_then_game_over_still_passes():
    # The byte is a CURRENT-stage selector, not a monotone counter: lives run out and the title
    # screen resets it to 0. An existential predicate must still credit the run; a final-value read
    # would wrongly fail it, and a monotonicity refusal would wrongly reject it.
    ok, failures = _kirby_stage3_success(_rows([1, 1, 2, 2, 2]) + _rows([0, 0], hp=0))
    assert ok, failures


def test_single_row_transient_at_target_is_refused():
    ok, failures = _kirby_stage3_success(_rows([1, 1, 2, 1, 1]))
    assert not ok
    assert failures == ["kirby_stage3_reached_only_as_single_row_transient"]


def test_target_rows_with_zero_hp_are_not_in_play():
    ok, failures = _kirby_stage3_success(_rows([1, 1]) + _rows([2, 2], hp=0))
    assert not ok
    assert failures == ["kirby_stage3_reached_only_while_not_in_play"]


def test_deeper_stage_also_passes():
    # `>=`, not `==`: a run that overshoots into Bubbly Clouds/Mt. Dedede has reached Stage 3.
    ok, failures = _kirby_stage3_success(_rows([1, 1, 2, 2, 3, 3, 4, 4]))
    assert ok, failures


def test_out_of_range_stage_byte_is_refused():
    # KDL has five stages; anything above index 4 means the byte is not the stage selector here.
    rows = _rows([1, 1, 2, 2])
    rows[3]["watch"]["stage"] = 200
    ok, failures = _kirby_stage3_success(rows)
    assert not ok
    assert failures == ["kirby_stage3_missing_or_invalid_oracle_field"]


def test_bool_stage_value_is_not_accepted_as_int():
    rows = _rows([1, 1, 2, 2])
    rows[2]["watch"]["stage"] = True
    ok, failures = _kirby_stage3_success(rows)
    assert not ok
    assert failures == ["kirby_stage3_missing_or_invalid_oracle_field"]


def test_missing_stage_field_is_hard_refusal():
    rows = _rows([1, 1, 2, 2])
    del rows[2]["watch"]["stage"]
    ok, failures = _kirby_stage3_success(rows)
    assert not ok
    assert failures == ["kirby_stage3_missing_or_invalid_oracle_field"]


def test_single_corrupted_glitch_row_does_not_block_a_real_completion():
    # Same all-fields-zero single-tick signature score_gate0.py documents, landing between the two
    # rows that establish the stage -- must be filtered, not treated as a break in the streak.
    rows = _rows([1, 1, 2]) + _rows([0], hp=0) + _rows([2])
    ok, failures = _kirby_stage3_success(rows)
    assert ok, failures


def test_banked_human_run_columns_are_not_scoreable():
    # runs/2026-07-28_kirby_stage3_human/ predates the wiring: its watch dicts are c1..c5/band, not
    # stage/hp. Pinned so nobody later "maps" c1 -> stage by assumption -- refuse, never guess.
    rows = [{"watch": {"c1": 2, "c2": 1, "c3": 1, "c4": 1, "c5": 1, "band": 9}} for _ in range(4)]
    ok, failures = _kirby_stage3_success(rows)
    assert not ok
    assert failures == ["kirby_stage3_missing_or_invalid_oracle_field"]


def test_no_watch_rows_at_all_is_refused():
    ok, failures = _kirby_stage3_success([{"not_watch": {}}])
    assert not ok
    assert failures == ["kirby_stage3_no_watch_rows"]


def test_empty_rows_is_refused():
    ok, failures = _kirby_stage3_success([])
    assert not ok
    assert failures == ["kirby_stage3_no_watch_rows"]


def test_cli_subprocess_pass_exits_zero(tmp_path):
    oracle = tmp_path / "oracle.jsonl"
    oracle.write_text("\n".join(json.dumps(r) for r in _rows([0, 1, 1, 2, 2])), encoding="utf-8")
    proc = subprocess.run([sys.executable, "-m", "eval.score_exam_kirby_stage3", str(oracle)],
                          cwd=str(_REPO_ROOT), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["overall"] == "PASS"


def test_cli_subprocess_fail_exits_nonzero(tmp_path):
    oracle = tmp_path / "oracle.jsonl"
    oracle.write_text("\n".join(json.dumps(r) for r in _rows([0, 1, 1, 1])), encoding="utf-8")
    proc = subprocess.run([sys.executable, "-m", "eval.score_exam_kirby_stage3", str(oracle)],
                          cwd=str(_REPO_ROOT), capture_output=True, text=True)
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["overall"] == "FAIL_CAPABILITY"


def test_cli_subprocess_missing_file_exits_nonzero(tmp_path):
    proc = subprocess.run([sys.executable, "-m", "eval.score_exam_kirby_stage3",
                           str(tmp_path / "nope.jsonl")], cwd=str(_REPO_ROOT),
                          capture_output=True, text=True)
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["overall"] == "INSUFFICIENT_DATA"
