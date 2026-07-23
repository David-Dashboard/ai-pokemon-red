"""F4 name->place probe driver (headless, $0, NO LLM).  See reports/2026-07-23-f4-name-place-probe.md.

Reuses the LIVE perception path: PokemonRedPlugin (fade-aware PerceptionPlugin) + the free
ExploreBrain autopilot. The perceiver sees pixels only; map_id (0xD35E) is read ONLY for offline
scoring (never fed to the perceiver) -> the no-leak posture is preserved. A driver-side
anti-absorption burst forces the explorer back out of Oak's lab so the trajectory REVISITS places.

Emits trace.jsonl: {step, map_id (oracle), area (coined place_id), warped, conf, context, thought}.

Run from the repo root (needs roms/PokemonRed.gb + runs/red_start.state, both gitignored):
  UV_PROJECT_ENVIRONMENT=.venv-win UV_NATIVE_TLS=true uv run --frozen python \
    reports/probes/2026-07-23-f4/f4_drive.py --steps 4000 --seed 3 --out runs/f4_esc
"""
from __future__ import annotations
import argparse, json, os, random, sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)

from core.contracts import ToolCall
from core.brains import ExploreBrain
from games.pokemon_red import PokemonRedPlugin
from games.pokemon_red.perceiver import OverworldPerceiver

ADDR_MAP_ID = 0xD35E
RED_WATCH = {"x": 0xD362, "y": 0xD361, "map": 0xD35E, "party": 0xD163, "badges": 0xD356}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default=os.path.join(REPO, "roms/PokemonRed.gb"))
    ap.add_argument("--state", default=os.path.join(REPO, "runs/red_start.state"))
    ap.add_argument("--steps", type=int, default=4000)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    random.seed(args.seed)
    os.makedirs(args.out, exist_ok=True)

    plugin = PokemonRedPlugin(rom_path=args.rom, init_state=args.state,
                              perceiver=OverworldPerceiver(), watch=RED_WATCH,
                              out_dir=args.out, headless=True)
    explore = ExploreBrain("f4", single_step=True, probe_interactables=True)

    DIRS = ["up", "down", "left", "right"]
    trace = open(os.path.join(args.out, "trace.jsonl"), "w", encoding="utf-8")
    cid = 0
    prev_map = None
    same_map = 0
    rnd_budget = 0
    for i in range(args.steps):
        obs = plugin.observe("f4")
        map_id = int(plugin.emu.read(ADDR_MAP_ID))          # SCORING ONLY, never to perceiver
        area = (obs.data.get("pose") or {}).get("area")
        warped = (prev_map is not None and map_id != prev_map)
        same_map = 0 if warped else same_map + 1
        if warped:
            rnd_budget = 0
        rec = {"step": i, "map_id": map_id, "area": area, "warped": warped,
               "conf": obs.data.get("confidence"), "context": obs.data.get("context")}

        if same_map > 50 and rnd_budget == 0:
            rnd_budget = 80                                  # sustained escape burst out of a big room
        if rnd_budget > 0:
            buttons = [random.choice(DIRS)]; rnd_budget -= 1; rec["thought"] = "escape:random"
        else:
            call = explore.decide(obs, [], {})
            if call is None:
                buttons = [random.choice(DIRS)]; rec["thought"] = "exhausted:random"
            else:
                buttons = [b for b in (call.args.get("buttons") or [call.args.get("button")]) if b] \
                          or [random.choice(DIRS)]
                rec["thought"] = getattr(explore, "last_thought", "")
        trace.write(json.dumps(rec) + "\n")
        cid += 1
        plugin.handle(ToolCall(tool="press_sequence", args={"buttons": buttons},
                               agent_id="f4", call_id=f"c{cid}"))
        prev_map = map_id
    trace.close()
    print(f"done: {args.steps} steps -> {args.out}/trace.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
