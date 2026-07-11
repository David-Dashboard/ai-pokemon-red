# Glyph R1 (cache-driven text-region detection) — gate verdict (2026-07-11)

_Status: **KILL**, banked. One scoring attempt against the pinned gate
(`reports/2026-07-03-glyph-r1-cache-driven-detection.md` section 4b) — per that doc's own attempt
cap, this counts as attempt 1 of 2; no re-run, no tuning to pass._

Built in the dedicated worktree `ai-pokemon-red-glyphr1` (branch `feat/glyph-r1-build`), per the design
doc's pinned requirements verbatim: `core/text_regions_r1.py` (the R1 detector + the section-4.0
snap-to-grid mitigation), `eval/score_glyph_r1.py` (the warmup-replay harness + gate scorer),
`eval/fixtures/text_regions/warmup_labels.json` (the bounded hand-labeling prep bill, section 4a).
`core/glyph_cache.py`, `core/blob.py`, `eval/score_text_regions.py` (`_iou`/`_load_fixture`), and
`eval/score_glyph_cache.py` (`N_WARMUP_CONFIRMING_FRAMES`/`_MIN_REAL_CELLS`) are reused unmodified, as
pinned.

## Pre-check 0 (already resolved in the design doc) — implemented, not re-measured

The design doc's own section 4.0 pre-check (31% of live `read_region` crops mod-8-aligned, FAIL vs
the 80% bar) was already resolved and mitigated before this build started: `core/text_regions_r1.py`'s
`confirm_region`/`snap_to_grid` slice every confirm-time crop from the FULL FRAME at tile-grid
boundaries, never from the caller's own (possibly off-grid) pixel origin. Applied uniformly, including
to the warmup harness's own hand-drawn (also non-grid-guaranteed) bboxes. Regression-tested in
`tests/test_text_regions_r1.py` (`test_confirm_region_snaps_an_off_grid_rect_before_slicing`) and
`tests/test_score_glyph_r1.py` (`test_warm_cache_from_labels_confirms_via_snap_to_grid_not_raw_crop`).

## Warmup prep bill (section 4a) — measured, with one deviation from the design doc's illustrative table

`eval/fixtures/text_regions/warmup_labels.json`: up to 5 hand-labeled text-bbox warmup frames per
qualifying game, drawn directly from each game's own `runs/probe_*/world/` recording (main-checkout
path — `runs/` is gitignored and not present in this worktree), MD5-excluded against
`eval/fixtures/text_regions/labels.json`'s 31 labeled frames per the pinned split rule.

**Qualification (measured):**

| Game | Labeled target-bearing frames | Warmup candidates (MD5-exclusion mechanical) | Qualifies? |
|---|---|---|---|
| Mortal Kombat Advance | 6 (≥3 ✓) | **4** (< 5 ✗) | **NO** — excluded |
| Dragon Ball Z: Legacy of Goku I & II | 4 (≥3 ✓) | 30 (≥5 ✓) | YES |
| Final Fantasy VI Advance | 3 (≥3 ✓) | 15 (≥5 ✓) | YES |
| Legend of Zelda: Minish Cap | 4 (≥3 ✓) | 28 (≥5 ✓) | YES |
| Naruto: Ninja Council 2 | 2 (< 3 ✗) | 17 | **NO** — excluded (design doc predicted this) |
| Super Mario Advance 2 | 7 (≥3 ✓) | 24 (≥5 ✓) | YES |

**Deviation, flagged honestly:** the design doc's section-4a table estimated Mortal Kombat Advance at
7 warmup candidates (naive `14 total − 7 labeled` count). The real MD5-mechanical count, applying the
pinned rule ("EXCLUDING every frame byte-identical to a labeled fixture frame") literally, is **4**:
two groups of intra-probe duplicate frames (`frame_000003/4/5` and `frame_000007/8/9`, byte-identical
within each group) each collapse to a single exclusion once one member's hash matches a labeled
frame's hash, removing more frames than a flat count-subtraction predicts. Mortal Kombat Advance
therefore fails the ≥5-warmup-candidate floor and is excluded — a real, measured outcome, not an
oversight (receipts: `eval/fixtures/text_regions/warmup_labels.json`'s `excluded` block).

4 games qualify: DBZ, FFVI, Zelda, SMA2.

## Gate run — verbatim scorer output

```
$ uv run --frozen python -m eval.score_glyph_r1 --probe-root <main-checkout>/runs -v

=== Dragon Ball Z: Legacy of Goku I & II ===
  warm-cache: 5/5 confirming frames (WARM), 989 distinct glyph shapes confirmed from 5 warmup frames replayed
  recall:    0.154  (2/13 targets)
  precision: 0.250  (2/8 candidates)
  phantom_count (distractor frames): 0
  verdict: KILL

=== Final Fantasy VI Advance ===
  warm-cache: 5/5 confirming frames (WARM), 859 distinct glyph shapes confirmed from 5 warmup frames replayed
  recall:    0.125  (1/8 targets)
  precision: 0.333  (1/3 candidates)
  phantom_count (distractor frames): 0
  verdict: KILL

=== Legend of Zelda: Minish Cap ===
  warm-cache: 5/5 confirming frames (WARM), 955 distinct glyph shapes confirmed from 5 warmup frames replayed
  recall:    0.286  (4/14 targets)
  precision: 0.222  (4/18 candidates)
  phantom_count (distractor frames): 1
  verdict: KILL

=== Super Mario Advance 2 ===
  warm-cache: 4/5 confirming frames (NOT WARM -- measured, reported, not silently skipped), 191 distinct glyph shapes confirmed from 5 warmup frames replayed
  recall:    0.545  (6/11 targets)
  precision: 0.353  (6/17 candidates)
  phantom_count (distractor frames): 0
  verdict: KILL

=== POOLED (all qualifying games) ===
  recall:    0.283  (13/46 targets)
  precision: 0.283  (13/46 candidates)
  phantom_count: 1
  NOTE: at least one game's cache did not reach 5 confirming warmup frames -- its per-game numbers
  above are measured on a cache warmed with FEWER than the pinned warmup, reported honestly, not
  treated as a clean same-condition measurement.

R1 GATE (pooled): KILL (PASS>=(0.85,0.9,0 phantoms); KILL<=(0.27,0.49))
```

## Banked verdict: KILL

Pooled **precision 0.283 ≤ 0.49** (R0's own failed precision) — a clean kill by the pinned rule, on
its own terms, regardless of recall. Pooled recall (0.283) sits just above the 0.27 recall-kill floor,
so precision is the deciding criterion. All 4 qualifying games individually verdict KILL; none reach
inconclusive, so **this is attempt 1 of 2 with a clean result — no second attempt is warranted or
permitted by the stricter-only amendment rule** (a kill is not "missed the bar," it's the floor).

SMA2's cache did not reach the pinned 5-confirming-frame warmup (4/5) — flagged, not silently
absorbed into the pooled number as if fully warm. Even so it is the best-performing game (recall 0.545,
precision 0.353) and still misses the pass bar by a wide margin; a fully-warm SMA2 cache would not
plausibly flip the pooled verdict (it already contributes the *strongest* per-game numbers of the four).

## Mechanical diagnosis: why precision died (not asserted, read from the numbers)

1. **Vocabulary size exploded far beyond Gate 2's Gen-1 precedent.** Gate 2 (Gen-1, crisp binary font)
   confirmed **46** distinct glyph shapes total and passed at 96.9% free / 0 mismatches. Here, 5 warmup
   frames on a SINGLE GBA game confirmed **191–989** distinct glyph-cell fingerprints — roughly
   4×–21× Gen-1's entire alphabet, from the same "first 5 confirming frames" budget. GBA fonts render
   anti-aliased (sub-pixel blending), so the same LETTER at different x-phase/kerning offsets hashes to
   materially different fingerprints; Gen-1's blocky 1-bit font does not have this problem, which is
   exactly why Gate 2 passed on it. R1's fixed-vocabulary-reuse premise (design doc section 2c's
   collision estimate assumes "roughly uncorrelated content" over a modest confirmed-key set) is
   measurably weaker once the confirmed-key count is in the hundreds instead of tens.
2. **The observed phantom (`zelda_scenery_002.png`, a pure-art distractor, 1 phantom candidate) is the
   same textured-backdrop collision mode that killed R0** — resurfacing under R1's Hamming≤4 tolerant
   match once ~955 confirmed keys are in play, despite R1's matching rule being provably grounded
   (bitwise/near-bitwise identity to a brain-confirmed glyph) rather than a texture heuristic. The
   design doc's own section-2c caveat named this risk explicitly ("textured/structured backdrops... can
   correlate more than the [collision] bound assumes") — measured here, not merely feared.
3. **Recall misses split into two distinct failure modes, not one:** (a) genuine out-of-vocabulary
   misses (`dbz_webfoot_020.png`: 0 candidates — a publisher-logo wordmark whose glyph shapes never
   appeared in the 5 warmup frames, the expected, honestly-scoped R1 limitation per design doc section
   5) vs (b) candidates that fired but missed their IoU target (`dbz_selectgame_024.png`: 3 candidates,
   0 matched a real target) — consistent with (1)/(2): the detector is finding SOMETHING via the
   swollen tolerant-match vocabulary, just not reliably the right something.

**Reading this against the design doc's own framing:** R1 was built exactly as designed and its
mechanism (grid-aligned scan, from_cache hit rule, ≥3-run denoise, snap-to-grid) is unit-tested and
behaves as specified (`tests/test_text_regions_r1.py`). The KILL is a property of the **GBA
anti-aliased-font / small-warmup-sample combination**, not an implementation bug — the same detector
logic, run against Gate 2's Gen-1 fixture (crisp font, larger effectively-shared vocabulary across many
more frames), is the configuration that already validated the underlying cache mechanism.

## What this does NOT settle (explicitly, so it isn't silently assumed)

- Whether R1 would fare better on Gen-1 Pokémon dialog (crisp font, the one game class Gate 2 already
  validated) is not measured here — Gate 1's fixture has zero labeled Pokémon Red frames (design doc
  section 4a, unchanged), so R1 cannot be scored on that game class without new labeling, out of scope
  for this attempt.
- Whether a MUCH longer warmup (beyond the pinned 5-confirming-frame definition) would shrink the
  swollen vocabulary's collision rate is not measured — the pinned warmup definition was reused
  unmodified specifically to avoid this becoming a tunable free parameter (design doc section 4a's own
  reasoning for reusing Gate 2's warmup rule verbatim).

## Per the design doc's own kill clause

> **KILL** if recall <= 0.27 or precision <= 0.49 (R0's own failed numbers) on the same split — R1 has
> not improved on what it was built to fix; fall back to brain-driven `read_region` alone (no detector).

Banked as written: **do not lift `core/text_regions_r1.py` into a wired/production path.** The
fallback the design doc names — brain-driven `read_region`, unassisted, as the sole text-finding
mechanism (design doc section 3, option 2) — stands as-is; nothing in this build changes that
recommendation. `core/glyph_cache.py` (Gate 2, PASS) is unaffected and remains reusable on its own.

## vNext candidates (NOT decided — David's call, listed per gate-methodology)

1. Score R1 against a crisp-font game (Gen-1 Pokémon) once Gate-1-style labels exist for it — tests
   whether the anti-aliasing diagnosis (above) is the real driver, isolating it from the "small warmup
   sample" variable.
2. A stricter Hamming tolerance (lower than the reused `_DEFAULT_TOL=4`) specifically for R1's
   from_cache lookup, trading recall for precision — a stricter-only amendment per the design doc's
   amendment rule, would need its own dated doc and counts against the 2-attempt cap.
3. Accept the design doc's own fallback and do not pursue an R1.1 — brain-driven `read_region` alone,
   unassisted, per section 3 option 2.

---
_See also: `reports/2026-07-03-glyph-r1-cache-driven-detection.md` (the pinned design + gate this
verdict scores against), `reports/2026-07-05-glyph-read-design.md` (the R0 doc this amends),
`core/text_regions_r1.py`, `eval/score_glyph_r1.py`, `eval/fixtures/text_regions/warmup_labels.json`._
