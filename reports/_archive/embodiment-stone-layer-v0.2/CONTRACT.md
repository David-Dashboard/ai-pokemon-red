# CONTRACT.md — The Embodiment Stone Layer Constitution

**Status: FROZEN. Contract version: 1.**
**Binding file: `core/contracts.py` (SHA-256 pinned in `tests/test_contract_frozen.py`).**
**Canonical wire examples: `contracts/golden_vectors_v1.json` (never edited; new versions add new files).**

The human-readable source of truth for this project's only immutable layer.
Everything else — Gateway, Controllers, Brains, domain plugins, runner,
observatory — is soft and may be rewritten freely, *provided it honors this
contract*. What is frozen is the **wire format and its semantics**, not Python
aesthetics. `contracts.py` is one language binding of this constitution.

This layer is a sibling of the Arena tool-call stone layer and inherits its
discipline. Where Arena froze "agents act on worlds via ToolCalls", this freezes
"one Brain drives many embodiments by naming Skills."

---

## 1. The contract in one paragraph

An embodiment (`DomainPlugin`) presents the Brain with a `Percept` whose `skills`
list is a menu of named, parameterized `Skill`s. A `Brain` turns a Percept into
exactly one `Goal` per invocation — naming a `Skill.handle` and filling typed
params, never emitting coordinates or motor commands. A `Gateway` validates the
Goal (`validate()`), applies permission/risk policy, and is the single door to
execution. A `Controller` realizes an extended Goal as low-level action at the
embodiment's control rate; the Brain is never inside that loop. Every value
crossing the boundary is plain JSON. Deterministic simulated worlds additionally
implement `Replayable`; real-world embodiments never do.

## 2. Invariants (normative)

1. **The handle invariant.** A Goal names a `Skill.handle` from the current
   Percept's menu and supplies its typed params. It never carries coordinates,
   motor commands, or raw actions. This is the abstraction the whole layer
   exists to protect.
2. **Single door.** Nothing acts on any embodiment except a Goal authorized
   through the Gateway. Brains never call plugin methods directly.
3. **Errors are observations.** Illegal, denied, failed, or pending actions
   return `Outcome(ok=False)` with a readable `error` and useful `data` — never
   an exception across the boundary.
4. **JSON wire.** Everything crossing the boundary is JSON-serializable. Tensors
   and rich objects live only inside Brains/Controllers/plugins.
5. **Perception structure is soft.** Only the Percept *envelope* is frozen
   (`timestep`, `frame`, `episode`, `skills`, `text`, `data`). Entities, rasters,
   set-of-marks, symbolic state — all ride in `data` as per-domain convention.
   Do not "fix" this by freezing an Entity schema (that is the Arena R11 schema-
   zoo failure mode).
6. **Shallow-freeze discipline.** Frozen dataclasses do not freeze nested dicts.
   The Gateway deep-copies wire values at the boundary; no component mutates a
   wire value after sending or receiving it.
7. **Time regimes.** In Replayable worlds, `timestep` is the tick number (as
   float). In real-world embodiments, it is unix epoch seconds. A plugin
   declares one regime and never mixes them.
8. **One decision per invocation.** Multi-step turns are runner loops calling
   `decide()` repeatedly, never a fatter Goal signature. Concurrent/multi-agent
   stepping is NOT yet in the contract (HYPOTHESES.md, Nexus).
9. **Handle invariant survives continuity.** The Controller, not the Brain,
   turns an extended Goal into a continuous trajectory. Continuous control never
   leaks back into the Goal as coordinates or setpoints the Brain authored.
10. **The Brain names; the Controller realizes; the Gateway permits.** These
    three roles are distinct and a component never assumes another's job.
11. **Reward is scalar.** `Outcome.reward` is the single number learners
    consume. Multi-objective signals ride in `Outcome.data`. (HYPOTHESES.md,
    Theta-3: keep environment reward separate from controller shaping.)
12. **Async approval is an observation.** Expressed as
    `Outcome(ok=False, error="pending:<id>")` with the id echoed in `data`,
    polled by retry. Being denied or queued is never an exception.
13. **Reversibility is an untrusted hint.** A Skill's `reversible`/`cost` is
    reported by the plugin. The Gateway reconciles against external policy and
    may only RAISE risk, never lower it (HYPOTHESES.md, Vesper-1).
14. **Import, never copy.** Wire types are imported from `core.contracts`.
    Copy-pasting definitions into a plugin or service is fork drift, forbidden.

## 3. Change process (the escape valve)

A contract with no legal change path gets forked around. Changes are allowed,
but only like this:

1. RFC entry in `DECISIONS.md`: what gap, why no convention inside `data` can
   cover it, migration impact on stored logs.
2. **Additive only.** New optional fields with defaults. Never rename, remove,
   retype, or change the meaning of an existing field (protobuf discipline).
3. Bump `CONTRACT_VERSION`; add `contracts/golden_vectors_v{N}.json` (old vector
   files are never edited and must keep parsing forever).
4. Update `PINNED_SHA256` and `PINNED_VERSION` in the frozen test, in the same
   commit as the RFC.
5. Commit message must contain `CONTRACT-CHANGE-APPROVED` (the pre-commit hook
   rejects contract edits without it).
6. **A human explicitly approves.** AI may draft RFCs, never execute 3–5 alone.

Red flag in review: structured conventions accreting inside `data` blobs
("stringly-typed schemas"). One or two (entities, approval_id) are healthy
pressure-relief; a zoo means the freeze is too tight and an RFC is overdue.

## 4. Risk register (v1)

| # | Risk | Status / Mitigation |
|---|------|---------------------|
| R1 | Future AI sessions "helpfully" refactor the contract | Hash pin + CLAUDE.md standing order + pre-commit token |
| R2 | Shallow freeze: nested dicts mutated after logging | Invariant 6 (Gateway deep-copy) |
| R3 | Slow real-world actions vs. synchronous Outcome | Long actions return `data={"job_id":...}` + a poll tool, by convention |
| R4 | Hours-long approval queues vs. synchronous permission | Invariant 12 (pending: convention, poll by retry) |
| R5 | `timestep` ambiguity (tick vs. wall clock) corrupting metrics | Invariant 7; plugins declare regime |
| R6 | Freezing an Entity schema breeds a per-domain schema zoo | Invariant 5 (perception rides in `data`) |
| R7 | TOCTOU: world moves between perceive and act | `Goal.percept_timestep` field is frozen; rejection RULE is soft (HYPOTHESES Nexus-2 conflict) |
| R8 | Self-reported risk understated by a buggy/adversarial plugin | Invariant 13 (Gateway may only raise) |
| R9 | Salami: many sub-threshold irreversible goals sum past the line | Soft RiskLedger (HYPOTHESES Vesper-2); NOT frozen — semantics contested |
| R10 | Stateful risk ledger contaminates benchmark comparability | Benchmark-mode Gateway resets ledger per episode (HYPOTHESES Witness-1) |
| R11 | Over-freezing → schema zoo inside `data` | §3 red-flag rule |
| R12 | Old logs unreadable after a change | §3 additive-only + envelope carries `contract_version` |
| R13 | Multi-agent / concurrent stepping doesn't fit one-Goal `decide()` | Invariant 8; deferred (HYPOTHESES Nexus-1) — needs RFC, not a soft hack |
| R14 | Conditional skill menus make a non-stationary action space | Soft: learned Brains score over skill embeddings with masking (HYPOTHESES Theta-1) |
| R15 | CRLF checkout breaks the hash pin | Test LF-normalizes before hashing |
| R16 | The freeze mechanism itself gets deleted | Hook + CI treat the test and `scripts/` as protected paths |

## 5. What is explicitly NOT frozen

Gateway and its permission/risk policy, the RiskLedger and its reset rule,
Controllers and control rates, Brains and their belief/memory, all domain
plugins and their `data` payload shapes, the staleness/TOCTOU rejection rule,
severity derivation from cost, multi-agent arbitration, encoders, runner,
observatory. Churn freely; honor the contract. The open questions behind these
are tracked, with hypotheses, in `HYPOTHESES.md`.
