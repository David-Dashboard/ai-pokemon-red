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


def test_clearing_float_islands_into_bubbly_clouds_passes():
    # 0 Green Greens -> 1 Castle Lololo -> 2 Float Islands -> 3 Bubbly Clouds, held several samples.
    ok, failures = _kirby_stage3_success(_rows([0, 0, 1, 1, 2, 2, 2, 3, 3, 3]))
    assert ok, failures
    assert failures == []


def test_score_wraps_pass():
    result = scorer.score(_rows([2, 2, 3, 3]))
    assert result["overall"] == "PASS"
    assert result["task_id"] == "EX02"
    assert result["task"] == "kirby_dreamland_clear_stage_3"


def test_only_reaching_float_islands_fails():
    # The bar is "advancing PAST Stage 3" (index >= 3), not reaching it (index 2). A run that gets
    # to Float Islands and stops has NOT cleared Stage 3 -- this is the off-by-one that matters.
    ok, failures = _kirby_stage3_success(_rows([0, 1, 1, 2, 2, 2, 2]))
    assert not ok
    assert failures == ["kirby_stage3_never_cleared_stage_3"]


def test_never_leaving_stage_2_fails():
    ok, failures = _kirby_stage3_success(_rows([0, 0, 1, 1, 1, 1]))
    assert not ok
    assert failures == ["kirby_stage3_never_cleared_stage_3"]


def test_boot_only_all_zero_rows_never_passes():
    # Cold boot reads stage=0, hp=0. A MULTI-row zero stretch is a real boot/title screen, not the
    # single-tick sampler glitch, so it is kept and scored as what it is: no stage ever reached.
    # `== 0` must never be read as "reached Green Greens".
    rows = _rows([0, 0, 0, 0], hp=0)
    ok, failures = _kirby_stage3_success(rows)
    assert not ok
    assert failures == ["kirby_stage3_never_cleared_stage_3"]
    assert scorer.score(rows)["overall"] == "FAIL_CAPABILITY"


def test_lone_all_zero_row_is_the_glitch_signature():
    ok, failures = _kirby_stage3_success(_rows([0], hp=0))
    assert not ok
    assert failures == ["kirby_stage3_all_rows_corrupt_glitch"]


def test_no_lower_stage_before_the_clear_is_refused():
    # A trace that reads 3 from its very first row has no progression behind it and is
    # indistinguishable from a byte stuck/substituted at 3 -- score_exam_red_badge.py's reason.
    ok, failures = _kirby_stage3_success(_rows([3, 3, 3]))
    assert not ok
    assert failures == ["kirby_stage3_no_lower_stage_before_clear"]


def test_sampled_death_inside_the_streak_does_not_break_it():
    # A first-ever clear arrives in Bubbly Clouds on low HP; a single sampled death must not turn a
    # genuine three-row hold at stage 3 into a "single row transient". The streak is over `stage`
    # alone; `hp >= 1` only has to hold SOMEWHERE inside it.
    rows = _rows([2]) + [_row(3, hp=5), _row(3, hp=0), _row(3, hp=5)]
    ok, failures = _kirby_stage3_success(rows)
    assert ok, failures


def test_two_single_sample_visits_split_by_a_title_screen_are_refused():
    # The glitch filter must not splice two separate one-sample visits into one apparent 2-row hold:
    # a multi-row all-zero stretch is a real title-screen reset and has to break the streak.
    rows = _rows([1]) + _rows([3]) + _rows([0] * 20, hp=0) + _rows([3])
    ok, failures = _kirby_stage3_success(rows)
    assert not ok
    assert failures == ["kirby_stage3_cleared_only_as_single_row_transient"]


def test_cleared_then_game_over_still_passes():
    # The byte is a CURRENT-stage selector, not a monotone counter: lives run out and the title
    # screen resets it to 0. An existential predicate must still credit the run; a final-value read
    # would wrongly fail it, and a monotonicity refusal would wrongly reject it.
    ok, failures = _kirby_stage3_success(_rows([2, 2, 3, 3, 3]) + _rows([0, 0], hp=0))
    assert ok, failures


def test_single_row_transient_at_target_is_refused():
    ok, failures = _kirby_stage3_success(_rows([2, 2, 3, 2, 2]))
    assert not ok
    assert failures == ["kirby_stage3_cleared_only_as_single_row_transient"]


def test_target_rows_with_zero_hp_are_not_in_play():
    ok, failures = _kirby_stage3_success(_rows([2, 2]) + _rows([3, 3], hp=0))
    assert not ok
    assert failures == ["kirby_stage3_cleared_only_while_not_in_play"]


def test_deeper_stage_also_passes():
    # `>=`, not `==`: a run that overshoots into Mt. Dedede has plainly also cleared Stage 3.
    ok, failures = _kirby_stage3_success(_rows([2, 2, 4, 4]))
    assert ok, failures


def test_out_of_range_stage_byte_is_refused():
    # KDL has five stages; anything above index 4 means the byte is not the stage selector here.
    rows = _rows([2, 2, 3, 3])
    rows[3]["watch"]["stage"] = 200
    ok, failures = _kirby_stage3_success(rows)
    assert not ok
    assert failures == ["kirby_stage3_missing_or_invalid_oracle_field"]


def test_bool_stage_value_is_not_accepted_as_int():
    rows = _rows([2, 2, 3, 3])
    rows[2]["watch"]["stage"] = True
    ok, failures = _kirby_stage3_success(rows)
    assert not ok
    assert failures == ["kirby_stage3_missing_or_invalid_oracle_field"]


def test_missing_stage_field_is_hard_refusal():
    rows = _rows([2, 2, 3, 3])
    del rows[2]["watch"]["stage"]
    ok, failures = _kirby_stage3_success(rows)
    assert not ok
    assert failures == ["kirby_stage3_missing_or_invalid_oracle_field"]


def test_single_corrupted_glitch_row_does_not_block_a_real_completion():
    # Same all-fields-zero single-tick signature score_gate0.py documents, landing between the two
    # rows that establish the stage -- must be filtered, not treated as a break in the streak.
    rows = _rows([2, 2, 3]) + _rows([0], hp=0) + _rows([3])
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
    oracle.write_text("\n".join(json.dumps(r) for r in _rows([0, 1, 2, 3, 3])), encoding="utf-8")
    proc = subprocess.run([sys.executable, "-m", "eval.score_exam_kirby_stage3", str(oracle)],
                          cwd=str(_REPO_ROOT), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["overall"] == "PASS"


def test_cli_subprocess_fail_exits_nonzero(tmp_path):
    oracle = tmp_path / "oracle.jsonl"
    oracle.write_text("\n".join(json.dumps(r) for r in _rows([0, 1, 2, 2])), encoding="utf-8")
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
