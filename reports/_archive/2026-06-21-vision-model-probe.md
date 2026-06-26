# Vision-model probe — lightweight zero-shot perception on Game Boy frames (2026-06-21)

**Question (David):** are there off-the-shelf *lightweight zero-shot* vision models, and what do
they actually output on our 160×144 pixel-art frames — across the input forms (full image vs
grid-crop, native vs upscaled)?

**Why it matters (north star):** the project wants *cheap, off-the-shelf, generalizable* perception
from the screen. Today perception is a hand-built, Pokémon-specific perceiver (template font,
odometry, occupancy) — reliable for this one world but **not** generalizable. The live bottleneck is
the **walk-to-a-ball affordance** (localize + transact the Pokéball on Oak's table). So: can a
zero-shot model ground that without bespoke engineering? This is a *diagnose-before-betting* probe —
nothing is wired into the agent.

## Setup

- **Harness:** `eval/vision_probe.py` (reusable, model-pluggable, resilient — each model×frame×condition
  wrapped, failures recorded). Overlays + `results.json` + `REPORT.md` + per-frame montages
  (`eval/_probe_montage.py`) under `runs/vision_probe/`.
- **Frames (7, ground-truth-known):** interior rooms (player + NPC + TV/PC + plant + table + doormat),
  the intro **battle** demo (Nidorino vs Gengar), the **title** screen (Charmander + trainer + logo +
  text), an overworld interior. *(No confirmed Oak-lab-Pokéball-table frame — see caveats.)*
- **Input conditions:** full-frame & center-crop × native / 2× / 4× — **nearest-neighbour** upscale
  (bilinear would blur pixel-art).
- **Models / envs:** CLIP (`clip-vit-base-patch32`) + OWLv2 (`owlv2-base-patch16-ensemble`) ran on
  `.venv-probe` (py3.14, transformers 5.x). **Florence-2-base** + **Moondream2** needed
  `.venv-probe4` (py3.12 + transformers 4.49) — *both fail to load on transformers 5.x* (remote code
  written for 4.x). **Sonnet** (paid reference ceiling) via the wired litellm:4001. CPU only (GPU is a
  2 GB MX250 — unusable for these). Moondream's 3.8 GB download flaked (`IncompleteRead`); retrying.

## Headline

**Lightweight zero-shot models DO produce real signal on GB sprites — but capability splits sharply by
output type, and the sprite domain gap hits *fine-grained semantics* hardest (across the *whole*
spectrum, up to and including Sonnet).** What survives the 16-px pixel-art gap is **localization**
(everyone) and **scene/text** (CLIP, Florence). Correct object *labels* only come for the larger,
blockier sprites (TVs, creatures, logos, text).

| Model | Size | Latency (CPU)¹ | Best at | Fails at | One-line verdict |
|---|---|---|---|---|---|
| **CLIP** | 0.15B | **~0.15 s** (~7/s) | **Scene class** — battle **1.00**, title 0.96, room ✓ | no localization | cheap reliable **mode/scene gate** |
| **Florence-2** | 0.23B | ~7.7 s/task (~23 s/frame²) | **OCR** (read "Red Version… GAME FREAK inc."), scene caption, logo ID | open-vocab **detect = 1 box** (weak) | small **captioner/OCR**, not a detector |
| **OWLv2** | 0.15B | ~12 s | **Where** salient sprites are (TV `@[64,16,80,32]` 0.44; both battlers; Charmander 0.52) | **What** they are (player→"monster"); phantom "Pokeball" | **localizes, mislabels** small sprites |
| **YOLOv8n** | 3.2M | **~0.09 s** (~11/s) | localizes salient sprites (boxes the player + plant) | **closed COCO vocab forces garbage labels** — player & plant → "traffic light" (0.6); worse at 4× | fastest, but **unusable labels** on pixel-art |
| **YOLO-World** | ~13M | ~0.35 s | open-vocab; a few *correct* low-conf hits (TV 0.24, plant 0.27); no Poké Ball FPs | **low recall** — (none) on creatures/title/most objects | fast open-vocab, but **misses most**; cleaner & weaker than OWLv2 |
| **Sonnet** | — | ~3.9 s (cloud³) | **What + where** (all 4 room objects named + coords at native) | fine-grained sprite **identity** (species flip-flops) | the ceiling; not lightweight |
| **Moondream2** | 1.8B | pending | (pending — download flaked) | — | retryable |

¹ Mean per-call wall-clock on **Intel i7-10510U** (4C/8T @1.8 GHz, no usable GPU). **Upscale barely changes CPU latency** (native vs 4×: OWLv2 11.6→12.1 s, Florence 8.0→7.6 s) — these models resize to a fixed internal resolution, so input form is an *accuracy* choice, not a speed one.
² Florence runs 3 tasks/frame (caption + open-vocab-detect + OCR). ³ Sonnet latency is cloud round-trip (network + API), **not** CPU compute.
**Speed takeaway:** a fast tier (YOLOv8n ~0.09 s, CLIP ~0.15 s, YOLO-World ~0.35 s) could run per-step; OWLv2/Florence (~12–23 s/frame) are **stuck-moment-escalation-only** on this CPU. But **speed and usefulness are inversely correlated here** — the fastest models (YOLO) are the least reliable on sprites; the most useful localizer (OWLv2) is the slowest.

## Per-model detail

- **CLIP — scene classifier.** Battle demo → "a Pokémon battle between two monsters" **1.00** at every
  condition; title → "title screen with a logo" 0.96; rooms → "person/people in a room" (correct gist).
  No boxes. **Useful as a cheap mode gate** — notably it could disambiguate the full-screen-bright menus
  our pixel `detect_mode` mislabels (the nickname keyboard read as `battle`).
- **Florence-2 — captioner + OCR.** **OCR read the title text** (`Red Version … GAME FREAK inc.`) and it
  **recognized the Pokémon logo**; battle caption got count+colour ("two animals, one purple, one pink" →
  "a purple wolf and a pink…") but not species; room captions plausible with drift (table→"bed"). Its
  `<OPEN_VOCABULARY_DETECTION>` returned **only 1 box** every time — Florence is not a usable detector
  here. The **OCR is the standout free capability** (our textbox decoder only covers the hand-calibrated
  early-game charset).
- **OWLv2 — open-vocab detector.** Localization tracks **sprite size/contrast**: TVs/PCs nailed
  (label+box, 0.44–0.55), both battle creatures found as "monster" (0.26/0.21), Charmander 0.52. The
  **player (16 px) is always detected but mislabeled "monster"** (recurring center tile `[65,60,79,76]`).
  **Recurring false-positive "Pokeball"** on round table-items and at 4× — i.e. the *one affordance class
  we want is the unreliable one*. Real detections sit ≥0.2; the 0.05 threshold just adds clutter.
- **Sonnet — ceiling.** Names + locates all room objects even at native (player ~(85,105), PC ~(105,48),
  plant ~(138,105), cabinet ~(18,75)). But **fine-grained identity is unstable and input-form-dependent**:
  the pink battler was "Togetic" (native) → "Clefable" (4×) → "Snubbull" (crop), **none correct** (it's
  Nidorino) — though the big iconic "Gengar" was right every time. Also occasional phantom Poké Balls at 4×.

## Input-condition findings (directly answering the question)

1. **Upscale 4× → more fine detail, but more hallucination.** Sonnet enumerates each chair individually
   at 4× (vs "chairs" at native); CLIP confidence rises on a single centered subject (0.37→0.75,
   0.49→0.74, 0.72→0.84). **But** 4× also spawns phantom Poké Balls (OWLv2 *and* Sonnet) and "bed/
   nightstand" drift. For OWLv2, 4× does **not** raise true-detection scores (it resizes internally;
   TV stays ~0.44 at every scale) — it only adds low-confidence clutter.
2. **Crop helps a centered subject but drops edge context — sometimes catastrophically.** On the **title
   screen**, cropping removed the logo/text: CLIP **flipped** title→"battle" (0.96→0.91), and Sonnet lost
   the "title screen" framing. When the discriminative content (text, logo) is at the edge, crop hurts.
3. **No free lunch; native full-frame is the safe default** for a strong VLM (keeps text + context).
   Crop+upscale is the lever for a *cheap classifier* on a *centered* subject. **Nearest-neighbour**
   (not bilinear) matters for sprites.

## What this means for the project

- **For the walk-to-a-ball affordance (the live bottleneck):** a free local detector **alone won't
  reliably ground the Pokéball** — small-sprite semantics is exactly where every model fails, and the
  "Pokeball" class specifically is FP-prone. **But localization survives.** The attractive shape is a
  **hybrid that respects the dual-process seam:** System-1 uses a cheap detector for *saliency* ("here
  are the N non-floor sprites + boxes"), and a stronger step (Sonnet escalation, or our existing
  interaction-probe / template check) decides *which* is the ball. We don't need the cheap model to be
  right about *what* — only about *where*.
- **Two concrete, in-scope wins surfaced (free, local):**
  - **CLIP as a mode/scene gate** — battle/title/room at ~1.0 confidence. Could harden `detect_mode`
    where the pixel heuristic mislabels bright full-screen menus (the nickname-keyboard-as-`battle` bug).
  - **Florence-2 OCR** — read GB text zero-shot. Worth a targeted follow-up on real **dialog/battle-menu**
    frames; if it holds, it generalizes our charset-limited textbox decoder.
- **The domain gap is real but NOT total.** Blocky/large content (TVs, creatures, logos, text) is
  recognized; tiny sprites are localized-but-mislabeled everywhere. This empirically reaffirms the
  north-star tension: off-the-shelf perception is *reachable for saliency + scene + text*, but
  *sprite-level identity* still needs grounding (template, RAM-oracle scoring, or a strong VLM).

## Follow-up — per-cell classification (the "grid" idea)

**Idea (David):** instead of whole-frame detection (where a 16-px sprite is lost), tile the frame into
**sprite-sized 16×16 cells**, upscale each 8×, and CLIP-**classify each cell** → a semantic grid.
The extreme of "crop+upscale helps a centered subject." `eval/probe_grid.py` (batched: all 90 cells in
one CLIP pass, ~1–2 s/frame on CPU).

**Result: it works for coarse semantics — but is brutally sensitive to label wording, and "ball" stays
FP-prone.**
- **First label set failed completely:** with `"the player character sprite from Pokemon"` in the list,
  CLIP labeled **every** cell — floor included — "player" at ~65%. A label containing "Pokemon" pulls
  all pixel-art toward it.
- **Neutral visual labels → a clean grid:** with `"a blank repeating tiled floor pattern"` / `"a small
  cartoon person"` / `"a blue glowing screen"` / `"a leafy green plant"` / `"a brown box"`, the bedroom
  frame came out **right**: floor cells → background, and **TV ✓, player ✓, plant ✓, cabinet→box ✓** each
  in its correct cell. This **beats whole-frame** for small-sprite semantics (whole-frame CLIP only did
  scene; whole-frame OWLv2 mislabeled the player "monster").
- **But the affordance class is still the weak one:** the gray console and the plant's **pot-base both
  got tagged "ball"** (52% / 41%) — the same Pokéball/round-object false-positive seen everywhere else.
  Threshold-sensitive (a 41% FP) and dependent on the sprites sitting on the 16-px lattice (held here on a
  static interior).

**Implication:** a **per-cell CLIP "semantic occupancy grid"** is a plausible *cheap, generalizable
System-1 perception layer* — better than whole-frame for tiny sprites, ~1–2 s/frame, no game-specific
training — **if** labels are calibrated. It still can't pinpoint the Pokéball alone. The robust shape:
cheap **saliency/anomaly first** (frame-diff vs the modal floor tile → candidate non-floor cells, which we
*already* compute in the occupancy/motion-saliency layer), then per-cell classify only those few cells,
and confirm the ball with a stronger step. I.e. per-cell classification is a *refinement* on top of our
existing saliency, not a replacement for it.

## CLIP-variant comparison + the precision/recall split

Two follow-ups (David): (a) compare CLIP variants incl. **MobileCLIP**; (b) recognize that CLIP is a
*precision* tool (classify a given cell) and we also need *recall* (find which cells matter).

**(a) CLIP variants — per-cell classifier, 10 hand-labeled bedroom cells** (`eval/clip_compare.py`, via
`open_clip`):

| model | params | per-cell | acc (10) | "ball" FP |
|---|---|---|---|---|
| ViT-B-32 (openai) ← *old baseline* | 151M | 47 ms | **5/10** ⚠ | console→ball |
| ViT-B-16-SigLIP | 203M | 222 ms | 9/10 | console+pot→ball |
| **MobileCLIP2-S0** | **75M** | 89 ms | **9/10** | **none** (console→floor, pot→person) |
| MobileCLIP-S2 | 99M | 229 ms | 9/10 | pot→ball |
| MobileCLIP-B | 150M | 254 ms | 9/10 | pot→ball |

**MobileCLIP2-S0 wins** — smallest (75M), fast, top accuracy, best false-positive behavior. The
**ViT-B-32 we'd been using is the *worst* (5/10)** — earlier per-cell results understated CLIP by using its
weakest variant. (Shared miss = the ambiguous cabinet cell; ~13% confidences because softmax over 8 labels
is flat — argmax is the signal.)

**(b) Recall is the hard part (CLIP can't do it).** CLIP/MobileCLIP classify a *given* cell; they don't
find which cells matter — forced on all 90 they label background too. Two model-free recall (proposal)
methods were both fragile (`eval/probe_recall.py`):
- **Background-subtraction** (vs median cell): 2/4 recall, 39% flagged incl. floor — broke on the *bimodal*
  frame (beige floor + black margin poison the median).
- **Density/outlier** (objects = isolated cells): worked on a uniform-floor frame (sensible 26% proposal on
  the furniture) but **flagged ~100% on diagonal-patterned floors** — floor cells aren't self-similar
  (per-cell pattern phase), so they don't cluster.

⇒ **Single-frame model-free recall on GB floors is floor-texture-dependent and unreliable.** Recall in a
game comes from **temporal + behavioral** signals, which we *already have*: **motion-saliency** (frame-diff →
animating NPCs/player) and the **interaction-probe** (face a wall + press A). The architecture this points to:

> **recall** = motion-saliency + interaction-probe (temporal/behavioral) **→ precision** = MobileCLIP2-S0
> labels the proposed cells (~89 ms each, 9/10). CLIP is the *labeler*, never the *finder*.

This is the cheapest concrete path to a generalizable perception layer that surfaced from the whole probe.

**Realized prototype (`eval/probe_pipeline.py`) — David's two-track design, end-to-end:**
**whole-image → descriptive text** (Florence-2 caption + OCR) **+ CLIP grid → spatial object map**
(MobileCLIP2-S0 per-cell). On the bedroom frame the caption gave a correct gist ("a room… a small orange
character… a blue computer monitor… the character is standing in front of the monitor"; mild hallucination
"two plants") and the grid returned coordinate-tagged objects (TV `screen@(4,1)` ✓, `plant@(7,3)` ✓, player
`person@(4,4)` ✓; cabinet→screen, pot→person the known ambiguous misses; floor cleanly dropped). The caption
supplies the *gist/vocabulary*, the grid supplies the *coordinates* — complementary, both cheap, both local.
Limit unchanged: a lone tiny sprite (a single Poké Ball) is still not reliably named by either. Not wired into
the agent — a prototype.

## Lighter OCR / captioner alternatives (follow-up)

**OCR** (`eval/ocr_compare.py`) — dedicated engines are far lighter than Florence's VLM-OCR:

| OCR | size | speed | gen1 dialog | title/logo font |
|---|---|---|---|---|
| **RapidOCR** (PP-OCR mobile, ONNX) | **~8 MB** | ~1.0 s | needs **3× upscale** → "I was a seri ous Poké" ✓ | "Red Versio… GAME FREAK inC" (minor errs) |
| Florence-2 | 230M | ~5–7 s | "I was a seriousPOKé" ✓ | "Red VersionC'95.96.98 GAME FREAK inc." (cleanest) |
| *our template decoder* | ~0 | free | **gen1 ~100%** (baseline) | n/a (charset not calibrated) |

⇒ **RapidOCR is ~30× smaller + ~5× faster than Florence and reads GB text usably** (upscale small fonts; 1×
hurt the small dialog, 3× hurt the big logo — text-size-dependent). For *in-game gen1 dialog* our template
decoder still wins (free, ~100%); a general OCR earns its keep on **other fonts/menus/games**. Florence is
most accurate but heaviest.

**Captioner** (`eval/captioner_compare.py`, bedroom frame):

| model | size | speed (CPU) | caption quality |
|---|---|---|---|
| GIT-base | 177M | 9.5 s | **useless** ("the game is a bit different…") — COCO captioner fails on sprites |
| BLIP-base | 247M | 2.5 s | terse/generic: "a small game with a small plant" / lab "a man in a kitchen" |
| BLIP-large | 470M | 5.5 s | generic: "a video game with a person" / lab "a person in a store" |
| CoCa-ViT-B-32 | 254M | 3.6 s | **hallucinated**: "signs on a white wall" / "a man riding a bike on the street" |
| **Florence-2-base** | 230M | ~7 s | correct *detailed* gist + OCR — the practical floor |
| SmolVLM-256M | 256M | **46.6 s** | good *and* instruction-following, but ~7× slower |

⇒ **Florence-2-base beats every pure/lighter captioner on sprites.** Dedicated caption-only models
(BLIP, CoCa, GIT, ViT-GPT2) are COCO/natural-image trained and inherit that bias (terse, generic, or
hallucinated — same failure as YOLOv8n→"traffic light"). **Florence's multi-task training on a huge diverse
set (FLD-5B) is *why* it's robust to OOD pixel-art — not a cost.** And the multi-task heads cost nothing at
caption time: Florence runs **one task per call** (`<MORE_DETAILED_CAPTION>`), so it isn't "also detecting/
OCR-ing" — no efficiency penalty vs a pure captioner, and it's more accurate. SmolVLM-256M is the only
genuinely-different alternative (instructable, but ~7× slower).

## Caveats / not tested

- Small set (7 frames), house/intro scenes; **no Oak-lab Pokéball-table frame** (the exact affordance) —
  a follow-up should capture lab + dialog + battle-menu frames and re-probe (esp. Florence OCR + a
  saliency detector on the real ball table).
- CPU-only; OWLv2/Florence ~5–15 s/frame — fine for **stuck-moment escalation**, too slow for per-step.
- OWLv2 at threshold 0.05 inflates clutter (real signal ≥0.2). Florence open-vocab path may be
  mis-invoked (1 box) — its `<OD>`/grounding tasks weren't separately tuned.
- **Moondream2 pending** (download flaked, retrying).
- "Lightweight" ≠ "free of setup": Florence/Moondream need transformers 4.x (a separate py3.12 venv),
  not the modern 5.x stack.

## Repro

```
# clip + owlv2 (py3.14 / tf5):   .venv-probe\Scripts\python.exe   eval/vision_probe.py --models clip,owlv2
# florence + moondream (py3.12): .venv-probe4\Scripts\python.exe  eval/vision_probe.py --models florence,moondream --conditions full_native,full_4x,crop_4x
# sonnet (paid, litellm:4001):   .venv-probe\Scripts\python.exe   eval/vision_probe.py --models sonnet --conditions full_native,full_4x,crop_4x
# montages:                      uv run python eval/_probe_montage.py
```
Artifacts: `runs/vision_probe/{REPORT.md, results.json, <model>/*.png, montage_*.png}`.
