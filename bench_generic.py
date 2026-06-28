"""Batch perception benchmark: run play_generic.py across all GB/GBC ROMs in roms/.

For each ROM, captures: reached-gameplay, exploration progress, stall mode, crash.
Writes per-game logs under runs/bench_generic/<game>/bench.jsonl and a summary CSV.

  uv run python bench_generic.py
  uv run python bench_generic.py --steps 150 --warmup 40
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import traceback
import uuid

from core.brains import ExploreBrain, ScriptedBrain
from core.gateway import Gateway
from core.grid_perceiver import CameraScrollSignal, ForegroundSignal, GridPerceiver
from core.perception_plugin import PerceptionPlugin
from core.permissions import Allowlist
from core.runner import run_episode

_FOLLOW_KEYS = ("gold", "kirby", "metroid", "spaceinv", "f1race", "ffa", "sml")
_SANDBOX = Allowlist({"press_button", "press_sequence", "wait"})

# Known gameplay states (skip the warmup for these).
_KNOWN_STATES: dict[str, str] = {
    "cave noire": "runs/cn_open.state",
    "gauntlet ii": "runs/gauntlet_play.state",
}

# Games where the body-embodiment mismatches ExploreBrain's spatial assumptions
# (no avatar to move, or non-locomotion gameplay). Flagged for the ontology table.
_EMBODIMENT_MISMATCH = {"tetris", "space invaders", "mortal kombat", "f-1 race", "f1race"}


def _camera_class(rom_path: str) -> str:
    slug = os.path.basename(rom_path).lower()
    return "follow" if any(k in slug for k in _FOLLOW_KEYS) else "fixed"


def _find_state(slug_lower: str) -> str | None:
    for key, path in _KNOWN_STATES.items():
        if key in slug_lower and os.path.exists(path):
            return path
    return None


def _ontology_stage(game_slug: str, reached: bool, explored: int, stall: str) -> str:
    """Map failure mode to the perception ontology stage label."""
    sl = game_slug.lower()
    if any(k in sl for k in _EMBODIMENT_MISMATCH):
        return "S4 (embodiment mismatch)"
    if not reached:
        return "S2 (title/menu — can't reach gameplay)"
    if explored < 3:
        return "S2/S8 (stuck on menu it can't parse)"
    if "plateau" in stall or "frontier" in stall:
        if any(k in sl for k in _FOLLOW_KEYS):
            return "S3/S6 (follow-camera pose drift -> map warp)"
        return "S5 (affordance / dead-end — no frontiers)"
    if "wall" in stall or "no_move" in stall:
        return "S4/S5 (stuck at wall / collision)"
    if "crash" in stall:
        return "S0 (emulator crash)"
    return "S5 (exploration plateau)"


def _run_one(rom_path: str, steps: int, warmup_steps: int, out_root: str) -> dict:
    game_slug = os.path.splitext(os.path.basename(rom_path))[0]
    out_dir = os.path.join(out_root, game_slug)
    os.makedirs(out_dir, exist_ok=True)

    cam = _camera_class(rom_path)
    slug_lower = game_slug.lower()
    init_state = _find_state(slug_lower)
    effective_warmup = 0 if init_state else warmup_steps

    move_signal = ForegroundSignal() if cam == "fixed" else CameraScrollSignal()
    perceiver = GridPerceiver(move_signal=move_signal)

    result: dict = {
        "game": game_slug,
        "rom": rom_path,
        "camera": cam,
        "init_state": init_state,
        "steps_total": steps,
        "warmup": effective_warmup,
        "reached_gameplay": False,
        "cells_found": 0,
        "frontiers_max": 0,
        "contexts_seen": [],
        "consecutive_no_new": 0,
        "stall_mode": "unknown",
        "ontology": "",
        "crash": None,
        "explore_steps_taken": 0,
    }

    # Per-step accumulators for stall detection.
    contexts: list[str] = []
    poses: list[tuple] = []
    cells_over_time: list[int] = []

    def on_step_warmup(step, obs, result_tool, events):
        d = obs.data
        ctx = d.get("context", "unknown")
        contexts.append(ctx)
        if ctx == "gameplay":
            result["reached_gameplay"] = True

    try:
        plugin = PerceptionPlugin(
            rom_path=rom_path,
            out_dir=out_dir,
            headless=True,
            init_state=init_state,
            perceiver=perceiver,
        )
        gateway = Gateway(plugin, _SANDBOX)
        agent_id = f"agent-{uuid.uuid4()}"

        # Phase 1: warmup
        if effective_warmup > 0:
            warmup_brain = ScriptedBrain(agent_id, seed=0)
            run_episode(gateway, plugin, warmup_brain, agent_id,
                        max_steps=effective_warmup, on_step=on_step_warmup)

        if init_state:
            result["reached_gameplay"] = True  # state file = gameplay assumed

        # Phase 2: explore
        explore_brain = ExploreBrain(agent_id, single_step=True)
        explore_steps_taken = 0

        def on_explore(step, obs, result_tool, events):
            nonlocal explore_steps_taken
            explore_steps_taken += 1
            d = obs.data
            ctx = d.get("context", "unknown")
            contexts.append(ctx)
            if ctx == "gameplay":
                result["reached_gameplay"] = True
            sm = d.get("spatial_memory") or {}
            pose = (d.get("pose") or {}).get("value")
            cells = sm.get("visited", 0)
            fr = sm.get("frontiers") or []
            poses.append(tuple(pose) if pose else None)
            cells_over_time.append(cells)
            result["frontiers_max"] = max(result["frontiers_max"], len(fr))

        run_episode(gateway, plugin, explore_brain, agent_id,
                    max_steps=steps - effective_warmup, on_step=on_explore)

        result["explore_steps_taken"] = explore_steps_taken
        result["cells_found"] = cells_over_time[-1] if cells_over_time else 0
        result["contexts_seen"] = sorted(set(contexts))

        # Stall classification.
        stall = _classify_stall(cells_over_time, poses, contexts, slug_lower)
        result["stall_mode"] = stall
        result["ontology"] = _ontology_stage(game_slug, result["reached_gameplay"],
                                              result["cells_found"], stall)

        # Log
        plugin.close()
        _write_log(out_dir, result)

    except Exception as e:
        result["crash"] = str(e)
        result["stall_mode"] = "crash"
        result["ontology"] = _ontology_stage(game_slug, result["reached_gameplay"],
                                              result["cells_found"], "crash")
        tb = traceback.format_exc()
        try:
            with open(os.path.join(out_dir, "crash.txt"), "w") as f:
                f.write(tb)
        except Exception:
            pass
        try:
            plugin.close()
        except Exception:
            pass

    return result


def _classify_stall(cells_over_time: list[int], poses: list, contexts: list[str],
                    slug_lower: str) -> str:
    """Heuristic stall classifier from the step traces."""
    if any(k in slug_lower for k in _EMBODIMENT_MISMATCH):
        return "embodiment_mismatch"

    gameplay_steps = sum(1 for c in contexts if c == "gameplay")
    if gameplay_steps == 0:
        return "title_stuck"

    if not cells_over_time or cells_over_time[-1] == 0:
        return "no_gameplay_cells"

    # Did exploration plateau? Look at the last 30% of steps.
    n = len(cells_over_time)
    if n >= 10:
        tail = cells_over_time[int(n * 0.7):]
        if tail and (max(tail) - min(tail)) == 0:
            if cells_over_time[-1] <= 3:
                return "title_plateau_low_cells"
            return "frontier_plateau"

    # Consecutive stuck-at-same-pose?
    if len(poses) >= 8:
        last_poses = [p for p in poses[-10:] if p is not None]
        if last_poses and len(set(last_poses)) == 1:
            return "stuck_at_wall_no_move"

    # No cells and contexts are all static.
    all_static = all(c in ("static", "unknown") for c in contexts)
    if all_static:
        return "menu_only"

    return "explored_ok"


def _write_log(out_dir: str, result: dict) -> None:
    path = os.path.join(out_dir, "bench.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")


def _find_roms(roms_dir: str) -> list[str]:
    roms = []
    for fname in sorted(os.listdir(roms_dir)):
        if fname.lower().endswith((".gb", ".gbc")):
            roms.append(os.path.join(roms_dir, fname))
    return roms


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch perception benchmark across all GB/GBC ROMs.")
    ap.add_argument("--roms-dir", default="roms", help="Directory with .gb/.gbc files (not gba/nds subdirs).")
    ap.add_argument("--steps", type=int, default=150)
    ap.add_argument("--warmup", type=int, default=40)
    ap.add_argument("--out", default="runs/bench_generic")
    ap.add_argument("--rom", default=None, help="Run only this ROM (for debugging).")
    args = ap.parse_args()

    roms = _find_roms(args.roms_dir)
    if args.rom:
        roms = [r for r in roms if args.rom.lower() in r.lower()] or [args.rom]
    print(f"Benchmarking {len(roms)} ROMs -> {args.out}\n")

    all_results = []
    for i, rom in enumerate(roms, 1):
        slug = os.path.splitext(os.path.basename(rom))[0]
        print(f"[{i}/{len(roms)}] {slug} ...", flush=True)
        t0 = time.time()
        r = _run_one(rom, args.steps, args.warmup, args.out)
        elapsed = time.time() - t0
        r["elapsed_s"] = round(elapsed, 1)
        all_results.append(r)
        status = "CRASH" if r["crash"] else ("GAMEPLAY" if r["reached_gameplay"] else "TITLE")
        print(f"  -> {status}  cells={r['cells_found']}  stall={r['stall_mode']}  "
              f"ontology={r['ontology']}  [{elapsed:.1f}s]")

    # Write summary CSV.
    csv_path = os.path.join(args.out, "summary.csv")
    os.makedirs(args.out, exist_ok=True)
    fields = ["game", "camera", "reached_gameplay", "cells_found", "frontiers_max",
              "explore_steps_taken", "stall_mode", "ontology", "contexts_seen", "crash", "elapsed_s"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in all_results:
            row = dict(r)
            row["contexts_seen"] = "|".join(r.get("contexts_seen") or [])
            w.writerow(row)

    print(f"\nSummary written -> {csv_path}")

    # Print ranked failure-mode table.
    from collections import Counter
    stalls = Counter(r["stall_mode"] for r in all_results)
    onts = Counter(r["ontology"] for r in all_results)
    print("\n=== STALL MODE FREQUENCY ===")
    for mode, cnt in stalls.most_common():
        print(f"  {cnt:2d}  {mode}")
    print("\n=== ONTOLOGY STAGE FREQUENCY ===")
    for stage, cnt in onts.most_common():
        print(f"  {cnt:2d}  {stage}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
