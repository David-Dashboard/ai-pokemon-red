# HYPOTHESES.md — What Is NOT Frozen, and How to Build It

This file exists so coding agents do not mistake a *deliberate deferral* for a
*missing feature* and "helpfully" freeze a guess into `core/contracts.py`. The
stone layer froze only what is constant across every future we can foresee
(CONTRACT.md). Everything below is real, but its shape is not yet certain — so it
lives in the **soft layer** with a hypothesis attached, or it waits for an RFC.

How to use this file:
- Building soft-layer code (Gateway, Controller, plugin)? Find the relevant entry
  and follow its hypothesis. It is a recommendation, not a frozen rule — improve
  it, but record what you changed in `DECISIONS.md`.
- Tempted to add a field to a wire type? Check here first. If it is listed as
  deferred, it is deferred on purpose. Adding it needs CONTRACT.md §3.
- Spinning up the adversarial PR reviewers (CLAUDE.md step 4)? Assign each
  reviewer one agent below. They map onto the contract's known weak axes.

Status legend: 🟢 build-now-in-soft · 🟡 deferred (field/field-stub present, semantics unstable) · 🔴 needs RFC before any code

---

## Settled forks (decided; recorded so they are not re-litigated)

- **Param typing — HYBRID (settled).** Structural/primitive param types
  (`int/float/enum/string`) are validated centrally in `validate()`. Reference
  types (`element_id/selection/map_point/waypoint`) resolve against the soft
  `Percept.data` shape and are validated by the plugin/Gateway. Free text stays
  `string`: untrusted, never interpolated into an executable context.
- **Reversibility — COST VECTOR is source of truth (settled).** `Skill.cost`
  is `{CostDim: magnitude}`. Any human-readable "severity" is COMPUTED in the
  soft layer, never stored. Physical harm dominates regardless of magnitude.
- **Both Brain and Gateway see reversibility (settled).** Brain reads it to be
  cautious; Gateway enforces. The plugin's report is an untrusted hint that the
  Gateway may only raise (Invariant 13 / Vesper-1).

---

## Agent A — Chronos (concurrency)

**Nexus-2 supersedes the naive fix — read both.**

- **A1 · TOCTOU** 🟡 — `Goal.percept_timestep` is a frozen field, but the
  *rejection rule* ("reject if world advanced past tolerance") is SOFT and lives
  in the Gateway, because it conflicts with simultaneous-move multi-agent (see
  Nexus-2). Hypothesis: single-agent/turn-based Gateways enforce it; multi-agent
  Gateways replace it with epoch arbitration.
- **A2 · Partial batch failure** 🔴 — atomic vs. independent multi-goal
  semantics. No batch type is frozen (one Goal per invocation, Invariant 8).
  Needs an RFC if/when RTS lands; do not bolt a `GoalBatch` into the wire early.
- **A3 · Approval stalls real-time domains** 🟢 — you cannot pause a quadcopter
  for a human. Hypothesis: real-time Controllers define a safe holding behavior
  (hover/loiter/no-op) + default-deny-on-timeout, run while an approval is
  `pending:`. Build in the Controller, not the contract.

## Agent B — Vesper (safety / red-team)

- **B1 · Self-reported severity** 🟢 — the plugin rating its own risk is the fox
  guarding the henhouse. Hypothesis: the Gateway owns an external policy table
  keyed on `verb`/`handle`; the plugin's `cost` may only RAISE the policy
  rating, never lower it. Frozen support: Invariant 13.
- **B2 · Salami attack** 🟢 — a Brain decomposes one gated irreversible action
  into many sub-threshold ones. Hypothesis: a soft `RiskLedger` in the Gateway
  accumulates per-CostDim spend and gates the PROJECTED total, not the single
  goal. Reset keyed off `DomainPlugin.resettable`: per-episode in sim, persistent
  in non-resettable domains (so the defense survives "resets" where
  irreversibility is real). NOT frozen — semantics still contested by Nexus-3
  and Witness-1.
- **B3 · Free-text injection** 🟢 — settled by the hybrid: anything resolving to
  an effect is typed and checked; `string` is untrusted and never interpolated
  into a URL/shell/DOM context.

## Agent C — Sigma (type theory / API evolution)

- **C1 · Declared types not enforced** 🟢 — `validate()` runs real checks for
  primitive params; reference params pass through to plugin validation by design.
  Optional v0.x ergonomics: generate a per-Skill model from `params`.
- **C2 · Frozen vs. extensible** 🟢 — resolved by the grammar/vocabulary split.
  Add `Frame`/`CostDim`/`Verb`/`param-type`/status terms at runtime via
  `register_*`; this edits no frozen file. Editing a SEED member is an RFC.
- **C3 · Protocol checks shape, not behavior** 🟢 — `runtime_checkable` confirms
  methods exist, not that `reset()` raises when `resettable=False`. Hypothesis:
  a conformance harness — golden vectors per Protocol every plugin must pass.
  Build alongside the first two real plugins. This is the piece that makes
  "frozen" enforceable rather than advisory.

## Agent D — Nexus (multi-agent / game theory)

- **D1 · Single-agent step** 🔴 — the contract specifies one Brain. Multi-agent
  is the biggest unexamined axis. FORK FOR THE HUMAN before any code: joint
  `step(dict[AgentId, GoalBatch])`, OR N plugin instances over a shared world
  with env-owned arbitration? This reshapes the loop — needs an RFC, not a soft
  patch.
- **D2 · TOCTOU vs. simultaneous moves** 🔴 — A1's staleness rejection would
  reject every legitimate second-mover in a simultaneous turn. Hypothesis: a
  decision EPOCH — all agents bind to one timestep, the plugin resolves jointly,
  staleness applies across epochs, never within one. Resolve together with D1.
- **D3 · Collusive salami** 🟡 — the per-Brain ledger (B2) is blind to two
  cooperating agents each staying under budget. Known limitation for v1; shared/
  hierarchical budgets are future work.

## Agent E — Theta (RL learnability)

- **E1 · Non-stationary action space** 🟢 — conditional skill menus mean the
  action set changes shape per step. Hypothesis: learned Brains MUST score over
  skill embeddings with masking (pointer-net / action-as-input), not a fixed
  categorical head. Document loudly; a naive fixed head is untrainable here.
- **E2 · Ledger breaks Markov** 🟢 — identical Percept, different verdict by
  hidden ledger state. Hypothesis: expose REMAINING budget in `Percept.data` so
  the Brain can learn to pace itself. Extends "Brain sees reversibility" to its
  logical end.
- **E3 · Reward routing** 🟢 — Hypothesis: split ENVIRONMENT reward (sparse,
  scored, comparable — `Outcome.reward`) from CONTROLLER shaping (dense,
  plugin-private, never scored). Invariant 11 supports this.

## Agent F — Witness (eval integrity / reproducibility)

- **F1 · Stateful ledger contaminates benchmarks** 🟢 — two identical Brains get
  different verdicts by ledger history → runs not independent → scores not
  comparable. Hypothesis: benchmark-mode Gateway resets the ledger to a seeded
  budget per episode (or excludes it). Safety-mode and benchmark-mode Gateways
  diverge deliberately.
- **F2 · Seeding + wall-clock** 🟢 — `perceive`/`execute` aren't pure, and
  real-time `timestep` (epoch seconds) is a reproducibility hazard. Hypothesis:
  require `Replayable.reset(seed)`; in benchmark mode, drive a logical clock, not
  real time. The real-time-control vs. reproducible-eval tension is forced into
  the open, not papered over.
- **F3 · Run provenance** 🟢 — a bare reward number is unauditable. Hypothesis:
  emit a `RunManifest` per run (contract version, vocab-registry snapshot, seeds,
  component hashes). This is the line between benchmark and demo.

---

## Coding-agent quick reference

- 🔴 (D1, D2, A2) — do NOT write code that assumes these. Raise an RFC.
- 🟡 (A1, B2, D3) — a field or stub exists; treat its semantics as unstable and
  isolate dependence behind a soft interface.
- 🟢 (everything else) — build in the soft layer now, following the hypothesis,
  recording deviations in `DECISIONS.md`.
- Top three to build first: **C3 conformance harness**, **B1 Gateway policy
  table**, **F3 RunManifest** — they convert "frozen", "untrusted plugin", and
  "benchmark" from aspirations into enforcement.
