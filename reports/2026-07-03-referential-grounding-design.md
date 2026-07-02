# Referential / static-object grounding — design + cheap probe (2026-07-03)

_Status: **design + leading-indicator probe**. Changes no repo code. Gate-first governs; this scopes the
keystone gap named in `reports/CONTEXT-BRIEFING.md` ("The frontier" §named/semantic layer) and `HANDOFF.md`
§1. Aligned to ADR-001 (perceiver-only, no brain edits) and the North Eye 7-slot contract + Realizer Ladder
(`reports/north-eye-perception-constitution.md`). Flags where a piece leans toward ADR-002 (self-built
ontology, PROPOSED/gated)._

---

## 0. The gap, concretely

The brain can already point at referents it perceives (*explore*, *go-to-cell*, *win-battle*) — instruction-
following ≈ objective injection (`CONTEXT-BRIEFING.md` §"On instruction-following"). What it **cannot** do is
point at a *named static object or place* and have System-1 locate it on screen without privileged state.

Two live failures motivate it:
1. **It1 Poké-Ball pick only worked because the run BRIEF hard-coded the answer.** `runs/brain_red_starter/CLAUDE.md`
   step 3 literally says *"the balls are on the table tiles EAST (right) of you… press `right` once… then `a`."*
   That is the human bridging the missing static-object channel. The perceiver has **no static-object percept**:
   its only entity channel is **motion-saliency** (`games/pokemon_red/saliency.py`, `core/entities.py`,
   `core/blob.py`) — a Poké Ball sitting on a table produces zero foreground and is invisible to it.
2. **NDS/Emerald audits had no way to name a menu target or a destination** — same missing layer, no
   language→location resolver.

---

## 1. Decomposition (per the master principle: decouple localization from classification; behaviour=truth)

Referential grounding is **not one capability**. It splits into three decoupled sub-problems, mirroring the
project's localization-vs-classification split and its L1→L3 stack:

| Layer | Question | What it emits | Realizer rung | Nature |
|---|---|---|---|---|
| **(a) Static-object detection** | "what discrete candidates are on screen?" (NOT motion) | screen candidates (bbox/centroid/tile) + fingerprint | **R0** (pixel ops) → R1 template | L1 signal, meaning-free |
| **(b) Naming / anchoring** | "which candidate/place is *this label*?" | candidate↔label / place↔label binding | **R1** online lookup → R3 VLM only if forced | L2/L3, the named/semantic layer |
| **(c) Resolution** | "brain says a name → give me a screen loc or goto target" | (col,row) or goto-cell, + confidence + `None` | R0 (map lookup over (a)+(b)) | seam query |

The load-bearing discipline: **(a) is appearance-cheap and world-agnostic; (b) is where meaning enters and
must be behaviour-grounded, never hand-asserted; (c) is plumbing over (a)+(b).** Building (a) alone is a
concrete, gate-able win; (b) is the genuinely hard/ADR-002-adjacent part; (c) is trivial once (a)+(b) exist.

### What each layer REUSES vs NEEDS-NEW

- **(a) Static detection — mostly reuse.**
  - Reuse `core/blob.py` `connected_components` (`blob.py:200`) — pure-numpy 4-connected components over a
    **static** foreground mask (edge/colour-distinctiveness), instead of the motion mask it's paired with today.
  - Reuse `core/tilemap.py` `TileFunctionMap.fingerprint` (`tilemap.py:94`) as the per-candidate **recurrence
    key** — *touch-once-recognise-everywhere*, verified below.
  - **New:** a *static* saliency mask (colour-distinctiveness / edge density per tile) to replace the
    rolling-background mask in `core/entities.py:80`. `EntityDetector` is structured perfectly for this — swap
    `RollingBg`→a static-mask function and it already does avatar-drop, HUD-drop, min-area, centroid. ~1 new
    numpy function + a flag on `EntityDetector`.
- **(b) Naming — the hard part, partly ADR-002.**
  - Reuse the **hypothesize→ground→compile existence proof**: `TileFunctionMap` already binds an *appearance
    key* to a *behaviour label* (walkable/blocked) online (`perceiver.py:138` `_observe_faced_tile`). Naming a
    static object is the SAME mechanism generalised from "function" to "identity/label": bind candidate-key →
    label when behaviour (interact+A → a Poké-Ball dialog) confirms it. **This is exactly ADR-002's move**
    (self-built ontology, PROPOSED, §9 gated) — flag it; do NOT build the general ontology loop here.
  - Reuse `screen_text` decode (`perceiver.py:267` `_read_text`) as the cheap **behavioural label source**:
    "what did interacting with this candidate say?" is the pixels-only grounding signal (no oracle).
  - **New / gated:** the label store keyed by candidate-fingerprint. Minimal version is per-run + hand-seeded
    from the brief's noun; the general version is ADR-002 and must not be built pre-gate.
- **(c) Resolution — pure reuse.**
  - The place-graph + occupancy map (`perceiver.py:501` reachable-place BFS, `spatial_memory.map`) already
    turn a world cell into a `goto` target. A resolver is: name → candidate (via b) → its world cell (via a's
    centroid + `_PLAYER_CELL` offset, `perceiver.py:57`) → existing `goto`. No new machinery.

---

## 2. Cheap probe — can a cheap detector find the Poké Balls? (READ-ONLY, no paid LLM, no live run)

Recorded frames used (already exist; Oak's lab = RAM map 40, 145 frames): `runs/brain_red_starter/world/`
`frame_000321.png`, `frame_000366.png`, `frame_000381.png` — all three clearly show the Poké-Ball table (the
exact scene the It1 brief hard-coded). Probe script kept in scratchpad (not committed).

### Channel A — the EXISTING motion detector (`core/entities.py`) on a static frame
`EntityDetector.detect()` on each lab frame → **0 entities** (all 3 frames). Confirms the gap quantitatively:
the current channel is motion-only; a static ball is invisible. This is the failure the brief hand-patched.

### Channel B — cheap static red-saliency (R0, pure numpy)
Per-pixel **saturated-red** mask `(R>150) & (R−G>90) & (R−B>90)` + `connected_components` (reused from
`core/blob.py:200`), min 6px. Consistent across all 3 frames:

| blob class | count | area (px) | what it is |
|---|---|---|---|
| area ≈ 80, collinear row, equal size | **3** | 80,80,80 | **the three Poké Balls** ✓ |
| area ≈ 114 | 2 | 114,114 | the red machine/PC on the left wall (false positive) |

Headline: **a cheap R0 detector finds all three Poké Balls, 100% recall**, with centroids landing exactly on
the table row (frame 321: tiles (5,4),(6,4),(7,4)). **Precision if "any red blob = ball" = 3/5 = 60%** (the
2 machine blobs). But the balls are trivially separable from the machine by cheap shape cues — **uniform equal
area (~80px each), collinear (same row, 16px pitch)** vs the machine's larger irregular blobs — recovering
precision to ~100% with one collinearity/equal-size heuristic. No motion, no RAM, no model, microseconds.

### Channel C — tile-fingerprint recurrence (`TileFunctionMap.fingerprint`, R0)
- **Cross-frame recurrence works exactly:** ball tile (5,4) in frame 321 and the same ball at (5,6) in frame
  366 (camera scrolled 2 tiles) hash to the **identical** key `…000e6`. *Touch-once-recognise-everywhere*
  holds for a static object — the reuse win the tilemap was built for.
- **Distinctness:** across the whole lab frame, the ball-candidate fingerprints have **0 exact collisions and
  0 tolerant (hamming≤8) collisions** with the 17 other (non-red) lab tile-types. The ball appearance is a
  clean, separable key.
- **Caveat (honest):** a single Poké Ball spans **3 adjacent tiles** with **3 different** keys
  (`…0e6`,`…066`,`…067`) — sub-16px object + table shading. So "one object" needs the connected-components
  grouping from Channel B; the per-tile fingerprint is a *recurrence/identity* key for a grouped candidate,
  not an object segmenter on its own.

### What a cheap R0/R1 static channel WOULD and WOULDN'T catch
- **WOULD:** high-contrast / distinctly-coloured static sprites on a plainer background (Poké Balls, item
  balls, coloured doors/signs, HUD icons); recognise the same object across camera shifts; give a world-cell
  target for `goto`. Covers the two live failures' *detection* half.
- **WOULDN'T (needs R1/R2 or layer b):** telling a ball from a same-coloured appliance without the
  shape/behaviour cue; objects that blend into their tileset (a brown box on a brown floor — no colour/edge
  pop); **naming** anything (that is layer b — behaviour or a VLM, not colour); menu-target naming on DS
  (different fidelity; colour-pop won't generalise — that's an R1 template / OCR job).

---

## 3. Smallest first build (the honest end-to-end test)

Build **only layer (a) + the trivial (c)**, seed (b) from the brief noun — do **not** build the ADR-002
naming loop yet:

1. **Static-candidate percept** (`games/pokemon_red/` or `core/`): a static-mask variant of `EntityDetector`
   (colour-distinctiveness + edge density mask → `connected_components` → equal-size/collinear grouping →
   candidate {centroid, world-cell, fingerprint}). Surface candidates in `SymbolicState.spatial_memory`
   alongside the existing motion `rois` — additive, no contract change (same pattern as `perceiver.py:495`).
2. **Resolver** (c): brain asks "static objects near me?" → gets candidate world-cells → existing `goto`/face
   +`a`. For It1, the brain no longer needs "balls are EAST" — it reads *"3 static candidates at cells …"*,
   faces the nearest, presses `a`.
3. **Grounding label** (thin b): the candidate the brain interacts with that yields a Poké-Ball dialog
   (`screen_text`) is *behaviourally* the ball — bind key→"pokeball" **per-run only** (learning-boundary law).

**The honest end-to-end test (the whole point):** **un-bridge the brief** — delete step 3's
"balls are on the table tiles EAST of you" hint from `runs/brain_red_starter/CLAUDE.md`, leave only "get the
Pokémon; interact with what you find" — then **re-audit** (the paid `claude -p` It1 run). **PASS = party 0→1
with the brain locating the ball from the static-object percept alone.** That is the leading-indicator turned
proof: the perceiver, not the human, grounded the referent.

---

## 4. Gate / tripwire (what greenlights the build vs kills it cheap)

**Cheap pre-build gate (extend the scratchpad probe to a scored offline harness — no paid run):** hand-label
the ball centroids on ~20 lab frames + a handful of *distractor* frames (lab with no balls, other interiors).
- **PASS (greenlight layer a):** static detector achieves **recall ≥ 0.9** on ball tiles AND **precision ≥ 0.8**
  *after* the shape/collinearity heuristic, AND **0 false candidates on the distractor frames** (fail-safe:
  a miss must return "no candidate / escalate", never a phantom — `CONTEXT-BRIEFING.md` cheap-index rule).
  Current 3-frame probe already hits recall 1.0 / raw-precision 0.6 → ~1.0 post-heuristic → **on track**.
- **FAIL (kill cheap):** if precision needs the balls' *specific* red (won't generalise — every world has a
  different palette) OR the shape heuristic is Pokémon-specific → the cheap colour channel doesn't generalise;
  **stop at Red, do not lift to `core/`**, and reframe (a) as an R1 template/edge-density detector or defer to
  the ADR-002 gate. (This mirrors the leave-one-tileset-out kill in `core/tilemap.py`: appearance ≠ identity
  across tilesets.)

**End-to-end gate (the paid audit, only if the offline gate passes):** party 0→1 with the brief un-bridged,
verified against the RAM oracle **and** the transcript (guard the false positive — `CONTEXT-BRIEFING.md`
adversarial-verification rule). Constancy check: all new code world-side, brain = unmodified `claude -p`.

**ADR-002 tripwire:** layer (a) is safe/cheap/ADR-001-clean (perceiver-only). Layer (b) — binding a
candidate-key to a *language label* generally, across worlds, online — **IS** the ADR-002 self-built-ontology
move (`_archive/2026-06-25-adr-002-ontology-discovery.md` §9, PROPOSED/gated). Do **not** build the general
naming loop under this doc. The smallest build seeds the label from the brief noun + one behaviour
confirmation, per-run — enough to un-bridge It1 without opening the ontology direction. If a reviewer finds
themselves writing a general "name any object in any world" store, **STOP — that is the ADR-002 gate, not
this one.**

---

## 5. North Eye 7-slot contract for the static-object primitive (layer a)

1. **Computational:** "what discrete static candidates are on screen, and where?" — serves the *resolve-a-
   named-target* decision. Minimal: candidates + location, not scene reconstruction.
2. **Grounding:** appearance-cheap detection is *advisory*; the label/identity is grounded by
   behaviour (interact→`screen_text`) — behaviour=truth, appearance-advisory, exactly as walkability is today.
3. **Algorithmic:** static mask (colour-distinctiveness/edge) → `connected_components` → shape grouping →
   fingerprint. R0.
4. **Implementational:** numpy/PIL, reusing `blob.py` + `tilemap.py`. Swappable up to R1 template / R2 CNN if
   the colour channel fails the gate.
5. **Output:** candidate list + per-candidate confidence + explicit **`None`/empty** when nothing pops (fail
   safe → brain escalates/explores, never a phantom).
6. **Layer & composition:** L1 signal (detection) feeding L2 anchoring (b) feeding the seam query (c).
   Consumes a frame; produces `spatial_memory` candidates, additive to existing `rois`.
7. **Selection:** activated by grounding payoff (does a static candidate the brain interacts with produce a
   consequence?), not a hand-label — same self-selection bar as every North Eye primitive.

---

## Appendix — file:line anchors
- Motion-only entity gap: `core/entities.py:80` (`RollingBg` mask), `games/pokemon_red/saliency.py:59`,
  `games/pokemon_red/perceiver.py:464` (motion-saliency block, camera-static only).
- Reusable primitives: `core/blob.py:200` (`connected_components`), `core/blob.py:102` (`segment_blobs`),
  `core/tilemap.py:94` (`fingerprint`), `core/tilemap.py:135` (`classify`).
- Behavioural-label existence proof: `games/pokemon_red/perceiver.py:138` (`_observe_faced_tile`),
  `core/tilemap.py:118` (`observe`).
- Resolution substrate: `games/pokemon_red/perceiver.py:501` (reachable place BFS), `:534` (`spatial_memory`
  assembly), `:57` (`_PLAYER_CELL` for screen→world).
- The hard-coded bridge to remove for the honest test: `runs/brain_red_starter/CLAUDE.md` step 3.
- ADR-002 direction (do not cross without its gate): `reports/_archive/2026-06-25-adr-002-ontology-discovery.md` §9.
```
Probe numbers (3 lab frames): motion detector 0/3 balls; static red-saliency 3/3 balls (recall 1.0),
raw precision 0.6 (2 machine FPs), ~1.0 after equal-size+collinear heuristic; fingerprint recurrence exact
across camera shift; 0 collisions with 17 other lab tile-types.
```
