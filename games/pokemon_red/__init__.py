"""Pokémon Red world plugin (emulator-driven, real-world regime).

This is the testbed's stand-in for "a real desktop": a live, open-ended,
stateful program the agent drives through button presses. Per CONTRACT.md
it implements `GamePlugin` ONLY — never `Replayable`. An open-world RPG has
no clean reset/terminal, which is precisely why emulators and the real
desktop share a classification.
"""

from core.permissions import Allowlist

from .plugin import PokemonRedPlugin

# The sandbox for this world: exactly the in-game button tools (the plugin exposes no others). Lives
# here, beside the world it secures, not in core/ — core stays game-agnostic.
POKEMON_SANDBOX = Allowlist({"press_button", "press_sequence", "wait"})

# Pokémon's tailored planner prompt (turn-then-move semantics + the optional GOTO directive). Passed
# to LLMButtonBrain(system=...) by the Pokémon drivers; core/ ships only a neutral default.
POKEMON_SYSTEM = (
    "You are playing Pokémon Red (top-down view). You control the small trainer "
    "sprite. Your job right now is to EXPLORE — walk to doors, stairs, and exits to "
    "reach new areas.\n"
    "Move with the d-pad. A single tap only TURNS you to face that way, so send a "
    "direction 2-4 times to actually walk, e.g. 'down down down'. Press A ONLY to "
    "talk to a person or confirm a dialog box; do NOT press A in an empty room. "
    "Never press START or SELECT.\n"
    "IN A BATTLE (your Pokémon at the bottom, the foe at the top): when the four options "
    "FIGHT / PKMN / ITEM / RUN are shown, move the cursor with the d-pad and press A — pick FIGHT "
    "to attack. A move list then appears; press up/down to highlight a move and A to use it (your "
    "first move is a fine default if unsure). Pressing A also advances battle text. You can't RUN "
    "from a trainer battle, and you rarely need ITEM or PKMN — focus on attacking.\n"
    "Reply in this format. THINK and MOVE are required; GOTO and LESSON are optional:\n"
    "THINK: <one short sentence — what you see and what you'll do>\n"
    "MOVE: <2-4 buttons separated by spaces, from: up down left right a b>\n"
    "GOTO: x y   (optional) send yourself to a known map cell (coordinates are shown when "
    "available); a free pathfinder then walks you there over the next steps, so you needn't "
    "steer every tile.\n"
    "LESSON: <one short lesson>   (optional) record something durable you learned THIS run — what "
    "blocked you, what actually worked, or where you really are. It is remembered and shown back "
    "to you on later turns this run only (it does not carry over to future runs)."
)

__all__ = ["PokemonRedPlugin", "POKEMON_SANDBOX", "POKEMON_SYSTEM"]
