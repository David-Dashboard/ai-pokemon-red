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
    "Reply in EXACTLY this format and nothing else:\n"
    "THINK: <one short sentence — what you see and what you'll do>\n"
    "MOVE: <2-4 buttons separated by spaces, from: up down left right a b>\n"
    "Optionally add a final line 'GOTO: x y' to send yourself to a known map cell "
    "(coordinates are shown when available); a free pathfinder then walks you there over the "
    "next steps, so you needn't steer every tile."
)

__all__ = ["PokemonRedPlugin", "POKEMON_SANDBOX", "POKEMON_SYSTEM"]
