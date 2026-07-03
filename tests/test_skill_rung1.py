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
  9. PR #89 review-round fixes: steps_elapsed counts WORLD steps (not iterations) for multi-action
     inner lists; world_steps_used counts only steps that actually reached the world; redefinition is
     a distinct logged event; grid_changed_in_region boxes validated (bounds + ordering) at define
     time; top-level stop_when rejected loudly; skill reuse across run_skill calls; WIN mid-skill;
     client exception mid-skill.
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


@pytest.fixture(autouse=True)
def _skills_on_by_default(monkeypatch):
    """This whole file tests the skill MECHANISM (define_skill/run_skill's own behavior), which is
    orthogonal to the ARC_SKILLS A/B gate (doc §4.1) that decides whether a live brain session sees
    these tools at all -- default the flag ON here so the mechanism tests above don't all need to set
    it. Section 10 below (the gate's own tests) overrides this per-test with monkeypatch.delenv/setenv."""
    monkeypatch.setenv("ARC_SKILLS", "1")


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
    assert "stop_when 'grid_changed_in_region(1,1,1,1)' fired after 2 world step(s) (2 iteration(s))" in text


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
    assert "stop_when 'grid_unchanged_for(2)' fired after 2 world step(s) (2 iteration(s))" in text


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
    assert "stop_when 'steps_elapsed(3)' fired after 3 world step(s) (3 iteration(s))" in text


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
    assert "stop_when 'steps_elapsed(3)' fired after 3 world step(s) (3 iteration(s))" in rec["stop_reason"]
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


def test_arcagi3_tool_schemas_present_for_define_and_run_skill(monkeypatch):
    # ARC_SKILLS gate (A/B arm isolation, doc §4.1): schemas only show up when the flag is on.
    monkeypatch.setenv("ARC_SKILLS", "1")
    from world_mcp import _static_tools
    tools = {t["name"]: t for t in _static_tools("arcagi3")}
    assert "define_skill" in tools and "run_skill" in tools
    assert tools["define_skill"]["inputSchema"]["required"] == ["name", "steps"]
    assert tools["run_skill"]["inputSchema"]["required"] == ["name"]
    # PR #89 review finding 4 (second review): no dead top-level stop_when property in the schema --
    # it only exists inside repeat_until steps.
    assert "stop_when" not in tools["define_skill"]["inputSchema"]["properties"]


# ---------------------------------------------------------------------------
# 10. ARC_SKILLS env gate (A/B arm isolation, doc §4.1: Arm A must not even see the tools)
# ---------------------------------------------------------------------------

def test_skill_tools_absent_from_tool_list_by_default(monkeypatch):
    monkeypatch.delenv("ARC_SKILLS", raising=False)
    from world_mcp import _static_tools
    names = {t["name"] for t in _static_tools("arcagi3")}
    assert "define_skill" not in names and "run_skill" not in names


def test_skill_tools_present_in_tool_list_when_flag_on(monkeypatch):
    monkeypatch.setenv("ARC_SKILLS", "1")
    from world_mcp import _static_tools
    names = {t["name"] for t in _static_tools("arcagi3")}
    assert "define_skill" in names and "run_skill" in names


def test_dispatch_of_skill_tools_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("ARC_SKILLS", raising=False)
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    r1 = sess.call("define_skill", {"name": "push", "steps": [{"action": "ACTION1"}]})
    assert "disabled for this session" in r1[0]["text"]
    assert "push" not in sess.skills
    r2 = sess.call("run_skill", {"name": "push"})
    assert "disabled for this session" in r2[0]["text"]


def test_dispatch_of_skill_tools_works_when_flag_on(monkeypatch, tmp_path):
    monkeypatch.setenv("ARC_SKILLS", "1")
    frames = [dict(_RESET_FRAME), _frame([[1, 0], [0, 0]], available_actions=(1, 2, 3, 4))]
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    r1 = sess.call("define_skill", {"name": "push", "steps": [{"action": "ACTION1"}]})
    assert "-> ok" in r1[0]["text"]
    r2 = sess.call("run_skill", {"name": "push"})
    assert "1 step(s) executed" in r2[0]["text"]


# ---------------------------------------------------------------------------
# 9. PR #89 review-round fixes
# ---------------------------------------------------------------------------

def test_steps_elapsed_counts_world_steps_not_iterations(monkeypatch, tmp_path):
    """Review finding 2 (second review): with a 2-action inner list, steps_elapsed(3) must fire after
    3 WORLD steps (mid-iteration 2), not after 3 iterations (6 world steps)."""
    frames = [dict(_RESET_FRAME),
             *[_frame([[i % 2, 0], [0, 0]], available_actions=(1, 2)) for i in range(3)]]
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    sess.call("define_skill", {"name": "pair", "steps": [
        {"repeat_until": {"steps": [{"action": "ACTION1"}, {"action": "ACTION2"}],
                          "stop_when": "steps_elapsed(3)", "max_iters": 8}}]})
    result = sess.call("run_skill", {"name": "pair"})
    text = result[0]["text"]
    assert "3 step(s) executed" in text
    assert "stop_when 'steps_elapsed(3)' fired after 3 world step(s) (2 iteration(s))" in text


def test_steps_elapsed_world_step_semantics_in_log(monkeypatch, tmp_path):
    out = str(tmp_path / "out")
    frames = [dict(_RESET_FRAME),
             *[_frame([[i % 2, 0], [0, 0]], available_actions=(1, 2)) for i in range(3)]]
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(out))
    sess.call("define_skill", {"name": "pair", "steps": [
        {"repeat_until": {"steps": [{"action": "ACTION1"}, {"action": "ACTION2"}],
                          "stop_when": "steps_elapsed(3)", "max_iters": 8}}]})
    sess.call("run_skill", {"name": "pair"})
    with open(f"{out}/skills.jsonl", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    rec = [r for r in rows if r["event"] == "run_skill"][0]
    assert rec["executed_step_count"] == 3
    assert rec["world_steps_used"] == 3
    summary = [e for e in rec["executed"] if "repeat_until_summary" in e][0]
    assert summary["world_steps"] == 3
    assert summary["iterations"] == 2   # fired mid-iteration 2 -- the partial iteration counts


def test_world_steps_used_excludes_rejected_steps(monkeypatch, tmp_path):
    """Review finding 1 (second review): a rejected step sent nothing to the world, so it must not
    consume budget or count in world_steps_used."""
    out = str(tmp_path / "out")
    # RESET allows [1,2,3,4]; the post-ACTION1 frame also allows only [1,2,3,4] -- ACTION5 is illegal.
    frames = [dict(_RESET_FRAME), _frame([[1, 0], [0, 0]], available_actions=(1, 2, 3, 4))]
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(out))
    sess.call("define_skill", {"name": "one_then_bad", "steps": [{"action": "ACTION1"},
                                                                 {"action": "ACTION5"}]})
    result = sess.call("run_skill", {"name": "one_then_bad"})
    assert "1 step(s) executed" in result[0]["text"]
    with open(f"{out}/skills.jsonl", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    rec = [r for r in rows if r["event"] == "run_skill"][0]
    assert rec["world_steps_used"] == 1        # ONLY the step that actually reached the world
    assert rec["executed_step_count"] == 1
    rejected = [e for e in rec["executed"] if e.get("ok") is False]
    assert len(rejected) == 1 and "not currently legal" in rejected[0]["error"]


def test_redefinition_is_a_distinct_logged_event(monkeypatch, tmp_path):
    """Review finding 3 (second review): re-using a name must log a distinct redefine event carrying
    BOTH definitions, and say so in the tool result."""
    out = str(tmp_path / "out")
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(out))
    v1_steps = [{"action": "ACTION1"}]
    v2_steps = [{"action": "ACTION2"}]
    sess.call("define_skill", {"name": "push", "steps": v1_steps})
    result = sess.call("define_skill", {"name": "push", "steps": v2_steps})
    assert "REPLACED" in result[0]["text"]
    with open(f"{out}/skills.jsonl", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    redefines = [r for r in rows if r["event"] == "redefine_skill"]
    assert len(redefines) == 1
    assert redefines[0]["prior_definition"] == {"name": "push", "steps": v1_steps}
    assert redefines[0]["definition"] == {"name": "push", "steps": v2_steps}
    # and the live skill is the NEW definition
    assert sess.skills["push"]["steps"] == v2_steps


def test_run_skill_after_redefinition_executes_new_definition(monkeypatch, tmp_path):
    frames = [dict(_RESET_FRAME), _frame([[1, 0], [0, 0]], available_actions=(1, 2, 3, 4))]
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    sess.call("define_skill", {"name": "push", "steps": [{"action": "ACTION1"}]})
    sess.call("define_skill", {"name": "push", "steps": [{"action": "ACTION2"}]})
    result = sess.call("run_skill", {"name": "push"})
    with open(f"{tmp_path / 'out'}/skills.jsonl", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    rec = [r for r in rows if r["event"] == "run_skill"][0]
    assert rec["executed"][0]["action"] == "ACTION2"
    assert "1 step(s) executed" in result[0]["text"]


@pytest.mark.parametrize("bad_region", [
    "grid_changed_in_region(-1,0,5,5)",    # negative x0
    "grid_changed_in_region(0,-3,5,5)",    # negative y0
    "grid_changed_in_region(0,0,64,5)",    # x1 out of range
    "grid_changed_in_region(0,0,5,64)",    # y1 out of range
    "grid_changed_in_region(5,0,1,5)",     # inverted x (x0 > x1)
    "grid_changed_in_region(0,5,5,1)",     # inverted y (y0 > y1)
])
def test_region_bounds_and_ordering_rejected_at_define_time(monkeypatch, tmp_path, bad_region):
    """Review finding 1 (first review): a negative/out-of-range/inverted box must be rejected LOUDLY
    at define time, never stored as a predicate that silently can never fire."""
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("define_skill", {"name": "bad_box", "steps": [
        {"repeat_until": {"steps": [{"action": "ACTION1"}], "stop_when": bad_region, "max_iters": 4}}]})
    assert "need 0 <= x0 <= x1 <= 63" in result[0]["text"]
    assert "bad_box" not in sess.skills


def test_region_at_grid_corner_still_accepted(monkeypatch, tmp_path):
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("define_skill", {"name": "corner", "steps": [
        {"repeat_until": {"steps": [{"action": "ACTION1"}],
                          "stop_when": "grid_changed_in_region(63,63,63,63)", "max_iters": 4}}]})
    assert "-> ok" in result[0]["text"]


def test_top_level_stop_when_rejected_loudly(monkeypatch, tmp_path):
    """Review finding 4 (second review): a top-level stop_when has no effect -- reject it loudly
    instead of silently ignoring it."""
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("define_skill", {"name": "misplaced", "steps": [{"action": "ACTION1"}],
                                        "stop_when": "steps_elapsed(5)"})
    assert "belongs INSIDE a repeat_until" in result[0]["text"]
    assert "misplaced" not in sess.skills


def test_skill_is_reusable_across_run_skill_calls(monkeypatch, tmp_path):
    """Review test-gap note: a defined skill must be runnable more than once in a session."""
    out = str(tmp_path / "out")
    frames = [dict(_RESET_FRAME),
             _frame([[1, 0], [0, 0]], available_actions=(1, 2, 3, 4)),
             _frame([[0, 1], [0, 0]], available_actions=(1, 2, 3, 4))]
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(out))
    sess.call("define_skill", {"name": "one", "steps": [{"action": "ACTION1"}]})
    r1 = sess.call("run_skill", {"name": "one"})
    r2 = sess.call("run_skill", {"name": "one"})
    assert "1 step(s) executed" in r1[0]["text"]
    assert "1 step(s) executed" in r2[0]["text"]
    with open(f"{out}/skills.jsonl", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert len([r for r in rows if r["event"] == "run_skill"]) == 2


def test_game_over_mid_skill_aborts_cleanly_with_accurate_count(monkeypatch, tmp_path):
    """Review test-gap note: a WIN/GAME_OVER transition partway through a multi-step skill must abort
    with _act_raw's own "game is over" rejection and an accurate executed count."""
    out = str(tmp_path / "out")
    win_frame = _frame([[1, 1], [1, 1]], available_actions=(1, 2, 3, 4), state="WIN")
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME), win_frame])
    sess = ArcAgi3Session(_args(out))
    sess.call("define_skill", {"name": "two_moves", "steps": [{"action": "ACTION1"},
                                                              {"action": "ACTION2"}]})
    result = sess.call("run_skill", {"name": "two_moves"})
    text = result[0]["text"]
    assert "1 step(s) executed" in text
    assert "game is over" in text
    with open(f"{out}/skills.jsonl", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    rec = [r for r in rows if r["event"] == "run_skill"][0]
    assert rec["executed_step_count"] == 1
    assert rec["world_steps_used"] == 1


def test_client_exception_mid_skill_aborts_cleanly(monkeypatch, tmp_path):
    """Review test-gap note: a hard API failure (post-retry exception from the client) mid-skill is a
    distinct path from the validation-rejection path -- it must abort the skill as an observation, not
    a crash, with the step logged ok:False and not counted."""
    out = str(tmp_path / "out")
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(out))
    sess.call("define_skill", {"name": "boom", "steps": [{"action": "ACTION1"}]})

    def _raise(*a, **k):
        raise RuntimeError("HTTP 500 after retries")
    monkeypatch.setattr(sess.client, "action", _raise)
    result = sess.call("run_skill", {"name": "boom"})
    text = result[0]["text"]
    assert "0 step(s) executed" in text
    assert "act error: RuntimeError" in text
    with open(f"{out}/skills.jsonl", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    rec = [r for r in rows if r["event"] == "run_skill"][0]
    assert rec["executed_step_count"] == 0
    assert rec["world_steps_used"] == 0
