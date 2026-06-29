# Dataset + CNN portfolio for the perception ontology — plan

_2026-06-28. Companion to [`perception-ontology.md`](perception-ontology.md). PLAN only — no training has
been authorized/started. Introduces a training pipeline into a so-far training-free repo; treat torch + a
detector framework as a deliberate new-dependency conversation, not a drift._

## Core principles (baked in, learned the hard way)

1. **Leave-one-GAME-out splits.** Same-game frames leak (the modality probe proved it — splitting Pokémon
   runs would have been bogus). Validate on held-out *games*, not held-out *frames*. Keep the existing
   held-out set (crystalis / zelda / sml / f1race) sacrosanct; add held-out GBA titles too.
2. **Weak-supervision bootstrap — the biggest lever.** We already have label *generators* for free: RAM
   oracles (HUD values, avatar x/y), the `best_shift` router (camera class), contingency (avatar pixels), the
   glyph/RapidOCR decoders (text). Auto-label with these, human-*verify* a subset → ~10× less manual labeling.
3. **General, not per-game.** A CNN trained cross-game and frozen is legitimate harness/code (the
   learning-boundary law permits across-game code updates) — **only** if it generalizes leave-one-game-out. A
   per-game-tuned CNN would violate the constancy claim. Generalization is the acceptance bar, not accuracy.
4. **Lightweight / CPU-fast.** These run in System-1, some per-frame. Mandatory: small models
   (MobileNetV3-small tier), CPU-runnable, no per-frame GPU. Cheap is a hard constraint.
5. **Measure-first ordering.** The end-to-end bench tells us which model actually moves task-success. Build in
   priority order but let the bench re-rank — don't train all four blind.

## The dataset (one corpus, layered labels)

Sample frames from the `runs/` recordings (~thousands across ~20 GB/GBC/GBA games), stratified by ontology
cell (balance modes, camera classes, platforms). One versioned corpus: `datasets/ontology/` = `frames/` +
layered label files. The existing `datasets/labels/v2` (avatar/enemy/item/exit/npc/health/text boxes,
~50 frames/game) is the **seed**, especially for S7.

| Label layer | Stage | Label type | Source |
|---|---|---|---|
| `mode`       | S2 | 1 class / frame        | human (montage sheets — fast) |
| `substrate`  | S1 | 1 class / game         | **auto** (channel-spread, tile-autocorr) |
| `camera`     | S3 | 1 class / (game,mode)  | **auto-bootstrap** `best_shift`, human-verify |
| `embodiment` | S4 | 1 class / (game,mode)  | **auto-bootstrap** contingency, human-verify |
| `avatar`     | S6 | keypoint / bbox        | **auto** contingency+RAM, human-verify |
| `entities`   | S7 | bbox + class           | human (expensive — propose-and-correct) |
| `hud/text`   | S8 | region + string        | **auto** oracle+RapidOCR |

**S7 is the expensive layer.** Mitigate: pre-label with a weak detector (motion+appearance) → humans
*correct* rather than draw. Settle a **general entity taxonomy** first:
`avatar · enemy · npc · item · projectile · obstacle · exit · ui`.

## The CNN portfolio

| # | Model | Stage | ML task | Input | Arch (lightweight) |
|---|---|---|---|---|---|
| 1 | **Mode classifier**   | S2     | image classification        | 1 frame        | MobileNetV3-small / tiny ConvNet |
| 2 | **Camera+embodiment** | S3,S4  | clip/pair classification    | frame-pair(+flow) | small 2-frame CNN |
| 3 | **Avatar localizer**  | S6     | keypoint / heatmap          | 1 frame        | tiny U-Net / heatmap head |
| 4 | **Entity detector**   | S7     | object detection (bbox+cls) | 1 frame        | YOLO-nano / NanoDet |
| — | OCR                   | S8     | —                           | —              | **reuse RapidOCR, no training** |
| — | Segmentation          | S7 climb | instance seg              | 1 frame        | MobileSAM/FastSAM **distilled — deferred** |

- **#1 Mode** — highest priority: per-frame router, weak hand-coded coverage (fine menu-detection near-chance
  cross-game), cheap labels, seed data exists. Simplest task, biggest routing payoff.
- **#2 Camera/embodiment** — needs *motion*; input is a frame-pair / flow (one frame can't tell fixed from
  follow). Labels nearly free (the behavioural router already decides it; the CNN *distills* it for
  single-glance speed). High ROI, low label cost.
- **#3 Avatar** — bbox/keypoint, fixed-camera-relevant only (follow cameras use odometry, not a CNN).
  Contingency gives weak labels for free.
- **#4 Entity detector** — biggest content hole, most data-hungry. Detection (bbox+class) is the right task;
  instance segmentation is the climb target only if detection proves insufficient (Cradle-style SAM,
  distilled to stay cheap).

## Sequencing (proposed)

1. **Labeling pipeline + bootstrap auto-labelers** (camera/embodiment/avatar/text from routers+oracles) — the
   unlock; cheap labels at scale.
2. **Train #1 Mode classifier** — smallest task, biggest router payoff; validate leave-one-game-out. Proves
   the train → general-CNN → deploy loop end-to-end.
3. **Run the end-to-end bench** → re-ranks #2/#3/#4 by *measured* task impact.
4. **Train the bench-prioritized model** next, labeling pipeline already in place.

## Open decisions before committing

- **The training shift itself** — new pipeline (data, GPU/Colab, label tooling), new deps (torch + a detector
  framework). Compliant if general, but a deliberate new axis of complexity.
- **Sequencing: mode-first vs bench-first.** Recommendation: mode-first (cheap, proves the loop), then the
  bench picks the next. Alternative: run the bench before any training so the first model is bench-chosen.
