"""Free closed-loop validation of the AFFORDANCE layer (interaction-probe + motion-saliency), NO API.
The harness lesson: validate the LOOP, not just primitives. We run the real ROM from start.state with
the free autopilot (single-step + probe) wrapped in a HybridBrain whose fallback is a scripted 'press A'
(stands in for the paid LLM: it advances dialog and accepts menu choices). So the agent navigates +
probes for free, and the only thing we're testing is whether the probe actually finds Oak / a Pokeball
and triggers the starter — RAM is read only as the oracle (party count, map, battle).

Run: uv run python -m eval.probe_loop [steps]
"""
from __future__ import annotations

import sys

from core.brains import ExploreBrain, HybridBrain, _call
from core.gateway import Gateway
from core.runner import run_episode
from games.pokemon_red import POKEMON_SANDBOX
from games.pokemon_red.memory_map import ADDR_IS_IN_BATTLE, ADDR_MAP_ID, ADDR_PARTY_COUNT
from games.pokemon_red.perceiver import OverworldPerceiver
from games.pokemon_red.plugin import PokemonRedPlugin

ROM = "roms/PokemonRed.gb"
STATE = "start.state"
STEPS = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
AID = "a"


class PressA:
    """Stand-in for the paid LLM: at any real decision (a menu/choice/battle) just press A — enough to
    advance dialog and accept the starter's YES/NO. The point is to test the PROBE, not the planner."""
    agent_id = AID
    goto = None
    lesson = None
    last_thought = "press A"

    def decide(self, obs, tools, context):
        return _call("press_button", {"button": "a"}, AID)


def main() -> int:
    plugin = PokemonRedPlugin(rom_path=ROM, out_dir="runs/probe_loop", headless=True,
                              init_state=STATE, perceiver=OverworldPerceiver())
    gw = Gateway(plugin, POKEMON_SANDBOX)
    brain = HybridBrain(ExploreBrain(AID, single_step=True, probe_interactables=True),
                        PressA(), advance_on_dialog=True)
    R = plugin.emu.read
    trace = {"maps": [], "probes": 0, "got_starter_step": None, "battle_step": None}

    def on_step(step, obs, result, events):
        m = R(ADDR_MAP_ID)
        if not trace["maps"] or trace["maps"][-1] != m:
            trace["maps"].append(m)
        if "probe interactable" in getattr(brain, "last_thought", ""):
            trace["probes"] += 1
        if trace["got_starter_step"] is None and R(ADDR_PARTY_COUNT) > 0:
            trace["got_starter_step"] = step
            print(f"  [step {step}] *** GOT A STARTER (party_count={R(ADDR_PARTY_COUNT)}) on map {m} ***")
        if trace["battle_step"] is None and R(ADDR_IS_IN_BATTLE):
            trace["battle_step"] = step
            print(f"  [step {step}] entered a battle on map {m}")
        if step % 150 == 0:
            print(f"  [step {step}] map={m} party={R(ADDR_PARTY_COUNT)} in_battle={R(ADDR_IS_IN_BATTLE)} "
                  f"probes={trace['probes']}")

    print(f"running the free autopilot+probe loop for {STEPS} steps from {STATE} ...")
    run_episode(gw, plugin, brain, AID, max_steps=STEPS, on_step=on_step)
    plugin.close()

    print("\n=== RESULT ===")
    print("map trajectory:", trace["maps"])
    print("reached Oak's lab (map 40):", 40 in trace["maps"])
    print("interaction-probes fired:", trace["probes"])
    print("GOT THE STARTER:", trace["got_starter_step"] is not None,
          f"(step {trace['got_starter_step']})" if trace["got_starter_step"] else "")
    print("entered a battle:", trace["battle_step"] is not None,
          f"(step {trace['battle_step']})" if trace["battle_step"] else "")
    ok = trace["got_starter_step"] is not None
    print("\nVERDICT:", "PASS — the probe reached an interactable and got the starter for $0"
          if ok else "INCOMPLETE — did not get the starter; see trajectory/probes above")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
