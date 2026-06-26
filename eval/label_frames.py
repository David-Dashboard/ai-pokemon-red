"""Hand-label on-screen entities/regions + the frame MODE across game recordings -- a reusable ground set.

Cheap pixel localizers can't isolate the avatar from enemies/animation (eval/probe_avatar_localize). Rather
than label only the avatar, capture what every downstream perception primitive needs scoring against:
  * MODE (per frame): gameplay / menu / dialog / battle / transition / title / other -> the modality detector
    (core/modality.py) ground truth.
  * ENTITIES: avatar (-> track/localize), enemies + NPCs + items (-> entity-via-motion, interaction targets,
    the consequence detector), exits (-> doorways/stairs = navigation targets + room-transition grounding).
    npc = a friendly/neutral character you TALK to (vs enemy = hostile); when unsure which, skip it.
  * REGIONS: text + health boxes ALSO prompt for the READ string (e.g. "8/10", "B 2F") -> the OCR ground
    truth (read_text) for the ADR-002 HUD-grounding gate. Stored as box[4]; blank to skip.
EVERY category is a BOUNDING BOX (uniform; a box subsumes a point -- its centre is the localizer target, its
extent enables IoU scoring). One human pass, many uses. Frames are sampled across the WHOLE run so modes are
VARIED (titles/menus/transitions, not just gameplay) -- and you should label SEVERAL games for variety.

Run locally (needs a display; tkinter+PIL only, no new dep). Per frame:
  * MODE: press one of  g gameplay  m menu  d dialog  c battle  t transition  i title  x other
  * BOX: keys 1..7 pick a category; DRAG a box (press a corner, drag, release) around each thing present.
    A plain click (no drag) drops a small box at that point. Categories: 1 avatar 2 enemy 3 item 4 text
    5 health 6 exit (doorway/stairs) 7 npc (friendly/neutral character).
  * u = undo last in active category   n/-> /space = next   b/<- = prev   q = save+quit
Label ONLY what's present; an empty frame (just set the mode + next) is fine. Saves <run>/frame_labels.json
incrementally (resumable). Boxes are [x0,y0,x1,y1] in original 160x144 px.

  python -m eval.label_frames runs/2026-06-23_cavenoire_explore --n 50
  python -m eval.label_frames "D:\\ai_pokemon_runs\\2026-06-23_kirby_ramplay" --n 50
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import tkinter as tk
from tkinter import simpledialog

import numpy as np
from PIL import Image, ImageTk

_SCALE = 4
_W, _H = 160, 144
# (name, colour). EVERY category is a bounding box now (uniform interaction; box centre = the point if needed).
CATS = [("avatar", "#39FF14"), ("enemy", "#FF3030"), ("item", "#00E5FF"),
        ("text", "#FFE000"), ("health", "#FF40FF"), ("exit", "#FF8C00"), ("npc", "#B469FF")]
# (mode, key). One per frame; the modality-detector ground truth.
MODES = [("gameplay", "g"), ("menu", "m"), ("dialog", "d"), ("battle", "c"),
         ("transition", "t"), ("title", "i"), ("other", "x")]
_COL = {c[0]: c[1] for c in CATS}
_VALUE_CATS = ("text", "health")   # these boxes also carry the READ string (OCR ground truth); appended as box[4]


def _varied_idxs(frames, want):
    """Pick `want` VISUALLY DIVERSE frames (farthest-point sampling on a cheap 8x8 signature) so a menu-heavy
    or static run doesn't yield 50 near-identical frames. Falls back gracefully; pool is capped for speed."""
    n = len(frames)
    if n <= want:
        return list(range(n))
    stride = max(1, n // 800)                       # cap the candidate pool (~<=800 tiny loads) for speed
    cand = list(range(0, n, stride))
    sig = np.stack([np.asarray(Image.open(frames[i]).convert("L").resize((8, 8), Image.BILINEAR), np.float32).ravel()
                    for i in cand])
    picked = [len(cand) // 2]                       # seed mid-run; FPS fills in the most-different frames
    dist = np.full(len(cand), np.inf)
    while len(picked) < min(want, len(cand)):
        dist = np.minimum(dist, np.linalg.norm(sig - sig[picked[-1]], axis=1))
        picked.append(int(dist.argmax()))
    return sorted(cand[p] for p in picked)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", help="recording dir with frame_*.png")
    ap.add_argument("--n", type=int, default=50, help="how many frames to sample (evenly, across the WHOLE run)")
    args = ap.parse_args()

    frames = sorted(glob.glob(os.path.join(args.run, "frame_*.png")))
    if not frames:
        print(f"no frames in {args.run}"); return 1
    idxs = _varied_idxs(frames, args.n)           # diverse frames (not even-spacing) -> varied modes/scenes

    out_path = os.path.join(args.run, "frame_labels.json")
    labels = {}
    if os.path.exists(out_path):
        labels = {int(d["frame"]): d for d in json.load(open(out_path))}
        for d in labels.values():            # migrate older files: backfill any categories added since (e.g. npc)
            d.setdefault("mode", None)
            for c in CATS:
                d.setdefault(c[0], [])
        print(f"resuming: {len(labels)} frames already have records")

    w, h, bar = _W * _SCALE, _H * _SCALE, 44
    root = tk.Tk(); root.title(os.path.basename(args.run))
    canvas = tk.Canvas(root, width=w, height=h + bar); canvas.pack()
    st = {"k": 0, "cat": "avatar", "drag": None, "now": None, "photo": None}

    def px(e):                                    # canvas px -> clamped original px
        return (round(min(max(e.x / _SCALE, 0), _W), 1), round(min(max(e.y / _SCALE, 0), _H), 1))

    def rec():
        i = idxs[st["k"]]
        return labels.setdefault(i, {"frame": i, "mode": None, **{c[0]: [] for c in CATS}})

    def save():
        json.dump([labels[i] for i in sorted(labels)], open(out_path, "w"), indent=0)

    def draw():
        i = idxs[st["k"]]
        img = Image.open(frames[i]).convert("RGB").resize((w, h), Image.NEAREST)
        st["photo"] = ImageTk.PhotoImage(img)
        canvas.delete("all")
        canvas.create_image(0, 0, anchor="nw", image=st["photo"])
        r = labels.get(i, {})
        for name, col in CATS:
            for b in r.get(name, []):
                canvas.create_rectangle(b[0] * _SCALE, b[1] * _SCALE, b[2] * _SCALE, b[3] * _SCALE,
                                        outline=col, width=2)
                if len(b) > 4 and b[4]:                          # show the typed value above text/health boxes
                    canvas.create_text(b[0] * _SCALE + 1, b[1] * _SCALE - 7, anchor="w", fill=col, text=b[4])
        if st["drag"] is not None and st["now"] is not None:    # live preview of the box being dragged
            (x0, y0), (x1, y1) = st["drag"], st["now"]
            canvas.create_rectangle(x0 * _SCALE, y0 * _SCALE, x1 * _SCALE, y1 * _SCALE,
                                    outline=_COL[st["cat"]], width=1, dash=(3, 2))
        canvas.create_rectangle(0, h, w, h + bar, fill="#111", outline="")
        mode = r.get("mode")
        modeleg = " ".join(f"{k}:{m}{'<' if m == mode else ''}" for m, k in MODES)
        catleg = "  ".join(f"{j+1}:{c[0]}{'*' if c[0] == st['cat'] else ''}" for j, c in enumerate(CATS))
        canvas.create_text(6, h + 11, anchor="w", fill="#9fe",
                           text=f"f{i} ({st['k']+1}/{len(idxs)})  MODE={mode or '-':10s}  {modeleg}")
        canvas.create_text(6, h + 32, anchor="w", fill="#eee",
                           text=f"[{st['cat']}]  {catleg}    drag=box  u=undo  n/->=next  b/<-=prev  q=quit")
        root.title(f"{os.path.basename(args.run)}  f{i}  mode={mode or '-'}  cat={st['cat']}")

    def press(e):
        if e.y >= h:
            return
        st["drag"] = px(e); st["now"] = px(e)

    def motion(e):
        if st["drag"] is None:
            return
        st["now"] = px(e); draw()

    def release(e):
        if st["drag"] is None:
            return
        (x0, y0), (x1, y1) = st["drag"], px(e)
        st["drag"] = st["now"] = None
        if abs(x1 - x0) < 3 and abs(y1 - y0) < 3:                # a plain click -> a small box at the point
            x0, y0, x1, y1 = x0 - 4, y0 - 4, x0 + 4, y0 + 4
        box = [round(max(min(x0, x1), 0), 1), round(max(min(y0, y1), 0), 1),
               round(min(max(x0, x1), _W), 1), round(min(max(y0, y1), _H), 1)]
        if st["cat"] in _VALUE_CATS:           # text/health carry the READ value (OCR ground truth for the HUD gate)
            v = simpledialog.askstring("value", f"what does this {st['cat']} read? (e.g. 8/10, B 2F) — blank=skip",
                                       parent=root)
            box.append((v or "").strip())
        rec()[st["cat"]].append(box)
        draw()

    def undo(_):
        if st["drag"] is not None:
            st["drag"] = st["now"] = None
        elif rec()[st["cat"]]:
            rec()[st["cat"]].pop()
        draw()

    def go(step):
        st["drag"] = st["now"] = None; rec()
        st["k"] = max(0, min(len(idxs) - 1, st["k"] + step))
        save(); draw()

    canvas.bind("<Button-1>", press)
    canvas.bind("<B1-Motion>", motion)
    canvas.bind("<ButtonRelease-1>", release)
    for j, c in enumerate(CATS):
        root.bind(str(j + 1), lambda e, nm=c[0]: (st.update(cat=nm, drag=None, now=None), draw()))
    for m, k in MODES:
        root.bind(k, lambda e, nm=m: (rec().update(mode=nm), draw()))
    root.bind("u", undo)
    for key in ("n", "<space>", "<Right>"):
        root.bind(key, lambda e: go(1))
    for key in ("b", "<Left>"):
        root.bind(key, lambda e: go(-1))
    root.bind("q", lambda e: (save(), root.destroy()))
    draw(); root.mainloop()
    boxes = sum(len(v) for r in labels.values() for k, v in r.items() if k not in ("frame", "mode"))
    modes = sum(1 for r in labels.values() if r.get("mode"))
    print(f"saved {len(labels)} frames ({modes} with a mode, {boxes} boxes) -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
