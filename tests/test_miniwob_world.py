"""Unit tests for the MiniWoB++ computer-use world (core/miniwob_world.py + world_mcp.py's
MiniWobSession/_miniwob_static_tools). CI-safe: no browser, no miniwob/selenium install — a FakeMiniWobEnv
stands in for the real gymnasium env, monkeypatched into MiniWobWorld so these tests run anywhere.

Covers (per the plan + the PR #64 fix round):
  1. Click bounds: MiniWobWorld's defense-in-depth clamp AND MiniWobSession's loud out-of-viewport
     rejection (the probe's 177px gotcha; silent clamping corrupts brain feedback).
  2. observe()'s payload shape (utterance + screen size + episode status; no DOM, no reward, no fields).
  3. reward/dom/done never appear in ANY MiniWobSession.call() action tool-result path (grep-style).
  4. tools/list wiring: miniwob_* worlds advertise exactly the expected tool set; other worlds unaffected.
  5. The wall-clock episode-timer override: core.EPISODE_MAX_TIME is injected via JS on EVERY reset, and
     the env is constructed with the raw (undiscounted) reward_processor.
  6. Selenium exception sanitization + --record failing loud for this family.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pytest

import world_mcp
from core.miniwob_world import EPISODE_MAX_TIME_MS, MiniWobWorld, VIEWPORT_HEIGHT, VIEWPORT_WIDTH
from world_mcp import GAMES, MiniWobSession, _MINIWOB_WORLDS, _static_tools


# ---------------------------------------------------------------------------
# Fake miniwob env: a gymnasium-shaped Env stand-in, no browser/selenium/miniwob install needed.
# ---------------------------------------------------------------------------

class _FakeDriver:
    """Records execute_script calls so tests can assert the EPISODE_MAX_TIME JS injection happened."""
    def __init__(self):
        self.scripts: list[str] = []

    def execute_script(self, script, *args):
        self.scripts.append(script)


class _FakeInstance:
    def __init__(self):
        self.driver = _FakeDriver()


class _FakeUnwrapped:
    def __init__(self):
        self.instance = _FakeInstance()

    def create_action(self, action_type, **kwargs):
        return {"type": action_type, **kwargs}


class _FakeMiniwobEnv:
    """Minimal stand-in for miniwob.envs.miniwob_envs.ClickButtonEnv etc. Deliberately includes
    dom_elements/fields in its obs dict (like the real env) so MiniWobWorld's withholding is
    exercised, not just assumed. Accepts reward_processor like the real MiniWoBEnvironment."""

    def __init__(self, render_mode=None, reward_processor=None):
        self.render_mode = render_mode
        self.reward_processor = reward_processor
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


def test_miniwob_session_rejects_out_of_viewport_click(fake_env_cls, tmp_path):
    """PR #64 finding 5: a click outside the clickable band must be REJECTED loudly, not silently
    clamped to a different pixel — and the env must NOT be stepped."""
    args = _args("miniwob_click_button", str(tmp_path / "out"))
    sess = MiniWobSession(args)
    try:
        result = sess.call("click", {"x": 50, "y": 190})   # y in the unreachable 177-209 band
        text = " ".join(c["text"] for c in result if c.get("type") == "text")
        assert "error" in text and "outside" in text
        assert "No click was performed" in text
        assert sess.mw.env._step_n == 0, "out-of-viewport click must not step the env"
    finally:
        sess.close()


def test_miniwob_session_rejects_negative_click_coords(fake_env_cls, tmp_path):
    args = _args("miniwob_click_button", str(tmp_path / "out"))
    sess = MiniWobSession(args)
    try:
        result = sess.call("click", {"x": -1, "y": 50})
        text = " ".join(c["text"] for c in result if c.get("type") == "text")
        assert "error" in text and sess.mw.env._step_n == 0
    finally:
        sess.close()


def test_miniwob_session_in_viewport_click_steps_env(fake_env_cls, tmp_path):
    args = _args("miniwob_click_button", str(tmp_path / "out"))
    sess = MiniWobSession(args)
    try:
        result = sess.call("click", {"x": 25, "y": 105})
        text = " ".join(c["text"] for c in result if c.get("type") == "text")
        assert "[click (25,105) -> ok]" in text
        assert sess.mw.env._step_n == 1
    finally:
        sess.close()


# ---------------------------------------------------------------------------
# 2. observe()'s payload shape: utterance, screen size, episode status — no DOM, no fields, no reward.
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


def test_observe_reports_episode_status(fake_env_cls, tmp_path):
    """observe carries the episode status line (in progress -> over after a terminating action ->
    back to in progress after reset_episode). This is the ONLY place episode-over surfaces."""
    args = _args("miniwob_click_button", str(tmp_path / "out"))
    sess = MiniWobSession(args)
    try:
        text = sess.call("observe", {})[0]["text"]
        assert "Episode in progress" in text
        result = sess.call("click", {"x": 25, "y": 105})   # fake env terminates on CLICK_COORDS
        text = " ".join(c["text"] for c in result if c.get("type") == "text")
        assert "Episode over" in text and "reset_episode" in text
        result = sess.call("reset_episode", {})
        text = " ".join(c["text"] for c in result if c.get("type") == "text")
        assert "Episode in progress" in text
    finally:
        sess.close()


# ---------------------------------------------------------------------------
# 3. reward/dom/done never appear in ANY MiniWobSession.call() tool-result path (mocked serve loop).
#    "done" (PR #64 finding 3): the env's terminated flag is oracle-derived — the brain may see the
#    plain-English episode-status line in observe, but never the raw done flag in an action result.
# ---------------------------------------------------------------------------

_FORBIDDEN_SUBSTRINGS = ("reward", "dom_element", "\"fields\"", "'fields'", "done")


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


# ---------------------------------------------------------------------------
# 5. Wall-clock episode timer (PR #64 critical finding): the ~10s JS timer must be overridden on EVERY
#    reset (each episode re-arms it) and the env constructed with the raw-reward processor, so a slow
#    (deliberating LLM) brain isn't auto-failed at -1.0 / time-decayed.
# ---------------------------------------------------------------------------

def test_reset_injects_episode_max_time_override(fake_env_cls):
    w = MiniWobWorld("click-button")
    w.reset()
    scripts = w.env.unwrapped.instance.driver.scripts
    assert any("core.EPISODE_MAX_TIME" in s and str(EPISODE_MAX_TIME_MS) in s for s in scripts), \
        f"reset() must inject the EPISODE_MAX_TIME JS override; scripts ran: {scripts}"
    w.close()


def test_every_reset_reapplies_the_timer_override(fake_env_cls):
    """The override targets the live page's global, which each episode re-arms — one injection at
    construction is not enough; every reset must re-apply it."""
    w = MiniWobWorld("click-button")
    w.reset()
    w.reset()
    scripts = [s for s in w.env.unwrapped.instance.driver.scripts if "core.EPISODE_MAX_TIME" in s]
    assert len(scripts) == 2
    w.close()


def test_session_reset_episode_reapplies_the_timer_override(fake_env_cls, tmp_path):
    args = _args("miniwob_click_button", str(tmp_path / "out"))
    sess = MiniWobSession(args)
    try:
        before = len([s for s in sess.mw.env.unwrapped.instance.driver.scripts
                      if "core.EPISODE_MAX_TIME" in s])
        sess.call("reset_episode", {})
        after = len([s for s in sess.mw.env.unwrapped.instance.driver.scripts
                     if "core.EPISODE_MAX_TIME" in s])
        assert after == before + 1
    finally:
        sess.close()


def test_env_constructed_with_raw_reward_processor(fake_env_cls):
    """reward_processor must be the undiscounted raw_reward mapper — without it, even an untimed
    episode's reward is scaled by the JS timer's linear decay."""
    w = MiniWobWorld("click-button")
    rp = w.env.reward_processor
    assert rp is not None, "env must be constructed with reward_processor="
    assert rp({"raw_reward": 0.7}) == pytest.approx(0.7)
    assert rp({"raw_reward": -1}) == pytest.approx(-1.0)
    w.close()


# ---------------------------------------------------------------------------
# 6. Selenium exception sanitization + --record fails loud (PR #64 findings 4 and 7).
# ---------------------------------------------------------------------------

def test_action_exception_is_sanitized_to_class_plus_first_line(fake_env_cls, tmp_path):
    """A Selenium exception's str() can embed multi-line page/element/session dumps — only the class
    name + first line may reach the brain."""
    args = _args("miniwob_click_button", str(tmp_path / "out"))
    sess = MiniWobSession(args)
    try:
        secret = "SECRET-DOM-DUMP: <button ref=1>Ok</button>"
        def _boom(action):
            raise RuntimeError(f"element not interactable\n{secret}\nSession info: chrome=149")
        sess.mw.env.step = _boom
        result = sess.call("click", {"x": 25, "y": 105})
        text = " ".join(c["text"] for c in result if c.get("type") == "text")
        assert "RuntimeError" in text and "element not interactable" in text
        assert secret not in text and "Session info" not in text
    finally:
        sess.close()


def test_record_fails_loud_for_miniwob_family(fake_env_cls, tmp_path):
    args = _args("miniwob_click_button", str(tmp_path / "out"))
    args.record = True
    with pytest.raises(SystemExit, match="--record is not supported"):
        MiniWobSession(args)
