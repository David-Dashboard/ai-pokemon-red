---
name: unified-prompt-architecture
description: Constitution-first layering — the generalizable prompt spine for aria (companion + trainer); purpose is its own layer, not persona
metadata:
  node_type: memory
  type: project
  originSessionId: 1b436777-2031-4eb5-bd24-c03e024f92da
---

**Design principle (David's vision, 2026-06-20): ONE generalizable system+user prompt spine for every
aria deployment, ordered by decreasing stability.** Canonical doc: `ai-aria/PROMPT_ARCHITECTURE.md`
(written this session, on branch `pokemon-red-constitution` — should be promoted to aria `main` when
synced, else it's stranded on the game branch). An anti-drift header was also added to
`ai-aria/persona.yaml`.

**The spine (top→bottom):** 0 **Constitution** (irreducible PURPOSE, human-authored, the cache anchor,
never retrieved) → 1 **Persona** (voice/style only) → 2 **Derived durable knowledge** (lessons/facts) →
3 **Retrieval** (push+pull, over derived tiers only) → 4 **Working state** (current obs/transcript,
volatile). Same five layers for the companion and the Red trainer; a deployment fills them differently
and empty layers vanish (dormant-until-seeded). Constitution = companion-charter for Aria,
`POKEMON_SYSTEM` for the trainer.

**Why it matters / the headline rule:** PURPOSE must NOT live in persona. Today it does (persona.yaml
short_summary/backstory/values + place.yaml self_concept all assert "beat the Elite Four"), so a persona
rewrite would drop the mission AND the caching/dedup that depend on the constitution sitting at the
cached top. aria already has the 3-tier static/near-static/volatile split (`prompt.py:55-77`) but the top
is `persona`, with no distinct `constitution` slot — this is code drift from the original intent
(`20260521_wishes.txt:46`, `20260521_agentic_workflow.txt:159-164`).

**Key downstream consequences:** putting `POKEMON_SYSTEM` in a cached constitution slot (instead of the
harness stapling it into the uncacheable user message, `core/brains.py:565`) fixes BOTH the cache
(lifts the prefix over Haiku's 4096-token floor → from 34% toward ~80%) AND the ~7×/wake duplication at
once. Retrieval push+pull are NOT redundant if scoped (push=relevance-to-now, pull=by-need, both over
derived tiers only; constitution always-pushed/never-retrieved).

**OPEN DECISION (undecided, α preferred):** who owns the trainer's within-run memory — (α) aria
stateless, harness owns it (matches the [[learning-boundary]] author-vs-store split, removes
duplication) vs (β) aria owns it, harness stops duplicating. See [[cost-blocker]] and
`reports/2026-06-20-cost-investigation.md`. Solutions not yet built; this is the design record.
