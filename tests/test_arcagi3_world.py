"""Unit tests for the ARC-AGI-3 world (core/arcagi3_world.py + world_mcp.ArcAgi3Session +
_arcagi3_static_tools). CI-safe: no real network — requests.Session.post/get are monkeypatched with a
FakeArcApi that stands in for https://three.arcprize.org, scripted from the docs' worked JSON examples
(same fixture data runs/arcagi3_probe/client.py's --offline mode uses; see PROBE_REPORT.md).

Covers:
  1. Grid rendering (render_grid): a 64x64 grid and a smaller grid, both single-char-per-cell, rows
     capped at the grid's own width (<=64 chars, since the API caps grids at 64x64).
  2. diff_grids correctness: no-prior-frame case, a real diff (by-color-transition counts), a
     shape-change case (e.g. a level transition resizing the grid).
  3. available_actions validation + ACTION6 coordinate validation via ArcAgi3Session._act /.call.
  4. Oracle-only score fields: a leak test that greps every tool result's JSON blob for
     levels_completed/win_levels/state substrings — must never appear on the wire.
  5. Throttle logic: ArcAgi3Client._throttle enforces >= _MIN_INTERVAL between calls.
  6. tools/list wiring: arcagi3 advertises exactly observe/remember/act/reset_game/define_skill/run_skill.

Skill compilation rung 1 (define_skill/run_skill, reports/2026-07-03-skill-compilation-design.md) has
its own dedicated test module: tests/test_skill_rung1.py.
"""
from __future__ import annotations

import argparse
import json
import time

import pytest

import world_mcp
from core.arcagi3_world import ALL_ACTIONS, ArcAgi3Client, _MIN_INTERVAL, diff_grids, render_grid
from world_mcp import GAMES, ArcAgi3Session, _ARCAGI3_WORLDS, _static_tools


# ---------------------------------------------------------------------------
# 1. render_grid
# ---------------------------------------------------------------------------

def test_render_grid_small():
    grid = [[0, 0, 1], [1, 1, 1]]
    text = render_grid(grid)
    lines = text.splitlines()
    assert lines == ["001", "111"]


def test_render_grid_64x64_rows_capped_at_64_chars():
    grid = [[i % 16 for i in range(64)] for _ in range(64)]
    text = render_grid(grid)
    lines = text.splitlines()
    assert len(lines) == 64
    assert all(len(line) <= 64 for line in lines)
    # index 15 renders as hex 'F', index 10 as 'A', etc.
    assert lines[0][15] == "F"
    assert lines[0][10] == "A"


def test_render_grid_empty():
    assert render_grid([]) == "(empty grid)"


def test_render_grid_rejects_out_of_range_color_loudly():
    # PR #77 review finding 3: an out-of-spec color index must raise, never silently wrap (idx % 16).
    with pytest.raises(ValueError, match="outside the documented"):
        render_grid([[0, 16]])
    with pytest.raises(ValueError, match="outside the documented"):
        render_grid([[-1]])


def test_render_grid_rejects_non_numeric_cell_loudly():
    with pytest.raises(ValueError, match="non-numeric"):
        render_grid([[0, "x"]])


# ---------------------------------------------------------------------------
# 2. diff_grids
# ---------------------------------------------------------------------------

def test_diff_grids_first_frame_has_no_prior():
    d = diff_grids(None, [[0, 0], [0, 0]])
    assert d["changed"] == 0
    assert "first frame" in d["note"]


def test_diff_grids_counts_changes_by_color_transition():
    prev = [[0, 0], [0, 0]]
    curr = [[0, 1], [1, 0]]
    d = diff_grids(prev, curr)
    assert d["changed"] == 2
    assert d["by_color"] == {"0->1": 2}


def test_diff_grids_multiple_transitions():
    prev = [[0, 1, 2]]
    curr = [[0, 2, 2]]
    d = diff_grids(prev, curr)
    assert d["changed"] == 1
    assert d["by_color"] == {"1->2": 1}


def test_diff_grids_shape_change_reported_not_crashed():
    prev = [[0, 0], [0, 0]]
    curr = [[0, 0, 0]]
    d = diff_grids(prev, curr)
    assert d["changed"] == -1
    assert "shape changed" in d["note"]


# ---------------------------------------------------------------------------
# Fake ARC API: scripted responses keyed by (method, path), mirroring the docs' worked examples.
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeArcApi:
    """Scripts POST/GET calls against a requests.Session, keyed by path. `frames` is a list of
    canned FrameData dicts returned in order for successive RESET/ACTION calls (mirrors the probe
    client's fixture data); scorecard open/close return fixed small dicts."""

    def __init__(self, frames):
        self._frames = list(frames)
        self.calls = []
        self.rate_limit_once = False   # if True, the FIRST action call 429s once before succeeding

    def post(self, url, json=None, timeout=None):
        self.calls.append(("POST", url, json))
        if url.endswith("/api/scorecard/open"):
            return _FakeResp({"card_id": "card-123"})
        if url.endswith("/api/scorecard/close"):
            return _FakeResp({"card_id": "card-123", "score": 0})
        if url.endswith("/api/cmd/RESET") or "/api/cmd/ACTION" in url:
            if self.rate_limit_once and len([c for c in self.calls if "/api/cmd/" in c[1]]) == 1:
                self.rate_limit_once = False
                return _FakeResp({}, status=429)
            return _FakeResp(self._frames.pop(0))
        raise AssertionError(f"unexpected POST {url}")

    def get(self, url, timeout=None):
        self.calls.append(("GET", url, None))
        raise AssertionError(f"unexpected GET {url}")


def _install_fake_api(monkeypatch, frames):
    fake = FakeArcApi(frames)
    monkeypatch.setattr("requests.Session.post",
                        lambda self, url, json=None, timeout=None: fake.post(url, json=json, timeout=timeout))
    monkeypatch.setattr("requests.Session.get",
                        lambda self, url, timeout=None: fake.get(url, timeout=timeout))
    monkeypatch.setattr("time.sleep", lambda s: None)   # don't actually wait in tests
    return fake


_RESET_FRAME = {
    "game_id": "ls20-abc", "guid": "guid-1", "frame": [[[0, 0], [0, 0]]],
    "state": "NOT_FINISHED", "levels_completed": 0, "win_levels": 254,
    "available_actions": [1, 2, 3, 4],
}
_ACTION1_FRAME = {
    "game_id": "ls20-abc", "guid": "guid-1", "frame": [[[0, 0], [1, 1]]],
    "state": "NOT_FINISHED", "levels_completed": 3, "win_levels": 254,
    "available_actions": [1, 2, 3, 4, 6],
}
_ACTION6_FRAME = {
    "game_id": "ls20-abc", "guid": "guid-1", "frame": [[[1, 1], [1, 1]]],
    "state": "NOT_FINISHED", "levels_completed": 5, "win_levels": 254,
    "available_actions": [1, 2, 3, 4],
}
_WIN_FRAME = {
    "game_id": "ls20-abc", "guid": "guid-1", "frame": [[[1, 1], [1, 1]]],
    "state": "WIN", "levels_completed": 254, "win_levels": 254,
    "available_actions": [1, 2, 3, 4],
}


def _args(out: str, arc_game="ls20") -> argparse.Namespace:
    return argparse.Namespace(game="arcagi3", rom=None, init_state=None, out=out, record=False,
                              with_screenshot=False, keep_frames=False, seeds_file=None, seed=None,
                              arc_game=arc_game)


# ---------------------------------------------------------------------------
# 3. available_actions validation + ACTION6 coordinate validation
# ---------------------------------------------------------------------------

def test_session_boots_and_observe_shows_reset_grid(monkeypatch, tmp_path):
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    text = sess.call("observe", {})[0]["text"]
    assert "00" in text and "available_actions: [1, 2, 3, 4]" in text
    assert "step: 0" in text


def test_act_rejects_action_not_in_available_actions(monkeypatch, tmp_path):
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("act", {"action": "ACTION6", "x": 1, "y": 1})   # not in [1,2,3,4]
    text = result[0]["text"]
    assert "not currently legal" in text
    assert "ACTION6" in text


def test_act_accepts_legal_simple_action(monkeypatch, tmp_path):
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME), dict(_ACTION1_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("act", {"action": "ACTION1"})
    text = result[0]["text"]
    assert "act ACTION1 -> ok" in text


def test_first_post_action_observe_diffs_against_the_reset_grid(monkeypatch, tmp_path):
    """Regression (PR #77 review finding 2): the prior-grid gate must not key on _step_count —
    client.reset() hardcodes step=0, so a step-count gate reported "first frame — nothing to diff"
    on the FIRST post-action observe of every episode even though the RESET grid exists to diff
    against. RESET grid is [[0,0],[0,0]], ACTION1 grid is [[0,0],[1,1]] -> exactly 2 cells 0->1."""
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME), dict(_ACTION1_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("act", {"action": "ACTION1"})
    obs_text = result[-1]["text"]
    assert "first frame" not in obs_text
    assert "2 cell(s) changed (0->1x2)" in obs_text
    # and a plain observe right after reports the same diff (it reads the same cached state)
    obs2 = sess.call("observe", {})[0]["text"]
    assert "2 cell(s) changed (0->1x2)" in obs2


def test_reset_frame_has_no_prior_to_diff_even_mid_session(monkeypatch, tmp_path):
    """A reset_game mid-session starts a NEW instance — its first frame must not diff against the
    previous instance's grid (the gate keys on the frame being a RESET, not on step count)."""
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME), dict(_ACTION1_FRAME), dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    sess.call("act", {"action": "ACTION1"})
    result = sess.call("reset_game", {})
    assert "first frame" in result[-1]["text"]


def test_act_action6_requires_x_and_y(monkeypatch, tmp_path):
    frames = [dict(_RESET_FRAME)]
    frames[0] = {**_RESET_FRAME, "available_actions": [6]}
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("act", {"action": "ACTION6"})   # missing x, y
    text = result[0]["text"]
    assert "requires integer x and y" in text


def test_act_action6_rejects_out_of_range_coords(monkeypatch, tmp_path):
    frames = [{**_RESET_FRAME, "available_actions": [6]}]
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("act", {"action": "ACTION6", "x": 64, "y": 0})   # 64 is out of [0,63]
    text = result[0]["text"]
    assert "must be in [0, 63]" in text


def test_act_action6_accepts_valid_coords(monkeypatch, tmp_path):
    frames = [{**_RESET_FRAME, "available_actions": [6]}, dict(_ACTION6_FRAME)]
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    result = sess.call("act", {"action": "ACTION6", "x": 12, "y": 34})
    text = result[0]["text"]
    assert "act ACTION6 (12,34) -> ok" in text


def test_act_rejects_unknown_action_name():
    assert "ACTION9" not in ALL_ACTIONS


def test_act_after_win_is_rejected_except_reset(monkeypatch, tmp_path):
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME), dict(_WIN_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    sess.call("act", {"action": "ACTION1"})
    result = sess.call("act", {"action": "ACTION2"})
    text = result[0]["text"]
    assert "game is over" in text


def test_reset_game_starts_new_instance(monkeypatch, tmp_path):
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME), dict(_WIN_FRAME), dict(_RESET_FRAME)])
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    sess.call("act", {"action": "ACTION1"})
    result = sess.call("reset_game", {})
    assert "new instance started" in result[0]["text"]
    assert "step: 0" in result[1]["text"]


# ---------------------------------------------------------------------------
# 4. oracle-only score fields: never leak levels_completed/win_levels/state into a tool result
# ---------------------------------------------------------------------------

_FORBIDDEN_SUBSTRINGS = ("levels_completed", "win_levels")


def test_no_tool_result_leaks_score_fields(monkeypatch, tmp_path):
    frames = [dict(_RESET_FRAME), dict(_ACTION1_FRAME)]
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(str(tmp_path / "out")))
    calls = [("observe", {}), ("act", {"action": "ACTION1"}), ("observe", {}),
            ("remember", {"lesson": "explore the grid edges first"})]
    for name, cargs in calls:
        result = sess.call(name, cargs)
        blob = json.dumps(result).lower()
        for banned in _FORBIDDEN_SUBSTRINGS:
            assert banned not in blob, f"tool {name!r} leaked forbidden token {banned!r}: {blob}"


def test_oracle_jsonl_is_where_score_fields_actually_go(monkeypatch, tmp_path):
    out = str(tmp_path / "out")
    frames = [dict(_RESET_FRAME), dict(_ACTION1_FRAME)]
    _install_fake_api(monkeypatch, frames)
    sess = ArcAgi3Session(_args(out))
    sess.call("act", {"action": "ACTION1"})
    with open(f"{out}/oracle.jsonl", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert any("levels_completed" in r for r in rows)
    assert any(r.get("levels_completed", 0) == 3 for r in rows)


# ---------------------------------------------------------------------------
# 5. throttle logic
# ---------------------------------------------------------------------------

def test_client_throttle_enforces_min_interval(monkeypatch):
    slept = []
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))
    fake_now = [1000.0]
    monkeypatch.setattr("time.monotonic", lambda: fake_now[0])

    client = ArcAgi3Client(api_key="k")
    client._throttle()   # first call: _last_call_ts starts at 0.0, way in the "past" -- no sleep needed
    assert not slept

    slept.clear()
    fake_now[0] += _MIN_INTERVAL   # advance exactly one interval since the last recorded call
    client._throttle()
    # should NOT need to sleep (or sleep ~0) since a full interval has passed
    assert not slept or slept[-1] <= 1e-6


def test_client_throttle_sleeps_when_called_too_soon(monkeypatch):
    slept = []
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))
    fake_now = [2000.0]
    monkeypatch.setattr("time.monotonic", lambda: fake_now[0])

    client = ArcAgi3Client(api_key="k")
    client._last_call_ts = fake_now[0]   # pretend a call JUST happened
    client._throttle()
    assert slept, "a call arriving immediately after the last one must sleep"
    assert slept[-1] == pytest.approx(_MIN_INTERVAL, abs=1e-6)


def test_client_post_retries_on_429_then_succeeds(monkeypatch, tmp_path):
    monkeypatch.setattr("time.sleep", lambda s: None)
    fake = FakeArcApi([dict(_RESET_FRAME)])
    fake.rate_limit_once = True
    monkeypatch.setattr("requests.Session.post",
                        lambda self, url, json=None, timeout=None: fake.post(url, json=json, timeout=timeout))
    client = ArcAgi3Client(api_key="k")
    client.open_scorecard()
    fr = client.reset("ls20")
    assert fr.state == "NOT_FINISHED"
    # exactly 2 POSTs to /api/cmd/RESET: the 429'd attempt + the retry that succeeded
    reset_calls = [c for c in fake.calls if "/api/cmd/RESET" in c[1]]
    assert len(reset_calls) == 2


# ---------------------------------------------------------------------------
# 6. tools/list wiring
# ---------------------------------------------------------------------------

def test_arcagi3_advertises_expected_tools():
    names = {t["name"] for t in _static_tools("arcagi3")}
    assert names == {"observe", "remember", "act", "reset_game", "define_skill", "run_skill"}


def test_arcagi3_registered_in_games():
    assert "arcagi3" in GAMES
    assert GAMES["arcagi3"]["watch"] == {}
    assert "arcagi3" in _ARCAGI3_WORLDS


def test_other_worlds_unaffected_by_arcagi3_addition():
    names = {t["name"] for t in _static_tools("cave_noire")}
    assert "act" not in names and "reset_game" not in names


def test_missing_arc_game_fails_loud_at_launch(monkeypatch):
    monkeypatch.setattr("sys.argv", ["world_mcp.py", "--game", "arcagi3"])
    with pytest.raises(SystemExit, match="--arc-game"):
        world_mcp.main()


def test_missing_arc_api_key_fails_loud_at_launch(monkeypatch):
    """PR #77 review finding 1: an absent/empty ARC_API_KEY must be rejected in main()'s launch
    validation — never deferred to the lazily-built session, where it would die with a generic 401
    mid-protocol. The error names the missing variable but never echoes any value."""
    monkeypatch.delenv("ARC_API_KEY", raising=False)
    monkeypatch.setattr("sys.argv", ["world_mcp.py", "--game", "arcagi3", "--arc-game", "ls20"])
    with pytest.raises(SystemExit, match="ARC_API_KEY"):
        world_mcp.main()


def test_empty_arc_api_key_fails_loud_at_launch(monkeypatch):
    monkeypatch.setenv("ARC_API_KEY", "")
    monkeypatch.setattr("sys.argv", ["world_mcp.py", "--game", "arcagi3", "--arc-game", "ls20"])
    with pytest.raises(SystemExit, match="ARC_API_KEY"):
        world_mcp.main()


def test_record_fails_loud_at_launch_for_arcagi3(monkeypatch):
    monkeypatch.setenv("ARC_API_KEY", "test-key")   # get past the key guard to reach the record guard
    monkeypatch.setattr("sys.argv", ["world_mcp.py", "--game", "arcagi3", "--arc-game", "ls20", "--record"])
    with pytest.raises(SystemExit, match="--record is not supported"):
        world_mcp.main()


def test_frame_count_greater_than_one_uses_last_grid_and_is_logged(monkeypatch, tmp_path):
    """Docs say `frame` may hold 1-N grids; only the LAST is rendered, and frame_count is logged to
    the oracle row (never the tool result) so we can tell if N>1 ever actually happens live."""
    multi = {**_ACTION1_FRAME, "frame": [[[0, 0], [0, 0]], [[9, 9], [9, 9]]]}
    _install_fake_api(monkeypatch, [dict(_RESET_FRAME), multi])
    out = str(tmp_path / "out")
    sess = ArcAgi3Session(_args(out))
    result = sess.call("act", {"action": "ACTION1"})
    text = result[-1]["text"]
    assert "99" in text and "00" not in text.splitlines()[1]   # rendered the LAST grid ([9,9],[9,9])
    with open(f"{out}/oracle.jsonl", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert any(r.get("frame_count") == 2 for r in rows)
