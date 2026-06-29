# Perception ontology — the end-state stages (world-agnostic)

_2026-06-28. The canonical reference the perception roadmap reorganizes around._

Perception is a pipeline where **meta-perception (routers) configures content-perception, then fusion
assembles the result.** Each stage classifies into a **stable ontology**: across GB → GBA → NDS → a desktop
screen → a robot camera, the categories' *values* differ, but the *axes* do not. Downstream stages are
**dispatched** by the upstream ones — a primitive run outside its ontology cell is the source of every
class-bounded failure we have measured (motion-localizers on follow cameras, appearance-segmentation on busy
backgrounds, colour cues on monochrome).

Each stage is tagged by **how it's determined** (single-frame / behavioural / accumulated) and its **cadence**
(per-frame vs per-world prior — i.e. compute every tick vs probe-once-and-cache).

---

## Phase I — Meta-perception (establish the structure; the routers)

**S1 · Substrate** — what the signal *is*, independent of content.
- Ontology: resolution · channels (**colour vs monochrome**) · # viewports (single/dual/multi) · rendering
  basis (**tile · free-sprite · 3D-rendered · UI/widget · natural-image**)
- _single-frame, cheap_ · **per-world prior** → routes which appearance primitives are valid (tiles →
  recurrence/CC; colour → colour cues; 3D → breaks tile methods).

**S2 · Mode / context** — what *kind* of screen this is, right now.
- Ontology: gameplay · menu · dialog · cutscene/transition · title/boot · map/inventory  *(desktop:
  app-window · dialog · desktop · robot: task-phase)*
- _per-frame_ · **per-frame (dynamic)** → routes spatial-vs-symbolic parsing; gates whether locomotion means
  anything this frame.

**S3 · Viewpoint / camera class** — the self↔viewport relation.
- Ontology: fixed · follow/scroll · 1D-scroll · static-single-screen · **egocentric/first-person**
- _behavioural (move; does the avatar or the world move?)_ · **per-world prior** → routes the localization
  method.

**S4 · Embodiment & agency** — is there a self, and how do my actions act?
- Ontology: self-presence (single-avatar · disembodied/cursor · multi-entity · piece-control) × control
  coupling (direct-locomotion · indirect/cursor · turn-based vs real-time · button vs pointer/touch)
- _behavioural (contingency — what's controllable)_ · **per-world prior** → routes whether
  avatar-localization applies; defines "did my action land."

**S5 · Spatial topology** — the shape of the world.
- Ontology: grid/occupancy · continuous-2D · place-graph/rooms · metric-3D · non-spatial (menu/puzzle)
- _accumulated behaviourally_ · **per-world prior** → routes the `spatial_memory` representation.

## Phase II — Content perception (each dispatched by Phase I)

**S6 · Localization & pose** — where am I in the world.
- Dispatched by S3×S4×S5: motion-localizer (fixed) · odometry + centre-prior (follow) · place-node (rooms) ·
  none (non-spatial / egocentric-no-map).

**S7 · Entities / objects** — what else is in the scene.
- Dispatched by S1×S3: motion (movers, fixed cam) · appearance-outlier (tiled bg) · colour-segment (colour
  substrate) · learned (3D/natural). Output = positions, **not** identities (function needs grounding).

**S8 · Symbolic surface** — text, numbers, icons, options.
- Dispatched by S2×S1: OCR / glyph-read in menu/dialog/HUD modes. HUD scalars, dialog, menu options.

**S9 · Affordances** — what I can *do* from here.
- **Derived, not sensed**: open directions (from S5/S6) · interactables (from S7 + grounding) · options (from
  S8). An entity becomes an affordance only once behaviour grounds its function.

## Phase III — Integration

**S10 · Temporal fusion & confidence** — smooth, track, bridge gaps; **never fabricate**. Kalman/odometry on
pose; persistence on entities; emit confidence (low ⇒ attach the raw frame + tell the planner).

**S11 · State assembly** — fuse into the `SymbolicState` seam:
`{context, pose, spatial_memory, affordances, entities, last_action, screen_text, confidence}` — the single
thing the brain sees.

---

## Why this is the end-state

1. **Universal across domains.** Same axes, different cells. A **desktop screen**: S1=UI/widget+colour,
   S2=window/dialog, S3=static, S4=disembodied-cursor, S5=non-spatial/document, S8=text-rich. A **robot**:
   S1=natural-image, S3=egocentric, S4=own-body+proprioception, S5=metric-3D. Nothing in the taxonomy breaks
   — it fills different cells.
2. **Determinacy is labelled.** Each stage is tagged single-frame / behavioural / accumulated and per-frame /
   per-world-prior → the cost model (what to compute every tick vs probe-once-and-cache).
3. **It IS the per-world perceiver config, formalized.** Phase I (the priors) is the content of the swappable
   "perceiver constitution." Most of it is **behaviourally discovered** (S3, S4, S5) — the ADR-002 thesis
   generalized from "what is my HP" to "what *kind of world* is this."

## Build implication

**Router first, then fill the cells.** Build the Phase-I classifier stack (S2, S3, S4 are the weak-coverage
router stages — the natural lightweight-CNN targets), then dispatch the Phase-II content primitives per cell.
Classical methods already work in-cell at S6–S8; learned models belong at the routers (S2–S4) and as the
S7 climb target — not as a blanket replacement. (Training detail + dataset plan: see the companion plan.)
