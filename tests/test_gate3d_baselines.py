"""Unit tests for tools/gate3d_baselines.py's CI-safe logic: policy factories, seed-block
distinctness (from each other AND from the pinned gate seeds), and the summary-stats computation in
run_baseline. NO real vizdoom import here (module-level import of core.vizdoom_world.VizdoomWorld is
lazy, inside run_baseline, precisely so this file can run in CI without vizdoom installed) --
run_baseline itself is exercised against a tiny FAKE world stand-in, mirroring
tests/test_doom_dtc_session.py's fake-vizdoom style but scoped to only what VizdoomWorld exposes that
this tool actually calls (reset/step/episode_finished/tic/game_variables/close)."""
from __future__ import annotations

import json

from tools.gate3d_baselines import (
    BUTTONS,
    MAX_STEPS,
    N_EPISODES,
    SEED_BLOCKS,
    _attack_only_policy,
    _random_policy,
    _run_episode,
    _spinner_policy,
    run_baseline,
)

# ---------------------------------------------------------------------------
# Seed-block distinctness: the 3 baselines' seed ranges must not overlap each other or the 30 pinned
# gate seeds (eval/fixtures/gate3d_seeds.json: 1000..1029).
# ---------------------------------------------------------------------------

PINNED_GATE_SEEDS = set(range(1000, 1030))


def test_seed_blocks_do_not_overlap_each_other():
    ranges = {name: set(range(base, base + N_EPISODES)) for name, base in SEED_BLOCKS.items()}
    names = list(ranges)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            assert ranges[names[i]].isdisjoint(ranges[names[j]]), (names[i], names[j])


def test_seed_blocks_do_not_overlap_pinned_gate_seeds():
    for name, base in SEED_BLOCKS.items():
        block = set(range(base, base + N_EPISODES))
        assert block.isdisjoint(PINNED_GATE_SEEDS), name


# ---------------------------------------------------------------------------
# Policy factories.
# ---------------------------------------------------------------------------

def test_random_policy_only_emits_pinned_buttons():
    policy = _random_policy(42)
    seen = {policy(i) for i in range(200)}
    assert seen <= set(BUTTONS)
    assert len(seen) > 1   # 200 draws over 3 buttons should see more than one value


def test_random_policy_reproducible_for_same_seed():
    a = [_random_policy(7)(i) for i in range(50)]
    b = [_random_policy(7)(i) for i in range(50)]
    assert a == b


def test_random_policy_differs_across_seeds_typically():
    # Small consecutive int seeds can coincidentally alias on a 3-way choice() (Mersenne Twister
    # quirk) -- use seeds from the tool's own actual seed blocks (20000/21000), which is what
    # run_baseline really passes, to pin real production behavior rather than an arbitrary pair.
    a = [_random_policy(20000)(i) for i in range(50)]
    b = [_random_policy(21000)(i) for i in range(50)]
    assert a != b


def test_spinner_policy_alternates_turn_left_and_attack():
    policy = _spinner_policy(0)
    seq = [policy(i) for i in range(6)]
    assert seq == ["TURN_LEFT", "ATTACK", "TURN_LEFT", "ATTACK", "TURN_LEFT", "ATTACK"]


def test_attack_only_policy_never_turns():
    policy = _attack_only_policy(0)
    assert all(policy(i) == "ATTACK" for i in range(20))


# ---------------------------------------------------------------------------
# _run_episode + run_baseline summary stats, against a tiny fake world.
# ---------------------------------------------------------------------------

class _FakeWorld:
    """Minimal stand-in exposing exactly what gate3d_baselines.py calls on VizdoomWorld: reset(seed),
    step(button, repeat), .episode_finished, .tic, game_variables(), close(). Ends the episode after a
    fixed number of steps and awards one killcount per ATTACK action."""

    def __init__(self, end_after_steps: int = 5):
        self.end_after_steps = end_after_steps
        self._step_count = 0
        self._killcount = 0
        self._tic = 0
        self._finished = True
        self.closed = False

    def reset(self, seed=None):
        self._step_count = 0
        self._killcount = 0
        self._tic = 0
        self._finished = False

    def step(self, button, repeat=1):
        self._step_count += 1
        self._tic += 4
        if button == "ATTACK":
            self._killcount += 1
        if self._step_count >= self.end_after_steps:
            self._finished = True

    @property
    def episode_finished(self):
        return self._finished

    @property
    def tic(self):
        return self._tic

    def game_variables(self):
        # Mirrors core.vizdoom_world.VizdoomWorld's real guard EXACTLY: None once the episode has
        # ended, even on the very step that just ended it (VizdoomWorld's own docstring: "Returns
        # None when the episode has ended"). This is the behavior that made the first cut of
        # _run_episode always report killcount=None for episodes that end by death rather than by
        # hitting MAX_STEPS -- see test_run_episode_snapshots_gv_before_the_terminal_step_hides_it.
        if self._finished:
            return None
        return {"KILLCOUNT": float(self._killcount), "HEALTH": 100.0, "AMMO2": 26.0}

    def close(self):
        self.closed = True


def test_run_episode_stops_at_episode_finished_before_max_steps():
    world = _FakeWorld(end_after_steps=3)
    rec = _run_episode(world, seed=1, policy=_attack_only_policy(1))
    assert rec["steps"] == 3
    assert rec["episode_finished"] is True
    # KNOWN ADAPTER LIMITATION (core.vizdoom_world.VizdoomWorld.game_variables(), not fixable from
    # this tool): it returns None once is_episode_finished() is True, INCLUDING on the very step that
    # just caused it to become true -- there is no guarded way to read the truly-terminal killcount.
    # _run_episode's best-effort fix is to snapshot the last non-None reading INSIDE the loop, so the
    # reported killcount is "as of one step before termination" rather than a flat None. Here that is
    # 2 (the 3rd ATTACK's own increment is on the now-unreadable terminal step) -- NOT 3. A naive
    # "read game_variables() once after the loop" would report None; this is the honest next-best value.
    assert rec["killcount"] == 2.0


def test_run_episode_caps_at_max_steps_when_episode_never_ends():
    world = _FakeWorld(end_after_steps=MAX_STEPS + 100)
    rec = _run_episode(world, seed=1, policy=_attack_only_policy(1))
    assert rec["steps"] == MAX_STEPS
    assert rec["episode_finished"] is False
    # MAX_STEPS is reached WITHOUT the episode ever finishing, so game_variables() is still readable
    # on the very last step -- no off-by-one here, unlike the death-ending case above (every step
    # ATTACKs, so killcount == steps exactly).
    assert rec["killcount"] == MAX_STEPS


def test_run_baseline_writes_one_jsonl_row_per_episode_and_a_correct_summary(tmp_path, monkeypatch):
    fake = _FakeWorld(end_after_steps=4)
    monkeypatch.setattr("core.vizdoom_world.VizdoomWorld", lambda cfg: fake, raising=False)
    import core.vizdoom_world  # noqa: F401  -- ensure the module exists to patch onto

    out_path = tmp_path / "attack_only.jsonl"
    result = run_baseline("attack_only", _attack_only_policy, str(out_path), n_episodes=5)

    with open(out_path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert len(rows) == 5
    # end_after_steps=4 -> the 4th ATTACK's increment lands on the now-unreadable terminal step (see
    # the adapter-limitation note above), so the best-effort reported killcount is 3, not 4.
    assert all(r["killcount"] == 3.0 for r in rows)
    assert result["n_episodes"] == 5
    assert result["mean_killcount"] == 3.0
    assert result["std_killcount"] == 0.0
    assert result["killcount_distribution"] == {"3": 5}
    assert fake.closed is True
