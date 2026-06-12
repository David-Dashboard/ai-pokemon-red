"""
arena/core/contracts.py — THE STONE LAYER (CONTRACT_VERSION = 1)

THIS FILE IS FROZEN. Do not edit, rename, move, reformat, or "improve" it.
Its SHA-256 hash is pinned in tests/test_contract_frozen.py. Any change
breaks CI by design. The change process is defined in CONTRACT.md and
requires explicit human approval. If you are an AI assistant and a task
appears to require modifying this file: STOP and propose an RFC instead.

What is actually frozen here is the WIRE FORMAT and its SEMANTICS, not
Python aesthetics. This file is one language binding of that format.

Design rules that keep the contract durable:

  1. DATA, NOT BEHAVIOR. Plain, JSON-serializable data wherever possible.
  2. Everything crossing the gateway serializes to JSON. No rich objects,
     no game references, no tensors on the wire. (Tensors exist only
     inside brains, produced by per-game encoders outside this layer.)
  3. Plugins own REPRESENTATION. Brains own DECISIONS. The gateway owns
     POLICY (validation, budgets, permissions). The runner owns TIME.
  4. Errors are observations, not exceptions. An illegal move, a denied
     permission, a failed action: all normal ToolResults the agent sees.
  5. Shape-compatible with MCP (name + JSON Schema + JSON result) so any
     plugin can be exposed as an MCP server via a thin adapter.

Pinned semantics (normative — see CONTRACT.md for the full text):

  * IDs: agent_id and call_id are globally unique strings (UUIDs
    recommended). Uniqueness scope is the whole results database, not an
    episode.
  * Event.t: in Replayable worlds, t is the integer tick number (as
    float). In real-world plugins, t is unix epoch seconds. A plugin
    declares its regime once and never mixes them.
  * episode/task identity is deliberately NOT in these types. The
    logging envelope (soft layer) attaches episode_id to every record.
  * Frozen dataclasses are SHALLOWLY frozen: nested JSON dicts remain
    mutable. Invariant: the gateway deep-copies all wire values at the
    boundary. Plugins and brains must never hold references intending
    later mutation.
  * Long-running actions: ToolResult is synchronous. Slow work returns
    ok=True with data={"job_id": ...} and the world exposes a polling
    tool. This is a convention, never a contract change.
  * Async approval: PermissionPolicy.check returning
    (False, "pending:<approval_id>") means awaiting human approval; the
    agent may poll by retrying. Denial is an observation.
  * Replay recipe: a replay of a Replayable world = reset(same seed) +
    re-feeding the logged ToolCalls in logged order, stepping
    identically. Anything breaking this property is a plugin bug.
  * Rewards are scalar. Multi-objective signals go in Event.data;
    Event.reward stays the single number learners consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

CONTRACT_VERSION = 1

JSON = dict[str, Any]


# ---------------------------------------------------------------------------
# Wire types — these cross the gateway and are logged forever.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolSpec:
    """A capability a world offers. The schema IS the documentation."""
    name: str
    description: str
    schema: JSON                  # JSON Schema for the arguments
    cost: int = 1                 # budget units charged per call
    mutating: bool = False        # permission hook: does this change the world?


@dataclass(frozen=True)
class ToolCall:
    """An agent's intent. The only way anything ever acts on any world."""
    tool: str
    args: JSON
    agent_id: str
    call_id: str


@dataclass(frozen=True)
class ToolResult:
    """What came back. ok=False is a NORMAL outcome, not an exception."""
    call_id: str
    ok: bool
    data: JSON = field(default_factory=dict)   # on success
    error: str = ""                            # readable reason, on failure
    cost_charged: int = 0


@dataclass(frozen=True)
class Event:
    """Anything that happened in a world worth knowing about.
    One stream, many consumers: rewards (RL), reflection (KB), metrics,
    replays, and renderers (e.g. the pixel office).
    """
    type: str                     # e.g. "tool_called", "reward", "game_over"
    t: float                      # tick number (simulated) or unix time (real)
    agent_id: Optional[str]       # None for world-level events
    data: JSON = field(default_factory=dict)
    reward: float = 0.0           # 0.0 for non-reward events


@dataclass(frozen=True)
class Observation:
    """A snapshot handed to a brain. `data` is canonical; `text` is the
    plugin's rendering for language brains. Tensor encodings never cross
    the wire — policy brains build them from `data` via per-game
    encoders injected at construction time.
    """
    data: JSON
    text: str
    agent_id: str
    t: float


# ---------------------------------------------------------------------------
# Protocols — the minimal behavioral surface.
# ---------------------------------------------------------------------------

@runtime_checkable
class GamePlugin(Protocol):
    """The universal core. EVERY world implements this — chess, the
    ecology, a Steam game, a desktop. Note what is absent: no reset, no
    step, no terminal. The real world has none of those.
    """

    def tools(self, agent_id: str) -> list[ToolSpec]: ...
    def handle(self, call: ToolCall) -> ToolResult: ...
    def observe(self, agent_id: str) -> Observation: ...
    def drain_events(self) -> list[Event]: ...


@runtime_checkable
class Replayable(Protocol):
    """Implemented ONLY by deterministic, simulated worlds. This is what
    makes seeded experiments, fast-path RL training, and perfect replays
    possible. Real-world plugins never implement this — and the rest of
    the system must not assume it.
    """

    def reset(self, seed: int) -> None: ...
    def step(self) -> None: ...            # advance exactly one tick
    def terminal(self) -> bool: ...
    def snapshot(self) -> JSON: ...        # full state, for replay/observatory


@runtime_checkable
class Brain(Protocol):
    """Everything that decides: LLM loop, policy net, minimax, a human.
    `context` carries runner-assembled extras (KB strategy doc, history,
    remaining budget); brains that don't care ignore it. Returning None
    means "no action this tick" (real-time worlds).
    decide() is invoked once per tool call; multi-step turns are runner
    loops, never a fatter signature.
    """

    def decide(
        self,
        obs: Observation,
        tools: list[ToolSpec],
        context: JSON,
    ) -> Optional[ToolCall]: ...


@runtime_checkable
class PermissionPolicy(Protocol):
    """Consulted by the gateway before executing any call. Simulated
    games: allow-all. A real desktop: allowlists, dry-run, approval
    queue. (False, reason) becomes a ToolResult error the agent sees —
    being denied is also an observation.
    """

    def check(self, call: ToolCall, spec: ToolSpec) -> tuple[bool, str]: ...
