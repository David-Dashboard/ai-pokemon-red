"""Compare lightweight OCR (RapidOCR, ~8MB ONNX) vs Florence-2 (0.23B VLM) on
GB text: the title-screen font and the in-game gen1 textbox font.

    .venv-probe4\\Scripts\\python.exe eval/ocr_compare.py
"""
import time
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR
import torch
from transformers import AutoProcessor, AutoModelForCausalLM

FRAMES = [
    ("title (logo font)", "runs/haiku_eval/frame_000016.png"),
    ("gen1 dialog", "runs/modes/242_ui_candidate_dialog.png"),
    ("gen1 dialog 2", "runs/modes/260_ui_candidate_dialog.png"),
]

ocr = RapidOCR()


def rapid(pil, up):
    im = pil.convert("RGB")
    if up > 1:
        im = im.resize((im.width * up, im.height * up), Image.NEAREST)
    arr = np.array(im)[:, :, ::-1]  # RGB->BGR
    t = time.time()
    res, _ = ocr(arr)
    dt = time.time() - t
    txt = " | ".join(r[1] for r in res) if res else "(none)"
    return txt, dt


fp = AutoProcessor.from_pretrained("microsoft/Florence-2-base", trust_remote_code=True)
fm = AutoModelForCausalLM.from_pretrained(
    "microsoft/Florence-2-base", trust_remote_code=True, torch_dtype=torch.float32).eval()


def florence_ocr(pil):
    inp = fp(text="<OCR>", images=pil.convert("RGB"), return_tensors="pt")
    t = time.time()
    g = fm.generate(input_ids=inp["input_ids"], pixel_values=inp["pixel_values"],
                    max_new_tokens=128, num_beams=1, do_sample=False)
    dt = time.time() - t
    s = fp.batch_decode(g, skip_special_tokens=False)[0]
    return str(fp.post_process_generation(s, task="<OCR>", image_size=pil.size).get("<OCR>", "")), dt


for name, path in FRAMES:
    pil = Image.open(path)
    print(f"\n=== {name}: {path} ===")
    for up in (1, 3):
        txt, dt = rapid(pil, up)
        print(f"  RapidOCR {up}x : {dt:5.2f}s  {txt!r}")
    txt, dt = florence_ocr(pil)
    print(f"  Florence    : {dt:5.2f}s  {txt!r}")
