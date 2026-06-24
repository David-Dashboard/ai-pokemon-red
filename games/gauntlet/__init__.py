"""Gauntlet II world package (the SECOND world, for the constancy test).

Ships per-world CONFIG only: the sandbox, a THIN system prompt, and a `GauntletPlugin` (the shared
`core.perception_plugin.PerceptionPlugin` wired with Gauntlet's flavor text). The brain (`core/`) and the
world-interface infra (emulator + plugin body) are reused UNCHANGED — only this config and the perceiver
differ. Imports only `core/` + its own modules (never a sibling game): the import-boundary wall.
"""
from core.perception_plugin import PerceptionPlugin
from core.permissions import Allowlist

# The sandbox: exactly the in-game button tools (same shape as Pokemon's; the semantics differ, not the code).
GAUNTLET_SANDBOX = Allowlist({"press_button", "press_sequence", "wait"})

_BUTTON_DESC = ("Press one Game Boy button (a, b, start, select, up, down, left, right). "
                "The d-pad walks; B fires; A/START advance the title/hero-select.")
_SEQUENCE_DESC = ("Press several buttons in order in one call — efficient for walking a few steps. "
                  "Diagonals are two presses (e.g. up then left).")

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


class GauntletPlugin(PerceptionPlugin):
    """The shared perception-only plugin with Gauntlet's flavor text (the d-pad walks; B fires)."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("out_dir", "runs/gauntlet")
        kwargs.setdefault("button_desc", _BUTTON_DESC)
        kwargs.setdefault("sequence_desc", _SEQUENCE_DESC)
        super().__init__(**kwargs)


__all__ = ["GauntletPlugin", "GAUNTLET_SANDBOX", "GAUNTLET_SYSTEM"]
