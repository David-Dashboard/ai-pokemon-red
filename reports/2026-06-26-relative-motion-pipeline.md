# Relative-motion pipeline — the next avatar/entity-localization build (2026-06-26)

The avatar-localization bake-off (`eval/compare_localizers.py`) showed cheap motion-localizers work for
FIXED cameras (baseline: Cave Noire 56% in-box / 4px) but fail for FOLLOW cameras (the avatar stays centered
→ no on-screen motion → ≈0%). The fix is **not** a better screen-localizer — it's to make everything
relative to the camera, so one pipeline handles both camera classes.

## The principle
**All motion is relative to the camera.** Measure the camera's motion first; everything else is *object*
motion relative to it. The camera term is just **0** for fixed cameras → both classes fall out of one pipeline.

## The three steps
**① Camera motion** — `best_shift` (`core/egomotion.py`; phase-correlation of consecutive frames). Cheap,
robust on flat pixel art (research: beats ORB/RANSAC homography here). Two uses:
- **Output:** the per-step scroll. SUM it over time → **world position** (odometry).
- **Router:** `best_shift` ≈ 0 → FIXED camera; large → FOLLOW camera.

**② Object motion** — compensate the camera (shift-align the previous frame to the current), then the
**RESIDUAL** = independently-moving objects.
- The **avatar** = the residual-mover whose motion correlates with the commanded button (control-correlation —
  our existing contingency heatmap, now applied to the *compensated* residual).
- **Blob-segment** the residual (`core/blob.py`, pure-numpy CC) → bounding boxes for every entity (avatar /
  enemies / items).
- **This is the hard part.** A raw residual is noisy: camera-compensation error, animation flicker, and
  freshly-revealed pixels at the scroll edge all leak in → the blob-precision problem (bake-off: P=6%, ~14×
  too many blobs). The work: a **tighter background model** (shorter window / higher threshold / morphological
  erosion), a **flicker-rejection** step, and the **control-correlation** filter to pick the avatar out of the
  movers.

**③ Fuse** — a Kalman / particle filter on top:
- Track world-position (from ①) with a constant-velocity model; correct drift with occasional **absolute fixes**
  (room/screen transitions, recognizable landmarks).
- Fuse observers weighted by confidence; coast through gaps; output `position + velocity + confidence` — or
  **`None` when all observers are weak** (never fabricate). Particle filter (vs Kalman) if the residual is
  multi-modal (two candidate avatars).

## Build order (Realizer Ladder — cheapest first)
1. **Router (`best_shift` regime) + a CLEAN residual in ② + control-correlation to pick the avatar.** This is
   where the accuracy lives; it attacks the two real failure modes (wrong-peak → blob/residual veto;
   wrong-regime → switch to odometry).
2. **The Kalman/odometry fuse in ③** — for smoothing + confidence + gap-bridging; add once ② is trustworthy.
3. **Climb to a learned model only on measured failure** (VLM grounding is documented to fail; SAM is for
   hi-res desktop, not 160×144; the self-supervised agency-discovery line, e.g. ADM, requires training).

## Caveats
- `best_shift` assumes the BACKGROUND fills most of the frame (so the dominant shift = the camera). Usually
  true for tiled retro backgrounds; if a big foreground sprite dominates, ① can lock onto it — the
  optical-flow-orientation trick (depth-invariant under pure translation) is the cheap robustness booster.
- A Kalman filter smooths **noise**; it can't invent a **missing** observation. It does NOT rescue a centered
  avatar's screen position — that's why ① (world-position via odometry) is the real fix for follow cameras.
- **numpy only** (no scipy, no OpenCV, no training). Don't tune on held-out games (Crystalis / Zelda LA /
  Super Mario Land / F-1 Race).

## Where the pieces already exist
- ① `core/egomotion.py::best_shift` (done). ② `core/blob.py` (pure-numpy CC, from the bake-off) + the
  contingency heatmap in `core/localize.py` (the existing `AvatarLocalizer`). ③ — to build. The bake-off
  baseline IS the fixed-camera special case of ② (camera term = 0).
