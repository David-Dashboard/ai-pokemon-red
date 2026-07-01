# ADR-003 (PROPOSED) — The Embodiment Universal Contract (UEC) as the north-star target

**Status:** PROPOSED — north-star target; **gated** (no code lands until a roadmap rung forces it). The
frozen v1 (`CONTRACT_VERSION = 1`, `core/contracts.py`) stays **Accepted** (ADR-001, `ARCHITECTURE.md`) and
is **not swapped, not touched, not re-typed** by this ADR. This is doc-only: it records a target, not a change.

**Origin:** 2026-07-01, from the `reports/_archive/2026-07-01-migration-embodiment-contract.md` analysis
(itself grounded in `main`) plus a two-agent verification this session that corrected its headline claim
(see Corrected mapping table below).

---

## Context

The project's frozen "stone layer" — `core/contracts.py` (`CONTRACT_VERSION = 1`, SHA-256 hash-pinned in
`tests/test_contract_frozen.py`) — is the ADR-001 seam between the world interface (`ai-pokemon-red`,
System 1) and the agent (`ai-aria`, System 2). Separately, an **Embodiment Universal Contract (UEC)** was
designed independently: the `embodiment-stone-layer-v0.2` scaffold (`Skill` / `Percept` / `Goal` / `Outcome`
+ a `Controller` tier + reversibility **cost vectors** + a `HYPOTHESES.md` adversarial register), now vendored
read-only at [`embodiment-stone-layer-v0.2/`](embodiment-stone-layer-v0.2/) (see its `README.md`).

Until this ADR, both the UEC (a zip) and a migration analysis
(`reports/_archive/2026-07-01-migration-embodiment-contract.md`) were "floating" — un-versioned, outside any
repo. The need is to converge them **without a big-bang rewrite**: swapping the frozen, hash-pinned,
golden-vectored v1 for the UEC's shapes would violate the additive-only change process (inline in
`core/contracts.py`, enforced by `tests/test_contract_frozen.py`), churn every golden vector, and break the
hash pin — for zero behavioral gain. The right move, per the migration doc's own Stage 0, is to record the
UEC as the documented **north-star target** that v2/v3 converge toward as roadmap rungs force each delta,
and stop drift toward an ad-hoc rewrite.

## Decision

Adopt the UEC (vendored at [`embodiment-stone-layer-v0.2/`](embodiment-stone-layer-v0.2/)) as the documented
convergence target. The frozen v1 is **NOT swapped**; genuine deltas land **additively, one per forcing
rung**, via the existing change process — never as a rewrite. Until a rung forces a delta, the current thin
v1 shapes stand as-is.

### Corrected mapping table (UEC ↔ repo v1 ↔ verdict)

The source migration doc claimed "~80% congruent, ONE delta (reversibility)." That is **understated** — a
line-by-line comparison of the vendored `core/contracts.py` (UEC) against the repo's `core/contracts.py`
(v1, lines 58–180) this session found **~4 real structural deltas**, not one:

| UEC (embodiment-stone-layer) | repo v1 (frozen) | verdict |
|---|---|---|
| `Skill`(handle, verb, params, enums, reversible, cost:dict, duration) | `ToolSpec`(name, description, schema, cost:int, mutating:bool) | **3 deltas here** — see below |
| `Goal`(skill, params, percept_timestep, data) | `ToolCall`(tool, args, agent_id, call_id) | Congruent role; UEC adds explicit percept binding, drops agent/call IDs to soft |
| `Outcome`(ok, status, reward, error, episode, data) | `ToolResult`(call_id, ok, data, error, cost_charged) + `Event.reward` | **KEEP repo's split** (result vs. reward-event) — cleaner for RL. No change |
| `Percept`(timestep, frame, episode, skills, text, data) | `Observation`(data, text, agent_id, t) + SymbolicState in `data` | Congruent; UEC names frame/episode + carries the skills menu |
| `DomainPlugin`(name, resettable, perceive, skills, execute) | `GamePlugin`(tools, handle, observe, drain_events) | **Delta (events)** — UEC drops the explicit `drain_events()` stream → soft "observatory" |
| `Controller`(begin/step/done, rate_hz) | System 1 (soft: hybrid/autopilot/escalation) | Repo already has it, richer; keep in the soft layer + ADR-001 |
| `Gateway` / reversibility gating | `PermissionPolicy`(check) | Congruent; UEC returns a full Outcome and may only RAISE risk |
| `Replayable` | `Replayable` | Identical |
| registries (Frame/CostDim/Verb) | `SymbolicState.context` (free string) | Soft — free-string already does this job |
| pure `validate()` | validation inside `gateway.execute()` | Optional extraction; not forced |

### The 4 real structural deltas (each with its forcing rung)

1. **Cost**: scalar `int` (repo `ToolSpec.cost`) → vector `dict[str, float]` (UEC `Skill.cost`, keyed by
   `CostDim`: financial / physical / visibility / data_loss). Forced at **It4**.
2. **Reversibility**: `mutating: bool` (repo) → `reversible: bool` + cost hint (UEC) — **semantics
   INVERTED**. The repo's Gateway (`PermissionPolicy.check`) reads the `mutating` flag directly as the
   permission signal. The UEC's plugin self-reports `reversible`/`cost` as an *untrusted hint*, and its
   Gateway may only **RAISE** the risk rating, never lower it (UEC Invariant 13 / `HYPOTHESES.md` Vesper-1).
   This is the first `CONTRACT_VERSION = 2` candidate. Forced at **It4**.
3. **Params**: full JSON Schema (repo `ToolSpec.schema`) → lightweight `{param: type_string}` + a separate
   `enums` dict (UEC `Skill.params` / `Skill.enums`). Soft-adjacent; part of skill-coarsening at **It2**.
4. **Events**: explicit `drain_events()` stream (repo `GamePlugin.drain_events`, line 136 of
   `core/contracts.py`) → soft "observatory" (kept OUT of the UEC contract entirely). Soft — no forcing
   rung; the repo's stream stays as-is.

Plus softer shifts, none of which force a version bump: agent/call IDs pushed to the soft layer (UEC's
`Goal` carries no `agent_id`/`call_id`); episode state made explicit (`Goal.data`/`Outcome.episode`); the
Brain sees an explicit skills-menu on every `Percept` (repo's `Brain.decide()` already receives `tools`
separately, so this is naming, not a gap).

## Staged convergence (gated on the rung that forces each)

- **It2 (2nd 2D world):** skill-handle coarsening (`navigate_to` / `interact` / `touch_target`) + System-1
  resolvers. **SOFT — no `contracts.py` change.** This is the north-star test: are the primitives real
  tools, or Red-specific hacks? Coarsen `touch(x,y)` → `touch_target(id)` resolved against the perceiver's
  touch-target list — no coordinates on the wire.
- **It4 (sim→real / home):** the reversibility cost-vector — the first legitimate `CONTRACT_VERSION = 2`.
  **ADDITIVE** optional field, defaulting empty so v1 plugins are unaffected. Until It4, `mutating: bool` +
  `PermissionPolicy` are sufficient — **do NOT add it speculatively.**
- **Controller naming:** never forced into the contract. Doc-only note: `System 1 ≡ Controller`,
  `System 2 ≡ Brain`, so the two projects' vocabularies line up without either codebase changing.

## Do-NOT guardrails

- Don't swap `contracts.py` v1 for UEC shapes — retyping a frozen field is a change-process violation and
  churns every golden vector for zero behavioral gain.
- Don't rename types (`GamePlugin`→`DomainPlugin`, `Observation`→`Percept`, etc.) — pure churn of the
  hash-pinned file. Names are soft documentation; align them in an ADR, never in code.
- Don't add the cost vector before It4 — `mutating: bool` is the correct thin version until irreversibility
  is real. Speculative addition is the schema-zoo failure mode (UEC's own R11 risk).
- Don't pull System 1 into the contract — it's world-coupled and soft, per ADR-001; the UEC agreeing it's a
  separate tier (`Controller`) is *support* for the current placement, not a reason to freeze it.
- Don't put coordinates on the wire — coarsen `touch(x,y)` → `touch_target(id)` resolved against the
  perceiver's touch-target list, keeping geometry in the perceiver/System-1.

## Adversarial review lens

Adopt the UEC's `HYPOTHESES.md` register as the per-stage review lens. Each persona maps onto the delta it
guards:

- **Chronos** (concurrency / TOCTOU) — `percept_timestep` staleness; the UEC's `Goal.percept_timestep` is
  frozen but its rejection rule is soft (HYPOTHESES A1). Relevant if/when the repo adopts explicit percept
  binding.
- **Vesper** (safety / red-team) — the plugin self-reports risk and the Gateway may only raise
  (HYPOTHESES B1) + the salami/risk-ledger defense (B2). Guards the **reversibility delta**: this is exactly
  the semantics inversion between `mutating: bool` (repo, Gateway-checked) and `reversible`+cost (UEC,
  plugin-reported, Gateway-only-raises).
- **Sigma** (type evolution) — structural-vs-reference param typing (HYPOTHESES C1) + golden-vector
  conformance (C3). Guards the **params delta**: JSON Schema vs. type-strings+enums.
- **Nexus** (multi-agent / game theory) — per-agent ledger blindness (HYPOTHESES D3); the single-Brain-step
  assumption (D1). Not currently forced by anything on the repo's roadmap, but flagged for It4+ if the home
  ever hosts more than one embodiment.
- **Theta** (RL learnability) — a non-stationary skill-menu needs a pointer-net, not a fixed categorical
  head (HYPOTHESES E1); expose remaining budget in the Percept (E2). Guards **It2 coarsening**: once tools
  become coarse conditional skills, the action space stops being stationary.
- **Witness** (eval integrity / reproducibility) — a stateful ledger vs. benchmark comparability
  (HYPOTHESES F1); seeding + a logical clock vs. wall-clock (F2). Relevant once any risk ledger or real-time
  Controller lands.

## Change-process cross-reference

The repo has **no standalone `CONTRACT.md`** (the UEC ships one). The additive-only ceremony lives inline in
`core/contracts.py` (module docstring, ~lines 2–51) and is enforced by `tests/test_contract_frozen.py` (the
`PINNED_SHA256` hash pin + a `CONTRACT-CHANGE-APPROVED` commit token convention). This is functionally
equivalent to the UEC's `CONTRACT.md` §3, just inlined rather than a separate file.

**Deferred, out-of-scope follow-up:** formalizing a standalone repo `CONTRACT.md` (mirroring the UEC's) is
not part of this ADR and is not scheduled against any rung.

## Drift tripwires

| Drift | Guard |
|---|---|
| Building/promoting/claiming anything from the UEC before a rung forces it | Nothing lands until It2 (coarsening) or It4 (cost vector) forces it. The UEC is a **target**, not a patch. |
| Treating this ADR as a spec to implement now | ADR-003 stays **PROPOSED** and lives in `reports/_archive/` — do **NOT** inline it into `ARCHITECTURE.md` — until its gate is defined and passes (mirrors the ADR-002 convention). |
| Swapping `contracts.py` v1 for UEC shapes "while we're at it" | Retyping a frozen field is a change-process violation; see Do-NOT guardrails above. |
| Adding the cost vector speculatively "since we're touching this area" | Forced at It4 only; adding it early is the schema-zoo failure mode both `CONTRACT.md` (UEC, R11) and this repo's discipline warn against. |
| Re-deriving a "1 delta" framing from the original migration doc without the correction | The migration doc (`2026-07-01-migration-embodiment-contract.md`) carries a correction note at its top; this ADR is the authoritative mapping — ~4 real deltas, not 1. |

---

## References

- Vendored UEC scaffold: [`embodiment-stone-layer-v0.2/`](embodiment-stone-layer-v0.2/) (`CONTRACT.md`,
  `HYPOTHESES.md`, `core/contracts.py`, `contracts/golden_vectors_v1.json`, `tests/test_contract_frozen.py`
  — reference only, not wired into this repo's build or tests; see its `README.md`).
- Internalized migration analysis:
  [`2026-07-01-migration-embodiment-contract.md`](2026-07-01-migration-embodiment-contract.md).
- This repo's frozen contract: `core/contracts.py` (`CONTRACT_VERSION = 1`), `tests/test_contract_frozen.py`.
- ADR-001 (Accepted): `ARCHITECTURE.md` — the dual-process seam this contract implements.
- ADR-002 (Proposed): `reports/_archive/2026-06-25-adr-002-ontology-discovery.md` — this ADR mirrors its
  Status/Origin/Context/Decision/Drift-tripwires structure.
- Roadmap rungs referenced: `ROADMAP.md` — It2 (2nd 2D world, skill-coarsening), It4 (sim→real / home,
  the reversibility cost-vector).
