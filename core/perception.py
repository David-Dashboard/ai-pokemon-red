"""Perception seam (Iteration 02): screen -> SymbolicState.

The agent plans over a SymbolicState rather than raw pixels — and, by design, NEVER
over privileged RAM (RAM is demoted to a scoring oracle; see the plugin's oracle log).

The schema is ROLE-NAMED so the same contract holds across games and toward reality:
`pose` / `spatial_memory` / `affordances` / `last_action` / `confidence` are exactly a
mobile robot's belief state — only the *representation* behind each role is
environment-specific (a tile grid here; metric pose or a place-graph elsewhere). We keep
the names general now (free) and let a second environment force the real abstraction.

See reports/2026-06-13-iteration-02-perception-spec.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

JSON = dict[str, Any]


@dataclass(frozen=True)
class SymbolicState:
    """What the planner sees instead of pixels. JSON-serializable via to_dict()."""

    confidence: float = 0.0                  # 0..1; low ⇒ attach the raw frame + TELL the planner
    context: str = "unknown"                 # situation label (NOT a fixed game-mode enum)
    pose: Optional[JSON] = None              # where am I (estimated): {frame, value, uncertain}
    spatial_memory: Optional[JSON] = None    # what I've mapped: {kind: occupancy-grid|place-graph, ...}
    affordances: list = field(default_factory=list)  # what/where I can act from here (frontiers, options)
    last_action: Optional[JSON] = None       # {action, outcome} — did my last move change anything
    screen_text: str = ""                    # text read off the screen (e.g. a dialog box), "" if none
    raw_available: bool = True               # a richer observation (the image) can be attached
    raw_ref: str = ""                        # path/handle to that raw observation, when present

    def to_dict(self) -> JSON:
        return {
            "confidence": self.confidence,
            "context": self.context,
            "pose": self.pose,
            "spatial_memory": self.spatial_memory,
            "affordances": list(self.affordances),
            "last_action": self.last_action,
            "screen_text": self.screen_text,
            "raw_available": self.raw_available,
            "raw_ref": self.raw_ref,
        }


class PerceptMemory:
    """Per-run scratch the perceiver owns: calibration, the occupancy map, tile caches.
    Step 1: empty. Step 2+: odometry cursor, occupancy grid, learned tile semantics.
    Deliberately NOT the agent's narrative memory and NEVER holds RAM."""

    def __init__(self) -> None:
        self.data: JSON = {}


@runtime_checkable
class Perceiver(Protocol):
    """screen -> SymbolicState. `frame` is the raw observation (an image path or pixel array);
    `memory` is the perceiver's own persisted state; `context` carries auxiliaries the world can
    supply (the just-taken `last_action`, the frame's `frame_path` for the image fallback). The
    perceiver receives pixels only — it has no access to RAM, which makes the no-leak rule
    structural."""

    def perceive(self, frame: Any, memory: PerceptMemory,
                 context: Optional[JSON] = None) -> SymbolicState: ...


class StubPerceiver:
    """Step-1 placeholder: emits a low-confidence SymbolicState that just points at the raw
    frame, so the planner falls back to the image (today's behaviour) while the seam and the
    oracle exist end-to-end. No pixel work — that's the Step-2 OverworldPerceiver."""

    def perceive(self, frame: Any, memory: PerceptMemory,
                 context: Optional[JSON] = None) -> SymbolicState:
        raw_ref = frame if isinstance(frame, str) else (context or {}).get("frame_path", "")
        return SymbolicState(confidence=0.0, context="unknown",
                             raw_available=bool(raw_ref), raw_ref=raw_ref)
