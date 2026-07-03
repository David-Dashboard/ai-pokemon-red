#!/usr/bin/env python
"""eval/ceiling_gate3d.py -- GATE-3D scripted-optimum CEILING TEST (free, no LLM).

Purpose (HANDOFF.md top block, 2026-07-05 day-close): arm (a-1) of GATE-3D-A1-as-amended-by-A2
(reports/2026-07-04-vizdoom-3d-floor-design.md SS A2.2) requires the brain's mean final KILLCOUNT
K >= 5.61 (= max(D+1.5, 1.15*D), D=4.11 from the spinner_multihot decoy, eval/fixtures/gate3d_baselines.json).
The best paid brain run achieved K=4.074 (runs/brain_gate3d/run3_v_FAIL, per HANDOFF). Before spending
again on a paid re-run, this script asks: can a PERFECT policy even reach 5.61 under the exact same
episode constraints? If not, the bar is unreachable and must be re-pinned -- a design error to document,
not silently change (eval/score_gate3d.py, the seeds file, and the baselines file are NOT touched by
this script; the gate of record stays as-is).

This is a CEILING measurement, not a candidate agent: unlike the brain (and unlike core/vizdoom_world.py,
which this script does NOT import from, to keep the ceiling policy's privileged perception cleanly
out of the seam-facing adapter), this script reads ViZDoom's labels buffer directly -- server-side
ground truth about enemy screen position -- to find the nearest live enemy and its exact pixel azimuth.
Nothing here touches the agent wire (no world_mcp.py import, no MCP call); it measures the INSTRUMENT's
(the episode/action-space's) ceiling, not an agent's skill.

Episode physics matched EXACTLY to the pinned gate (reports/2026-07-04-vizdoom-3d-floor-design.md
AMENDMENT A1.3/A1.4 + AMENDMENT A2, core/vizdoom_world.py, scenarios/dtc_gate.cfg):
  - scenario:      scenarios/dtc_gate.cfg (defend_the_center.wad, stock wad resolved via
                   vizdoom.scenarios_path, same as core/vizdoom_world.py)
  - action set:    TURN_LEFT, TURN_RIGHT, ATTACK -- the SAME three actions the brain had (and the same
                   set tools/gate3d_baselines.py's decoys use). No MOVE_* : the brain never had it either.
  - action grain:  tics=4 fixed per action (core.vizdoom_world.TICS_PER_STEP), episode_timeout=1000
                   tics = 250 steps max, exactly the pinned budget (AMENDMENT A1.3/A2).
  - ammo budget:   dtc_gate.cfg ships AMMO2=26 (no pickups) -- the same 26-bullet budget named in the
                   task brief; the policy tracks it and can choose not to fire when no target is
                   centered (unlike the blind spinners, which fire every step regardless).
  - one attempt per seed, over the 30 PINNED gate seeds (eval/fixtures/gate3d_seeds.json, untouched).

Policy per step (privileged azimuth-seeker):
  1. Read the labels buffer; drop the DoomPlayer label; keep only labels still "alive" (dtc's
     defend_the_center wad only ever labels an enemy while it exists -- once killed, its label is
     simply absent from the next frame, confirmed live against the labels-buffer probe run for this
     script; the probe's label field dump and sign-check trace are committed as Table 1 in the
     report's appendix -- reports/2026-07-03-gate3d-ceiling-test.md -- covering the exact field
     names used here: `x`, `width`, `object_position_x/y`).
  2. Among remaining enemies, pick the NEAREST by Euclidean distance in world XY (object_position_x/y)
     to the player (player position is fixed at the arena center in dtc, confirmed (0,0) throughout).
  3. Compute that enemy's azimuth as a SCREEN-SPACE pixel offset: bbox_center_x - 160 (screen is
     RES_320X240, so screen-center-x = 160) -- the ANALOGOUS screen-x offset to the brief's ~25px
     tolerance, but measured on ViZDoom's ground-truth label centroid: same units, a DIFFERENT and
     noiseless instrument than the brief's P2 frame-diff centroid (noisy, null during turns), so the
     two "25px" values are not directly comparable -- see the report's Limitations section
     (reports/2026-07-03-gate3d-ceiling-test.md).
  4. If |offset| <= TOLERANCE_PX: fire (if ammo remains), else hold fire and turn toward the target
     (TURN_LEFT if the target is to the left of center i.e. offset < 0, else TURN_RIGHT -- verified
     against the live sign convention: TURN_LEFT increases ANGLE, which decreases a target's
     screen-space x for a target ahead-and-right, matching core/vizdoom_world.py's own P1 sign
     convention doc, reports/... AMENDMENT A1.2).
  5. If no enemy label is present: turn in a fixed scan direction (TURN_RIGHT) one step, to search --
     mirrors what the brain's own "no mover -> keep turning" fallback would have to do; costs no ammo.

Run ALL 30 pinned seeds, one attempt each, same 250-step / 1000-tic timeout as the gate. Reports, per
seed: kills (final KILLCOUNT) and shots (ammo2_first - ammo2_last, same formula as eval/score_gate3d.py
_brain_kps / tools/gate3d_baselines.py). Then: mean K, mean KPS, min/max, and the verdict line.

Two tolerance variants are both run and reported (the brief's exact 25px vs a swept best-tuned value)
so "bar unreachable" can be separated from "brain's aiming tolerance too loose": `--tolerances` accepts
a comma list of pixel tolerances to sweep; 25 is always included whether or not it is passed explicitly.

Must run inside the vizdoom-world Docker image (built from Dockerfile.vizdoom) -- vizdoom is not a
project dependency of this repo (mirrors tools/gate3d_baselines.py's Docker requirement exactly).

Usage (inside the vizdoom-world container, repo root mounted at /work):
    python eval/ceiling_gate3d.py --seeds-file eval/fixtures/gate3d_seeds.json \\
        --tolerances 25,12 --out eval/fixtures/gate3d_ceiling_results.json

Driver (from Windows/PowerShell or Git Bash, mirrors tools/run_gate3d_baselines.sh):
    docker run --rm -v "$PWD:/work" -w /work --entrypoint python vizdoom-world \\
        eval/ceiling_gate3d.py --tolerances 25,12
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

CFG_PATH = "scenarios/dtc_gate.cfg"
BUTTON_NAMES = ("TURN_LEFT", "TURN_RIGHT", "ATTACK")
GAME_VARIABLE_NAMES = ("HEALTH", "AMMO2", "KILLCOUNT")
TICS_PER_STEP = 4          # FIXED -- core.vizdoom_world.TICS_PER_STEP, the gate's pinned action grain.
MAX_TICS = 1000            # dtc_gate.cfg episode_timeout (AMENDMENT A1.3).
MAX_STEPS = 250            # 1000 tics / 4 tics-per-step.
SCREEN_WIDTH = 320
SCREEN_CENTER_X = SCREEN_WIDTH / 2.0   # 160.0
STARTING_AMMO = 26          # dtc_gate.cfg's pinned ammo budget (no pickups in this scenario).
DEFAULT_TOLERANCE_PX = 25   # the brief's exact tolerance to report as one of the two required numbers.


def _make_game(window_visible: bool = False):
    """Own DoomGame construction, matching core/vizdoom_world.py's VizdoomWorld.__init__ verbatim
    (same cfg, same button/variable set and order, same screen format/resolution) PLUS
    set_labels_buffer_enabled(True) -- the one privileged addition this ceiling script is allowed
    (task brief: "allowed to read ViZDoom's game state directly ... because this measures the
    INSTRUMENT's ceiling, not an agent"). Deliberately NOT importing core.vizdoom_world.VizdoomWorld
    itself, so this eval-only script owns its own game object end-to-end and never touches core/."""
    import vizdoom as vzd  # lazy, mirrors core/vizdoom_world.py's lazy-import discipline

    game = vzd.DoomGame()
    game.load_config(CFG_PATH)
    game.set_doom_scenario_path(os.path.join(vzd.scenarios_path, "defend_the_center.wad"))
    game.set_screen_format(vzd.ScreenFormat.RGB24)
    game.set_screen_resolution(vzd.ScreenResolution.RES_320X240)
    game.set_window_visible(window_visible)
    game.set_available_buttons([getattr(vzd.Button, n) for n in BUTTON_NAMES])
    game.set_available_game_variables([getattr(vzd.GameVariable, n) for n in GAME_VARIABLE_NAMES])
    game.set_labels_buffer_enabled(True)   # the privileged read: server-side enemy labels, oracle-only
    game.init()
    live_buttons = [str(b).rsplit(".", 1)[-1] for b in game.get_available_buttons()]
    button_index = {name: live_buttons.index(name) for name in BUTTON_NAMES}
    return game, button_index


def _action_vector(button_index: dict, button_name: str, n_buttons: int) -> list:
    vec = [0] * n_buttons
    vec[button_index[button_name]] = 1
    return vec


def _nearest_enemy(state, player_x: float, player_y: float):
    """Nearest live (non-player) label by Euclidean world-XY distance. Returns None if no enemy label
    is present this frame (all dead / not yet spawned into view -- dtc's label buffer simply omits a
    killed monster's label, confirmed live against the probe capture backing this script's report)."""
    best = None
    best_dist = None
    for lbl in (state.labels or []):
        if lbl.object_name == "DoomPlayer":
            continue
        dx = lbl.object_position_x - player_x
        dy = lbl.object_position_y - player_y
        dist = math.hypot(dx, dy)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = lbl
    return best


def _run_episode(game, button_index: dict, n_buttons: int, seed: int, tolerance_px: float) -> dict:
    """One episode, one seed, the ceiling policy. Returns a record shaped like
    tools/gate3d_baselines.py's per-episode rows (seed, steps, tic, killcount, ammo2_first/last, shots)
    so eval/score_gate3d.py's KPS formula can be reproduced identically by this report."""
    game.set_seed(int(seed))
    game.new_episode()
    step = 0

    def read_gv():
        if game.is_episode_finished():
            return None
        s = game.get_state()
        if s is None:
            return None
        gv = s.game_variables
        # order is HEALTH, AMMO2, KILLCOUNT per GAME_VARIABLE_NAMES / live var order (verified live,
        # identical to core/vizdoom_world.py's own _var_index-by-name construction).
        return {"HEALTH": float(gv[0]), "AMMO2": float(gv[1]), "KILLCOUNT": float(gv[2])}

    first_gv = read_gv()
    last_gv = first_gv or {}
    ammo2_first = None if first_gv is None else first_gv.get("AMMO2")
    # Shot accounting (review fix, PR #87). Two separate honest quantities, never conflated:
    #   * attack_decisions -- how many steps CHOSE the ATTACK action. At the pinned tics=4 grain this
    #     is 3-4x larger than bullets fired, because the pistol's refire cycle is ~14 tics: most
    #     4-tic ATTACK windows land mid-cycle and consume NO bullet. (The original field, named
    #     "shots_fired_counted", counted these decisions -- misleading, since it could exceed the
    #     26-round budget.)
    #   * bullets_fired -- actual rounds consumed, measured as the summed ammo2 decrease across ALL
    #     steps (not just ATTACK steps: the weapon state machine can consume the round on the tic
    #     AFTER a 4-tic ATTACK window ends, i.e. on the following turn step -- verified live during
    #     this fix round, where per-ATTACK-step-only attribution undercounted vs the episode ammo
    #     delta). Bounded by ammo2_first (26) by construction; equals ammo2_first - ammo2_last (the
    #     KPS formula's shot count, which was always ammo-delta-derived and is unaffected).
    attack_decisions = 0
    bullets_fired = 0
    prev_ammo = ammo2_first

    while step < MAX_STEPS and not game.is_episode_finished():
        state = game.get_state()
        if state is None:
            break
        target = _nearest_enemy(state, 0.0, 0.0)  # player is fixed at arena center in dtc (verified)
        gv_now = read_gv() or last_gv
        ammo_left = gv_now.get("AMMO2", 0.0)

        if target is None:
            # No enemy label visible this frame: scan by turning (costs no ammo). Mirrors the "no
            # mover -> keep turning" fallback any perceiver (brain or ceiling) must have with nothing
            # to aim at.
            action = "TURN_RIGHT"
        else:
            bbox_cx = target.x + target.width / 2.0
            offset_px = bbox_cx - SCREEN_CENTER_X
            if abs(offset_px) <= tolerance_px and ammo_left > 0:
                action = "ATTACK"
            elif abs(offset_px) <= tolerance_px:
                # centered but out of ammo: nothing useful to do: hold position (spend the fixed
                # tics=4 grain on a turn is arbitrary either way once ammo is gone -- keep facing it).
                action = "TURN_RIGHT"
            else:
                # TURN_LEFT increases ANGLE; a target with positive screen offset (right of center)
                # needs TURN_RIGHT to bring bbox_cx toward 160 -- verified against the live probe
                # capture backing this script (the trace is committed as Table 1 in the report's
                # appendix, reports/2026-07-03-gate3d-ceiling-test.md: sign checked over 77 tics of
                # continuous TURN_LEFT, zero wrong-sign steps).
                action = "TURN_RIGHT" if offset_px > 0 else "TURN_LEFT"

        if action == "ATTACK":
            attack_decisions += 1
        vec = _action_vector(button_index, action, n_buttons)
        game.make_action(vec, TICS_PER_STEP)
        step += 1
        gv = read_gv()
        if gv is not None:
            ammo_now = gv.get("AMMO2")
            if ammo_now is not None and prev_ammo is not None and ammo_now < prev_ammo:
                bullets_fired += int(prev_ammo - ammo_now)
            if ammo_now is not None:
                prev_ammo = ammo_now
            last_gv = gv

    ammo2_last = last_gv.get("AMMO2")
    ammo2_increased = (ammo2_first is not None and ammo2_last is not None and ammo2_last > ammo2_first)
    return {
        "seed": seed,
        "steps": step,
        "killcount": last_gv.get("KILLCOUNT"),
        "health": last_gv.get("HEALTH"),
        "ammo2_first": ammo2_first,
        "ammo2_last": ammo2_last,
        "ammo2_increased": ammo2_increased,
        # Two separate honest counts (see the accounting comment above): bullets_fired is actual
        # rounds consumed (ammo-delta-derived, bounded by the 26-round budget, cross-checks against
        # ammo2_first - ammo2_last); attack_decisions is how many steps chose ATTACK and CAN exceed
        # 26 -- it counts decisions, not effects (pistol refire cycle ~14 tics vs the 4-tic grain).
        "bullets_fired": bullets_fired,
        "attack_decisions": attack_decisions,
    }


def _shots_from_ammo(rec: dict) -> float:
    """Same formula eval/score_gate3d.py._brain_kps uses: shots = ammo2_first - ammo2_last, with any
    increase excluding the episode from the KPS sums (dtc has no ammo pickups -- an increase can only
    be a logging artifact)."""
    af, al = rec.get("ammo2_first"), rec.get("ammo2_last")
    if af is None or al is None or rec.get("ammo2_increased"):
        return None
    return af - al


def run_tolerance(seeds: list, tolerance_px: float) -> dict:
    game, button_index = _make_game()
    n_buttons = len(BUTTON_NAMES)
    try:
        records = []
        for seed in seeds:
            rec = _run_episode(game, button_index, n_buttons, seed, tolerance_px)
            records.append(rec)
    finally:
        game.close()

    killcounts = [r["killcount"] for r in records if r["killcount"] is not None]
    n = len(killcounts)
    mean_k = sum(killcounts) / n if n else 0.0
    min_k = min(killcounts) if killcounts else None
    max_k = max(killcounts) if killcounts else None

    total_kills = 0.0
    total_shots = 0.0
    excluded = 0
    for r in records:
        shots = _shots_from_ammo(r)
        kc = r.get("killcount")
        if shots is None or kc is None:
            excluded += 1
            continue
        total_kills += kc
        total_shots += shots
    kps = (total_kills / total_shots) if total_shots else None

    return {
        "tolerance_px": tolerance_px,
        "n_episodes": n,
        "mean_killcount": mean_k,
        "min_killcount": min_k,
        "max_killcount": max_k,
        "killcounts": killcounts,
        "mean_kps": kps,
        "total_kills": total_kills,
        "total_shots": total_shots,
        "kps_excluded_episodes": excluded,
        "records": records,
    }


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds-file", default="eval/fixtures/gate3d_seeds.json",
                    help="pinned 30-seed file (untouched; NOT edited by this script)")
    ap.add_argument("--tolerances", default=str(DEFAULT_TOLERANCE_PX),
                    help="comma-separated pixel tolerances to sweep (25 is always included)")
    ap.add_argument("--out", default="eval/fixtures/gate3d_ceiling_results.json",
                    help="where to write the raw per-seed / per-tolerance JSON")
    ap.add_argument("--gate-bar", type=float, default=5.61,
                    help="the pinned arm (a-1) bar to compare against (informational; scorer of record "
                         "is eval/score_gate3d.py, untouched)")
    args = ap.parse_args(argv)

    with open(args.seeds_file, encoding="utf-8") as f:
        seeds = [int(s) for s in json.load(f)]

    tolerances = sorted({int(t) for t in args.tolerances.split(",") if t.strip()} | {DEFAULT_TOLERANCE_PX})

    results = {}
    for tol in tolerances:
        print(f"== ceiling policy, tolerance={tol}px, {len(seeds)} seeds ==", file=sys.stderr)
        results[str(tol)] = run_tolerance(seeds, tol)
        r = results[str(tol)]
        print(f"   mean K={r['mean_killcount']:.3f}  mean KPS={r['mean_kps']:.4f}  "
              f"min/max={r['min_killcount']}/{r['max_killcount']}", file=sys.stderr)

    best_tol = max(tolerances, key=lambda t: results[str(t)]["mean_killcount"])
    out = {
        "gate_bar": args.gate_bar,
        "n_pinned_seeds": len(seeds),
        "tolerances_swept": tolerances,
        "default_tolerance_px": DEFAULT_TOLERANCE_PX,
        "best_tolerance_px": best_tol,
        "by_tolerance": results,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    default_r = results[str(DEFAULT_TOLERANCE_PX)]
    best_r = results[str(best_tol)]
    print("\n=== GATE-3D scripted-optimum ceiling test ===")
    print(f"pinned gate bar (arm a-1): K >= {args.gate_bar}")
    print(f"25px tolerance (brief default): mean K={default_r['mean_killcount']:.3f}  "
          f"mean KPS={default_r['mean_kps']:.4f}")
    print(f"best-tuned tolerance ({best_tol}px): mean K={best_r['mean_killcount']:.3f}  "
          f"mean KPS={best_r['mean_kps']:.4f}")
    reachable = best_r["mean_killcount"] >= args.gate_bar
    print(f"\nVERDICT: is K >= {args.gate_bar} reachable by a perfect azimuth-seeker? "
          f"{'YES' if reachable else 'NO'} (best K={best_r['mean_killcount']:.3f})")
    print(f"\nraw results written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
