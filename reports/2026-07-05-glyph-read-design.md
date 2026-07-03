# Glyph read (OCR) — design + pre-registered gate (2026-07-05)

_Status: **design + pre-registered gate only**. No code changes, no perceiver edits, no brain edits.
Gate-first governs; this scopes ADR-002 §3's sensorimotor-floor primitive named "glyph read (OCR) —
can't behaviour-ground a number without reading it" (`reports/_archive/2026-06-25-adr-002-ontology-
discovery.md` §3), designed to the North Eye 7-slot contract + Realizer Ladder
(`reports/north-eye-perception-constitution.md`). Builds only what a future gate run would need;
nothing here is promoted or greenlit by writing it down._

---

## 1. Scope the claim

**What "glyph read" must do for the next rungs of the north star**, and nothing more:

**(a) Unblock menu/dialog navigation in the sweep games.** HANDOFF's 2026-07-04 GBA probe sweep
(6 games, `runs/probe_*`) found the SAME #1 gap in every game: **no text channel**. Verified directly
from the sweep transcripts (this pass): none of the 6 games' worlds expose `read_region` at all —
`world_mcp.py:94` scopes `_REGION_TOOL_WORLDS = {"cave_noire", "cave_noire_baseline", "gauntlet",
"kirby_dreamland"}`, so every GBA probe ran with `observe`/`press_button`/`press_sequence`/`wait`/
`explore` only. The Zelda probe's own verdict names it explicitly:
`verdict=stuck_dialog gaps=...,dialog_and_name_entry_text_unreadable,menu_options_unreadable,...`
— it got boxed into a file-select/name-entry screen with **no way to see the letter grid**, and
separately the grid-perceiver *hallucinated dungeon cells* on a menu screen because it had nothing
else to report. Both symptoms trace to the same hole: no primitive answers "what does this screen
say" or even "is there text here at all."

**(b) Feed the naming/anchoring layer.** `reports/2026-07-03-referential-grounding-design.md` §1(b)
already names text as **the cheapest label source** for naming a static candidate ("interact with
candidate → `screen_text` says 'POKé BALL'" grounds the label without a VLM). That design explicitly
reuses `_read_text` (dialog decode) as the behavioural-label channel and defers the general "bind any
appearance-key to any label" loop to ADR-002. Glyph-read is the **prerequisite pixel-to-string
plumbing** the naming layer calls into — it doesn't do naming itself.

**(c) Stay world-agnostic-within-sensory-class.** Per ADR-002 §10 and the North Eye ladder: the
primitive must not bake in Pokémon Gen-1's 8px grid, GB's fixed 4-shade palette, or any one game's
textbox geometry. `games/pokemon_red/textbox.py` (existing, read below) is the **anti-pattern to
generalize away from**, not the target design.

**Non-goals (explicitly out of scope for this doc):** full-page paragraph OCR, general-purpose
zero-shot text spotting, anything that reads ROM tile data without David's sign-off (see §2c), and
the ADR-002 naming/anchoring loop itself (referential-grounding design already fences that off).

---

## 2. The existing precedent — read before designing anything new

`games/pokemon_red/textbox.py` + `eval/calibrate_font.py` is a **already-built, working R1 template-OCR
system** for exactly one game:
- Fixed geometry hand-coded: `CELL=8`, `X0=8`, `NCELLS=18`, `LINES=((112,120),(128,136))` — Gen-1's
  known textbox pixel layout.
- The glyph table (`gen1_font.json`) is calibrated **offline, once, by a human** reading 6 sample
  frames and typing the ground-truth strings (`calibrate_font.py` `SAMPLES`), not learned online, not
  brain-confirmed, and not re-run per session.
- Lookup is exact-match + small-Hamming fallback (`FontTable.lookup`, `tb.pack` — an 8x8 binary cell to
  a 64-bit key) — deterministic because emulated rendering is deterministic. Unknown glyphs → `'?'`,
  never a fabricated guess (the same honesty rule as everywhere else in the codebase).
- This is the exact template-match KEY-and-LOOKUP mechanism the ADR-002-native design below reuses —
  but the offline/human/per-game calibration is precisely what must NOT be repeated per world; that is
  a hand-coded-per-game font, which HANDOFF's own drift language would call the "primitive ossification"
  pattern if generalized this way (`reports/_archive/2026-06-25-adr-002-ontology-discovery.md` §11).

**The HUD-grounding gate precedent** (`reports/2026-07-03-adr002-gate-plan.md`,
`reports/_archive/2026-06-25-adr-002-ontology-discovery.md` §9, PASSED live 2026-07-03) already proved
the OTHER end of the spectrum: a brain handed `read_region` (a raw pixel crop, upscaled 3x, returned as
an image — `world_mcp.py:247` `_READ_REGION_TOOL`) can read digits itself, zero-shot, with its own
vision, well enough to ground a HUD value against a hidden RAM oracle at 1.000 truth-agreement over 15
readings. **No OCR primitive was needed for that gate to pass** — the brain's own vision was the
reader. This reframes the whole question: is a "glyph read" primitive needed at all, or is `read_region`
+ routing already sufficient, and the only missing piece is *knowing where to look*?

### Quantified: what fraction of brain calls are already reads?

Counted directly from the two available live transcripts (`runs/brain_cn_gate/transcript.jsonl`, the
PASSING HUD gate run; `runs/probe_*/transcript.jsonl`, the 6 GBA sweep probes):

| Run | Total tool calls | `read_region` calls | Fraction |
|---|---|---|---|
| `brain_cn_gate` (HUD gate, PASS, region tool available) | 99 | **39** | **39%** |
| 6x GBA sweep probes (region tool NOT wired for these worlds) | 15–19 each | **0** (tool absent) | 0% (not a choice — unavailable) |

**Reading this honestly:** in the one run where the brain *had* a region-read tool, it spent **~2 in 5
of every tool call** looking at pixels closely — that is the "cost per read" ADR-002's gate plan flagged
as an open question, now measured. It is not free: each `read_region` call is a full LLM turn (image in,
text out) at System-2 prices, and the gate run cost $3.52 for one short combat segment. In the sweep
games, the tool was simply never exposed, so the 0% figure is an availability gap, not a frequency
finding — but it corroborates HANDOFF's claim that this is the most-hit missing primitive: every single
sweep game got stuck on text/menus with no reading capability at all, GB-family games included ones that
DO have `read_region` gated on elsewhere in the codebase (`kirby_dreamland`, `gauntlet`) but the 6 GBA
titles do not.

---

## 3. Candidate realizers (R0-first, per the Realizer Ladder)

### (a) R0 zero-shot: brain reads `read_region` crops directly — already proven

The "primitive" here is NOT recognition (the brain already does that, per the HUD gate) — it is a cheap
**text-REGION detector**: where on screen is there likely to be readable text, so the brain knows where
to point `read_region` instead of guessing/tiling blindly (as MiniWoB's brain already does by tiling
crops over an unknown page, per HANDOFF 2026-07-04's computer-use block — workable but wasteful).

- **Computational:** "which screen regions likely contain glyphs?" — serves the routing decision (where
  should the brain spend its next `read_region` look), not recognition itself.
- **Algorithmic (R0):** text in 2D sprite-based games renders as **high local edge-density in a narrow
  horizontal band** — small glyph cells packed on a fixed-height row, unlike open scenery or sprites.
  A cheap detector: per-row edge-density profile (Sobel-free — reuse the gradient-popcount trick already
  in `core/tilemap.py:105` `TileFunctionMap.fingerprint`'s H/V dHash) thresholded + connected-components
  over the row-band (reuse `core/blob.py`'s `_label_bfs`) to find candidate text boxes (bbox list).
- **Cost this solves:** not accuracy, but **call count**. If the brain currently must `read_region` a
  guess-and-check sequence of crops to find where a textbox is, a free region-hint cuts that to one
  well-aimed look. This is a pure ROUTING/foveation aid, not a text-content channel — it never emits a
  character.
- **Ladder rung:** R0 (numpy, no training, reuses two already-shipped primitives).

### (b) R1 self-calibrating template OCR — the ADR-002-native design (recommended core piece)

Generalizes `textbox.py` + `calibrate_font.py`'s mechanism (glyph-key → char via template-match) but
inverts WHO calibrates it and WHEN: instead of a human typing ground truth offline once per game, the
**brain confirms readings within a run**, exactly the `TileFunctionMap` pattern
(`core/tilemap.py`) applied to glyphs instead of tile-function:

1. The text-region detector (3a) or the brain's own hypothesis flags a candidate glyph cell grid
   (cell size inferred from row edge-density peaks — most 2D console fonts are fixed-pitch 8x8 or 8x16,
   detectable from the row's own periodicity, not hand-typed per game).
2. First occurrence of a cell shape: brain reads the region via `read_region` (as it already does,
   proven at the HUD gate) and reports the string. S1 hashes each 8x8 (or detected-pitch) cell
   (`TileFunctionMap.fingerprint`-style dHash+intensity key, reusing the EXACT existing keying code,
   just applied to glyph cells instead of world tiles) and binds `key → char` from the brain's read,
   **per-run only** (learning-boundary law — blank every run, same as `TileFunctionMap` itself).
3. Future occurrences of the SAME key (recurring glyphs — deterministic emulator rendering guarantees
   identical bitmaps, exactly as `calibrate_font.py`'s docstring notes) are read **for free**, no LLM
   call — S1 template-match lookup, microseconds.
4. Novel/unseen keys fall back to a fresh brain read (never a fabricated guess — same `None`-on-unknown
   discipline as `FontTable.lookup`'s `'?'` and `TileFunctionMap.classify`'s `None`).

This is genuinely the **within-run, brain-confirmed generalization** of the already-proven
walkability-hypothesis loop (ADR-002 §4's "existence proof") and the already-proven glyph-template
mechanism (`textbox.py`) — combined so neither needs a human in the loop and neither is hand-coded to
one game's font.

- **Ladder rung:** R1 (classical CV keying + a tiny online dict — no model, no training weights, fully
  reuses `core/tilemap.py`'s hashing code with a glyph-sized cell instead of a tile).

### (c) R1 ROM-font path — flagged, needs David's OK, NOT the default

A GB/GBA ROM's font tile data can be extracted directly (bypassing pixel-rendering entirely) to build a
perfect glyph table with zero brain calls, ever. This is **strictly faster and cheaper than (b)** but:
- **Violates the standing constraint:** "ROM font extraction requires David's explicit OK — optional R1
  lever needing sign-off, not the default path" (this doc's own instructions).
- It is also GB/GBA-specific (a ROM format assumption) — doesn't generalize to NDS, browser/MiniWoB, or
  ARC-AGI-3's text-free grid, three of the five world-classes constancy already spans (HANDOFF
  2026-07-04). (b) generalizes across all of them (anything with a screen and recurring pixel patterns);
  (c) only ever helps GB-family carts.
- **Recommendation: do not build (c) under this doc.** Flag it as an optional accelerant for GB-family
  worlds specifically, contingent on David reviewing the extraction method (which ROM bytes, which
  license/legal posture) before any code touches it.

### (d) R2 small OCR model — climb only on a measured bar

A small fine-tuned OCR/CRNN-class model (per the Realizer Ladder's R2 rung) is the correct climb **only
if** (b) provably fails on real data — e.g. proportional (non-fixed-pitch) fonts, anti-aliased/photoreal
text (3D games, ADR-002 §10's "re-tiers for 3D" caveat), or genuinely too many distinct glyph shapes for
per-run online caching to pay off before the run ends. **Not attempted here** — no measured failure of
(b) exists yet; building this now would be "perfecting the engine before testing the riskiest
assumption" (the ADR-002 anti-drift table's named tripwire).

---

## 4. Recommendation: (a) + (b) hybrid

**Build the text-region detector (R0) to cut wasted `read_region` calls, and the within-run glyph cache
(R1) to make recurring text free after first-read.** This is the two-piece design ADR-002's own §3 gap
list implies ("glyph read... can't behaviour-ground a number without reading it") without re-inventing
what the HUD gate already proved works (brain-as-reader) or re-committing the sin `textbox.py` already
committed once (hand-per-game font calibration).

### 7-slot contract — (a) text-region detector

1. **Computational:** "where on this frame is there likely glyph-shaped content?" — serves the
   foveation/routing decision (where should the next `read_region` point), not recognition.
2. **Grounding:** advisory only — a region that gets `read_region`'d and the brain reports "no text
   here" is a miss the loop should down-weight for that region's appearance-key next time (a rare
   negative-grounding case, mirrored on `TileFunctionMap`'s "contradicting observation outvotes a stale
   one"). Never asserted as ground truth on its own.
3. **Algorithmic:** row-band edge-density profile (reuse the dHash gradient popcount, `core/tilemap.py`)
   + `connected_components` over the thresholded band (reuse `core/blob.py`). R0.
4. **Implementational:** numpy/PIL, no new dependency, no training.
5. **Output:** candidate bbox list + confidence (density score) + explicit empty list when nothing pops
   (fail-safe — brain falls back to its current tile-and-guess behavior, never a phantom "here's text"
   that isn't).
6. **Layer & composition:** L1 signal, feeds the brain's `read_region` targeting (a routing hint, not a
   new seam field — additive, same non-disruptive pattern as the referential-grounding design's
   candidate list).
7. **Selection:** activated by grounding payoff — does aiming `read_region` at a flagged box actually
   yield text more often than a blind/tiled guess? Measured by the pre-registered gate below, not
   asserted.

### 7-slot contract — (b) within-run glyph cache

1. **Computational:** "have I (this run) already had this exact glyph-cell confirmed by the brain, and
   if so what did it read?" — serves the free-vs-paid-read decision. Not "what does this say" in
   general — only recurrence lookup.
2. **Grounding:** **the frontier slot.** A cache entry is grounded by exactly ONE brain-confirmed read
   (the brain reported this crop's text via `read_region`, same mechanism the HUD gate already used).
   **Invalidation is the honesty story:** if a cached key's context later disagrees — the brain reads a
   region containing a previously-cached key and reports DIFFERENT text than the cache's stored char —
   that is a collision (two different glyphs hashed to the same key, or a font/palette change mid-run)
   and the entry is a `TileFunctionMap`-style contradiction: outvoted, not silently kept. A "confirmed"
   glyph that later mismatches its own confirmed reading must **demote to unknown and re-ask**, never
   keep serving the stale answer — the exact honesty discipline `TileFunctionMap.observe`'s Counter
   already implements for tile-function (majority vote, self-correcting).
3. **Algorithmic:** dHash+intensity key per glyph-sized cell (reuse `TileFunctionMap.fingerprint`
   verbatim — cell size supplied by caller, not hard-coded to 8x8) → dict lookup, exact-match fast path +
   small-Hamming fallback (reuse `FontTable.lookup`'s pattern). R1 (classical CV keying + tiny online
   dict — no model weights).
4. **Implementational:** numpy, reusing two already-shipped modules (`core/tilemap.py`'s hash,
   `games/pokemon_red/textbox.py`'s pack/lookup shape) generalized to accept a caller-supplied cell
   geometry instead of Gen-1's hard-coded constants. Swappable to R2 (small OCR model) only if a measured
   gate shows the online-cache hit rate stays too low to pay for itself (see gate below).
5. **Output:** per-cell `(char | None, confidence, from_cache: bool)` — `None` on an unconfirmed/novel
   key (never a fabricated guess, matching `FontTable.lookup`'s `'?'`/`TileFunctionMap.classify`'s
   `None` discipline exactly). `from_cache=True` is what lets us measure "fraction free" for the gate.
6. **Layer & composition:** L1 signal (recurrence key) feeding an L2 grounded structure (the per-run
   glyph table) — the SAME layering `TileFunctionMap` already occupies for tile-function, just keyed on
   glyph cells. Consumes brain-confirmed `read_region` readings; produces free lookups for future frames.
7. **Selection:** activated by grounding payoff — a cache that doesn't reduce paid reads over a session
   isn't worth keeping; measured directly by the gate's "fraction free after N confirmations" metric,
   not asserted.

---

## 5. Pre-registered gate — cheapest decisive test, free/offline only

Per SS11's "a gate that can't fail" tripwire and the HUD-gate plan's own precedent (pin thresholds BEFORE
looking at outcomes). Both halves below are **free** — recorded frames already exist
(`runs/probe_*/world/*.png` for the sweep games, `runs/brain_cn_gate/world/*.png` for a Pokémon-family
dialog recording) and no paid LLM call is needed for either.

### Gate 1 — text-region detector (piece a): recall/precision on a scored fixture

**Fixture (to build, free, offline):** hand-label text-bearing boxes on **~30 frames** drawn from
**3 of the 6 already-recorded sweep games** (pick the 3 with the clearest distinct render styles —
e.g. Minish Cap dialog boxes, Mortal Kombat Advance's HUD/menu text, SMA2's overworld text popups —
plus the DBZ or Naruto set as a held-out 4th if time allows) — labels are bounding boxes around
actual on-screen glyph rows, drawn by a human from the PNGs already sitting under `runs/probe_*/world/`.
Include a handful of **distractor frames** (pure gameplay/scenery, no text) so false-positive rate is
measured, mirroring `eval/fixtures/static_objects_pokeball`'s recall+precision+distractor-phantom
pattern (the referential-grounding gate's own template, `reports/2026-07-03-referential-grounding-
design.md` §4).

**Pinned bar (PASS/FAIL, decided now, before running the detector):**
- **recall ≥ 0.85** (of hand-labeled text boxes, the detector's candidate list overlaps ≥ 0.3 IoU with)
- **precision ≥ 0.70** (of the detector's candidate boxes, this fraction actually overlap a real text box)
- **0 phantom boxes on distractor (no-text) frames** — a miss must fall back to "no candidate", never
  invent one (same fail-safe rule as the referential-grounding gate).

**FAIL means:** the row-edge-density detector doesn't generalize across these 3+ games' render styles —
kill it cheap, and fall back to the brain tiling `read_region` blind (still workable per MiniWoB's live
validation, just costlier) rather than lifting a game-specific heuristic to `core/`.

### Gate 2 — within-run glyph cache (piece b): fraction-free after N confirmations

**Fixture:** a Pokémon Red dialog recording already on disk covers this — `runs/brain_cn_gate/world/`
(136 frames, Cave Noire, region-tool live) or, better, a fresh **free, offline** capture: replay an
existing Pokémon Red dialog sequence (`games/pokemon_red/textbox.py`'s own calibration frames under
`runs/dialog/` already exist and are exactly this shape — repeating Gen-1 dialog text across many
frames). Simulate "brain confirmation" for the gate WITHOUT any paid call: treat `gen1_font.json`
(already-calibrated, ground-truth glyph→char mapping) as a stand-in oracle for what a brain's
`read_region` would have reported on first sight of each distinct glyph shape — this is legitimate
because the point of THIS specific gate is to measure the **cache's hit-rate mechanics** (how quickly do
recurring glyphs stop needing a fresh read), not to re-litigate whether a brain CAN read pixels (the HUD
gate already answered that).

**Procedure:** replay frames in order; for each glyph cell encountered, if its key has been "confirmed"
before (by the simulated first-read), serve free from cache; else "confirm" it now (charge one simulated
read) and cache it. Track, over the whole sequence: `frac_free = free_lookups / total_glyph_occurrences`
after the first **N=5** distinct dialog frames' worth of confirmations.

**Pinned bar (PASS/FAIL, decided now):**
- **frac_free ≥ 0.80** measured over the frames AFTER the first 5 confirming frames (i.e., once the
  common-glyph vocabulary — letters, punctuation, the ▼ arrow — has been seen once, at least 80% of all
  further glyph occurrences must be servable from cache, given Gen-1 text reuses a small fixed alphabet
  repeatedly — this is what "touch-once-recognise-everywhere" would need to actually pay off).
- **0 silent mismatches**: any cache hit that would have decoded differently than
  `gen1_font.json`'s ground truth for that exact bitmap is a correctness bug in the keying (not the
  concept) and fails the gate outright, regardless of frac_free.

**FAIL means:** either the hashing/keying doesn't recognize recurring glyphs reliably (a keying bug,
fixable) or the fixed-alphabet-reuse assumption is wrong for this game (unlikely, given `textbox.py`
already proves the SAME hashing scheme recognizes the SAME character deterministically across frames —
this gate mostly re-validates that under the "within-run, no pre-seeded table" framing, and should be
expected to pass given the underlying mechanism is unchanged).

**Both gates are prerequisites, not sufficient alone:** Gate 1 passing says "we know where to look."
Gate 2 passing says "once we've looked once, we don't have to look again." Neither gate runs a live paid
brain — that remains a separate, later paid run (analogous to the HUD gate's own Phase D), explicitly
NOT scoped into this design pass.

---

## 6. Build plan — smallest PRs

1. **PR-1 (free, offline): Gate 1 fixture + scorer.** `eval/fixtures/text_regions/` (hand-labeled boxes
   on ~30 frames from 3+ sweep games) + `eval/score_text_regions.py` (recall/precision/phantom-count vs
   the pinned bar). No production code yet — this is the measurement harness, run BEFORE building the
   detector, per the "pick the metric, hold the unit, let it fail" discipline.
2. **PR-2 (free, offline): the R0 text-region detector** (`core/text_regions.py` — row edge-density +
   connected-components, world-agnostic, no game import) scored against PR-1's fixture. If FAIL: stop,
   write up the negative result (mirrors the static-object-detector kill, PR #51/#52), do not lift
   further.
3. **PR-3 (free, offline): Gate 2 fixture + scorer.** `eval/score_glyph_cache.py` replaying the existing
   `runs/dialog/*` frames against `gen1_font.json` as the simulated-oracle, measuring frac_free per the
   pinned bar.
4. **PR-4 (free, offline): the R1 glyph cache** (`core/glyph_cache.py` — generalizes
   `TileFunctionMap.fingerprint` to a caller-supplied cell size + `FontTable`-style lookup, no Pokémon
   import) scored against PR-3's fixture.
5. **PR-5 (only if both gates PASS, and only then): wire `read_region` availability + the detector hint
   into `world_mcp.py` for the sweep's GBA worlds** (extend `_REGION_TOOL_WORLDS` or an equivalent), and
   ONE small paid run re-auditing a previously `stuck_dialog` sweep game (e.g. Minish Cap) with the
   detector+cache available, scored by verdict-improvement (stuck_dialog → progress) — the live proof,
   analogous to the HUD gate's Phase D. This is explicitly OUT OF SCOPE for this design doc to build; it
   is the next rung this doc unlocks.

---

## 7. Anti-drift table

| Drift | Guard |
|---|---|
| **Hand-code a per-game font** (repeat `textbox.py`'s offline/human-calibrated pattern for a NEW game) | STOP — that is the exact anti-pattern this doc generalizes away from. The cache (b) must accept brain-confirmed reads at runtime, any game, never a human-typed ground-truth table checked into the repo per world. |
| **Build the R2/R3 model before measuring (a)+(b) fail** | Both gates in §5 are free and must be run FIRST. Climbing to a trained OCR model without a measured (b) failure is "perfecting the engine before testing the riskiest assumption" (ADR-002's own named tripwire). |
| **ROM font extraction without sign-off** | Flagged in §3(c) as requiring David's explicit OK. Do not build it under this doc's authority; if a future builder is tempted (it IS the fastest path for GB-family worlds), that is a separate conversation, not a default. |
| **Persist the glyph cache across runs** | Learning-boundary HARD LAW — per-run only, blank every run, exactly like `TileFunctionMap`. A cache surviving to the next run is silent cross-run learning, forbidden regardless of how well-grounded it is within one run. |
| **A cache that never demotes a stale entry** | §4(b)'s slot-2 grounding story requires mismatch-triggered invalidation (majority-vote outvoting, per `TileFunctionMap.observe`). A cache that trusts its first read forever, even after a proven mismatch, breaks the honesty contract — treat this as load-bearing, not an edge case to skip. |
| **Treat Gate 1's hand-labeled fixture as reusable across all future sweep games without re-checking** | 3 games is a sample, not a proof of universal generalization — a 4th/5th game with a very different render style (photoreal 3D text, proportional fonts) should re-run Gate 1, not assume the pinned bar transfers for free (ADR-002 §10's re-tiers-for-3D caveat). |
| **Conflate (a) [routing] with (b) [recognition] as one primitive** | They are separately gated on purpose — a detector that finds text boxes says nothing about whether the brain (or a cache) can read them, and vice versa. Keep the 7-slot contracts and gates distinct; don't merge them into one "OCR primitive" claim. |

---

## Recommendation (restated)

Build **(a) a cheap R0 text-region detector** (routing/foveation, cuts wasted `read_region` guesses) **+
(b) a within-run, brain-confirmed glyph cache** (R1, generalizes the already-proven `TileFunctionMap`
hashing mechanism from tile-function to glyph-identity, making recurring text free after one brain read).
Do **not** build the ROM-font path without David's sign-off, and do **not** climb to a trained OCR model
before both free gates below are measured on real recorded frames.

## The pinned gate, verbatim

> **Gate 1 (text-region detector):** on ≥30 hand-labeled frames drawn from ≥3 of the 6 already-recorded
> GBA sweep games (`runs/probe_*/world/`) plus distractor no-text frames — **PASS** requires recall ≥
> 0.85 AND precision ≥ 0.70 AND 0 phantom boxes on distractor frames. **FAIL** kills the detector cheap;
> the brain falls back to tiled `read_region` guessing.
>
> **Gate 2 (glyph cache):** on a Pokémon Red dialog frame sequence (`runs/dialog/*`, `gen1_font.json` as
> simulated brain-confirmation oracle) — **PASS** requires fraction-of-glyph-occurrences servable free
> from cache ≥ 0.80 (measured after the first 5 confirming frames) AND 0 silent mismatches between a
> cached lookup and the ground-truth glyph it was keyed from. **FAIL** on either condition kills or
> revises the keying scheme before any live/paid validation.
>
> Both gates are free/offline, run on data already on disk, and must be measured (not asserted) before
> any paid brain run or any `world_mcp.py` wiring change.

---

_See also: `reports/north-eye-perception-constitution.md` (the 7-slot contract + Realizer Ladder),
`reports/_archive/2026-06-25-adr-002-ontology-discovery.md` (§3 sensorimotor floor, §9 gate,
§11 anti-drift — this doc's format template), `reports/2026-07-03-adr002-gate-plan.md` (the HUD gate's
scoring-harness precedent + its measured cost story), `reports/2026-07-03-referential-grounding-design.md`
(the naming/anchoring layer this primitive feeds), `games/pokemon_red/textbox.py` +
`eval/calibrate_font.py` (the existing per-game R1 precedent, generalized here), `core/tilemap.py`
(`TileFunctionMap` — the exact hashing/keying mechanism reused for glyphs)._
