"""Local vision service — a world-agnostic perception sidecar (cf. aria/litellm).

Exposes cheap, off-the-shelf, screen-only perception over HTTP so the light
world-interface repo never imports torch. Runs in its own py3.12 env (which has
transformers 4.x, open_clip, rapidocr) — sidestepping the transformers 4-vs-5
conflict and keeping ai-pokemon-red's deps to `requests`.

    .venv-probe4\\Scripts\\python.exe vision_service.py            # serves :4002

Endpoints (POST JSON; image as {"image_path": ...} on the same host, or {"image_b64": ...}):
  /health  -> {ok, loaded}
  /ocr     {region?:[x0,y0,x1,y1], upscale?:int}        -> {text, lines}
  /caption {with_ocr?:bool}                              -> {caption, ocr}
  /grid    {labels:[...], cell?:16, upscale?:8,
            background?:[...]}                           -> {cols, rows, cells:[{x,y,label,score}], objects:[...]}

Models load LAZILY on first use of each endpoint (so startup + /health are instant).
All CPU. Nothing here is game-specific — labels/cell-size/regions come from the caller.
"""
import base64
import io
import time

from flask import Flask, jsonify, request
from PIL import Image

app = Flask(__name__)

_M = {"clip": None, "florence": None, "ocr": None}  # lazy singletons


# --------------------------------------------------------------------------- #
def _load_image(payload):
    if payload.get("image_path"):
        return Image.open(payload["image_path"]).convert("RGB")
    if payload.get("image_b64"):
        return Image.open(io.BytesIO(base64.b64decode(payload["image_b64"]))).convert("RGB")
    raise ValueError("need image_path or image_b64")


def _clip():
    if _M["clip"] is None:
        import torch
        import open_clip
        model, _, pre = open_clip.create_model_and_transforms("MobileCLIP2-S0", pretrained="dfndr2b")
        model.eval()
        _M["clip"] = (torch, open_clip, model, pre, open_clip.get_tokenizer("MobileCLIP2-S0"))
    return _M["clip"]


def _florence():
    if _M["florence"] is None:
        import torch
        from transformers import AutoProcessor, AutoModelForCausalLM
        proc = AutoProcessor.from_pretrained("microsoft/Florence-2-base", trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            "microsoft/Florence-2-base", trust_remote_code=True, torch_dtype=torch.float32).eval()
        _M["florence"] = (torch, proc, model)
    return _M["florence"]


def _ocr_engine():
    if _M["ocr"] is None:
        from rapidocr_onnxruntime import RapidOCR
        _M["ocr"] = RapidOCR()
    return _M["ocr"]


# --------------------------------------------------------------------------- #
@app.route("/health", methods=["GET", "POST"])
def health():
    return jsonify(ok=True, loaded={k: v is not None for k, v in _M.items()})


@app.post("/ocr")
def ocr():
    import numpy as np
    p = request.get_json(force=True)
    img = _load_image(p)
    region = p.get("region")
    if region:
        img = img.crop(tuple(region))
    up = int(p.get("upscale", 1))
    if up > 1:
        img = img.resize((img.width * up, img.height * up), Image.NEAREST)
    t0 = time.time()
    res, _ = _ocr_engine()(np.array(img)[:, :, ::-1])  # RGB->BGR
    lines = [r[1] for r in res] if res else []
    return jsonify(text=" ".join(lines), lines=lines, latency_s=round(time.time() - t0, 3))


@app.post("/caption")
def caption():
    torch, proc, model = _florence()
    p = request.get_json(force=True)
    img = _load_image(p)

    def run(task):
        inp = proc(text=task, images=img, return_tensors="pt")
        g = model.generate(input_ids=inp["input_ids"], pixel_values=inp["pixel_values"],
                           max_new_tokens=256, num_beams=1, do_sample=False)
        s = proc.batch_decode(g, skip_special_tokens=False)[0]
        return str(proc.post_process_generation(s, task=task, image_size=img.size).get(task, "")).strip()

    t0 = time.time()
    cap = run("<MORE_DETAILED_CAPTION>")
    oc = run("<OCR>") if p.get("with_ocr") else ""
    return jsonify(caption=cap, ocr=oc, latency_s=round(time.time() - t0, 3))


@app.post("/grid")
def grid():
    torch, open_clip, model, pre, tok = _clip()
    p = request.get_json(force=True)
    img = _load_image(p)
    labels = p["labels"]
    cell = int(p.get("cell", 16))
    up = int(p.get("upscale", 8))
    background = set(p.get("background", []))
    W, H = img.size
    cols, rows = W // cell, H // cell

    cells_img, coords = [], []
    for r in range(rows):
        for c in range(cols):
            x0, y0 = c * cell, r * cell
            crop = img.crop((x0, y0, x0 + cell, y0 + cell)).resize((cell * up, cell * up), Image.NEAREST)
            cells_img.append(crop)
            coords.append((c, r))

    t0 = time.time()
    with torch.no_grad():
        tf = model.encode_text(tok(labels))
        tf = tf / tf.norm(dim=-1, keepdim=True)
        vf = model.encode_image(torch.stack([pre(im) for im in cells_img]))
        vf = vf / vf.norm(dim=-1, keepdim=True)
        probs = (vf @ tf.T).softmax(-1)

    out_cells, objects = [], []
    for i, (c, r) in enumerate(coords):
        j = int(probs[i].argmax())
        rec = {"x": c, "y": r, "label": labels[j], "score": round(float(probs[i][j]), 3)}
        out_cells.append(rec)
        if labels[j] not in background:
            objects.append(rec)
    return jsonify(cols=cols, rows=rows, cells=out_cells, objects=objects,
                   latency_s=round(time.time() - t0, 3))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    print(f"vision_service on http://{a.host}:{a.port}  (models load lazily)", flush=True)
    app.run(host=a.host, port=a.port, threaded=False)
