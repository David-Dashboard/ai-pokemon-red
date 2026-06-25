# ADR-002 (PROPOSED) — Self-built ontology: move the hand-code/learn boundary DOWN

**Status:** PROPOSED (2026-06-25). **Gated** on the grounding probe (§9). Revises — does not yet replace —
ADR-001 (`ARCHITECTURE.md`). ADR-001 stays **Accepted** until the probe validates the load-bearing claim;
on PASS this is promoted into `ARCHITECTURE.md` as Accepted ADR-002 and ROADMAP is updated.
**Origin:** the 2026-06-25 design discussion (System-1 ontology + primitives). **Not yet built.**

---

## 1. Why revise ADR-001
ADR-001 froze the seam as a fixed role-named `SymbolicState` schema and defined **constancy** as *"the
perceiver schema is constant; only its contents swap per world."* Designing Cave Noire combat exposed two cracks:

1. **The seam is navigation-shaped.** Cave Noire needs *entities, agent-status/life, threat, objective* — none
   expressible in the fixed schema (it carries pose/walls/frontiers; `screen_text=""`, `rois=[]`). ADR-001's own
   **invariant #4** ("perception lost something the agent needed") then fires *by construction* for every richer
   world — and the symbol-grounding caution ADR-001 cites (a static schema grounds only a vanishing fraction of
   worlds) bites us, not just Cradle.
2. **The hand-code/learn boundary is in the wrong place.** Today *everything below the seam is hand-coded* (a
   bespoke perceiver per world) and only the brain above is general. The bespoke perceiver is the **worst** place
   to hand-code: too game-specific to reuse, too high-level to be a primitive.

## 2. Decision — the move
Push the hand-coded line **DOWN** to a small fixed sensorimotor floor; let the learned line grow **DOWN** to
swallow the perceiver. Three layers:

```
General brain (System 2)                       ← unchanged
  ── Learned ontology + compiled skills         ← NEW: was the hand-coded perceiver
  ── Fixed sensorimotor primitives (System 1)   ← small, world-agnostic-within-a-sensory-class, in core/
Raw world I/O (pixels + buttons)
```

## 3. The sensorimotor floor (the irreducible primitives — they can't be hypothesized; grounding stands on them)
- **SENSE:** pixels · **change** (frame-diff) · **motion/flow** · **ego-motion** (self/agency) · **blob-segment**
  (connected-components = the substrate of "a thing") · **persistence/track** · a **recognition key** (perceptual
  hash) · **glyph read** (OCR — can't behaviour-ground a number without reading it).
- **ACT:** **emit input** · the **action↔effect binding**.
- **GROUND:** a world-agnostic **consequence detector** (pixels-only "something terminal/rewarding happened" —
  reset / game-over / a tracked scalar crossing a threshold). *The missing keystone:* without a consequence
  channel, behaviour can grade nothing.

Most already exist, fused into perceivers: `best_shift` (ego-motion), `grid_max`/modality (change), the
perceptual hash + tile→function map (recognition + grounding). **Genuinely missing as clean primitives:**
blob-segment+track, general glyph-read, the world-agnostic consequence detector.

## 4. The loop — hypothesize → ground → compile (replaces "push a fixed schema up")
1. **S2 hypothesizes** ontology from world-priors ("a dungeon — expect a life stat, enemies, a goal; look here").
2. **S1 grounds** by behaviour: builds a cheap detector over the primitives, verifies its firing **correlates with
   the consequence S2 predicted** (the thing I called a monster *did* drop my life), discards what doesn't ground.
3. **Compile** the survivors into free percepts + reflexes; re-wake S2 only on novelty.

**Existence proof:** the tile→function map already does exactly this for *walkability* (a hash hypothesis graded
by bumping). ADR-002 = generalize that one working mechanism from walkability to **all** ontology.

## 5. The seam (revised) — queryable, not a fixed push
Freeze the **sensorimotor primitive API**, not the schema. The brain **interrogates** perception ("what changed?
what's near me? read region R? seen this?") and perception answers from its grounded model — goal-directed query,
not a fixed dashboard. `core/contracts.py` freezes the primitive ops; perceptual *content* is an open per-world
payload.

## 6. Constancy, redefined
The constant thing is the **ontology-construction loop (the method)**, not the seam shape. Success shifts from
*"how little the perceiver schema changes"* to *"the same hypothesize→ground→compile loop builds a working
ontology in each new world with no new hand-coded perceiver."*

## 7. KEPT from ADR-001 (load-bearing — survives unchanged)
- **Dual-process** (S1 drives, S2 at decisions); **cost scales with novelty** — now front-loaded *per world* during discovery.
- **behaviour = truth** — now the grader of *all* ontology, not only walkability.
- **No privileged-state leak**; oracle = scoring only.
- **Learning-boundary** (within-run; across-run = deliberate, outcome-gated promotion — the Voyager/Huang gate now applies to *perception*, not just skills).

## 8. CHANGES from ADR-001
| | ADR-001 | ADR-002 |
|---|---|---|
| Seam | fixed `SymbolicState` schema | fixed primitive API + open ontology payload (queryable) |
| Perceiver | hand-coded per world | brain-hypothesized + behaviour-grounded |
| Constancy | fixed schema | constant loop (the method) |
| System 1 | `ExploreBrain` = the autopilot | primitives + compiled policies (ExploreBrain → one nav skill) |
| Progress metric | (cells explored) | grounded-objective progress |

## 9. GATING — Proposed until the riskiest assumption grounds
**Load-bearing claim:** behaviour can ground a brain-hypothesized ontology **beyond walkability** (a HUD/life
detector; entities). Everything above rests on this.
**The probe (cheapest proxy; reuses the MCP harness):** add `read_text` + `whats_changed` primitives to
`world_mcp.py`; let the brain hypothesize *"region R = my life"*; **score its grounded life-detector against the
RAM oracle** as it plays/fights. **PASS** = **(a) it grounds the truth** — the grounded life-detector tracks the
oracle's life value across a run; **AND (b) it rejects a decoy** — handed a plausible-but-wrong region (a score
counter / a static UI box), the loop *discards* it because its firing fails to correlate with the consequence.
Both arms required: (a) alone can be passed by a loop that "agrees" with any hypothesis (pattern-matching, not
behaviour-grounding). **FAIL** = the direction dies cheap, here, before any rewrite. On PASS → promote to Accepted +
generalize to entities.

## 10. Honest caveats (do not over-claim)
- The primitive kit bakes a **"2D screen of moving sprites" prior** (blob-segment assumes contiguous-pixel
  objects). It **re-tiers** for 3D/robotics (depth, 3D-flow, proprioception) — primitives are *sensory-class*-agnostic, not universal.
- We are **still hand-coding** — at the floor (≈10 cheap CV ops, reused forever) instead of the middle. That's the
  win, and it keeps cheap+no-training (floor = free classical CV; ceiling = brain-hypothesis + behaviour-grading).
- Open-ended discovery *from nothing* is unsolved; this leans on the brain's priors — **degrades in genuinely
  alien worlds** (falls back to slow emergence).
- Grounding needs **consequence/failure** — fine in games; the It4 safety wall in reality.

---

## 11. ANTI-DRIFT — guardrails for the next builder (read this before touching anything)

This direction is easy to drift on. Hold these or the rewrite goes wrong.

**THE FIRST ACTION IS THE GATE (§9). Nothing big is built, promoted, or claimed until it PASSES.** Build ONLY
what the HUD-grounding probe needs; run it; score it vs the RAM oracle with a pre-stated pass/fail. No sensorium
buildout, no doc promotion, no roadmap rewrite, until PASS.

### Drift tripwires (drift → guard)
| Drift | Guard |
|---|---|
| **Hand-code a Cave Noire combat perceiver** (revert to the per-game pattern ADR-002 exists to kill) | The deliverable is the hypothesize→ground→compile **LOOP**, not a bespoke perceiver. Writing game-specific perception logic? STOP — that's the exact drift. (Twin of the existing "primitive ossification" tripwire.) |
| **Over-build the sensorium before the gate** (all ~10 primitives + an ontology framework first) | Build ONLY the 2–3 primitives the gate needs (`read_text`, `whats_changed`, `consequence`). The full floor is POST-gate. Perfecting the engine before testing the riskiest assumption is the named anti-pattern. |
| **Promote ADR-002 / overwrite `ARCHITECTURE.md` / `ROADMAP.md`** | ADR-002 is **PROPOSED**. ADR-001 stays Accepted until the gate PASSES; only then promote. Don't claim a result you don't have. |
| **A gate that can't fail** ("looks right" = pass) | The probe MUST score the grounded detector vs the RAM oracle with a **pre-stated** pass/fail (e.g. detector agrees with oracle life on ≥X% of decisions). Pick the metric, hold the unit, let it fail — you've reversed your own headline claims 3× this way. |
| **Persist ontology/lessons across runs** | Learning-boundary HARD LAW: within-run only, blank every run. Across-run = deliberate, outcome-gated promotion — never auto-persist. |
| **Leak the oracle into grounding** | The `consequence` detector is **PIXELS-only**. RAM/oracle is the SCORER — never an agent input, never the grounding signal the agent reads. |
| **Screenshot back to the brain** | Symbolic/queryable seam only; the screenshot stays behind `--with-screenshot` (debug). Pixels-to-brain reopens the §4 confabulation failure. |

### Decided vs open (don't re-litigate the decided; don't claim the open)
- **DECIDED:** the direction (boundary moves down · hypothesize→ground→compile · queryable seam · constancy=loop); the **gate-first** build order; the kept invariants (§7).
- **OPEN / GATED:** does behaviour ground ontology beyond walkability? (the gate answers it) · the full sensorium API · roadmap-v2 · the seam's exact query interface.

### Read first (so you don't re-derive or contradict)
This doc · `HANDOFF.md` top block · `world_mcp.py` (the harness you EVOLVE — already symbolic-only / dual-process /
no-leak; don't regress it) · `core/tilemap.py` (the tile→function map = the existence proof) · plan-grounding
Part 1 (`reports/2026-06-22-plan-grounding-and-failure-modes.md` — why the gate is non-negotiable: Voyager/Huang).
