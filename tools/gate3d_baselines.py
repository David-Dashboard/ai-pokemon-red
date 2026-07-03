#!/usr/bin/env python
"""tools/gate3d_baselines.py -- the FOUR free, no-LLM baselines for GATE-3D-A1 as re-pinned by
AMENDMENT A2 (reports/2026-07-04-vizdoom-3d-floor-design.md SS A2.1-A2.3): random policy, ATTACK-only,
TRUE multi-hot blind spinner (TURN_LEFT + ATTACK pressed on the same tic, every step -- A1.4's literal
decoy), and the alternating TURN_LEFT/ATTACK spinner (retained per A2.1 as a second spinner data
point; it was PR #75's original stand-in and remains real evidence). Each runs 200 episodes of
`scenarios/dtc_gate.cfg`, same action grain (tics=4 fixed) and the same 1000-tic / 250-step /
death-terminated episode budget the paid gate run uses, on fresh RNG seed blocks distinct from the 30
pinned gate seeds (eval/fixtures/gate3d_seeds.json: 1000-1029), from each other, AND from the
2026-07-03 A2-trigger run's blocks (20000-22199) -- the A2.3 re-run must not reuse any prior seed.

Multi-hot decoy path (SS A2.1, binding): "the baselines tool MAY drive raw vizdoom directly
(make_action with a multi-hot vector) -- decoys are scripted, no-LLM, and do not need the seam; the
seam's single-button tool surface is a constraint on the *brain*, not on adversarial baselines." The
multi-hot policy therefore calls `world.game.make_action(...)` (VizdoomWorld's owned DoomGame, a
public attribute) with a name-keyed multi-hot vector, then `world.screen()` to refresh the adapter's
guarded tic/state view -- core/vizdoom_world.py itself stays untouched (A2.4: "the multi-hot path
lives in the baselines tool, not the seam"). The three single-button policies keep going through
VizdoomWorld.step() exactly as in the A2-trigger run.

Ammo logging (SS A2.3, for KPS): every episode row now records `ammo2_first` (first readable AMMO2
after reset) and `ammo2_last` (last readable AMMO2 before the episode ended), plus an
`ammo2_increased` flag (any increase across consecutive readings -- dtc has no ammo pickups, so an
increase means something is wrong and the episode is excluded from the KPS sums, loudly). Per-policy
KPS = (sum of final KILLCOUNT) / (sum of shots) over non-excluded episodes, shots = ammo2_first -
ammo2_last per episode (SS A2.2's formula). NB on the exclusion: A2.2's letter says the offending
episode is "excluded from the shots sum"; it is excluded here from BOTH sums (kills and shots) --
excluding it from shots alone would leave its kills inflating KPS, which is the LOOSER direction and
cannot be what a stricter-only amendment means.

Must run inside the vizdoom-world Docker image (built from Dockerfile.vizdoom) -- vizdoom is not a
project dependency. See tools/run_gate3d_baselines.sh for the WSL/Docker driver.

Output: runs/gate3d_baselines/{random,attack_only,spinner_multihot,spinner_alternating}.jsonl + a
summary. eval/fixtures/gate3d_baselines.json (the scorer's committed source for D and KPS_spinner) is
written by hand from this tool's summary output -- this tool does not write into eval/fixtures itself,
keeping "which numbers are pre-registered law" a deliberate, reviewed commit rather than a script
side effect.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys

# Repo root on sys.path (mirrors tools/smoke_sweep.py) so this runs as `python tools/gate3d_baselines.py`
# from any cwd inside the container.
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

N_EPISODES = 200
MAX_TICS = 1000          # GATE-3D-A1 episode timeout (A1.3)
MAX_STEPS = 250           # 1000 tics / tics=4 per step
TICS_PER_STEP = 4         # pinned grain (A1.3/A1.4); mirrors core.vizdoom_world.TICS_PER_STEP
CFG_PATH = "scenarios/dtc_gate.cfg"
BUTTONS = ("TURN_LEFT", "TURN_RIGHT", "ATTACK")

# Fresh seed blocks for the A2.3 re-run: distinct from the 30 pinned gate seeds (1000-1029), from each
# other, and from the 2026-07-03 A2-trigger run's blocks (20000/21000/22000 + 200 each).
SEED_BLOCKS = {
    "random": 30000,
    "attack_only": 31000,
    "spinner_multihot": 32000,
    "spinner_alternating": 33000,
}


# ---------------------------------------------------------------------------
# Policies. A policy is `policy(step_idx) -> action`, where action is either a single button-name str
# (executed through VizdoomWorld.step, the seam-equivalent grain) or a TUPLE of button names (executed
# as one multi-hot make_action on the raw DoomGame, per SS A2.1 -- decoy-only path).
# ---------------------------------------------------------------------------

def _random_policy(seed: int):
    """Uniform over the 3 single-button actions each step. Seeded per-episode (from the SAME fresh
    seed the episode itself resets on) so the policy's own randomness is reproducible per episode."""
    rng = random.Random(seed)

    def policy(_step: int) -> str:
        return rng.choice(BUTTONS)
    return policy


def _attack_only_policy(_seed: int):
    def policy(_step: int) -> str:
        return "ATTACK"
    return policy


def _spinner_multihot_policy(_seed: int):
    """A1.4's literal blind spinner: TURN_LEFT + ATTACK pressed on the SAME tic, every step (SS A2.1's
    binding measurement correction). Returns a tuple -> the runner takes the raw-vizdoom multi-hot
    path for it."""
    def policy(_step: int) -> tuple:
        return ("TURN_LEFT", "ATTACK")
    return policy


def _spinner_alternating_policy(_seed: int):
    """PR #75's original weakened stand-in (alternating TURN_LEFT / ATTACK each step), RETAINED per
    SS A2.1 as a second spinner data point. It no longer stands in for the pinned decoy -- the
    multi-hot variant above is that -- but it stays in the measured D set (add-only clause)."""
    def policy(step: int) -> str:
        return "TURN_LEFT" if step % 2 == 0 else "ATTACK"
    return policy


# ---------------------------------------------------------------------------
# Episode runner (both action paths) + per-episode ammo tracking.
# ---------------------------------------------------------------------------

def _multihot_vector(world, button_names: tuple) -> list[int]:
    """Name-keyed multi-hot vector over the LIVE button order (the probe's order-sensitivity gotcha:
    never a hard-coded positional index). Built from world.game (VizdoomWorld's owned DoomGame, public
    attribute) -- no private-attribute reach-ins, no changes to core/vizdoom_world.py."""
    live = [str(b).rsplit(".", 1)[-1] for b in world.game.get_available_buttons()]
    vec = [0] * len(live)
    for name in button_names:
        vec[live.index(name)] = 1
    return vec


def _run_episode(world, seed: int, policy) -> dict:
    """Run one episode to completion (episode_finished) or MAX_STEPS, whichever first. Returns the
    final oracle-shaped record incl. ammo2_first/ammo2_last (SS A2.3's KPS inputs).

    VizdoomWorld.game_variables() returns None once is_episode_finished() is True (the adapter's own
    guard, core/vizdoom_world.py) -- calling it only ONCE after the loop exits would read None on
    every episode that ends by death/timeout rather than by hitting MAX_STEPS mid-episode (the
    common case for dtc: player death ends the episode on the SAME step that produced the terminal
    game state). So the last known non-None reading is snapshotted after every step, INSIDE the loop,
    while it is still available, and that snapshot is what gets reported as the episode's final state."""
    world.reset(seed=seed)
    step = 0
    mh_cache: dict[tuple, list[int]] = {}
    first_gv = world.game_variables()
    last_gv: dict = first_gv or {}
    ammo2_first = None if first_gv is None else first_gv.get("AMMO2")
    prev_ammo2 = ammo2_first
    ammo2_increased = False
    while step < MAX_STEPS and not world.episode_finished:
        action = policy(step)
        if isinstance(action, str):
            world.step(action, repeat=1)
        else:
            # SS A2.1 raw-vizdoom decoy path: one multi-hot make_action at the SAME pinned grain,
            # then a guarded adapter read (world.screen() -> _read_state) to refresh world.tic exactly
            # the way step() itself would.
            vec = mh_cache.get(action)
            if vec is None:
                vec = mh_cache[action] = _multihot_vector(world, action)
            world.game.make_action(vec, TICS_PER_STEP)
            world.screen()
        step += 1
        gv = world.game_variables()
        if gv is not None:
            last_gv = gv
            ammo2 = gv.get("AMMO2")
            if ammo2 is not None and prev_ammo2 is not None and ammo2 > prev_ammo2:
                ammo2_increased = True   # dtc has no ammo pickups -- this episode is KPS-excluded
            if ammo2 is not None:
                prev_ammo2 = ammo2
    return {
        "seed": seed, "steps": step, "tic": world.tic,
        "killcount": last_gv.get("KILLCOUNT"), "health": last_gv.get("HEALTH"),
        "ammo2": last_gv.get("AMMO2"),
        "ammo2_first": ammo2_first, "ammo2_last": last_gv.get("AMMO2"),
        "ammo2_increased": ammo2_increased,
        "episode_finished": world.episode_finished,
    }


# ---------------------------------------------------------------------------
# Per-policy summary: mean/std/distribution of final killcounts + KPS (SS A2.2's formula).
# ---------------------------------------------------------------------------

def summarize(name: str, records: list[dict]) -> dict:
    killcounts = [r["killcount"] for r in records if r["killcount"] is not None]
    n = len(killcounts)
    mean = sum(killcounts) / n if n else 0.0
    variance = sum((k - mean) ** 2 for k in killcounts) / n if n else 0.0
    std = variance ** 0.5
    dist: dict[str, int] = {}
    for k in killcounts:
        key = str(int(k))
        dist[key] = dist.get(key, 0) + 1

    # KPS = (sum final KILLCOUNT) / (sum shots), shots = ammo2_first - ammo2_last per episode
    # (SS A2.2). Episodes with an ammo2 increase (or unreadable ammo/killcount) are excluded from BOTH
    # sums (see module docstring) and counted loudly.
    total_kills = 0.0
    total_shots = 0.0
    excluded = 0
    for r in records:
        af, al, kc = r.get("ammo2_first"), r.get("ammo2_last"), r.get("killcount")
        if af is None or al is None or kc is None or r.get("ammo2_increased") or al > af:
            excluded += 1
            continue
        total_kills += kc
        total_shots += af - al
    kps = (total_kills / total_shots) if total_shots else None

    return {"policy": name, "n_episodes": n, "mean_killcount": mean, "std_killcount": std,
            "killcount_distribution": dist,
            "total_kills": total_kills, "total_shots": total_shots, "kps": kps,
            "kps_excluded_episodes": excluded}


def run_baseline(name: str, policy_factory, out_path: str, *, n_episodes: int = N_EPISODES) -> dict:
    from core.vizdoom_world import VizdoomWorld

    world = VizdoomWorld(CFG_PATH)
    seed_base = SEED_BLOCKS[name]
    records = []
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            for i in range(n_episodes):
                seed = seed_base + i
                policy = policy_factory(seed)
                rec = _run_episode(world, seed, policy)
                records.append(rec)
                f.write(json.dumps(rec) + "\n")
    finally:
        world.close()
    return summarize(name, records)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default="runs/gate3d_baselines")
    ap.add_argument("--episodes", type=int, default=N_EPISODES)
    ap.add_argument("--only", choices=sorted(SEED_BLOCKS), default=None,
                    help="run a single baseline (debug); default runs all four")
    args = ap.parse_args(argv)

    plan = {
        "random": (_random_policy, "random.jsonl"),
        "attack_only": (_attack_only_policy, "attack_only.jsonl"),
        "spinner_multihot": (_spinner_multihot_policy, "spinner_multihot.jsonl"),
        "spinner_alternating": (_spinner_alternating_policy, "spinner_alternating.jsonl"),
    }
    names = [args.only] if args.only else list(plan)

    summary = {}
    for name in names:
        factory, fname = plan[name]
        out_path = os.path.join(args.out_dir, fname)
        print(f"== running {name} ({args.episodes} episodes) ==", file=sys.stderr)
        result = run_baseline(name, factory, out_path, n_episodes=args.episodes)
        summary[name] = result
        print(json.dumps(result, indent=2))

    summary_path = os.path.join(args.out_dir, "summary.json")
    os.makedirs(args.out_dir, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nsummary written to {summary_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
