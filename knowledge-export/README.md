# Knowledge export — aria cost root-cause + agent architecture (2026-06-20)

A self-contained bundle of the design/analysis notes produced in one working session on the
**ai-aria** (decoupled LLM brain) + **ai-pokemon-red** (world/harness) projects. Safe to ingest into a
personal-knowledge base. Some files carry YAML frontmatter and `[[wikilink]]` cross-references
(Obsidian-style); a few wikilinks point to notes kept in the source project that are **not** in this
bundle (listed at the bottom).

## Contents

| File | What it is |
| --- | --- |
| `ROADMAP.md` | **The multi-month arc.** One brain up a capability ladder of harder worlds (Pokémon → 2nd 2D game → FPS/TPS → real drone/car → legged robot), each adding one hard axis; the invariant architecture beneath; the small-worker as an orthogonal track; the two real discontinuities (real-time, sim→real). |
| `2026-06-20-cost-investigation.md` | **Cost root-cause.** Why a Haiku-4.5 game agent burned ~$7–9/day. Findings: the conversation prompt is ~92% of tokens (not the reflection/aux machinery); the system manual is duplicated ~7×/wake; prompt-caching is crippled because the cacheable prefix sits below Haiku's 4096-token floor while the big stable content rides the uncacheable user message; confirmed Haiku-4.5 pricing; the credit-out was the real cause of the API errors. |
| `PROMPT_ARCHITECTURE.md` | **Constitution-first prompt layering** (canonical design doc, lives in ai-aria). One generalizable system+user message spine for any agent: Constitution → Persona → Derived knowledge → Retrieval → Working state, ordered by decreasing stability so the immutable purpose is the cache anchor. 8 durable principles + anti-drift rules. |
| `dual-process-architecture.md` | **The cognitive-architecture vision (general, not game-specific).** aria = brain (System 2) that authors its own System 1 policies + owns within-run memory + acts on the world via tools; the world (game emulator / digital life / reality) exposes coarse skill-tools; System 1 drives cheaply, defers to System 2 on necessity/override. Cost scales with novelty, not steps. |
| `unified-prompt-architecture.md` | The constitution-first spine as a project note + the open α/β decision (who owns within-run memory: a stateless brain vs a brain that owns memory). Companion to `PROMPT_ARCHITECTURE.md`. |
| `cost-blocker.md` | Operational note: the corrected cost root-cause, confirmed pricing, and the "no paid runs until a cost-breaker exists" rule. |

## Reading order (story arc)

1. `2026-06-20-cost-investigation.md` — the symptom and the root cause.
2. `PROMPT_ARCHITECTURE.md` / `unified-prompt-architecture.md` — the structural fix (constitution-first layering) that falls out of the root cause.
3. `dual-process-architecture.md` — the larger vision the fix is a stepping-stone toward (brain + world-as-tools + System 1/2 + self-authored skills).
4. `cost-blocker.md` — the operational guardrail.

## Key transferable ideas (for an Agents knowledge base)

- **Constitution-first prompt layering:** order prompt blocks by decreasing stability; the immutable *purpose* is its own top layer and the cache anchor — keep it OUT of the persona so a persona rewrite can't drop it.
- **Prompt-shape inversion = broken caching:** if your stable content rides the user message and your cacheable system prefix is below the provider's minimum (Haiku 4.5 = 4096 tokens), caching silently does nothing.
- **Brain + world-as-tools + dual process:** one brain, swappable worlds that expose tool APIs; a fast self-authored System 1 drives, deferring to deliberate System 2 only on novelty/override.
- **Learning-boundary fork:** within-run skill compilation (discard at run end) vs across-run persistent improvement (a deliberate choice, not a default).

## Wikilinks referenced but not included in this bundle

`[[learning-boundary]]` (across-run = code only; within-run = ephemeral), `[[project-north-star]]`
(generalize across games → reality; cheap; no privileged state), `[[current-status]]`. Ask if you want
these pulled in too — they give the cross-references something to resolve.

_Diagrams (current-vs-target prompt, the unified spine, the α/β fork, the harness map) were rendered
in-conversation, not as files — they can be exported to SVG on request._
