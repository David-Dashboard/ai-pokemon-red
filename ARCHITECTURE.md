# ARCHITECTURE — the dual-process seam (ADR-001)

_The durable, version-controlled **contract** for how `ai-aria` and `ai-pokemon-red` divide responsibility.
Pinned so we don't drift. Companion docs: [`ROADMAP.md`](ROADMAP.md) (where the project is going),
[`HANDOFF.md`](HANDOFF.md) (current status), `ai-aria/PROMPT_ARCHITECTURE.md` (the brain's prompt layering)._

- **Status:** Accepted — 2026-06-20.
- **Supersedes:** the implicit "ai-pokemon-red is the harness that drives aria as a per-wake decision
  endpoint" model. The control is **inverted** relative to that: aria is the agent; the world serves it.
- **See also:** ADR-003 (Proposed) — the embodiment north-star contract —
  [`reports/_archive/2026-07-01-adr-003-embodiment-north-star-contract.md`](reports/_archive/2026-07-01-adr-003-embodiment-north-star-contract.md).

## Context

`ai-aria` is the product: a **general AI agent** (memory, retrieval, reflection, tools, reasoning), built
first as a personal companion. **Pokémon Red is a gym** — a non-conversational domain to stress-test and
improve aria's *agentic* design. The success metric is **a better, reusable agent**, not "beating Red."
So the partition between the two repos must put the **reusable, world-agnostic** parts in aria and the
**world-specific** parts in the interface — or the test produces throwaway code instead of agent improvements.

A run (run #β, 2026-06-20) and a design discussion surfaced that responsibilities had leaked across the
boundary. This ADR fixes the boundary.

## Decision — a dual-process system split across the two repos

> **`ai-pokemon-red` = the WORLD INTERFACE + System 1 (the fast, reflexive, world-coupled layer).
> `ai-aria` = the AGENT + System 2 (the slow, deliberate, world-agnostic reasoner + memory + identity).
> They meet at ONE frozen seam.**

| Concern | Lives in | Why |
| --- | --- | --- |
| Emulator, the game | `ai-pokemon-red` | the world |
| **Perception** (pixels → `SymbolicState`: pose, walls, frontiers, decoded text, ROIs) | `ai-pokemon-red` | world-specific; its job is to make state **faithful** so the agent never confabulates from raw pixels |
| **System 1** — reflexive fast loop: navigation autopilot, dialog/battle auto-advance, the escalation signals (`OutcomeMemory`, `DisconfirmDetector`) | `ai-pokemon-red` | System 1 is *sensorimotor* and world-bound; it operates directly on perception |
| **Executive / router** — when to act reflexively vs. wake System 2; skill sequencing (`HybridBrain`) | `ai-pokemon-red` (for now) | the recognized middle "executive" layer (3T); the dial that sets cost |
| The **oracle** (RAM → badges/maps/levels) | `ai-pokemon-red` | scoring ground-truth; **never crosses the seam** (no-leak law) |
| **System 2** — deliberate reasoning, planning, decisions | `ai-aria` | the general reasoner; reused unchanged across games |
| **All memory** — within-run lessons + durable notes/core/episodic + retrieval | `ai-aria` | memory IS the agent; world-agnostic |
| **Identity / constitution** (purpose, strategy) | `ai-aria` | the agent's identity belongs to the agent, **not sent by the world** |
| Authoring **new System-1 policies** (compiled skills) | `ai-aria` (authors) → `ai-pokemon-red` (executes) | System 2 reflects + compiles; System 1 runs it |

### The seam (the frozen contract)
- **World → agent:** the `SymbolicState` (`core/perception.py`, role-named: pose / spatial_memory /
  affordances / last_action / confidence / context). Coarse, **decision-level** — the agent is woken at
  decisions, not every frame.
- **Agent → world:** an intent (a button / sequence / `goto` today; coarse skill-calls as this matures).
- This seam is what makes aria **reusable**: a new world = a new perceiver that emits the *same* shape +
  a new constitution; the agent is untouched. (Perception-invariance is co-equal with the tool interface.)

### Invariants (do not drift from these)
1. **Override is bidirectional.** System 1 drives; it defers **up** to System 2 on *necessity*
   (novelty / low confidence) or when System 2 *overrides* (a surprise preempts). Cost scales with
   novelty, not steps.
2. **Identity & memory are System 2's (aria's).** The constitution and lessons are aria's config/memory,
   **never** stapled in by the world. (The β learning-boundary: aria owns within-run memory, wiped per run.)
3. **The oracle never crosses the seam.** RAM is scoring only.
4. **The perception seam is a *watched bottleneck*.** A fixed schema loses information; keep `SymbolicState`
   rich + extensible (`context` is explicitly "not a fixed enum"). **"Perception lost something the agent
   needed" is a first-class failure mode** in the run → insight loop — not an afterthought.
5. **General vs. game-specific, every fix.** When a run exposes a problem, classify the fix: a **general
   agent** improvement → `ai-aria`; a **world** improvement → `ai-pokemon-red` (perception / System 1).
   The payoff of the gym is the *general* improvements.
6. **Calibrated deferral — System 1 never *decides* what it can't decide reliably.** What belongs in System 1
   is set by **reliability × value**, not "perception vs planning": System 1 owns work that is BOTH high-value
   to do cheaply (it runs every step) AND that it can do *reliably* (deterministic / positive-ID) — movement/
   odometry, static-vs-changed, auto-advancing **positively-identified** routine dialog. A genuine **decision**,
   or **low confidence**, **defers up to System 2** — a menu is the agent's to read and decide; forcing a cheap
   System-1 classifier to do it is brain-dead decision-taking. The dangerous failure is System 1 being
   **confidently wrong** (the hash cross-tileset wall-recall collapse; a menu misread as gameplay); the safe
   default is **wake-when-unsure** (over-waking costs a little; under-waking corrupts behaviour). So build cheap
   System-1 parts as a **gate** — handle reliable routine free, escalate otherwise — **never as a replacement
   for System-2 judgment.** *Evidence:* the 2026-06-23 appearance/OCR probe (`eval/_archive/probe_modality_appearance.py`)
   — cheap perception cannot classify menus cross-game (pokemon 55% / spaceinv 64% balanced-acc), so menu
   *decisions* belong in System 2; cost stays bounded because decisions are rare vs routine steps. (Sharpens
   invariant #1.)

## Research grounding (this is well-trodden, not invented here)
- **Dual-process agents:** SwiftSage (Lin et al., NeurIPS 2023) — a fast *Swift* (System 1, small model) +
  slow *Sage* (System 2, LLM) agent that beats ReAct/Reflexion. The 2024–25 wave (DynaThink, Fast-Slow-
  Thinking, D-Mem dual-process *memory*, Cognitive Duality for web agents) is the same idea.
  https://arxiv.org/abs/2305.17390
- **System 1 world-coupled / System 2 deliberate + bidirectional override:** the classic three-layer
  robotics architecture — reactive / executive / deliberative (Firby's 3T, ATLANTIS, Gat).
  https://en.wikipedia.org/wiki/Three-layer_architecture
- **System 2 → System 1 compilation (our S5):** "Distilling System 2 into System 1" (Meta, 2024,
  arXiv:2407.06023) + Voyager's self-authored, transferable skill library (Wang et al., 2023,
  arXiv:2305.16291).
- **The caution — symbol-grounding bottleneck:** a static symbolic schema can ground only a vanishing
  fraction of possible worlds (information loss) — the documented reason Cradle struggles with spatial
  perception. The same literature endorses *separating perception from reasoning via a symbolic interface*
  (our seam). So: the seam is the enabler **and** the risk → invariant #4.

## Consequences
- **What we already did is mostly aligned.** S3 kept the System-1 signals (OutcomeMemory/disconfirm/
  transcript) in `ai-pokemon-red` and moved the System-2 *lessons* to aria — correct. The only real
  remaining fix is moving the **constitution** out of "the world sends it each wake" into **aria's config**.
- **It does NOT mean migrating the loop into aria.** System 1 stays world-side. aria stays a clean,
  general System-2 reasoner (the same shape as the companion) — that is the point.
- **Cost-first is preserved by construction** (System 1 drives; System 2 woken at decisions).

## Revisit only when surprised (the don't-drift clause)
This contract holds unless an **empirical surprise** forces a change — e.g. the `SymbolicState` seam proves
too lossy for a needed decision (invariant #4 fires), or a **real-time** world (It3) makes the per-decision
wake untenable and System 1 must own a tighter loop. A revision is a **new ADR**, made deliberately — never
by drift.
