"""Combined perception prototype (David's design):
  whole-image -> descriptive TEXT  (Florence-2: caption + OCR)
  + CLIP grid  -> spatial OBJECT MAP (MobileCLIP2-S0 per-cell classification)

Produces the kind of unified output the agent could consume: a textual scene
summary plus a coordinate-tagged object grid. Run with the py3.12 venv:

    .venv-probe4\\Scripts\\python.exe eval/probe_pipeline.py runs/perception_run/frame_000001.png
"""
import sys
import torch
import open_clip
from transformers import AutoProcessor, AutoModelForCausalLM
from PIL import Image, ImageDraw, ImageFont

frame = sys.argv[1] if len(sys.argv) > 1 else "runs/perception_run/frame_000001.png"
img = Image.open(frame).convert("RGB")
W, H = img.size

# ---------- whole image -> descriptive text (Florence-2) ----------
fp = AutoProcessor.from_pretrained("microsoft/Florence-2-base", trust_remote_code=True)
fm = AutoModelForCausalLM.from_pretrained(
    "microsoft/Florence-2-base", trust_remote_code=True, torch_dtype=torch.float32).eval()


def florence(task):
    inp = fp(text=task, images=img, return_tensors="pt")
    g = fm.generate(input_ids=inp["input_ids"], pixel_values=inp["pixel_values"],
                    max_new_tokens=256, num_beams=1, do_sample=False)
    t = fp.batch_decode(g, skip_special_tokens=False)[0]
    return fp.post_process_generation(t, task=task, image_size=(W, H))


caption = str(florence("<MORE_DETAILED_CAPTION>").get("<MORE_DETAILED_CAPTION>", "")).strip()
ocr = str(florence("<OCR>").get("<OCR>", "")).strip()

# ---------- CLIP grid -> spatial object map (MobileCLIP2-S0) ----------
CELL, UP = 16, 16
LABELS = ["a blank repeating tiled floor pattern", "a plain stone wall",
          "a small cartoon person or character", "a small round ball",
          "a glowing television or computer screen", "a leafy green potted plant",
          "a wooden box or cabinet", "a staircase"]
KEY = ["floor", "wall", "person", "ball", "screen", "plant", "furniture", "stairs"]
cols, rows = W // CELL, H // CELL

cm, _, pre = open_clip.create_model_and_transforms("MobileCLIP2-S0", pretrained="dfndr2b")
tok = open_clip.get_tokenizer("MobileCLIP2-S0")
cm.eval()
with torch.no_grad():
    tf = cm.encode_text(tok(LABELS))
    tf = tf / tf.norm(dim=-1, keepdim=True)

cells, coords = [], []
for r in range(rows):
    for c in range(cols):
        x0, y0 = c * CELL, r * CELL
        cells.append(img.crop((x0, y0, x0 + CELL, y0 + CELL)).resize((CELL * UP, CELL * UP), Image.NEAREST))
        coords.append((c, r))
with torch.no_grad():
    x = torch.stack([pre(im) for im in cells])
    vf = cm.encode_image(x)
    vf = vf / vf.norm(dim=-1, keepdim=True)
    probs = (vf @ tf.T).softmax(-1)

objects = []
for i, (c, r) in enumerate(coords):
    j = int(probs[i].argmax())
    if KEY[j] not in ("floor", "wall"):
        objects.append((KEY[j], c, r, float(probs[i][j])))

# ---------- output ----------
print(f"\n=== PERCEPTION OUTPUT for {frame} ===")
print(f"SCENE (Florence caption): {caption}")
print(f"ON-SCREEN TEXT (Florence OCR): {ocr or '(none)'}")
print(f"OBJECT GRID (MobileCLIP2-S0, cell=16px):")
for k, c, r, p in objects:
    print(f"   {k:9} at cell ({c},{r})  ~px({c*CELL+8},{r*CELL+8})")

OUT = 5
canvas = img.resize((W * OUT, H * OUT), Image.NEAREST).convert("RGB")
dr = ImageDraw.Draw(canvas)
try:
    f = ImageFont.truetype("arial.ttf", 13)
except Exception:
    f = ImageFont.load_default()
for k, c, r, p in objects:
    x0, y0 = c * CELL * OUT, r * CELL * OUT
    dr.rectangle([x0, y0, x0 + CELL * OUT - 1, y0 + CELL * OUT - 1], outline=(0, 230, 120), width=2)
    dr.text((x0 + 2, y0 + 1), f"{k}", fill=(0, 230, 120), font=f)
stem = frame.split("/")[-1].replace(".png", "")
out = f"runs/vision_probe/pipeline_{stem}.png"
canvas.save(out)
print(f"-> overlay {out}")
