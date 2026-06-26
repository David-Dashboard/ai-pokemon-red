# 2026-06-23 — Held-out verification: per-run camera classifier, hands-off zero-shot

Follow-on to the odometry-corpus work (PR #3). Two pieces: (1) the **per-RUN** camera-model classifier — the
cheap closer the per-FRAME centroid couldn't manage (a scroller's non-scroll-majority frames drown the
per-frame vote) — and (2) its zero-shot evaluation on the `dataset_split` **HELD-OUT** set (Crystalis / Zelda LA
/ Super Mario Land / F-1 Race), recorded **HANDS-OFF by the autonomous pipeline** (no human input — human-playing
the verification set would defeat the zero-shot test and risk leakage).

New: `eval/verify_heldout.py` (numpy+PIL, main env): per-run features `[scrollPrev, A4_locality, vshare]` from
the dev corpus → dev leave-one-UNIT-out → zero-shot classify each held-out game vs the dev centroids.

**TL;DR — the verification is thin BY CONSTRUCTION: only 1 of 4 held-out games was drivable hands-off, and that
one passed.** Crystalis (a never-tuned-on top-down RPG) classifies `follow_scroll` zero-shot by a clear margin.
The other three are driver-blocked (autonomous control can't drive a side-scroller / flip-screen intro / racer),
so they test the DRIVER, not the perceiver. Net: the per-run classifier generalizes where we can drive the game;
the bottleneck is autonomous control — which the hands-off discipline is exactly what exposed.

## Results

**DEV per-run leave-one-UNIT-out: 7/7 = 100%** (vs the per-FRAME centroid's 45% — per-run aggregation is the fix).
*Caveat: this is near-tautological — `[scrollPrev, A4, vshare]` were chosen precisely because they split these
classes, on these 7 units. The load-bearing generalization evidence is the OUT-OF-CORPUS held-out game, not 7/7.*

**HELD-OUT (autonomous, zero-shot, never tuned on).** Win metric = nearest dev class is the EXPECTED one by a
clear MARGIN (runner-up dist / nearest dist). Distance-FROM-corpus is high for *every* held-out game (they're new
GAMES) — so it is NOT a camera-model-novelty signal; the margin BETWEEN classes is what carries the verdict.

| game | true | pred | margin (over runner-up) | A4 | scrollPrev | verdict |
|---|---|---|--:|--:|--:|---|
| Crystalis | follow | **follow_scroll** | ×1.8 (over side) | 1.00 | 40% | **CONCLUSIVE ✓** |
| SML | side | scroll_side | ×1.0 (over fixed) | 0.07 | 0% | inconclusive — driver stalled |
| Zelda LA | flip-screen | fixed | ×8.9 (over follow) | 0.22 | 1% | ambiguous (fixed may be right) |
| F-1 Race | pseudo-3D | fixed | ×7.7 (over follow) | 0.10 | 0% | ambiguous — driver stalled |

## Conclusion

- **N=1 conclusive, and it passed.** Only Crystalis was drivable hands-off; it classifies `follow_scroll`
  zero-shot, nearest by a ×1.8 margin over side. That's the real out-of-corpus evidence the per-run classifier
  generalizes. (An earlier draft cited Crystalis's distance-from-corpus as "novelty ×2.1" — dropped: that number
  means "far from the 2-unit follow centroid," inevitable for a 3rd same-class game, and says nothing about
  camera-model novelty. The **margin** is the metric; novelty ≥1.8 keeps its PR #3 meaning — "a NEW camera model,"
  as in Doom — and does not apply to a correctly-classified known one.)
- **The other three are NOT perception failures — they test the DRIVER.** The harness separates **INCONCLUSIVE**
  (predicted a scroller but ~no motion → driver stalled) from **AMBIGUOUS** (predicted fixed + ~no motion →
  genuinely fixed OR stalled, can't tell hands-off). **SML** `pred=scroll_side` nominally matches truth but is
  refused — the run is degenerate (no motion, ×1.0 margin = right on the side/fixed boundary), not a win.
- **Zelda LA is the interesting AMBIGUOUS case:** flip-screen has no continuous scroll, so reading `fixed`
  (margin ×8.9) is arguably the *correct* camera answer — but hands-off we can't distinguish "correctly fixed"
  from "driver stalled in the intro," so it's not claimed (the low-motion gate would otherwise wrongly call a
  genuinely-fixed game inconclusive).
- **F-1 reading `fixed` is NOT a perception concern** — the car never accelerated (no throttle) → no road-scroll.
- **Methodology (the load-bearing bit):** the held-out set was recorded HANDS-OFF on purpose. That discipline is
  what surfaced the real bottleneck — autonomous **control** of non-top-down games, not camera-model
  **perception**. Hand-playing them would have "verified" the classifier on human-produced data and hidden it.

## Next

The gap is autonomous locomotion for side-scroll / racing / intro-gated games — i.e. a competent controller,
which is the agent itself (the project's end goal). Camera-model perception is verified-good where drivable, so
the generalizable ego-motion estimator can branch on it (fixed→none / 2D-scroll→`best_shift` / 3D→optical-flow)
for the games we can drive today, and the held-out set re-runs cleanly once autonomous control improves.
