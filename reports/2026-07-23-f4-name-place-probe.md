# F4 — the name→place probe (A2 keystone, $0 offline) — 2026-07-23

_Status: **free feasibility probe, banked**. Changes no repo code. Tests A2's riskiest assumption
(capability-map §A2, lines 45-60): can a name coined within ONE run resolve to a goto target after
≥5 transitions, scored offline (oracle map-id vs coined address), WITHOUT per-world ontology or
oracle map-ids on the wire? Probe design + scripts under `reports/probes/2026-07-23-f4/`._

## 0. The claim under test
A2 says the missing thing is **addressability, not reasoning**: System-1 owns a stable structure,
System-2 references it by name. Resolution (name→place→goto) is pure plumbing over the perceiver's
place-graph (referential-grounding doc §c) **iff the coined address is a faithful, stable proxy for
the true place**. So the whole probe reduces to one question: **is the pixels-only place-id a stable
address across ≥5 transitions?** Falsifier fires if binding needs hand-authored ontology OR oracle
map-ids on the wire.

## 1. The substrate already exists (verified)
`games/pokemon_red/perceiver.py:OverworldPerceiver` already coins internal `place` ids from
pixels-only warps (fade + best-shift residual), keyed door `edges`, and emits the id as
`pose.area` — a legitimate on-the-wire address (NOT the oracle map-id, which goes to `oracle.jsonl`
only, `perception_plugin.py:_log_oracle`). ExploreBrain already routes over it (`_cross_place`). So
nothing new is needed to TEST resolution — only to measure address stability.

## 2. Probe design ($0, no LLM, no-leak)
Existing `brain_red_starter` run is 3 transitions and LINEAR (no return) → can't test resolution.
So generate one: headless `PokemonRedPlugin` (the live fade-aware path) + the free `ExploreBrain`
autopilot, from `runs/red_start.state`, 4000 steps. A driver-side anti-absorption burst forces the
explorer back out of Oak's lab so the trajectory REVISITS places. `map_id` (0xD35E) is read for
SCORING ONLY; the perceiver sees pixels only. Score (`f4_score.py`): oracle map-id (truth) vs coined
`area` — split/merge, V-measure, and per-return **resolution** (name = settled area at first visit;
does the settled area on each later return still equal it?). Scripts + method are reproducible.

## 3. Results (2 seeds, 4000 steps, 11 transitions each)
| metric | seed 3 | seed 7 | reading |
|---|---|---|---|
| homogeneity (no MERGE) | 0.982 | 0.990 | a coined address almost never conflates two places — **clean address space** |
| completeness (no SPLIT) | 0.356 | 0.432 | the same true place is re-minted as MANY addresses — **massive over-split** |
| resolution, all returns | 2/11 | 2/11 | only immediate returns land on the coined address |
| resolution, returns ≥5 transitions | 1/7 | 0/7 | **name→place resolution fails after ≥5 transitions** |

- Map 40 (Oak's lab) alone is minted as **12 distinct place-ids** in one run; maps 0 and 37 as 6 each.
- **Every failure is a fail-safe SPLIT** (perceiver mints a fresh/unknown place), **ZERO confident-WRONG**
  (it never resolves "home" to a different named place).
- The split is **intrinsic, not my artifact**: 16 re-mints/1k frames during smooth ExploreBrain
  navigation vs 1.7/1k during the random escape burst.
- Mechanism matches the perceiver's own documented anti-corruption design (`perceiver.py` ~:398): on
  any unattributed scene-change it drops pose to UNKNOWN and mints a **fresh** place rather than risk a
  wrong reuse — so door edge-reuse never fires on a real return, and the coined name is orphaned.

## 4. Verdict — **UNCERTAIN** (as-built NO-GO; but the A2 falsifier's two killers are NOT forced)
- **Definitive:** the CURRENT place-graph fails name→place resolution after ≥5 transitions (0-1/7).
  The keystone's riskiest assumption — that the coined address is stable — is **falsified as-built**.
- **But not the A2 falsifier:** neither killer is triggered. No per-world ontology was authored; no
  oracle map-id was needed on the wire; the failure is **fail-safe** and the address space is **clean
  (homogeneity ~0.98, near-zero merge)** — the perceiver over-splits, it never conflates. The single
  missing piece is a **bounded, pixels-only place RE-RECOGNITION primitive** (recognise "I have been
  in this exact place before" on return, so edge-reuse fires), not the two things A2 warned would make
  it un-cheap. That is a concrete engineering gap, not a wall.
- Therefore: **cheap addressability is NOT achieved today, and NOT shown impossible cheaply.** UNCERTAIN.

## 5. What flips it (the next free probe, de-risks P4)
Probe a **place-fingerprint / re-localization** primitive (perceptual hash of the settled arrival
frame + door-cell, à la `tilemap.fingerprint`, R0→R1): on each return does it re-bind to the coined
place-id? Re-score resolution@≥5 on THIS SAME trajectory (fixture already generated). **GO** if
completeness and resolution@≥5 jump with no per-world constants and 0 confident-WRONG; **NO-GO** if it
needs oracle map-ids or hand-tuned per-place templates to disambiguate returns. Do NOT open the ADR-002
general naming loop — this is place identity only. Update capability-map §B4 A2 row with this verdict.

## Sources / artifacts
- `reports/2026-07-05-northstar-capability-map.md` §A2 (the claim + falsifier); `2026-07-03-referential-grounding-design.md` §c (resolution = plumbing).
- `games/pokemon_red/perceiver.py` (place-graph: `places`/`edges`/re-anchor ~:290-420,:557-588); `core/perception_plugin.py` (fade watch, no-leak oracle).
- Probe scripts: `reports/probes/2026-07-23-f4/{f4_drive.py,f4_score.py}`. Trajectories are gitignored `runs/`-style data (regenerable, seeds 3/7).
