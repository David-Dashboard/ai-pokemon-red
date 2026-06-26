"""Compare CLIP variants (OpenAI / SigLIP / MobileCLIP) as per-cell sprite
classifiers, on the bedroom frame's known cells. Reports params, load time,
per-cell latency, and top-1 accuracy on a small hand-labeled ground-truth set.

    .venv-probe4\\Scripts\\python.exe eval/clip_compare.py
"""
import time
import torch
import open_clip
from PIL import Image

MODELS = [
    ("ViT-B-32", "openai"),               # our baseline
    ("ViT-B-16-SigLIP", "webli"),         # SigLIP (strong reference)
    ("MobileCLIP2-S0", "dfndr2b"),        # newest tiny mobile
    ("MobileCLIP-S2", "datacompdr"),      # mid mobile
    ("MobileCLIP-B", "datacompdr"),       # big mobile
]

LABELS = [
    "a blank repeating tiled floor pattern",  # 0 floor
    "a plain stone wall",                      # 1 wall
    "a small cartoon person or character",     # 2 person
    "a small round ball",                      # 3 ball
    "a glowing television or computer screen",  # 4 screen
    "a leafy green potted plant",              # 5 plant
    "a wooden box or cabinet",                 # 6 furniture
    "a staircase",                             # 7 stairs
]
KEY = ["floor", "wall", "person", "ball", "screen", "plant", "furniture", "stairs"]

# ground truth on runs/perception_run/frame_000001.png (verified cell-by-cell)
GT = [(0, 0, "floor"), (9, 0, "floor"), (2, 2, "floor"), (7, 2, "floor"),
      (2, 6, "floor"), (6, 7, "floor"),
      (4, 1, "screen"), (1, 3, "furniture"), (7, 3, "plant"), (4, 4, "person")]
DIAG = [(4, 3, "console"), (7, 4, "pot-base")]   # the cells that FP'd as "ball"

CELL, UP = 16, 16
img = Image.open("runs/perception_run/frame_000001.png").convert("RGB")


def cell(c, r):
    x0, y0 = c * CELL, r * CELL
    return img.crop((x0, y0, x0 + CELL, y0 + CELL)).resize((CELL * UP, CELL * UP), Image.NEAREST)


allcells = [cell(c, r) for r in range(9) for c in range(10)]

print(f"{'model':22}{'params':>8}{'load':>7}{'90cell':>8}{'/cell':>7}{'acc':>6}   object preds | diag")
print("-" * 120)
for name, pre in MODELS:
    t0 = time.time()
    try:
        model, _, preprocess = open_clip.create_model_and_transforms(name, pretrained=pre)
        tok = open_clip.get_tokenizer(name)
    except Exception as e:
        print(f"{name:22} LOAD FAIL: {repr(e)[:70]}")
        continue
    model.eval()
    load = time.time() - t0
    nparams = sum(p.numel() for p in model.parameters()) / 1e6

    with torch.no_grad():
        tf = model.encode_text(tok(LABELS))
        tf = tf / tf.norm(dim=-1, keepdim=True)

    def classify(imgs):
        x = torch.stack([preprocess(i) for i in imgs])
        with torch.no_grad():
            vf = model.encode_image(x)
            vf = vf / vf.norm(dim=-1, keepdim=True)
            return (vf @ tf.T).softmax(-1)

    t1 = time.time()
    classify(allcells)
    grid_ms = (time.time() - t1) * 1000

    probs = classify([cell(c, r) for c, r, _ in GT])
    correct, obj = 0, []
    for i, (c, r, true) in enumerate(GT):
        j = int(probs[i].argmax())
        if KEY[j] == true:
            correct += 1
        if true != "floor":
            obj.append(f"{true}->{KEY[j]}({float(probs[i][j]):.0%})")

    dg = classify([cell(c, r) for c, r, _ in DIAG])
    diag = [f"{DIAG[i][2]}->{KEY[int(dg[i].argmax())]}" for i in range(len(DIAG))]

    print(f"{name:22}{nparams:6.0f}M {load:5.1f}s {grid_ms:6.0f}ms {grid_ms/90:5.1f}ms "
          f"{correct:2}/{len(GT)}  {', '.join(obj)} | {', '.join(diag)}")
    del model
