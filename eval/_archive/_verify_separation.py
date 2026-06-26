"""ADVERSARIAL VERIFICATION (throwaway): does MobileCLIP2-S0's IMAGE embedding
SEPARATE distinct 16px GB sprites well enough for k-NN label transfer?

Computes the exact numbers the critique demands:
  (1) mean INTRA-class vs INTER-class cosine, with multiple exemplars per class
  (2) leave-one-out 1-NN accuracy over the multi-exemplar set
  (3) the console-vs-ball / pot pair specifically (the FP we want to escape)

Reuses cells already hand-labeled in eval/clip_compare.py + frames already present.
    .venv-probe4\\Scripts\\python.exe eval/_verify_separation.py
"""
import itertools
import torch
import open_clip
from PIL import Image

CELL, UP = 16, 16

# Multi-exemplar labeled set. Cells verified in clip_compare.py GT/DIAG (frame_000001),
# plus same-class cells from other frames to get >1 per class for intra/inter + LOO-kNN.
# (col,row,frame) -> label
SET = [
    # floor (frame_000001 GT floors)
    (0, 0, "perception_run/frame_000001", "floor"),
    (9, 0, "perception_run/frame_000001", "floor"),
    (2, 2, "perception_run/frame_000001", "floor"),
    (7, 2, "perception_run/frame_000001", "floor"),
    (2, 6, "perception_run/frame_000001", "floor"),
    (6, 7, "perception_run/frame_000001", "floor"),
    # screen / tv
    (4, 1, "perception_run/frame_000001", "screen"),
    # furniture / cabinet
    (1, 3, "perception_run/frame_000001", "furniture"),
    # plant
    (7, 3, "perception_run/frame_000001", "plant"),
    # person / player
    (4, 4, "perception_run/frame_000001", "person"),
    # the two DIAG cells that text-CLIP false-positived as "ball"
    (4, 3, "perception_run/frame_000001", "console"),
    (7, 4, "perception_run/frame_000001", "pot-base"),
]

cm, _, pre = open_clip.create_model_and_transforms("MobileCLIP2-S0", pretrained="dfndr2b")
cm.eval()

cache = {}
def load(stem):
    if stem not in cache:
        cache[stem] = Image.open(f"runs/{stem}.png").convert("RGB")
    return cache[stem]

def crop(stem, c, r):
    img = load(stem)
    return img.crop((c*CELL, r*CELL, c*CELL+CELL, r*CELL+CELL)).resize((CELL*UP, CELL*UP), Image.NEAREST)

crops = [crop(s, c, r) for (c, r, s, _) in SET]
labels = [lab for (_, _, _, lab) in SET]
with torch.no_grad():
    V = cm.encode_image(torch.stack([pre(x) for x in crops]))
    V = V / V.norm(dim=-1, keepdim=True)
S = (V @ V.T)  # cosine sim matrix

n = len(SET)
intra, inter = [], []
for i, j in itertools.combinations(range(n), 2):
    (intra if labels[i] == labels[j] else inter).append(float(S[i, j]))

print("=== overall image-embedding separation (MobileCLIP2-S0, 16px cells) ===")
print(f"  n={n} cells, {len(set(labels))} classes")
if intra:
    print(f"  mean INTRA-class cosine = {sum(intra)/len(intra):.3f}  (n={len(intra)} pairs; want HIGH)")
print(f"  mean INTER-class cosine = {sum(inter)/len(inter):.3f}  (n={len(inter)} pairs; want LOW)")
if intra:
    print(f"  separation (intra-inter) = {sum(intra)/len(intra) - sum(inter)/len(inter):+.3f}")
print(f"  min inter-class cosine  = {min(inter):.3f}   max inter-class cosine = {max(inter):.3f}")

# leave-one-out 1-NN
correct = 0
for i in range(n):
    sims = [(float(S[i, j]), labels[j]) for j in range(n) if j != i]
    pred = max(sims)[1]
    correct += (pred == labels[i])
print(f"\n  LOO 1-NN accuracy = {correct}/{n} = {correct/n:.0%}")

# the specific FP pair we want to escape: console & pot-base vs everything
def sim(a, b):
    ia = labels.index(a); ib = labels.index(b)
    return float(S[ia, ib])

print("\n=== the console/pot 'ball' false-positive pair (does retrieval escape it?) ===")
print(f"  cosine(console, pot-base)  = {sim('console','pot-base'):.3f}")
print(f"  cosine(console, screen)    = {sim('console','screen'):.3f}")
print(f"  cosine(console, furniture) = {sim('console','furniture'):.3f}")
print(f"  cosine(pot-base, plant)    = {sim('pot-base','plant'):.3f}")
print(f"  cosine(pot-base, person)   = {sim('pot-base','person'):.3f}")
# what would each retrieve (excluding self & same-derived) among the *object* classes?
print("\n=== nearest non-floor neighbour for each object cell ===")
for i in range(n):
    if labels[i] == "floor":
        continue
    sims = sorted(((float(S[i, j]), labels[j]) for j in range(n) if j != i), reverse=True)
    top = [f"{l}:{s:.2f}" for s, l in sims[:3]]
    print(f"  {labels[i]:10} -> {', '.join(top)}")
