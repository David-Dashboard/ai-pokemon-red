"""Recall stage (model-free): which 16x16 cells are NOT background floor?
Class-agnostic proposal — pairs with CLIP (the precision/labeling stage).

Score each cell by how far it is from the median ("typical floor") cell, plus its
colour saturation (sprites are colourful, floor is muted). Flag cells over a
percentile threshold -> proposals. Measure recall on known object cells.

    .venv-probe\\Scripts\\python.exe eval/probe_recall.py
"""
import numpy as np
from PIL import Image, ImageDraw

CELL = 16
FRAMES = {
    "runs/perception_run/frame_000001.png": [(4, 1), (1, 3), (7, 3), (4, 4)],   # tv, cabinet, plant, player
    "runs/perception_run/frame_000019.png": [],
    "runs/percep_bench/frame_000030.png": [],
}


def analyze(path, gt_cells):
    img = np.asarray(Image.open(path).convert("RGB")).astype(float)
    H, W, _ = img.shape
    rows, cols = H // CELL, W // CELL
    cells = np.stack([img[r * CELL:(r + 1) * CELL, c * CELL:(c + 1) * CELL]
                      for r in range(rows) for c in range(cols)])  # [N,16,16,3]
    # Outlier/density recall: objects are RARE, isolated cells; floor AND black
    # margin are both COMMON (many near-identical neighbours). Flag cells whose
    # nearest neighbours are far away (= not part of any large background cluster).
    def norm(x):
        return (x - x.min()) / (np.ptp(x) + 1e-6)
    feats = cells.reshape(len(cells), -1)               # [N, 768]
    D = np.linalg.norm(feats[:, None, :] - feats[None, :, :], axis=2)  # [N,N]
    D.sort(axis=1)
    knn = D[:, 1:6].mean(1)                             # mean dist to 5 nearest -> outlierness
    score = norm(knn).reshape(rows, cols)

    thr = np.percentile(score, 75)        # flag the top quartile as "non-background"
    flagged = score >= thr

    print(f"\n{path}  ({cols}x{rows} cells)  threshold=p75")
    print("  saliency grid (0-9, '##'=flagged):")
    for r in range(rows):
        cellsrow = []
        for c in range(cols):
            d = int(min(9, score[r, c] * 10))
            cellsrow.append("##" if flagged[r, c] else f" {d}")
        print("   " + " ".join(cellsrow))

    if gt_cells:
        hit = sum(flagged[r, c] for c, r in gt_cells)
        print(f"  recall on {len(gt_cells)} known objects: {hit}/{len(gt_cells)} "
              f"({', '.join(f'({c},{r})={'Y' if flagged[r,c] else 'N'}' for c, r in gt_cells)})")
    print(f"  proposals: {int(flagged.sum())}/{rows*cols} cells flagged "
          f"({flagged.sum()/(rows*cols):.0%}) -> that's what CLIP would label")

    # overlay
    OUT = 5
    canvas = Image.open(path).convert("RGB").resize((W * OUT, H * OUT), Image.NEAREST)
    dr = ImageDraw.Draw(canvas, "RGBA")
    for r in range(rows):
        for c in range(cols):
            if flagged[r, c]:
                x0, y0 = c * CELL * OUT, r * CELL * OUT
                dr.rectangle([x0, y0, x0 + CELL * OUT - 1, y0 + CELL * OUT - 1],
                             outline=(0, 230, 120, 255), width=2)
    stem = path.split("/")[-1].replace(".png", "")
    canvas.save(f"runs/vision_probe/recall_{stem}.png")


for path, gt in FRAMES.items():
    analyze(path, gt)
