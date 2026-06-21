"""Minimal zero-shot CLIP classifier — point it at any image with your own labels.

Run with the probe venv (NOT `uv run`):
    .venv-probe\\Scripts\\python.exe eval/clip_quick.py <image> [label1] [label2] ...

Examples:
    .venv-probe\\Scripts\\python.exe eval/clip_quick.py runs/perception_run/frame_000012.png
    .venv-probe\\Scripts\\python.exe eval/clip_quick.py runs/haiku_eval/frame_000012.png "a battle" "a room" "a menu" "a title screen"
"""
import sys
from PIL import Image
import torch
from transformers import CLIPModel, CLIPProcessor

if len(sys.argv) < 2:
    print(__doc__)
    raise SystemExit(1)

img_path = sys.argv[1]
labels = sys.argv[2:] or [
    "a Pokemon battle between two monsters",
    "a video game screenshot of a person in a room",
    "a video game title screen",
    "a menu screen",
    "a screen of text dialog",
]

mid = "openai/clip-vit-base-patch32"
model = CLIPModel.from_pretrained(mid).eval()
proc = CLIPProcessor.from_pretrained(mid)

img = Image.open(img_path).convert("RGB")
inputs = proc(text=labels, images=img, return_tensors="pt", padding=True)
with torch.no_grad():
    probs = model(**inputs).logits_per_image.softmax(dim=1)[0]

print(f"\n{img_path}")
for lab, p in sorted(zip(labels, probs.tolist()), key=lambda kv: -kv[1]):
    bar = "#" * round(p * 30)
    print(f"  {p:6.1%}  {bar:<30} {lab}")
