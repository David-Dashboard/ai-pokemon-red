"""Make-or-break test for 'layout without walking': can vision read WALKABILITY
(wall vs walkable path), NPCs and exits across a room from ONE frame?

MobileCLIP2-S0 per-cell grid with navigation labels (green=walkable / red=blocked
/ orange=NPC / blue=exit) + Florence layout caption. Color overlay per frame so we
can eyeball wall-vs-walkable accuracy vs the visible truth.

    .venv-probe4\\Scripts\\python.exe eval/probe_walkability.py
"""
import torch
import open_clip
from transformers import AutoProcessor, AutoModelForCausalLM
from PIL import Image, ImageDraw

FRAMES = [
    "runs/perception_run/frame_000006.png",
    "runs/perception_run/frame_000016.png",
    "runs/perception_run/frame_000019.png",
    "runs/percep_bench/frame_000030.png",
]

LABELS = [  # (kind, text-prompt)
    ("walk", "empty tiled floor to walk on"),
    ("walk", "a plain open floor path"),
    ("block", "a wall"),
    ("block", "a table or counter or furniture"),
    ("block", "a television or computer monitor"),
    ("block", "a potted plant"),
    ("block", "a bookshelf or cabinet"),
    ("npc", "a person or character standing"),
    ("exit", "a doorway or staircase"),
]
texts = [t for _, t in LABELS]
kinds = [k for k, _ in LABELS]
COLOR = {"walk": (0, 200, 0), "block": (220, 40, 40), "npc": (255, 150, 0), "exit": (60, 120, 255)}
GLYPH = {"walk": ".", "block": "#", "npc": "N", "exit": "E"}

cm, _, pre = open_clip.create_model_and_transforms("MobileCLIP2-S0", pretrained="dfndr2b")
cm.eval()
tok = open_clip.get_tokenizer("MobileCLIP2-S0")
with torch.no_grad():
    tf = cm.encode_text(tok(texts))
    tf = tf / tf.norm(dim=-1, keepdim=True)

fp = AutoProcessor.from_pretrained("microsoft/Florence-2-base", trust_remote_code=True)
fm = AutoModelForCausalLM.from_pretrained(
    "microsoft/Florence-2-base", trust_remote_code=True, torch_dtype=torch.float32).eval()


def florence(img):
    inp = fp(text="<MORE_DETAILED_CAPTION>", images=img, return_tensors="pt")
    g = fm.generate(input_ids=inp["input_ids"], pixel_values=inp["pixel_values"],
                    max_new_tokens=200, num_beams=1, do_sample=False)
    s = fp.batch_decode(g, skip_special_tokens=False)[0]
    return str(fp.post_process_generation(s, task="<MORE_DETAILED_CAPTION>", image_size=img.size)
               .get("<MORE_DETAILED_CAPTION>", "")).strip()


CELL, UP, OUT = 16, 16, 5
for path in FRAMES:
    img = Image.open(path).convert("RGB")
    W, H = img.size
    cols, rows = W // CELL, H // CELL
    cells = [img.crop((c * CELL, r * CELL, c * CELL + CELL, r * CELL + CELL)).resize((CELL * UP, CELL * UP), Image.NEAREST)
             for r in range(rows) for c in range(cols)]
    with torch.no_grad():
        vf = cm.encode_image(torch.stack([pre(im) for im in cells]))
        vf = vf / vf.norm(dim=-1, keepdim=True)
        probs = (vf @ tf.T).softmax(-1)

    canvas = img.resize((W * OUT, H * OUT), Image.NEAREST).convert("RGB")
    dr = ImageDraw.Draw(canvas)
    grid, idx = [], 0
    for r in range(rows):
        row = []
        for c in range(cols):
            j = int(probs[idx].argmax())
            k = kinds[j]
            idx += 1
            row.append(GLYPH[k])
            dr.rectangle([c * CELL * OUT, r * CELL * OUT, (c + 1) * CELL * OUT - 1, (r + 1) * CELL * OUT - 1],
                         outline=COLOR[k], width=2)
        grid.append(row)
    out = "runs/vision_probe/walk_" + path.split("/")[-1]
    canvas.save(out)
    print(f"\n=== {path} -> {out} ===")
    print("FLORENCE LAYOUT:", florence(img)[:380])
    print("WALKABILITY GRID  (.=walk #=block N=npc E=exit):")
    for row in grid:
        print("  " + " ".join(row))
