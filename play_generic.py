"""Generic end-to-end play harness — runs the SHARED perceiver on ANY GB/GBC ROM.

Wires: GBEmulator(rom) -> PerceptionPlugin -> GridPerceiver(MoveSignal per camera class)
    -> ScriptedBrain warmup -> ExploreBrain exploration -> run_episode.
Headless. No LLM, no API calls.

Camera class is auto-detected from the ROM filename via the _FOLLOW_KEYS mapping
(gold/kirby/metroid/spaceinv/f1race/ffa/sml -> follow; everything else -> fixed).

  uv run python play_generic.py --rom "roms/Cave Noire (Japan) [T-En by Aeon Genesis v1.00].gb" --steps 150
  uv run python play_generic.py --rom "roms/Gauntlet II (USA, Europe).gb" --camera follow --steps 150
"""
from __future__ import annotations

import argparse
import os
import uuid

from core.brains import ExploreBrain, ScriptedBrain
from core.gateway import Gateway
from core.grid_perceiver import CameraScrollSignal, ForegroundSignal, GridPerceiver
from core.perception_plugin import PerceptionPlugin
from core.permissions import Allowlist
from core.runner import run_episode

# Camera-class heuristic: substring in the ROM slug -> follow-camera world.
# From eval/compare_localizers.py and eval/probe_entities.py.
_FOLLOW_KEYS = ("gold", "kirby", "metroid", "spaceinv", "f1race", "ffa", "sml")

_SANDBOX = Allowlist({"press_button", "press_sequence", "wait"})


def _camera_class(rom_path: str, override: str | None) -> str:
    if override in ("fixed", "follow"):
        return override
    slug = os.path.basename(rom_path).lower()
    return "follow" if any(k in slug for k in _FOLLOW_KEYS) else "fixed"


def main() -> int:
    ap = argparse.ArgumentParser(description="Generic GB/GBC play harness (perception benchmark).")
    ap.add_argument("--rom", required=True, help="Path to a .gb or .gbc ROM file.")
    ap.add_argument("--camera", choices=["fixed", "follow"], default=None,
                    help="Override camera class (default: auto from ROM name).")
    ap.add_argument("--steps", type=int, default=150,
                    help="Total steps (warmup + explore combined).")
    ap.add_argument("--warmup-steps", type=int, default=40,
                    help="ScriptedBrain steps to burn through the title/menu before ExploreBrain.")
    ap.add_argument("--init-state", default=None,
                    help="Optional .state file to load (skip the title entirely).")
    ap.add_argument("--out", default=None,
                    help="Output directory (default: runs/bench_generic/<game>/).")
    ap.add_argument("--window", action="store_true", help="Show SDL2 window (default headless).")
    args = ap.parse_args()

    cam = _camera_class(args.rom, args.camera)
    game_slug = os.path.splitext(os.path.basename(args.rom))[0]
    out_dir = args.out or os.path.join("runs", "bench_generic", game_slug)

    move_signal = ForegroundSignal() if cam == "fixed" else CameraScrollSignal()
    perceiver = GridPerceiver(move_signal=move_signal)

    plugin = PerceptionPlugin(
        rom_path=args.rom,
        out_dir=out_dir,
        headless=not args.window,
        init_state=args.init_state,
        perceiver=perceiver,
    )
    gateway = Gateway(plugin, _SANDBOX)
    agent_id = f"agent-{uuid.uuid4()}"

    # Phase 1: ScriptedBrain warmup (mash through title/menu).
    warmup_steps = 0 if args.init_state else args.warmup_steps
    explore_steps = args.steps - warmup_steps

    print(f"[generic] rom={game_slug!r}  camera={cam}  warmup={warmup_steps}  explore={explore_steps}  out={out_dir}")

    def on_step(step, obs, result, events):
        phase = "warmup" if step < warmup_steps else "explore"
        if step % 25 == 0 or step == args.steps - 1:
            d = obs.data
            sm = d.get("spatial_memory") or {}
            la = d.get("last_action") or {}
            print(f"  [{phase}] step {step:3d}  context={d.get('context'):8s}  "
                  f"pose={d.get('pose', {}).get('value')}  "
                  f"visited={sm.get('visited')}  frontiers={len(sm.get('frontiers') or [])}  "
                  f"last={la.get('action')}->{la.get('outcome')}")

    # Two-phase run: warmup then explore.
    try:
        if warmup_steps > 0:
            warmup_brain = ScriptedBrain(agent_id, seed=0)
            run_episode(gateway, plugin, warmup_brain, agent_id, max_steps=warmup_steps, on_step=on_step)

        explore_brain = ExploreBrain(agent_id, single_step=True)

        def on_explore_step(step, obs, result, events):
            on_step(step + warmup_steps, obs, result, events)

        summary = run_episode(gateway, plugin, explore_brain, agent_id,
                              max_steps=explore_steps, on_step=on_explore_step)
    finally:
        plugin.close()

    print(f"\nDone. steps={summary['steps']}  events={summary['event_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
