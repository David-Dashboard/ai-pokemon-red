"""One-off: overlay a 16px grid + (col,row) labels to pin the player's screen cell."""
import sys
from PIL import Image, ImageDraw, ImageFont
CELL, OUT = 16, 5
for path in sys.argv[1:]:
    img = Image.open(path).convert("RGB")
    W, H = img.size
    canvas = img.resize((W * OUT, H * OUT), Image.NEAREST)
    dr = ImageDraw.Draw(canvas)
    try:
        f = ImageFont.truetype("arial.ttf", 12)
    except Exception:
        f = ImageFont.load_default()
    for r in range(H // CELL):
        for c in range(W // CELL):
            x0, y0 = c * CELL * OUT, r * CELL * OUT
            dr.rectangle([x0, y0, x0 + CELL * OUT, y0 + CELL * OUT], outline=(0, 255, 0))
            dr.text((x0 + 2, y0 + 1), f"{c},{r}", fill=(255, 255, 0), font=f)
    out = path.rsplit(".", 1)[0] + "_grid.png"
    canvas.save(out)
    print(out)
