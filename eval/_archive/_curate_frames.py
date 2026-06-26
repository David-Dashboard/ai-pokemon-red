"""Throwaway: readable 2x montage of the affordance-rich sets so we can hand-pick
ground-truth probe frames (Pokeballs / NPCs / doorways / battle / dialog)."""
from PIL import Image, ImageDraw
import glob, os

dirs = ["runs/perception_run", "runs/haiku_eval"]
items = []
for d in dirs:
    items.extend(sorted(glob.glob(d + "/*.png")))

scale = 2
cols = 5
W, H = 160 * scale, 144 * scale
pad, labelh = 3, 16
rows = (len(items) + cols - 1) // cols
sheet = Image.new("RGB", (cols * (W + pad) + pad, rows * (H + labelh + pad) + pad), (30, 30, 30))
dr = ImageDraw.Draw(sheet)
for i, f in enumerate(items):
    r, c = divmod(i, cols)
    x = pad + c * (W + pad)
    y = pad + r * (H + labelh + pad)
    im = Image.open(f).convert("RGB").resize((W, H), Image.NEAREST)
    sheet.paste(im, (x, y))
    tag = os.path.basename(os.path.dirname(f))[:6] + "/" + os.path.basename(f).replace("frame_", "").replace(".png", "")
    dr.text((x + 2, y + H + 2), tag, fill=(255, 255, 0))

out = "runs/_frame_contact_sheet.png"
sheet.save(out)
print("wrote", out, "with", len(items), "frames", sheet.size)
