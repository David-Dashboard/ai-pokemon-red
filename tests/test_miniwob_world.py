"""Unit tests for the MiniWoB++ computer-use world (core/miniwob_world.py + world_mcp.py's
MiniWobSession/_miniwob_static_tools). CI-safe: no browser, no miniwob/selenium install — a FakeMiniWobEnv
stands in for the real gymnasium env, monkeypatched into MiniWobWorld so these tests run anywhere.

Covers (per the plan):
  1. Click-coordinate clamping to the real 177px viewport (the probe's documented gotcha).
  2. observe()'s payload shape (utterance + screen size + blobs; no DOM, no reward, no fields).
  3. reward/dom never appear in ANY MiniWobSession.call() tool-result path (grep-style assertion).
  4. tools/list wiring: miniwob_* worlds advertise exactly the expected tool set; other worlds unaffected.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pytest

import world_mcp
from core.miniwob_world import MiniWobWorld, VIEWPORT_HEIGHT, VIEWPORT_WIDTH
from world_mcp import GAMES, MiniWobSession, _MINIWOB_WORLDS, _static_tools


# ---------------------------------------------------------------------------
# Fake miniwob env: a gymnasium-shaped Env stand-in, no browser/selenium/miniwob install needed.
# ---------------------------------------------------------------------------

class _FakeUnwrapped:
    def create_action(self, action_type, **kwargs):
        return {"type": action_type, **kwargs}


class _FakeMiniwobEnv:
    """Minimal stand-in for miniwob.envs.miniwob_envs.ClickButtonEnv etc. Deliberately includes
    dom_elements/fields in its obs dict (like the real env) so MiniWobWorld's withholding is
    exercised, not just assumed."""

    def __init__(self, render_mode=None):
        self.render_mode = render_mode
        self.unwrapped = _FakeUnwrapped()
        self._step_n = 0

    def _obs(self):
        frame = np.zeros((210, 160, 3), dtype=np.uint8)
        frame[100:110, 20:30] = 200   # a fake "button" blob
        return {
            "utterance": 'Click on the "Ok" button.',
            "dom_elements": ({"ref": 1, "tag": "button", "text": "Ok", "left": 20, "top": 100},),
            "screenshot": frame,
            "fields": (("target", "Ok"),),
        }

    def reset(self, seed=None):
        self._step_n = 0
        return self._obs(), {"info_marker": "reset"}

    def step(self, action):
        self._step_n += 1
        terminated = self._step_n >= 1 and action.get("type") == "CLICK_COORDS"
        info = {"info_marker": "step"}
        return self._obs(), (0.99 if terminated else 0.0), terminated, False, info

    def close(self):
        pass


@pytest.fixture
def fake_env_cls(monkeypatch):
    """Patch core.miniwob_world's lazy `from miniwob.envs import miniwob_envs` import point so
    MiniWobWorld() never needs the real miniwob/selenium/Chromium stack."""
    import types
    fake_miniwob_pkg = types.ModuleType("miniwob")
    fake_envs_pkg = types.ModuleType("miniwob.envs")
    fake_envs_mod = types.ModuleType("miniwob.envs.miniwob_envs")
    fake_envs_mod.ClickButtonEnv = _FakeMiniwobEnv
    fake_envs_mod.ClickCheckboxesEnv = _FakeMiniwobEnv
    fake_envs_mod.FocusTextEnv = _FakeMiniwobEnv
    fake_envs_pkg.miniwob_envs = fake_envs_mod
    import sys
    monkeypatch.setitem(sys.modules, "miniwob", fake_miniwob_pkg)
    monkeypatch.setitem(sys.modules, "miniwob.envs", fake_envs_pkg)
    monkeypatch.setitem(sys.modules, "miniwob.envs.miniwob_envs", fake_envs_mod)
    return _FakeMiniwobEnv


def _args(game: str, out: str) -> "world_mcp.argparse.Namespace":
    import argparse
    return argparse.Namespace(game=game, rom=None, init_state=None, out=out, record=False,
                              with_screenshot=False, keep_frames=False)


# ---------------------------------------------------------------------------
# 1. Click clamp to the real 177px viewport.
# ---------------------------------------------------------------------------

def test_click_clamps_y_to_viewport_height(fake_env_cls):
    w = MiniWobWorld("click-button")
    w.reset()
    # env.step receives the CLAMPED coords via create_action; capture what MiniWobWorld actually sent.
    sent = {}
    orig_create_action = w.env.unwrapped.create_action
    def _spy(action_type, **kwargs):
        sent.update(kwargs)
        return orig_create_action(action_type, **kwargs)
    w.env.unwrapped.create_action = _spy
    w.click(50, 999)   # y way beyond VIEWPORT_HEIGHT
    assert sent["coords"][1] == VIEWPORT_HEIGHT - 1
    w.close()


def test_click_clamps_x_to_viewport_width(fake_env_cls):
    w = MiniWobWorld("click-button")
    w.reset()
    sent = {}
    orig_create_action = w.env.unwrapped.create_action
    def _spy(action_type, **kwargs):
        sent.update(kwargs)
        return orig_create_action(action_type, **kwargs)
    w.env.unwrapped.create_action = _spy
    w.click(-5, 50)
    assert sent["coords"][0] == 0
    w.close()


def test_click_within_bounds_is_unchanged(fake_env_cls):
    w = MiniWobWorld("click-button")
    w.reset()
    sent = {}
    orig_create_action = w.env.unwrapped.create_action
    def _spy(action_type, **kwargs):
        sent.update(kwargs)
        return orig_create_action(action_type, **kwargs)
    w.env.unwrapped.create_action = _spy
    w.click(40, 60)
    assert list(sent["coords"]) == [40, 60]
    w.close()


def test_miniwob_session_click_reports_clamp_in_text(fake_env_cls, tmp_path):
    args = _args("miniwob_click_button", str(tmp_path / "out"))
    sess = MiniWobSession(args)
    try:
        result = sess.call("click", {"x": 50, "y": 999})
        text = " ".join(c["text"] for c in result if c.get("type") == "text")
        assert "clamped" in text
    finally:
        sess.close()


# ---------------------------------------------------------------------------
# 2. observe()'s payload shape: utterance, screen size, blobs — no DOM, no fields, no reward.
# ---------------------------------------------------------------------------

def test_miniwob_world_never_stores_dom_or_fields(fake_env_cls):
    w = MiniWobWorld("click-button")
    w.reset()
    assert not hasattr(w, "dom_elements")
    assert not hasattr(w, "fields")
    assert not hasattr(w, "_dom_elements")
    assert not hasattr(w, "_fields")
    w.close()


def test_observe_content_includes_utterance_and_screen_size(fake_env_cls, tmp_path):
    args = _args("miniwob_click_button", str(tmp_path / "out"))
    sess = MiniWobSession(args)
    try:
        result = sess._observe_content()
        text = " ".join(c["text"] for c in result if c.get("type") == "text")
        assert "Ok" in text          # the utterance text made it through
        assert "160x210" in text     # screen size
    finally:
        sess.close()


def test_observe_content_has_no_dom_or_field_keywords(fake_env_cls, tmp_path):
    args = _args("miniwob_click_button", str(tmp_path / "out"))
    sess = MiniWobSession(args)
    try:
        result = sess._observe_content()
        text = " ".join(c["text"] for c in result if c.get("type") == "text").lower()
        for banned in ("dom", "ref=", "tag=", "field"):
            assert banned not in text, f"observe leaked a DOM/field-shaped token: {banned!r}"
    finally:
        sess.close()


# ---------------------------------------------------------------------------
# 3. reward/dom never appear in ANY MiniWobSession.call() tool-result path (mocked serve loop).
# ---------------------------------------------------------------------------

_FORBIDDEN_SUBSTRINGS = ("reward", "dom_element", "\"fields\"", "'fields'")


def test_no_tool_result_ever_contains_reward_or_dom(fake_env_cls, tmp_path):
    args = _args("miniwob_click_button", str(tmp_path / "out"))
    sess = MiniWobSession(args)
    try:
        calls = [
            ("observe", {}),
            ("click", {"x": 25, "y": 105}),
            ("observe", {}),
            ("type_text", {"text": "hello"}),
            ("press_key", {"key": "Enter"}),
            ("reset_episode", {}),
            ("whats_changed", {"x0": 0, "y0": 0, "x1": 10, "y1": 10}),
        ]
        for name, cargs in calls:
            result = sess.call(name, cargs)
            blob = json.dumps(result).lower()
            for banned in _FORBIDDEN_SUBSTRINGS:
                assert banned not in blob, f"tool {name!r} leaked forbidden token {banned!r}: {blob}"
    finally:
        sess.close()


def test_oracle_jsonl_is_where_reward_and_done_actually_go(fake_env_cls, tmp_path):
    """Reward isn't just absent from tool results — it IS logged, but only to oracle.jsonl on disk."""
    out = str(tmp_path / "out")
    args = _args("miniwob_click_button", out)
    sess = MiniWobSession(args)
    try:
        sess.call("click", {"x": 25, "y": 105})
        with open(os.path.join(out, "oracle.jsonl"), encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
        assert any("reward" in r for r in rows)
        assert any(r.get("task") == "click-button" for r in rows)
    finally:
        sess.close()


# ---------------------------------------------------------------------------
# 4. tools/list wiring.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("game", sorted(_MINIWOB_WORLDS))
def test_miniwob_worlds_advertise_expected_tools(game):
    names = {t["name"] for t in _static_tools(game)}
    assert names == {"observe", "read_region", "whats_changed", "click", "type_text",
                     "press_key", "reset_episode"}


def test_miniwob_worlds_do_not_advertise_gb_nav_tools():
    names = {t["name"] for t in _static_tools("miniwob_click_button")}
    assert "explore" not in names and "goto" not in names and "remember" not in names
    assert "press_button" not in names and "press_sequence" not in names


def test_other_worlds_unaffected_by_miniwob_addition():
    names = {t["name"] for t in _static_tools("cave_noire")}
    assert "click" not in names and "reset_episode" not in names


def test_miniwob_worlds_registered_in_games():
    for game in _MINIWOB_WORLDS:
        assert game in GAMES
        assert "task" in GAMES[game]
        assert GAMES[game]["watch"] == {}


def test_click_tool_schema_requires_x_and_y():
    for spec in _static_tools("miniwob_click_button"):
        if spec["name"] == "click":
            assert set(spec["inputSchema"]["required"]) == {"x", "y"}
