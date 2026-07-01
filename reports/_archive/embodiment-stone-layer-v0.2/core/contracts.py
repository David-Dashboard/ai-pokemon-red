"""
core/contracts.py — The Embodiment Stone Layer (FROZEN)
=======================================================
One language binding of the embodiment constitution in CONTRACT.md. This is
the SIBLING of the Arena tool-call stone layer: where that froze "agents act
on worlds via ToolCalls", this freezes "one Brain drives many embodiments by
NAMING skills" — spanning pixel-games · turn-based · RTS · FPS · desktop ·
drone/robot.

It is deliberately THIN. Per the Arena R11 lesson (over-freezing breeds a
schema zoo inside data blobs), only what is constant across every future we
can foresee is frozen here. Everything contested — risk ledgers, staleness
rejection, multi-agent stepping, severity thresholds — lives in the soft
layer and is catalogued for coding agents in HYPOTHESES.md.

WHAT IS FROZEN (the wire format and its semantics):
  · The four envelopes: Skill, Percept, Goal, Outcome.
  · The handle invariant: a Goal names a Skill.handle; it never carries
    coordinates, motor commands, or raw actions. (Free text rides in params
    as an opaque, untrusted value — never frozen structure.)
  · validate(goal, percept): a PURE, TOTAL function. Signature + purity are
    frozen; the body checks only menu-membership and primitive params.
  · The registry MECHANISM and its SEED vocabulary. Domains EXTEND the
    registries at runtime (register_*), which edits no frozen file.

WHAT IS NOT FROZEN (see CONTRACT.md §5 and HYPOTHESES.md):
  perception structure (entities/raster/state ride in Percept.data),
  reversibility severity/thresholds, the risk ledger, staleness rejection,
  the Controller/Gateway implementations, multi-agent arbitration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable

CONTRACT_VERSION = 1


# ===================================================== VERSIONED VOCABULARY
# Freeze the grammar, version the vocabulary. The SEED members below are part
# of the frozen file (changing a seed is an RFC). Domains add new terms at
# RUNTIME via register_*(), which mutates these sets in memory and edits no
# frozen path — that is the sanctioned extension mechanism, not a contract change.

FRAMES: set[str] = {"pixel", "grid", "world", "none"}
COST_DIMS: set[str] = {"financial", "physical", "visibility", "data_loss"}
VERBS: set[str] = {"move", "click", "type", "navigate", "engage",
                   "craft", "select", "read", "waypoint"}
SKILL_STATUS: set[str] = {"success", "failure", "aborted", "timeout", "invalid"}
EPISODE_STATUS: set[str] = {"running", "won", "lost", "truncated"}

# Param types split into two classes:
#   PRIMITIVE  — validate() can check these centrally (parse / membership).
#   REFERENCE  — point into Percept.data, whose shape is SOFT; the plugin/
#                gateway checks them. validate() lets them pass through.
PRIMITIVE_PARAM_TYPES: set[str] = {"int", "float", "enum", "string"}
REFERENCE_PARAM_TYPES: set[str] = {"element_id", "selection", "map_point", "waypoint"}

def register_frame(name: str) -> None: FRAMES.add(name)
def register_cost_dim(name: str) -> None: COST_DIMS.add(name)
def register_verb(name: str) -> None: VERBS.add(name)
def register_skill_status(name: str) -> None: SKILL_STATUS.add(name)
def register_param_type(name: str, *, reference: bool = False) -> None:
    (REFERENCE_PARAM_TYPES if reference else PRIMITIVE_PARAM_TYPES).add(name)


# ============================================================= THE ENVELOPES
# Frozen dataclasses, plain-JSON only. No tensors, no rich objects on the wire
# (Arena invariant 3). Nested dicts are only shallowly frozen — the gateway
# deep-copies at the boundary; no component mutates a wire value after sending.

@dataclass(frozen=True)
class Skill:
    """One offered action in the Percept's menu. Enumerable even when the
    underlying action space is continuous: the Controller realizes the
    continuous part, the Brain only names this handle.

    reversible/cost are an UNTRUSTED HINT from the plugin. The Gateway
    reconciles them against external policy and may only RAISE risk
    (see HYPOTHESES.md, Vesper-1). Human-readable 'severity' is COMPUTED
    in the soft layer from cost — never stored here.
    """
    handle: str
    verb: str
    params: dict[str, str] = field(default_factory=dict)        # name -> param-type
    enums: dict[str, list[str]] = field(default_factory=dict)   # for params typed "enum"
    reversible: bool = True
    cost: dict[str, float] = field(default_factory=dict)        # CostDim -> magnitude; {} = trivial
    duration: str = "extended"                                  # "instant" | "extended"
    data: dict = field(default_factory=dict)                    # SOFT per-domain escape hatch


@dataclass(frozen=True)
class Percept:
    """Everything the Brain sees for one decision. The skills menu is the ONLY
    thing strictly required to choose a Goal. Perception STRUCTURE
    (entities / raster / state / set-of-marks) is deliberately NOT frozen — it
    rides in `data` as a soft per-domain convention, with `text` as the compact
    render for LLM brains.

    `timestep` follows the Arena two-regime rule: simulated worlds use the tick
    number (as float); real-world embodiments use unix epoch seconds. A plugin
    declares one regime and never mixes them.
    """
    timestep: float
    frame: str = "none"                                         # a registered FRAME
    episode: str = "running"                                    # a registered EPISODE_STATUS
    skills: list[Skill] = field(default_factory=list)
    text: str = ""                                              # compact render for LLM context
    data: dict = field(default_factory=dict)                   # entities/raster/state/etc. (SOFT)


@dataclass(frozen=True)
class Goal:
    """The Brain's output. `skill` MUST match an offered Skill.handle; `params`
    MUST satisfy that skill's `params`. One decision per invocation: multi-step
    turns are runner loops calling the Brain repeatedly, never a fatter Goal.

    `percept_timestep` records which world the goal was computed against. The
    FIELD is frozen; the staleness/TOCTOU REJECTION RULE is soft (it conflicts
    with simultaneous-move multi-agent — see HYPOTHESES.md, Nexus-2).
    """
    skill: str
    params: dict[str, str] = field(default_factory=dict)
    percept_timestep: float = -1.0                             # -1 = unbound
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Outcome:
    """What came back. Mirrors the Arena conventions: errors are observations
    (ok=False with a readable error and useful data, never an exception across
    the boundary); reward is a single scalar (multi-objective signals ride in
    data); async approval is `ok=False, error="pending:<id>"` with the id echoed
    in data, polled by retry.
    """
    ok: bool
    status: str = "success"                                    # a registered SKILL_STATUS
    reward: float = 0.0
    error: str | None = None
    episode: str = "running"                                   # a registered EPISODE_STATUS
    data: dict = field(default_factory=dict)


# ================================================================ VALIDATOR
# The single source of goal-coherence truth and the anchor for golden vectors.
# PURE and TOTAL: no I/O, deterministic, same answer for the same inputs.
# Brain MAY call it to fail fast; Gateway MUST call it as the trust boundary.
# Permission/risk is the Gateway's SEPARATE job and is not done here.

@dataclass(frozen=True)
class Issue:
    code: str                                                  # UNKNOWN_SKILL, MISSING_PARAM, ...
    message: str
    param: str | None = None


def validate(goal: Goal, percept: Percept) -> list[Issue]:
    issues: list[Issue] = []
    menu = {s.handle: s for s in percept.skills}
    skill = menu.get(goal.skill)
    if skill is None:
        return [Issue("UNKNOWN_SKILL", f"{goal.skill!r} not in offered menu")]

    for name in skill.params:
        if name not in goal.params:
            issues.append(Issue("MISSING_PARAM", "required param absent", name))
    for name in goal.params:
        if name not in skill.params:
            issues.append(Issue("UNKNOWN_PARAM", "not in skill.params", name))

    for name, ptype in skill.params.items():
        if name not in goal.params:
            continue
        val = goal.params[name]
        if ptype in ("int", "float"):
            try:
                (int if ptype == "int" else float)(val)
            except (TypeError, ValueError):
                issues.append(Issue("BAD_PARAM", f"not a {ptype}: {val!r}", name))
        elif ptype == "enum":
            allowed = skill.enums.get(name, [])
            if val not in allowed:
                issues.append(Issue("BAD_PARAM", f"{val!r} not in {allowed}", name))
        # REFERENCE_PARAM_TYPES (element_id/selection/map_point/waypoint) and any
        # opaque "string"/registered type are intentionally NOT checked here:
        # they resolve against the SOFT Percept.data shape, so the plugin/gateway
        # validates them. Frozen validate() stays independent of data structure.
    return issues


# ===================================================== FILLABLE SEAMS (soft)
# Protocols define the boundary; their bodies are SOFT and implemented per
# domain. A DomainPlugin generalizes the Arena GamePlugin to non-game
# embodiments. Real-world embodiments implement DomainPlugin only — never fake
# Replayable (you cannot reset a drone).

@runtime_checkable
class DomainPlugin(Protocol):
    name: str
    resettable: bool
    def perceive(self) -> Percept: ...
    def skills(self, percept: Percept) -> list[Skill]: ...
    def execute(self, goal: Goal) -> Outcome: ...              # resolve handle + advance world


@runtime_checkable
class Replayable(Protocol):
    """Deterministic simulated worlds only. Real-world plugins never implement
    this. Replay = reset(same seed) + re-feed logged Goals in order."""
    def reset(self, seed: int) -> Percept: ...
    def terminal(self) -> bool: ...


@runtime_checkable
class Controller(Protocol):
    """Turns ONE extended Goal into low-level action at the embodiment's control
    rate. Identity for instant skills (pixel-games); the autopilot for drones;
    for desktop the intelligence is in done() (post-condition verification), not
    step(). The Brain is never inside this loop."""
    rate_hz: float
    def begin(self, goal: Goal, percept: Percept) -> None: ...
    def step(self, percept: Percept): ...                      # concrete action (domain-private)
    def done(self, percept: Percept) -> bool: ...              # SKILL termination (≠ episode)
    def result(self) -> Outcome: ...


@runtime_checkable
class Brain(Protocol):
    """Domain-agnostic deliberator. Sees the Percept (incl. each Skill's
    reversibility), owns its own belief/memory, returns ONE Goal per call."""
    def decide(self, percept: Percept, history: list[Outcome]) -> Goal: ...


@runtime_checkable
class Gateway(Protocol):
    """The single door. MUST call validate() on every goal, then apply
    permission/risk policy. Denials and approvals-pending are Outcomes
    (ok=False), never exceptions. Risk-ledger semantics are SOFT (HYPOTHESES.md,
    Vesper-2 / Witness-1)."""
    def authorize(self, goal: Goal, percept: Percept) -> Outcome: ...
