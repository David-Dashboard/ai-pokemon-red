"""core.vizdoom_world tests (VizdoomWorld adapter, GATE-3D PR-C). CI-safe: no real vizdoom install --
a FakeDoomGame stands in for vizdoom.DoomGame, monkeypatched via sys.modules the same way
tests/test_miniwob_world.py fakes miniwob (core.vizdoom_world's `import vizdoom` is lazy, inside
__init__, so this works without the real package present).

Covers:
  - lazy import (module imports fine with no vizdoom installed)
  - reset(seed)/step(button, repeat) mechanics, TICS_PER_STEP=4 FIXED (no tics param anywhere)
  - name-keyed action vector construction (not positional) -- probe's order-sensitivity gotcha
  - get_state()-None episode-boundary guard: screen is None + episode_finished True after end
  - game_variables() returns the oracle dict, guarded the same way, never mixed into screen/step results
  - repeat stops early if the episode ends mid-repeat
"""
from __future__ import annotations

import sys
import types

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Fake vizdoom module: DoomGame + Button/GameVariable/ScreenFormat/ScreenResolution enums.
# ---------------------------------------------------------------------------

class _FakeButton:
    _names = ("TURN_LEFT", "TURN_RIGHT", "ATTACK", "MOVE_FORWARD")

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"Button.{self.name}"


class _FakeGameVariable:
    _names = ("HEALTH", "AMMO2", "KILLCOUNT")

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"GameVariable.{self.name}"


class _FakeState:
    def __init__(self, tic, screen, game_variables):
        self.tic = tic
        self.screen_buffer = screen
        self.game_variables = game_variables


class _FakeDoomGame:
    """A scripted DoomGame: episode ends after `episode_tic_limit` tics OR when `.kill()` is called by
    a test to simulate death. Buttons/variables are exposed in a DELIBERATELY SHUFFLED order relative
    to core.vizdoom_world.BUTTON_NAMES/GAME_VARIABLE_NAMES, to exercise the name-keyed lookup (a
    positional-index bug would silently fire the wrong button)."""

    _LIVE_BUTTON_ORDER = ("ATTACK", "TURN_LEFT", "TURN_RIGHT")   # shuffled vs BUTTON_NAMES
    _LIVE_VAR_ORDER = ("KILLCOUNT", "HEALTH", "AMMO2")           # shuffled vs GAME_VARIABLE_NAMES

    def __init__(self):
        self.loaded_cfg = None
        self.scenario_path = None
        self.screen_format = None
        self.screen_resolution = None
        self.window_visible = None
        self._buttons = []
        self._variables = []
        self._tic = 0
        self._finished = True   # not started until new_episode()
        self._seed = None
        self._killcount = 0
        self.actions_taken = []   # log of (vec, tics) for assertions
        self.max_tics = 40

    def load_config(self, path):
        self.loaded_cfg = path

    def set_doom_scenario_path(self, path):
        self.scenario_path = path

    def set_screen_format(self, fmt):
        self.screen_format = fmt

    def set_screen_resolution(self, res):
        self.screen_resolution = res

    def set_window_visible(self, v):
        self.window_visible = v

    def set_available_buttons(self, buttons):
        # Bind to the fake's own shuffled canonical order, ignoring the caller's requested order --
        # mirrors a real engine: what you ASK for vs what get_available_buttons() reports may differ
        # in order, which is exactly why the adapter must look up by name.
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

    def is_episode_finished(self):
        return self._finished

    def get_state(self):
        if self._finished:
            return None
        screen = np.full((240, 320, 3), fill_value=min(255, self._tic), dtype=np.uint8)
        gv = [0.0] * len(self._LIVE_VAR_ORDER)
        gv[self._LIVE_VAR_ORDER.index("HEALTH")] = 100.0
        gv[self._LIVE_VAR_ORDER.index("AMMO2")] = 26.0
        gv[self._LIVE_VAR_ORDER.index("KILLCOUNT")] = float(self._killcount)
        return _FakeState(self._tic, screen, gv)

    def make_action(self, action_vec, tics):
        assert tics == 4, "TICS_PER_STEP must always be 4 -- no caller may vary it"
        self.actions_taken.append((list(action_vec), tics))
        self._tic += tics
        # ATTACK (at the fake's live index) scores a kill on the 2nd attack call, to exercise
        # game_variables() changing over the episode.
        atk_idx = self._LIVE_BUTTON_ORDER.index("ATTACK")
        if action_vec[atk_idx] == 1:
            self._killcount += 1
        if self._tic >= self.max_tics:
            self._finished = True

    def close(self):
        pass


@pytest.fixture
def fake_vizdoom(monkeypatch):
    mod = types.ModuleType("vizdoom")
    mod.DoomGame = _FakeDoomGame
    mod.Button = types.SimpleNamespace(**{n: _FakeButton(n) for n in _FakeButton._names})
    mod.GameVariable = types.SimpleNamespace(**{n: _FakeGameVariable(n) for n in _FakeGameVariable._names})
    mod.ScreenFormat = types.SimpleNamespace(RGB24="RGB24")
    mod.ScreenResolution = types.SimpleNamespace(RES_320X240="RES_320X240")
    mod.scenarios_path = "/fake/vizdoom/scenarios"
    monkeypatch.setitem(sys.modules, "vizdoom", mod)
    return mod


def _make_world(fake_vizdoom, **kwargs):
    from core.vizdoom_world import VizdoomWorld
    return VizdoomWorld("scenarios/dtc_gate.cfg", **kwargs)


# ---------------------------------------------------------------------------
# Lazy import: the module must import with no vizdoom installed at all.
# ---------------------------------------------------------------------------

def test_module_imports_without_vizdoom_installed():
    import core.vizdoom_world  # noqa: F401  -- must not raise even if the real package is absent
    assert hasattr(core.vizdoom_world, "VizdoomWorld")
    assert core.vizdoom_world.TICS_PER_STEP == 4


# ---------------------------------------------------------------------------
# reset / step mechanics.
# ---------------------------------------------------------------------------

def test_reset_starts_episode_and_returns_screen(fake_vizdoom):
    w = _make_world(fake_vizdoom)
    result = w.reset(seed=777)
    assert w.game._seed == 777
    assert result.screen is not None
    assert result.screen.shape == (240, 320, 3)
    assert result.episode_finished is False
    w.close()


def test_step_always_ticks_exactly_4_tics(fake_vizdoom):
    w = _make_world(fake_vizdoom)
    w.reset(seed=1)
    w.step("TURN_LEFT")
    assert w.game.actions_taken[-1][1] == 4
    w.close()


def test_step_builds_action_vector_by_name_not_position(fake_vizdoom):
    """The fake's live button order is (ATTACK, TURN_LEFT, TURN_RIGHT) -- shuffled vs BUTTON_NAMES
    (TURN_LEFT, TURN_RIGHT, ATTACK). A positional-index bug would fire the WRONG button here."""
    w = _make_world(fake_vizdoom)
    w.reset(seed=1)
    w.step("TURN_LEFT")
    vec, _ = w.game.actions_taken[-1]
    # TURN_LEFT lives at index 1 in the fake's live order -- assert exactly that slot is hot.
    assert vec == [0, 1, 0]
    w.close()


def test_step_rejects_unknown_button(fake_vizdoom):
    w = _make_world(fake_vizdoom)
    w.reset(seed=1)
    with pytest.raises(ValueError):
        w.step("MOVE_FORWARD")
    w.close()


def test_step_repeat_executes_multiple_times(fake_vizdoom):
    w = _make_world(fake_vizdoom)
    w.reset(seed=1)
    n_before = len(w.game.actions_taken)
    w.step("TURN_LEFT", repeat=3)
    assert len(w.game.actions_taken) - n_before == 3
    w.close()


def test_step_repeat_clamped_to_1_and_10(fake_vizdoom):
    w = _make_world(fake_vizdoom)
    w.reset(seed=1)
    w.game.max_tics = 10_000   # don't let the episode end mid-test
    n_before = len(w.game.actions_taken)
    w.step("TURN_LEFT", repeat=99)
    assert len(w.game.actions_taken) - n_before == 10
    n_before = len(w.game.actions_taken)
    w.step("TURN_LEFT", repeat=0)
    assert len(w.game.actions_taken) - n_before == 1
    w.close()


def test_step_repeat_stops_early_when_episode_ends_mid_repeat(fake_vizdoom):
    w = _make_world(fake_vizdoom)
    w.reset(seed=1)
    w.game.max_tics = 8   # ends after 2 steps of tics=4
    n_before = len(w.game.actions_taken)
    result = w.step("ATTACK", repeat=10)
    assert len(w.game.actions_taken) - n_before == 2   # stopped, did not force all 10
    assert result.episode_finished is True
    assert result.screen is None
    w.close()


# ---------------------------------------------------------------------------
# episode-boundary guard: get_state() is None after finish -> screen None, never a stale frame.
# ---------------------------------------------------------------------------

def test_screen_and_step_result_are_none_after_episode_finished(fake_vizdoom):
    w = _make_world(fake_vizdoom)
    w.reset(seed=1)
    w.game.max_tics = 4
    w.step("TURN_LEFT")   # this call ends the episode
    assert w.episode_finished is True
    assert w.screen() is None
    # a further step() call after finish must not crash and must keep reporting finished/None.
    result = w.step("TURN_LEFT")
    assert result.screen is None
    assert result.episode_finished is True
    w.close()


def test_game_variables_none_after_episode_finished(fake_vizdoom):
    w = _make_world(fake_vizdoom)
    w.reset(seed=1)
    w.game.max_tics = 4
    w.step("ATTACK")
    assert w.game_variables() is None
    w.close()


# ---------------------------------------------------------------------------
# game_variables(): oracle dict, name-keyed (fake's live var order is shuffled too).
# ---------------------------------------------------------------------------

def test_game_variables_returns_name_keyed_oracle_dict(fake_vizdoom):
    w = _make_world(fake_vizdoom)
    w.reset(seed=1)
    gv = w.game_variables()
    assert set(gv) == {"HEALTH", "AMMO2", "KILLCOUNT"}
    assert gv["HEALTH"] == 100.0
    assert gv["AMMO2"] == 26.0
    assert gv["KILLCOUNT"] == 0.0
    w.close()


def test_game_variables_killcount_updates_after_attack(fake_vizdoom):
    w = _make_world(fake_vizdoom)
    w.reset(seed=1)
    w.step("ATTACK")
    gv = w.game_variables()
    assert gv["KILLCOUNT"] == 1.0
    w.close()


# ---------------------------------------------------------------------------
# scenario path resolution: set_doom_scenario_path called with the vizdoom-package-relative wad path,
# never a committed .wad in this repo.
# ---------------------------------------------------------------------------

def test_scenario_path_resolved_against_vizdoom_package_not_committed(fake_vizdoom):
    import os
    w = _make_world(fake_vizdoom)
    assert w.game.scenario_path == os.path.join("/fake/vizdoom/scenarios", "defend_the_center.wad")
    w.close()


def test_episode_index_increments_across_resets(fake_vizdoom):
    w = _make_world(fake_vizdoom)
    w.reset(seed=1)
    assert w.episode_index == 0
    w.reset(seed=2)
    assert w.episode_index == 1
    w.close()
