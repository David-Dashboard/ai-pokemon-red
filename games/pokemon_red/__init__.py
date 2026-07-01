"""Pokémon Red world package (a lean PerceptionPlugin world, like cave_noire/gauntlet).

Ships per-world CONFIG only: the sandbox and a `PokemonRedPlugin` (the shared
`core.perception_plugin.PerceptionPlugin` wired with Pokémon's flavor text). The brain (`core/`) and the
world-interface infra (the plugin body) are reused UNCHANGED — only this config, the perceiver
(`perceiver.py`, unchanged from Iteration 02), and Pokémon's own fade-aware `emulator.py` differ.

The heavy `GamePlugin` (`plugin.py` + `reward.py`: RAM-based observe, reward shaping, battle-settle
pacing) was archived to `_archive/` when Red was wired into the game-agnostic MCP seam (`world_mcp.py`) —
see `_archive/plugin.py` for the pre-seam implementation it replaces.
"""
from core.permissions import Allowlist

from .plugin import PokemonRedPlugin

# The sandbox for this world: exactly the in-game button tools (the plugin exposes no others). Lives
# here, beside the world it secures, not in core/ — core stays game-agnostic.
POKEMON_SANDBOX = Allowlist({"press_button", "press_sequence", "wait"})

__all__ = ["PokemonRedPlugin", "POKEMON_SANDBOX"]
