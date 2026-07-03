#!/usr/bin/env python
"""tools/gate3d_baselines.py -- the three FREE, no-LLM baselines for GATE-3D-A1
(reports/2026-07-04-vizdoom-3d-floor-design.md AMENDMENT A1 SS A1.4): random policy, blind spinner,
ATTACK-only. Each runs 200 episodes of `scenarios/dtc_gate.cfg` directly against
core.vizdoom_world.VizdoomWorld (no MCP seam, no LLM -- these are scripted policies), same action grain
(tics=4 fixed) and the same 1000-tic / 250-step / death-terminated episode budget the paid gate run
uses, on fresh RNG seeds DISTINCT from the 30 pinned gate seeds (eval/fixtures/gate3d_seeds.json uses
1000-1029; this tool uses 20000+i, comfortably clear of that range and of each other baseline's range).

Must run inside the vizdoom-world Docker image (built from Dockerfile.vizdoom) -- vizdoom is not a
project dependency. See tools/run_gate3d_baselines.sh for the WSL/Docker driver.

DECOY DEVIATION (flagged per the brief, A1.4's blind-spinner definition): A1.4 pins the blind spinner
as "TURN_LEFT + ATTACK every step" -- a MULTI-HOT action. core.vizdoom_world.VizdoomWorld.step() takes
a single button name (see its docstring: "must be one of BUTTON_NAMES") -- the adapter has no multi-hot
entry point. This tool implements the decoy as ALTERNATING TURN_LEFT / ATTACK each step instead, and
this deviation is called out in the PR body per the brief's instruction ("document the deviation ...
for a stricter-only judgment call") rather than silently reinterpreting the pinned spec or reaching
into VizdoomWorld's internals to fake a multi-hot vector.

Output: runs/gate3d_baselines/{random,spinner,attack_only}.jsonl (one row per episode: seed, steps,
final tic, final killcount) + a summary printed to stdout. eval/fixtures/gate3d_baselines.json (the
scorer's committed R source) is written by hand from this tool's summary output -- this tool does not
write into eval/fixtures itself, keeping "which numbers are pre-registered law" a deliberate, reviewed
commit rather than a script side effect.
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
CFG_PATH = "scenarios/dtc_gate.cfg"
BUTTONS = ("TURN_LEFT", "TURN_RIGHT", "ATTACK")

# Fresh seeds, distinct from the 30 pinned gate seeds (eval/fixtures/gate3d_seeds.json: 1000-1029) and
# from each other baseline's block, so no baseline run can share a seed with the paid run or with
# another baseline.
SEED_BLOCKS = {"random": 20000, "spinner": 21000, "attack_only": 22000}


def _run_episode(world, seed: int, policy) -> dict:
    """Run one episode to completion (episode_finished) or MAX_STEPS, whichever first. `policy(step_idx)
    -> button_name` picks the action for each step. Returns the final oracle-shaped record.

    VizdoomWorld.game_variables() returns None once is_episode_finished() is True (the adapter's own
    guard, core/vizdoom_world.py) -- calling it only ONCE after the loop exits would read None on
    every episode that ends by death/timeout rather than the brain hitting MAX_STEPS mid-episode (the
    common case for dtc: player death ends the episode on the SAME step that produced the terminal
    game state). So the last known non-None reading is snapshotted after every step, INSIDE the loop,
    while it is still available, and that snapshot is what gets reported as the episode's final state."""
    world.reset(seed=seed)
    step = 0
    last_gv: dict = {}
    while step < MAX_STEPS and not world.episode_finished:
        button = policy(step)
        world.step(button, repeat=1)
        step += 1
        gv = world.game_variables()
        if gv is not None:
            last_gv = gv
    return {
        "seed": seed, "steps": step, "tic": world.tic,
        "killcount": last_gv.get("KILLCOUNT"), "health": last_gv.get("HEALTH"),
        "ammo2": last_gv.get("AMMO2"), "episode_finished": world.episode_finished,
    }


def _random_policy(seed: int):
    """Uniform over the 3 single-button actions each step. Seeded per-episode (from the SAME fresh
    seed the episode itself resets on) so the policy's own randomness is reproducible per episode."""
    rng = random.Random(seed)

    def policy(_step: int) -> str:
        return rng.choice(BUTTONS)
    return policy


def _spinner_policy(_seed: int):
    """DEVIATION from A1.4's literal "TURN_LEFT + ATTACK every step" (multi-hot) -- see module
    docstring. Alternates TURN_LEFT / ATTACK each step; both actions run every other step, same as the
    pinned decoy's intent (turn while shooting) within this adapter's single-button action surface."""
    def policy(step: int) -> str:
        return "TURN_LEFT" if step % 2 == 0 else "ATTACK"
    return policy


def _attack_only_policy(_seed: int):
    def policy(_step: int) -> str:
        return "ATTACK"
    return policy


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

    killcounts = [r["killcount"] for r in records if r["killcount"] is not None]
    n = len(killcounts)
    mean = sum(killcounts) / n if n else 0.0
    variance = sum((k - mean) ** 2 for k in killcounts) / n if n else 0.0
    std = variance ** 0.5
    dist: dict[str, int] = {}
    for k in killcounts:
        key = str(int(k))
        dist[key] = dist.get(key, 0) + 1
    return {"policy": name, "n_episodes": n, "mean_killcount": mean, "std_killcount": std,
            "killcount_distribution": dist}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default="runs/gate3d_baselines")
    ap.add_argument("--episodes", type=int, default=N_EPISODES)
    ap.add_argument("--only", choices=["random", "spinner", "attack_only"], default=None,
                    help="run a single baseline (debug); default runs all three")
    args = ap.parse_args(argv)

    plan = {
        "random": (_random_policy, "random.jsonl"),
        "spinner": (_spinner_policy, "spinner.jsonl"),
        "attack_only": (_attack_only_policy, "attack_only.jsonl"),
    }
    names = [args.only] if args.only else ["random", "spinner", "attack_only"]

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
