"""GateWorld — a synthetic gating probe (means-ends reasoning with backtracking).

See reports/2026-06-15-gating-probe-spec.md and games/gateworld/world.py.
"""
from .solver import ScriptedReasoner
from .world import FAMILIAR, GATE_MAP, GateWorld, NOVEL, Theme

__all__ = ["GateWorld", "Theme", "FAMILIAR", "NOVEL", "GATE_MAP", "ScriptedReasoner"]
