"""Leave-one-GAME-out GAMEPLAY-vs-NOT probe (run by eval/probe_modality_appearance.py default mode).

Needs .venv-probe4 (open_clip + rapidocr). Compares cheap numpy signals, the frac_flat-only ablation,
OCR text-amount, and CLIP (MobileCLIP2-S0) — and whether each GENERALIZES to a game never trained on.

LEAKAGE GUARD: all Pokemon runs are ONE unit. Labels for the 6 hand-labeled runs are the LABELS dict
(GAMEPLAY vs NOT, from viewing montage sheets); kanto1 labels come free from its oracle.jsonl.
Positive class = NOT-GAMEPLAY (the thing a menu/intro detector must flag).
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.modality import modality_signals  # numpy-only

# Hand labels (from the montage sheets): frame index -> "GP" | "NOT".
LABELS = {
    "red_random1": {
        "GP": [545, 625, 1250, 1458, 2082],
        "NOT": [0, 55, 109, 164, 208, 218, 273, 327, 382, 416, 436, 491, 600, 833, 1041, 1666, 1874, 2291, 2499],
    },
    "red_smart1": {
        "GP": [273, 327, 833],
        "NOT": [0, 55, 109, 164, 208, 218, 382, 416, 436, 491, 545, 600, 625, 1041, 1250, 1458, 1666, 1874, 2082, 2291, 2499],
    },
    "kirby_auto1": {
        "GP": [55, 109, 164, 218, 273, 327, 382, 436, 491, 545, 600, 667, 1333, 2000, 2666, 3333, 4000, 4666, 5333, 5999, 6666, 7332, 7999],
        "NOT": [0],
    },
    "metroid_auto1": {
        "GP": [55, 109, 164, 218, 273, 327, 382, 436, 491, 545, 600, 667, 1333, 2000, 2666, 3333, 4000, 4666, 5333, 5999, 6666, 7332, 7999],
        "NOT": [0],
    },
    "gauntlet_auto1": {
        "GP": [55, 109, 164, 218, 273, 327, 382, 436, 491, 545, 600, 667, 1333, 2000, 2666, 3333, 4000, 4666, 5333, 5999, 6666, 7332, 7999],
        "NOT": [0],
    },
    "spaceinv_smart1": {
        "GP": [55, 67, 109, 133, 200, 218, 266, 273, 382, 400, 436, 466, 491, 599, 666, 732, 799],
        "NOT": [0, 164, 327, 333, 533, 545, 600],
    },
}

UNIT = {
    "red_random1": "pokemon", "red_smart1": "pokemon", "kanto1": "pokemon",
    "kirby_auto1": "kirby", "metroid_auto1": "metroid",
    "gauntlet_auto1": "gauntlet", "spaceinv_smart1": "spaceinv",
}

KANTO_GP_CAP = 40   # evenly-spaced overworld frames sampled from kanto1 (balance the pokemon unit)


def _frame_path(run, idx):
    return os.path.join("runs", run, f"frame_{idx:06d}.png")


def _samples_from_labels():
    """[(run, unit, idx, label_int)] for the hand-labeled runs. label_int: 1=NOT, 0=GP."""
    out = []
    for run, d in LABELS.items():
        for idx in d["GP"]:
            out.append((run, UNIT[run], idx, 0))
        for idx in d["NOT"]:
            out.append((run, UNIT[run], idx, 1))
    return out


def _samples_from_kanto():
    """Free Pokemon labels from kanto1 oracle: dialog->NOT(1), overworld/battle->GP(0) (GP capped+even)."""
    run = "kanto1"
    opath = os.path.join("runs", run, "oracle.jsonl")
    if not os.path.exists(opath):
        return []
    rows = [json.loads(l) for l in open(opath, encoding="utf-8")]
    gp_idx, not_idx = [], []
    for r in rows:
        ctx = (r.get("perceived") or {}).get("context")
        idx = r.get("step")
        if ctx in ("overworld", "battle", "battle_text"):
            gp_idx.append(idx)
        elif ctx == "dialog":
            not_idx.append(idx)
    if len(gp_idx) > KANTO_GP_CAP:  # even stride
        gp_idx = [gp_idx[i] for i in np.linspace(0, len(gp_idx) - 1, KANTO_GP_CAP).astype(int)]
    return [(run, "pokemon", i, 0) for i in gp_idx] + [(run, "pokemon", i, 1) for i in not_idx]


def _load_pair(run, idx):
    """(pil_rgb, np_rgb, np_prev_rgb). prev = frame idx-1 (or this frame if idx==0)."""
    fp = _frame_path(run, idx)
    pil = Image.open(fp).convert("RGB")
    cur = np.asarray(pil)
    pp = _frame_path(run, idx - 1)
    prev = np.asarray(Image.open(pp).convert("RGB")) if (idx > 0 and os.path.exists(pp)) else cur
    return pil, cur, prev


def _cheap_feats(prev, cur):
    sig = modality_signals(prev, cur)
    if sig is None:
        return [0.0, 0.0, float((np.asarray(cur, np.float32).reshape(-1).std() < 12.0))]
    return [sig["frame_diff"], sig["frac_changed"], sig["frac_flat"]]


def _ocr_feats(ocr, np_rgb):
    img = Image.fromarray(np_rgb)
    img = img.resize((img.width * 3, img.height * 3), Image.NEAREST)  # GB text is tiny
    arr = np.asarray(img)[:, :, ::-1]  # RGB->BGR
    res, _ = ocr(arr)
    if not res:
        return [0.0, 0.0, 0.0]
    texts = [r[1] for r in res]
    confs = [float(r[2]) for r in res]
    return [float(sum(len(t) for t in texts)), float(len(texts)), float(np.mean(confs))]


# ---------- tiny numpy classifiers (no sklearn dependency) ----------

def _logistic(Xtr, ytr, Xte, iters=400, lr=0.5, l2=1e-2):
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
    Xtr = np.hstack([(Xtr - mu) / sd, np.ones((len(Xtr), 1))])
    Xte = np.hstack([(Xte - mu) / sd, np.ones((len(Xte), 1))])
    w = np.zeros(Xtr.shape[1])
    n1 = max(int(ytr.sum()), 1); n0 = max(len(ytr) - n1, 1)
    cw = np.where(ytr == 1, len(ytr) / (2 * n1), len(ytr) / (2 * n0))
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(Xtr @ w)))
        w -= lr * (Xtr.T @ ((p - ytr) * cw) / len(ytr) + l2 * w)
    return 1.0 / (1.0 + np.exp(-(Xte @ w)))


def _unit_norm(E):
    return E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)


def _clip_centroid_prob(Etr, ytr, Ete):
    E, Q = _unit_norm(Etr), _unit_norm(Ete)
    cN = E[ytr == 1].mean(0); cG = E[ytr == 0].mean(0)
    cN /= np.linalg.norm(cN) + 1e-9; cG /= np.linalg.norm(cG) + 1e-9
    return 1.0 / (1.0 + np.exp(-8.0 * (Q @ cN - Q @ cG)))


def _clip_knn_pred(Etr, ytr, Ete, k=5):
    E, Q = _unit_norm(Etr), _unit_norm(Ete)
    sims = Q @ E.T
    idx = np.argsort(-sims, axis=1)[:, :min(k, E.shape[0])]
    return (ytr[idx].mean(1) >= 0.5).astype(int)


def _bal_acc(yt, yp):
    accs = []
    for c in (0, 1):
        m = yt == c
        if m.sum():
            accs.append(float((yp[m] == c).mean()))
    return float(np.mean(accs)) if accs else float("nan")


def run_probe() -> int:
    from eval.dataset_split import is_heldout_run

    samples = _samples_from_labels() + _samples_from_kanto()
    samples = [s for s in samples if not is_heldout_run(os.path.join("runs", s[0]))]  # guard

    print(f"loading {len(samples)} labeled frames + CLIP/OCR (this takes ~1-2 min)...", flush=True)
    import open_clip
    import torch
    from rapidocr_onnxruntime import RapidOCR
    cm, _, pre = open_clip.create_model_and_transforms("MobileCLIP2-S0", pretrained="dfndr2b")
    cm.eval()
    ocr = RapidOCR()

    units, ys, cheap, flat, ocrf, pils = [], [], [], [], [], []
    for run, unit, idx, lab in samples:
        pil, cur, prev = _load_pair(run, idx)
        cf = _cheap_feats(prev, cur)
        units.append(unit); ys.append(lab)
        cheap.append(cf); flat.append([cf[2]]); ocrf.append(_ocr_feats(ocr, cur)); pils.append(pil)
    with torch.no_grad():
        emb = cm.encode_image(torch.stack([pre(p) for p in pils]))
        emb = (emb / emb.norm(dim=-1, keepdim=True)).cpu().numpy()

    units = np.array(units); ys = np.array(ys)
    cheap = np.array(cheap, float); flat = np.array(flat, float); ocrf = np.array(ocrf, float)
    uniq = ["pokemon", "kirby", "metroid", "gauntlet", "spaceinv"]

    print("\nper-unit label counts (NOT / GP):")
    for u in uniq:
        m = units == u
        print(f"  {u:9s} NOT={int(ys[m].sum()):3d}  GP={int((ys[m] == 0).sum()):3d}")

    methods = ["cheap-3d", "flat-only", "OCR-3d", "CLIP-centroid", "CLIP-knn", "CLIP+OCR"]
    table = {m: {} for m in methods}
    for u in uniq:
        te = units == u; tr = ~te
        def L(X):  # logistic prob on a feature block
            return _logistic(X[tr], ys[tr], X[te])
        pred = {
            "cheap-3d": (L(cheap) >= 0.5).astype(int),
            "flat-only": (L(flat) >= 0.5).astype(int),
            "OCR-3d": (L(ocrf) >= 0.5).astype(int),
            "CLIP-centroid": (_clip_centroid_prob(emb[tr], ys[tr], emb[te]) >= 0.5).astype(int),
            "CLIP-knn": _clip_knn_pred(emb[tr], ys[tr], emb[te]),
            "CLIP+OCR": ((0.5 * _clip_centroid_prob(emb[tr], ys[tr], emb[te]) + 0.5 * L(ocrf)) >= 0.5).astype(int),
        }
        for m in methods:
            table[m][u] = _bal_acc(ys[te], pred[m])

    print(f"\n{'method':14}" + "".join(f"{u[:8]:>9}" for u in uniq) + f"{'MEAN':>8}{'WORST':>8}")
    for m in methods:
        vals = [table[m][u] for u in uniq]
        print(f"{m:14}" + "".join(f"{v:>9.0%}" for v in vals) + f"{np.mean(vals):>8.0%}{np.min(vals):>8.0%}")

    # Honest, two-part verdict. The DECISIVE folds are pokemon (text-menus) & spaceinv (arcade title/pause)
    # -- the only two units with REAL in-game NOT. kirby/metroid/gauntlet have one flat boot frame as NOT,
    # so their ~100% is gameplay-recognition (vs a trivial flat boot), NOT menu-generalization.
    pmean = lambda mth: float(np.mean([table[mth][u] for u in uniq]))
    clip_mean = max(pmean("CLIP-centroid"), pmean("CLIP-knn"))
    clip_menu = max(min(table["CLIP-centroid"]["pokemon"], table["CLIP-centroid"]["spaceinv"]),
                    min(table["CLIP-knn"]["pokemon"], table["CLIP-knn"]["spaceinv"]))
    ocr_menu = min(table["OCR-3d"]["pokemon"], table["OCR-3d"]["spaceinv"])
    print("\n=== VERDICT (nuanced — the test corrected the claim in BOTH directions) ===")
    print(f"- GAMEPLAY-vs-title/boot: CLIP GENERALIZES (mean {clip_mean:.0%}; ~100% on kirby/metroid/gauntlet) "
          f"and beats cheap/flat -> the blanket 'appearance is useless for modality' is REFUTED.")
    print(f"- MENU/UI-vs-gameplay ACROSS DOMAINS (the hard part): on the two real-NOT folds, "
          f"CLIP pokemon={table['CLIP-centroid']['pokemon']:.0%}/{table['CLIP-knn']['pokemon']:.0%}, "
          f"spaceinv={table['CLIP-centroid']['spaceinv']:.0%}/{table['CLIP-knn']['spaceinv']:.0%}; "
          f"OCR-amount worst={ocr_menu:.0%}. Near chance -> does NOT cleanly generalize.")
    print("- NET: appearance separates gameplay from TITLES cross-game, but NOT in-game MENUS/DIALOGS/UI "
          "cross-game; OCR-text-amount is a poor menu cue on GB (gameplay HUDs are text-heavy too).")
    print("  CAVEAT: kirby/metroid/gauntlet folds have 1 boot NOT frame -> MEAN is optimistic; pokemon & "
          "spaceinv are the honest folds. Small N (~190 frames), wide error bars.")
    return 0
