"""GateWorld — a synthetic gating probe (means-ends reasoning with backtracking).

See reports/2026-06-15-gating-probe-spec.md and games/gateworld/world.py.
"""
from core.permissions import Allowlist

from .solver import ScriptedReasoner
from .world import FAMILIAR, GATE_MAP, GateWorld, NOVEL, Theme

# Same button contract as the Pokémon sandbox, but owned by this world — core/ stays game-agnostic.
GATEWORLD_SANDBOX = Allowlist({"press_button", "press_sequence", "wait"})

__all__ = ["GateWorld", "Theme", "FAMILIAR", "NOVEL", "GATE_MAP", "ScriptedReasoner",
           "GATEWORLD_SANDBOX"]
