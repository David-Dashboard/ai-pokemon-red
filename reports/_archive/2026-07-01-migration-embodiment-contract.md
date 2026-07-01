> **Correction note (2026-07-01):** (a) this doc's "~80% congruent, ONE delta" claim is
> **UNDERSTATED** — a line-by-line comparison this session found **~4 real structural deltas**
> (cost scalar→vector, reversibility semantics inverted, params JSON-Schema→type-strings, events
> stream→soft observatory); see ADR-003 for the corrected mapping. (b) its "branch note" below is
> **stale** — `feat/nds-reachability` now exists on the remote (PR #36, open). (c) ADR-003
> (`2026-07-01-adr-003-embodiment-north-star-contract.md`) is the **authoritative** record; treat
> this document as historical input to it, not as current guidance.

# MIGRATION PLAN — ai-pokemon-red → the Embodiment Contract

_A staged, additive plan to converge this project's frozen stone layer (`core/contracts.py`,
`CONTRACT_VERSION = 1`) with the **Embodiment Universal Contract (UEC)** designed separately
(the `embodiment-stone-layer` scaffold: `Skill` / `Percept` / `Goal` / `Outcome` + a `Controller`
tier + reversibility cost vectors). Companion docs: `ARCHITECTURE.md` (ADR-001), `ROADMAP.md`,
`CONTRACT.md` (§3 change process). Status: **proposal — gated on the §3 RFC + human approval.**_

> **Branch note (read first).** The request named `feat/nds-reachability`. That branch does **not**
> exist on the remote. The NDS work (`feat/nds-emulator`, `feat/nds-touch`) is already **merged to
> `main`** (`core/nds_emulator.py`, `nds_perceiver.py`, `nds_perception_plugin.py`, `play_nds.py`,
> `eval/nds_bench.py`); the latest NDS branch is `fix/nds-review` (2026-06-29). This plan is grounded
> in **`main`** as the latest state, and treats "reachability" as the **spatial-reachability** work the
> code is clearly heading toward (occupancy grids, frontiers, walls, `goto` — `core/localize*.py`,
> `grid.py`, `egomotion.py`, `docs/notes/spatial_reasoning_in_2d.txt`). If "nds-reachability" is a
> local unpushed branch, push it and I'll re-ground §4 against the real diff.

---

## 0. TL;DR — the migration is small, and mostly already underway

**You already built the stone layer.** `core/contracts.py` v1 (`ToolSpec`/`ToolCall`/`ToolResult`/
`Event`/`Observation` + `GamePlugin`/`Replayable`/`Brain`/`PermissionPolicy`) is the **thin binding**
of the same philosophy the UEC enriches. The two are ~80% congruent, and your roadmap is already
walking toward the rest ("coarse skill-calls as this matures" — `ARCHITECTURE.md`).

**So the correct migration is additive and staged — NOT a contract swap.** Replacing a frozen,
hash-pinned, golden-vectored v1 with a differently-shaped contract would violate `CONTRACT.md` §3
(additive-only; never rename/retype an existing field) **and** ADR-001's "revisit only when surprised"
clause. The UEC is best treated as the **target north-star** that v2/v3 converge toward, recorded as
an ADR, with each genuine delta landing only when a roadmap rung **forces** it.

**The single warning:** do not let the existence of a nicer-looking sibling contract trigger a
big-bang rewrite. Your v1 is good *because* it is thin. The UEC's own design notes reach the same
conclusion you did (the R11 over-freezing rule): freeze only what is constant.

---

## 1. The mapping (UEC ↔ current ↔ verdict)

| UEC concept (embodiment-stone-layer) | ai-pokemon-red today | Verdict |
|---|---|---|
| `Skill` (handle, verb, params, reversible, cost, duration) | `ToolSpec` (name, schema, cost, **`mutating: bool`**) | **Congruent.** Coarsening tools into named skills is your stated It2 direction. |
| `Goal` (skill, params, percept_timestep) | `ToolCall` (tool, args, agent_id, call_id) | **Congruent.** TOCTOU `percept_timestep` is deferred (soft) in both. |
| `Outcome` (ok, status, reward, error, episode) | `ToolResult` + `Event.reward` | **Keep yours.** Splitting result from reward-event is *cleaner* for RL than the UEC's merge. No change. |
| `Percept` (timestep, frame, episode, skills, text, data) | `Observation` + `SymbolicState` in `data` | **Congruent.** Perception structure already rides in `data` (UEC invariant 5 = your design). |
| `Controller` tier (begin/step/done, rate_hz) | **System 1** (HybridBrain, autopilot, escalation) | **You have it, richer than the UEC sketch** — and correctly in the *soft* layer + ADR-001, not the contract. Keep it there. |
| `Gateway` + reversibility gating | `Gateway` + `PermissionPolicy` | **Congruent.** `pending:` async-approval convention is identical. |
| reversibility **cost vector** | `mutating: bool` | **The one real delta.** Forced at It4 (irreversibility). See §3. |
| registries (Frame/CostDim/Verb) | `SymbolicState.context` (free string, "not a fixed enum") | **Soft.** Your free-string escape valve already does this job. |
| pure `validate()` | validation inside `gateway.execute()` | **Optional.** Could extract to a pure fn for golden-vectoring; not forced. |
| `DomainPlugin` | `GamePlugin` | Rename only — **don't**, it churns the frozen file for nothing. |
| `Replayable` | `Replayable` | **Identical.** |

The honest read: there is no structural migration here. There is a **skill-coarsening direction**
(already on the roadmap), **one deferred additive field** (reversibility cost), and a pile of
renames you should *not* do.

---

## 2. What the latest branch actually demands of the contract: **nothing**

The NDS/touch/reachability work is the real test of "do we need to migrate the contract now?" The
answer is no, and the way it was built proves the contract is right:

- **Touch (merged).** `NDSPerceptionPlugin` added a `touch` tool with an `{x,y}` schema **without
  editing `contracts.py`** — exactly the §3 discipline working. In UEC terms, `touch(x,y)` is the
  *coordinate leak* we flagged: raw geometry crossing to the brain. The convergence move is to
  **coarsen** it — `touch_target(id)` resolved against the perceiver's existing `touch_targets`
  list — which restores the handle invariant. That is the *same* coarsening as `goto`/`navigate`, and
  it is **soft** (a richer ToolSpec + a System-1 resolver), not a contract change.
- **Multi-screen (NDS dual screen).** Rides in `Observation.data` / `SymbolicState`. No contract
  change. The UEC's `Frame` registry would merely *name* what your `data` payload already carries.
- **Reachability (next).** Frontiers, walls, occupancy grids → `SymbolicState.spatial_memory` +
  `affordances` (**already the schema**). A `navigate_to(frontier_id)` autopilot is System 1. 100%
  soft. No contract change.

**Conclusion:** the latest branch is evidence *for* the thin contract, and the path it implies is the
skill-coarsening that §1 already identified — not a contract migration.

---

## 3. The genuine deltas, and the rung that forces each

Only three things actually differ, and none should land before its forcing rung:

1. **Skill-handle coarsening** — *forced at It2 (the 2nd 2D world).* This is the north-star test
   ("are the primitives real tools or Red-specific hacks?"). It is **soft**: coarser `ToolSpec`s
   (`navigate_to`, `interact`, `touch_target`) + System-1 resolvers. **No `contracts.py` change.**
   The UEC handle invariant becomes *true of your tools* without the contract being touched.

2. **Reversibility: `mutating: bool` → cost vector** — *forced at It4 (sim→real / home).* This is the
   **first legitimate `CONTRACT_VERSION = 2` candidate**, because irreversibility + safety can't be
   expressed by one boolean (UEC: `delete` vs `wire-transfer` vs `drone-over-crowd`). It is **additive**:
   a new optional `cost: dict[str,float]` (or `reversibility`) field on `ToolSpec`, defaulting empty so
   v1 plugins are unaffected. Until It4, `mutating` + `PermissionPolicy` are sufficient and the field
   is **deferred** (do not add it speculatively — your `mutating` flag is the right thin version now).

3. **Controller tier naming** — *never forced into the contract.* Your System 1 already exists and is
   richer than the UEC's `Controller` Protocol. ADR-001 places it correctly in the soft layer. The
   only action is documentation: note in an ADR that `System 1 ≡ Controller`, `System 2 ≡ Brain`, so
   the vocabularies line up. **No code change.**

---

## 4. The staged plan (mapped to roadmap rungs + the §3 process)

Each stage is gated on the rung that forces it and follows `CLAUDE.md`'s workflow
(Opus plan → branch → Sonnet build → **<5 adversarial reviewers** → merge) and, where the contract is
touched, `CONTRACT.md` §3 (RFC in `DECISIONS.md` → additive-only → version bump → new
`golden_vectors_v2.json` → human `CONTRACT-CHANGE-APPROVED`).

**Stage 0 — Record the target (now, doc-only, no code).**
Adopt the embodiment-stone-layer as an **ADR-003: "the north-star contract"**, with the §1 mapping
table. This makes the convergence explicit and stops future drift toward an ad-hoc rewrite. Carry the
UEC's `HYPOTHESES.md` adversarial register (Chronos/Vesper/Sigma/Nexus/Theta/Witness) into your review
lens for every stage below.

**Stage 1 — Coarsen the action vocabulary (It2, soft).**
As the 2nd world lands, express actions as coarse skills (`navigate_to`, `interact`, `touch_target`)
with System-1 resolvers. Reviewers to assign (from HYPOTHESES): **Theta** (does a coarse-skill menu
stay learnable / non-stationary?) and **Sigma** (are the skill params typed, or stringly?). **No
contract change** — this is the migration's main body and it happens entirely in the soft layer.

**Stage 2 — Pure `validate()` extraction (optional, any time, additive-safe).**
If you want golden-vector coverage of goal-coherence, lift the unknown-tool / schema checks out of
`gateway.execute()` into a pure `validate(call, tools)` helper. Soft-layer; no frozen change. Reviewer:
**Witness** (is it pure/total enough to be a benchmark anchor?).

**Stage 3 — Reversibility cost vector (It4, first `CONTRACT_VERSION = 2`).**
Additive `cost: dict[str,float]` on `ToolSpec` + a Gateway risk policy that may only **raise** a
plugin's self-reported rating (UEC Vesper-1), plus a session **risk ledger** for the salami defense
(Vesper-2), reset per-episode in sim / persistent in the home (keyed off `Replayable`). Full §3
ceremony. Reviewers: **Vesper** (self-report + salami) and **Nexus** (if multiple agents/bodies share
the home, the ledger is per-agent-blind — flag as a known limitation, don't solve early).

**Stage 4 — Real-time Controller formalization (It3, soft + ADR).**
When Portal/3D breaks "wake the LLM at decisions," System 1 owns the fast loop — your ADR-001 already
predicts this. Name it the Controller; add `rate_hz` semantics in the soft layer. Reviewer: **Chronos**
(the approval-pending path must not block a real-time loop — needs a safe holding behavior).

---

## 5. Explicitly do NOT do

- **Do not replace `contracts.py` v1 with the UEC shapes.** That is a retype of frozen fields → §3
  violation, and it churns every golden vector for zero behavioral gain. The UEC is a *target*, not a
  patch.
- **Do not rename `GamePlugin`→`DomainPlugin`, `Observation`→`Percept`, etc.** Pure churn of the
  hash-pinned file. The names are soft documentation; align them in an ADR, not in code.
- **Do not add the reversibility cost vector before It4.** `mutating: bool` is the correct thin version
  until irreversibility is real. Speculative addition is the schema-zoo failure mode (R11).
- **Do not pull System 1 into the contract.** It is world-coupled (ADR-001); it belongs in the soft
  layer. The UEC agreeing it's a separate tier is *support* for your placement, not a reason to freeze it.
- **Do not migrate touch to a coordinate-typed contract param.** Coarsen to `touch_target(id)` instead;
  keep raw geometry inside the perceiver/System-1, off the wire.

---

## 6. The smallest first step (this week, if you want momentum)

One PR, doc-only, zero risk: **ADR-003 (Stage 0)** — commit the §1 mapping table and the §3 staging as
the recorded relationship between this repo's contract and the embodiment north-star. It costs nothing,
touches no frozen path, and converts "we have two contracts floating around" into "we have one contract
and a documented target it converges toward." Run it through the normal Opus→branch→review loop; assign
one reviewer to pressure-test the claim *"the latest branch demands no contract change"* (§2) against the
actual `fix/nds-review` diff before you merge the framing.

Everything real after that is gated on It2 (coarsening, soft) and It4 (cost vector, the first v2) — so
the migration's critical path is **your roadmap**, not a contract project.
