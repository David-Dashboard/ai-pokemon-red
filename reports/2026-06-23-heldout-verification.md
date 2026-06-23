# 2026-06-23 — Held-out verification: per-run camera classifier, hands-off zero-shot

Follow-on to the odometry-corpus work (PR #3). Two pieces: (1) the **per-RUN** camera-model classifier — the
cheap closer the per-FRAME centroid couldn't manage (a scroller's non-scroll-majority frames drown the
per-frame vote) — and (2) its zero-shot evaluation on the `dataset_split` **HELD-OUT** set (Crystalis / Zelda LA
/ Super Mario Land / F-1 Race), recorded **HANDS-OFF by the autonomous pipeline** (no human input — human-playing
the verification set would defeat the zero-shot test and risk leakage).

New: `eval/verify_heldout.py` (numpy+PIL, main env): per-run features `[scrollPrev, A4_locality, vshare]` from
the dev corpus → dev leave-one-UNIT-out → zero-shot classify each held-out game vs the dev centroids.

## Results

**DEV per-run leave-one-UNIT-out: 7/7 = 100%** (vs the per-FRAME centroid's 45% — per-run aggregation is the fix).

**HELD-OUT (autonomous, zero-shot, never tuned on):**

| game | true | pred | novelty | A4 | scrollPrev | conclusive? |
|---|---|---|--:|--:|--:|---|
| Crystalis | follow | **follow_scroll ✓** | ×2.1 | 1.00 | 40% | **YES — clean win** |
| SML | side | scroll_side | ×6.1 | 0.07 | 0% | no — low-motion |
| Zelda LA | flip-screen | fixed | ×0.6 | 0.22 | 1% | no — low-motion |
| F-1 Race | pseudo-3D | fixed | ×0.7 | 0.10 | 0% | no — low-motion |

## Conclusion

- **The classifier GENERALIZES zero-shot where the autonomous pipeline produces locomotion.** Crystalis — a
  held-out, never-tuned-on top-down RPG — is correctly `follow_scroll` (and honestly flagged a new game, ×2.1).
  The per-run aggregation (7/7 in-corpus) holds out of corpus.
- **The other three folds are INCONCLUSIVE — they test the DRIVER, not the perceiver.** `--explore` can't drive a
  side-scroller (SML: run+jump), get past a flip-screen intro (Zelda), or accelerate a racer (F-1), so those
  recordings have ~no camera motion (`scrollPrev≈0`, `A4` low). The harness flags them `[LOW-MOTION → INCONCLUSIVE]`.
- **F-1 Race specifically is NOT a perception concern.** It read `fixed` only because the car never accelerated
  (the auto policy holds no throttle) → no road-scroll. It's an instance of the known autonomous-control gap, not
  a misclassification.
- **Methodology (the load-bearing bit):** the held-out set was recorded HANDS-OFF on purpose. That discipline is
  exactly what surfaced the real bottleneck — autonomous **control** of non-top-down games, not camera-model
  **perception**. Hand-playing them would have "verified" the classifier on human-produced data and hidden it.

## Next

The gap is autonomous locomotion for side-scroll / racing / intro-gated games — i.e. a competent controller,
which is the agent itself (the project's end goal). Camera-model perception is verified-good where drivable, so
the generalizable ego-motion estimator can branch on it (fixed→none / 2D-scroll→`best_shift` / 3D→optical-flow)
for the games we can drive today, and the held-out set re-runs cleanly once autonomous control improves.
