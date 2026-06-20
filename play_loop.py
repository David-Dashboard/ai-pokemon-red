"""Iteratively play Pokémon Red toward the Elite Four — cheap, persistent, and loop-safe.

  * Cheap: a free local autopilot (frontier exploration) does the walking; the LLM is woken only at
    decisions (HybridBrain). The log prints the LLM-call count + wake-rate so spend is visible.
  * Persistent: checkpoints the emulator state every --chunk steps, so progress survives a crash and
    resumes across launches.
  * Loop-safe: a progress watchdog HALTS when no real progress (badges / maps / level / newly-seen
    cells — read from the RAM oracle, never fed to the agent) happens for --stuck-steps. So it can
    make mistakes, but it never spins in an almost-infinite loop or burns budget doing nothing.
  * Budget-bounded: stops after --max-llm-calls LLM wakes (each ≈ one Haiku call).

The whole game is tens of thousands of steps; one launch won't finish it — relaunch to continue.

    ARIA_BEARER_TOKEN=... uv run python play_loop.py --rom roms/PokemonRed.gb
"""
from __future__ import annotations

import argparse
import os
import uuid

from core.brains import ExploreBrain, HybridBrain, LLMButtonBrain
from core.gateway import Gateway
from core.runner import run_episode
from games.pokemon_red import POKEMON_SANDBOX, POKEMON_SYSTEM


def main() -> int:
    ap = argparse.ArgumentParser(description="Iteratively play Pokémon Red — cheap, persistent, loop-safe.")
    ap.add_argument("--rom", required=True)
    ap.add_argument("--state", default="progress.state", help="checkpoint (resumed + rewritten)")
    ap.add_argument("--seed-state", default="start.state", help="initial state if no progress yet")
    ap.add_argument("--chunk", type=int, default=30, help="checkpoint + progress check every N steps")
    ap.add_argument("--max-steps", type=int, default=3000, help="hard step cap for this launch")
    ap.add_argument("--max-llm-calls", type=int, default=150, help="budget guard: stop after this many LLM wakes")
    ap.add_argument("--stuck-steps", type=int, default=60, help="halt if no real progress for this many steps")
    ap.add_argument("--url", default="http://localhost:8001")
    ap.add_argument("--model", default="aria")
    ap.add_argument("--token", default=os.environ.get("ARIA_BEARER_TOKEN"))
    args = ap.parse_args()

    from games.pokemon_red import PokemonRedPlugin
    from games.pokemon_red.memory_map import read_state
    from games.pokemon_red.perceiver import OverworldPerceiver

    aid = f"agent-{uuid.uuid4()}"
    init = args.state if os.path.exists(args.state) else args.seed_state
    plugin = PokemonRedPlugin(rom_path=args.rom, out_dir="runs/loop", headless=True,
                              init_state=init, perceiver=OverworldPerceiver())
    llm = LLMButtonBrain(aid, model=args.model, url=args.url, backend="aria",
                         api_key=args.token, use_vision=True, system=POKEMON_SYSTEM)
    brain = HybridBrain(ExploreBrain(aid, single_step=True, probe_interactables=True), llm, advance_on_dialog=True)  # autopilot ([d]=1 tile, probe walls when stuck) + auto-advance dialog + wake at decisions
    gw = Gateway(plugin, POKEMON_SANDBOX)

    coverage: set = set()

    def on_step(step, obs, result, events):
        st = read_state(plugin.emu.read)  # ORACLE: control + log only; NEVER the agent's input
        coverage.add((st["map_id"], st["x"], st["y"]))

    def fingerprint():
        st = read_state(plugin.emu.read)
        return (st["badges"], plugin._reward.maps_seen, st["party_level_sum"], len(coverage))

    print(f"[loop] resume={init}  max_steps={args.max_steps}  budget={args.max_llm_calls} LLM calls  "
          f"halt_if_stuck={args.stuck_steps} steps", flush=True)

    from core.brains import API_ERROR_CIRCUIT_BREAKER
    def _circuit_ok(step):   # halt a chunk EARLY on a persistent backend outage (don't grind the chunk)
        return getattr(brain, "consec_api_errors", 0) < API_ERROR_CIRCUIT_BREAKER

    best = None
    stale = done = 0
    stop = ""
    try:
        while done < args.max_steps:
            run_episode(gw, plugin, brain, aid, max_steps=args.chunk, on_step=on_step,
                        should_continue=_circuit_ok)
            done += args.chunk
            if getattr(brain, "consec_api_errors", 0) >= API_ERROR_CIRCUIT_BREAKER:
                stop = (f"the model API failed {brain.consec_api_errors}x in a row — HALTING "
                        f"(circuit breaker). last error: {brain.last_api_error}")
                break
            plugin.save_state(args.state)
            fp = fingerprint()
            st = read_state(plugin.emu.read)
            print(f"[loop] {done}/{args.max_steps}  badges={fp[0]} maps={fp[1]} lvl={fp[2]} cells={fp[3]} "
                  f"map={st['map_id']}  LLM_calls={brain.woke} ({100 * brain.wake_rate:.0f}% of steps)",
                  flush=True)
            improved = best is None or any(a > b for a, b in zip(fp, best))
            best = fp if best is None else tuple(max(a, b) for a, b in zip(fp, best))
            # A battle shows NO fingerprint progress (badges/maps/level/cells don't move until a mon
            # faints/levels), and with battle auto-advance a fight now runs many free steps per LLM
            # call — so the watchdog could halt mid-battle. Suppress staleness while in a battle: a
            # trainer fight can't be fled, has bounded turns, and --max-llm-calls is the real ceiling.
            # (in_battle is RAM — the oracle's control/log role only, never fed to the agent.)
            stale = 0 if (improved or st["in_battle"]) else stale + args.chunk
            if fp[0] >= 8:
                stop = "all 8 badges — onward to the Elite Four"
                break
            if brain.woke >= args.max_llm_calls:
                stop = f"budget guard hit ({brain.woke} LLM calls)"
                break
            if stale >= args.stuck_steps:
                stop = (f"no progress for {stale} steps — HALTING (not looping). Likely needs a "
                        f"capability we haven't built yet (battle/menu handling)")
                break
    finally:
        plugin.save_state(args.state)
        plugin.close()
    print(f"[loop] STOP: {stop or 'step cap reached'}. progress -> {args.state}; "
          f"total LLM calls={brain.woke}. Relaunch to continue.", flush=True)

    # Definition-of-Done step 1: auto-scaffold a report skeleton (oracle facts + exact brain wake
    # counts). Best-effort; won't clobber an existing report. Fill its TODOs + LEARNINGS/HANDOFF/memory.
    try:
        from eval.report_run import scaffold_report
        path, _ = scaffold_report("runs/loop", brain=brain)
        print(f"[loop] report: scaffolded {path} — fill its TODOs (see CLAUDE.md Definition of Done)"
              if path else "[loop] report: one already exists for this date — not overwriting.", flush=True)
    except Exception as e:  # pragma: no cover - reporting must never break a run
        print(f"[loop] report: auto-scaffold skipped ({type(e).__name__}: {e})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
