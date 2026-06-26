"""Tile the vision-probe overlays into one comparison grid per frame:
rows = model/task, columns = input condition. Run after vision_probe.py."""
import glob, os
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont

OUT = "runs/vision_probe"
CONDS = ["full_native", "full_4x", "crop_4x"]
CW, CH = 300, 250          # cell draw box
LABELW, HEADH = 150, 22    # row-label column, column-header row


def font(sz=13):
    try:
        return ImageFont.truetype("arial.ttf", sz)
    except Exception:
        return ImageFont.load_default()


def parse(p):
    model = os.path.basename(os.path.dirname(p))
    parts = os.path.basename(p)[:-4].split("__")
    head = parts[0]
    cond = parts[1] if len(parts) > 1 else "?"
    tag = parts[2] if len(parts) > 2 else ""
    return model, head, cond, tag


byframe = defaultdict(dict)   # head -> {(model,tag): {cond: path}}
for p in glob.glob(OUT + "/*/*.png"):
    if os.path.basename(p).startswith("montage"):
        continue
    m, head, cond, tag = parse(p)
    if cond in CONDS:
        byframe[head].setdefault((m, tag), {})[cond] = p

f = font(13)
fb = font(15)
for head, rowmap in sorted(byframe.items()):
    rows = sorted(rowmap.keys())
    W = LABELW + CW * len(CONDS)
    H = HEADH + CH * len(rows)
    sheet = Image.new("RGB", (W, H), (18, 18, 18))
    dr = ImageDraw.Draw(sheet)
    for ci, cond in enumerate(CONDS):
        dr.text((LABELW + ci * CW + 6, 4), cond, fill=(120, 220, 255), font=fb)
    for ri, key in enumerate(rows):
        y = HEADH + ri * CH
        dr.text((4, y + 6), f"{key[0]}\n{key[1]}", fill=(255, 220, 120), font=f)
        for ci, cond in enumerate(CONDS):
            p = rowmap[key].get(cond)
            if not p:
                continue
            im = Image.open(p).convert("RGB")
            sc = min((CW - 6) / im.width, (CH - 6) / im.height)
            im = im.resize((int(im.width * sc), int(im.height * sc)), Image.NEAREST)
            sheet.paste(im, (LABELW + ci * CW + 3, y + 3))
    out = os.path.join(OUT, f"montage_{head}.png")
    sheet.save(out)
    print("wrote", out, sheet.size, f"({len(rows)} rows)")
