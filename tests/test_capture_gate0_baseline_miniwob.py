"""Tests for tools/capture_gate0_baseline_miniwob.py -- the Gate 0 Arm W human-baseline rig.

CI-safe: no browser, no miniwob/selenium install -- the same _FakeMiniwobEnv monkeypatch seam
tests/test_miniwob_world.py uses stands in for the real gymnasium env. "David" is simulated by a
canned `prompt` callable (dependency-injected via capture_gate0_baseline_miniwob.run()'s `prompt`
param) -- these tests exercise the RIG's plumbing (dispatch, episode advance, artifact schema,
success/incomplete detection), never real MiniWoB gameplay.

HELD-OUT LAW: the `--mode paid_gate0` tests below exercise the rig's PLUMBING (mode selection,
path resolution, the --i-am-human guard, seed cross-contamination refusal) using the exact same
`_FakeEnv` fake -- never a real MiniWoB env, and never anything that could produce or observe real
held-out-seed task content. The paid seed *numbers* (1000-1004) are not sensitive -- they are
already committed in eval/fixtures/gate0_miniwob_paid_seeds.json and eval/score_gate0.py; what must
never leak into a dev/build process is the actual rendered environment content for those seeds,
which these tests never touch (the fake env ignores its seed argument entirely).
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


# The real env's PRESS_KEY vocabulary (miniwob.constants.DEFAULT_ALLOWED_KEYS), first 11 entries --
# PRESS_KEY takes an INDEX into this list, which is what _prompt_action resolves a typed name to.
_ALLOWED_KEYS = ("<Enter>", "<PageUp>", "<PageDown>", "<Backspace>", "<Delete>", "<Tab>", "<Space>",
                 "<ArrowUp>", "<ArrowRight>", "<ArrowDown>", "<ArrowLeft>")


class _FakeUnwrapped:
    def __init__(self):
        self.instance = _FakeInstance()
        self.action_space_config = types.SimpleNamespace(allowed_keys=_ALLOWED_KEYS)

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


def _args(tmp_path, seeds=(0, 1, 2, 3, 4), allow_retake=None, mode="readiness_dev",
          i_am_human=False):
    seeds_file = tmp_path / "seeds.json"
    seeds_file.write_text(json.dumps(list(seeds)), encoding="utf-8")
    return argparse.Namespace(out=str(tmp_path / "out"), seeds_file=str(seeds_file),
                              player="AutomatedSmokeTest", test=True, allow_retake=allow_retake,
                              mode=mode, i_am_human=i_am_human)


def test_under_real_path_guard():
    assert m._under_real_path(m.REAL_OUT)
    assert m._under_real_path(m.REAL_OUT + "/nested")
    assert not m._under_real_path(m.REAL_OUT + "_other")
    assert not m._under_real_path("/tmp/scratch")


def test_prompt_action_parses_click_type_key_quit():
    answers = iter(["", "bogus", "click 12 34", "type hi there", "key Enter", "quit"])
    tool, args = m._prompt_action(lambda _msg: next(answers), list(_ALLOWED_KEYS))
    assert tool == "click" and args == {"x": 12, "y": 34}
    answers2 = iter(["type hi there"])
    tool, args = m._prompt_action(lambda _msg: next(answers2), list(_ALLOWED_KEYS))
    assert tool == "type_text" and args == {"text": "hi there"}
    # A typed key NAME is validated here but passed through AS A NAME: MiniWobSession._resolve_key is
    # the single place a name becomes miniwob's PRESS_KEY index, for human and agent alike. Pre-resolving
    # here (the old behaviour) is impossible to do safely -- indices 0/5/9 are <Enter>/<Tab>/<ArrowDown>
    # while '0'-'9' are ALSO key names, so a pre-resolved "5" and a typed "5" are indistinguishable.
    for typed, sent in (("key Enter", "<Enter>"), ("key Tab", "<Tab>"),
                        ("key ArrowDown", "<ArrowDown>"), ("key <Tab>", "<Tab>")):
        answers3 = iter([typed])
        tool, args = m._prompt_action(lambda _msg: next(answers3), list(_ALLOWED_KEYS))
        assert tool == "press_key" and args == {"key": sent}
    # A key the environment doesn't accept re-prompts instead of dying inside the browser.
    answers4 = iter(["key Escape", "key Tab"])
    tool, args = m._prompt_action(lambda _msg: next(answers4), list(_ALLOWED_KEYS))
    assert tool == "press_key" and args == {"key": "<Tab>"}
    answers5 = iter(["quit"])
    tool, args = m._prompt_action(lambda _msg: next(answers5), list(_ALLOWED_KEYS))
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
    args = argparse.Namespace(out=m.REAL_OUT, seeds_file=str(seeds_file), player="x", test=True,
                              allow_retake=None)
    rc = m.run(args)
    assert rc == 2


def test_first_attempt_has_attempt_number_1_and_empty_retake_reason(fake_env_cls, tmp_path):
    args = _args(tmp_path)
    answers = iter(["click 10 10"] * 5)
    rc = m.run(args, prompt=lambda _msg: next(answers), opener=lambda _path: None)
    assert rc == 0
    metrics = json.loads((tmp_path / "out" / "human_metrics.json").read_text(encoding="utf-8"))
    assert metrics["attempt_number"] == 1
    assert metrics["retake_reason"] == ""


def test_overwrite_refused_without_allow_retake(fake_env_cls, tmp_path):
    args = _args(tmp_path)
    answers = iter(["click 10 10"] * 5)
    rc = m.run(args, prompt=lambda _msg: next(answers), opener=lambda _path: None)
    assert rc == 0
    metrics_path = tmp_path / "out" / "human_metrics.json"
    original = metrics_path.read_text(encoding="utf-8")

    # Second attempt, no --allow-retake: must refuse outright and leave the first artifact untouched.
    args2 = _args(tmp_path)
    answers2 = iter(["click 20 20"] * 5)
    rc2 = m.run(args2, prompt=lambda _msg: next(answers2), opener=lambda _path: None)
    assert rc2 == 2
    assert metrics_path.read_text(encoding="utf-8") == original


def test_overwrite_allowed_with_allow_retake_records_attempt_and_reason(fake_env_cls, tmp_path):
    args = _args(tmp_path)
    answers = iter(["click 10 10"] * 5)
    rc = m.run(args, prompt=lambda _msg: next(answers), opener=lambda _path: None)
    assert rc == 0

    args2 = _args(tmp_path, allow_retake="Docker died mid-capture, first attempt never scored")
    answers2 = iter(["click 20 20"] * 5)
    rc2 = m.run(args2, prompt=lambda _msg: next(answers2), opener=lambda _path: None)
    assert rc2 == 0
    metrics = json.loads((tmp_path / "out" / "human_metrics.json").read_text(encoding="utf-8"))
    assert metrics["attempt_number"] == 2
    assert metrics["retake_reason"] == "Docker died mid-capture, first attempt never scored"
    # the prior attempt's oracle trace was archived (never deleted), not silently appended-into --
    # otherwise _miniwob_success would see 2 terminal rows per episode and the retake could never
    # score as success no matter how clean it was.
    archived = list((tmp_path / "out").glob("oracle.attempt1_*.jsonl"))
    assert len(archived) == 1
    fresh_oracle_rows = [json.loads(line) for line in
                         (tmp_path / "out" / "oracle.jsonl").read_text().splitlines()]
    assert {row["episode"] for row in fresh_oracle_rows} == {0, 1, 2, 3, 4}


def test_free_rerun_after_partial_crash_scores_cleanly(fake_env_cls, tmp_path):
    """PR #119 re-review MAJOR (live-reproduced by the reviewer): MiniWobSession writes each
    episode's done=True terminal row to oracle.jsonl incrementally DURING the run, so an attempt
    that completes episodes 0-1 and then quits BEFORE any canonical human_metrics.json write
    leaves real stale terminal rows on disk. The documented recovery for exactly this case is a
    free re-run with no flags ("just re-run the command; nothing extra needed" -- --allow-retake
    cannot even apply, since there is no canonical file to allow retaking). Pre-fix, the oracle
    archival was gated on the canonical file's existence, so the free re-run appended onto the
    stale trace and failed forever with miniwob_episode_0/1_terminal_count. Post-fix, archival
    fires whenever oracle.jsonl exists at session start, and the clean 5-episode re-run must
    score as success."""
    # Attempt 1: episodes 0 and 1 complete (terminal rows hit disk), quit at episode 2's prompt.
    args = _args(tmp_path)
    answers = iter(["click 10 10", "click 10 10", "quit"])
    rc = m.run(args, prompt=lambda _msg: next(answers), opener=lambda _path: None)
    assert rc == 1
    out = tmp_path / "out"
    assert not (out / "human_metrics.json").exists()
    stale_rows = [json.loads(line) for line in (out / "oracle.jsonl").read_text().splitlines()]
    assert any(r.get("done") is True for r in stale_rows)   # the poison: real terminal rows on disk

    # Attempt 2: the documented free re-run -- no flags, all 5 episodes clean.
    args2 = _args(tmp_path)
    answers2 = iter(["click 10 10"] * 5)
    rc2 = m.run(args2, prompt=lambda _msg: next(answers2), opener=lambda _path: None)
    assert rc2 == 0
    metrics = json.loads((out / "human_metrics.json").read_text(encoding="utf-8"))
    assert metrics["success"] is True
    assert metrics["failures"] == []
    assert metrics["attempt_number"] == 1   # still the FIRST attempt -- the crashed try never scored
    assert metrics["retake_reason"] == ""
    # The stale partial trace was archived byte-for-byte (renamed, never deleted), and the live
    # oracle.jsonl now contains ONLY this run's rows -- one terminal per episode, all 5 episodes.
    archived = list(out.glob("oracle.attempt1_*.jsonl"))
    assert len(archived) == 1
    archived_rows = [json.loads(line) for line in archived[0].read_text().splitlines()]
    assert archived_rows == stale_rows
    fresh_rows = [json.loads(line) for line in (out / "oracle.jsonl").read_text().splitlines()]
    assert {row["episode"] for row in fresh_rows} == {0, 1, 2, 3, 4}
    assert sum(1 for r in fresh_rows if r.get("done") is True) == 5


def test_artifact_has_capture_modality_and_input_event_times(fake_env_cls, tmp_path):
    args = _args(tmp_path)
    answers = iter(["click 10 10"] * 5)
    rc = m.run(args, prompt=lambda _msg: next(answers), opener=lambda _path: None)
    assert rc == 0
    metrics = json.loads((tmp_path / "out" / "human_metrics.json").read_text(encoding="utf-8"))
    assert metrics["capture_modality"] == "screenshot_relay_typed_action"
    assert isinstance(metrics["input_event_times"], list)
    assert len(metrics["input_event_times"]) == metrics["primitive_actions"] == 10
    assert all(isinstance(t, float) for t in metrics["input_event_times"])


def test_tty_guard_refuses_real_path_when_stdin_not_a_tty(monkeypatch, tmp_path):
    seeds_file = tmp_path / "seeds.json"
    seeds_file.write_text(json.dumps([0, 1, 2, 3, 4]), encoding="utf-8")
    monkeypatch.setattr(m.sys.stdin, "isatty", lambda: False, raising=False)
    args = argparse.Namespace(out=m.REAL_OUT, seeds_file=str(seeds_file), player="x", test=False,
                              allow_retake=None)
    rc = m.run(args)
    assert rc == 2


def test_tty_guard_does_not_block_non_real_path(fake_env_cls, monkeypatch, tmp_path):
    """The TTY guard is scoped to the REAL baseline path -- a scratch --out in non-test mode is a
    documented, already-warned-about manual dry run and must not be blocked by it."""
    seeds_file = tmp_path / "seeds.json"
    seeds_file.write_text(json.dumps([0, 1, 2, 3, 4]), encoding="utf-8")
    monkeypatch.setattr(m.sys.stdin, "isatty", lambda: False, raising=False)
    out = tmp_path / "scratch_non_real"
    args = argparse.Namespace(out=str(out), seeds_file=str(seeds_file), player="x", test=False,
                              allow_retake=None)
    answers = iter(["click 10 10"] * 5)
    rc = m.run(args, prompt=lambda _msg: next(answers), opener=lambda _path: None)
    assert rc == 0
    assert (out / "human_metrics.json").exists()


def test_atomic_write_leaves_no_partial_file_on_crash(monkeypatch, tmp_path):
    target = tmp_path / "human_metrics.json"

    def _boom(*_a, **_kw):
        raise RuntimeError("simulated crash mid-write")

    monkeypatch.setattr(m.json, "dump", _boom)
    with pytest.raises(RuntimeError):
        m._atomic_write_json(str(target), {"schema_version": 1})
    assert not target.exists()
    # no stray temp file left behind either
    assert list(tmp_path.glob("human_metrics.json.tmp*")) == []


# ---------------------------------------------------------------------------------------------
# --mode paid_gate0 (held-out-seed replay for the paid gate's MiniWoB human denominator)
# ---------------------------------------------------------------------------------------------

def test_mode_config_paths_are_distinct_and_match_source_pins():
    """paid_gate0's real_out must be the EXACT path gate0_paid_source_pins.json's
    artifact_paths.miniwob_human names -- a silent drift here would make a real capture land
    somewhere score_gate0's source-pin verification never looks."""
    dev_out = m.MODE_CONFIG["readiness_dev"]["real_out"]
    paid_out = m.MODE_CONFIG["paid_gate0"]["real_out"]
    assert dev_out != paid_out
    assert paid_out.replace("\\", "/").endswith("runs/gate0_paid_human_baseline/miniwob")
    assert dev_out.replace("\\", "/").endswith("runs/gate0_human_baseline/miniwob")
    assert m.MODE_CONFIG["readiness_dev"]["seeds_file"] != m.MODE_CONFIG["paid_gate0"]["seeds_file"]


def test_under_real_path_guard_is_mode_aware():
    dev_out, paid_out = m.MODE_CONFIG["readiness_dev"]["real_out"], m.MODE_CONFIG["paid_gate0"]["real_out"]
    assert m._under_real_path(dev_out, dev_out)
    assert not m._under_real_path(paid_out, dev_out)
    assert m._under_real_path(paid_out, paid_out)
    assert not m._under_real_path(dev_out, paid_out)


def test_paid_mode_dry_run_five_episode_success_writes_conformant_artifact(fake_env_cls, tmp_path):
    args = _args(tmp_path, seeds=(1000, 1001, 1002, 1003, 1004), mode="paid_gate0", i_am_human=True)
    answers = iter(["click 10 10"] * 5)
    rc = m.run(args, prompt=lambda _msg: next(answers), opener=lambda _path: None)
    assert rc == 0

    metrics = json.loads((tmp_path / "out" / "human_metrics.json").read_text(encoding="utf-8"))
    assert metrics["mode"] == "paid_gate0"
    assert metrics["success"] is True
    assert metrics["expected_seeds"] == [1000, 1001, 1002, 1003, 1004]
    oracle_rows = [json.loads(line) for line in (tmp_path / "out" / "oracle.jsonl").read_text().splitlines()]
    assert {row["seed"] for row in oracle_rows} == {1000, 1001, 1002, 1003, 1004}


def test_paid_mode_refuses_without_i_am_human(fake_env_cls, tmp_path):
    args = _args(tmp_path, seeds=(1000, 1001, 1002, 1003, 1004), mode="paid_gate0", i_am_human=False)
    rc = m.run(args, prompt=lambda _msg: (_ for _ in ()).throw(AssertionError("must not prompt")),
               opener=lambda _path: None)
    assert rc == 2
    # refused before any directory/artifact was created -- no partial state left behind either.
    assert not (tmp_path / "out").exists()


def test_paid_mode_refuses_dev_seed_manifest_cross_contamination(fake_env_cls, tmp_path):
    """A DEV seeds file (0..4) must never satisfy --mode paid_gate0."""
    args = _args(tmp_path, seeds=(0, 1, 2, 3, 4), mode="paid_gate0", i_am_human=True)
    rc = m.run(args)
    assert rc == 2
    assert not (tmp_path / "out").exists()


def test_dev_mode_refuses_paid_seed_manifest_cross_contamination(fake_env_cls, tmp_path):
    """The held-out paid seeds (1000..1004) must never satisfy --mode readiness_dev (the default)."""
    args = _args(tmp_path, seeds=(1000, 1001, 1002, 1003, 1004))  # mode defaults to readiness_dev
    rc = m.run(args)
    assert rc == 2
    assert not (tmp_path / "out").exists()


def test_paid_mode_test_flag_refuses_real_baseline_path(tmp_path):
    seeds_file = tmp_path / "seeds.json"
    seeds_file.write_text(json.dumps([1000, 1001, 1002, 1003, 1004]), encoding="utf-8")
    args = argparse.Namespace(out=m.MODE_CONFIG["paid_gate0"]["real_out"], seeds_file=str(seeds_file),
                              player="x", test=True, allow_retake=None, mode="paid_gate0",
                              i_am_human=True)
    rc = m.run(args)
    assert rc == 2


def test_paid_mode_default_out_and_seeds_file_when_omitted(tmp_path):
    """Passing --out/--seeds-file=None (argparse's default when the flag is omitted) must resolve
    to paid_gate0's own canonical paths, not silently fall back to the DEV ones. run() mutates
    `args` in place while resolving defaults, so inspect the Namespace after the call -- a stronger
    check than the return code alone (both a correct and an incorrect resolution can return 2, for
    different reasons)."""
    args = argparse.Namespace(out=None, seeds_file=None, player="x", test=True, allow_retake=None,
                              mode="paid_gate0", i_am_human=True)
    m.run(args)
    assert args.out == m.MODE_CONFIG["paid_gate0"]["real_out"]
    assert args.seeds_file == str(m.MODE_CONFIG["paid_gate0"]["seeds_file"])


def test_paid_mode_never_prints_task_utterance(fake_env_cls, tmp_path, capsys):
    """HELD-OUT LAW: --mode paid_gate0 must never echo task/page text to stdout. The DEV mode's
    utterance print is unaffected (asserted in the second half below)."""
    args = _args(tmp_path, seeds=(1000, 1001, 1002, 1003, 1004), mode="paid_gate0", i_am_human=True)
    answers = iter(["click 10 10"] * 5)
    rc = m.run(args, prompt=lambda _msg: next(answers), opener=lambda _path: None)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Select the indicated checkboxes" not in out   # the fake env's utterance text
    assert "suppressed in --mode paid_gate0" in out

    # fresh --out subdir so this dev run's artifact doesn't collide with the paid run's above
    dev_args = _args(tmp_path, seeds=(0, 1, 2, 3, 4))
    dev_args.out = str(tmp_path / "dev_out")
    answers2 = iter(["click 10 10"] * 5)
    rc2 = m.run(dev_args, prompt=lambda _msg: next(answers2), opener=lambda _path: None)
    assert rc2 == 0
    dev_out = capsys.readouterr().out
    assert "Select the indicated checkboxes" in dev_out   # unaffected for readiness_dev


def test_unknown_mode_refused(tmp_path):
    args = _args(tmp_path, mode="bogus_mode")
    rc = m.run(args)
    assert rc == 2
    assert not (tmp_path / "out").exists()


# ---------------------------------------------------------------------------------------------
# --mode paid_gate0_v2 (Gate 0 v2's FRESH held-out block -- prereg §4.1/P9). Same _FakeEnv-only
# discipline as the paid_gate0 block above: the rig's PLUMBING is exercised, never a real MiniWoB
# env for a held-out seed. The v2 seed *numbers* are committed in
# eval/fixtures/gate0_miniwob_paid_v2_seeds.json; what must never leak into a dev/build process is
# the rendered task CONTENT for them, which these tests never touch.
# ---------------------------------------------------------------------------------------------

import eval.score_gate0 as _scorer

V2_SEEDS = tuple(_scorer.MODES["paid_gate0_v2"][1])


def test_v2_mode_config_matches_the_scorer_and_its_source_pins():
    """A silent drift here would make a real v2 capture land somewhere score_gate0's source-pin
    verification never looks."""
    cfg = m.MODE_CONFIG["paid_gate0_v2"]
    assert cfg["seeds_file"] == _scorer.MODES["paid_gate0_v2"][0]
    assert cfg["real_out"].replace("\\", "/").endswith("runs/gate0_paid_v2_human_baseline/miniwob")
    pins = json.loads(_scorer.SOURCE_PIN_FILES["paid_gate0_v2"].read_text(encoding="utf-8"))
    assert pins["artifact_paths"]["miniwob_human"] == \
        "runs/gate0_paid_v2_human_baseline/miniwob/human_metrics.json"
    # distinct from BOTH other modes, in both directions
    for other in ("readiness_dev", "paid_gate0"):
        assert cfg["real_out"] != m.MODE_CONFIG[other]["real_out"]
        assert cfg["seeds_file"] != m.MODE_CONFIG[other]["seeds_file"]
        assert not m._under_real_path(cfg["real_out"], m.MODE_CONFIG[other]["real_out"])
        assert not m._under_real_path(m.MODE_CONFIG[other]["real_out"], cfg["real_out"])


def test_v2_is_registered_as_a_held_out_mode():
    assert m.HELD_OUT_MODES == frozenset({"paid_gate0", "paid_gate0_v2"})
    assert set(m.MODE_CONFIG) - m.HELD_OUT_MODES == {"readiness_dev"}


def test_v2_mode_dry_run_five_episode_success_writes_conformant_artifact(fake_env_cls, tmp_path):
    """The artifact's `mode` MUST be paid_gate0_v2 -- eval/score_gate0.py's _verify_sources requires
    the human artifact's mode to EQUAL the scoring mode, else `human_metric_identity:miniwob`."""
    args = _args(tmp_path, seeds=V2_SEEDS, mode="paid_gate0_v2", i_am_human=True)
    answers = iter(["click 10 10"] * 5)
    rc = m.run(args, prompt=lambda _msg: next(answers), opener=lambda _path: None)
    assert rc == 0

    metrics = json.loads((tmp_path / "out" / "human_metrics.json").read_text(encoding="utf-8"))
    assert metrics["mode"] == "paid_gate0_v2"
    assert (metrics["schema_version"], metrics["arm"], metrics["role"]) == (1, "miniwob", "human")
    assert metrics["success"] is True
    assert metrics["expected_seeds"] == list(V2_SEEDS)
    assert metrics["wall_clock_s"] >= 0 and metrics["primitive_actions"] > 0
    # PR #174's fields survive the v2 addition (built on, not reverted or duplicated).
    assert metrics["operator_hint"] == m.OPERATOR_HINT
    assert metrics["press_key_resolution"] == m.PRESS_KEY_RESOLUTION
    oracle_rows = [json.loads(line) for line in (tmp_path / "out" / "oracle.jsonl").read_text().splitlines()]
    assert {row["seed"] for row in oracle_rows} == set(V2_SEEDS)


def test_v2_mode_refuses_without_i_am_human(fake_env_cls, tmp_path):
    args = _args(tmp_path, seeds=V2_SEEDS, mode="paid_gate0_v2", i_am_human=False)
    rc = m.run(args, prompt=lambda _msg: (_ for _ in ()).throw(AssertionError("must not prompt")),
               opener=lambda _path: None)
    assert rc == 2
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("wrong_seeds", [(0, 1, 2, 3, 4), (1000, 1001, 1002, 1003, 1004)])
def test_v2_mode_refuses_cross_contamination_from_either_other_block(fake_env_cls, tmp_path,
                                                                     wrong_seeds):
    args = _args(tmp_path, seeds=wrong_seeds, mode="paid_gate0_v2", i_am_human=True)
    assert m.run(args) == 2
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("mode", ["readiness_dev", "paid_gate0"])
def test_other_modes_refuse_the_v2_seed_manifest(fake_env_cls, tmp_path, mode):
    """The v2 block must never satisfy a v1/dev capture either -- the guard is symmetric."""
    args = _args(tmp_path, seeds=V2_SEEDS, mode=mode, i_am_human=True)
    assert m.run(args) == 2
    assert not (tmp_path / "out").exists()


def test_v2_mode_test_flag_refuses_real_baseline_path(tmp_path):
    seeds_file = tmp_path / "seeds.json"
    seeds_file.write_text(json.dumps(list(V2_SEEDS)), encoding="utf-8")
    args = argparse.Namespace(out=m.MODE_CONFIG["paid_gate0_v2"]["real_out"],
                              seeds_file=str(seeds_file), player="x", test=True,
                              allow_retake=None, mode="paid_gate0_v2", i_am_human=True)
    assert m.run(args) == 2


def test_v2_mode_default_out_and_seeds_file_when_omitted(tmp_path):
    args = argparse.Namespace(out=None, seeds_file=None, player="x", test=True, allow_retake=None,
                              mode="paid_gate0_v2", i_am_human=True)
    m.run(args)
    assert args.out == m.MODE_CONFIG["paid_gate0_v2"]["real_out"]
    assert args.seeds_file == str(m.MODE_CONFIG["paid_gate0_v2"]["seeds_file"])


def test_v2_mode_never_prints_task_utterance(fake_env_cls, tmp_path, capsys):
    args = _args(tmp_path, seeds=V2_SEEDS, mode="paid_gate0_v2", i_am_human=True)
    answers = iter(["click 10 10"] * 5)
    assert m.run(args, prompt=lambda _msg: next(answers), opener=lambda _path: None) == 0
    out = capsys.readouterr().out
    assert "Select the indicated checkboxes" not in out
    assert "suppressed in --mode paid_gate0_v2" in out
