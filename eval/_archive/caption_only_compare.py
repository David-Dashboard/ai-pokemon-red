"""Pure captioners (caption-only, unlike multi-task Florence): BLIP + CoCa.
Compared on the bedroom frame and the Oak's-lab frame (with the Pokeball table).

    .venv-probe4\\Scripts\\python.exe eval/caption_only_compare.py
"""
import time
import traceback
import torch
import open_clip
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration

FRAMES = [
    ("bedroom", "runs/perception_run/frame_000001.png"),
    ("oak-lab+balls", "runs/modes/242_ui_candidate_dialog.png"),
]
imgs = [(n, Image.open(p).convert("RGB")) for n, p in FRAMES]


def blip(mid):
    p = BlipProcessor.from_pretrained(mid)
    m = BlipForConditionalGeneration.from_pretrained(mid).eval()
    n = sum(x.numel() for x in m.parameters()) / 1e6
    out = {}
    for name, im in imgs:
        s = time.time()
        ids = m.generate(**p(im, return_tensors="pt"), max_new_tokens=40)
        out[name] = (p.decode(ids[0], skip_special_tokens=True), time.time() - s)
    return n, out


def coca():
    # pick a CoCa caption checkpoint
    tag = next((p for (mm, p) in open_clip.list_pretrained()
                if mm == "coca_ViT-B-32" and "mscoco" in p), None) or "mscoco_finetuned_laion2b_s13b_b90k"
    model, _, tf = open_clip.create_model_and_transforms("coca_ViT-B-32", pretrained=tag)
    model.eval()
    n = sum(x.numel() for x in model.parameters()) / 1e6
    out = {}
    for name, im in imgs:
        s = time.time()
        with torch.no_grad():
            gen = model.generate(tf(im).unsqueeze(0))
        txt = open_clip.decode(gen[0]).split("<end_of_text>")[0].replace("<start_of_text>", "").strip()
        out[name] = (txt, time.time() - s)
    return n, out


for label, fn in [("BLIP-base", lambda: blip("Salesforce/blip-image-captioning-base")),
                  ("BLIP-large", lambda: blip("Salesforce/blip-image-captioning-large")),
                  ("CoCa-ViT-B-32", coca)]:
    try:
        n, out = fn()
        print(f"\n[{label}] {n:.0f}M params")
        for name, (cap, dt) in out.items():
            print(f"   {name:14} ({dt:4.1f}s): {cap}")
    except Exception:
        print(f"\n[{label}] FAILED: {traceback.format_exc().splitlines()[-1][:170]}")
