"""Estimate a paid run's LLM call count + cost WITHOUT spending — run HybridBrain with a FREE
fallback (ScriptedBrain stands in for the LLM) and count how often it would WAKE the expensive brain.

Each wake == one LLM call in a paid run. Live-run #1 woke 351/400 (88%) because the autopilot was
permanently stuck on the phantom-frontier bug; after the seam/portal fix the autopilot has real
frontiers, so this measures whether the cost model is actually restored. Free (no API, no credits).

Caveat: the random fallback drives a different trajectory than a real LLM would, so treat the count
as an order-of-magnitude estimate (and the mode-wakes depend on where the walk wanders). The headline
that matters is the STUCK-wake rate vs run #1's 88%.

    uv run python -m eval.estimate_wake_rate --rom roms/PokemonRed.gb --load-state start.state --steps 300
"""
from __future__ import annotations

import argparse
import uuid

from core.brains import ExploreBrain, HybridBrain, ScriptedBrain
from core.gateway import Gateway
from core.runner import run_episode
from games.pokemon_red import POKEMON_SANDBOX, PokemonRedPlugin
from games.pokemon_red.memory_map import read_state
from games.pokemon_red.perceiver import OverworldPerceiver

# Rough uncached-Haiku cost per LLM wake, from live-run #1: ~$3 over 351 wakes (vision prompt).
_USD_PER_WAKE = 3.0 / 351


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Estimate paid-run LLM wakes/cost for free.")
    ap.add_argument("--rom", required=True)
    ap.add_argument("--load-state", default="start.state")
    ap.add_argument("--steps", type=int, default=300)
    ap.add_argument("--out", default="runs/wake_estimate")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    aid = f"agent-{uuid.uuid4()}"
    plugin = PokemonRedPlugin(rom_path=args.rom, out_dir=args.out, headless=True,
                              init_state=args.load_state, perceiver=OverworldPerceiver())
    brain = HybridBrain(ExploreBrain(aid), ScriptedBrain(aid, seed=args.seed),  # FREE LLM stand-in
                        advance_on_dialog=True)   # match the real Pokémon driver (dialog is auto-advanced free)
    gw = Gateway(plugin, POKEMON_SANDBOX)

    tally = {"mode": 0, "stuck": 0}
    coverage: set = set()

    def on_step(step, obs, result, events):
        st = read_state(plugin.emu.read)                  # ORACLE: progress accounting only
        coverage.add((st["map_id"], st["x"], st["y"]))
        if brain.mode == "llm":                           # this step woke the (stand-in) LLM
            t = brain.last_thought
            tally["mode" if "[wake:mode]" in t else "stuck"] += 1

    try:
        run_episode(gw, plugin, brain, aid, max_steps=args.steps, on_step=on_step)
    finally:
        plugin.close()

    woke, total = brain.woke, brain.total
    rate = 100 * woke / total if total else 0.0
    maps = sorted({m for m, _, _ in coverage})
    print("=== wake-rate estimate (FREE; ScriptedBrain stands in for the LLM) ===")
    print(f"steps: {total}   LLM wakes: {woke} ({rate:.1f}% of steps)   [live-run #1 was 88%]")
    print(f"  by reason: mode (battle/menu/dialog) = {tally['mode']}   stuck (no frontier) = {tally['stuck']}")
    print(f"coverage: {len(coverage)} unique (map,x,y) cells   maps visited: {maps}")
    print(f"projected uncached cost for {woke} wakes: ~${woke * _USD_PER_WAKE:.2f} "
          f"(@ ~${_USD_PER_WAKE:.4f}/wake, the live-run-#1 empirical rate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
