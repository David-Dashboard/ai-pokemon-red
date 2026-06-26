# 2026-06-24 — visual embedding / commodity vision models: survey for screen-only perception

Reference scan (wide web research, 3 parallel surveys) of lightweight commodity vision models, judged against
THIS project's constraints: 160×144 hard pixel-art, 16px sprites, **CPU-only (no usable GPU)**, tasks =
frame-to-frame change/move detection · sprite localization · scene/mode classification, cheap-first, commodity
licenses, and the standing prior that **a plain perceptual hash beat CLIP on pixel-art** ("CLIP is a labeler,
not a finder").

## Headline (convergent across all three surveys + this repo's prior)
**Learned embeddings are *invariance machines* — engineered to FORGIVE small image changes.** Our live problem
(detect a one-tile move while ignoring flicker) is the opposite. Embeddings pool away the localized signal that
a per-cell pixel-diff captures (grid-max AUC 0.99). The "hash beats CLIP on pixel-art" pattern **strengthens**
in our regime (exact pixel registration, 4-colour palette, no sensor noise → invariance buys nothing). So:
- **Change / move / sprite-localization → classical pixel/spatial methods, not embeddings.**
- **Embeddings earn a place only on SEMANTIC tasks** we don't solve well: scene/mode classification (cave/town/
  battle) and "have I seen this place" novelty/retrieval. And even there, OOD on pixel-art is real + unbenchmarked.

## Taxonomy + pros/cons (for our use case)
| Family | Best commodity picks | Pros | Cons here | Fit |
|---|---|---|---|---|
| Image-text (CLIP-like) | **SigLIP2** (Apache), **TinyCLIP-39M** (MIT); MobileCLIP ⚠NC | zero-shot scene labels, text-queryable | global vector → no localization; OOD-weak on sprites | scene/mode gate (escalation) |
| Self-supervised ViT | **DINOv2 ViT-S/14** (Apache, 21M, 384-d, ~50ms CPU); DINOv3 ⚠gated | strong features; **patch tokens can localize**; real CPU bench | natural-image OOD; ViT 14px patch ≈ 1 sprite; needs a tiny probe | best embedding *if* we want one |
| Efficient CNN extractors | **ConvNeXt-Atto** (Apache, 3.4M, 320-d); MobileNetV3-S (2.5M) | cheapest neural; early conv edges survive pixel-art better than ViT | still OOD; blunt scalar for change | cheap per-step novelty (if ever) |
| Training-free hashes | pHash/dHash/wHash, PDQ, `imagehash` | ~free | **built to ignore small changes** → calls a real move "same"; no localize | scene dedup only |
| Classical SPATIAL | **per-cell pixel-diff / grid-max**, per-cell **SSIM**, **MOG2/KNN bg-subtraction** | flicker-robust by construction; µs–ms; numpy/OpenCV | SSIM needs scipy/skimage (or DIY numpy); MOG2 needs OpenCV | **the move/flicker upgrade path** |
| Lightweight segmentation | MobileSAM/FastSAM/EdgeSAM; **`connectedComponents`** | isolate the sprite | SAMs interactive (don't say *if* it moved), tiny-object-weak, 100s ms CPU; **FastSAM AGPL** | use blob detection, not SAM |

## License landmines (you said "commodity")
- **Non-commercial weights — avoid for shipping:** MobileCLIP / MobileCLIP2 (Apple AMLR), MetaCLIP-2 (CC-BY-NC),
  jina-clip-v2 (CC-BY-NC), I-JEPA, MAE, ConvNeXt-**V2** small (FCMAE). **FastSAM = AGPL-3.0.** DINOv3 = gated + custom.
- **Clean (Apache/MIT):** DINOv2, SigLIP/SigLIP2, TinyCLIP, EVA-CLIP (code), ConvNeXt-**V1** atto/femto/pico,
  EdgeNeXt, EfficientViT, MobileNetV3.
- **Dependency cost:** any neural model ⇒ add `torch` or `onnxruntime` (heavy — a "separate conversation" dep).
  Classical: per-cell SSIM is DIY-able in **pure numpy (zero deps)**; MOG2 needs OpenCV.

## CPU-latency reality
No vendor publishes commodity-x86-CPU latency for these; mobile/NPU numbers are not CPU. Only real CPU bench
found: DINOv2-S ≈ 46–62 ms/img on a strong desktop core (scale ~5–15× worse on a Pi/modest laptop). Tiny CNNs
(MobileNetV3-S, ConvNeXt-atto) are far cheaper by FLOPs but unbenchmarked on CPU. ONNX-export → `onnxruntime`
(or transformers.js/WASM) is the realistic no-GPU path; budget ~0.5–2 s/frame for a B-class model — escalation-only,
not per-step.

## What this means for us
1. **False-MOVE / flicker (the live problem):** NOT an embedding job. Empirically (`eval/probe_spatial_move.py`):
   grid-max and per-cell SSIM both hit AUC 0.99 (vs 0.86 whole-frame) but both leave ~25–33% runaway residual →
   **grid-max (numpy, no deps) + a behavioral no-progress guard.** See `2026-06-24-phantom-move-probe.md`.
2. **Scene/mode classification (a separate, real weakness — `detect_modality` is crude):** the one place an
   embedding could help. Clean picks: **DINOv2 ViT-S/14 + a tiny linear probe**, or **SigLIP2** (text-queryable).
   Gated behind (a) a torch/onnx dependency conversation and (b) an empirical pixel-art transfer check on our
   own frames first (OOD risk).
3. **Sprite isolation:** skip SAM-family; `connectedComponents` on a background-subtraction mask is cheaper + more
   reliable on a 16px sprite.

## Sources (selected)
MobileCLIP/2 https://github.com/apple/ml-mobileclip · TinyCLIP https://github.com/wkcn/TinyCLIP · SigLIP2
https://huggingface.co/blog/siglip2 · DINOv2 https://github.com/facebookresearch/dinov2 · DINOv3 license
https://huggingface.co/facebook/dinov3-convnext-tiny-pretrain-lvd1689m/blob/main/LICENSE.md · dinov2.cpp CPU
bench https://alexlavaee.me/projects/dinov2cpp/ · timm https://github.com/huggingface/pytorch-image-models ·
imagehash https://github.com/JohannesBuchner/imagehash · PDQ https://github.com/facebook/ThreatExchange ·
LPIPS https://github.com/richzhang/PerceptualSimilarity · OpenCV bg-subtraction
https://docs.opencv.org/4.13.0/d1/dc5/tutorial_background_subtraction.html · efficient-SAM survey
https://arxiv.org/html/2410.04960v1 · Atari SSL (ST-DIM) https://arxiv.org/pdf/1906.08226 · hash-vs-CLIP regime
https://www.mdpi.com/2079-9292/15/7/1493
