"""Unit tests for the ViZDoom GATE-3D world (world_mcp.DoomDtcSession + core/vizdoom_world.py +
_vizdoom_static_tools). CI-safe: no real vizdoom install — a FakeDoomGame stands in for
vizdoom.DoomGame (same fake shape as tests/test_vizdoom_world.py's, extended with a scripted
turn/monster-walk sequence so P1/P2 have real signal to react to).

Covers:
  1. tools/list wiring: doom_dtc_gate advertises exactly observe/remember/turn_left/turn_right/
     attack/new_episode; other worlds unaffected.
  2. observe()'s payload shape: ego (P1) + movers (P2) + episode status — NO screenshot, NO game
     variables (HEALTH/AMMO2/KILLCOUNT) in ANY tool result.
  3. P1 is computed and logged on EVERY action sub-step (including `repeat`), not lazily inside
     observe() — the PR #73 review finding this class exists to satisfy.
  4. Oracle rows land in oracle.jsonl (episode/step/tic/health/ammo2/killcount) — never on the wire.
  5. One-attempt-per-seed: an early new_episode abandons the current seed (oracle row logged) and
     advances; running out of seeds is reported, not a crash.
  6. Episode-boundary guard: observe() after finish reports status, not a stale/None-shaped crash.
  7. Fixed action grain: turn_left/turn_right/attack tools take no `tics` param; `repeat` is 1..10.
"""
from __future__ import annotations

import json
import os
import sys
import types

import numpy as np
import pytest

import world_mcp
from world_mcp import GAMES, DoomDtcSession, _VIZDOOM_WORLDS, _load_doom_seeds, _static_tools


# ---------------------------------------------------------------------------
# Fake vizdoom module (mirrors tests/test_vizdoom_world.py's fake, extended with scripted content
# so a turn changes the frame in a way P1 can read, and an IDLE-equivalent state has a "monster" blob
# that moves when the game is stepped with ATTACK — simulating a walking monster's own animation).
# ---------------------------------------------------------------------------

class _FakeButton:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"Button.{self.name}"


class _FakeGameVariable:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"GameVariable.{self.name}"


class _FakeState:
    def __init__(self, tic, screen, game_variables):
        self.tic = tic
        self.screen_buffer = screen
        self.game_variables = game_variables


_PANORAMA_W = 320 * 8   # a wide wrapping "360-degree" texture -- a real Doom rotation never runs out
_PANORAMA = np.random.RandomState(42).randint(60, 90, (240, _PANORAMA_W)).astype(np.uint8)


def _render(shift: int, monster_x: int) -> np.ndarray:
    """A synthetic 240x320 RGB frame: a 320-wide crop of a wide WRAPPING textured panorama (indexed
    modulo _PANORAMA_W, so `shift` can accumulate arbitrarily across many turns -- like a real
    rotating camera -- while each CONSECUTIVE pair's delta stays a small, MAX_SHIFT-bounded step) plus
    a small bright square "monster" at column monster_x, rows 180-192 -- deliberately BELOW P1's yaw
    band (rows 84-156, core.yaw_flow.BAND) so a static-position monster blob can't anchor a false
    dx=0 correlation peak in P1's own signal (P2's abs-diff still sees it fine; it uses the full
    frame, not the band)."""
    cols = (np.arange(320) + shift) % _PANORAMA_W
    band = _PANORAMA[:, cols]
    frame = np.stack([band, band, band], axis=-1).copy()
    frame[180:192, monster_x:monster_x + 10] = 240   # bright monster blob, well above PIX_T
    return frame


class _FakeDoomGame:
    _LIVE_BUTTON_ORDER = ("TURN_LEFT", "TURN_RIGHT", "ATTACK")
    _LIVE_VAR_ORDER = ("HEALTH", "AMMO2", "KILLCOUNT")

    def __init__(self):
        self.scenario_path = None
        self._buttons = []
        self._variables = []
        self._tic = 0
        self._finished = True
        self._seed = None
        self._killcount = 0
        self._shift = 0          # cumulative background shift (ego yaw signal)
        self._monster_x = 150    # monster column, walks toward the player each IDLE-ish (ATTACK) step
        self.actions_taken = []
        self.max_tics = 100_000

    def load_config(self, path):
        pass

    def set_doom_scenario_path(self, path):
        self.scenario_path = path

    def set_screen_format(self, fmt):
        pass

    def set_screen_resolution(self, res):
        pass

    def set_window_visible(self, v):
        pass

    def set_available_buttons(self, buttons):
        self._buttons = [_FakeButton(n) for n in self._LIVE_BUTTON_ORDER]

    def get_available_buttons(self):
        return self._buttons

    def set_available_game_variables(self, variables):
        self._variables = [_FakeGameVariable(n) for n in self._LIVE_VAR_ORDER]

    def get_available_game_variables(self):
        return self._variables

    def init(self):
        pass

    def set_seed(self, seed):
        self._seed = seed

    def new_episode(self):
        self._tic = 0
        self._finished = False
        self._killcount = 0
        self._shift = 0
        self._monster_x = 150

    def is_episode_finished(self):
        return self._finished

    def get_state(self):
        if self._finished:
            return None
        screen = _render(self._shift, self._monster_x)
        gv = [100.0, 26.0, float(self._killcount)]
        return _FakeState(self._tic, screen, gv)

    def make_action(self, action_vec, tics):
        assert tics == 4
        self.actions_taken.append(list(action_vec))
        self._tic += tics
        tl_idx = self._LIVE_BUTTON_ORDER.index("TURN_LEFT")
        tr_idx = self._LIVE_BUTTON_ORDER.index("TURN_RIGHT")
        atk_idx = self._LIVE_BUTTON_ORDER.index("ATTACK")
        if action_vec[tl_idx] == 1:
            # core.yaw_flow's documented sign convention: TURN_LEFT -> world image streams RIGHT
            # (+dx). This fake's _render(shift) samples cols = arange(320)+shift, i.e. increasing
            # `shift` scrolls the SAMPLED WINDOW right, which moves board content left on screen
            # (cur[x] ~= prev[x + shift] ~= prev[x - (-shift)], so dx = -shift by yaw_flow's cur[x] ~
            # prev[x - dx] convention) -- so TURN_LEFT must DECREASE shift to read back dx > 0.
            self._shift -= 40    # a real turn -> real background shift (P1 signal)
        elif action_vec[tr_idx] == 1:
            self._shift += 40
        elif action_vec[atk_idx] == 1:
            self._killcount += 1
            self._monster_x = max(0, self._monster_x - 15)   # monster walks closer -> P2 signal
        if self._tic >= self.max_tics:
            self._finished = True

    def close(self):
        pass


@pytest.fixture
def fake_vizdoom(monkeypatch):
    mod = types.ModuleType("vizdoom")
    mod.DoomGame = _FakeDoomGame
    mod.Button = types.SimpleNamespace(TURN_LEFT=_FakeButton("TURN_LEFT"), TURN_RIGHT=_FakeButton("TURN_RIGHT"),
                                       ATTACK=_FakeButton("ATTACK"))
    mod.GameVariable = types.SimpleNamespace(HEALTH=_FakeGameVariable("HEALTH"), AMMO2=_FakeGameVariable("AMMO2"),
                                             KILLCOUNT=_FakeGameVariable("KILLCOUNT"))
    mod.ScreenFormat = types.SimpleNamespace(RGB24="RGB24")
    mod.ScreenResolution = types.SimpleNamespace(RES_320X240="RES_320X240")
    mod.scenarios_path = "/fake/vizdoom/scenarios"
    monkeypatch.setitem(sys.modules, "vizdoom", mod)
    return mod


def _args(out: str, seeds=(1, 2, 3)) -> "world_mcp.argparse.Namespace":
    import argparse
    return argparse.Namespace(game="doom_dtc_gate", rom=None, init_state=None, out=out, record=False,
                              with_screenshot=False, keep_frames=False, seeds_file=None, seed=list(seeds))


# ---------------------------------------------------------------------------
# 1. tools/list wiring.
# ---------------------------------------------------------------------------

def test_doom_dtc_gate_advertises_expected_tools():
    names = {t["name"] for t in _static_tools("doom_dtc_gate")}
    assert names == {"observe", "remember", "turn_left", "turn_right", "attack", "new_episode"}


def test_doom_action_tools_have_no_tics_param_only_repeat():
    for t in _static_tools("doom_dtc_gate"):
        if t["name"] in ("turn_left", "turn_right", "attack"):
            props = t["inputSchema"]["properties"]
            assert "tics" not in props
            assert props["repeat"]["minimum"] == 1
            assert props["repeat"]["maximum"] == 10


def test_other_worlds_unaffected_by_doom_addition():
    names = {t["name"] for t in _static_tools("cave_noire")}
    assert "turn_left" not in names and "new_episode" not in names


def test_doom_dtc_gate_registered_in_games():
    assert "doom_dtc_gate" in GAMES
    assert GAMES["doom_dtc_gate"]["watch"] == {}
    assert "doom_dtc_gate" in _VIZDOOM_WORLDS


# ---------------------------------------------------------------------------
# 2. observe() payload shape: ego + movers + episode status, no screenshot/game variables anywhere.
# ---------------------------------------------------------------------------

def test_observe_reports_ego_and_movers_and_episode_status(fake_vizdoom, tmp_path):
    sess = DoomDtcSession(_args(str(tmp_path / "out")))
    try:
        text = sess.call("observe", {})[0]["text"]
        assert "ego:" in text and "movers:" in text and "episode:" in text
    finally:
        sess.close()


_FORBIDDEN_SUBSTRINGS = ("health", "ammo2", "killcount", "screen_buffer")


def test_no_tool_result_ever_contains_game_variables_or_screenshot(fake_vizdoom, tmp_path):
    sess = DoomDtcSession(_args(str(tmp_path / "out")))
    try:
        calls = [
            ("observe", {}),
            ("turn_left", {}),
            ("observe", {}),
            ("attack", {"repeat": 2}),
            ("remember", {"lesson": "turn until azimuth is 0"}),
        ]
        for name, cargs in calls:
            result = sess.call(name, cargs)
            blob = json.dumps(result).lower()
            for banned in _FORBIDDEN_SUBSTRINGS:
                assert banned not in blob, f"tool {name!r} leaked forbidden token {banned!r}: {blob}"
            # no image content block anywhere (no-screenshot law for this world)
            assert all(c.get("type") != "image" for c in result)
    finally:
        sess.close()


def test_oracle_jsonl_is_where_game_variables_actually_go(fake_vizdoom, tmp_path):
    out = str(tmp_path / "out")
    sess = DoomDtcSession(_args(out))
    try:
        sess.call("attack", {})
        with open(os.path.join(out, "oracle.jsonl"), encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
        assert any("killcount" in r for r in rows)
        assert any(r.get("killcount", 0) >= 1 for r in rows)
    finally:
        sess.close()


# ---------------------------------------------------------------------------
# 3. P1 computed + logged on EVERY action sub-step (not lazily inside observe()).
# ---------------------------------------------------------------------------

def test_p1_logged_on_every_action_substep_not_only_on_observe(fake_vizdoom, tmp_path):
    out = str(tmp_path / "out")
    sess = DoomDtcSession(_args(out))
    try:
        # 3 turn_left calls, never calling observe in between -- grounding.jsonl must still have 3 rows.
        sess.call("turn_left", {})
        sess.call("turn_left", {})
        sess.call("turn_left", {})
        with open(os.path.join(out, "grounding.jsonl"), encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
        turn_rows = [r for r in rows if r["commanded"] == "left"]
        assert len(turn_rows) == 3
        # a real turn produced a real background shift -- P1 must agree with the commanded direction.
        assert all(r["direction"] == "left" for r in turn_rows)
    finally:
        sess.close()


def test_repeat_logs_one_grounding_row_per_substep(fake_vizdoom, tmp_path):
    out = str(tmp_path / "out")
    sess = DoomDtcSession(_args(out))
    try:
        sess.call("turn_right", {"repeat": 5})
        with open(os.path.join(out, "grounding.jsonl"), encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
        assert len(rows) == 5
        assert all(r["direction"] == "right" for r in rows)
    finally:
        sess.close()


def test_attack_logs_grounding_row_with_no_commanded_direction(fake_vizdoom, tmp_path):
    out = str(tmp_path / "out")
    sess = DoomDtcSession(_args(out))
    try:
        sess.call("attack", {})
        with open(os.path.join(out, "grounding.jsonl"), encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
        assert rows[-1]["commanded"] is None
    finally:
        sess.close()


def test_movers_reported_after_attack_when_p1_reports_none(fake_vizdoom, tmp_path):
    """ATTACK doesn't shift the background (ego-stationary by the design's own definition), so P1
    should read direction=="none" and the gate should be OPEN — P2 gets a chance to report the
    monster's own motion (it walks closer on each attack in this fake)."""
    out = str(tmp_path / "out")
    sess = DoomDtcSession(_args(out))
    try:
        sess.call("attack", {})
        text = sess.call("attack", {})[-1]["text"]
        assert "movers:" in text
        # not a hard assertion on contents (blob detection is threshold-sensitive) — but it must not be
        # the "not ego-stationary" gate-closed message, since P1 should read "none" on an ATTACK step.
        assert "not ego-stationary" not in text
    finally:
        sess.close()


def test_observe_movers_diffs_the_actual_action_pair_not_a_self_diff(fake_vizdoom, tmp_path):
    """Regression: observe()'s P2 call must diff the (before, after) pair the LAST action sub-step
    actually ran on. A bug that rolls both sides of the diff forward to the post-action frame (i.e.
    diffing the current frame against itself) would always report [] here even though the monster
    visibly moved 15px between the two attack calls -- this must NOT be a self-diff false negative."""
    out = str(tmp_path / "out")
    sess = DoomDtcSession(_args(out))
    try:
        sess.call("attack", {})   # monster steps from x=150 -> x=135
        text = sess.call("observe", {})[0]["text"]
        assert "confidently nothing moving" not in text, (
            f"expected a real mover from the monster's 15px walk, got a self-diffed empty read: {text}")
    finally:
        sess.close()


def test_movers_gate_closed_immediately_after_a_turn(fake_vizdoom, tmp_path):
    out = str(tmp_path / "out")
    sess = DoomDtcSession(_args(out))
    try:
        text = sess.call("turn_left", {})[-1]["text"]
        assert "not ego-stationary" in text
    finally:
        sess.close()


# ---------------------------------------------------------------------------
# 4. episode-boundary guard + one-attempt-per-seed.
# ---------------------------------------------------------------------------

def test_new_episode_before_finish_abandons_and_advances(fake_vizdoom, tmp_path):
    out = str(tmp_path / "out")
    sess = DoomDtcSession(_args(out, seeds=(11, 22)))
    try:
        assert sess._seed_idx == 0
        sess.call("turn_left", {})   # episode not finished yet
        sess.call("new_episode", {})
        assert sess._seed_idx == 1
        with open(os.path.join(out, "oracle.jsonl"), encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
        abandoned = [r for r in rows if r.get("abandoned")]
        assert len(abandoned) == 1
        assert abandoned[0]["episode"] == 0
    finally:
        sess.close()


def test_new_episode_reports_exhaustion_when_out_of_seeds(fake_vizdoom, tmp_path):
    out = str(tmp_path / "out")
    sess = DoomDtcSession(_args(out, seeds=(1,)))
    try:
        result = sess.call("new_episode", {})
        text = result[0]["text"]
        assert "no more" in text.lower()
    finally:
        sess.close()


def test_observe_after_episode_finish_reports_status_not_a_crash(fake_vizdoom, tmp_path):
    out = str(tmp_path / "out")
    sess = DoomDtcSession(_args(out, seeds=(1, 2)))
    try:
        sess.world.game.max_tics = 4   # end the episode after one action
        sess.call("turn_left", {})
        assert sess.world.episode_finished
        text = sess.call("observe", {})[0]["text"]
        assert "finished" in text.lower()
    finally:
        sess.close()


def test_requires_at_least_one_pinned_seed(fake_vizdoom, tmp_path):
    import argparse
    args = argparse.Namespace(game="doom_dtc_gate", rom=None, init_state=None, out=str(tmp_path / "out"),
                              record=False, with_screenshot=False, keep_frames=False, seeds_file=None,
                              seed=None)
    with pytest.raises(SystemExit):
        DoomDtcSession(args)


# ---------------------------------------------------------------------------
# --record rejection at launch (mirrors the miniwob guard).
# ---------------------------------------------------------------------------

def test_record_fails_loud_at_launch_for_doom_dtc_gate(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["world_mcp.py", "--game", "doom_dtc_gate", "--record"])
    with pytest.raises(SystemExit, match="--record is not supported"):
        world_mcp.main()


def test_missing_seed_fails_loud_at_launch_not_mid_protocol(monkeypatch):
    """A missing pinned seed must be rejected in main()'s argument validation (SystemExit BEFORE the
    server speaks) — not inside the lazily-built DoomDtcSession, where main()'s tools/call handler
    only catches `Exception` (SystemExit is a BaseException and would escape, killing the process
    mid-protocol instead of being reported as a normal tool error). No fake vizdoom needed: main()
    must exit before ever constructing the session."""
    monkeypatch.setattr(sys, "argv", ["world_mcp.py", "--game", "doom_dtc_gate"])
    with pytest.raises(SystemExit, match="at least one pinned seed"):
        world_mcp.main()


# ---------------------------------------------------------------------------
# _load_doom_seeds: --seeds-file accepts EITHER one-int-per-line OR a JSON array (GATE-3D PR-D adds
# the JSON form so DoomDtcSession's --seeds-file can point straight at the committed
# eval/fixtures/gate3d_seeds.json, a JSON array, without a separate conversion step).
# ---------------------------------------------------------------------------

def _ns(**over):
    import argparse
    base = dict(seeds_file=None, seed=None)
    base.update(over)
    return argparse.Namespace(**base)


def test_load_doom_seeds_from_json_array_file(tmp_path):
    p = tmp_path / "seeds.json"
    p.write_text("[1000, 1001, 1002]", encoding="utf-8")
    assert _load_doom_seeds(_ns(seeds_file=str(p))) == [1000, 1001, 1002]


def test_load_doom_seeds_from_one_int_per_line_file(tmp_path):
    p = tmp_path / "seeds.txt"
    p.write_text("1000\n1001\n1002\n", encoding="utf-8")
    assert _load_doom_seeds(_ns(seeds_file=str(p))) == [1000, 1001, 1002]


def test_load_doom_seeds_json_array_takes_priority_over_seed_flag(tmp_path):
    p = tmp_path / "seeds.json"
    p.write_text("[5, 6, 7]", encoding="utf-8")
    assert _load_doom_seeds(_ns(seeds_file=str(p), seed=[1, 2, 3])) == [5, 6, 7]


def test_load_doom_seeds_falls_back_to_seed_flag_when_no_seeds_file():
    assert _load_doom_seeds(_ns(seed=[3, 1, 4])) == [3, 1, 4]


def test_load_doom_seeds_empty_when_neither_given():
    assert _load_doom_seeds(_ns()) == []
