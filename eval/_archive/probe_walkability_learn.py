"""CENTERPIECE TEST: does a behavior-labelled CLIP-embedding store GENERALIZE
walkability to unseen tiles by retrieval? (David's "walk->walkable, embedding
generalizes" idea, measured on real gameplay + behavioral ground truth.)

Ground truth from the oracle (NO live RAM; replay of recorded runs): for each
overworld step the player is centre-screen at cell (4,4); the FACED tile (cell
(4,4)+dir) in the PRE-move frame is WALKABLE if the move succeeded (outcome
'moved') else BLOCKED. Crop is pure terrain (player not on it yet).

Then: temporal split (first 60% = store, last 40% = test); k-NN retrieve each
test tile's label from the store by cosine; report accuracy / per-class
precision-recall / confusion / majority baseline / novelty distance / and
cross-MAP generalization (test tiles in maps never seen in the store).

    .venv-probe4\\Scripts\\python.exe eval/probe_walkability_learn.py runs/fix2 [runs/fix4 ...]
"""
import sys
import json
import os
from collections import Counter
import torch
import open_clip
from PIL import Image

RUN_DIRS = sys.argv[1:] or ["runs/fix2"]
PLAYER = (4, 4)
CELL, UP = 16, 16
OFF = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


def dir_of(action):
    if not action:
        return None
    a = action.split("+")[0].strip().lower()
    return a if a in OFF else None


def label_of(outcome):
    if not outcome:
        return None
    o = outcome.lower()
    if o == "moved":
        return "walkable"
    if o in ("blocked", "changed-nothing", "no-move", "stuck", "unchanged"):
        return "blocked"
    return None  # 'unknown' etc.


# ---- gather behaviour-labelled faced-tile crops (from the PRE-move frame) ----
samples = []  # (crop_img, label, map_id, global_step)
outcome_hist = Counter()
gstep = 0
for run in RUN_DIRS:
    rows = [json.loads(l) for l in open(os.path.join(run, "oracle.jsonl"), encoding="utf-8")]
    for i in range(1, len(rows)):
        cur = rows[i]
        p = cur.get("perceived", {})
        outcome_hist[p.get("outcome")] += 1
        if p.get("context") != "overworld" or cur.get("in_battle"):
            continue
        d = dir_of(p.get("action"))
        lab = label_of(p.get("outcome"))
        if d is None or lab is None:
            continue
        prev = rows[i - 1]
        fpath = os.path.join(run, f"frame_{prev['step']:06d}.png")
        if not os.path.exists(fpath):
            continue
        cx, cy = PLAYER[0] + OFF[d][0], PLAYER[1] + OFF[d][1]
        img = Image.open(fpath).convert("RGB")
        crop = img.crop((cx * CELL, cy * CELL, cx * CELL + CELL, cy * CELL + CELL)).resize((CELL * UP, CELL * UP), Image.NEAREST)
        gstep += 1
        samples.append((crop, lab, cur.get("map_id"), gstep))

print(f"runs: {RUN_DIRS}")
print(f"outcomes seen: {dict(outcome_hist)}")
print(f"labelled faced-tile samples: {len(samples)}  label dist: {dict(Counter(s[1] for s in samples))}")
if len(samples) < 40:
    print("too few samples; add more runs"); raise SystemExit

# save a few crops per label to eyeball labelling correctness
os.makedirs("runs/vision_probe/walk_samples", exist_ok=True)
seen = Counter()
for crop, lab, mp, gs in samples:
    if seen[lab] < 4:
        crop.save(f"runs/vision_probe/walk_samples/{lab}_{seen[lab]}_map{mp}.png")
        seen[lab] += 1

# ---- embed ----
cm, _, pre = open_clip.create_model_and_transforms("MobileCLIP2-S0", pretrained="dfndr2b")
cm.eval()
with torch.no_grad():
    V = cm.encode_image(torch.stack([pre(s[0]) for s in samples]))
    V = V / V.norm(dim=-1, keepdim=True)
labels = [s[1] for s in samples]
maps = [s[2] for s in samples]

# ---- temporal split (store = first 60%, test = last 40%) ----
n = len(samples)
k0 = int(n * 0.6)
store_V, store_lab, store_map = V[:k0], labels[:k0], maps[:k0]
test_V, test_lab, test_map = V[k0:], labels[k0:], maps[k0:]
store_maps = set(store_map)

def knn_predict(qv, k=3):
    sims = store_V @ qv
    topk = sims.topk(min(k, len(store_lab))).indices.tolist()
    votes = Counter(store_lab[j] for j in topk)
    return votes.most_common(1)[0][0], float(sims.max())

for k in (1, 3):
    correct = 0
    conf = Counter()
    cross_correct = cross_total = 0
    novel_sims = []
    for qv, tl, tm in zip(test_V, test_lab, test_map):
        pred, msim = knn_predict(qv, k)
        novel_sims.append(msim)
        conf[(tl, pred)] += 1
        if pred == tl:
            correct += 1
        if tm not in store_maps:
            cross_total += 1
            cross_correct += (pred == tl)
    acc = correct / len(test_lab)
    maj = max(Counter(test_lab).values()) / len(test_lab)
    print(f"\n=== k={k} ===  test n={len(test_lab)}")
    print(f"  accuracy {acc:.1%}   (majority-class baseline {maj:.1%})")
    for tl in ("walkable", "blocked"):
        tp = conf[(tl, tl)]
        actual = sum(v for (a, _), v in conf.items() if a == tl)
        pred_as = sum(v for (_, pp), v in conf.items() if pp == tl)
        rec = tp / actual if actual else 0
        prec = tp / pred_as if pred_as else 0
        print(f"  {tl:9}: recall {rec:.1%}  precision {prec:.1%}  (n={actual})")
    print(f"  confusion (actual->pred): {dict(conf)}")
    if cross_total:
        print(f"  cross-MAP (test maps unseen in store) acc: {cross_correct}/{cross_total} = {cross_correct/cross_total:.1%}")
    nv = torch.tensor(novel_sims)
    print(f"  nearest-store cosine: min {nv.min():.2f} mean {nv.mean():.2f} (low = novel/far from store)")

# ---- GENERALIZATION: leave-one-MAP-out (test = a map NOT in the store) ----
by_map = Counter(maps)
print(f"\n=== leave-one-map-out generalization ===  map counts: {dict(by_map)}")
for held in sorted(by_map, key=lambda m: -by_map[m]):
    test_idx = [i for i in range(n) if maps[i] == held]
    store_idx = [i for i in range(n) if maps[i] != held]
    if len(test_idx) < 20 or len(store_idx) < 20:
        continue
    sV = V[store_idx]
    sL = [labels[i] for i in store_idx]
    correct = 0
    conf = Counter()
    sims_all = []
    for i in test_idx:
        sims = sV @ V[i]
        j = int(sims.argmax())
        pred = sL[j]
        sims_all.append(float(sims.max()))
        conf[(labels[i], pred)] += 1
        correct += (pred == labels[i])
    acc = correct / len(test_idx)
    maj = max(Counter(labels[i] for i in test_idx).values()) / len(test_idx)
    nv = torch.tensor(sims_all)
    print(f"  hold map {held}: test n={len(test_idx)} acc {acc:.1%} (maj {maj:.1%}) "
          f"nearest-cos min {nv.min():.2f} mean {nv.mean():.2f}  conf {dict(conf)}")
    # accuracy stratified by how NOVEL the test tile is (low cosine = unseen appearance)
    for lo, hi in [(0.0, 0.90), (0.90, 0.97), (0.97, 1.01)]:
        bin_idx = [t for t, s in zip(test_idx, sims_all) if lo <= s < hi]
        if bin_idx:
            bc = sum((sL[int((sV @ V[t]).argmax())] == labels[t]) for t in bin_idx)
            print(f"      cos[{lo:.2f},{hi:.2f}): n={len(bin_idx)} acc {bc/len(bin_idx):.1%}")
