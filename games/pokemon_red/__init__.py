"""Pokémon Red world package — a lean PerceptionPlugin world (like cave_noire/gauntlet).

Ships per-world CONFIG only: the sandbox + a thin `PokemonRedPlugin` that IS the shared
`core.perception_plugin.PerceptionPlugin` wired with Pokémon flavor text (same pattern as
`games/cave_noire/__init__.py`). The brain (`core/`), the PerceptionPlugin body, and the perceiver
(`perceiver.py`, unchanged from Iteration 02) are reused as-is; only this config differs.

Known gap (tracked, perception follow-up): the perceiver's fade-based warp signal — `context['transition']`,
backed by `emulator.py`'s `faded()` — is NOT wired through the lean PerceptionPlugin path, so Red falls back
to the best-shift residual for warp detection. (The generic `core/gb_emulator.PyBoyEmulator` the base builds
does not expose `faded()`.)

The heavy pre-seam `GamePlugin` (RAM-based observe, RewardTracker, battle-settle pacing) was archived to
`_archive/plugin.py` + `_archive/reward.py` when Red was wired into the game-agnostic MCP seam (`world_mcp.py`).
"""
from __future__ import annotations

from core.perception_plugin import PerceptionPlugin
from core.permissions import Allowlist

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


# The sandbox for this world: exactly the in-game button tools (the plugin exposes no others). Lives
# here, beside the world it secures, not in core/ — core stays game-agnostic.
POKEMON_SANDBOX = Allowlist({"press_button", "press_sequence", "wait"})

__all__ = ["PokemonRedPlugin", "POKEMON_SANDBOX"]
