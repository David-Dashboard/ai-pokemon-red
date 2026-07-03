"""eval/score_a3_precheck.py -- GATE-3D-A3-PC: the binding offline pre-check pinned by
reports/2026-07-05-p1-clutter-redesign.md S3.1, before PR-H wires the redesigned P1 into any live seam
and before any paid run is scheduled.

Two pieces, both implemented here:

  1. The A3 SCORER (`arm_b_a3`, `run_positions`) -- the pinned onset rule applied to a grounding-shaped
     row list: a commanded-turn row is a SCORED turn step only if `run_pos >= 2` (run_pos counts from 0
     at the first row of a maximal run of consecutive same-direction turn commands; a run is broken by
     any non-turn action, any direction change, or an episode boundary). This reproduces the design
     doc's own numbers when run directly on run3's grounding.jsonl (S1.5/S3.1): raw sign_agreement
     0.7741 (956 scored / 1483 turn rows), onset-excluded sign_agreement 0.8559 (708 scored) -- see
     `tests/test_score_a3_precheck.py` for the regression pin.

  2. The REPLAY DRIVER (`main`) -- run3's raw per-tic PNGs were never retained (`--keep-frames` was not
     on for that run; `runs/brain_gate3d/run3_v_FAIL/world/` holds only grounding.jsonl/oracle.jsonl, no
     frames), so grounding.jsonl's OWN commanded-turn sequence cannot be re-scored with a different P1
     directly -- there are no raw frame pairs behind those rows to hand to a new estimator. Per the
     redesign doc's own contingency ("reconstructing frame pairs from a fresh instrumented replay of the
     same 27 episodes' seeds ... one free re-run of dtc_gate.cfg under the pinned seeds with frame
     capture enabled"), this module instead re-runs `scenarios/dtc_gate.cfg` under the 30 PINNED SEEDS
     (eval/fixtures/gate3d_seeds.json, the same seeds run3 used) with a scripted, no-LLM, turn-heavy
     policy (mirrors tools/gate3d_baselines.py's direct-VizdoomWorld pattern -- free, Docker CPU only),
     and computes OLD-P1 (single-band) and NEW-P1 (multi-band, core.yaw_flow.DEFAULT_BANDS) SIDE BY SIDE
     on IDENTICAL frame pairs, per action sub-step, exactly mirroring world_mcp.py::DoomDtcSession's own
     per-substep P1 computation (prev_gray/cur_gray rolled forward one sub-step at a time -- the same
     pairing invariant PR #73 established). This is not literally "replaying run3's sequence" (that
     sequence's frames don't exist to replay), but it IS the same scenario/seeds/action-grain producing
     a fresh, comparable commanded-turn stream scored under the same pinned onset rule -- the closest
     free substitute the retained data allows, documented here rather than silently assumed.

  Both numbers (with/without the onset exclusion) are reported for BOTH P1 versions, per S3.1's
  "BOTH numbers are reported" binding clause -- 4 numbers total, so the improvement attribution stays
  visible per-mechanism (mechanism 1 = the scoring rule; mechanism 2 = the estimator redesign).

Must run inside the vizdoom-world Docker image (built from Dockerfile.vizdoom) for `main` (vizdoom is
not a project dependency); the scorer functions themselves (`arm_b_a3`, `run_positions`) are pure stdlib
and importable/testable anywhere, same split as eval/score_gate3d.py vs tools/gate3d_baselines.py.

Usage (scoring an existing grounding.jsonl, e.g. run3's own, for the onset-rule numbers only):
    uv run python -m eval.score_a3_precheck --score-only \\
        runs/brain_gate3d/run3_v_FAIL/world/grounding.jsonl

Usage (the full free replay + side-by-side old-P1/new-P1 A3-PC table):
    uv run python -m eval.score_a3_precheck --replay \\
        --seeds-file eval/fixtures/gate3d_seeds.json --out runs/a3_precheck
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Repo root on sys.path (mirrors tools/gate3d_baselines.py) so this runs as `python -m eval.score_a3_precheck`.
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

# Pinned bars, copied verbatim from eval/score_gate3d.py (ARM (b)'s numeric bars, unchanged by A3 --
# only the scored-step DEFINITION changes, per S3.1).
ARM_B_SIGN_AGREEMENT_MIN = 0.90
ARM_B_MIN_TURN_STEPS = 20
ARM_B_NONE_RATE_MAX = 0.50

ONSET_EXCLUDE_RUN_POS = 1   # rows with run_pos <= this are excluded (S3.1 pinned; NOT widenable)

MAX_STEPS = 250             # 1000 tics / tics=4 per step (mirrors gate3d_baselines.py / A1.3)
CFG_PATH = "scenarios/dtc_gate.cfg"


# ---------------------------------------------------------------------------
# Part 1: the A3 onset-rule scorer -- pure stdlib, works on any grounding-shaped row list.
# ---------------------------------------------------------------------------

def run_positions(grounding: list[dict]) -> list[int]:
    """For each row (in the given order, which MUST already be sorted by (episode, step) -- both this
    module's replay writer and world_mcp.py's _log_grounding emit rows in that order), return its
    `run_pos`: 0 at the first row of a maximal run of consecutive same-direction TURN commands, else
    incrementing while the SAME episode keeps commanding the SAME direction. -1 for non-turn rows
    (commanded not in {"left","right"}) -- they never enter ARM (b)'s scoring set at all (unchanged
    from GATE-3D-A1/A2) and run_pos is meaningless for them; -1 is a sentinel, not a scorable position.

    A run is broken by (S3.1 verbatim): any non-turn action (commanded == null), any direction change,
    or an episode boundary -- all three collapse to the same check here: the previous SCORABLE row's
    (episode, commanded) no longer matches this row's.
    """
    out: list[int] = []
    prev_key: tuple | None = None   # (episode, commanded) of the immediately-preceding TURN row
    pos = -1
    for r in grounding:
        cmd = r.get("commanded")
        if cmd not in ("left", "right"):
            out.append(-1)
            prev_key = None   # ATTACK (or any non-turn row) breaks the run outright
            continue
        key = (r.get("episode"), cmd)
        pos = 0 if key != prev_key else pos + 1
        out.append(pos)
        prev_key = key
    return out


def arm_b_a3(grounding: list[dict], *, exclude_onset: bool) -> dict:
    """ARM (b)-analog scoring under GATE-3D-A3 (S3.1). When `exclude_onset` is True, rows with
    run_pos <= ONSET_EXCLUDE_RUN_POS are dropped from BOTH the sign-agreement and the None-rate
    computation (S3.1: "excluded ... AND from the None-rate computation"), before the
    >= ARM_B_MIN_TURN_STEPS minimum is applied (S3.1: "the minimum applies AFTER this exclusion -- no
    vacuous pass"). When False, this reproduces eval/score_gate3d.py::_arm_b's raw numbers exactly
    (mechanism-1-unfixed baseline)."""
    run_pos = run_positions(grounding)
    turns = [(r, rp) for r, rp in zip(grounding, run_pos) if rp >= 0]
    if exclude_onset:
        turns = [(r, rp) for r, rp in turns if rp > ONSET_EXCLUDE_RUN_POS]

    n_turns = len(turns)
    scored = [r for r, _ in turns if r.get("direction") is not None]
    n_scored = len(scored)
    n_agree = sum(1 for r in scored if r["direction"] == r["commanded"])
    sign_agreement = (n_agree / n_scored) if n_scored else 0.0
    none_rate = (1 - n_scored / n_turns) if n_turns else 1.0

    enough_steps = n_scored >= ARM_B_MIN_TURN_STEPS
    passed = (enough_steps
              and sign_agreement >= ARM_B_SIGN_AGREEMENT_MIN
              and none_rate <= ARM_B_NONE_RATE_MAX)
    return {
        "exclude_onset": exclude_onset,
        "n_turn_steps": n_turns, "n_scored_turn_steps": n_scored,
        "sign_agreement": sign_agreement, "none_rate": none_rate,
        "enough_steps": enough_steps, "passed": passed,
    }


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_seeds(path: str) -> list[int]:
    with open(path, encoding="utf-8") as f:
        return [int(s) for s in json.load(f)]


# ---------------------------------------------------------------------------
# Part 2: the free replay -- old-P1 vs new-P1 computed side by side on IDENTICAL frame pairs.
# ---------------------------------------------------------------------------

def _turn_heavy_policy(rng):
    """Scripted, no-LLM policy for the replay (there is no brain here -- see module docstring: run3's
    frames don't exist to replay, so this generates a FRESH commanded-turn stream on the same
    scenario/seeds/grain). Deliberately turn-heavy with HELD turns (a run of several same-direction
    turns before switching), rather than the baselines' alternating/random shape, so the replay
    exercises run_pos across a real range (0, 1, 2, 3+) the way an actual playing policy does --
    a policy that never holds a turn past run_pos=1 could not populate the "safe" positions at all."""
    turn_left = rng.random() < 0.5
    hold = rng.randint(3, 8)   # a held run of 3-7 consecutive same-direction turns

    def policy(step: int):
        cycle = step % (hold + 2)   # `hold` turn steps, then 2 ATTACK steps, then flip direction
        nonlocal turn_left
        if cycle == 0 and step > 0:
            turn_left = not turn_left
        if cycle < hold:
            return "TURN_LEFT" if turn_left else "TURN_RIGHT"
        return "ATTACK"
    return policy


def _run_episode_dual_p1(world, seed: int, episode_idx: int, policy_factory, ncc_floor, prom_floor):
    """Run one episode, computing OLD-P1 (single-band) and NEW-P1 (multi-band) on the SAME frame pair
    per action sub-step -- mirrors world_mcp.py::DoomDtcSession._do_action's per-substep grain
    (prev_gray/cur_gray rolled forward one sub-step at a time, never a multi-substep batch). Returns two
    grounding-shaped row lists (old, new), aligned 1:1 by (episode, step)."""
    from core.yaw_flow import DEFAULT_BANDS, yaw_band_flow

    import numpy as np

    def to_gray(screen):
        return np.asarray(screen)[..., :3].mean(axis=2).astype(np.float32)

    rng = __import__("random").Random(seed)
    policy = policy_factory(rng)

    result = world.reset(seed=seed)
    prev_gray = to_gray(result.screen) if result.screen is not None else None
    old_rows, new_rows = [], []
    step = 0
    while step < MAX_STEPS and not world.episode_finished:
        action = policy(step)
        commanded = "left" if action == "TURN_LEFT" else ("right" if action == "TURN_RIGHT" else None)
        result = world.step(action, repeat=1)
        step += 1
        cur_gray = to_gray(result.screen) if result.screen is not None else None
        if prev_gray is not None and cur_gray is not None:
            old_reading = yaw_band_flow(prev_gray, cur_gray, ncc_floor=ncc_floor, prom_floor=prom_floor)
            new_reading = yaw_band_flow(prev_gray, cur_gray, ncc_floor=ncc_floor, prom_floor=prom_floor,
                                         bands=DEFAULT_BANDS)
            old_rows.append({"episode": episode_idx, "seed": seed, "step": step, "tic": world.tic,
                             "commanded": commanded, "direction": old_reading.direction,
                             "dx_px": old_reading.dx_px, "confidence": old_reading.confidence})
            new_rows.append({"episode": episode_idx, "seed": seed, "step": step, "tic": world.tic,
                             "commanded": commanded, "direction": new_reading.direction,
                             "dx_px": new_reading.dx_px, "confidence": new_reading.confidence})
        prev_gray = cur_gray
    return old_rows, new_rows


def run_replay(seeds: list[int], *, ncc_floor: float = 0.2, prom_floor: float = 0.02) -> tuple[list[dict], list[dict]]:
    """Runs all `seeds` episodes through scenarios/dtc_gate.cfg (the pinned scenario), returning
    (old_p1_grounding, new_p1_grounding) -- two full grounding-shaped row lists, aligned 1:1."""
    from core.vizdoom_world import VizdoomWorld

    world = VizdoomWorld(CFG_PATH)
    old_all: list[dict] = []
    new_all: list[dict] = []
    try:
        for ep_idx, seed in enumerate(seeds):
            old_rows, new_rows = _run_episode_dual_p1(world, seed, ep_idx, _turn_heavy_policy,
                                                       ncc_floor, prom_floor)
            old_all.extend(old_rows)
            new_all.extend(new_rows)
    finally:
        world.close()
    return old_all, new_all


def format_precheck_table(old_raw: dict, old_excl: dict, new_raw: dict, new_excl: dict) -> str:
    lines = ["=== GATE-3D-A3-PC (offline pre-check, reports/2026-07-05-p1-clutter-redesign.md S3.1) ===", ""]
    lines.append(f"{'':22} {'sign_agreement':>15} {'none_rate':>10} {'n_scored':>9}  verdict")
    for label, d in (("old-P1  (raw)", old_raw), ("old-P1  (onset excl.)", old_excl),
                     ("new-P1  (raw)", new_raw), ("new-P1  (onset excl.)", new_excl)):
        verdict = "PASS" if d["passed"] else "FAIL"
        lines.append(f"{label:22} {d['sign_agreement']:>15.4f} {d['none_rate']:>10.4f} "
                     f"{d['n_scored_turn_steps']:>9}  {verdict}")
    lines.append("")
    a3pc_pass = new_excl["passed"]
    lines.append(f"A3-PC bar: sign_agreement >= {ARM_B_SIGN_AGREEMENT_MIN}, none_rate <= "
                 f"{ARM_B_NONE_RATE_MAX}, n_scored >= {ARM_B_MIN_TURN_STEPS} (new-P1, onset rule applied)")
    lines.append(f"GATE-3D-A3-PC: {'PASS' if a3pc_pass else 'FAIL'}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_mutually_exclusive_group(required=True)
    sub.add_argument("--score-only", metavar="GROUNDING_JSONL",
                     help="score an existing grounding.jsonl under the A3 onset rule (both numbers); "
                          "no ViZDoom/replay involved.")
    sub.add_argument("--replay", action="store_true",
                     help="run the free headless replay (scenarios/dtc_gate.cfg, pinned seeds) "
                          "and print the full old-P1 vs new-P1 4-number table. Requires vizdoom.")
    ap.add_argument("--seeds-file", default="eval/fixtures/gate3d_seeds.json")
    ap.add_argument("--out", default="runs/a3_precheck", help="--replay only: where to write the "
                    "old_p1_grounding.jsonl / new_p1_grounding.jsonl replay logs")
    args = ap.parse_args(argv)

    if args.score_only:
        grounding = load_jsonl(args.score_only)
        raw = arm_b_a3(grounding, exclude_onset=False)
        excl = arm_b_a3(grounding, exclude_onset=True)
        print(f"raw:     sign_agreement={raw['sign_agreement']:.4f}  none_rate={raw['none_rate']:.4f}  "
              f"n_scored={raw['n_scored_turn_steps']}  passed={raw['passed']}")
        print(f"excl:    sign_agreement={excl['sign_agreement']:.4f}  none_rate={excl['none_rate']:.4f}  "
              f"n_scored={excl['n_scored_turn_steps']}  passed={excl['passed']}")
        return 0

    seeds = load_seeds(args.seeds_file)
    print(f"== GATE-3D-A3-PC replay: {len(seeds)} pinned seeds, {CFG_PATH} ==", file=sys.stderr)
    old_all, new_all = run_replay(seeds)

    os.makedirs(args.out, exist_ok=True)
    old_path = os.path.join(args.out, "old_p1_grounding.jsonl")
    new_path = os.path.join(args.out, "new_p1_grounding.jsonl")
    with open(old_path, "w", encoding="utf-8") as f:
        for r in old_all:
            f.write(json.dumps(r) + "\n")
    with open(new_path, "w", encoding="utf-8") as f:
        for r in new_all:
            f.write(json.dumps(r) + "\n")

    old_raw = arm_b_a3(old_all, exclude_onset=False)
    old_excl = arm_b_a3(old_all, exclude_onset=True)
    new_raw = arm_b_a3(new_all, exclude_onset=False)
    new_excl = arm_b_a3(new_all, exclude_onset=True)

    report = format_precheck_table(old_raw, old_excl, new_raw, new_excl)
    print(report)
    report_path = os.path.join(args.out, "A3_PRECHECK_REPORT.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print(f"\nreplay logs + report written to {args.out}/", file=sys.stderr)
    return 0 if new_excl["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
