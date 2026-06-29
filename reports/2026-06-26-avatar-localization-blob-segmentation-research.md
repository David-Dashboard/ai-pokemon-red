# Avatar localization + blob segmentation — research grounding (2026-06-26)

Source: a deep-research sweep (102 agents, 20 sources, 25 claims adversarially verified → 19 confirmed,
6 refuted). Synthesized through our constraints: cheap-classical-first, pixels-only, cross-game, fixed +
scrolling cameras, 160×144 retro art. This grounds the next build (avatar-localization + blob-segmentation).

## What this VALIDATES (we're on the right track)
- **Our `AvatarLocalizer`'s action-correlation IS the canonical method.** Control-grounded **contingency**
  (Bellemare/Veness/Bowling, *AAAI 2012*): the avatar = the pixels whose next-frame value depends on the most
  recent action. We independently arrived at the academically-validated, training-free, cross-game approach.
- **Our `best_shift` ego-motion is the RIGHT choice for scrolling pixel art.** The research's own caveat:
  grid-keypoint / ORB+RANSAC homography trackers get **starved by low-texture 160×144 tiles** and confused by
  animation flicker; for pure-translation scroll, **phase-correlation / best-shift is cheaper + more robust** —
  exactly what we already have. (So do NOT switch to ORB/homography for our domain.)

## Concrete UPGRADES the literature points to
1. **Bayes-filter the contingency map** (Bellemare). Instead of decaying-heatmap + argmax, feed the per-pixel
   contingency probability into a Bayes filter — **truncated-Gaussian motion model + Gaussian observation
   model** — and take the **MAP** location. Principled temporal smoothing/robustness over a raw argmax.
2. **Contingency need not be spatially connected** → the same mechanism finds **projectiles / other
   controllables** (bullets are separate from the avatar), not just the avatar — a free generalization.
3. **Blob/sprite segmentation = connected-components on a foreground mask.** `scipy.ndimage.label`
   (numpy-ecosystem) or `cv2.connectedComponentsWithStats` (one call → per-blob **bbox + area + centroid**).
   Recommended over Hu-moments (which give one centroid only). Refine with morphology (erosion/dilation);
   **watershed to split touching blobs** (the known CC failure mode).
4. **Persistence/tracking** = centroid / IoU association across frames (SORT) for blob identity over time.

## The cheap-first pipeline (ranked by cost), for us
- **Fixed camera:** rolling-median bg-subtract (have) → foreground mask → `ndimage.label` → blobs
  (centroid/bbox/area) → avatar = the blob whose motion correlates with the commanded action (contingency,
  have) → Bayes-filter smooth.
- **Scrolling camera:** `best_shift` (have) → warp-align → bg-subtract → CC → blobs → contingency for avatar.
  Optional robustness booster: **optical-flow orientations** (depth-invariant under pure translation) to peel
  independently-moving sprites off the coherent scrolling background.

## When to climb to a learned model (the measured trigger)
- **NOT raw VLM.** GPT-4o is documented to fail at localizing player-adjacent objects (Cradle, NeurIPS 2024;
  corroborated by Eureka's 13.1 AP50). The production screen-only agent **Cradle** uses **SAM (ViT-H) +
  Set-of-Mark with heavy classical pre/post-filtering** — and that's for **high-res desktop/PC games**. At
  160×144, classical CC labeling is adequate; SAM is overkill (lighter MobileSAM/FastSAM/SAM2 only shift this
  if measurement says so).
- **The climb target is self-supervised agency-discovery** — ADM (Choi et al., *ICLR 2019*), action-conditioned
  video prediction, AC-State — real + effective but **all require training**. So: climb only when the classical
  Bayes-filter contingency stack **measurably** fails.

## Avoid (adversarially refuted, 0-3)
- **Color/palette segmentation** by "constant character color" — NOT robust across games.
- **Template matching** (`matchTemplate` ~0.9) as a general locator — brittle to animation/scale/rotation.
- Don't assume the published moving-camera pipelines run real-time — **benchmark on our 160×144 target.**

## Open questions = OUR measurements (the literature doesn't cover retro)
- Failure rate of the classical contingency localizer on busy **scrolling 160×144** — no source benchmarks it.
- Does `best_shift` beat ORB+RANSAC on flat pixel art (the lit assumes feature-rich natural video)? Likely yes.
- Does **animation flicker** corrupt the contingency heatmap — is the decaying-heatmap smoothing enough, or is
  an explicit flicker-rejection step needed?

## Dependency note
Prefer `scipy.ndimage.label` (small, numpy-ecosystem) or a ~20-line pure-numpy connected-components for the
core path; **avoid OpenCV (`cv2`) unless measurement forces it** (new heavy dep — separate conversation).
