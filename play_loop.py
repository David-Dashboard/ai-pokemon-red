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
    ap.add_argument("--stuck-wakes", type=int, default=30,
                    help="halt after this many LLM WAKES with no real progress — the wake-denominated "
                         "watchdog. Catches flailing that --stuck-steps misses once free auto-advance "
                         "inflates the step count between wakes (the run-#15 'aimless wandering' case)")
    ap.add_argument("--max-cost-usd", type=float, default=1.50,
                    help="estimated-spend circuit breaker: halt when the running cost ESTIMATE "
                         "(token usage x model pricing) reaches this many USD. 0 = off")
    ap.add_argument("--max-prompt-tokens", type=int, default=48000,
                    help="per-wake prompt-token cap: halt if any single wake's prompt exceeds this "
                         "(a runaway-bloat tripwire, well above the observed ~13-30k/wake baseline). 0 = off")
    ap.add_argument("--url", default="http://localhost:8001")
    ap.add_argument("--model", default="aria")
    ap.add_argument("--token", default=os.environ.get("ARIA_BEARER_TOKEN"))
    ap.add_argument("--allow-dirty-memory", action="store_true",
                    help="skip the fresh-run aria-memory guard (use when resuming, or for a deliberate "
                         "dirty start). A FRESH run on un-reset aria memory leaks the prior run under the "
                         "beta learning boundary (S3).")
    args = ap.parse_args()

    from games.pokemon_red import PokemonRedPlugin
    from games.pokemon_red.memory_map import read_state
    from games.pokemon_red.perceiver import OverworldPerceiver

    aid = f"agent-{uuid.uuid4()}"
    init = args.state if os.path.exists(args.state) else args.seed_state
    # Fail-loud freshness guard (S3 beta): a FRESH run (seed-state, no checkpoint to resume) must start
    # on reset aria memory, else it leaks the prior run. A resume (init == args.state) legitimately
    # carries this run's own accumulated aria memory across launches, so the guard is skipped there.
    if not args.allow_dirty_memory and init == args.seed_state:
        from reset_aria_memory import _default_data_dir, is_clean
        if not is_clean():
            print(f"[loop] ABORT: aria memory ({_default_data_dir()}) is NOT reset, but this is a FRESH "
                  f"run — it would leak the prior run (beta learning boundary). Run "
                  f"reset_aria_memory.py --yes, or pass --allow-dirty-memory.", flush=True)
            return 2
    plugin = PokemonRedPlugin(rom_path=args.rom, out_dir="runs/loop", headless=True,
                              init_state=init, perceiver=OverworldPerceiver())
    llm = LLMButtonBrain(aid, model=args.model, url=args.url, backend="aria",
                         api_key=args.token, use_vision=True, system=POKEMON_SYSTEM,
                         owns_memory=True)  # aria owns within-run memory (S3 beta); this driver is aria-only
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
          f"halt_if_stuck={args.stuck_steps} steps / {args.stuck_wakes} wakes  "
          f"cost_cap=${args.max_cost_usd:.2f}  prompt_cap={args.max_prompt_tokens} tok", flush=True)

    from core.brains import API_ERROR_CIRCUIT_BREAKER
    from core.cost_guard import spend_halt_reason, wake_stall_halt_reason
    def _circuit_ok(step):   # per-step halt: stop a chunk EARLY on a backend outage OR a spend overrun
        if getattr(brain, "consec_api_errors", 0) >= API_ERROR_CIRCUIT_BREAKER:
            return False
        return spend_halt_reason(brain, max_cost_usd=args.max_cost_usd,
                                 max_prompt_tokens=args.max_prompt_tokens) is None

    best = None
    woke_at_progress = 0       # brain.woke at the last real-progress checkpoint (stuck-wakes baseline)
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
            spend_stop = spend_halt_reason(brain, max_cost_usd=args.max_cost_usd,
                                           max_prompt_tokens=args.max_prompt_tokens)
            if spend_stop:
                stop = spend_stop
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
            if improved or st["in_battle"]:
                woke_at_progress = brain.woke      # reset the wake-watchdog baseline on real progress
            if fp[0] >= 8:
                stop = "all 8 badges — onward to the Elite Four"
                break
            if brain.woke >= args.max_llm_calls:
                stop = f"budget guard hit ({brain.woke} LLM calls)"
                break
            wake_stop = wake_stall_halt_reason(brain.woke, woke_at_progress, args.stuck_wakes)
            if wake_stop:
                stop = wake_stop + " — likely needs a capability we haven't built yet"
                break
            if stale >= args.stuck_steps:
                stop = (f"no progress for {stale} steps — HALTING (not looping). Likely needs a "
                        f"capability we haven't built yet (battle/menu handling)")
                break
    finally:
        plugin.save_state(args.state)
        plugin.close()
    print(f"[loop] STOP: {stop or 'step cap reached'}. progress -> {args.state}; "
          f"total LLM calls={brain.woke}, est spend ~${getattr(brain, 'total_cost_usd', 0.0):.2f} "
          f"({getattr(brain, 'total_prompt_tokens', 0)} in / "
          f"{getattr(brain, 'total_completion_tokens', 0)} out tok). Relaunch to continue.", flush=True)

    # Definition-of-Done step 1: auto-scaffold a report skeleton (oracle facts + exact brain wake
    # counts). Best-effort; won't clobber an existing report. Fill its TODOs + LEARNINGS/HANDOFF/memory.
    try:
        from eval.report_run import scaffold_report
        path, _ = scaffold_report("runs/loop", brain=brain,
                                  cost=f"~${getattr(brain, 'total_cost_usd', 0.0):.2f} (estimated)")
        print(f"[loop] report: scaffolded {path} — fill its TODOs (see CLAUDE.md Definition of Done)"
              if path else "[loop] report: one already exists for this date — not overwriting.", flush=True)
    except Exception as e:  # pragma: no cover - reporting must never break a run
        print(f"[loop] report: auto-scaffold skipped ({type(e).__name__}: {e})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
