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
    "IN A BATTLE: FIRST read the screen — name YOUR Pokémon (shown at the bottom) and the FOE "
    "(top) from the image and the on-screen text before you decide; do not assume which Pokémon is "
    "yours. When FIGHT / PKMN / ITEM / RUN appear, pick FIGHT — then in the move list choose a move "
    "that DEALS DAMAGE. Do NOT just mash A: the highlighted move may be a non-damaging status move "
    "(GROWL, TAIL WHIP, LEER only lower stats — they never reduce the foe's HP), so wasting turns on "
    "it can't win. Use up/down to land on an ATTACKING move (prefer one that's super-effective against "
    "the foe's type), then press A. You are only woken at a DECISION — the action menu "
    "(FIGHT / PKMN / ITEM / RUN) or the move list; the battle narration is auto-advanced for you (the "
    "text since your last decision is provided), so when you are woken you are AT a menu: make a "
    "choice, don't just try to advance text. You can't RUN a trainer "
    "battle and rarely need ITEM or PKMN — keep attacking until the foe faints.\n"
    "Reply in this format. THINK and MOVE are required; GOTO is optional:\n"
    "THINK: <one short sentence — what you see and what you'll do>\n"
    "MOVE: <2-4 buttons separated by spaces, from: up down left right a b>\n"
    "GOTO: x y   (optional) send yourself to a known map cell (coordinates are shown when "
    "available); a free pathfinder then walks you there over the next steps, so you needn't "
    "steer every tile."
    # NOTE (S3 beta): the harness no longer advertises a plain `LESSON:` line. aria owns within-run
    # memory and already teaches its native <lesson>/<note> tags (its own memory protocol); those tags
    # are parsed + stripped by aria before the reply, so they never reach the harness THINK/MOVE parser.
)

__all__ = ["PokemonRedPlugin", "POKEMON_SANDBOX", "POKEMON_SYSTEM"]
