"""Cave Noire world package (the THIRD world; fixed-camera class).

Ships per-world CONFIG only: the sandbox, a THIN system prompt, and a `CaveNoirePlugin` (the shared
`core.perception_plugin.PerceptionPlugin` wired with Cave Noire's flavor text). The brain (`core/`) and
the world-interface infra (emulator + plugin body) are reused UNCHANGED — only this config and the
perceiver differ. Imports only `core/` + its own modules (never a sibling game): the import-boundary wall.
"""
from core.perception_plugin import PerceptionPlugin
from core.permissions import Allowlist

CAVE_NOIRE_SANDBOX = Allowlist({"press_button", "press_sequence", "wait"})

_BUTTON_DESC = ("Press one Game Boy button (a, b, start, select, up, down, left, right). "
                "The d-pad moves one step; A acts (interact / pick up); START/SELECT open menus.")
_SEQUENCE_DESC = ("Press several buttons in order in one call — efficient for walking a few steps. "
                  "Moves are 4-directional (no diagonals).")
_RENDER_HEADER = "Top-down dungeon exploration. Perception is approximate; a screenshot is attached."

# A THIN per-world prompt: identity + controls + goal only (NO game-specific strategy — keeping it thin
# is the constancy result we want). Reuses the exact THINK/MOVE/GOTO contract the parser depends on.
CAVE_NOIRE_SYSTEM = (
    "You are playing Cave Noire (top-down view), a turn-based dungeon. You control an explorer. Your job "
    "right now is to EXPLORE — move down open passages toward unexplored areas.\n"
    "Move one step at a time with the d-pad (4 directions, no diagonals). Press A to act (interact / pick "
    "up). The game waits for your input, so there is no time pressure.\n"
    "Reply in this format. THINK and MOVE are required; GOTO is optional:\n"
    "THINK: <one short sentence — what you see and what you'll do>\n"
    "MOVE: <1-4 buttons separated by spaces, from: up down left right a>\n"
    "GOTO: x y   (optional) send yourself to a known map cell (coordinates are shown when available); "
    "a free pathfinder then walks you there over the next steps."
)


class CaveNoirePlugin(PerceptionPlugin):
    """The shared perception-only plugin with Cave Noire's flavor text (4-dir moves; A acts)."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("out_dir", "runs/cave_noire")
        kwargs.setdefault("button_desc", _BUTTON_DESC)
        kwargs.setdefault("sequence_desc", _SEQUENCE_DESC)
        kwargs.setdefault("render_header", _RENDER_HEADER)
        super().__init__(**kwargs)


__all__ = ["CaveNoirePlugin", "CAVE_NOIRE_SANDBOX", "CAVE_NOIRE_SYSTEM"]
