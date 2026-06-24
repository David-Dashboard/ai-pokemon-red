"""Gauntlet II world package (the SECOND world, for the constancy test).

Ships the GamePlugin + perceiver + sandbox + a THIN system prompt. The brain (`core/`) is reused
UNCHANGED — only this per-world package and its prompt differ. Imports only `core/` + its own modules
(never a sibling game): the import-boundary wall.
"""
from core.permissions import Allowlist

from .plugin import GauntletPlugin

# The sandbox: exactly the in-game button tools (same shape as Pokemon's; the semantics differ, not the code).
GAUNTLET_SANDBOX = Allowlist({"press_button", "press_sequence", "wait"})

# A THIN per-world prompt: identity + controls + goal only (NO game-specific strategy — keeping it thin is
# the constancy result we want). Reuses the exact THINK/MOVE/GOTO contract the parser depends on.
GAUNTLET_SYSTEM = (
    "You are playing Gauntlet II (top-down view). You control a hero in a continuous maze. Your job "
    "right now is to EXPLORE — walk down open corridors toward unexplored areas.\n"
    "Move with the d-pad. Press B to FIRE in the direction you face. A and START are rarely needed "
    "(mainly to start the game / pick a hero). A diagonal is two presses (e.g. 'up left').\n"
    "Reply in this format. THINK and MOVE are required; GOTO is optional:\n"
    "THINK: <one short sentence — what you see and what you'll do>\n"
    "MOVE: <2-4 buttons separated by spaces, from: up down left right a b>\n"
    "GOTO: x y   (optional) send yourself to a known map cell (coordinates are shown when available); "
    "a free pathfinder then walks you there over the next steps."
)

__all__ = ["GauntletPlugin", "GAUNTLET_SANDBOX", "GAUNTLET_SYSTEM"]
