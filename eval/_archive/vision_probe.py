"""Lightweight zero-shot vision probe on Game Boy (160x144) Pokemon frames.

Question (David, 2026-06-21): do off-the-shelf *lightweight* zero-shot vision
models produce anything useful on retro pixel-art sprites, and does the INPUT
FORM matter -- full frame vs grid-crop, native vs nearest-neighbour upscale?

This is a DIAGNOSE-BEFORE-BETTING probe (north star = cheap, off-the-shelf,
generalizable perception). It does NOT wire anything into the agent; it just
runs each model over a small curated, ground-truth-known frame set across the
input-condition matrix and dumps overlays + a markdown report so we can SEE
hits vs misses.

Run with the ISOLATED probe venv (NOT `uv run`, which would re-sync it away):
    .venv-probe\\Scripts\\python.exe eval/vision_probe.py --models clip,owlv2,florence
    .venv-probe\\Scripts\\python.exe eval/vision_probe.py --models moondream
    .venv-probe\\Scripts\\python.exe eval/vision_probe.py --models sonnet   # paid, needs litellm:4001

Models are loaded ONE AT A TIME (CPU RAM bound) and every (model, frame,
condition) call is wrapped -- a failure is recorded, never fatal.
"""
from __future__ import annotations

import argparse
import base64
import gc
import io
import json
import os
import time
import traceback
from dataclasses import dataclass, field, asdict

from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------- #
# Curated frames: ground-truth-known, spanning affordance types.
# roi = (left, top, right, bottom) in native 160x144 px, or None -> center crop.
# --------------------------------------------------------------------------- #
@dataclass
class Frame:
    path: str
    note: str           # what is actually in it (human ground truth)
    roi: tuple | None = None


FRAMES = [
    Frame("runs/perception_run/frame_000001.png",
          "bedroom: player sprite (red), TV/console (blue, top), potted plant (right)"),
    Frame("runs/perception_run/frame_000012.png",
          "interior: dark-haired NPC, table, stairs (top-left), red doormat (bottom)"),
    Frame("runs/perception_run/frame_000016.png",
          "interior: player (red) + dark-haired NPC, table with items, chairs, doormat"),
    Frame("runs/perception_run/frame_000019.png",
          "interior wide: player + NPC, table, chairs, counters, TV"),
    Frame("runs/haiku_eval/frame_000012.png",
          "intro battle demo: two creatures facing off (pink Nidorino / purple Gengar)"),
    Frame("runs/haiku_eval/frame_000016.png",
          "title screen: Charmander + trainer sprite, 'Pokemon Red' logo, copyright text"),
    Frame("runs/percep_bench/frame_000030.png",
          "overworld interior: player sprite, PC/computer, potted plant"),
]

# Open-vocabulary targets (detectors + pointers). Includes game-specific terms
# that are ABSENT in most frames, to observe false-positive behaviour.
TARGETS = ["person", "television", "potted plant", "table", "chair",
           "monster", "lizard", "Pokeball", "doorway", "stairs"]

# CLIP scene-level candidate labels (zero-shot classification needs full phrases).
CLIP_LABELS = [
    "a video game screenshot of a person standing in a room",
    "a video game screenshot of two people in a room",
    "a Pokemon battle between two monsters",
    "a video game title screen with a logo",
    "a screen of copyright text",
    "an empty room with furniture",
    "a person next to a television",
    "a person next to a potted plant",
]

CONDITIONS = ["full_native", "full_2x", "full_4x", "crop_native", "crop_4x"]
CROP_FRAC = 0.70  # center crop keeps the central 70% (drops emulator margins)


# --------------------------------------------------------------------------- #
# Input-condition generation (nearest-neighbour upscale: keep pixels crisp).
# --------------------------------------------------------------------------- #
def make_condition(img: Image.Image, cond: str, roi=None) -> Image.Image:
    img = img.convert("RGB")
    if cond.startswith("crop"):
        if roi is not None:
            base = img.crop(roi)
        else:
            w, h = img.size
            cw, ch = int(w * CROP_FRAC), int(h * CROP_FRAC)
            x0, y0 = (w - cw) // 2, (h - ch) // 2
            base = img.crop((x0, y0, x0 + cw, y0 + ch))
    else:
        base = img
    scale = 4 if cond.endswith("4x") else 2 if cond.endswith("2x") else 1
    if scale != 1:
        base = base.resize((base.width * scale, base.height * scale), Image.NEAREST)
    return base


# --------------------------------------------------------------------------- #
# Result record + overlay rendering.
# --------------------------------------------------------------------------- #
@dataclass
class Result:
    frame: str
    model: str
    condition: str
    task: str = ""
    text: str = ""                       # free-form output (caption / OCR / classify)
    boxes: list = field(default_factory=list)   # [{label, score, box:[x0,y0,x1,y1]}]
    points: list = field(default_factory=list)  # [{label, x, y}]
    latency_s: float = 0.0
    error: str = ""


def _font(sz=12):
    try:
        return ImageFont.truetype("arial.ttf", sz)
    except Exception:
        return ImageFont.load_default()


def render_overlay(img: Image.Image, res: Result, out_path: str):
    """Draw boxes/points on the (already-scaled) image + a caption strip below."""
    canvas = img.convert("RGB").copy()
    dr = ImageDraw.Draw(canvas)
    f = _font(12)
    for b in res.boxes:
        x0, y0, x1, y1 = b["box"]
        dr.rectangle([x0, y0, x1, y1], outline=(255, 40, 40), width=2)
        lab = b["label"] + (f' {b["score"]:.2f}' if b.get("score") is not None else "")
        dr.text((x0 + 1, max(0, y0 - 12)), lab, fill=(255, 255, 0), font=f)
    for p in res.points:
        x, y = p["x"], p["y"]
        dr.ellipse([x - 4, y - 4, x + 4, y + 4], outline=(0, 230, 230), width=2)
        dr.text((x + 5, y), p["label"], fill=(0, 230, 230), font=f)
    # caption strip
    cap = f'[{res.model} | {res.condition} | {res.task}] '
    cap += res.error or (res.text[:300] if res.text else f'{len(res.boxes)} box / {len(res.points)} pt')
    cap = cap.replace("\n", " / ")   # textlength can't measure multiline
    strip_h = 60
    out = Image.new("RGB", (max(canvas.width, 360), canvas.height + strip_h), (20, 20, 20))
    out.paste(canvas, (0, 0))
    drs = ImageDraw.Draw(out)
    # wrap caption
    words, line, yy = cap.split(" "), "", canvas.height + 3
    for w in words:
        if drs.textlength(line + w + " ", font=f) > out.width - 6:
            drs.text((3, yy), line, fill=(220, 220, 220), font=f)
            yy += 14
            line = ""
        line += w + " "
    drs.text((3, yy), line, fill=(220, 220, 220), font=f)
    out.save(out_path)


# --------------------------------------------------------------------------- #
# Model adapters. Each returns list[Result] for one (frame, condition).
# Adapters are classes with .load() / .run(img, frame, cond) / .unload().
# --------------------------------------------------------------------------- #
class ClipAdapter:
    name = "clip"

    def load(self):
        import torch
        from transformers import CLIPModel, CLIPProcessor
        self.torch = torch
        mid = "openai/clip-vit-base-patch32"
        self.model = CLIPModel.from_pretrained(mid)
        self.proc = CLIPProcessor.from_pretrained(mid)
        self.model.eval()

    def run(self, img, frame, cond):
        t0 = time.time()
        inputs = self.proc(text=CLIP_LABELS, images=img, return_tensors="pt", padding=True)
        with self.torch.no_grad():
            logits = self.model(**inputs).logits_per_image.softmax(dim=1)[0]
        ranked = sorted(zip(CLIP_LABELS, logits.tolist()), key=lambda kv: -kv[1])[:3]
        txt = " | ".join(f"{lab} ({p:.2f})" for lab, p in ranked)
        return [Result(frame.path, self.name, cond, task="zero-shot-classify",
                       text=txt, latency_s=time.time() - t0)]

    def unload(self):
        del self.model, self.proc


class Owlv2Adapter:
    name = "owlv2"

    def load(self):
        import torch
        from transformers import Owlv2ForObjectDetection, Owlv2Processor
        self.torch = torch
        mid = "google/owlv2-base-patch16-ensemble"
        self.proc = Owlv2Processor.from_pretrained(mid)
        self.model = Owlv2ForObjectDetection.from_pretrained(mid)
        self.model.eval()

    def run(self, img, frame, cond):
        t0 = time.time()
        inputs = self.proc(text=[TARGETS], images=img, return_tensors="pt")
        with self.torch.no_grad():
            outputs = self.model(**inputs)
        tgt = self.torch.tensor([img.size[::-1]])
        res = self.proc.post_process_grounded_object_detection(
            outputs, target_sizes=tgt, threshold=0.05, text_labels=[TARGETS])[0]
        boxes = []
        for box, score, lab in zip(res["boxes"].tolist(), res["scores"].tolist(),
                                   res["text_labels"]):
            boxes.append({"label": lab, "score": float(score),
                          "box": [round(v) for v in box]})
        boxes = sorted(boxes, key=lambda b: -b["score"])[:8]
        return [Result(frame.path, self.name, cond, task="open-vocab-detect",
                       boxes=boxes, latency_s=time.time() - t0)]

    def unload(self):
        del self.model, self.proc


class FlorenceAdapter:
    name = "florence"

    def load(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor
        self.torch = torch
        mid = "microsoft/Florence-2-base"
        self.proc = AutoProcessor.from_pretrained(mid, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            mid, trust_remote_code=True, torch_dtype=torch.float32)
        self.model.eval()

    def _task(self, img, task_prompt, text_input=None):
        prompt = task_prompt + (text_input or "")
        inputs = self.proc(text=prompt, images=img, return_tensors="pt")
        gen = self.model.generate(input_ids=inputs["input_ids"],
                                  pixel_values=inputs["pixel_values"],
                                  max_new_tokens=256, num_beams=1, do_sample=False)
        txt = self.proc.batch_decode(gen, skip_special_tokens=False)[0]
        return self.proc.post_process_generation(
            txt, task=task_prompt, image_size=(img.width, img.height))

    def run(self, img, frame, cond):
        out = []
        # 1) free-form caption: what does it think it sees?
        t0 = time.time()
        try:
            p = self._task(img, "<MORE_DETAILED_CAPTION>")
            out.append(Result(frame.path, self.name, cond, task="caption",
                              text=str(p.get("<MORE_DETAILED_CAPTION>", p)),
                              latency_s=time.time() - t0))
        except Exception as e:
            out.append(Result(frame.path, self.name, cond, task="caption",
                              error=repr(e)[:200], latency_s=time.time() - t0))
        # 2) open-vocab detection of our targets
        t0 = time.time()
        try:
            p = self._task(img, "<OPEN_VOCABULARY_DETECTION>", ". ".join(TARGETS))
            od = p.get("<OPEN_VOCABULARY_DETECTION>", {})
            boxes = []
            for bb, lab in zip(od.get("bboxes", []), od.get("bboxes_labels", [])):
                boxes.append({"label": lab, "score": None, "box": [round(v) for v in bb]})
            out.append(Result(frame.path, self.name, cond, task="open-vocab-detect",
                              boxes=boxes, latency_s=time.time() - t0))
        except Exception as e:
            out.append(Result(frame.path, self.name, cond, task="open-vocab-detect",
                              error=repr(e)[:200], latency_s=time.time() - t0))
        # 3) OCR (text frames)
        t0 = time.time()
        try:
            p = self._task(img, "<OCR>")
            out.append(Result(frame.path, self.name, cond, task="ocr",
                              text=str(p.get("<OCR>", p)), latency_s=time.time() - t0))
        except Exception as e:
            out.append(Result(frame.path, self.name, cond, task="ocr",
                              error=repr(e)[:200], latency_s=time.time() - t0))
        return out

    def unload(self):
        del self.model, self.proc


class MoondreamAdapter:
    name = "moondream"

    def load(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        mid = "vikhyatk/moondream2"
        # Don't pin a possibly-nonexistent revision; take latest and probe its API.
        self.model = AutoModelForCausalLM.from_pretrained(mid, trust_remote_code=True)
        self.model.eval()
        self.new_api = hasattr(self.model, "caption") and hasattr(self.model, "point")
        if not self.new_api:  # old API needs a tokenizer + encode_image/answer_question
            self.tok = AutoTokenizer.from_pretrained(mid, trust_remote_code=True)

    def run(self, img, frame, cond):
        out = []
        t0 = time.time()
        try:
            if self.new_api:
                cap = self.model.caption(img, length="normal")["caption"]
            else:
                enc = self.model.encode_image(img)
                cap = self.model.answer_question(enc, "Describe this image.", self.tok)
            out.append(Result(frame.path, self.name, cond, task="caption",
                              text=str(cap), latency_s=time.time() - t0))
        except Exception as e:
            out.append(Result(frame.path, self.name, cond, task="caption",
                              error=repr(e)[:200], latency_s=time.time() - t0))
        if not self.new_api:
            return out  # old API has no pointing
        for obj in ("person", "Pokeball", "monster"):
            t0 = time.time()
            try:
                pts = self.model.point(img, obj)["points"]
                pp = [{"label": obj, "x": round(p["x"] * img.width),
                       "y": round(p["y"] * img.height)} for p in pts]
                out.append(Result(frame.path, self.name, cond, task=f"point:{obj}",
                                  points=pp, latency_s=time.time() - t0))
            except Exception as e:
                out.append(Result(frame.path, self.name, cond, task=f"point:{obj}",
                                  error=repr(e)[:200], latency_s=time.time() - t0))
        return out

    def unload(self):
        del self.model


class SonnetAdapter:
    """Reference ceiling via the already-wired litellm endpoint (paid)."""
    name = "sonnet"

    def __init__(self, url, model, token):
        self.url, self.model, self.token = url, model, token

    def load(self):
        import requests
        self.requests = requests

    def run(self, img, frame, cond):
        t0 = time.time()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        q = (f"This is a {img.width}x{img.height} Game Boy screenshot. List every "
             "person, creature, and interactable object (TV, table, plant, Pokeball, "
             "doorway, stairs) you can see, each with an approximate pixel coordinate "
             "(x,y) of its center. Be concise.")
        payload = {"model": self.model, "max_tokens": 400, "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": q},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]}
        try:
            r = self.requests.post(f"{self.url}/v1/chat/completions", json=payload,
                                   headers={"Authorization": f"Bearer {self.token}"},
                                   timeout=120)
            r.raise_for_status()
            txt = r.json()["choices"][0]["message"]["content"]
            return [Result(frame.path, self.name, cond, task="describe+locate",
                           text=txt, latency_s=time.time() - t0)]
        except Exception as e:
            return [Result(frame.path, self.name, cond, task="describe+locate",
                           error=repr(e)[:200], latency_s=time.time() - t0)]

    def unload(self):
        pass


class YoloAdapter:
    """Ultralytics YOLOv8n — closed-vocab COCO detector (person/tv/chair/plant...)."""
    name = "yolov8n"
    weights = "yolov8n.pt"
    open_vocab = False

    def load(self):
        from ultralytics import YOLO
        self.model = YOLO(self.weights)
        if self.open_vocab:
            self.model.set_classes(TARGETS)

    def run(self, img, frame, cond):
        t0 = time.time()
        res = self.model.predict(img, conf=0.05, verbose=False)[0]
        names = res.names
        boxes = []
        for b in res.boxes:
            boxes.append({"label": names[int(b.cls)], "score": float(b.conf),
                          "box": [round(v) for v in b.xyxy[0].tolist()]})
        boxes = sorted(boxes, key=lambda b: -b["score"])[:8]
        task = "open-vocab-detect" if self.open_vocab else "coco-detect"
        return [Result(frame.path, self.name, cond, task=task,
                       boxes=boxes, latency_s=time.time() - t0)]

    def unload(self):
        del self.model


class YoloWorldAdapter(YoloAdapter):
    """Ultralytics YOLO-World — open-vocab (prompt with TARGETS), fast architecture."""
    name = "yolo-world"
    weights = "yolov8s-world.pt"
    open_vocab = True


ADAPTERS = {a.name: a for a in [ClipAdapter, Owlv2Adapter, FlorenceAdapter,
                                MoondreamAdapter, YoloAdapter, YoloWorldAdapter]}


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="clip,owlv2,florence",
                    help="comma list of: clip,owlv2,florence,moondream,sonnet")
    ap.add_argument("--conditions", default=",".join(CONDITIONS))
    ap.add_argument("--frames-limit", type=int, default=0, help="0 = all curated frames")
    ap.add_argument("--out", default="runs/vision_probe")
    ap.add_argument("--vision-url", default="http://localhost:4001")
    ap.add_argument("--vision-model", default="vision-escalation")
    ap.add_argument("--llm-token", default="sk-litellm-local")
    args = ap.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    conds = [c.strip() for c in args.conditions.split(",") if c.strip()]
    frames = FRAMES[: args.frames_limit] if args.frames_limit else FRAMES
    os.makedirs(args.out, exist_ok=True)

    all_results: list[Result] = []
    for mname in models:
        if mname == "sonnet":
            adapter = SonnetAdapter(args.vision_url, args.vision_model, args.llm_token)
        elif mname in ADAPTERS:
            adapter = ADAPTERS[mname]()
        else:
            print(f"!! unknown model {mname}; skipping")
            continue
        print(f"\n=== loading {mname} ===", flush=True)
        try:
            adapter.load()
        except Exception:
            print(f"!! {mname} FAILED TO LOAD:\n{traceback.format_exc()}", flush=True)
            all_results.append(Result("-", mname, "-", error="load-failed: " +
                                      traceback.format_exc().splitlines()[-1][:200]))
            continue
        mdir = os.path.join(args.out, mname)
        os.makedirs(mdir, exist_ok=True)
        for fr in frames:
            if not os.path.exists(fr.path):
                print(f"   (missing {fr.path})", flush=True)
                continue
            base = Image.open(fr.path)
            for cond in conds:
                cimg = make_condition(base, cond, fr.roi)
                try:
                    results = adapter.run(cimg, fr, cond)
                except Exception as e:
                    results = [Result(fr.path, mname, cond, error="run-crash: " + repr(e)[:200])]
                stem = os.path.splitext(os.path.basename(fr.path))[0]
                fdir = os.path.dirname(fr.path).split("/")[-1]
                for k, res in enumerate(results):
                    tag = res.task.replace(":", "-") or str(k)
                    out_png = os.path.join(mdir, f"{fdir}_{stem}__{cond}__{tag}.png")
                    try:
                        render_overlay(cimg, res, out_png)
                    except Exception as e:
                        print(f"   overlay fail {out_png}: {e}", flush=True)
                    all_results.append(res)
                    flag = "ERR " + res.error if res.error else \
                        (res.text[:70] if res.text else f"{len(res.boxes)}box/{len(res.points)}pt")
                    line = (f"   {mname:10} {fdir}/{stem:13} {cond:12} {res.task:18} "
                            f"{res.latency_s:5.1f}s  {flag}")
                    print(line.encode("ascii", "replace").decode(), flush=True)  # cp1252-safe
        try:
            adapter.unload()
        except Exception:
            pass
        del adapter
        gc.collect()

    # merge into any existing results.json so models can be run incrementally
    rpath = os.path.join(args.out, "results.json")
    prior = []
    if os.path.exists(rpath):
        try:
            prior = json.load(open(rpath, encoding="utf-8"))
        except Exception:
            prior = []
    newkeys = {(r.frame, r.model, r.condition, r.task) for r in all_results}
    merged = [p for p in prior
              if (p["frame"], p["model"], p["condition"], p["task"]) not in newkeys]
    merged += [asdict(r) for r in all_results]
    with open(rpath, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    order = ["clip", "owlv2", "yolov8n", "yolo-world", "florence", "moondream", "sonnet"]
    seen = [m for m in order if any(p["model"] == m for p in merged)]
    write_report(args.out, frames, seen, merged)
    print(f"\nDONE. {len(all_results)} new / {len(merged)} total -> {args.out}\\REPORT.md", flush=True)


def write_report(out, frames, models, results):
    lines = ["# Vision probe report\n",
             "Lightweight zero-shot models on 160x144 Game Boy frames, across the "
             "input-condition matrix (full/crop x native/upscale, nearest-neighbour).\n",
             "Overlays are in the per-model subfolders. `text` is truncated here.\n"]
    by = {}
    for r in results:
        by.setdefault((r["frame"], r["model"]), []).append(r)

    def _b(b):
        s = f'{b["score"]:.2f}' if b.get("score") is not None else "?"
        return f'{b["label"]}({s})@{b["box"]}'

    for fr in frames:
        lines.append(f"\n## {fr.path}\n\n> ground truth: {fr.note}\n")
        for m in models:
            rs = by.get((fr.path, m), [])
            if not rs:
                continue
            lines.append(f"\n### {m}\n")
            lines.append("| condition | task | latency | output |")
            lines.append("|---|---|---|---|")
            for r in rs:
                o = ("**ERR** " + r["error"]) if r["error"] else (
                    r["text"].replace("\n", " ")[:160] if r["text"] else
                    ", ".join(_b(b) for b in r["boxes"][:5]) or
                    ", ".join(f'{p["label"]}({p["x"]},{p["y"]})' for p in r["points"][:5]) or "—")
                lines.append(f"| {r['condition']} | {r['task']} | {r['latency_s']:.1f}s | {o} |")
    with open(os.path.join(out, "REPORT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
