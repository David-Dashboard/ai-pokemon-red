"""Run the NDS perception stack on a single ROM — thin driver mirroring play_gauntlet.py.

Wires DeSmuMEEmulator → NDSPerceiver → NDSPerceptionPlugin (includes touch tool) → ScriptedBrain/ExploreBrain.
For the multi-ROM bench harness + ontology report, see eval/nds_bench.py.

Example usage:
    python play_nds.py play --rom "roms/nds/New Super Mario Bros. (USA).nds" --steps 150
    python play_nds.py bench --roms-dir roms/nds --steps 150   # delegates to eval/nds_bench
"""
from __future__ import annotations

import argparse
import json
import os
import uuid

from core.brains import ExploreBrain, ScriptedBrain
from core.gateway import Gateway
from core.nds_emulator import DeSmuMEEmulator
from core.nds_perceiver import NDSPerceiver
from core.nds_perception_plugin import NDSPerceptionPlugin
from core.permissions import Allowlist
from core.runner import run_episode
from core.screen_role import _mean_diff  # noqa: reuse canonical mean-abs-diff in render check

NDS_SANDBOX = Allowlist({"press_button", "press_sequence", "wait", "touch"})

_NDS_BUTTON_DESC = (
    "Press one NDS button (a, b, x, y, l, r, start, select, up, down, left, right). "
    "D-pad moves the character; A/B act; START/SELECT open menus."
)
_NDS_SEQUENCE_DESC = (
    "Press several NDS buttons in order — efficient for multi-step movement. "
    "Supply a list of button strings."
)
_NDS_RENDER_HEADER = "NDS spatial gameplay. Perception is approximate (256×192 grid). Screenshot attached."


def run_one(rom_path: str, label: str, steps: int, out_dir: str,
            expected_screen: str | None = None, verbose: bool = True) -> dict:
    """Run one NDS ROM for `steps` steps. Returns an instrument dict (JSON-serialisable)."""
    import numpy as np
    from eval.nds_bench import classify_ontology, _WARMUP_STEPS, _EXPLORE_STEPS

    result: dict = {"label": label, "rom": os.path.basename(rom_path), "renders": False,
                    "error": None, "discovery": {}, "spatial": {}, "per_screen": {}, "ontology": {}}
    agent_id = f"agent-nds-{uuid.uuid4().hex[:8]}"
    perceiver = NDSPerceiver()

    try:
        emu = DeSmuMEEmulator(rom_path, headless=True)
    except Exception as e:
        result["error"] = f"emulator-init: {e}"
        result["ontology"] = {"stage": "S1-substrate", "note": "emulator failed to open ROM"}
        if verbose:
            print(f"  [{label}] EMULATOR ERROR: {e}")
        return result

    try:
        plugin = NDSPerceptionPlugin(
            emulator=emu, out_dir=os.path.join(out_dir, label.replace(" ", "_").lower()),
            perceiver=perceiver, button_desc=_NDS_BUTTON_DESC,
            sequence_desc=_NDS_SEQUENCE_DESC, render_header=_NDS_RENDER_HEADER,
        )
    except Exception as e:
        result["error"] = f"plugin-init: {e}"
        emu.close()
        return result

    try:
        f0 = emu.screen_ndarray()
        emu.tick(30)
        f1 = emu.screen_ndarray()
        emu.tick(30)
        f2 = emu.screen_ndarray()
        d01 = _mean_diff(f0.astype(np.float32), f1.astype(np.float32))
        d12 = _mean_diff(f1.astype(np.float32), f2.astype(np.float32))
        renders = (d01 > 0.5) or (d12 > 0.5)
        result["renders"] = renders
        result["per_screen"]["render_diff_mean"] = round((d01 + d12) / 2, 3)
        result["per_screen"]["top_diff"] = round(float(np.abs(f1[:192].astype(np.float32) - f0[:192].astype(np.float32)).mean()), 3)
        result["per_screen"]["bot_diff"] = round(float(np.abs(f1[192:].astype(np.float32) - f0[192:].astype(np.float32)).mean()), 3)
        if not renders:
            result["error"] = "frozen/blank — frame unchanged over 60 cycles"
            result["ontology"] = {"stage": "S1-substrate", "note": "ROM did not render (frozen or blank)"}
            if verbose:
                print(f"  [{label}] FROZEN — skipping")
            plugin.close()
            return result
        if verbose:
            print(f"  [{label}] renders OK (diff={d01:.1f})")
    except Exception as e:
        result["error"] = f"render-check: {e}"
        plugin.close()
        return result

    discovery_snapshots: list[dict] = []
    spatial_snapshots: list[dict] = []
    discovery_commit_step = None

    def on_warmup_step(step, obs, res, events):
        nonlocal discovery_commit_step
        role = perceiver.last_role
        sm = (obs.data.get("spatial_memory") or {})
        discovery_snapshots.append({"step": step, "gameplay": role.get("gameplay"), "conf": role.get("confidence", 0.0)})
        spatial_snapshots.append({"step": step, "visited": sm.get("visited", 0),
                                  "frontiers": len(sm.get("frontiers") or []),
                                  "pose": (obs.data.get("pose") or {}).get("value"),
                                  "ego_motion": sm.get("ego_motion")})
        if discovery_commit_step is None and role.get("gameplay") is not None:
            discovery_commit_step = step
        if verbose and step % 30 == 0:
            print(f"    [{label}] warmup step {step:3d}  role={role.get('gameplay')} conf={role.get('confidence', 0):.2f}  "
                  f"visited={sm.get('visited', 0)}  frontiers={len(sm.get('frontiers') or [])}")

    try:
        run_episode(Gateway(plugin, NDS_SANDBOX), plugin, ScriptedBrain(agent_id, seed=42), agent_id,
                    max_steps=_WARMUP_STEPS, on_step=on_warmup_step)
    except Exception as e:
        result["error"] = f"warmup-run: {e}"
        plugin.close()
        return result

    explore_snapshots: list[dict] = []

    def on_explore_step(step, obs, res, events):
        role = perceiver.last_role
        sm = (obs.data.get("spatial_memory") or {})
        explore_snapshots.append({"step": step, "visited": sm.get("visited", 0),
                                  "frontiers": len(sm.get("frontiers") or []),
                                  "pose": (obs.data.get("pose") or {}).get("value"),
                                  "ego_motion": sm.get("ego_motion"), "conf": role.get("confidence", 0.0)})
        if verbose and step % 30 == 0:
            print(f"    [{label}] explore step {step:3d}  role={role.get('gameplay')} conf={role.get('confidence', 0):.2f}  "
                  f"visited={sm.get('visited', 0)}  frontiers={len(sm.get('frontiers') or [])}")

    try:
        run_episode(Gateway(plugin, NDS_SANDBOX), plugin, ExploreBrain(agent_id, single_step=True), agent_id,
                    max_steps=_EXPLORE_STEPS, on_step=on_explore_step)
    except Exception as e:
        result["error"] = f"explore-run: {e}"

    final_role = perceiver.last_role
    all_confs = [s["conf"] for s in discovery_snapshots if s["conf"] > 0]
    avg_conf = round(sum(all_confs) / len(all_confs), 3) if all_confs else 0.0
    gameplay_votes: dict[str, int] = {}
    for s in discovery_snapshots:
        g = s.get("gameplay")
        if g:
            gameplay_votes[g] = gameplay_votes.get(g, 0) + 1
    dominant = max(gameplay_votes, key=lambda k: gameplay_votes[k]) if gameplay_votes else None

    result["discovery"] = {
        "final_gameplay": final_role.get("gameplay"), "dominant_screen": dominant,
        "expected_screen": expected_screen,
        "screen_correct": (dominant == expected_screen) if expected_screen else None,
        "avg_confidence": avg_conf, "commit_step": discovery_commit_step,
        "votes": gameplay_votes, "_debug": final_role.get("_debug", {}),
    }
    all_spatial = spatial_snapshots + [
        {"step": s["step"] + _WARMUP_STEPS, "visited": s["visited"],
         "frontiers": s["frontiers"], "pose": s["pose"], "ego_motion": s["ego_motion"]}
        for s in explore_snapshots
    ]
    max_visited = max((s["visited"] for s in all_spatial), default=0)
    poses = [s["pose"] for s in all_spatial if s["pose"] is not None]
    unique_poses = len(set(tuple(p) if isinstance(p, list) else p for p in poses))
    ego_motions = [s["ego_motion"] for s in all_spatial if s["ego_motion"]]
    moved_count = sum(1 for e in ego_motions
                      if isinstance(e, dict) and (e.get("dx", 0) != 0 or e.get("dy", 0) != 0))
    result["spatial"] = {"max_cells_visited": max_visited,
                         "final_cells_visited": all_spatial[-1]["visited"] if all_spatial else 0,
                         "unique_poses": unique_poses, "ego_motion_non_zero": moved_count,
                         "pipeline_ran": True}
    result["ontology"] = classify_ontology(label, result)
    plugin.close()
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="NDS driver + bench delegation")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("play", help="Run a single NDS ROM")
    p.add_argument("--rom", required=True)
    p.add_argument("--steps", type=int, default=150)
    p.add_argument("--out", default="runs/nds_play")
    p.add_argument("--label", default="game")
    p.add_argument("--expected-screen", default="")
    p.add_argument("--quiet", action="store_true")

    b = sub.add_parser("bench", help="Bench all NDS candidates (delegates to eval/nds_bench.py)")
    b.add_argument("--roms-dir", default="roms/nds")
    b.add_argument("--steps", type=int, default=150)
    b.add_argument("--out", default="runs/nds_bench")
    b.add_argument("--report", default="reports/nds-bench.md")
    b.add_argument("--quiet", action="store_true")

    args = ap.parse_args()

    if args.cmd == "play":
        expected = getattr(args, "expected_screen", "") or None
        result = run_one(rom_path=args.rom, label=args.label, steps=args.steps,
                         out_dir=args.out, expected_screen=expected or None,
                         verbose=not getattr(args, "quiet", False))
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("renders") else 1

    # bench mode: delegate to eval/nds_bench
    from eval.nds_bench import run_bench, write_report
    results = run_bench(roms_dir=args.roms_dir, steps=args.steps, out_dir=args.out,
                        verbose=not args.quiet)
    write_report(results, args.report)
    ok = sum(1 for r in results if r.get("renders") is True)
    print(f"\nBench complete. {ok} ROMs rendered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
