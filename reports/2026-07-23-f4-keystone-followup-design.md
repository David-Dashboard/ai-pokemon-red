# F4 keystone follow-up — designing the experiment that forces the A2 answer (2026-07-23)

_Status: **design only, $0**. No code, no paid run. Follows PR #135
(`reports/2026-07-23-f4-name-place-probe.md`, UNCERTAIN: as-built place-graph fails resolution@≥5
transitions, but neither A2 killer — per-world ontology, oracle map-id on the wire — was forced). This
doc designs the next probe so the answer is forced either way._

## 1. Diagnosis — why the graph over-splits

The place-graph has exactly **one** re-identification mechanism: `_transit`'s `edges` dict, keyed
`(src_place_id, exit_cell)` (`games/pokemon_red/perceiver.py:556-589`). It fires only on a clean fade
+ single commanded direction. Every OTHER way pose gets lost — a fade with no attributable direction
(battle/dialog entry-exit), a non-fade scene-cut (interior stairs, which don't fade per the F4
report), a mixed/ambiguous action — falls into the `was_unknown` recovery branch (`perceiver.py:
395-409`), which **unconditionally mints `next_place` at (0,0)**, never comparing the newly-settled
scene against any place already in `m["places"]`. That branch IS the over-split mechanism, and it's
deliberately blind (`perceiver.py`'s own comment: "re-anchor ONCE, deliberately ... rather than
guessing which known place/cell we're back at") — a correct anti-corruption choice given it had no
comparison signal to guess with. Oak's lab mints 12 place-ids because it round-trips through this
branch repeatedly (dialog/menu exits), never through `_transit`.

**So: not a graph-building bug, a missing primitive.** The graph has no notion of "have I seen this
exact scene before," only "did I arrive via a door I've already logged."

## 2. Candidate approaches, evaluated

- **Coarser addressing key** (cruder pixel signature, e.g. global tile histogram): risks re-opening
  MERGE, not just fixing SPLIT — GB tile art repeats constantly (the failure mode that KILL-CHEAP'd
  the static-object R0 detector, `HANDOFF.md:456`, 154 phantoms). Rejected as primary without a
  tolerant, thresholded match — which is candidate 3.
- **Node-merging by behavioural equivalence** (post-hoc: merge place-ids whose edge/traversal
  signatures coincide): sound as an *offline audit*, but as the *online* re-id step it needs too much
  accumulated behaviour to decide in time. Kept as a secondary check (§4), not the fix itself.
- **Landmark-anchored, content-based re-localization ("place fingerprint") — chosen.** Reuse
  `core/tilemap.py:TileFunctionMap.fingerprint` (perceptual dHash, already proven for **recurrence** —
  same room/tileset, later revisit, NOT cross-tileset generalization, per `perception-primitives`)
  applied to the **whole settled arrival frame**. Store one fingerprint per place at first stable
  visit; on recovery, compare against stored ones at the SAME fixed tolerance already used in
  `tilemap.py` — no per-place tuning. No/multi match → still mint new (fail-safe preserved).

## 3. The minimal addressing change

At settle time (via `_transit` or a fresh mint), compute `fingerprint(settled_frame)` into a new
`m["place_fp"][place_id]`. In `was_unknown` recovery (`perceiver.py:402-409`), BEFORE minting
`next_place`: fingerprint the current settled frame, compare to every stored `place_fp` at the
existing tolerance; exactly one match within tolerance → re-bind to that place (restore cursor/edges)
instead of minting; else mint new as today. Pixels only, one constant, no map_id at match time.

## 4. The $0 offline experiment (GO/NO-GO, forces the A2 answer)

1. Implement §3. Re-run `f4_drive.py` **unchanged** (seeds 3/7, 4000 steps, same anti-absorption burst
   — deterministic) through the patched perceiver.
2. Re-score with `f4_score.py` **unchanged** (still oracle map_id vs coined `area`, offline only).
3. Optionally cross-check with candidate 2 as an independent offline audit of the SAME re-bindings.

**GO** (keystone survives): resolution@≥5 rises materially (bar: combined ≥8/14 across both seeds,
today 1/14) AND completeness ≥0.7 (today 0.36-0.43) AND homogeneity stays ≥0.95 (no new MERGE) AND the
fingerprint crop + tolerance are IDENTICAL across both seeds/every place AND map_id is touched only by
the scorer, never inside the match step.

**NO-GO, killer forced** (A2 falsified for real): the GO bar needs a per-map/per-place tolerance or
template (a de-facto per-world ontology), OR the match needs map_id to break a near-miss tie, OR any
MERGE appears (a confident-wrong bound bought the completeness gain).

**NO-GO, null result** (sharper than F4's UNCERTAIN): resolution/completeness don't move even at a
generously loosened tolerance — content similarity within one tileset doesn't discriminate rooms. That
means the gap isn't engineering (as F4 §4 hoped) but that pixels-only place identity is genuinely
hard — closer to actually falsifying the keystone than "UNCERTAIN."

Any of the three outcomes converts UNCERTAIN into a banked verdict; update capability-map §A2 with
whichever fires.

## Sources
`reports/2026-07-23-f4-name-place-probe.md` (probe under follow-up) · `games/pokemon_red/perceiver.py:
287-459,556-589` (perceive loop, recovery branch, `_transit`) · `core/tilemap.py:80-109`
(`TileFunctionMap.fingerprint`) · `.claude/skills/perception-primitives/SKILL.md` (recurrence-proven,
not a cross-tileset oracle) · `HANDOFF.md:456` (static-object KILL CHEAP — why a coarser key alone is
rejected).
