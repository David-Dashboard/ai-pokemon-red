"""Compare lightweight image->text captioners vs Florence-2-base (0.23B):
GIT-base (~0.17B plain captioner) and SmolVLM-256M (instruction-following).

    .venv-probe4\\Scripts\\python.exe eval/captioner_compare.py
"""
import time
import traceback
import torch
from PIL import Image

frame = "runs/perception_run/frame_000001.png"
pil = Image.open(frame).convert("RGB")
print(f"frame: {frame}  (ground truth: player, TV/PC, potted plant, cabinet, tiled floor)")


def git():
    from transformers import AutoProcessor, AutoModelForCausalLM
    p = AutoProcessor.from_pretrained("microsoft/git-base-coco")
    m = AutoModelForCausalLM.from_pretrained("microsoft/git-base-coco").eval()
    n = sum(x.numel() for x in m.parameters()) / 1e6
    s = time.time()
    ids = m.generate(pixel_values=p(images=pil, return_tensors="pt").pixel_values, max_length=50)
    cap = p.batch_decode(ids, skip_special_tokens=True)[0]
    return n, time.time() - s, cap


def smol():
    from transformers import AutoProcessor, AutoModelForVision2Seq
    mid = "HuggingFaceTB/SmolVLM-256M-Instruct"
    p = AutoProcessor.from_pretrained(mid)
    m = AutoModelForVision2Seq.from_pretrained(mid, torch_dtype=torch.float32).eval()
    n = sum(x.numel() for x in m.parameters()) / 1e6
    msgs = [{"role": "user", "content": [{"type": "image"},
            {"type": "text", "text": "Describe this video game screenshot. List the characters and objects."}]}]
    prompt = p.apply_chat_template(msgs, add_generation_prompt=True)
    s = time.time()
    inp = p(text=prompt, images=[pil], return_tensors="pt")
    out = m.generate(**inp, max_new_tokens=120)
    cap = p.batch_decode(out, skip_special_tokens=True)[0].split("Assistant:")[-1].strip()
    return n, time.time() - s, cap


for name, fn in [("GIT-base", git), ("SmolVLM-256M", smol)]:
    try:
        n, dt, cap = fn()
        print(f"\n[{name}] {n:.0f}M params, {dt:.1f}s\n  {cap}")
    except Exception:
        print(f"\n[{name}] FAILED: {traceback.format_exc().splitlines()[-1][:170]}")
