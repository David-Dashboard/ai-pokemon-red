"""PokemonRedPlugin — the shared perception-only PerceptionPlugin with Pokémon Red's flavor text.

Same pattern as `games/cave_noire/__init__.py` / `games/gauntlet/__init__.py`: this class sets Pokémon's
flavor defaults (out_dir, button/sequence descriptions, render header) and inherits observe / tools /
handle / watch->oracle / _extra_context UNCHANGED from `core.perception_plugin.PerceptionPlugin`. The
heavy pre-seam `GamePlugin` (RAM observe, RewardTracker, battle-settle pacing) lives in `_archive/`.
"""
from __future__ import annotations

from core.perception_plugin import PerceptionPlugin

_BUTTON_DESC = ("Press one Game Boy button (a, b, start, select, up, down, left, right). "
                "The d-pad walks one step; A confirms/interacts/advances dialog; B cancels.")
_SEQUENCE_DESC = ("Press several buttons in order in one call — efficient for walking a few tiles "
                  "or stepping through a menu.")
_RENDER_HEADER = "Overworld exploration. Perception is approximate; a screenshot is attached."


class PokemonRedPlugin(PerceptionPlugin):
    """The shared perception-only plugin with Pokémon Red's flavor text (d-pad walks; A confirms)."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("out_dir", "runs/pokemon_red")
        kwargs.setdefault("button_desc", _BUTTON_DESC)
        kwargs.setdefault("sequence_desc", _SEQUENCE_DESC)
        kwargs.setdefault("render_header", _RENDER_HEADER)
        super().__init__(**kwargs)
