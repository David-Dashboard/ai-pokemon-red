# 2026-06-25 — Design backlog: ideas, principles, hypotheses & issues for future visits

Captured from the 2026-06-25 brainstorm (David + Claude). **Nothing here is a build order.** Everything is
sequenced behind the ADR-002 gate (the HUD-grounding probe, `reports/2026-06-25-adr-002-ontology-discovery.md` §9).
Status legend: **DECIDED** (settled this session) · **OPEN** (direction agreed, details unresolved) ·
**PARKED** (deliberately deferred to a later iteration) · **PROBE** (a cheap test exists — named inline).

---

## 0. The triage lens (use this on every new idea)
For any idea: **find the cheapest probe of the riskiest assumption it rests on**, then bucket it —
**(a)** the gate already tests it · **(b)** it carries a *new* risky assumption → give it its own cheap probe ·
**(c)** pure engineering, no risk → just build it when sequenced. **Most of this session's ideas (entities,
focus, spatial reasoning) share ONE root assumption — *behaviour can ground a brain-hypothesized percept* — which
the HUD gate already tests.** Don't multiply probes for one root. (DECIDED — the working method.)

## 1. Decided this session
- **DECIDED — the gate must reject a decoy, not just confirm the truth.** ADR-002 §9 PASS now has two arms:
  (a) the grounded life-detector tracks the RAM oracle, AND (b) handed a plausible-but-wrong region, the loop
  *discards* it. (a) alone is passable by a loop that "agrees" with any hypothesis = pattern-matching, not
  grounding. *(Written into §9.)*
- **DECIDED — fit the perception method to the DATA's complexity** (law). Hash/classical-CV for pixel-art;
  learned embeddings (CLIP/DINOv2) earn their place on rich data (real camera, 3D). The appearance/recognition
  primitive gets a **swappable backend**, tier dialed to the sensory class — same law the brain already follows
  ("cheapest model that clears the bar"). Memory: `fit-perception-method-to-data-complexity`. **PROBE/trigger:**
  explicitly try embeddings at It3 (3D) / It4 (real camera).
- **DECIDED — senses = a toolbox of lightweight primitives the brain composes** (= the queryable seam, ADR-002
  §5). Granularity = **mid-level verbs** ("what changed in R", "read R", "segment the moving things", "seen
  this?"). **Toolbox for discovery; compiled reflex for routine** — composing primitives via the LLM *every step*
  is the Cradle GPT-4o-per-step cost catastrophe. Interface stays **OPEN/gated** (don't spec it before the gate).

## 2. The sensorimotor floor — senses (reference)
The named primitives (ADR-002 §3), plain ↔ technical:
- **change** = frame-differencing · **motion/flow** = optical flow · **ego-motion** = visual-odometry signal
  (`best_shift`: whole-frame registration; residual after camera comp = foreground motion) ·
  **blob-segment** = connected-components on a foreground mask · **persistence/track** = temporal data association ·
  **recognition-key** = perceptual hash (→ embedding on rich data) · **glyph-read** = OCR.
- **Have already (in `core/`):** change/grid-max (AUC 0.99), ego-motion + foreground residual, per-tile hash.
- **Missing:** clean blob-segmentation into object crops, tracking, any live embedding (CLIP only in `eval/`).
- **For the gate, newly needed:** `read_text` (OCR a region) + a clean `whats_changed` + the `consequence` signal.
  Everything else is post-gate.

## 3. Rung-2 ideas (post-gate, once entities can be grounded) — OPEN
- **Entity detection via motion.** Moving thing (still *or* ego-comp'd moving camera) → diff/residual →
  connected-components → object boxes. Cheap, classical (numpy/OpenCV), no model. *Static* objects under a static
  camera would need real segmentation — **probably YAGNI** (agents move/spawn = change events; static terrain is
  already the occupancy grid/tilemap). Keep the primitive **meaning-free** ("here are the blobs + fingerprints");
  the brain hypothesizes "those are enemies," behaviour grounds it. Hardcoding "blob=enemy" = the bespoke-perceiver
  drift.
- **`focus` — foveated attention** (the unifying primitive). `focus(region) → crop → appearance-key → match vs a
  within-run appearance store → {known: id | novel}`. **Makes embeddings affordable** (embed only the focused crop,
  not the frame) → the cheap path to rich-data recognition at It3/It4. The gate's `read_text(region)` is `focus`'s
  degenerate case. **Disciplines:** returns a fingerprint + match, **not raw pixels to the brain** (else the
  screenshot→confabulation tripwire reopens); appearance gives **identity/novelty only** — *meaning* still comes
  from behaviour; appearance-match **aliases** (the hash-alias / ObjectNav "visually-similar-but-wrong" scar) → it
  is a hypothesis, must be behaviour-confirmable.
- **Spatial reasoning + a spatial scratchpad.** Two layers: **(L1) grounded substrate** (System 1 owns; position/
  adjacency/walkability; *true*; mostly built — tile→function map + occupancy/place-graph) and **(L2) the scratchpad**
  (brain owns; spatial *guesses* — "exit north", "region dangerous"; behaviour-graded) = **the spatial instance of
  hypothesize→ground→compile.** Principles: **reason ON the map, not IN the LLM's head** — offload geometry to
  query tools (`path(A,B)`, `nearest(enemy)`, `direction_to(goal)`); the LLM reasons about *meaning* over the
  results (LLMs are weak at metric-grid geometry). **Lean topological/landmark-graph** for the brain-facing layer
  (LLM-friendly + generalizes to 3D), metric grid underneath in System 1. **YAGNI to respect:** maybe **no
  persistent brain-owned store** — System 1 holds the map, the brain re-reasons each wake. **PROBE:** can the brain
  reach a spatial goal with only a local view + query tools + *no* persistent store? If it re-explores cleared
  ground / loses a threat across wakes, *that lostness specifies exactly what L2 must hold* — let the failure design
  the scratchpad. A primitive version **already runs** (`world_mcp` observe/explore/goto = spatial reasoning over
  corridors); the real question is how much richer the view needs to be for *things* in space, not from-zero.
- **Source note:** `spatial_reasoning_in_2d.txt` (David's 7-layer design) maps onto the above — its Layer 5
  (interaction→walkability) is already built (the tile-map, ADR-002's existence proof); Layer 2 ≈ occupancy/
  place-graph; Layers 1/3/4 (CLIP, scene context, spatial RAG) are the embedding parts, deferred by the fit law.

## 4. PARKED for It3+ (the real-time regime — conscious ADRs, never drift)
*(Also recorded in `reports/2026-06-25-roadmap-v2-discovery-loop.md` "Parked for It3+".)*
- **The latency / VLA concern.** When a world stops pausing (3D/FPS, sub-100ms reflexes), "wake System 2 at
  decisions" breaks — the named It3 discontinuity. Sequential action has two flavors: **skill-expansion**
  (`goto`/`explore`, the turn-based version we have) vs **action chunks + interrupt** (open-loop sequence halted by
  the pixels-only **consequence monitor** when reality diverges — the consequence detector doubles as the interrupt).
  Our fast layer is a **compiled *symbolic* policy, not a trained net** (no-training). **Not testable on a
  turn-based Game Boy** — needs a non-pausing world (Doom/Portal).
- **System-2-as-expert → distill a *learned* fast policy (a VLA).** David's hypothesis: S2 acts through S1 across
  many episodes, **self-generating + self-labelling** traces (free — kills the human-teleop cost that makes real
  VLAs expensive), then a fast policy imitates it = the *neural* "distill System 2 into System 1." **Data math
  favors it in the narrow regime:** narrow single-task BC (ACT/ALOHA ~50 demos; Diffusion Policy ~100–200) is cheap;
  only *generalist* VLAs need 10⁵–10⁶ trajectories (RT-1 130k, OpenVLA/Octo ~1M). **David's framing: the longer the
  agent stays in one environment, the faster it gets** (accumulated self-play → compiled/distilled faster policy =
  time-in-world → speed). **Tensions (why it's gated, not free):** (1) it **revises the no-per-world-training north
  star** — explicit invariant-revision ADR; (2) **neural/GPU infra departure** (project is CPU-only) — **DEFERRED,
  future feature** (David); (3) BC distribution-shift → **iterative DAgger**, S2 keeps re-labeling, doesn't cleanly
  "retire"; (4) only pays off **sub-100ms** (FPS) where a symbolic policy can't express the reactivity. **Default
  stays:** S2 writes a *symbolic* policy; a trained net is the **rare, justified exception**, not the plan.

## 5. Risks / traps to respect (each already bit us once, or is a named failure mode)
- **Cost catastrophe** — composing primitives via the LLM every step = Cradle's GPT-4o-per-step. Mitigation = the
  compile step (discovery via toolbox → routine via free reflex).
- **Screenshot→brain confabulation** — never hand raw pixels/crops to the brain; symbolic/fingerprint only.
- **Appearance aliasing** — "seen this before, by appearance" aliases (hash-alias / ObjectNav). Appearance proposes;
  behaviour grounds.
- **LLMs are weak at metric geometry** — externalize spatial reasoning to query tools; don't make the LLM do it.
- **Bespoke-perceiver drift** — writing game-specific perception logic is the exact thing ADR-002 kills; keep
  primitives meaning-free, semantics in the hypothesize→ground loop.
- **Invariant drift** — the no-training and learning-boundary laws get revised only by **deliberate ADR** (the
  VLA-distillation and across-run-memory items both touch them), never silently.

## 6. The cheap probes worth running (when their gate opens)
1. **The HUD gate (Rung 0, ACTIVE)** — grounds life + rejects a decoy vs the RAM oracle. Settles the root assumption.
2. **Consequence-detector cross-game generality** (a *new* risky assumption the gate doesn't cover) — does the
   pixels-only "something terminal happened" signal fire across ≥2 games **without per-game tuning**? If it needs
   tuning, that's quiet hand-coding.
3. **Spatial goal-reaching without a persistent store** (Rung 2) — see §3; the lostness specifies the scratchpad.
4. **Foveated embeddings separate entities on richer data** (It3+) — does focus+embedding actually distinguish
   entities once the data is complex enough to need embeddings?
