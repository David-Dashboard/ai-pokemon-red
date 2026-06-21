# Perception architecture — decision record (2026-06-21)

**Status: DESIGN CONVERGED + EMPIRICALLY GROUNDED. Build not yet wired in (only off-by-default scaffolding).**
This records a long design session: a vision-model probe → a proposed configurable-vision perception module →
three adversarial reviews → empirical embedding experiments → a converged, evidence-based architecture.
Companion raw-benchmark doc: `reports/2026-06-21-vision-model-probe.md` (read it for the per-model numbers).

---

## TL;DR (the decision)

- **World model = an ONLINE, behavior-labelled `tile → function` map, built BY THE AGENT AS IT PLAYS**
  (walk a tile → walkable; bump → blocked; probe+A → interactable). Behaviour = ground truth. (David's call:
  "the agent can build it as it plays" — no offline RAM pre-generation.)
- **Key the map by a CHEAP tile FINGERPRINT (perceptual hash / template), NOT CLIP** — because the only thing
  embedding retrieval reliably does on this game is recognise *near-identical recurring tiles*, which a hash does
  deterministically, faster, no torch/GPU, and CI-testable. This already gives the speedup David wants:
  **touch each distinct tile-type once, recognise it everywhere it recurs — no walking every cell.**
- **CLIP/MobileCLIP embedding is reserved for NOVELTY DETECTION** (a tile far from everything seen → "unknown,
  go explore it"). That is the one thing the embedding does well. It must NOT predict the *function* of a novel
  tile (proven ≈chance).
- **Vision (CLIP grid / Florence caption) is ADVISORY only, never authoritative for walkability**; passed up to
  System 2 with provenance, never committed/vote-fused into the behavioural map. (Fusion review, below.)
- **OCR: template decoder DEFAULT, RapidOCR FALLBACK** (gen1 dialog/battle = the common text, where the template
  is free + ~100%; RapidOCR earns its keep on other fonts/menus/games).
- **No frozen-contract change.** Everything lives in `PerceptMemory` (per-run, world-side) + a sparse advisory
  channel in the extensible `spatial_memory`.

This is the same conclusion reached independently by (a) David's "minimal-fixed version" (CLIP = perception
support, not the world model; experience = truth), (b) the adversarial reviews, and (c) the empirical data.

---

## The decisive empirical result (why CLIP is NOT the world model)

Test (`eval/probe_walkability_learn.py`): build a behaviour-labelled CLIP-embedding store from recorded runs
(faced tile = walkable if a move succeeded, blocked if it failed — ground truth from the oracle's
action+outcome, NO live RAM), then k-NN retrieve walkability for held-out tiles. Data: `fix2 + fix4 +
novelty_val`, 1663 labelled faced-tiles.

- **Temporal split: 97.7% accuracy** (maj baseline 73.9%) — BUT nearest-store cosine **min 0.97 / mean 1.00**
  ⇒ this is **near-exact tile RECURRENCE (memorisation of a finite tileset), not generalisation.**
- **Leave-one-MAP-out (the real generalisation test):**
  - hold **map 40 (lab): 26.9%** — *worse than the 74.8% majority baseline* (518 walkable lab-floor tiles
    retrieved as "blocked"); hold map 0: 77.1% (maj 72.6%); map 38: 89.2%; map 37: 94.1%.
  - **Stratified by novelty (nearest-store cosine):** `>0.97` → **~100%** (every map); `0.90–0.97` → 15–94%
    (wild); `<0.90` (genuinely novel appearance) → **0–71% ≈ chance.**

**Conclusion:** the CLIP image embedding captures **appearance, not function** — held-out lab floor is closer
to some house/Pallet *wall* than to house/Pallet *floor*. So embedding retrieval **recognises recurring tiles
near-perfectly but does NOT generalise walkability to new tile appearances.** (Same root cause as the earlier
text-label walkability failure where MobileCLIP tagged all floor "blocked", and the per-cell "ball" FP.)
⇒ Use a cheap fingerprint for the recurrence win; use the embedding's *distance* only as a novelty signal.

**⚠ Data limitation (David flagged it, confirmed):** every run we have covers only ~5 early-game maps
(40 lab / 0+37 Pallet / 38 house / 39 rival-house; Viridian = 3 frames). No cities/routes/caves/forests, no
save-states, `red_play.mp4` is empty. The cross-map test already exposes the generalisation failure *within*
early game, so the direction is settled; broader data (other tilesets) would only quantify the distinct-tile
"vocabulary" size — and the chosen design (agent builds the map online as it plays) doesn't need pre-generated
data anyway.

---

## The adversarial reviews (what survived)

Three multi-agent adversarial reviews (6 lenses each, findings verified):

1. **Design review** (the original "configurable vision models" proposal): 22/24 real. It over-anchored on the
   one-time Oak/Pokéball event; David corrected the framing (the 90% is nav/NPCs/battle) + added a **speed
   preference** ("don't walk into every wall to learn a room"), which reframes cheap-first as *time-to-advance*
   and favours vision-seeded layout. The CLIP-grid's job flipped from object-finding (its weakness) to
   layout/function classification.

2. **Fusion review** ("how to fuse many overlapping signals"): 23/24 real, 17 high — all 6 lenses converged:
   - **Do NOT weighted-vote overlapping signals** ("more = more robust" is FALSE — vision signals are
     *correlated failures*, same domain gap → same errors; summing inflates shared bias).
   - **Split by RELIABILITY CLASS, not cheapness:** System 1 COMMITS only behaviourally-grounded,
     self-correcting signals (occupancy-from-movement, pose, detect_mode, motion ROIs, decoded text);
     **vision is advisory, surfaced UP with provenance, never committed.**
   - **Typed-evidence PRECEDENCE, not weights:** behavioural-confirmed (walked/bumped/probed) = veto/overrides;
     temporal (motion) = "something animates here"; vision = low-fixed-weight prior **only in its validated
     context, never its softmax** (flat ~13% = noise). **Walkability stays movement-mono-source.**
   - Keep the committed perceiver **deterministic + model-free**; quarantine non-deterministic/network vision in
     the existing escalation tier (`core/vision_escalation.py` — already advisory/cached/capped/failure-safe).
     No contract change (advisory rides `spatial_memory`; state in `PerceptMemory`; calibrate vision reliability
     OFFLINE vs the RAM oracle → constant tables, never live).

3. **Embedding-retrieval review:** launched but did not return (session limit). Superseded by the empirical
   result above, which is stronger evidence than a review.

(Deep-research literature sweep: failed on the session web-limit — retry after reset to ground in prior art:
self-supervised traversability / BADGR / WayFAST, Bayesian occupancy fusion, Cradle/Voyager skill libraries,
SwiftSage dual-process, CLIP embedding-arithmetic pitfalls.)

---

## What's BUILT (off-by-default scaffolding; NOT wired into the agent)

- `vision_service.py` — Flask sidecar (py3.12 env), lazy `/caption` (Florence-2), `/grid` (MobileCLIP2-S0),
  `/ocr` (RapidOCR), `/health`. Smoke-tested cross-env. Currently stopped.
- `core/vision_client.py` — world-agnostic HTTP client (requests-only, graceful degrade). The decoupled,
  north-star-aligned host (mirrors aria/litellm) — keeps the world-repo torch-free.
- Eval/probe scripts (all under `eval/`): `vision_probe.py`, `clip_compare.py`, `probe_grid.py`,
  `probe_recall.py`, `probe_walkability.py`, `probe_embed_retrieval.py`, `probe_walkability_learn.py` (the
  decisive one), `ocr_compare.py`, `captioner_compare.py`, `caption_only_compare.py`, `clip_quick.py`.
- Isolated venvs (gitignored): `.venv-probe` (py3.14, clip/owlv2/yolo via tf5), `.venv-probe4` (py3.12 +
  transformers 4.49 + open_clip + ultralytics + rapidocr + flask — Florence/Moondream need tf<5).
- **NOT built:** any wiring into the perceiver/brain/agent; the fingerprint world-model; the online
  behaviour-labelling; the novelty gate. The original "Phases 2–5" plan is **superseded** by this decision.

---

## Open decision (deferred)

**Learning-boundary / store persistence.** The online behaviour-labelled map is within-run by default
(law-compliant: rebuilt each run, wiped between). A map that **persists across runs** = across-run learning,
currently forbidden by the HARD LAW (the roadmap anticipates revisiting this at It4). The fingerprint→function
table is small and could be a shipped asset (offline-built, like `gen1_font.json`) — that would be the
law-compliant "permanent" form — but defer until the online within-run version is proven.

---

## NEXT (build, evidence-based)

1. **Tile fingerprint + online behaviour-labelled `tile→function` map** in the perceiver (world-side,
   `PerceptMemory`): generalise the existing occupancy map from *position-keyed* to *appearance-keyed* so a
   tile-type learned once is recognised wherever it recurs (the "don't walk every cell" speedup). Cheap hash,
   deterministic, CI-testable. **This is the highest-value, lowest-risk first build.**
2. **Novelty gate** from embedding distance (or even hash-miss): unseen tile-type → "unknown, explore"/frontier.
3. Keep OCR = template-default + RapidOCR-fallback; vision (CLIP/Florence) advisory via the escalation tier only.
4. (Later) retry the literature deep-research; reconsider persistence (It4 question).

---

## OPEN QUESTIONS & TEST PLAN (what remains — nothing below is tested yet)

We answered *"does embedding retrieval recognise/generalise walkability"* (yes-recurrence / no-generalisation).
We have NOT designed or tested *how the agent USES any of this*, nor the composition ideas. These are open.

### A. David's explicit questions
1. **How will the agent USE the spatial embeddings / the tile→function map?** (the decision layer — undesigned.)
   Candidate uses, to compare by *steps-saved* and *wakes-saved*: (i) **route over the appearance-keyed map**
   (BFS treats predicted-blocked tiles as walls → the agent avoids walking into known-by-appearance walls without
   re-bumping them = the speedup); (ii) **inject a compact symbolic summary into the LLM context at wakes**
   ("ahead: walkable path; NPC 2N; unexplored E"); (iii) **novelty-driven exploration target** (head toward
   far-from-store/unknown tiles). Open: which usage actually reduces steps/wakes, and does (i) ever route the
   agent INTO a real wall (must keep the behavioural veto on contact).
2. **Scene embedding (whole screen) vs tile embedding — how used together?** Hypothesis: the **tile** embedding =
   local function; the **scene** embedding = context/mode (indoor vs outdoor, room-type, battle) that could
   DISAMBIGUATE a tile whose function depends on context (same appearance, different function by area). Open test:
   does conditioning tile-retrieval on the scene-cluster improve function accuracy — especially in the unreliable
   cosine `0.90–0.97` band? Cheap, offline (we have both embeddings).
3. **Linear-combination experimentation** (`tile + scene`, `tile + text("walkable")`, contextual vectors). Prior
   evidence says CLIP vector arithmetic is unreliable for precise composition — but it's CHEAP to settle offline:
   measure whether any combination beats tile-alone on the leave-map-out function-retrieval (or improves the
   novelty gate). Low expectation; worth a definitive negative/positive.
4. **LLM → text → spatial embedding** (VLM/LLM describes a tile/scene → embed the TEXT → retrieve by text-embedding).
   **This is the most promising UNTESTED lever for the generalisation failure:** image-embeddings encode
   *appearance* (so lab-floor ≠ house-floor), but a *description* carries *function* ("walkable grass" ≈ "walkable
   path" in TEXT space), so text-embeddings of same-function tiles may cluster ACROSS appearances — potentially
   rescuing the cross-tileset generalisation that image-embedding lost (26.9% lab). Risks: the VLM mislabels GB
   sprites (we measured this), and it costs an LLM call per tile/region. Test: caption each faced-tile (or its
   region) with Florence/Sonnet → text-embed → re-run the LEAVE-MAP-OUT retrieval; compare to the 26.9%/baseline.

### B. Other open questions surfaced this session
5. **Fingerprint vs CLIP head-to-head for recurrence** — we INFERRED a perceptual hash matches CLIP's exact-tile
   recognition (cosine ~1.0); verify it directly (and that it's cheaper/deterministic).
6. **Fingerprint robustness** — Gen-1 tiles ANIMATE (water, flowers), have PALETTE swaps, sub-tile SCROLL, and
   map-edge cases where the player isn't at (4,4). Does the appearance-key stay stable across animation frames of
   the *same* tile? (Testable offline on recorded frames; may need tolerance/normalisation.)
7. **Novelty-threshold calibration** — where to set the "unknown → explore" gate (we saw cos `>0.97` reliable,
   `<0.90` ≈ chance, `0.90–0.97` wild); does one threshold transfer across tilesets?
8. **End-to-end navigation SPEEDUP** (the actual goal) — measure steps-to-traverse a new area WITH vs WITHOUT the
   appearance-keyed map (replay or live). Retrieval accuracy ≠ speedup; this is the metric that matters.
9. **Beyond walkable** — does fingerprinting extend to *interactable* (probe+A), *NPC* (moving/animating), *exit/
   warp* (special)? NPCs especially don't fingerprint as static tiles.
10. **Live cost/latency** of the stack per step (even the cheap parts) — unmeasured live.
11. **Cross-GAME transfer** (north star, It2): behaviour=truth generalises; the fingerprint is per-tileset — does
    the approach drop into a 2nd game cleanly?
12. **Store persistence** (within-run vs across-run = the learning-boundary / It4 decision) — deferred.
13. **OCR fallback trigger** — the exact condition RapidOCR engages (template '?'-heavy) — untested live.
14. **Prior-art grounding** (deep-research, deferred on web limit) — the self-supervised-traversability literature
    (BADGR / WayFAST) is the closest analog and may already answer #4/#8; could shift the design.

### C. Prioritised test plan (cheapest-first; most are FREE + offline, reuse the probe harness)
1. **LLM-caption → text-embedding generalisation test (Q4)** — highest value: it could rescue cross-appearance
   generalisation that image-embedding failed. Re-run leave-map-out with text-embeddings of VLM captions.
2. **Linear-combination test (Q3)** + **scene-conditioning test (Q2)** — both on the same leave-map-out split.
3. **Fingerprint vs CLIP + robustness (Q5, Q6)** — animation/palette/scroll on recorded frames.
4. **Navigation speedup + "how the agent uses it" (Q8, Q1)** — needs the map built first (task #7), then a
   replay/live A/B (with vs without the appearance-keyed map).
5. **Retry the literature deep-research (Q14)** once the web limit resets — may inform #1/#4/#8 before we build.
