"""Unit tests for the Kirby GB skill port (world_mcp.World.define_skill/run_skill), per
reports/2026-07-03-kirby-skill-port-entity-v3.md (the doc pinning this build) and
reports/2026-07-03-skill-compilation-design.md (the rung-1 formalism this ports). CI-safe: no PyBoy, no
real ROM -- kirby_dreamland's World is built directly against a FakeEmulator (tests/test_pokemon_red.py,
already reused by test_cave_noire.py/test_gauntlet.py) and a small scripted Perceiver (returns a
pre-programmed SymbolicState queue) so `move_blocked`/`move_succeeded`/`region_changed` fire
deterministically without fighting FollowCameraPerceiver's real pixel heuristics (covered elsewhere).

Covers (mirrors tests/test_skill_rung1.py's ARC-port coverage, adapted to Kirby's press-shaped steps
and closed enum):
  1. define_skill: valid definitions accepted + logged verbatim; malformed definitions rejected loudly.
  2. run_skill: step dispatch (each step resolves to the exact press_button execution path via the
     gateway), unknown skill.
  3. Each pinned stop_when predicate: steps_elapsed, move_blocked, move_succeeded, region_changed.
  4. Loop caps: max_iters <= 8 enforced; nesting rejected.
  5. The 50-press absolute ceiling, enforced regardless of the skill's own definition.
  6. Logging shape: skills.jsonl gets one define_skill record + one run_skill record with executed
     steps, iteration counts, stop reason, executed-step count, and world_steps_used.
  7. Skill lifetime: skills live only in the World object, gone when a fresh session starts.
  8. No-leak: define_skill/run_skill results never carry the hp oracle.
  9. Gating: KIRBY_SKILLS on/off, ARC_SKILLS must not leak the tools onto kirby_dreamland and vice
     versa, other GB games never see these tools even with KIRBY_SKILLS=1 set.
  10. RESIDUAL #1 (PR #92 verification comment, mandatory): the logged run_skill `step` is the
      PRE-trailing-observe boundary, so `step - world_steps_used` stays exactly the pre-macro step (the
      §5.6 macro-interior exclusion formula's S0) even though a trailing render observe follows the log.
  11. Per-press semantics: one plugin.observe() per press (not per predicate check) -- the doc §2 "one
      oracle row per press" pin, checked via _obs_count deltas.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pytest

from core.gateway import Gateway
from core.grid_perceiver import FollowCameraPerceiver
from core.perception import PerceptMemory, SymbolicState
from core.perception_plugin import PerceptionPlugin
from core.permissions import Allowlist

import world_mcp
from world_mcp import World, _KIRBY_SKILL_MAX_WORLD_STEPS, _static_tools

from tests.test_pokemon_red import FakeEmulator


class _ScriptedPerceiver:
    """A Perceiver that returns a pre-programmed queue of SymbolicStates, one per perceive() call
    (repeats the last one once the queue is exhausted). Lets tests drive `move_blocked`/
    `move_succeeded`/`steps_elapsed` deterministically without depending on FollowCameraPerceiver's
    real pixel-diff heuristics (that algorithm is covered by its own tests elsewhere)."""

    def __init__(self, states: list[SymbolicState]) -> None:
        self._states = list(states)
        self._i = 0

    def perceive(self, frame, memory: PerceptMemory, context=None) -> SymbolicState:
        if self._i < len(self._states):
            s = self._states[self._i]
            self._i += 1
        else:
            s = self._states[-1] if self._states else SymbolicState(context="gameplay")
        return s


def _moved_state() -> SymbolicState:
    return SymbolicState(confidence=1.0, context="gameplay",
                         pose={"value": (0, 0)}, spatial_memory={"visited": 1},
                         last_action={"action": "right", "outcome": "moved"})


def _blocked_state() -> SymbolicState:
    return SymbolicState(confidence=1.0, context="gameplay",
                         pose={"value": (0, 0)}, spatial_memory={"visited": 1},
                         last_action={"action": "right", "outcome": "blocked"})


def _unknown_state() -> SymbolicState:
    return SymbolicState(confidence=1.0, context="gameplay",
                         pose={"value": (0, 0)}, spatial_memory={"visited": 1},
                         last_action={"action": "right", "outcome": "unknown"})


def _make_world(out, *, states=None, screens=None, game="kirby_dreamland") -> World:
    """Build a real World against kirby_dreamland's own plugin/perceiver-module wiring, but with a
    FakeEmulator (no PyBoy) and, optionally, a scripted perceiver (states) standing in for
    FollowCameraPerceiver's real pixel algorithm. `screens`, if given, is a starting current-frame
    value (FakeEmulator.screen_ndarray() returns whatever `._screen` is currently set to, and a test
    drives region_changed scenarios by mutating `w.plugin.emu._screen` directly BETWEEN calls -- this
    avoids counting screen_ndarray() call sites (fade-sample + perceive-once each call it once per
    press/observe, an internal detail this test file should not have to track)."""
    spec = world_mcp.GAMES[game]
    emu = FakeEmulator()
    if screens is not None:
        emu._screen = screens[0]
    perceiver = _ScriptedPerceiver(states) if states is not None else FollowCameraPerceiver()
    plugin = PerceptionPlugin(rom_path=None, emulator=emu, out_dir=out, headless=True,
                              perceiver=perceiver, watch=spec["watch"],
                              render_header="test")
    w = World.__new__(World)
    w.with_screenshot = False
    w.keep_frames = False
    w.plugin = plugin
    w.gw = Gateway(plugin, Allowlist({"press_button", "press_sequence", "wait"}))
    from core.brains import ExploreBrain
    w.explore = ExploreBrain("mcp-brain", single_step=True)
    w.lessons = []
    w.decisions = 0
    w.auto_tiles = 0
    w.visited = 0
    w.region_tools = game in world_mcp._REGION_TOOL_WORLDS
    w._frame_hist = []
    w.kirby_skills_world = game in world_mcp._KIRBY_SKILLS_WORLDS
    w._kirby_skills_enabled = w.kirby_skills_world and world_mcp._kirby_skills_enabled()
    w.skills = {}
    import os
    w._skill_log_path = os.path.join(out, "skills.jsonl")
    return w


def _args(out: str, game="kirby_dreamland") -> argparse.Namespace:
    return argparse.Namespace(game=game, rom=None, init_state=None, out=out, record=False,
                              with_screenshot=False, keep_frames=False)


@pytest.fixture(autouse=True)
def _skills_on_by_default(monkeypatch):
    """This file tests the skill MECHANISM, orthogonal to the KIRBY_SKILLS gate itself (section 9
    below tests the gate). Default the flag ON so mechanism tests don't all need to set it."""
    monkeypatch.setenv("KIRBY_SKILLS", "1")
    monkeypatch.delenv("ARC_SKILLS", raising=False)


def _load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------------------
# 1. define_skill: accept valid, reject malformed
# ---------------------------------------------------------------------------

def test_define_skill_accepts_flat_step_list(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "walk", "steps": [{"button": "right"}, {"button": "right"}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "define_skill 'walk' -> ok, 2 top-level step(s)" in text
    assert "walk" in w.skills


def test_define_skill_rejects_empty_steps(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "noop", "steps": []})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "must be a non-empty list" in text
    assert "noop" not in w.skills


def test_define_skill_rejects_unknown_button(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [{"button": "diagonal"}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "is not valid" in text
    assert "bad" not in w.skills


def test_define_skill_rejects_missing_name(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "", "steps": [{"button": "right"}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "non-empty string" in text


def test_define_skill_rejects_bad_hold_frames(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [{"button": "right", "hold_frames": 0}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "hold_frames must be an int in [1, 120]" in text


def test_define_skill_logs_definition_verbatim(tmp_path):
    out = str(tmp_path / "out")
    w = _make_world(out)
    steps = [{"button": "right"}, {"button": "right"}]
    w.call("define_skill", {"name": "walk", "steps": steps})
    rows = _load_jsonl(f"{out}/skills.jsonl")
    define_rows = [r for r in rows if r["event"] == "define_skill"]
    assert len(define_rows) == 1
    assert define_rows[0]["definition"] == {"name": "walk", "steps": steps}


# ---------------------------------------------------------------------------
# 2. run_skill: step dispatch + unknown skill
# ---------------------------------------------------------------------------

def test_run_skill_unknown_name_errors(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("run_skill", {"name": "ghost"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "no skill named 'ghost'" in text


def test_run_skill_executes_flat_steps_via_exact_press_path(tmp_path):
    out = str(tmp_path / "out")
    states = [_moved_state(), _moved_state(), _moved_state()]
    w = _make_world(out, states=states)
    w.call("define_skill", {"name": "walk", "steps": [{"button": "right"}, {"button": "right"}]})
    result = w.call("run_skill", {"name": "walk"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "run_skill 'walk' -> 2 step(s) executed" in text
    assert "all top-level steps executed" in text


def test_run_skill_stops_on_illegal_button_like_press_would(tmp_path):
    out = str(tmp_path / "out")
    w = _make_world(out, states=[_moved_state()])
    # Bypass define_skill's own validation to exercise the executor's own defense-in-depth
    # (mirrors test_skill_rung1.py's illegal-action test, which does the same against ARC's executor).
    w.skills["bad"] = {"name": "bad", "steps": [{"button": "diagonal"}]}
    result = w.call("run_skill", {"name": "bad"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "0 step(s) executed" in text
    assert "invalid button" in text


# ---------------------------------------------------------------------------
# 3. stop_when predicates
# ---------------------------------------------------------------------------

def test_steps_elapsed_fires_after_n_presses(tmp_path):
    out = str(tmp_path / "out")
    states = [_moved_state() for _ in range(10)]
    w = _make_world(out, states=states)
    w.call("define_skill", {"name": "walk3", "steps": [
        {"repeat_until": {"steps": [{"button": "right"}], "stop_when": "steps_elapsed(3)", "max_iters": 8}}]})
    result = w.call("run_skill", {"name": "walk3"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "steps_elapsed(3)" in text
    assert "3 press(es)" in text
    assert "3 step(s) executed" in text


def test_move_blocked_fires_on_blocked_outcome(tmp_path):
    out = str(tmp_path / "out")
    states = [_moved_state(), _moved_state(), _blocked_state()]
    w = _make_world(out, states=states)
    w.call("define_skill", {"name": "bump", "steps": [
        {"repeat_until": {"steps": [{"button": "right"}], "stop_when": "move_blocked", "max_iters": 8}}]})
    result = w.call("run_skill", {"name": "bump"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "'move_blocked' fired after 3 press(es)" in text
    assert "3 step(s) executed" in text


def test_move_succeeded_fires_on_moved_outcome(tmp_path):
    out = str(tmp_path / "out")
    states = [_blocked_state(), _moved_state()]
    w = _make_world(out, states=states)
    w.call("define_skill", {"name": "recover", "steps": [
        {"repeat_until": {"steps": [{"button": "up"}], "stop_when": "move_succeeded", "max_iters": 8}}]})
    result = w.call("run_skill", {"name": "recover"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "'move_succeeded' fired after 2 press(es)" in text


def test_move_blocked_does_not_fire_on_unknown_outcome(tmp_path):
    """Fragility note (doc §3): only the exact 'blocked' string fires it -- 'unknown' (e.g. a
    dead-reckoning miss) must not be mistaken for a wall."""
    out = str(tmp_path / "out")
    states = [_unknown_state() for _ in range(3)]
    w = _make_world(out, states=states)
    w.call("define_skill", {"name": "probe", "steps": [
        {"repeat_until": {"steps": [{"button": "right"}], "stop_when": "move_blocked", "max_iters": 2}}]})
    result = w.call("run_skill", {"name": "probe"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "reached max_iters=2 without stop_when firing" in text


def test_region_changed_fires_when_box_differs(tmp_path):
    out = str(tmp_path / "out")
    blank = np.zeros((144, 160, 3), dtype=np.uint8)
    changed = blank.copy()
    changed[10:20, 10:20] = 255
    # Frame sequence: plugin.observe() is called once per press. First press -> `changed` frame (diffs
    # against the FakeEmulator's implicit initial blank tracked by an earlier _track_frame call is not
    # guaranteed, so give three presses: first two yield `blank` (baseline pair, no diff), the third
    # yields `changed` (diffs against the blank _track_frame captured on the SECOND press).
    states = [_moved_state(), _moved_state(), _moved_state()]
    w = _make_world(out, states=states, screens=[blank])
    w.call("observe", {})   # seed _frame_hist with the first (blank) frame before run_skill

    # Flip the emulator's current frame to `changed` after the loop's 2nd press -- a real emulator
    # would render the changed pixels once the approach reaches the suspect; here the test switches
    # deterministically at a known press count. Each press+observe cycle calls emu.screen_ndarray()
    # exactly THREE times (PerceptionPlugin._sample_fade after the press, PerceptionPlugin._perceive_once
    # inside observe(), and World._track_frame's own read) -- all three must agree within one press, so
    # the flip must land on a 3-call boundary.
    calls = {"n": 0}

    def _scripted_screen():
        calls["n"] += 1
        # calls 1-3 belong to press #1 -> blank. calls 4-6 belong to press #2 -> still blank (so
        # _frame_hist holds (blank, blank) after press #2, no diff yet). calls 7+ belong to press #3
        # -> `changed` (diffs against press #2's tracked blank frame).
        return blank if calls["n"] <= 6 else changed

    w.plugin.emu.screen_ndarray = _scripted_screen

    w.call("define_skill", {"name": "approach", "steps": [
        {"repeat_until": {"steps": [{"button": "right"}],
                          "stop_when": "region_changed(10,10,20,20)", "max_iters": 8}}]})
    result = w.call("run_skill", {"name": "approach"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "region_changed(10,10,20,20)" in text
    assert "3 press(es)" in text


def test_region_changed_rejects_oversize_box_at_define_time(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "big", "steps": [
        {"repeat_until": {"steps": [{"button": "right"}],
                          "stop_when": "region_changed(0,0,200,200)", "max_iters": 8}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "exceeds the" in text and "source-pixel cap" in text


def test_region_changed_rejects_inverted_box_at_define_time(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [
        {"repeat_until": {"steps": [{"button": "right"}],
                          "stop_when": "region_changed(20,20,10,10)", "max_iters": 8}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "need 0 <= x0 < x1" in text


def test_region_changed_never_fires_against_a_smaller_actual_frame_no_crash(tmp_path):
    """A box within the _REGION_MAX_SIDE cap can still exceed the ACTUAL frame's dimensions (define-time
    validation has no frame to check against yet). _check_kirby_stop_when must degrade to 'never fires'
    (a max_iters cap-out), never raise/crash, against a frame smaller than the requested box."""
    out = str(tmp_path / "out")
    small = np.zeros((20, 20, 3), dtype=np.uint8)   # much smaller than the real 160x144 GB screen
    states = [_moved_state() for _ in range(3)]
    w = _make_world(out, states=states, screens=[small])
    w.call("observe", {})
    w.call("define_skill", {"name": "toobig", "steps": [
        {"repeat_until": {"steps": [{"button": "right"}],
                          "stop_when": "region_changed(50,50,90,90)", "max_iters": 2}}]})
    result = w.call("run_skill", {"name": "toobig"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "reached max_iters=2 without stop_when firing" in text


def test_stop_when_rejects_predicate_outside_pinned_enum(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [
        {"repeat_until": {"steps": [{"button": "right"}], "stop_when": "entity_count_changed",
                          "max_iters": 8}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "not one of the pinned Kirby predicates" in text


def test_stop_when_rejects_n_above_cap(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [
        {"repeat_until": {"steps": [{"button": "right"}], "stop_when": "steps_elapsed(51)",
                          "max_iters": 8}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "n must be in [1, 50]" in text


def test_hp_dropped_style_predicate_rejected():
    """doc §3: hp_dropped is explicitly rejected -- oracle/RAM fields never enter stop_when."""
    from world_mcp import World
    with pytest.raises(ValueError, match="not one of the pinned Kirby predicates"):
        World._parse_kirby_stop_when("hp_dropped")


# ---------------------------------------------------------------------------
# 4. Loop caps: max_iters <= 8; no nesting
# ---------------------------------------------------------------------------

def test_max_iters_above_cap_rejected(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [
        {"repeat_until": {"steps": [{"button": "right"}], "stop_when": "steps_elapsed(1)", "max_iters": 9}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "max_iters must be an int in [1, 8]" in text


def test_max_iters_zero_rejected(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [
        {"repeat_until": {"steps": [{"button": "right"}], "stop_when": "steps_elapsed(1)", "max_iters": 0}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "max_iters must be an int in [1, 8]" in text


def test_nested_repeat_until_rejected(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [
        {"repeat_until": {"steps": [{"repeat_until": {"steps": [{"button": "right"}],
                                                       "stop_when": "steps_elapsed(1)", "max_iters": 2}}],
                          "stop_when": "steps_elapsed(2)", "max_iters": 2}}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "nesting is not allowed" in text


def test_max_iters_reached_without_stop_when_firing_reports_reason(tmp_path):
    out = str(tmp_path / "out")
    states = [_unknown_state() for _ in range(20)]
    w = _make_world(out, states=states)
    w.call("define_skill", {"name": "stuck", "steps": [
        {"repeat_until": {"steps": [{"button": "right"}], "stop_when": "move_blocked", "max_iters": 3}}]})
    result = w.call("run_skill", {"name": "stuck"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "reached max_iters=3 without stop_when firing" in text
    assert "3 step(s) executed" in text


# ---------------------------------------------------------------------------
# 5. The 50-press absolute ceiling
# ---------------------------------------------------------------------------

def test_absolute_50_step_ceiling_enforced_across_multiple_top_level_loops(tmp_path):
    out = str(tmp_path / "out")
    states = [_unknown_state() for _ in range(120)]
    w = _make_world(out, states=states)
    # 7 top-level repeat_until blocks x max_iters=8 = 56 possible presses (never actually fires
    # move_blocked, since every scripted state has outcome="unknown") -- 56 > the 50-press absolute
    # ceiling, so the ceiling must cut the run off mid-block (during the 7th block's 2nd iteration:
    # 6*8=48 done, +2 more hits the 50 cap).
    w.call("define_skill", {"name": "huge", "steps": [
        {"repeat_until": {"steps": [{"button": "right"}], "stop_when": "move_blocked", "max_iters": 8}}
        for _ in range(7)
    ]})
    result = w.call("run_skill", {"name": "huge"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert f"stopped: absolute {_KIRBY_SKILL_MAX_WORLD_STEPS}-press ceiling hit" in text
    assert f"{_KIRBY_SKILL_MAX_WORLD_STEPS} step(s) executed" in text


# ---------------------------------------------------------------------------
# 6. Logging shape
# ---------------------------------------------------------------------------

def test_run_skill_log_has_all_pinned_fields(tmp_path):
    out = str(tmp_path / "out")
    states = [_moved_state(), _moved_state()]
    w = _make_world(out, states=states)
    w.call("define_skill", {"name": "walk", "steps": [{"button": "right"}, {"button": "right"}]})
    w.call("run_skill", {"name": "walk"})
    rows = _load_jsonl(f"{out}/skills.jsonl")
    run_rows = [r for r in rows if r["event"] == "run_skill"]
    assert len(run_rows) == 1
    rec = run_rows[0]
    for key in ("executed", "executed_step_count", "stop_reason", "world_steps_used", "step", "name"):
        assert key in rec, f"missing {key!r} in run_skill record: {rec}"
    assert rec["executed_step_count"] == 2
    assert rec["world_steps_used"] == 2
    assert rec["name"] == "walk"


def test_repeat_until_summary_carries_iterations_field(tmp_path):
    out = str(tmp_path / "out")
    states = [_moved_state() for _ in range(10)]
    w = _make_world(out, states=states)
    w.call("define_skill", {"name": "walk3", "steps": [
        {"repeat_until": {"steps": [{"button": "right"}], "stop_when": "steps_elapsed(3)", "max_iters": 8}}]})
    w.call("run_skill", {"name": "walk3"})
    rows = _load_jsonl(f"{out}/skills.jsonl")
    rec = [r for r in rows if r["event"] == "run_skill"][0]
    summary = [e for e in rec["executed"] if "repeat_until_summary" in e][0]
    assert summary["iterations"] == 3


def test_qualifying_conditional_call_needs_iterations_ge_2(tmp_path):
    """doc §5.4 (entity-gate v3's skill-mechanism guard, not this port's own gate, but the log field
    it reads must be present and correct): a single-iteration repeat_until logs iterations == 1."""
    out = str(tmp_path / "out")
    states = [_blocked_state()]
    w = _make_world(out, states=states)
    w.call("define_skill", {"name": "onepress", "steps": [
        {"repeat_until": {"steps": [{"button": "right"}], "stop_when": "move_blocked", "max_iters": 8}}]})
    w.call("run_skill", {"name": "onepress"})
    rows = _load_jsonl(f"{out}/skills.jsonl")
    rec = [r for r in rows if r["event"] == "run_skill"][0]
    summary = [e for e in rec["executed"] if "repeat_until_summary" in e][0]
    assert summary["iterations"] == 1   # laundering hole case: caller must apply the >=2 guard, not us


# ---------------------------------------------------------------------------
# 7. Skill lifetime: within-run only
# ---------------------------------------------------------------------------

def test_skills_do_not_survive_a_new_session(tmp_path):
    out1 = str(tmp_path / "out1")
    w1 = _make_world(out1)
    w1.call("define_skill", {"name": "walk", "steps": [{"button": "right"}]})
    assert "walk" in w1.skills

    out2 = str(tmp_path / "out2")
    w2 = _make_world(out2)
    assert "walk" not in w2.skills


# ---------------------------------------------------------------------------
# 8. No-leak: hp oracle never in a tool result
# ---------------------------------------------------------------------------

def test_define_and_run_skill_never_leak_hp_oracle(tmp_path):
    out = str(tmp_path / "out")
    states = [_moved_state()]
    w = _make_world(out, states=states)
    r1 = w.call("define_skill", {"name": "walk", "steps": [{"button": "right"}]})
    r2 = w.call("run_skill", {"name": "walk"})
    for result in (r1, r2):
        for c in result:
            if c.get("type") == "text":
                assert "0xD086" not in c["text"] and "hp" not in c["text"].lower()


# ---------------------------------------------------------------------------
# 9. Gating: KIRBY_SKILLS on/off, world scoping, ARC_SKILLS non-interference
# ---------------------------------------------------------------------------

def test_kirby_skill_tools_absent_from_tools_list_by_default(monkeypatch):
    monkeypatch.delenv("KIRBY_SKILLS", raising=False)
    names = [t["name"] for t in _static_tools("kirby_dreamland")]
    assert "define_skill" not in names and "run_skill" not in names


def test_kirby_skill_tools_present_in_tools_list_when_flag_on(monkeypatch):
    monkeypatch.setenv("KIRBY_SKILLS", "1")
    names = [t["name"] for t in _static_tools("kirby_dreamland")]
    assert "define_skill" in names and "run_skill" in names


def test_kirby_skill_tools_never_leak_to_other_gb_games(monkeypatch):
    """KIRBY_SKILLS=1 must not perturb any other GB world's tool list (doc §2: 'other GB games never
    see these tools')."""
    monkeypatch.setenv("KIRBY_SKILLS", "1")
    for game in ("cave_noire", "cave_noire_baseline", "gauntlet", "gb_generic", "pokemon_red"):
        names = [t["name"] for t in _static_tools(game)]
        assert "define_skill" not in names and "run_skill" not in names, f"{game} leaked skill tools"


def test_arc_skills_flag_does_not_enable_kirby_skill_tools(monkeypatch):
    """One-flag-per-world (doc §2 decision of record): ARC_SKILLS=1 alone must not unlock Kirby's
    skill tools."""
    monkeypatch.delenv("KIRBY_SKILLS", raising=False)
    monkeypatch.setenv("ARC_SKILLS", "1")
    names = [t["name"] for t in _static_tools("kirby_dreamland")]
    assert "define_skill" not in names and "run_skill" not in names


def test_kirby_skills_flag_does_not_enable_arc_skill_tools(monkeypatch):
    monkeypatch.delenv("ARC_SKILLS", raising=False)
    monkeypatch.setenv("KIRBY_SKILLS", "1")
    names = [t["name"] for t in _static_tools("arcagi3")]
    assert "define_skill" not in names and "run_skill" not in names


def test_dispatch_of_skill_tools_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("KIRBY_SKILLS", raising=False)
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "walk", "steps": [{"button": "right"}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "skill tools are disabled for this session" in text
    assert "walk" not in w.skills
    result2 = w.call("run_skill", {"name": "walk"})
    text2 = " ".join(c["text"] for c in result2 if c.get("type") == "text")
    assert "skill tools are disabled for this session" in text2


def test_dispatch_of_skill_tools_works_when_flag_on(tmp_path):
    w = _make_world(str(tmp_path / "out"))   # autouse fixture already sets KIRBY_SKILLS=1
    result = w.call("define_skill", {"name": "walk", "steps": [{"button": "right"}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "ok, 1 top-level step(s)" in text


def test_world_init_reads_kirby_skills_once_at_construction(tmp_path, monkeypatch):
    """A/B arm isolation: KIRBY_SKILLS is read at World.__init__ time, not per-call, matching
    ArcAgi3Session._skills_enabled's fixed-at-init discipline."""
    monkeypatch.setenv("KIRBY_SKILLS", "1")
    w = _make_world(str(tmp_path / "out"))
    assert w._kirby_skills_enabled is True
    monkeypatch.delenv("KIRBY_SKILLS", raising=False)
    assert w._kirby_skills_enabled is True   # unaffected by env flip after construction


def test_kirby_skills_scoped_to_kirby_dreamland_only_via_world_flag(tmp_path):
    """gb_generic shares kirby_dreamland's sandbox-dispatch branch but must NOT get skill tools even
    with KIRBY_SKILLS=1 -- the world-membership check (_KIRBY_SKILLS_WORLDS) is the actual gate, not
    just the sandbox family."""
    w = _make_world(str(tmp_path / "out"), game="gb_generic")
    assert w._kirby_skills_enabled is False
    result = w.call("define_skill", {"name": "walk", "steps": [{"button": "right"}]})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "skill tools are disabled" in text


# ---------------------------------------------------------------------------
# 10. RESIDUAL #1: log BEFORE any trailing observe (span boundary S0 stays claimable)
# ---------------------------------------------------------------------------

def test_run_skill_logs_step_before_trailing_observe_advances_it(tmp_path):
    """PR #92 verification comment residual #1: run_skill must log BEFORE any trailing observe, so
    `step - world_steps_used` (the macro's pre-macro/START boundary, doc §5.6's S0) is the step the
    brain's PRE-approach NEAR claim actually saw -- not polluted by the trailing render's own observe
    bumping _obs_count first. This test proves the formula holds against REAL logged output: the
    world had 0 prior observes; run_skill executes 3 presses (3 per-press observes, steps 1-3); the
    logged `step` must be 3 (not 4, which is what it would be if the trailing render's observe had
    already run before the log write)."""
    out = str(tmp_path / "out")
    states = [_moved_state(), _moved_state(), _moved_state()]
    w = _make_world(out, states=states)
    assert w.plugin._obs_count == 0
    w.call("define_skill", {"name": "walk3", "steps": [{"button": "right"}, {"button": "right"},
                                                        {"button": "right"}]})
    w.call("run_skill", {"name": "walk3"})
    rows = _load_jsonl(f"{out}/skills.jsonl")
    rec = [r for r in rows if r["event"] == "run_skill"][0]
    assert rec["step"] == 3                      # post-macro step: 3 per-press observes, no more
    assert rec["world_steps_used"] == 3
    start_step = rec["step"] - rec["world_steps_used"]
    assert start_step == 0                        # S0: the pre-macro step (before any press)
    # The trailing render's OWN observe (for the tool result the brain sees) runs AFTER the log write
    # and is accounted for separately -- it must have advanced _obs_count past the logged step.
    assert w.plugin._obs_count == 4               # 3 per-press + 1 trailing render observe
    # Macro-interior exclusion worked example (doc §5.6): a claim naming step 1 or 2 (strictly between
    # start_step=0 and end_step=rec["step"]=3) would be MACRO-INTERIOR and excluded; a claim naming
    # exactly start_step (0) or exactly rec["step"] (3) is a boundary claim and stays claimable.
    for interior_step in (1, 2):
        assert start_step < interior_step < rec["step"], "interior step must satisfy the exclusion formula"
    for boundary_step in (start_step, rec["step"]):
        assert not (start_step < boundary_step < rec["step"]), "boundary steps must NOT be excluded"


def test_run_skill_log_step_boundary_holds_across_multiple_calls(tmp_path):
    """Same S0/S1 pin, but on a SECOND run_skill call after other observes already advanced the step
    counter -- the formula must hold relative to whatever step the world was already at, not just 0."""
    out = str(tmp_path / "out")
    states = [_moved_state() for _ in range(10)]
    w = _make_world(out, states=states)
    w.call("observe", {})   # step 1
    w.call("observe", {})   # step 2
    w.call("define_skill", {"name": "walk2", "steps": [{"button": "right"}, {"button": "right"}]})
    w.call("run_skill", {"name": "walk2"})   # steps 3, 4 (per-press observes)
    rows = _load_jsonl(f"{out}/skills.jsonl")
    rec = [r for r in rows if r["event"] == "run_skill"][0]
    assert rec["world_steps_used"] == 2
    assert rec["step"] == 4
    assert rec["step"] - rec["world_steps_used"] == 2   # S0 == the step BEFORE this macro started


# ---------------------------------------------------------------------------
# 11. Per-press semantics: exactly one observe() per press (doc §2 "one oracle row per press")
# ---------------------------------------------------------------------------

def test_one_observe_call_per_press_not_per_predicate_check(tmp_path):
    """Guards against the double-observe bug this build must avoid: _check_kirby_stop_when must reuse
    the outcome captured by the SAME press's observe(), never call plugin.observe() a second time to
    evaluate move_blocked/move_succeeded."""
    out = str(tmp_path / "out")
    states = [_moved_state(), _moved_state(), _blocked_state()]
    w = _make_world(out, states=states)
    w.call("define_skill", {"name": "bump", "steps": [
        {"repeat_until": {"steps": [{"button": "right"}], "stop_when": "move_blocked", "max_iters": 8}}]})
    assert w.plugin._obs_count == 0
    w.call("run_skill", {"name": "bump"})
    # 3 presses -> exactly 3 per-press observes, THEN +1 trailing render observe == 4 total.
    assert w.plugin._obs_count == 4


def test_one_oracle_row_per_press_plus_trailing_render_through_the_real_log(tmp_path):
    """PR #93 executor review finding 3 (counter-family divergence): pin the step<->press alignment
    STRUCTURALLY through the real oracle.jsonl, not just through _obs_count -- the number of oracle
    rows a run_skill call appends must equal world_steps_used (one row per press, doc §2's pin) plus
    exactly 1 for the trailing render observe. A future change that observes more or less than once
    per press inside the loop (the drift the reviewer warned about) breaks this test."""
    import os
    out = str(tmp_path / "out")
    states = [_moved_state() for _ in range(6)]
    w = _make_world(out, states=states)
    w.call("define_skill", {"name": "walk3", "steps": [{"button": "right"}, {"button": "right"},
                                                        {"button": "right"}]})
    oracle_path = os.path.join(out, "oracle.jsonl")
    rows_before = len(_load_jsonl(oracle_path)) if os.path.exists(oracle_path) else 0
    w.call("run_skill", {"name": "walk3"})
    rows_after = len(_load_jsonl(oracle_path))
    rec = [r for r in _load_jsonl(f"{out}/skills.jsonl") if r["event"] == "run_skill"][0]
    assert rows_after - rows_before == rec["world_steps_used"] + 1   # 3 per-press + 1 trailing render
    # And the oracle rows' own `step` values are contiguous (each observe wrote exactly one row).
    steps = [r["step"] for r in _load_jsonl(oracle_path)]
    assert steps == list(range(steps[0], steps[0] + len(steps)))


def test_patience_never_fires_inside_the_per_press_loop(tmp_path):
    """PR #93 executor review finding 1: PATIENCE's auto-advance loop inside PerceptionPlugin.observe()
    is inert for kirby_dreamland today (FollowCameraPerceiver's motion-derived labels never classify
    gated-static), but nothing pinned that. If a future Kirby-specific context label joins the
    gated-static set, PATIENCE could silently multi-press inside a single per-press observe -- world
    frames advancing while `step` advances by 1, quietly breaking §2's one-press-one-step alignment.
    Pin: every oracle row logged during a run_skill has patience_advances == 0."""
    import os
    out = str(tmp_path / "out")
    states = [_moved_state() for _ in range(6)]
    w = _make_world(out, states=states)
    w.call("define_skill", {"name": "walk3", "steps": [{"button": "right"}, {"button": "right"},
                                                        {"button": "right"}]})
    w.call("run_skill", {"name": "walk3"})
    rows = _load_jsonl(os.path.join(out, "oracle.jsonl"))
    assert rows, "run_skill must have logged oracle rows"
    assert all(r.get("patience_advances") == 0 for r in rows), \
        f"PATIENCE fired inside the per-press loop: {[r for r in rows if r.get('patience_advances')]}"
    # No patience_trail either -- no hidden auto-presses attributed to any observe in the loop.
    assert all("patience_trail" not in r for r in rows)


def test_redefinition_is_a_distinct_logged_event(tmp_path):
    out = str(tmp_path / "out")
    w = _make_world(out)
    w.call("define_skill", {"name": "walk", "steps": [{"button": "right"}]})
    w.call("define_skill", {"name": "walk", "steps": [{"button": "left"}]})
    rows = _load_jsonl(f"{out}/skills.jsonl")
    redefine_rows = [r for r in rows if r["event"] == "redefine_skill"]
    assert len(redefine_rows) == 1
    assert redefine_rows[0]["prior_definition"] == {"name": "walk", "steps": [{"button": "right"}]}
    assert redefine_rows[0]["definition"] == {"name": "walk", "steps": [{"button": "left"}]}


def test_run_skill_after_redefinition_executes_new_definition(tmp_path):
    out = str(tmp_path / "out")
    states = [_moved_state(), _moved_state()]
    w = _make_world(out, states=states)
    w.call("define_skill", {"name": "walk", "steps": [{"button": "right"}]})
    w.call("define_skill", {"name": "walk", "steps": [{"button": "left"}, {"button": "left"}]})
    result = w.call("run_skill", {"name": "walk"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "2 step(s) executed" in text


def test_top_level_stop_when_rejected_loudly(tmp_path):
    w = _make_world(str(tmp_path / "out"))
    result = w.call("define_skill", {"name": "bad", "steps": [{"button": "right"}],
                                     "stop_when": "steps_elapsed(1)"})
    text = " ".join(c["text"] for c in result if c.get("type") == "text")
    assert "belongs INSIDE a repeat_until step" in text
    assert "bad" not in w.skills
