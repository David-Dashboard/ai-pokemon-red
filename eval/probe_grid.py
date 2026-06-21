"""Per-cell CLIP probe: tile a frame into sprite-sized cells, upscale each, and
zero-shot-classify EACH cell — turning whole-frame detection into a semantic grid.
Tests David's idea: does isolating+enlarging one sprite per cell recover the
semantics that whole-frame perception loses on tiny 16px sprites?

Run with the probe venv:
    .venv-probe\\Scripts\\python.exe eval/probe_grid.py runs/perception_run/frame_000001.png
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont
import torch
from transformers import CLIPModel, CLIPProcessor

CELL = 16     # sprite-sized cell (GB object = 2x2 8px tiles)
UP = 8        # upscale fed to CLIP (16 -> 128)
OUT = 5       # overlay upscale for the saved image
OFFX = int(sys.argv[2]) if len(sys.argv) > 2 else 0   # optional sub-tile align
OFFY = int(sys.argv[3]) if len(sys.argv) > 3 else 0

# label set MUST include background classes or every floor tile is forced to an object
LABELS = [
    "a blank repeating tiled floor pattern", "a plain wall", "a small cartoon person",
    "a human figure", "a small round ball", "a blue glowing screen",
    "a leafy green plant", "a brown box", "a flight of stairs",
]
SHORT = {LABELS[0]: ".", LABELS[1]: "#", LABELS[2]: "P", LABELS[3]: "N",
         LABELS[4]: "O", LABELS[5]: "TV", LABELS[6]: "PL", LABELS[7]: "T", LABELS[8]: "S"}
COLOR = {LABELS[0]: None, LABELS[1]: (90, 90, 90), LABELS[2]: (255, 60, 60),
         LABELS[3]: (255, 160, 0), LABELS[4]: (0, 230, 120), LABELS[5]: (80, 140, 255),
         LABELS[6]: (60, 220, 60), LABELS[7]: (200, 140, 60), LABELS[8]: (220, 60, 220)}

frame = sys.argv[1]
img = Image.open(frame).convert("RGB")
W, H = img.size
cols, rows = (W - OFFX) // CELL, (H - OFFY) // CELL

cells, coords = [], []
for r in range(rows):
    for c in range(cols):
        x0, y0 = OFFX + c * CELL, OFFY + r * CELL
        cell = img.crop((x0, y0, x0 + CELL, y0 + CELL)).resize((CELL * UP, CELL * UP), Image.NEAREST)
        cells.append(cell)
        coords.append((c, r))

mid = "openai/clip-vit-base-patch32"
model = CLIPModel.from_pretrained(mid).eval()
proc = CLIPProcessor.from_pretrained(mid)
inputs = proc(text=LABELS, images=cells, return_tensors="pt", padding=True)
with torch.no_grad():
    probs = model(**inputs).logits_per_image.softmax(dim=1)  # [ncells, nlabels]

# overlay
canvas = img.resize((W * OUT, H * OUT), Image.NEAREST).convert("RGB")
dr = ImageDraw.Draw(canvas)
try:
    f = ImageFont.truetype("arial.ttf", 11)
except Exception:
    f = ImageFont.load_default()

grid = [["  " for _ in range(cols)] for _ in range(rows)]
for i, (c, r) in enumerate(coords):
    p = probs[i]
    j = int(p.argmax())
    lab, conf = LABELS[j], float(p[j])
    grid[r][c] = SHORT[lab] if conf >= 0.40 else ".."
    col = COLOR[lab]
    if col and conf >= 0.40:   # only mark confident non-floor cells
        x0, y0 = (OFFX + c * CELL) * OUT, (OFFY + r * CELL) * OUT
        dr.rectangle([x0, y0, x0 + CELL * OUT - 1, y0 + CELL * OUT - 1], outline=col, width=2)
        dr.text((x0 + 2, y0 + 1), f"{SHORT[lab]}{conf:.0%}", fill=col, font=f)

os.makedirs("runs/vision_probe", exist_ok=True)
stem = os.path.basename(frame).replace(".png", "")
out = f"runs/vision_probe/grid_{stem}_off{OFFX}-{OFFY}.png"
canvas.save(out)

print(f"\n{frame}  ({cols}x{rows} cells, offset {OFFX},{OFFY})  -> {out}")
print("legend: .=floor #=wall P=player N=npc O=pokeball TV=tv/pc PL=plant T=table S=stairs (>=40%)")
for r in range(rows):
    print("  " + " ".join(f"{grid[r][c]:>2}" for c in range(cols)))
