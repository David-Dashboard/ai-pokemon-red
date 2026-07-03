"""Unit tests for tools/gate3d_baselines.py's CI-safe logic (as amended by A2): policy factories incl.
the TRUE multi-hot spinner, seed-block distinctness (from each other, from the pinned gate seeds, AND
from the superseded A2-trigger run's blocks), the ammo2 first/last logging, and the KPS summary math.
NO real vizdoom import here (the VizdoomWorld import is lazy, inside run_baseline, precisely so this
file can run in CI without vizdoom installed) -- the episode runner is exercised against a fake
world/game pair mirroring exactly what the tool touches: reset/step/episode_finished/tic/
game_variables/screen/close on the world, and get_available_buttons/make_action/is_episode_finished
on world.game (the SS A2.1 raw multi-hot path)."""
from __future__ import annotations

import json

from tools.gate3d_baselines import (
    BUTTONS,
    MAX_STEPS,
    N_EPISODES,
    SEED_BLOCKS,
    TICS_PER_STEP,
    _attack_only_policy,
    _random_policy,
    _run_episode,
    _spinner_alternating_policy,
    _spinner_multihot_policy,
    run_baseline,
    summarize,
)

# ---------------------------------------------------------------------------
# Seed-block distinctness: the 4 baselines' seed ranges must not overlap each other, the 30 pinned
# gate seeds (eval/fixtures/gate3d_seeds.json: 1000..1029), or the superseded 2026-07-03 A2-trigger
# run's blocks (20000/21000/22000 + 200 each) -- SS A2.3's "fresh seed blocks".
# ---------------------------------------------------------------------------

PINNED_GATE_SEEDS = set(range(1000, 1030))
A2_TRIGGER_RUN_SEEDS = set(range(20000, 20200)) | set(range(21000, 21200)) | set(range(22000, 22200))


def test_all_four_policies_have_seed_blocks():
    assert set(SEED_BLOCKS) == {"random", "attack_only", "spinner_multihot", "spinner_alternating"}


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


def test_seed_blocks_are_fresh_vs_the_a2_trigger_run():
    for name, base in SEED_BLOCKS.items():
        block = set(range(base, base + N_EPISODES))
        assert block.isdisjoint(A2_TRIGGER_RUN_SEEDS), name


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
    # quirk) -- use seeds from the tool's own actual seed blocks, which is what run_baseline really
    # passes, to pin real production behavior rather than an arbitrary pair.
    a = [_random_policy(30000)(i) for i in range(50)]
    b = [_random_policy(31000)(i) for i in range(50)]
    assert a != b


def test_spinner_multihot_policy_presses_both_buttons_every_step():
    policy = _spinner_multihot_policy(0)
    for i in range(5):
        assert policy(i) == ("TURN_LEFT", "ATTACK")   # a TUPLE -> the raw multi-hot path


def test_spinner_alternating_policy_alternates_turn_left_and_attack():
    policy = _spinner_alternating_policy(0)
    seq = [policy(i) for i in range(6)]
    assert seq == ["TURN_LEFT", "ATTACK", "TURN_LEFT", "ATTACK", "TURN_LEFT", "ATTACK"]


def test_attack_only_policy_never_turns():
    policy = _attack_only_policy(0)
    assert all(policy(i) == "ATTACK" for i in range(20))


# ---------------------------------------------------------------------------
# Fake world/game pair. The game mirrors the raw-vizdoom surface the SS A2.1 multi-hot path touches
# (get_available_buttons/make_action/is_episode_finished); the world mirrors VizdoomWorld's guarded
# API exactly, INCLUDING game_variables() -> None once the episode has finished (the adapter's real
# guard -- the source of the "last readable reading is one step before the terminal one" off-by-one
# documented in the tool).
# ---------------------------------------------------------------------------

class _FakeGame:
    LIVE = ("TURN_LEFT", "TURN_RIGHT", "ATTACK")

    def __init__(self, end_after_steps: int = 5):
        self.end_after_steps = end_after_steps
        self.steps = 0
        self._tic = 0
        self.killcount = 0
        self.ammo = 26
        self.finished = True
        self.actions: list[list[int]] = []   # every make_action vector, in order

    def new_episode(self):
        self.steps = 0
        self._tic = 0
        self.killcount = 0
        self.ammo = 26
        self.finished = False

    def get_available_buttons(self):
        return [f"Button.{n}" for n in self.LIVE]   # str(b).rsplit(".", 1)[-1] -> the name

    def is_episode_finished(self):
        return self.finished

    def make_action(self, vec, tics):
        assert tics == TICS_PER_STEP
        self.actions.append(list(vec))
        self.steps += 1
        self._tic += tics
        if vec[self.LIVE.index("ATTACK")]:
            self.ammo -= 1
            self.killcount += 1
        if self.steps >= self.end_after_steps:
            self.finished = True


class _FakeWorld:
    def __init__(self, end_after_steps: int = 5):
        self.game = _FakeGame(end_after_steps)
        self.closed = False

    def reset(self, seed=None):
        self.game.new_episode()

    def step(self, button, repeat=1):
        vec = [0] * len(self.game.LIVE)
        vec[self.game.LIVE.index(button)] = 1
        if not self.game.is_episode_finished():
            self.game.make_action(vec, TICS_PER_STEP)

    def screen(self):
        return None   # guarded read; the tool only calls it for its tic-refresh side effect

    @property
    def episode_finished(self):
        return self.game.is_episode_finished()

    @property
    def tic(self):
        return self.game._tic

    def game_variables(self):
        # Mirrors core.vizdoom_world.VizdoomWorld's real guard EXACTLY: None once the episode has
        # ended, even on the very step that just ended it.
        if self.game.is_episode_finished():
            return None
        return {"KILLCOUNT": float(self.game.killcount), "HEALTH": 100.0,
                "AMMO2": float(self.game.ammo)}

    def close(self):
        self.closed = True


# ---------------------------------------------------------------------------
# _run_episode: both action paths + ammo logging.
# ---------------------------------------------------------------------------

def test_run_episode_multihot_presses_both_buttons_in_one_make_action():
    world = _FakeWorld(end_after_steps=4)
    _run_episode(world, seed=1, policy=_spinner_multihot_policy(1))
    tl = _FakeGame.LIVE.index("TURN_LEFT")
    atk = _FakeGame.LIVE.index("ATTACK")
    assert len(world.game.actions) == 4
    # THE A2.1 point: one make_action per step with BOTH bits set -- not two alternating single-hots.
    assert all(v[tl] == 1 and v[atk] == 1 for v in world.game.actions)


def test_run_episode_single_button_path_stays_single_hot():
    world = _FakeWorld(end_after_steps=4)
    _run_episode(world, seed=1, policy=_attack_only_policy(1))
    assert all(sum(v) == 1 for v in world.game.actions)


def test_run_episode_logs_ammo_first_and_last():
    world = _FakeWorld(end_after_steps=4)
    rec = _run_episode(world, seed=1, policy=_attack_only_policy(1))
    assert rec["ammo2_first"] == 26.0
    # KNOWN ADAPTER LIMITATION (see the tool's docstring): the 4th ATTACK's decrement lands on the
    # now-unreadable terminal step, so the last READABLE reading is after step 3 -> 23.
    assert rec["ammo2_last"] == 23.0
    assert rec["ammo2_increased"] is False
    assert rec["killcount"] == 3.0


def test_run_episode_stops_at_episode_finished_before_max_steps():
    world = _FakeWorld(end_after_steps=3)
    rec = _run_episode(world, seed=1, policy=_attack_only_policy(1))
    assert rec["steps"] == 3
    assert rec["episode_finished"] is True
    assert rec["killcount"] == 2.0   # last readable reading, one step before the terminal one


def test_run_episode_caps_at_max_steps_when_episode_never_ends():
    world = _FakeWorld(end_after_steps=MAX_STEPS + 100)
    rec = _run_episode(world, seed=1, policy=_attack_only_policy(1))
    assert rec["steps"] == MAX_STEPS
    assert rec["episode_finished"] is False
    # MAX_STEPS reached WITHOUT the episode finishing -> game_variables() still readable on the very
    # last step, no off-by-one here (every step ATTACKs, so killcount == steps exactly).
    assert rec["killcount"] == MAX_STEPS
    assert rec["ammo2_last"] == 26.0 - MAX_STEPS


# ---------------------------------------------------------------------------
# summarize: killcount stats + KPS (SS A2.2's formula) + the loud exclusion.
# ---------------------------------------------------------------------------

def _rec(killcount, ammo_first, ammo_last, *, increased=False):
    return {"killcount": killcount, "ammo2_first": ammo_first, "ammo2_last": ammo_last,
            "ammo2_increased": increased}


def test_summarize_kps_is_total_kills_over_total_shots():
    records = [_rec(2.0, 26.0, 21.0), _rec(4.0, 26.0, 11.0)]   # kills 6, shots 5 + 15 = 20
    s = summarize("x", records)
    assert s["total_kills"] == 6.0
    assert s["total_shots"] == 20.0
    assert s["kps"] == 0.3
    assert s["kps_excluded_episodes"] == 0


def test_summarize_excludes_ammo_increase_episodes_from_both_sums():
    records = [_rec(2.0, 26.0, 21.0), _rec(9.0, 26.0, 25.0, increased=True)]
    s = summarize("x", records)
    assert s["total_kills"] == 2.0     # the increased episode's 9 kills NOT counted
    assert s["total_shots"] == 5.0     # ...nor its shots
    assert s["kps_excluded_episodes"] == 1


def test_summarize_excludes_unreadable_ammo_or_killcount():
    records = [_rec(2.0, 26.0, 21.0), _rec(None, 26.0, 20.0), _rec(3.0, None, None)]
    s = summarize("x", records)
    assert s["total_shots"] == 5.0
    assert s["kps_excluded_episodes"] == 2


def test_summarize_kps_none_when_no_shots():
    s = summarize("x", [_rec(0.0, 26.0, 26.0)])
    assert s["kps"] is None


def test_summarize_killcount_stats():
    records = [_rec(4.0, 26.0, 20.0)] * 3 + [_rec(1.0, 26.0, 20.0)]
    s = summarize("x", records)
    assert s["n_episodes"] == 4
    assert s["mean_killcount"] == 3.25
    assert s["killcount_distribution"] == {"4": 3, "1": 1}


# ---------------------------------------------------------------------------
# run_baseline end-to-end against the fake (jsonl rows + summary).
# ---------------------------------------------------------------------------

def test_run_baseline_writes_one_jsonl_row_per_episode_and_a_correct_summary(tmp_path, monkeypatch):
    fake = _FakeWorld(end_after_steps=4)
    monkeypatch.setattr("core.vizdoom_world.VizdoomWorld", lambda cfg: fake, raising=False)
    import core.vizdoom_world  # noqa: F401  -- ensure the module exists to patch onto

    out_path = tmp_path / "attack_only.jsonl"
    result = run_baseline("attack_only", _attack_only_policy, str(out_path), n_episodes=5)

    with open(out_path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert len(rows) == 5
    # end_after_steps=4 -> last readable reading is after step 3 (adapter guard off-by-one): 3 kills,
    # ammo 26 -> 23 (3 shots).
    assert all(r["killcount"] == 3.0 for r in rows)
    assert all(r["ammo2_first"] == 26.0 and r["ammo2_last"] == 23.0 for r in rows)
    assert result["n_episodes"] == 5
    assert result["mean_killcount"] == 3.0
    assert result["std_killcount"] == 0.0
    assert result["killcount_distribution"] == {"3": 5}
    assert result["total_kills"] == 15.0
    assert result["total_shots"] == 15.0
    assert result["kps"] == 1.0
    assert fake.closed is True
