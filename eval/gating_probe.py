"""The gating probe — does the agent do means-ends reasoning with backtracking, or just recall?

Runs GateWorld (a synthetic gate: fetch an item, carry it back, open the gate, reach the goal)
through the SAME HybridBrain(ExploreBrain, reasoner) loop the Pokémon agent uses — the free autopilot
explores, gets stuck at the gate, and the reasoner is woken to do the class-2 part. It runs TWO
skins of the identical world under one NEUTRAL prompt:
  * familiar — invokes the generic "key opens door" prior (recall-friendly)
  * novel    — a fragment + a barrier with no semantic open-relationship (must be inferred)

Verdict by the solve-delta:
  solved BOTH         -> reasoning that transfers (the capability is real)
  solved familiar only-> recall-leaning (it leaned on the prior, didn't infer)
  solved NEITHER      -> can't do class-2 gating yet

Default --brain scripted is FREE (an oracle reasoner) and proves the world + loop are solvable; that
is the plumbing check and the upper bound. --brain llm runs the real (credit-gated) measurement with
a neutral, world-agnostic system prompt (the leak control). Everything but the reasoner is identical.

Run (free):  uv run python -m eval.gating_probe
Run (LLM):   ARIA_BEARER_TOKEN=... uv run python -m eval.gating_probe --brain llm --backend aria
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid

from core.brains import ExploreBrain, HybridBrain, LLMButtonBrain
from core.gateway import Gateway
from core.permissions import GATEWORLD_SANDBOX
from core.runner import run_episode
from games.gateworld import FAMILIAR, GateWorld, NOVEL, ScriptedReasoner

# World-agnostic: NO mention of Pokémon, NO "key", and NO hint binding the specific object to the
# specific gate. The one generic dynamics note ("may need to carry an object past an obstacle") is
# identical across skins, so it can't differentially help — the leak control is the solve-delta
# between skins, which this preserves. Both skins use this exact prompt.
NEUTRAL_SYSTEM = (
    "You control an avatar on a tile grid. Your goal is to reach the goal tile described below.\n"
    "Move with the d-pad: up, down, left, right (one tile each). Press A to interact with whatever "
    "you are standing on or directly next to. Some paths are blocked; you may need to find and carry "
    "an object to get past an obstacle — reason it out from what you observe.\n"
    "Reply in EXACTLY this format and nothing else:\n"
    "THINK: <one short sentence — what you see and what you'll do>\n"
    "MOVE: <1-4 buttons separated by spaces, from: up down left right a b>"
)


def make_reasoner(args, agent_id: str):
    if args.brain == "scripted":
        return ScriptedReasoner(agent_id)
    default_url = {"llamacpp": "http://localhost:8080", "aria": "http://localhost:8001"}.get(
        args.backend, "http://localhost:11434")
    return LLMButtonBrain(agent_id, model=args.model or {"aria": "aria"}.get(args.backend, "llama3.2-vision"),
                          url=args.llm_url or default_url, backend=args.backend,
                          use_vision=False, api_key=args.llm_token, system=NEUTRAL_SYSTEM)


def run_one(theme, args) -> dict:
    agent_id = f"agent-{uuid.uuid4()}"
    world = GateWorld(theme=theme)
    brain = HybridBrain(ExploreBrain(agent_id), make_reasoner(args, agent_id))
    gateway = Gateway(world, GATEWORLD_SANDBOX)
    marks = {"solve_step": None, "wakes_at_solve": None}

    def on_step(step, obs, result, events):
        if marks["solve_step"] is None and any(e.type == "goal_reached" for e in events):
            marks["solve_step"] = step + 1            # decisions taken to reach the goal
            marks["wakes_at_solve"] = brain.woke
        if args.verbose:
            pose = (obs.data.get("pose") or {}).get("value")
            inv = (obs.data.get("inventory") or {}).get("has_item")
            print(f"  [{step:03d}] pose={pose} item={inv} mode={brain.mode} "
                  f"think={brain.last_thought!r}")

    print(f"\n=== theme: {theme.name} ===")
    run_episode(gateway, world, brain, agent_id, max_steps=args.max_steps, on_step=on_step)
    return {"theme": theme.name, "solved": world.solved,
            "solve_step": marks["solve_step"], "wakes_at_solve": marks["wakes_at_solve"]}


def verdict(results: dict) -> str:
    fam = results.get("familiar", {}).get("solved")
    nov = results.get("novel", {}).get("solved")
    if fam and nov:
        return "REASONING that transfers — solved BOTH skins (familiar and novel)."
    if fam and not nov:
        return "RECALL-LEANING — solved the familiar skin but NOT the novel one (leaned on the prior)."
    if not fam and not nov:
        return "CANNOT do class-2 gating yet — solved NEITHER skin."
    return "MIXED — solved the novel skin but not the familiar (unexpected; inspect the trace)."


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the GateWorld gating probe (reasoning vs recall).")
    ap.add_argument("--brain", choices=["scripted", "llm"], default="scripted",
                    help="scripted = free oracle reasoner (plumbing check); llm = real measurement")
    ap.add_argument("--backend", choices=["ollama", "llamacpp", "aria"], default="aria")
    ap.add_argument("--model", default=None)
    ap.add_argument("--llm-url", default=None)
    ap.add_argument("--llm-token", default=os.environ.get("ARIA_BEARER_TOKEN"))
    ap.add_argument("--max-steps", type=int, default=80)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.brain == "llm" and args.backend == "aria" and not args.llm_token:
        print("\n--brain llm --backend aria needs a bearer token (--llm-token or "
              "$ARIA_BEARER_TOKEN).\n", file=sys.stderr)
        return 2

    results = {}
    for theme in (FAMILIAR, NOVEL):
        r = run_one(theme, args)
        results[theme.name] = r
        print(f"  -> solved={r['solved']}  solve_step={r['solve_step']}  "
              f"reasoner_wakes_at_solve={r['wakes_at_solve']}")

    print("\n=== gating-probe verdict ===")
    for name, r in results.items():
        flag = "PASS" if r["solved"] else "FAIL"
        detail = (f"solved in {r['solve_step']} decisions, {r['wakes_at_solve']} reasoner wakes"
                  if r["solved"] else "did not reach the goal")
        print(f"  {name:9s}: {flag}  ({detail})")
    print(f"\n  {verdict(results)}")
    if args.brain == "scripted":
        print("  (scripted oracle = plumbing check + upper bound; rerun with --brain llm for the "
              "real reasoning-vs-recall measurement.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
