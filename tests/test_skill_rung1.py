"""Unit tests for skill compilation rung 1 (world_mcp.ArcAgi3Session.define_skill/run_skill), per
reports/2026-07-03-skill-compilation-design.md. CI-safe: no real network — same FakeArcApi pattern as
tests/test_arcagi3_world.py (requests.Session.post/get monkeypatched).

Covers:
  1. define_skill: valid definitions accepted + logged verbatim; malformed definitions rejected loudly
     at DEFINE time (never silently stored).
  2. run_skill: step dispatch (each step resolves to the exact `act` execution path), unknown skill.
  3. Each pinned stop_when predicate: grid_changed_in_region, grid_unchanged_for, steps_elapsed.
  4. Loop caps: max_iters <= 8 enforced; nesting (repeat_until inside repeat_until) rejected.
  5. The 50-world-step absolute ceiling, enforced regardless of the skill's own definition.
  6. Logging shape: skills.jsonl gets one define_skill record + one run_skill record with executed
     steps, iteration counts, stop reason, and executed-step count (the doc's >=3-executed-steps gate
     rule needs this to be scoreable).
  7. Skill lifetime: skills live only in the session object, gone when a fresh session starts (no
     persistence anywhere -- blank-agent law).
  8. No-leak: define_skill/run_skill results never carry levels_completed/win_levels.
"""
from __future__ import annotations

import argparse
import json

import pytest

from world_mcp import ArcAgi3Session

from tests.test_arcagi3_world import FakeArcApi, _install_fake_api, _RESET_FRAME


def _args(out: str, arc_game="ls20") -> argparse.Namespace:
    return argparse.Namespace(game="arcagi3", rom=None, init_state=None, out=out, record=False,
                              with_screenshot=False, keep_frames=False, seeds_file=None, seed=None,
                              arc_game=arc_game)


def _frame(grid, *, available_actions=(1, 2, 3, 4, 5), state="NOT_FINISHED"):
    return {"game_id": "ls20-abc", "guid": "guid-1", "frame": [grid], "state": state,
            "levels_completed": 0, "win_levels": 254, "available_actions": list(available_actions)}


# ---------------------------------------------------------------------------
# 1. define_skill: accept valid, reject malformed
# ---------------------------------------------------------------------------

def test_define_skill_accepts_flat_step_list(monkeypatch, tmp_path):
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("define_skill", {"name": "push", "steps": [{"action": "ACTION1"}, {"action": "ACTION2"}]})
    text = result[0]["text"]
    assert "define_skill 'push' -> ok, 2 top-level step(s)" in text
    assert "push" in sess.skills


def test_define_skill_rejects_empty_steps(monkeypatch, tmp_path):
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("define_skill", {"name": "noop", "steps": []})
    assert "must be a non-empty list" in result[0]["text"]
    assert "noop" not in sess.skills


def test_define_skill_rejects_unknown_action(monkeypatch, tmp_path):
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("define_skill", {"name": "bad", "steps": [{"action": "ACTION9"}]})
    assert "not a valid ARC action" in result[0]["text"]
    assert "bad" not in sess.skills


def test_define_skill_rejects_missing_name(monkeypatch, tmp_path):
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("define_skill", {"name": "", "steps": [{"action": "ACTION1"}]})
    assert "non-empty string" in result[0]["text"]


def test_define_skill_logs_definition_verbatim(monkeypatch, tmp_path):
    out = str(tmp_path / "out")
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(out))
    steps = [{"action": "ACTION1"}, {"action": "ACTION2"}]
    sess.call("define_skill", {"name": "push", "steps": steps})
    with open(f"{out}/skills.jsonl", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    define_rows = [r for r in rows if r["event"] == "define_skill"]
    assert len(define_rows) == 1
    assert define_rows[0]["definition"] == {"name": "push", "steps": steps}


# ---------------------------------------------------------------------------
# 2. run_skill: step dispatch + unknown skill
# ---------------------------------------------------------------------------

def test_run_skill_unknown_name_errors(monkeypatch, tmp_path):
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("run_skill", {"name": "nope"})
    assert "no skill named" in result[0]["text"]


def test_run_skill_executes_flat_steps_via_exact_act_path(monkeypatch, tmp_path):
    """Each step must resolve to act's EXACT execution path (doc §3 "honest accounting"): rejecting an
    action not in available_actions stops the skill exactly like a bare `act` call would."""
    frames = [dict(_RESET_FRAME), _frame([[0, 1], [1, 1]], available_actions=(1, 2, 3, 4))]
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    sess.call("define_skill", {"name": "one_move", "steps": [{"action": "ACTION1"}]})
    result = sess.call("run_skill", {"name": "one_move"})
    text = result[0]["text"]
    assert "1 step(s) executed" in text
    assert "all top-level steps executed" in text


def test_run_skill_stops_on_illegal_action_like_act_would(monkeypatch, tmp_path):
    # RESET only allows [1,2,3,4] -- ACTION5 is illegal, so the skill must halt on step 1 (0 executed).
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    sess.call("define_skill", {"name": "bad_move", "steps": [{"action": "ACTION5"}]})
    result = sess.call("run_skill", {"name": "bad_move"})
    text = result[0]["text"]
    assert "0 step(s) executed" in text
    assert "not currently legal" in text


# ---------------------------------------------------------------------------
# 3. stop_when predicates
# ---------------------------------------------------------------------------

def test_grid_changed_in_region_fires_when_box_differs(monkeypatch, tmp_path):
    # RESET grid all-0s; each ACTION1 flips cell (1,1) to 1 on the 2nd call -- region (1,1,1,1) should
    # fire after exactly 2 iterations (iteration 1: no change yet since frame arrives after the call;
    # iteration 2: the flip is visible).
    frames = [
        {**_RESET_FRAME, "frame": [[[0, 0], [0, 0]]], "available_actions": [1]},
        _frame([[0, 0], [0, 0]], available_actions=(1,)),          # after iter 1: unchanged
        _frame([[0, 0], [0, 1]], available_actions=(1,)),          # after iter 2: cell (1,1) flips
    ]
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    sess.call("define_skill", {"name": "poke", "steps": [
        {"repeat_until": {"steps": [{"action": "ACTION1"}],
                          "stop_when": "grid_changed_in_region(1,1,1,1)", "max_iters": 8}}]})
    result = sess.call("run_skill", {"name": "poke"})
    text = result[0]["text"]
    assert "2 step(s) executed" in text
    assert "stop_when 'grid_changed_in_region(1,1,1,1)' fired after 2 iteration(s)" in text


def test_grid_unchanged_for_fires_after_k_identical_steps(monkeypatch, tmp_path):
    same_grid = [[0, 0], [0, 0]]
    frames = [dict(_RESET_FRAME), *[_frame(same_grid, available_actions=(1,)) for _ in range(3)]]
    frames[0] = {**_RESET_FRAME, "frame": [same_grid], "available_actions": [1]}
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    sess.call("define_skill", {"name": "stuck", "steps": [
        {"repeat_until": {"steps": [{"action": "ACTION1"}],
                          "stop_when": "grid_unchanged_for(2)", "max_iters": 8}}]})
    result = sess.call("run_skill", {"name": "stuck"})
    text = result[0]["text"]
    assert "stop_when 'grid_unchanged_for(2)' fired after 2 iteration(s)" in text


def test_steps_elapsed_fires_after_n_iterations(monkeypatch, tmp_path):
    frames = [dict(_RESET_FRAME), *[_frame([[i % 2, 0], [0, 0]], available_actions=(1,)) for i in range(3)]]
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    sess.call("define_skill", {"name": "three", "steps": [
        {"repeat_until": {"steps": [{"action": "ACTION1"}],
                          "stop_when": "steps_elapsed(3)", "max_iters": 8}}]})
    result = sess.call("run_skill", {"name": "three"})
    text = result[0]["text"]
    assert "3 step(s) executed" in text
    assert "stop_when 'steps_elapsed(3)' fired after 3 iteration(s)" in text


def test_stop_when_rejects_predicate_outside_pinned_enum(monkeypatch, tmp_path):
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("define_skill", {"name": "bad_pred", "steps": [
        {"repeat_until": {"steps": [{"action": "ACTION1"}], "stop_when": "scrolled()", "max_iters": 4}}]})
    assert "not one of the pinned ARC predicates" in result[0]["text"]


def test_stop_when_rejects_k_above_cap(monkeypatch, tmp_path):
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("define_skill", {"name": "toobig", "steps": [
        {"repeat_until": {"steps": [{"action": "ACTION1"}], "stop_when": "grid_unchanged_for(9)", "max_iters": 4}}]})
    assert "k must be in [1, 8]" in result[0]["text"]


def test_stop_when_rejects_n_above_cap(monkeypatch, tmp_path):
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("define_skill", {"name": "toobig", "steps": [
        {"repeat_until": {"steps": [{"action": "ACTION1"}], "stop_when": "steps_elapsed(51)", "max_iters": 4}}]})
    assert "n must be in [1, 50]" in result[0]["text"]


# ---------------------------------------------------------------------------
# 4. loop caps: max_iters <= 8, no nesting
# ---------------------------------------------------------------------------

def test_max_iters_above_cap_rejected(monkeypatch, tmp_path):
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("define_skill", {"name": "toolong", "steps": [
        {"repeat_until": {"steps": [{"action": "ACTION1"}], "stop_when": "steps_elapsed(10)", "max_iters": 9}}]})
    assert "max_iters must be an int in [1, 8]" in result[0]["text"]


def test_max_iters_zero_rejected(monkeypatch, tmp_path):
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("define_skill", {"name": "zero", "steps": [
        {"repeat_until": {"steps": [{"action": "ACTION1"}], "stop_when": "steps_elapsed(1)", "max_iters": 0}}]})
    assert "max_iters must be an int in [1, 8]" in result[0]["text"]


def test_nested_repeat_until_rejected(monkeypatch, tmp_path):
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("define_skill", {"name": "nested", "steps": [
        {"repeat_until": {"steps": [
            {"repeat_until": {"steps": [{"action": "ACTION1"}], "stop_when": "steps_elapsed(1)", "max_iters": 2}}],
         "stop_when": "steps_elapsed(5)", "max_iters": 4}}]})
    assert "nesting is not allowed" in result[0]["text"]
    assert "nested" not in sess.skills


def test_max_iters_reached_without_stop_when_firing_reports_reason(monkeypatch, tmp_path):
    # Grid changes every step (never triggers grid_unchanged_for) but max_iters=2 caps execution.
    frames = [dict(_RESET_FRAME),
             _frame([[1, 0], [0, 0]], available_actions=(1,)),
             _frame([[0, 1], [0, 0]], available_actions=(1,))]
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    sess.call("define_skill", {"name": "capped", "steps": [
        {"repeat_until": {"steps": [{"action": "ACTION1"}],
                          "stop_when": "grid_unchanged_for(8)", "max_iters": 2}}]})
    result = sess.call("run_skill", {"name": "capped"})
    text = result[0]["text"]
    assert "2 step(s) executed" in text
    assert "reached max_iters=2 without stop_when firing" in text


# ---------------------------------------------------------------------------
# 5. absolute 50-world-step ceiling
# ---------------------------------------------------------------------------

def test_absolute_50_step_ceiling_enforced_across_multiple_top_level_loops(monkeypatch, tmp_path):
    """Two top-level repeat_until blocks, each max_iters=8 with a stop_when that never fires (30 total
    < 50, so this one completes cleanly) -- sets up the next test's contrast. Here we instead directly
    stack enough max-iters loops to blow the 50-step ceiling and check it's enforced mid-skill."""
    # 7 top-level repeat_until blocks * max_iters=8 = 56 requested world steps > 50 ceiling.
    n_frames = 60
    frames = [dict(_RESET_FRAME)] + [_frame([[i % 2, 0], [0, 0]], available_actions=(1,))
                                     for i in range(n_frames)]
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    loop_step = {"repeat_until": {"steps": [{"action": "ACTION1"}],
                                  "stop_when": "steps_elapsed(8)", "max_iters": 8}}
    sess.call("define_skill", {"name": "overbudget", "steps": [loop_step] * 7})
    result = sess.call("run_skill", {"name": "overbudget"})
    text = result[0]["text"]
    assert "50-world-step ceiling hit" in text
    assert "50 step(s) executed" in text   # exactly the ceiling, never more


# ---------------------------------------------------------------------------
# 6. logging shape
# ---------------------------------------------------------------------------

def test_run_skill_log_has_executed_steps_iterations_stop_reason_and_count(monkeypatch, tmp_path):
    out = str(tmp_path / "out")
    frames = [dict(_RESET_FRAME), *[_frame([[i % 2, 0], [0, 0]], available_actions=(1,)) for i in range(3)]]
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(out))
    sess.call("define_skill", {"name": "three", "steps": [
        {"repeat_until": {"steps": [{"action": "ACTION1"}],
                          "stop_when": "steps_elapsed(3)", "max_iters": 8}}]})
    sess.call("run_skill", {"name": "three"})
    with open(f"{out}/skills.jsonl", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    run_rows = [r for r in rows if r["event"] == "run_skill"]
    assert len(run_rows) == 1
    rec = run_rows[0]
    assert rec["name"] == "three"
    assert rec["executed_step_count"] == 3
    assert "stop_when 'steps_elapsed(3)' fired after 3 iteration(s)" in rec["stop_reason"]
    assert isinstance(rec["executed"], list) and len(rec["executed"]) >= 1
    assert rec["world_steps_used"] == 3


def test_qualifying_call_guard_data_is_present(monkeypatch, tmp_path):
    """The doc's >=3-executed-steps qualifying-call gate rule is scored OFFLINE from this log --
    confirm executed_step_count is exactly the count of executed PRIMITIVE steps (not repeat_until
    summaries, which are also appended to `executed` but must not inflate the count)."""
    out = str(tmp_path / "out")
    frames = [dict(_RESET_FRAME), *[_frame([[i % 2, 0], [0, 0]], available_actions=(1,)) for i in range(2)]]
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(out))
    sess.call("define_skill", {"name": "two", "steps": [
        {"repeat_until": {"steps": [{"action": "ACTION1"}],
                          "stop_when": "steps_elapsed(2)", "max_iters": 8}}]})
    sess.call("run_skill", {"name": "two"})
    with open(f"{out}/skills.jsonl", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    rec = [r for r in rows if r["event"] == "run_skill"][0]
    assert rec["executed_step_count"] == 2   # below the >=3 qualifying-call bar -- would be INSUFFICIENT_DATA
    has_summary = any("repeat_until_summary" in e for e in rec["executed"])
    assert has_summary   # the loop summary is logged too, but must not count toward executed_step_count


# ---------------------------------------------------------------------------
# 7. skill lifetime: within-run only, gone on a fresh session (no persistence)
# ---------------------------------------------------------------------------

def test_skills_do_not_survive_a_new_session(monkeypatch, tmp_path):
    out = str(tmp_path / "out")
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess1 = ArcAgi3Session(_args(out))
    sess1.call("define_skill", {"name": "push", "steps": [{"action": "ACTION1"}]})
    assert "push" in sess1.skills

    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess2 = ArcAgi3Session(_args(str(tmp_path / "out2")))
    assert sess2.skills == {}
    result = sess2.call("run_skill", {"name": "push"})
    assert "no skill named" in result[0]["text"]


# ---------------------------------------------------------------------------
# 8. no-leak: define_skill/run_skill never carry oracle fields
# ---------------------------------------------------------------------------

def test_define_and_run_skill_never_leak_score_fields(monkeypatch, tmp_path):
    frames = [dict(_RESET_FRAME), *[_frame([[i % 2, 0], [0, 0]], available_actions=(1,)) for i in range(2)]]
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    r1 = sess.call("define_skill", {"name": "two", "steps": [
        {"repeat_until": {"steps": [{"action": "ACTION1"}],
                          "stop_when": "steps_elapsed(2)", "max_iters": 8}}]})
    r2 = sess.call("run_skill", {"name": "two"})
    for result in (r1, r2):
        blob = json.dumps(result).lower()
        assert "levels_completed" not in blob
        assert "win_levels" not in blob


def test_arcagi3_tool_schemas_present_for_define_and_run_skill():
    from world_mcp import _static_tools
    tools = {t["name"]: t for t in _static_tools("arcagi3")}
    assert "define_skill" in tools and "run_skill" in tools
    assert tools["define_skill"]["inputSchema"]["required"] == ["name", "steps"]
    assert tools["run_skill"]["inputSchema"]["required"] == ["name"]
