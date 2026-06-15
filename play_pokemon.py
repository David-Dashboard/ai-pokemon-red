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
            brain = HybridBrain(ExploreBrain(agent_id), llm, advance_on_dialog=True)
    elif args.brain == "explore":
        if not args.perception:
            print("\nSetup error:\n--brain explore needs --perception (it navigates on the "
                  "SymbolicState occupancy map).\n", file=sys.stderr)
            return 2
        from core.brains import ExploreBrain
        brain = ExploreBrain(agent_id)
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
    from games.pokemon_red.memory_map import read_state
    coverage: set = set()
    wd = {"best": None, "last": 0}

    def note_progress(step):
        st = read_state(plugin.emu.read)               # ORACLE: watchdog only, never the agent's input
        coverage.add((st["map_id"], st["x"], st["y"]))
        fp = (st["badges"], st["party_level_sum"], len(coverage))
        improved = wd["best"] is None or any(a > b for a, b in zip(fp, wd["best"]))
        wd["best"] = fp if wd["best"] is None else tuple(max(a, b) for a, b in zip(fp, wd["best"]))
        if improved:
            wd["last"] = step

    max_llm_calls = args.max_llm_calls

    def should_continue(step):
        if max_llm_calls > 0 and getattr(brain, "woke", 0) >= max_llm_calls:
            print(f"\n[guard] budget cap hit ({getattr(brain, 'woke', 0)} LLM calls) - HALTING.")
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
    if args.record:
        print(f"  recording: {args.record}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
