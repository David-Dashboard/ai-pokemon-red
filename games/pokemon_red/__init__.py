"""Pokémon Red world plugin (emulator-driven, real-world regime).

This is the testbed's stand-in for "a real desktop": a live, open-ended,
stateful program the agent drives through button presses. Per CONTRACT.md
it implements `GamePlugin` ONLY — never `Replayable`. An open-world RPG has
no clean reset/terminal, which is precisely why emulators and the real
desktop share a classification.
"""

from .plugin import PokemonRedPlugin

__all__ = ["PokemonRedPlugin"]
