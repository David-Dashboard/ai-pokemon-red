"""Run an agent on Pokémon Red.

Examples:
    # zero-dependency smoke test (still needs PyBoy + your own ROM):
    python play_pokemon.py --rom path/to/PokemonRed.gb --brain scripted --steps 50

    # LLM agent via a local Ollama vision model:
    python play_pokemon.py --rom path/to/PokemonRed.gb --brain llm \
        --model llama3.2-vision --steps 200 --window

    # ...or via a local llama.cpp server (llama-server, OpenAI-compatible;
    # start it with --mmproj for vision):
    python play_pokemon.py --rom path/to/PokemonRed.gb --brain llm --backend llamacpp \
        --steps 200 --window

    # ...or via the decoupled ai-aria companion (its own bearer-authed service):
    ARIA_BEARER_TOKEN=... python play_pokemon.py --rom path/to/PokemonRed.gb \
        --brain llm --backend aria --steps 200 --window

    # record an MP4 of the run (works with or without a window; combine with --sound to
    # also watch live):
    python play_pokemon.py --rom path/to/PokemonRed.gb --brain hybrid --backend aria \
        --perception --load-state start.state --steps 400 --record runs/play.mp4

You must supply your own legally-obtained Pokémon Red ROM. None is bundled.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid

from core.gateway import Gateway
from core.runner import run_episode
from games.pokemon_red import POKEMON_SANDBOX, POKEMON_SYSTEM


def main() -> int:
    ap = argparse.ArgumentParser(description="Let an AI agent play Pokémon Red.")
    ap.add_argument("--rom", required=True, help="path to your Pokémon Red ROM (.gb)")
    ap.add_argument("--brain", choices=["scripted", "llm", "explore", "hybrid"], default="scripted",
                    help="explore = local frontier autopilot (no LLM/API; needs --perception); "
                         "hybrid = autopilot + wake the LLM only at decisions (needs --perception)")
    ap.add_argument("--steps", type=int, default=100)
    ap.add_argument("--backend", choices=["ollama", "llamacpp", "aria"], default="ollama",
                    help="LLM server for --brain llm")
    ap.add_argument("--model", default=None,
                    help="model name (Ollama tag, llama.cpp's loaded model, "
                         "or the aria model id; defaults per backend)")
    ap.add_argument("--llm-url", default=None,
                    help="LLM server URL (default: Ollama :11434, llama.cpp :8080, aria :8001)")
    ap.add_argument("--llm-token", default=os.environ.get("ARIA_BEARER_TOKEN"),
                    help="bearer token for an authed endpoint (aria); "
                         "defaults to $ARIA_BEARER_TOKEN")
    ap.add_argument("--no-vision", action="store_true", help="text-only LLM prompt")
    ap.add_argument("--perception", action="store_true",
                    help="Iteration-02: plan over a pixels-derived SymbolicState (odometry + "
                         "occupancy map) instead of RAM; RAM is logged to oracle.jsonl for scoring")
    ap.add_argument("--window", action="store_true", help="show the emulator window")
    ap.add_argument("--sound", action="store_true",
                    help="play the game audio (implies a window; runs at real-time so it's not "
                         "chipmunk-fast — best with --brain explore/hybrid for continuous sound)")
    ap.add_argument("--watch-delay", type=int, default=0,
                    help="idle frames to pause between moves (windowed/sound runs) so it's watchable; "
                         "60 ~ a 1s pause per move. The music keeps playing through the pause.")
    ap.add_argument("--record", default=None, metavar="PATH.mp4",
                    help="record the run to an MP4 (video + game audio) at this path; works with or "
                         "without a window (recording forces sound emulation and muxes it in)")
    ap.add_argument("--record-fps", type=int, default=30, help="frame rate of the recorded MP4")
    ap.add_argument("--record-scale", type=int, default=3,
                    help="integer upscale of the 160x144 frame in the MP4 (3 -> 480x432)")
    ap.add_argument("--out", default="runs/pokemon_red")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--load-state", default=None,
                    help="boot from a .state saved past the intro (see human_play.py)")
    ap.add_argument("--save-state", default=None,
                    help="write the final emulator state here when the run ends")
    ap.add_argument("--stuck-steps", type=int, default=0,
                    help="cost guardrail: HALT if no real progress (new maps/cells/badges/levels, "
                         "read from the RAM ORACLE — never shown to the agent) for this many steps. "
                         "0 = off; auto-enabled (80) for paid brains (llm/hybrid) so a thrash can't "
                         "burn budget like live-run #1 did.")
    ap.add_argument("--max-llm-calls", type=int, default=0,
                    help="budget cap: HALT after this many LLM wakes (each ~= one paid call). "
                         "0 = off. Use on paid (--brain llm/hybrid) runs to bound spend.")
    ap.add_argument("--max-cost-usd", type=float, default=0.0,
                    help="estimated-spend circuit breaker: HALT when the running cost ESTIMATE "
                         "(token usage x model pricing) reaches this many USD. 0 = off; auto-enabled "
                         "($1.00) for paid brains (llm/hybrid) — the true cost ceiling --max-llm-calls "
                         "only approximates (a bloated wake can cost many times a lean one).")
    ap.add_argument("--max-prompt-tokens", type=int, default=0,
                    help="per-wake prompt-token cap: HALT if any single wake's prompt exceeds this "
                         "(a runaway-bloat tripwire). 0 = off; auto-enabled (48000) for paid brains — "
                         "well above the observed ~13-30k/wake baseline so a normal large wake won't trip it.")
    ap.add_argument("--stuck-wakes", type=int, default=0,
                    help="wake-denominated watchdog: HALT after this many LLM WAKES with no real "
                         "progress (catches flailing the step watchdog misses once free auto-advance "
                         "inflates the step count between wakes). 0 = off; auto-enabled (30) for paid brains.")
    args = ap.parse_args()

    agent_id = f"agent-{uuid.uuid4()}"

    try:
        from games.pokemon_red import PokemonRedPlugin
        perceiver = None
        if args.perception:
            from games.pokemon_red.perceiver import OverworldPerceiver
            perceiver = OverworldPerceiver()
        plugin = PokemonRedPlugin(rom_path=args.rom, out_dir=args.out,
                                  headless=not (args.window or args.sound),
                                  init_state=args.load_state, perceiver=perceiver,
                                  sound=args.sound, record_path=args.record,
                                  record_fps=args.record_fps, record_scale=args.record_scale)
    except (FileNotFoundError, ImportError) as e:
        print(f"\nSetup error:\n{e}\n", file=sys.stderr)
        return 2

    if args.brain in ("llm", "hybrid"):
        from core.brains import LLMButtonBrain
        default_url = {"llamacpp": "http://localhost:8080",
                       "aria": "http://localhost:8001"}.get(
                           args.backend, "http://localhost:11434")
        url = args.llm_url or default_url
        default_model = {"aria": "aria"}.get(args.backend, "llama3.2-vision")
        model = args.model or default_model
        if args.backend == "aria" and not args.llm_token:
            print("\nSetup error:\n--backend aria needs a bearer token "
                  "(--llm-token or $ARIA_BEARER_TOKEN).\n", file=sys.stderr)
            return 2
        llm = LLMButtonBrain(agent_id, model=model, url=url,
                             backend=args.backend, use_vision=not args.no_vision,
                             api_key=args.llm_token, system=POKEMON_SYSTEM)
        if args.brain == "llm":
            brain = llm
        else:  # hybrid = free autopilot + wake the LLM only at decisions
            if not args.perception:
                print("\nSetup error:\n--brain hybrid needs --perception.\n", file=sys.stderr)
                return 2
            from core.brains import ExploreBrain, HybridBrain
            brain = HybridBrain(
                ExploreBrain(agent_id, single_step=True, probe_interactables=True),
                llm, advance_on_dialog=True)
    elif args.brain == "explore":
        if not args.perception:
            print("\nSetup error:\n--brain explore needs --perception (it navigates on the "
                  "SymbolicState occupancy map).\n", file=sys.stderr)
            return 2
        from core.brains import ExploreBrain
        brain = ExploreBrain(agent_id, single_step=True, probe_interactables=True)  # [d]=1 tile; probe walls when stuck
    else:
        from core.brains import ScriptedBrain
        brain = ScriptedBrain(agent_id, seed=args.seed)

    gateway = Gateway(plugin, POKEMON_SANDBOX)

    # Progress watchdog (cost guardrail). It reads the RAM ORACLE for ground-truth progress — this is
    # control/scoring only and is NEVER fed into the agent's Observation (the no-leak wall holds).
    stuck = args.stuck_steps
    if stuck == 0 and args.brain in ("llm", "hybrid"):
        stuck = 80
        print(f"[guard] paid brain '{args.brain}': progress watchdog ON - halts after {stuck} steps "
              f"with no progress (override with --stuck-steps).")
    # Cost guardrails (S1) — the spend breaker, per-wake prompt cap, and wake-denominated watchdog.
    # Auto-enabled for paid brains (like --stuck-steps) so a forgotten flag can't leave a paid run
    # unguarded; each is overridable by its own flag (and 0 disables it on an explicit override).
    max_cost = args.max_cost_usd
    max_prompt_tokens = args.max_prompt_tokens
    stuck_wakes = args.stuck_wakes
    if args.brain in ("llm", "hybrid"):
        if max_cost == 0.0:
            max_cost = 1.00
        if max_prompt_tokens == 0:
            max_prompt_tokens = 48000
        if stuck_wakes == 0:
            stuck_wakes = 30
        print(f"[guard] paid brain '{args.brain}': cost cap ~${max_cost:.2f}, prompt cap "
              f"{max_prompt_tokens} tok/wake, wake watchdog {stuck_wakes} wakes (override each with its flag).")
    from games.pokemon_red.memory_map import read_state
    coverage: set = set()
    wd = {"best": None, "last": 0, "woke": 0}

    def note_progress(step):
        st = read_state(plugin.emu.read)               # ORACLE: watchdog only, never the agent's input
        coverage.add((st["map_id"], st["x"], st["y"]))
        fp = (st["badges"], st["party_level_sum"], len(coverage))
        improved = wd["best"] is None or any(a > b for a, b in zip(fp, wd["best"]))
        wd["best"] = fp if wd["best"] is None else tuple(max(a, b) for a, b in zip(fp, wd["best"]))
        # A battle shows NO fingerprint progress (badges/level/cells don't move until a mon faints), and
        # with battle auto-advance a fight runs many free steps per LLM call — so the watchdog could halt
        # mid-fight. Treat being in a battle as progress: a trainer fight can't be fled and is bounded;
        # --max-llm-calls is the real ceiling. (in_battle is RAM — oracle/watchdog only, never the agent.)
        if improved or st["in_battle"]:
            wd["last"] = step
            wd["woke"] = getattr(brain, "woke", 0)     # wake-watchdog baseline (reset on real progress)

    max_llm_calls = args.max_llm_calls

    from core.brains import API_ERROR_CIRCUIT_BREAKER
    from core.cost_guard import spend_halt_reason, wake_stall_halt_reason

    def should_continue(step):
        ce = getattr(brain, "consec_api_errors", 0)
        if ce >= API_ERROR_CIRCUIT_BREAKER:    # persistent backend outage (e.g. credits) -> fail fast
            print(f"\n[guard] the model API failed {ce}x in a row - HALTING (circuit breaker).\n"
                  f"        last error: {getattr(brain, 'last_api_error', '')}")
            return False
        if max_llm_calls > 0 and getattr(brain, "woke", 0) >= max_llm_calls:
            print(f"\n[guard] budget cap hit ({getattr(brain, 'woke', 0)} LLM calls) - HALTING.")
            return False
        # spend ceilings (cost breaker + per-wake prompt-token cap) and the wake-denominated watchdog —
        # one shared, tested implementation (core.cost_guard); wd["woke"] is the wake count at the last
        # oracle-progress checkpoint (RAM-derived, set in note_progress — never reaches the agent).
        reason = spend_halt_reason(brain, max_cost_usd=max_cost, max_prompt_tokens=max_prompt_tokens)
        if reason is None:
            reason = wake_stall_halt_reason(getattr(brain, "woke", 0), wd["woke"], stuck_wakes)
        if reason:
            print(f"\n[guard] {reason} - HALTING.")
            return False
        if stuck <= 0:
            return True
        if step - wd["last"] >= stuck:
            print(f"\n[guard] no progress for {step - wd['last']} steps - HALTING (watchdog). "
                  f"Likely stuck or needs a capability we haven't built yet (battle/menu).")
            return False
        return True

    def on_step(step, obs, result, events):
        data = getattr(result, "data", {})
        r = data.get("reward", 0.0)
        flair = f"  reward={r:+.1f}" if r else ""
        if "map_id" in obs.data:  # RAM-mode observation
            head = (f"[{step:04d}] map={obs.data['map_id']} ({obs.data['x']},{obs.data['y']}) "
                    f"badges={obs.data['badges']}{flair}")
        else:                     # perception-mode observation (SymbolicState)
            pose = (obs.data.get("pose") or {}).get("value")
            la = obs.data.get("last_action") or {}
            head = (f"[{step:04d}] pose={pose} last={la.get('outcome')} "
                    f"conf={obs.data.get('confidence')}{flair}")
        # The LLM brain exposes its latest reasoning; show it under each step.
        thought = getattr(brain, "last_thought", "")
        if thought:
            safe = thought.encode("ascii", "replace").decode()  # Windows-console safe
            print(f"{head}\n        think: {safe}  -> {data.get('action', '')}")
        else:
            print(head)
        note_progress(step)                      # update the progress watchdog (oracle-side)
        if args.watch_delay > 0:                 # idle pause between moves (real-time only)
            plugin.emu.tick(args.watch_delay)    # music keeps playing; the character waits

    print(f"Agent {agent_id} playing for {args.steps} steps with the {args.brain} brain...\n")
    try:
        summary = run_episode(gateway, plugin, brain, agent_id,
                              max_steps=args.steps, on_step=on_step,
                              should_continue=should_continue)
        if args.save_state:
            plugin.save_state(args.save_state)
            print(f"saved final state -> {args.save_state}")
    finally:
        plugin.close()

    print("\n=== episode summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    if hasattr(brain, "wake_rate"):  # hybrid: how often the expensive brain was actually needed
        print(f"  llm_woke: {brain.woke}/{brain.total} steps ({100 * brain.wake_rate:.1f}%) "
              f"— autopilot handled the rest for free")
    if getattr(brain, "total_prompt_tokens", 0) or getattr(brain, "total_cost_usd", 0.0):
        print(f"  tokens: {brain.total_prompt_tokens} in / {brain.total_completion_tokens} out "
              f"({brain.total_cached_tokens} cached); est spend ~${brain.total_cost_usd:.2f}")
    if args.record:
        print(f"  recording: {args.record}")

    # Definition-of-Done step 1: auto-scaffold a report skeleton for PAID runs (oracle facts from
    # <out>/oracle.jsonl, exact wake counts from the brain). Best-effort — never fail a run over a
    # report; it won't clobber an existing file. Fill its TODOs + LEARNINGS/HANDOFF/memory (CLAUDE.md).
    if args.brain in ("llm", "hybrid"):
        try:
            from eval.report_run import scaffold_report
            cost = (f"~${brain.total_cost_usd:.2f} (estimated)"
                    if getattr(brain, "total_cost_usd", 0.0) else None)
            path, _ = scaffold_report(args.out, brain=brain, cost=cost)
            print(f"  report: scaffolded {path} — fill its TODOs (see CLAUDE.md Definition of Done)"
                  if path else "  report: a report for this run/date already exists — not overwriting "
                               "(re-run eval.report_run --force to refresh facts).")
        except Exception as e:  # pragma: no cover - reporting must never break a run
            print(f"  report: auto-scaffold skipped ({type(e).__name__}: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
