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
from pathlib import Path

import numpy as np
import pytest

import world_mcp
from core.miniwob_world import EPISODE_MAX_TIME_MS, MiniWobWorld, VIEWPORT_HEIGHT, VIEWPORT_WIDTH
from world_mcp import GAMES, MiniWobSession, _MINIWOB_WORLDS, _static_tools


# ---------------------------------------------------------------------------
# Fake miniwob env: a gymnasium-shaped Env stand-in, no browser/selenium/miniwob install needed.
# ---------------------------------------------------------------------------

class _FakeDriver:
    """Records execute_script calls (own list + the env's shared call-order log), so tests can assert
    both THAT the EPISODE_MAX_TIME injection happened and WHEN, relative to env.reset calls."""
    def __init__(self, calls: list):
        self.scripts: list[str] = []
        self._calls = calls

    def execute_script(self, script, *args):
        self.scripts.append(script)
        self._calls.append(("execute_script", script))


class _FakeInstance:
    def __init__(self, calls: list):
        self.driver = _FakeDriver(calls)


class _FakeActionSpaceConfig:
    """The real miniwob ActionSpaceConfig's `allowed_keys` tuple. PRESS_KEY's `key` field is a
    Discrete(len(allowed_keys)) INDEX into this, never a keysym — MiniWobSession._resolve_key reads it to
    turn the brain's key NAME into that index. Angle-bracketed, same shape as the real vocabulary."""
    allowed_keys = ("<Enter>", "<Tab>", "<ArrowDown>", "<ArrowUp>", "<Backspace>")


class _FakeUnwrapped:
    def __init__(self, calls: list):
        self.instance = _FakeInstance(calls)
        self.action_space_config = _FakeActionSpaceConfig()

    def create_action(self, action_type, **kwargs):
        return {"type": action_type, **kwargs}


class _FakeMiniwobEnv:
    """Minimal stand-in for miniwob.envs.miniwob_envs.ClickButtonEnv etc. Deliberately includes
    dom_elements/fields in its obs dict (like the real env) so MiniWobWorld's withholding is
    exercised, not just assumed. Accepts reward_processor like the real MiniWoBEnvironment.
    `calls` is a chronological log of ("reset", seed) / ("execute_script", script) events shared
    with the fake driver — the injection-ordering regression asserts against it."""

    def __init__(self, render_mode=None, reward_processor=None):
        self.render_mode = render_mode
        self.reward_processor = reward_processor
        self.calls: list = []
        self.unwrapped = _FakeUnwrapped(self.calls)
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
        self.calls.append(("reset", seed))
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


def _args(game: str, out: str, seeds=None) -> "world_mcp.argparse.Namespace":
    import argparse
    return argparse.Namespace(game=game, rom=None, init_state=None, out=out, record=False,
                              with_screenshot=False, keep_frames=False, seeds_file=None,
                              seed=None if seeds is None else list(seeds))


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
# 4. Gate 0 click-checkboxes pinned seeds: exact manifests, launch guard, one attempt each.
# ---------------------------------------------------------------------------

def test_gate0_miniwob_seed_manifests_are_exact():
    root = Path(__file__).parents[1] / "eval" / "fixtures"
    assert json.loads((root / "gate0_miniwob_dev_seeds.json").read_text()) == list(range(5))
    assert json.loads((root / "gate0_miniwob_paid_seeds.json").read_text()) == list(range(1000, 1005))


def test_click_checkboxes_requires_pinned_seeds_at_launch(monkeypatch):
    import sys
    monkeypatch.setattr(sys, "argv", ["world_mcp.py", "--game", "miniwob_click_checkboxes"])
    with pytest.raises(SystemExit, match="needs pinned seeds"):
        world_mcp.main()


def test_click_checkboxes_rejects_duplicate_seeds_at_launch(monkeypatch):
    import sys
    monkeypatch.setattr(sys, "argv", ["world_mcp.py", "--game", "miniwob_click_checkboxes",
                                     "--seed", "10", "--seed", "10"])
    with pytest.raises(SystemExit, match="distinct pinned seeds"):
        world_mcp.main()


def test_click_checkboxes_rejects_duplicate_seeds_in_session(fake_env_cls, tmp_path):
    with pytest.raises(SystemExit, match="distinct pinned seeds"):
        MiniWobSession(_args("miniwob_click_checkboxes", str(tmp_path / "out"), seeds=(10, 10)))


def test_click_checkboxes_starts_supplied_seed_and_logs_episode_seed(fake_env_cls, tmp_path):
    out = str(tmp_path / "out")
    sess = MiniWobSession(_args("miniwob_click_checkboxes", out, seeds=(10, 11)))
    try:
        assert sess.mw.current_seed == 10
        rows = [json.loads(line) for line in Path(out, "oracle.jsonl").read_text().splitlines()]
        assert rows == [{"episode": 0, "seed": 10, "step": 0, "task": "click-checkboxes",
                         "reward": 0.0, "done": False, "abandoned": False}]
    finally:
        sess.close()


def test_early_reset_abandons_once_and_advances_exactly_once(fake_env_cls, tmp_path):
    out = str(tmp_path / "out")
    sess = MiniWobSession(_args("miniwob_click_checkboxes", out, seeds=(10, 11, 12)))
    try:
        result = sess.call("reset_episode", {})
        text = " ".join(c["text"] for c in result if c.get("type") == "text")
        assert "new episode started" in text
        assert sess.mw.current_seed == 11
        reset_seeds = [value for kind, value in sess.mw.env.calls if kind == "reset"]
        assert reset_seeds == [10, 10, 11]
        rows = [json.loads(line) for line in Path(out, "oracle.jsonl").read_text().splitlines()]
        assert [(r["episode"], r["seed"], r["done"], r["abandoned"]) for r in rows] == [
            (0, 10, False, False), (0, 10, True, True), (1, 11, False, False)]
    finally:
        sess.close()


def test_completed_episode_advances_without_abandonment(fake_env_cls, tmp_path):
    out = str(tmp_path / "out")
    sess = MiniWobSession(_args("miniwob_click_checkboxes", out, seeds=(10, 11)))
    try:
        sess.call("click", {"x": 25, "y": 105})
        sess.call("reset_episode", {})
        rows = [json.loads(line) for line in Path(out, "oracle.jsonl").read_text().splitlines()]
        assert not any(r["abandoned"] for r in rows)
        assert sess.mw.current_seed == 11
    finally:
        sess.close()


def test_pinned_seed_exhaustion_is_stable_and_does_not_reroll(fake_env_cls, tmp_path):
    out = str(tmp_path / "out")
    sess = MiniWobSession(_args("miniwob_click_checkboxes", out, seeds=(10,)))
    try:
        first = sess.call("reset_episode", {})
        second = sess.call("reset_episode", {})
        observe = sess.call("observe", {})
        action = sess.call("click", {"x": 25, "y": 105})
        assert "no more pinned seeds" in first[0]["text"]
        assert "no more pinned seeds" in second[0]["text"]
        assert "manifest exhausted" in observe[0]["text"]
        assert "manifest exhausted" in action[0]["text"]
        reset_seeds = [value for kind, value in sess.mw.env.calls if kind == "reset"]
        assert reset_seeds == [10, 10]
        rows = [json.loads(line) for line in Path(out, "oracle.jsonl").read_text().splitlines()]
        assert sum(r["abandoned"] for r in rows) == 1
    finally:
        sess.close()


def test_other_miniwob_tasks_keep_sequential_default_seeds(fake_env_cls, tmp_path):
    sess = MiniWobSession(_args("miniwob_click_button", str(tmp_path / "out")))
    try:
        assert sess.mw.current_seed == 0
        sess.call("reset_episode", {})
        assert sess.mw.current_seed == 1
    finally:
        sess.close()


# ---------------------------------------------------------------------------
# 5. tools/list wiring.
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


def test_reset_tool_describes_pinned_abandon_advance_semantics():
    spec = next(t for t in _static_tools("miniwob_click_checkboxes")
                if t["name"] == "reset_episode")
    description = spec["description"]
    assert "abandons" in description and "next pinned seed" in description
    assert "never rerolls" in description


# ---------------------------------------------------------------------------
# 5. Wall-clock episode timer (PR #64 critical finding + re-validation): the ~10s JS timeout is
#    scheduled AT episode start, reading core.EPISODE_MAX_TIME at that moment — so the override must be
#    injected BEFORE the episode the caller receives. Live-proven failure mode of the naive version:
#    session's episode 1 scored -1.0, episode 2 scored +1.0 with identical 30s idles.
# ---------------------------------------------------------------------------

def test_reset_injects_episode_max_time_override(fake_env_cls):
    w = MiniWobWorld("click-button")
    w.reset()
    scripts = w.env.unwrapped.instance.driver.scripts
    assert any("core.EPISODE_MAX_TIME" in s and str(EPISODE_MAX_TIME_MS) in s for s in scripts), \
        f"reset() must inject the EPISODE_MAX_TIME JS override; scripts ran: {scripts}"
    w.close()


def test_first_reset_injects_override_before_the_episode_the_caller_receives(fake_env_cls):
    """THE injection-ordering regression (PR #64 re-validation blocker): the first brain-visible
    episode must start with the override already armed — i.e. the call order on the first reset() is
    reset (throwaway, boots the page), execute_script (inject), reset (the real episode). An injection
    only AFTER the last reset arms episode 2 but leaves episode 1 on the ~10s clock (-1.0)."""
    w = MiniWobWorld("click-button")
    w.reset()
    kinds = [kind for kind, _ in w.env.calls]
    assert kinds[:3] == ["reset", "execute_script", "reset"], \
        f"first reset() must be: throwaway reset -> inject -> real reset; got {w.env.calls}"
    # And the injection between the two resets is the EPISODE_MAX_TIME override, not something else.
    assert "core.EPISODE_MAX_TIME" in w.env.calls[1][1]
    # The episode the caller received is the one started by the LAST reset — no reset after it without
    # a preceding armed override.
    assert kinds.count("reset") == 2
    w.close()


def test_subsequent_resets_inject_after_each_reset(fake_env_cls):
    """After the first (arming) reset, each reset re-injects once as page-reload insurance: first
    reset -> 2 injections (arm + post), second reset -> 1 more."""
    w = MiniWobWorld("click-button")
    w.reset()
    w.reset()
    scripts = [s for s in w.env.unwrapped.instance.driver.scripts if "core.EPISODE_MAX_TIME" in s]
    assert len(scripts) == 3
    # the second reset happens with the override already in place (armed on the first).
    kinds = [kind for kind, _ in w.env.calls]
    assert kinds == ["reset", "execute_script", "reset", "execute_script", "reset", "execute_script"]
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


def test_record_fails_loud_at_launch_for_miniwob_family(monkeypatch):
    """PR #64 re-validation nit: the --record rejection must fire in main()'s argument validation
    (at LAUNCH, before the server speaks), not inside the lazily-built MiniWobSession where the
    SystemExit would escape mid-protocol on the first tool call. No fake env needed — main() must
    exit before any world construction (and before reading stdin)."""
    import sys
    monkeypatch.setattr(sys, "argv", ["world_mcp.py", "--game", "miniwob_click_button", "--record"])
    with pytest.raises(SystemExit, match="--record is not supported"):
        world_mcp.main()


def test_record_still_accepted_for_gb_worlds_at_arg_validation(monkeypatch):
    """The main()-level guard is miniwob-scoped: --record on a GB world must get past argument
    validation (its serve loop then just waits on stdin — give it an empty one so main() returns)."""
    import io
    import sys
    monkeypatch.setattr(sys, "argv", ["world_mcp.py", "--game", "cave_noire", "--record"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert world_mcp.main() == 0   # no SystemExit at validation; loop sees EOF and exits cleanly
