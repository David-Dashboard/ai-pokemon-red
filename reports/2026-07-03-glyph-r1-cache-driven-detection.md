# Glyph R1 design: cache-driven text-region detection (2026-07-03)

_Status: **design + pre-registered gate only**. No code changes, no perceiver edits, no brain edits.
Amends `reports/2026-07-05-glyph-read-design.md` ("the R0 doc") after its Gate 1 measured FAIL
(0.27 recall / 0.49 precision / 5 phantom boxes on distractors vs the pinned 0.85/0.70/0 bar,
`eval/score_text_regions.py`). Gate 2 (the within-run glyph cache, `core/glyph_cache.py`) PASSED
(96.9% frac_free after warmup, 0 mismatches, per HANDOFF's 2026-07-05 entry) and is reused here
unmodified — R1 is a new detector (piece a), not a new cache._

_Amended 2026-07-03, same day, per the adversarial review posted on PR #88 (all findings accepted):
the fixture plan is re-pinned against a measured per-game frame inventory (§4a — the prior revision's
"free... no new fixture labeling" claim was wrong and is retracted); a grid-alignment pre-check was
added, measured, and FAILED, so a snap-to-grid mitigation is now pinned (§4.0); the "sparse probes
(15-19 tool calls)" claim is corrected to measured frame counts (14-41); and an attempt cap on
inconclusive results is pinned (§4b)._

---

## 1. Why R0 died and what R1 inverts

R0 (`core/text_regions.py`) tried to find text **bottom-up**: per-row edge-density (a Sobel-free
gradient-popcount sum over horizontal strips), thresholded, merged into bands via
`core.blob.connected_components`. Measured against `eval/fixtures/text_regions/` (31 hand-labeled
frames, 6 sweep games + distractors): **recall 0.27, precision 0.49, 5 phantom boxes**. The module's
own docstring already names the failure mode: "glyph texture is a ROW-level phenomenon... not
reliably a per-cell one," and textured backdrops (title-screen art, HUD chrome, sprite detail) light
up the same edge-density signal as real text — edge density alone can't tell "small packed glyphs"
from "any small packed pixels."

**R1 inverts the test.** Instead of asking "does this region look texturally like text" (a
bottom-up guess that any textured surface can spoof), ask **"does this region contain tiles that
are BITWISE IDENTICAL to glyphs the brain has already confirmed this run"** (a top-down match
against ground truth, not a texture heuristic). A cluster of cells whose fingerprints hit the
confirmed glyph cache isn't textured-like-text — it verifiably **is** text, because the cache entry
was grounded by a brain read (`core/glyph_cache.py`'s `confirm()`, mirroring the HUD-gate's proven
`read_region` mechanism). This can't be spoofed by decorative texture the same way edge density can:
a title-screen logo's pixels don't happen to bitwise-match a confirmed "A" glyph's dHash unless it
actually contains that glyph.

The trade R1 makes explicit: **R1 detects nothing new** — it can only ever re-find glyphs the cache
already knows. It is not a replacement for R0's job (finding **novel** text regions cold) but a
narrower, cheaper, more precise job: **re-finding recurring text once the vocabulary is warm.** This
doc's §3 (cold-start) is the honest accounting of what that leaves unsolved.

---

## 2. Scan design

### 2a. Granularity: grid-aligned, not sliding window

**Pinned: 8x8 tile-grid-aligned scan, cell size matching the cache's confirmed cell size.** Not a
sliding window.

Justification: `games/pokemon_red/textbox.py`'s `cells()` (the existing, working Gen-1 decoder) slices
glyph cells at fixed grid offsets — `CELL=8`, `X0=8`, `LINES=((112,120),(128,136))` — because the
emulator renders text tile-aligned to the console's native 8x8 tile grid; this is a hardware property
of tile-based 2D rendering (GB/GBA background layers are literally composed of 8x8 tiles), not a
Pokémon-specific assumption. `core.tilemap.TileFunctionMap.fingerprint` (which `GlyphCache.fingerprint`
reuses verbatim, `core/glyph_cache.py:61-65`) already assumes and pools to a fixed grid for the same
reason. A grid-aligned scan is therefore not a shortcut that loses generality — it matches how the
renderer actually produces the pixels the cache was confirmed against.

**Conditional pin (amended per PR #88 review finding 3):** the above holds only if the CACHE-POPULATION
crops are themselves grid-aligned, and measured on the one live `read_region` transcript on disk they
are NOT (only 31% of live crop origins are mod-8 aligned in both axes — §4.0's pre-check, measured
2026-07-03). The grid-aligned scan is therefore pinned TOGETHER WITH §4.0's snap-to-grid confirm-time
mitigation, not standalone: a scanner aligned to tile boundaries can only match fingerprints that were
also hashed at tile boundaries.

A sliding window (scan every pixel offset, not just tile boundaries) would catch text that renders
off-grid — proportional fonts, sub-tile-scrolled text during a scroll animation, or a game that
doesn't tile-align its font at all. None of the 6 sweep games or Gen-1 Pokémon are known to do this;
it is flagged, not built:

**R2 fallback (not this doc):** if a future game's text is measurably off-grid (a Gate-1-style
fixture where grid-aligned R1 recall stays low specifically on frames from that game, while cache
coverage is otherwise adequate), climb to a sliding window at some stride < 8px. This is strictly
more expensive (a WxH scan instead of a (W/8)x(H/8) one, ~64x more candidate positions before any
matching) and is not attempted here per the same "don't climb before a measured failure" rule R0's
doc already pinned.

### 2b. Matching rule

For each grid cell in the frame: compute `GlyphCache.fingerprint(cell)` (reused verbatim, no new
hashing code) and call `cache.lookup(...)` — actually, `cache.from_cache(...)`, since detection only
needs the boolean "is this a known glyph," not which character. A cell is a **hit** iff
`cache.from_cache(fingerprint) is True` (a confirmed, uncontested cache entry — contested/tied entries
already abstain via `lookup()`'s existing tie logic, so R1 inherits that honesty discipline for free).

### 2c. Cluster-size threshold (false-positive control)

**Pinned: a candidate text region requires >= 3 hit cells in an unbroken run along one row** — a
similar but deliberately STRICTER denoise threshold than R0's actual `_DEFAULT_MIN_ROWS = 2` default
(`core/text_regions.py:46`; the prior revision said "exactly mirroring," which overstated the parallel),
applied to horizontal cell runs instead of row bands (single-cell hits are exactly the hash-collision failure mode this threshold exists to kill —
see collision estimate below). Adjacent hit-rows merge via `core.blob.connected_components` (reused
unchanged from R0) into a bbox, same as R0's own band-merge step. A lone hit cell, or a run of 1-2,
is dropped — not enough to distinguish "real recurring glyph" from "a coincidental single-tile hash
collision."

**Collision-risk estimate, so 3 isn't a made-up number:** `GlyphCache.fingerprint` returns a 132-bit
key split as (4-bit intensity bucket, 128-bit gradient) with matching tolerance `_INTEN_TOL=1` bucket
and gradient Hamming <= `_DEFAULT_TOL=4` (`core/glyph_cache.py:41,43`; `core/tilemap.py:48-51`). Two
*unrelated* natural-image 8x8 tiles landing within Hamming-4 of a specific confirmed key's 128-bit
gradient by chance is a small but non-zero probability (loosely, sum of binomial(128,k) for k<=4 over
2^128 — a generous back-of-envelope upper bound after accounting for the intensity gate is well under
1e-4 per tile-pair, though textured/structured backdrops are not uniformly random and can correlate
more than this bound assumes, which is exactly why R0 died on them). A single stray hit at that rate
across a 20x18 or 30x20 grid (see §2d) is a plausible false accept once in a while; **three in an
unbroken row** at even a pessimistic 1e-2 correlated-content collision rate is ~1e-6 per frame — the
threshold buys several orders of magnitude of margin cheaply. This is an estimate, not a measured
number; the fixture in §4 measures the real rate.

One precedent note that makes the tolerance defensible rather than novel (added per PR #88 review
finding 4): Gate 2's 96.9%/0-mismatch result already exercised this exact tolerant-match code path —
`eval/score_glyph_cache.py` calls `cache.lookup()`, which routes through `_exact_or_near`'s
Hamming<=4 + intensity-bucket matching (`core/glyph_cache.py:110-121`), not a stricter exact-only
path — so the 0-mismatch precedent transfers to R1's matching rule as-is.

### 2d. Cost

`GlyphCache.fingerprint` is the exact same call `core/tilemap.py`'s `TileFunctionMap` already makes
per-tile during normal S1 perception (average-pool to 8x8, two `np.roll` compares, a `packbits`) — no
new hashing primitive, just more calls per frame. Frame sizes actually in the fixtures:
- GBA sweep frames (`eval/fixtures/text_regions/`, confirmed 240x160 px): 30x20 = **600 tiles/frame**.
- GB-family frames (160x144 px, Pokémon Red / Cave Noire native resolution): 20x18 = **360
  tiles/frame**.

`glyph_cache.py`'s own docstring frames its hashing cost as already-amortized (`TileFunctionMap`
already scans the full tilemap for walkability every frame in the existing pipeline); 360-600
fingerprint computations plus a dict lookup each is the same order of magnitude as work already
happening every frame for tile-function classification, not a new cost tier. No measured per-frame
timing exists yet — flagged as a cheap, free thing to measure in the same pass as §4's fixture replay
(wall-clock the detector over the fixture set), not asserted here.

---

## 3. Cold-start: where do the first confirmations come from?

**Honest problem statement:** R1 detects nothing until the cache holds at least one confirmed glyph,
and the cache is blank at run start (learning-boundary law, `core/glyph_cache.py`'s own docstring).
R1 alone cannot bootstrap a run — it needs a first-confirmation source that isn't R1 itself.

Three candidates, evaluated honestly:

1. **Seed from the game's standard dialog-window position.** Pokémon Gen-1's dialog box renders at a
   fixed, known screen region (`textbox.py`'s `LINES=((112,120),(128,136))`, `X0=8`) whenever a
   textbox is open — this is a per-game geometric constant, exactly the thing the R0/R1 design line
   has been trying to avoid hard-coding (`reports/2026-07-05-glyph-read-design.md` anti-drift table:
   "hand-code a per-game font"/geometry is the named anti-pattern). Reusing it purely as a **cold-start
   seed location for the brain's FIRST `read_region` call** (not as a permanent per-game constant baked
   into R1 itself) is a narrower ask than hand-coding a font, but it is still a per-game fact, and nothing
   in the current codebase supplies an equivalent "standard dialog position" for the 6 GBA sweep games —
   each would need its own seed geometry discovered first.
2. **Brain-driven `read_region` requests, unprompted.** The brain already spends ~39% of tool calls on
   `read_region` in the one live gate run where the tool was available
   (R0 doc §2, `runs/brain_cn_gate/transcript.jsonl`) — i.e., it already looks around without being told
   where. If the brain reads a region on its own initiative (curiosity, or because a `stuck_dialog`
   verdict pattern like the Zelda probe's makes it try), that read is a legitimate confirmation source
   with zero new design surface: nothing to build, it already happens. The honest caveat: this is
   exactly the "guess-and-check... workable but wasteful" cost R0's doc used to justify building a
   detector in the first place (§3(a)) — relying on it alone for cold-start doesn't remove that cost,
   it just accepts paying it once, at the start of a run, before R1 has anything to serve free.
3. **Dialog-box heuristics (a lightweight, generic "this looks like a UI panel" cue).** `games/pokemon_
   red/perceiver.py:220-227` already has exactly this for Gen-1: a region check for "clear UI panel"
   (battle/dialog needs bottom>0.3 near-white fraction, a menu needs right>0.35) that is NOT the killed
   R0 edge-density detector — it is a coarser, different, already-existing per-game cue. Generalizing an
   equivalent (near-white or high-contrast rectangular panel heuristic) across the 6 sweep games is
   unmeasured and could hit the same textured-backdrop problem that killed R0 if not scoped carefully.

**Pin: (2), brain-driven `read_region` requests, is the cold-start source.** It requires zero new code
(the mechanism already exists and is already measured at 39% of calls in the one live run that has
it), it does not reintroduce a per-game geometric constant into `core/`, and it does not resurrect R0's
specific failure mode (texture-triggered phantom regions). One requirement rides on this pin: when a
brain-driven read feeds `GlyphCache.confirm()`, the cell slicing must snap to the tile grid per §4.0's
measured pre-check — the brain's own crops are majority-OFF-grid (69% of live calls), so unsnapped
confirms would be systematically invisible to the grid-aligned scan. The honest cost it accepts: **R1 provides
zero value for however many turns it takes the brain to confirm its first few glyphs unprompted** —
this is a real latency/cost tax on cold-start, not a solved problem, and is exactly what §4's warm-cache
precondition below exists to fence off from the gate (the gate does NOT claim R1 helps cold-start; it
only claims R1 helps once warm). (1) — seeding from a known dialog position — is flagged as a possible
per-game accelerant a future builder could add on top, analogous to R0 doc §3(c)'s ROM-font path: not
built here, would need per-game geometry sign-off the same way, and is NOT required for R1's gate below
to be measured.

---

## 4. Pre-registered gate

Reuses the exact Gate 1 fixture R0 failed on (`eval/fixtures/text_regions/`, `eval/score_text_regions.py`)
for comparability, plus Gate 2's exact cache-warmup procedure (`eval/score_glyph_cache.py`'s
confirming-frame mechanism) to define "warm." **"Free" throughout this section means NO PAID RUNS
ONLY** — the gate does require bounded prep work (labeling + one harness script), itemized in §4a;
the prior revision's "no new fixture labeling" claim was wrong and is retracted (PR #88 review
finding 1).

### 4.0 Pre-check (numbered, own pass/fail — must resolve before the gate runs): are live-confirmed crops tile-grid-aligned?

`GlyphCache.confirm()` does not enforce grid alignment (it hashes whatever crop the caller hands it),
and the live population path (brain-driven `read_region`, §3) uses brain-chosen pixel coordinates. If
live-confirmed crops are off-grid, the grid-aligned scan (§2a) hashes cells at tile boundaries that do
not match the off-grid confirmed fingerprints — a 1-5px spatial shift changes the average-pooled dHash
in a way the Hamming<=4 tolerance was never designed to absorb (it absorbs rendering/anti-aliasing
noise, not phase shift). This was PR #88 review finding 3 (sev-1) and it is real.

**Pass/fail rule (pinned):** if >= 80% of live `read_region` crop origins are mod-8 aligned in BOTH
axes, proceed grid-aligned unmodified; below that, a mitigation must be pinned before the gate runs.

**Measured (2026-07-03, free — `runs/brain_cn_gate/transcript.jsonl`, the only live `read_region`
transcript on disk, 39 calls):**
- `x0` mod-8 aligned: 39/39 (100%)
- `y0` mod-8 aligned: 12/39 (31%) — observed `y0 % 8` values: {0: 12, 4: 7, 5: 17, 6: 3}
- both axes aligned: 12/39 (**31%**)
- The single most common crop, `(x0,y0,x1,y1) = (0,125,64,138)`, issued 17 times, is off-grid by 5px
  in y (it targets the HP line inside the dialog box, not the tile grid).

**Result: FAIL** (31% << 80%) — **mitigation required and hereby pinned: snap-to-grid quantization at
confirm time.** Cells fed to `confirm()` must be sliced from the FULL FRAME at tile-grid boundaries,
taking the tile cells that overlap the brain's crop rect (expand the rect outward to the enclosing
mod-8 boundaries in frame coordinates). The brain still sees its own unmodified crop — only the
cache-population slicing snaps. This is a pinned requirement on any implementation PR, decided now.
The alternative mitigation — per-glyph phase-offset scanning (hash all 64 sub-tile phases per cell) —
is rejected for cost (~64x §2d's per-frame work) unless snap-to-grid measurably fails.

Bound stated honestly: 39 calls, one game (Cave Noire, GB), one run — a small sample, but it is the
entire live evidence on disk, and the >= 80% bar cannot be met by this sample regardless of what future
runs show, so the mitigation is pinned rather than deferred to more measurement.

### 4a. Warm-cache precondition (must hold before R1's own numbers mean anything)

**Pinned: "warm" = the `GlyphCache` state after the first 5 confirming frames of the game-under-test's
OWN warmup sequence**, using `eval/score_glyph_cache.py`'s exact confirming-frame procedure
(`N_WARMUP_CONFIRMING_FRAMES = 5`, `_MIN_REAL_CELLS = 4` — the same numbers, the same meaning, the same
code path that produced Gate 2's validated 96.9%-free state on Gen-1). The warmup FRAMES come from the
same game being scored (per-game inventory below); the warmup PROCEDURE and its parameters are Gate 2's,
unmodified.

**Why reuse Gate 2's warmup and not a fresh one:** Gate 2 already measured exactly how much
confirmation is needed before the cache pays off (5 frames, 96.9% free after) — inventing a second,
different warmup definition for R1 would be an unpinned, tunable knob (pick however much warmup makes
R1's numbers look best). Reusing the existing, already-gated warmup state removes that degree of
freedom.

**Known mismatch to flag honestly:** Gate 2's warmup fixture is Gen-1 Pokémon dialog frames
(`runs/dialog/*`); Gate 1's fixture is the 6 GBA sweep games (`eval/fixtures/text_regions/`) — DIFFERENT
games, different fonts, different glyph shapes. A cache warmed on Gen-1's alphabet will **not** contain
GBA sweep games' glyph fingerprints at all (different font bitmaps hash to different, unrelated keys).
This means R1 scored this way, on Gate 1's actual fixture, is expected to show near-zero recall — not
because R1 is broken, but because **this specific cross-game combination has no warm vocabulary to
match against.** This is not a loophole; it is the honest reason §4b's gate is scoped to a
same-game warm/measure pair, not "reuse Gate 2's literal cache object against Gate 1's literal frames."

**Concrete fixture plan (re-pinned per PR #88 review findings 1+2 — the prior revision's "sparse
probes (15-19 tool calls each)" claim was wrong; counts below were measured directly on disk,
2026-07-03):**

| Game | Frame source (`runs/`) | Frames on disk | Labeled Gate-1 frames (targets + distractors) | Warmup candidates (probe minus labeled) |
|---|---|---|---|---|
| Mortal Kombat Advance | `probe_0247_-_Mortal_Kombat_Advance__U__Venom/world/` | 14 | 6 + 1 | 7 |
| DBZ Legacy of Goku | `probe_2288_-_2_in_1_-_Dragon_Ball_Z_-_The_Legacy_of_Goku_I___II__U/world/` | 41 | 4 + 0 | 37 |
| FFVI Advance | `probe_2689_-_Final_Fantasy_VI_Advance__U__Xenophobia/world/` | 28 | 3 + 1 | 24 |
| Zelda Minish Cap | `probe_Legend_of_Zelda__The_-_The_Minish_Cap__U/world/` | 35 | 4 + 1 | 30 |
| Naruto Ninja Council 2 | `probe_Naruto_-_Ninja_Council_2__U/world/` | 22 | 2 + 1 | 19 |
| SMA2 Super Mario World | `probe_Super_Mario_Advance_2_-_Super_Mario_World__U/world/` | 37 | 7 + 1 | 29 |
| Pokémon Red (Gen-1) | `dialog/` | 272 | **0** | n/a — cannot be scored |

All 31 labeled fixture PNGs in `eval/fixtures/text_regions/` are **byte-identical copies** of
probe-dir frames (verified by MD5 over both sets, 31/31 matched) — warmup and scoring frames come from
the same recordings, so the split rule below is mechanically checkable, not honor-system.

**Pinned split + qualification rule:**
- **Warmup set per game** = that game's probe-dir frames EXCLUDING every frame byte-identical to a
  labeled fixture frame (never warm on a frame that will be scored — the exclusion is enforced by the
  same MD5 check used to build the table).
- **A game QUALIFIES iff** it has **>= 3 labeled target-bearing frames** AND **>= 5 text-bearing
  warmup frames** (5 = Gate 2's own `N_WARMUP_CONFIRMING_FRAMES`, same number, same meaning). By
  labeled-frame count, **5 of 6 GBA games qualify on the first condition** (MK 6, DBZ 4, FFVI 3,
  Zelda 4, SMA2 7); **Naruto (2) does not and is excluded now.** Whether each qualifying game's warmup
  candidates contain >= 5 TEXT-BEARING frames is only knowable during the labeling pass below — a game
  that comes up short **drops out at measurement time and is reported as excluded**, never silently
  skipped.
- **The gate runs on ALL qualifying games**; per-game and pooled recall/precision are both reported.
- **Pokémon Red cannot be scored** (zero labeled Gate-1 frames); `runs/dialog/*` stays what it already
  is — Gate 2's warmup fixture — and is not an R1 scoring input.

**Prep work required — the full bill, stated plainly ("free" = no paid runs, NOT zero work):**
1. **Hand-label text bboxes on up to 5 text-bearing warmup frames per qualifying game** (<= 25 frames
   of new bbox labeling, same procedure as Gate 1's fixture). Needed because no `gen1_font.json`-style
   glyph->char oracle exists for any GBA game — the labeled warmup bboxes define WHICH cells receive
   simulated confirmation.
2. **Simulated confirmation for warmup:** every non-blank 8x8 grid cell inside a labeled warmup bbox is
   `confirm()`'d with a single shared placeholder reading. Placeholders are legitimate because this
   gate tests DETECTION (`from_cache` boolean) only, not character identity — the identity half stays
   validated by Gate 2 on Gen-1. One shared placeholder (not per-hash unique strings) so
   `_exact_or_near`'s Hamming-near aggregation cannot manufacture spurious ties that would make
   `lookup()` abstain.
3. **One small harness extension:** a warmup-replay entry point that takes a probe dir + warmup labels
   and returns a warmed `GlyphCache`, then reuses `eval/score_text_regions.py`'s IoU scoring unchanged.

That is the whole bill: ~25 frames of bbox labeling + one harness script + zero paid calls. The gate
is NOT runnable today as-is — it is runnable after that bounded prep, and this doc stops claiming
otherwise.

### 4b. The gate itself

**Pinned bar (decided now, before running R1):**
- **recall >= 0.85** and **precision >= 0.90** on text-region detection — same recall bar as R0's
  gate, precision bar raised from R0's 0.70 to **0.90** because R1's whole design premise is that
  matching against ground-truth-confirmed glyphs should be far more precise than a texture heuristic;
  a detector that still can't clear 0.90 precision after switching from "looks textured" to "bitwise
  matches a confirmed glyph" has not actually fixed R0's failure mode.
- **0 phantom boxes on distractor (no-text) frames** — same fail-safe rule as R0's gate, unchanged.
- Measured ONLY on frames from a game whose cache was warmed on that same game's own frames per §4a's
  concrete fixture plan (qualification rule + MD5-exclusion split). A non-qualifying game is excluded
  from this gate's scoring, not force-scored with a foreign-game cache (which would just re-measure "zero
  vocabulary overlap," not R1's actual detection quality).

**Kill criterion (pinned, mirrors R0's own 0.27 result as the reference for "this is a real kill, not
noise"):** if measured recall or precision falls **at or below R0's own failed numbers (recall <= 0.27
or precision <= 0.49)** on the same-game warm/held-out split, R1 has not improved on the thing it was
built to fix — kill it cheap, same as R0, and do not lift a warm-cache-dependent detector into
`core/` at all; fall back to brain-driven `read_region` (§3, option 2) as the sole text-finding
mechanism, unassisted. A result strictly between R0's failed numbers and the 0.85/0.90 pass bar (e.g.
recall 0.5, precision 0.75) is neither a clean pass nor a clean kill — flag as "measured but
inconclusive," do not round it up to a pass, and do not merge it as if it cleared the bar.

**Stricter-only amendment rule (pinned):** any future revision of this gate's numbers (recall/precision
bar, cluster-size threshold, warm-cache definition) may only move the bar UP (stricter) or narrow the
scope (e.g., restrict to fewer games), never down, without a fresh, separately-dated design doc
explaining why the original bar was wrong on its own terms (not just "the measured result missed it").
This mirrors the R0 doc's own "thresholds are NOT tuned post-hoc to pass" discipline
(`eval/score_text_regions.py`'s docstring) applied to future edits of this doc, not just the original
authoring.

**Attempt cap (pinned, added per PR #88 review finding 5 — the stricter-only rule alone left
scope-narrowing as unbounded shots on goal):** at most **2 total scoring attempts** of the same
underlying detector under the pinned configuration — the original run, plus at most one re-run after a
stricter-only amendment. Scope-narrowing amendments COUNT as attempts (the cap is on scoring attempts,
not on docs). **A second inconclusive result pauses the lane and escalates to David with the measured
numbers — no third attempt, no silent rescoping.** No standing repo convention existed for this
(reviewer checked); this doc sets one for this lane.

**Cost class of the gate:** no paid brain call anywhere — warmup is a labeled-bbox replay against probe
frames on disk, scoring reuses `GlyphCache`, `core.blob.connected_components`, and
`eval/score_text_regions.py`'s IoU-matching machinery unchanged, and the scoring labels are Gate 1's
verbatim (R1 does not get a new, possibly friendlier scoring fixture). The bounded prep bill (warmup
bbox labeling + one harness script) is itemized in §4a and is a prerequisite, not already done.

---

## 5. What R1 does NOT solve (restated, so it isn't silently assumed)

- **Cold-start detection is still zero-value until the cache is warm** (§3) — R1 is a warm-cache
  amplifier, not a cold-start solution. The brain-driven `read_region` cost R0 was built to reduce is
  still paid, in full, for however long cold-start takes.
- **Novel glyph shapes anywhere in a frame are invisible to R1 by construction** — a new character
  never confirmed this run (a proper noun's first letter, a symbol never seen before) will never match
  any cache entry, so R1 will never flag the region containing ONLY novel glyphs, even if it's real
  text. R1 only re-finds recurring text; it does not replace a general "is there text here" signal for
  first-sight content. Mixed regions (some known glyphs + some novel ones) are still findable via
  known-glyph hits, per §2c's cluster rule — but a region that is entirely first-sight text is a miss,
  not a phantom, so it doesn't break Gate 1's phantom rule, but it does cap R1's achievable recall on
  any frame with fresh-only text.
- **Cross-game cache reuse is explicitly not proposed** — §4a's warm/held-out pairing is same-game
  only; nothing here claims a cache warmed on one game helps detection on a different game (different
  fonts hash to unrelated fingerprints, as the mismatch in §4a shows directly).

---

## 6. Open questions (not answered by this doc)

- ~~Does any GBA sweep game have enough same-game frames for a warm/held-out split?~~ **Measured
  2026-07-03 (§4a's inventory): yes by raw count** — 14-41 frames per probe dir, 7-37 warmup
  candidates after excluding labeled frames. The RESIDUAL unknown: do >= 5 of each qualifying game's
  warmup candidates actually BEAR TEXT (only knowable during the §4a labeling pass — a game short of 5
  drops out at measurement time, reported).
- Whether the placeholder-confirmation warmup (§4a prep item 2) faithfully proxies live brain-driven
  confirms is untested — §4.0's snap-to-grid mitigation closes the known geometric divergence (live
  crops are majority-off-grid), but a live warm cache could still differ from the simulated one in
  which glyphs get confirmed first. Not resolvable offline; flagged for the eventual paid live run
  (out of scope here, same as the R0 doc's Phase-D analogue).
- Real per-frame wall-clock cost of the 360-600 fingerprint calls (§2d) is estimated by analogy to
  `TileFunctionMap`'s existing amortized cost, not measured directly — cheap to measure in the same
  pass as the gate replay, not done here.
- Whether cold-start option (1) (seed from a known dialog-window position, as a per-game accelerant
  layered on top of option (2)) is worth building for any specific sweep game is deferred, same as R0
  doc's ROM-font path — needs a separate per-game sign-off conversation, not decided here.

---

## 7. Anti-drift table

| Drift | Guard |
|---|---|
| **Treat R1 as a cold-start solution** | It is not (§3, §5). It only re-finds text once glyphs are already confirmed. Do not wire it as the sole text-finding mechanism without a cold-start source (brain-driven reads, pinned §3). |
| **Score R1 against a foreign-game cache and call it a measurement** | §4a's mismatch case — a cache warmed on one game's font has zero vocabulary overlap with another game's glyphs. Only same-game warm/held-out splits count toward the gate. |
| **Round an inconclusive result up to PASS** | §4b's kill criterion pins R0's own 0.27/0.49 as the "still broken" floor and 0.85/0.90 as the bar; anything between is inconclusive, not a pass, and must be reported as such. |
| **Lower the bar post-hoc if the measured result just misses it** | The stricter-only amendment rule (§4b) — any relaxation needs a fresh, separately-dated, separately-justified doc, not a same-day retune. |
| **Bake a per-game dialog-window position into `core/text_regions.py` or a new R1 module** | Cold-start option (1) is flagged, not pinned, precisely because it's a per-game geometric constant — the same anti-pattern R0's doc already fenced off. If ever built, it lives as a per-game accelerant outside `core/`, with sign-off, not as a default. |
| **Assume the 3-cell cluster threshold generalizes without checking** | §2c's collision estimate is a back-of-envelope bound assuming roughly uncorrelated content; textured/structured backdrops (the thing that killed R0) can correlate more than the bound assumes. The fixture replay in §4 measures the real phantom rate — if phantoms reappear even with the cluster threshold, raise it (stricter-only) before concluding R1 is clean. |
| **Feed off-grid live crops into `confirm()` unsnapped** | §4.0's pre-check measured 69% of live crops off-grid — unsnapped confirms are systematically invisible to the grid-aligned scan (a silent recall killer that would surface as an unexplained gate FAIL). Snap-to-grid at confirm time is a pinned implementation requirement, not optional. |
| **Warm the cache on a frame that will be scored** | The MD5 byte-identity exclusion (§4a) is mechanical — warming on a scored frame trivially guarantees detection on it and voids the measurement. Any harness that skips the exclusion check is scoring theater. |
| **Iterate scope-narrowing amendments until a subset passes** | The attempt cap (§4b): 2 total scoring attempts, narrowing counts, second inconclusive = pause + escalate to David. Unbounded shots on goal through permitted "narrowing" was the reviewer-named loophole; it is closed by count, not by intent. |

---

## The pinned gate, verbatim

> **Pre-check 0 (resolved 2026-07-03):** live `read_region` crops measured 31% tile-aligned
> (`runs/brain_cn_gate/transcript.jsonl`, 39 calls) vs the pinned >= 80% bar — FAIL. Mitigation pinned:
> confirm-time snap-to-grid slicing (cells fed to `confirm()` sliced from the full frame at mod-8
> boundaries overlapping the brain's crop). A requirement on any implementation PR; the gate below
> presumes it.
>
> **R1 warm-cache precondition:** the `GlyphCache` used for scoring a game must be warmed on that SAME
> game's own probe-dir frames, EXCLUDING every frame byte-identical (MD5) to a labeled fixture frame,
> using Gate 2's exact confirming-frame procedure (`N_WARMUP_CONFIRMING_FRAMES=5`, `_MIN_REAL_CELLS=4`)
> with labeled-warmup-bbox simulated confirmations (single shared placeholder reading). A game
> qualifies iff >= 3 labeled target-bearing frames AND >= 5 text-bearing warmup frames; by current
> inventory MK/DBZ/FFVI/Zelda/SMA2 qualify on labels, Naruto is excluded (2), and Pokémon Red cannot be
> scored (0 labeled frames). The gate runs on ALL qualifying games; per-game + pooled numbers reported.
>
> **Prep prerequisite (the gate is NOT runnable today):** <= 25 frames of warmup text-bbox labeling
> (up to 5 per qualifying game) + one warmup-replay harness script. "Free" means no paid runs only.
>
> **PASS** requires recall >= 0.85 AND precision >= 0.90 AND 0 phantom boxes on distractor frames,
> measured only on qualifying same-game warm/held-out pairs, scoring labels reused verbatim from
> `eval/fixtures/text_regions/labels.json`.
>
> **KILL** if recall <= 0.27 or precision <= 0.49 (R0's own failed numbers) on the same split — R1 has
> not improved on what it was built to fix; fall back to brain-driven `read_region` alone (no detector).
>
> Anything strictly between KILL and PASS is **inconclusive**, reported as such, never rounded to a
> pass and never merged as if it cleared the bar.
>
> **Amendment rule + attempt cap:** any future change to these numbers may only move stricter or
> narrower, requires a fresh dated design doc, and may never be a same-day post-hoc retune to convert a
> miss into a pass. At most 2 total scoring attempts of the same underlying detector
> (scope-narrowing amendments count); a second inconclusive pauses the lane and escalates to David with
> the numbers — no third attempt.
>
> No paid brain call anywhere in this gate: warmup replays probe frames on disk, scoring replays
> `eval/fixtures/text_regions/`.

---

_See also: `reports/2026-07-05-glyph-read-design.md` (the R0 doc this amends — its §3(a)/(b) candidate
list, §5 Gate 1/2 definitions, §7 anti-drift table this doc's §7 extends), `core/text_regions.py` (the
killed R0 detector — read for the exact failure-mode docstring), `core/glyph_cache.py` (the validated
Gate-2-passing cache this doc's R1 detector queries, unmodified), `core/tilemap.py`
(`TileFunctionMap.fingerprint` — the hash R1's collision estimate in §2c is grounded in),
`eval/score_text_regions.py` / `eval/score_glyph_cache.py` (the exact scoring harnesses reused here,
unmodified), `games/pokemon_red/textbox.py` (the Gen-1 tile-aligned geometry `LINES`/`CELL`/`X0` that
justifies §2a's grid-aligned pin and supplies §3's flagged-not-built cold-start seed option),
`games/pokemon_red/perceiver.py:220-227` (the existing, separate, non-R0 "UI panel" heuristic referenced
in §3 option 3).
