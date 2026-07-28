import json
import subprocess
import sys
from pathlib import Path

import eval.score_exam_red_badge as scorer
from eval.score_exam_red_badge import _red_badge_success

_REPO_ROOT = Path(scorer.__file__).resolve().parents[1]


def _rows(success=True):
    # index0: fresh. index1: starter obtained (party 0->1). index2: gym battle (in_battle==2).
    # index3: battle ends. index4-6 (success only): badge bit flips and stays set -- both
    # corroborating preconditions (party 0->1, then in_battle==2) land BEFORE the badge flip.
    rows = [{"watch": {"x": 3, "y": 7, "map": 38, "party": 0, "badges": 0, "in_battle": 0,
                       "party_hp_hi": 0, "party_hp_lo": 0}},
            {"watch": {"x": 5, "y": 4, "map": 40, "party": 1, "badges": 0, "in_battle": 0,
                       "party_hp_hi": 0, "party_hp_lo": 20}},
            {"watch": {"x": 6, "y": 4, "map": 40, "party": 1, "badges": 0, "in_battle": 2,
                       "party_hp_hi": 0, "party_hp_lo": 20}},
            {"watch": {"x": 6, "y": 4, "map": 40, "party": 1, "badges": 0, "in_battle": 0,
                       "party_hp_hi": 0, "party_hp_lo": 20}}]
    if not success:
        return rows
    rows += [{"watch": {"x": 6, "y": 5, "map": 40, "party": 1, "badges": 1, "in_battle": 0,
                        "party_hp_hi": 0, "party_hp_lo": 20}}
             for _ in range(3)]
    return rows


def test_synthetic_fresh_start_to_first_badge_passes():
    ok, failures = _red_badge_success(_rows())
    assert ok, failures
    assert failures == []


def test_score_wraps_pass():
    result = scorer.score(_rows())
    assert result["overall"] == "PASS"
    assert result["task_id"] == "EX01"


def test_never_earned_fails():
    ok, failures = _red_badge_success(_rows(False))
    assert not ok
    assert failures == ["red_badge_never_earned"]


def test_repro_badge_flip_without_any_battle_is_refused():
    # PR #139 review REVISE finding 1, repro (a): the verifier reproduced a false PASS on a trace
    # where `badges` flips 0->1 while `in_battle` never once reaches 2 anywhere -- no gym/trainer
    # battle evidence at all. Must now refuse, not PASS.
    rows = [{"watch": {"x": 3, "y": 7, "map": 38, "party": 0, "badges": 0, "in_battle": 0,
                       "party_hp_hi": 0, "party_hp_lo": 0}},
            {"watch": {"x": 5, "y": 4, "map": 40, "party": 1, "badges": 0, "in_battle": 0,
                       "party_hp_hi": 0, "party_hp_lo": 20}},
            {"watch": {"x": 6, "y": 4, "map": 40, "party": 1, "badges": 1, "in_battle": 0,
                       "party_hp_hi": 0, "party_hp_lo": 20}}]
    ok, failures = _red_badge_success(rows)
    assert not ok
    assert failures == ["red_badge_no_battle_after_party_acquisition"]


def test_repro_badge_flip_with_party_always_zero_is_refused():
    # PR #139 review REVISE finding 1, repro (b): the verifier reproduced a false PASS on a trace
    # where `badges` flips 0->1 while `party` stays 0 for the ENTIRE trace -- physically impossible
    # (a Gym battle cannot be won, let alone entered, with an empty party). Must now refuse.
    rows = [{"watch": {"x": 3, "y": 7, "map": 38, "party": 0, "badges": 0, "in_battle": 0,
                       "party_hp_hi": 0, "party_hp_lo": 0}},
            {"watch": {"x": 5, "y": 4, "map": 40, "party": 0, "badges": 0, "in_battle": 2,
                       "party_hp_hi": 0, "party_hp_lo": 0}},
            {"watch": {"x": 6, "y": 4, "map": 40, "party": 0, "badges": 1, "in_battle": 0,
                       "party_hp_hi": 0, "party_hp_lo": 0}}]
    ok, failures = _red_badge_success(rows)
    assert not ok
    assert failures == ["red_badge_no_party_0_to_1"]


def test_badge_flip_before_battle_is_refused():
    # The badge bit flipping BEFORE the qualifying battle row (rather than never having a battle at
    # all) must also be refused -- ordering matters, not just presence of a battle somewhere.
    rows = [{"watch": {"x": 3, "y": 7, "map": 38, "party": 0, "badges": 0, "in_battle": 0,
                       "party_hp_hi": 0, "party_hp_lo": 0}},
            {"watch": {"x": 5, "y": 4, "map": 40, "party": 1, "badges": 0, "in_battle": 0,
                       "party_hp_hi": 0, "party_hp_lo": 20}},
            {"watch": {"x": 6, "y": 4, "map": 40, "party": 1, "badges": 1, "in_battle": 0,
                       "party_hp_hi": 0, "party_hp_lo": 20}},
            {"watch": {"x": 6, "y": 4, "map": 40, "party": 1, "badges": 1, "in_battle": 2,
                       "party_hp_hi": 0, "party_hp_lo": 20}}]
    ok, failures = _red_badge_success(rows)
    assert not ok
    assert failures == ["red_badge_flip_not_after_battle"]


def test_party_transition_not_exactly_zero_to_one_refused():
    rows = _rows()
    rows[1]["watch"]["party"] = 2
    ok, failures = _red_badge_success(rows)
    assert not ok
    assert failures == ["red_badge_party_transition_not_exactly_0_to_1"]


def test_bool_party_value_is_not_accepted_as_int():
    rows = _rows()
    rows[1]["watch"]["party"] = True
    ok, failures = _red_badge_success(rows)
    assert not ok
    assert failures == ["red_badge_missing_or_invalid_oracle_field"]


def test_bool_in_battle_value_is_not_accepted_as_int():
    rows = _rows()
    rows[2]["watch"]["in_battle"] = True
    ok, failures = _red_badge_success(rows)
    assert not ok
    assert failures == ["red_badge_missing_or_invalid_oracle_field"]


def test_not_fresh_start_party_nonzero_refused():
    rows = _rows()
    rows[0]["watch"]["party"] = 1
    ok, failures = _red_badge_success(rows)
    assert not ok
    assert failures == ["red_badge_not_fresh_start"]


def test_not_fresh_start_badge_already_set_refused():
    rows = _rows()
    rows[0]["watch"]["badges"] = 1
    ok, failures = _red_badge_success(rows)
    assert not ok
    assert failures == ["red_badge_not_fresh_start"]


def test_missing_badges_field_is_hard_refusal():
    rows = _rows()
    del rows[2]["watch"]["badges"]
    ok, failures = _red_badge_success(rows)
    assert not ok
    assert failures == ["red_badge_missing_or_invalid_oracle_field"]


def test_bool_badges_value_is_not_accepted_as_int():
    # JSON `true` decodes to Python bool and `True == 1`, so a naive int check would treat a bool
    # badges byte as a legitimate bit-0 set. Must be refused, not silently coerced.
    rows = _rows()
    rows[2]["watch"]["badges"] = True
    ok, failures = _red_badge_success(rows)
    assert not ok
    assert failures == ["red_badge_missing_or_invalid_oracle_field"]


def test_out_of_range_badges_byte_is_refused():
    rows = _rows()
    rows[2]["watch"]["badges"] = 300
    ok, failures = _red_badge_success(rows)
    assert not ok
    assert failures == ["red_badge_missing_or_invalid_oracle_field"]


def test_badge_bit_reverting_after_set_fails():
    rows = _rows()
    rows[-1]["watch"]["badges"] = 0
    ok, failures = _red_badge_success(rows)
    assert not ok
    assert "red_badge_bit_reverted_after_set" in failures


def test_single_corrupted_glitch_row_does_not_block_a_real_completion():
    # Same PyBoy polling-sampler glitch signature score_gate0.py documents: every watched field
    # simultaneously 0 for one tick, sandwiched between otherwise-consistent rows.
    rows = _rows()
    rows.insert(2, {"watch": {"x": 0, "y": 0, "map": 0, "party": 0, "badges": 0, "in_battle": 0,
                              "party_hp_hi": 0, "party_hp_lo": 0}})
    ok, failures = _red_badge_success(rows)
    assert ok, failures


def test_no_watch_rows_at_all_is_refused():
    ok, failures = _red_badge_success([{"not_watch": {}}])
    assert not ok
    assert failures == ["red_badge_no_watch_rows"]


def test_empty_rows_is_refused():
    ok, failures = _red_badge_success([])
    assert not ok
    assert failures == ["red_badge_no_watch_rows"]


def test_missing_oracle_file_is_fail_closed_none(tmp_path):
    from eval._exam_common import load_oracle_jsonl
    assert load_oracle_jsonl(tmp_path / "nope.jsonl") is None


def test_malformed_json_line_is_fail_closed_none(tmp_path):
    from eval._exam_common import load_oracle_jsonl
    bad = tmp_path / "oracle.jsonl"
    bad.write_text("{not json}\n", encoding="utf-8")
    assert load_oracle_jsonl(bad) is None


def test_cli_end_to_end_pass_via_oracle_file(tmp_path):
    from eval._exam_common import load_oracle_jsonl
    oracle = tmp_path / "oracle.jsonl"
    oracle.write_text("\n".join(json.dumps({"watch": row["watch"]}) for row in _rows()), encoding="utf-8")
    rows = load_oracle_jsonl(oracle)
    assert rows is not None
    result = scorer.score(rows)
    assert result["overall"] == "PASS"


def test_cli_subprocess_pass_exits_zero(tmp_path):
    oracle = tmp_path / "oracle.jsonl"
    oracle.write_text("\n".join(json.dumps({"watch": row["watch"]}) for row in _rows()), encoding="utf-8")
    proc = subprocess.run([sys.executable, "-m", "eval.score_exam_red_badge", str(oracle)],
                          cwd=str(_REPO_ROOT), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["overall"] == "PASS"


def test_cli_subprocess_missing_file_exits_nonzero(tmp_path):
    missing = tmp_path / "nope.jsonl"
    proc = subprocess.run([sys.executable, "-m", "eval.score_exam_red_badge", str(missing)],
                          cwd=str(_REPO_ROOT), capture_output=True, text=True)
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["overall"] == "INSUFFICIENT_DATA"


# The REAL wrong-WRAM-bank row, copied verbatim out of the banked paid Red arm
# (reports/2026-07-24-gate0-armR-verdict/oracle.jsonl rows 335 and 347, byte-identical to
# eval/fixtures/gate0_red_human_attempt2_completion.jsonl row 363). Not hand-invented.
_BANKED_WRONG_BANK_ROW = {"x": 1, "y": 1, "map": 1, "party": 0, "badges": 1, "in_battle": 0,
                          "party_hp_hi": 0, "party_hp_lo": 0}


def test_real_banked_wrong_bank_row_after_the_battle_is_not_a_false_pass():
    # The FALSE PASS this scorer's widened filter exists to stop. The corrupt row reads badges == 1
    # (bit 0 SET). Landing after the qualifying battle it satisfies the badge-flip check, and as the
    # LAST row nothing after it clears the bit, so red_badge_bit_reverted_after_set never fires --
    # a trace in which no badge was ever earned scored PASS. Strictly worse than a false FAIL: this
    # is a graduation-exam scorer.
    rows = _rows(False) + [{"watch": dict(_BANKED_WRONG_BANK_ROW)}]
    ok, failures = _red_badge_success(rows)
    assert not ok
    assert failures == ["red_badge_never_earned"]


def test_mistyped_residue_row_cannot_manufacture_a_badge_that_was_never_earned():
    # PR #191 RE-review NEW-2. `_is_corrupt_glitch_row` declines to drop a residue-shaped row with
    # ONE mistyped field, and only badges/party/in_battle were type-checked downstream -- so the row
    # escaped the filter AND every type check and donated a spurious `badges` bit 0 to a trace in
    # which no badge is ever earned. `origin/main` caught the two-row form only by accident (the
    # SECOND, even-residue row tripped red_badge_bit_reverted_after_set); the widened filter drops
    # that row, removing the accidental net. The one-row form was a false PASS on origin/main TOO.
    #
    # Refusing the untypeable row closes both, including the hole origin/main also had.
    spurious = {"x": 7, "y": "7", "map": 7, "badges": 7, "party": 0, "in_battle": 0,
                "party_hp_hi": 0, "party_hp_lo": 0}          # one str field -> not droppable
    even_residue = {"x": 6, "y": 6, "map": 6, "badges": 6, "party": 0, "in_battle": 0,
                    "party_hp_hi": 0, "party_hp_lo": 0}      # bit 0 clear -> the revert signal
    for label, extra in (("spurious only", [spurious]),
                         ("spurious + even residue", [spurious, even_residue])):
        rows = _rows(False) + [{"watch": dict(w)} for w in extra]
        assert _red_badge_success(rows) == (
            False, ["red_badge_missing_or_invalid_oracle_field"]), label


def test_badge_refusal_guard_does_not_fire_on_a_well_typed_trace():
    # The other direction: the guard must not refuse genuine traces. The same construction with the
    # mistyped field repaired is droppable corruption again, and the true reason comes back.
    well_typed = {"x": 7, "y": 7, "map": 7, "badges": 7, "party": 0, "in_battle": 0,
                  "party_hp_hi": 0, "party_hp_lo": 0}
    rows = _rows(False) + [{"watch": dict(well_typed)}]
    assert _red_badge_success(rows) == (False, ["red_badge_never_earned"])
    assert _red_badge_success(_rows()) == (True, [])


def test_real_banked_traces_report_the_true_failure_not_the_artifact():
    # Regression on committed REAL data, both traces that carry the non-zero variant. Before the
    # widening both returned red_badge_flip_not_after_battle -- a failure reason manufactured
    # entirely by the corrupt row's badges==1 flipping the bit at its index, ahead of battle_idx.
    # The true reason on both traces is that no badge was ever earned.
    for name in ("reports/2026-07-24-gate0-armR-verdict/oracle.jsonl",
                 "eval/fixtures/gate0_red_human_attempt2_completion.jsonl"):
        rows = [json.loads(line) for line
                in (_REPO_ROOT / name).read_text(encoding="utf-8").splitlines() if line.strip()]
        ok, failures = _red_badge_success(rows)
        assert not ok, name
        assert failures == ["red_badge_never_earned"], (name, failures)
