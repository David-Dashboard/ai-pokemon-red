"""Make-or-break test for the embedding-retrieval / spatial-entity-store idea:
does MobileCLIP's IMAGE embedding separate tiny 16px sprites, and does a cell in
ONE frame retrieve the correct labelled exemplar from the bedroom frame?

(1) pairwise cosine among 7 known bedroom exemplars -> is inter-class structure there at all?
(2) cross-frame retrieval overlay: colour every cell of query frames by its nearest
    bedroom exemplar's class -> eyeball whether PC->tv, floor->floor, player->player, etc.
(3) novelty heat: brightness = 1 - max-similarity-to-any-exemplar (bright = far from store).

    .venv-probe4\\Scripts\\python.exe eval/probe_embed_retrieval.py
"""
import torch
import open_clip
from PIL import Image, ImageDraw

EXEMPLARS = {  # runs/perception_run/frame_000001.png  (col,row) -> label  (verified earlier)
    (4, 1): "tv", (4, 4): "player", (7, 3): "plant", (1, 3): "cabinet",
    (0, 0): "floor", (9, 0): "floor", (2, 5): "floor",
}
EX_FRAME = "runs/perception_run/frame_000001.png"
QUERIES = ["runs/percep_bench/frame_000030.png",       # overworld: PC, player, plant
           "runs/perception_run/frame_000016.png",      # room: player, NPC, table
           "runs/modes/242_ui_candidate_dialog.png"]    # Oak lab: Pokeball table (novel!)
CELL, UP, OUT = 16, 16, 5
CCOL = {"tv": (80, 140, 255), "player": (255, 60, 60), "plant": (60, 220, 60),
        "cabinet": (200, 140, 60), "floor": (120, 120, 120)}

cm, _, pre = open_clip.create_model_and_transforms("MobileCLIP2-S0", pretrained="dfndr2b")
cm.eval()


def cell_crop(img, c, r):
    return img.crop((c * CELL, r * CELL, c * CELL + CELL, r * CELL + CELL)).resize((CELL * UP, CELL * UP), Image.NEAREST)


def embed(crops):
    with torch.no_grad():
        v = cm.encode_image(torch.stack([pre(x) for x in crops]))
        return v / v.norm(dim=-1, keepdim=True)


eximg = Image.open(EX_FRAME).convert("RGB")
ex_labels = list(EXEMPLARS.values())
ex_vecs = embed([cell_crop(eximg, c, r) for (c, r) in EXEMPLARS])

print("=== exemplar pairwise cosine (is inter-class structure present?) ===")
keys = list(EXEMPLARS.values())
print("        " + "  ".join(f"{l[:5]:>5}" for l in keys))
for i, li in enumerate(keys):
    row = "  ".join(f"{float(ex_vecs[i] @ ex_vecs[j]):5.2f}" for j in range(len(keys)))
    print(f"{li[:7]:>7} {row}")

for q in QUERIES:
    img = Image.open(q).convert("RGB")
    W, H = img.size
    cols, rows = W // CELL, H // CELL
    V = embed([cell_crop(img, c, r) for r in range(rows) for c in range(cols)])
    sims = V @ ex_vecs.T
    best = sims.argmax(1)
    bestsim = sims.max(1).values

    cls = img.resize((W * OUT, H * OUT), Image.NEAREST).convert("RGB")
    nov = Image.new("RGB", (W * OUT, H * OUT))
    dc, dn = ImageDraw.Draw(cls), ImageDraw.Draw(nov)
    lo, hi = float(bestsim.min()), float(bestsim.max())
    idx = 0
    for r in range(rows):
        for c in range(cols):
            lab = ex_labels[int(best[idx])]
            s = float(bestsim[idx])
            idx += 1
            x0, y0 = c * CELL * OUT, r * CELL * OUT
            dc.rectangle([x0, y0, x0 + CELL * OUT - 1, y0 + CELL * OUT - 1], outline=CCOL[lab], width=2)
            t = 0 if hi == lo else (hi - s) / (hi - lo)   # within-frame novelty 0..1
            dn.rectangle([x0, y0, x0 + CELL * OUT - 1, y0 + CELL * OUT - 1], fill=(int(255 * t), 0, 0))
    stem = q.split("/")[-1].replace(".png", "")
    cls.save(f"runs/vision_probe/retr_{stem}.png")
    nov.save(f"runs/vision_probe/novel_{stem}.png")
    print(f"\n{q}: nearest-exemplar cosine range {lo:.2f}..{hi:.2f}  -> retr_{stem}.png + novel_{stem}.png")
