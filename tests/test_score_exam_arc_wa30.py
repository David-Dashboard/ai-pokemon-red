import json
import subprocess
import sys
from pathlib import Path

import eval.score_exam_arc_wa30 as scorer
from eval._exam_common import load_oracle_jsonl
from eval.score_exam_arc_wa30 import _arc_wa30_success

_REPO_ROOT = Path(scorer.__file__).resolve().parents[1]

# A verbatim byte-for-byte copy of runs/brain_arcagi3/run1_L1of9/world/oracle.jsonl -- a REAL log
# written by world_mcp.py::ArcAgi3Session._log_oracle during the banked 2026-07-03 ARC run, not a
# hand-built dict. It exists because the synthetic `_rows()` helper below builds its rows from
# scorer.GAME_ID and therefore agrees with the scorer by construction: it cannot detect the scorer
# disagreeing with reality. It did not -- the shipped scorer pinned game_id == "wa30" exactly while
# every banked row carries "wa30-ee6fef47", so EX09 could only ever return FAIL_CAPABILITY
# ["arc_wrong_game_id_row"], refusing on identity before it looked at play at all.
_BANKED_ORACLE = _REPO_ROOT / "eval" / "fixtures" / "arcagi3_wa30_banked" / "run1_L1of9_oracle.jsonl"
_BANKED_GAME_ID = "wa30-ee6fef47"


def _rows(levels=(0, 0, 1, 1, 2, 3), state_at_end="NOT_FINISHED", game_id=_BANKED_GAME_ID):
    # Defaults to the REAL banked game_id, not scorer.GAME_ID -- a synthetic row must not be
    # allowed to define its own notion of a valid identity.
    rows = []
    for step, lvl in enumerate(levels):
        state = state_at_end if step == len(levels) - 1 else "NOT_FINISHED"
        rows.append({"step": step, "game_id": game_id, "action": "ACTION1", "args": {},
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


# --- game_id identity, exercised against the REAL banked log -------------------------------------

def test_banked_oracle_rows_clear_the_game_id_check():
    """The regression this file exists for: a real trace must never be refused on identity."""
    rows = load_oracle_jsonl(_BANKED_ORACLE)
    assert rows, f"banked fixture missing/malformed: {_BANKED_ORACLE}"
    assert {r["game_id"] for r in rows} == {_BANKED_GAME_ID}
    _, failures = _arc_wa30_success(rows)
    assert "arc_wrong_game_id_row" not in failures
    assert "arc_inconsistent_game_id_rows" not in failures


def test_banked_oracle_fails_only_on_the_task_bar_not_on_identity():
    """EX09 is still NOT passed by any banked trace -- run1_L1of9 tops out at levels_completed=1
    against LEVEL_TARGET=3. The point of the fix is that the refusal is now the HONEST one
    (the task was not achieved) instead of a bookkeeping mismatch on game_id."""
    rows = load_oracle_jsonl(_BANKED_ORACLE)
    assert max(r["levels_completed"] for r in rows) == 1 < scorer.LEVEL_TARGET
    result = scorer.score(rows)
    assert result["overall"] == "FAIL_CAPABILITY"
    assert result["failures"] == ["arc_level_target_not_reached"]


def test_bare_game_key_accepted():
    # world_mcp.py's --arc-game takes the bare key too ("e.g. ls20") and logs the flag verbatim,
    # so a run launched as `--arc-game wa30` must not be refused either.
    ok, failures = _arc_wa30_success(_rows(game_id="wa30"))
    assert ok, failures


def test_a_different_game_family_is_still_refused():
    # The docs' worked example id, i.e. a genuinely different game in full suffixed form.
    ok, failures = _arc_wa30_success(_rows(game_id="ls20-016295f7601e"))
    assert not ok
    assert failures == ["arc_wrong_game_id_row"]


def test_near_miss_game_keys_are_refused():
    # Prefix matching must be on "wa30-" (or the exact bare key), never a bare startswith("wa30")
    # and never a substring test.
    for bad in ("wa300-ee6fef47", "wa30x", "wa3", "xxwa30-ee6fef47", ""):
        ok, failures = _arc_wa30_success(_rows(game_id=bad))
        assert not ok, bad
        assert failures == ["arc_wrong_game_id_row"], bad


def test_non_string_game_id_refused():
    ok, failures = _arc_wa30_success(_rows(game_id=None))
    assert not ok
    assert failures == ["arc_wrong_game_id_row"]


def test_two_different_wa30_builds_in_one_log_refused():
    # Same family, different suffix on different rows = a stitched/substituted oracle, not a run.
    rows = _rows()
    rows[3]["game_id"] = "wa30-deadbeef"
    ok, failures = _arc_wa30_success(rows)
    assert not ok
    assert failures == ["arc_inconsistent_game_id_rows"]


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
