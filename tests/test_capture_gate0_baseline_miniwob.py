"""Tests for tools/capture_gate0_baseline_miniwob.py -- the Gate 0 Arm W human-baseline rig.

CI-safe: no browser, no miniwob/selenium install -- the same _FakeMiniwobEnv monkeypatch seam
tests/test_miniwob_world.py uses stands in for the real gymnasium env. "David" is simulated by a
canned `prompt` callable (dependency-injected via capture_gate0_baseline_miniwob.run()'s `prompt`
param) -- these tests exercise the RIG's plumbing (dispatch, episode advance, artifact schema,
success/incomplete detection), never real MiniWoB gameplay.
"""
from __future__ import annotations

import argparse
import json
import sys
import types

import numpy as np
import pytest

import tools.capture_gate0_baseline_miniwob as m


class _FakeDriver:
    def execute_script(self, script, *args):
        pass


class _FakeInstance:
    def __init__(self):
        self.driver = _FakeDriver()


class _FakeUnwrapped:
    def __init__(self):
        self.instance = _FakeInstance()

    def create_action(self, action_type, **kwargs):
        return {"type": action_type, **kwargs}


class _FakeEnv:
    """Terminates with reward 1.0 on the FIRST action of every episode -- lets a scripted 'one click
    per episode' answer stream exercise the rig's full 5-episode success path."""

    def __init__(self, render_mode=None, reward_processor=None):
        self.reward_processor = reward_processor
        self.unwrapped = _FakeUnwrapped()

    def _obs(self):
        return {"utterance": 'Select the indicated checkboxes and click Submit.',
                "dom_elements": (), "screenshot": np.zeros((177, 160, 3), dtype=np.uint8), "fields": ()}

    def reset(self, seed=None):
        return self._obs(), {}

    def step(self, action):
        return self._obs(), 1.0, True, False, {}

    def close(self):
        pass


@pytest.fixture
def fake_env_cls(monkeypatch):
    fake_miniwob_pkg = types.ModuleType("miniwob")
    fake_envs_pkg = types.ModuleType("miniwob.envs")
    fake_envs_mod = types.ModuleType("miniwob.envs.miniwob_envs")
    fake_envs_mod.ClickCheckboxesEnv = _FakeEnv
    fake_envs_pkg.miniwob_envs = fake_envs_mod
    monkeypatch.setitem(sys.modules, "miniwob", fake_miniwob_pkg)
    monkeypatch.setitem(sys.modules, "miniwob.envs", fake_envs_pkg)
    monkeypatch.setitem(sys.modules, "miniwob.envs.miniwob_envs", fake_envs_mod)
    return _FakeEnv


def _args(tmp_path, seeds=(0, 1, 2, 3, 4)):
    seeds_file = tmp_path / "seeds.json"
    seeds_file.write_text(json.dumps(list(seeds)), encoding="utf-8")
    return argparse.Namespace(out=str(tmp_path / "out"), seeds_file=str(seeds_file),
                              player="AutomatedSmokeTest", test=True)


def test_under_real_path_guard():
    assert m._under_real_path(m.REAL_OUT)
    assert m._under_real_path(m.REAL_OUT + "/nested")
    assert not m._under_real_path(m.REAL_OUT + "_other")
    assert not m._under_real_path("/tmp/scratch")


def test_prompt_action_parses_click_type_key_quit():
    answers = iter(["", "bogus", "click 12 34", "type hi there", "key Enter", "quit"])
    tool, args = m._prompt_action(lambda _msg: next(answers))
    assert tool == "click" and args == {"x": 12, "y": 34}
    answers2 = iter(["type hi there"])
    tool, args = m._prompt_action(lambda _msg: next(answers2))
    assert tool == "type_text" and args == {"text": "hi there"}
    answers3 = iter(["key Enter"])
    tool, args = m._prompt_action(lambda _msg: next(answers3))
    assert tool == "press_key" and args == {"key": "Enter"}
    answers4 = iter(["quit"])
    tool, args = m._prompt_action(lambda _msg: next(answers4))
    assert tool == "quit" and args == {}


def test_dry_run_five_episode_success_writes_conformant_artifact(fake_env_cls, tmp_path):
    args = _args(tmp_path)
    answers = iter(["click 10 10"] * 5)
    rc = m.run(args, prompt=lambda _msg: next(answers), opener=lambda _path: None)
    assert rc == 0

    metrics_path = tmp_path / "out" / "human_metrics.json"
    assert metrics_path.exists()
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    # Exact schema score_gate0._verify_sources requires (tests/test_score_gate0.py
    # test_frozen_source_pins_load_exact_artifacts): schema_version, arm, role, mode,
    # wall_clock_s, primitive_actions.
    assert metrics["schema_version"] == 1
    assert metrics["arm"] == "miniwob"
    assert metrics["role"] == "human"
    assert metrics["mode"] == "readiness_dev"
    assert metrics["success"] is True
    assert metrics["wall_clock_s"] >= 0
    # 5 clicks (one terminal per episode) + 5 reset_episode calls (one after each episode,
    # including the exhausting call after episode 4).
    assert metrics["primitive_actions"] == 10
    assert metrics["player"] == "TEST:AutomatedSmokeTest"
    assert metrics["test_mode"] is True

    oracle_rows = [json.loads(line) for line in (tmp_path / "out" / "oracle.jsonl").read_text().splitlines()]
    episodes = {row["episode"] for row in oracle_rows}
    assert episodes == {0, 1, 2, 3, 4}


def test_dry_run_quit_writes_incomplete_artifact_not_canonical(fake_env_cls, tmp_path):
    args = _args(tmp_path)
    rc = m.run(args, prompt=lambda _msg: "quit", opener=lambda _path: None)
    assert rc == 1
    assert not (tmp_path / "out" / "human_metrics.json").exists()
    incomplete = list((tmp_path / "out").glob("human_metrics.INCOMPLETE_*.json"))
    assert len(incomplete) == 1
    metrics = json.loads(incomplete[0].read_text(encoding="utf-8"))
    assert metrics["success"] is False
    assert "human_quit" in metrics["failures"]
    assert metrics["primitive_actions"] == 0


def test_refuses_seed_manifest_that_does_not_match_frozen_dev_seeds(tmp_path):
    args = _args(tmp_path, seeds=(9, 9, 9, 9, 9))
    rc = m.run(args)
    assert rc == 2
    assert not (tmp_path / "out").exists()


def test_test_mode_refuses_real_baseline_path(tmp_path):
    seeds_file = tmp_path / "seeds.json"
    seeds_file.write_text(json.dumps([0, 1, 2, 3, 4]), encoding="utf-8")
    args = argparse.Namespace(out=m.REAL_OUT, seeds_file=str(seeds_file), player="x", test=True)
    rc = m.run(args)
    assert rc == 2
