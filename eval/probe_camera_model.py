"""Camera-model probe — can cheap, pixels-only motion signals (grounded by the BUTTON log) tell which
CAMERA MODEL a game uses, on a game never tuned on? This is the measure-first step before building a
generalizable odometry/ego-motion estimator (the System-1 "how did I move" sense the agent needs as the
worlds climb 2D -> 3D -> reality).

The four camera classes in the DEV corpus:
  scroll_topdown  red (Pokemon)        camera scrolls under a centered player; D-pad -> global 2D shift
  scroll_side     kirby, metroid       horizontal scroll dominant; D-pad -> mostly-horizontal shift
  fixed           spaceinv, gauntlet   no camera scroll; only a LOCAL sprite moves; global shift ~ 0
  fp3d            vizdoom my_way_home   non-rigid optical flow; turn = uniform column shift, advance = expansion

Per transition (prev -> cur) we compute cheap numpy motion features and the four button-grounded axes:
  A1  no-input    what moves when NO button is pressed (idle animation / auto-scroll baseline)
  A2  sign        does a D-pad press produce a CONSISTENT global camera shift? (coupling, GB only)
  A3  residual    leftover after the best single 2D translation (low = rigid scroll; high = 3D/local)
  A4  locality    is the change GLOBAL (whole frame moves) or LOCAL (one sprite, rest static)?

TIMING (critical — the off-by-one that wrecked the early ViZDoom smoke test):
  GB recorder saves frame_i AFTER applying act_i  -> transition (i-1 -> i) is caused by buttons[i].
  ViZDoom recorder logs pose+buttons BEFORE acting -> transition (i-1 -> i) is caused by buttons[i-1].

Pixels only. RAM/pose is used only as a NON-LEAKING oracle to VALIDATE the 3D signatures, never as a feature.
Run:  uv run python -m eval.probe_camera_model
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

from eval.vizdoom_flow_ceiling import expansion_flow, xcorr_shift_x  # reuse the 3D flow proxies

# (run, camera_class, source). source picks the frame<->button timing (see module docstring).
# NOTE on labels: these are the AS-RUN a-priori labels for the same-data probe. The probe itself found
# one is WRONG -- Gauntlet II is a follow-SCROLLER, not "fixed" (A4=0.86 whole-frame motion vs truly-fixed
# Space Invaders 0.19). Kept as-is to reproduce the original run; the rebuilt-corpus re-run should adopt
# the report's corrected camera-MOTION-type taxonomy {fixed / rigid-2D-scroll / nonrigid-3D-flow}.
# See reports/2026-06-23-camera-model-probe.md.
RUNS = [
    ("red_random1",     "scroll_topdown", "gb"),
    ("red_smart1",      "scroll_topdown", "gb"),
    ("kirby_auto1",     "scroll_side",    "gb"),
    ("metroid_auto1",   "scroll_side",    "gb"),
    ("spaceinv_smart1", "fixed",          "gb"),
    ("gauntlet_auto1",  "fixed",          "gb"),
    ("vizdoom_mywayhome", "fp3d",         "vizdoom"),
]
CLASSES = ["scroll_topdown", "scroll_side", "fixed", "fp3d"]

# Same-GAME runs are ONE unit -> we leave-one-UNIT-out, NOT one-run-out, so a held-out game is never
# "recognized" from a same-game sibling (red_random1/red_smart1 are both Pokemon Red). Mirrors the
# appearance probe's UNIT dict. A class counts as a genuine cross-game test only if >=2 DIFFERENT units
# share it; a class with a single unit is a SINGLETON (no sibling) -> reported as novelty, excluded from
# the cross-game mean.
UNIT = {
    "red_random1": "pokemon", "red_smart1": "pokemon",
    "kirby_auto1": "kirby", "metroid_auto1": "metroid",
    "spaceinv_smart1": "spaceinv", "gauntlet_auto1": "gauntlet",
    "vizdoom_mywayhome": "vizdoom",
}

NW, NH = 128, 112        # normalize every frame to this (grayscale) so GB & ViZDoom are comparable
MAX_SHIFT, STEP = 18, 2  # 2D translation search (pixels on the normalized frame)
CELL = 8                 # locality grid cell (px)
N_SAMPLE = 300           # transitions sampled per run (uniform over the run)
MOVE_EPS = 2.0           # frame_diff above which a transition "moved" (0-255 gray)
DIR_EPS = 2.0            # shift magnitude above which a D-pad press "scrolled"

_GB_DIR = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


# ---------- cheap, pixels-only motion features ----------

def _gray(run, idx, _cache={}):
    key = (run, idx)
    if key not in _cache:
        if len(_cache) > 4000:
            _cache.clear()
        fp = os.path.join("runs", run, f"frame_{idx:06d}.png")
        im = Image.open(fp).convert("L").resize((NW, NH), Image.BILINEAR)
        _cache[key] = np.asarray(im, dtype=np.float32)
    return _cache[key]


def best_shift(a, b):
    """Best integer 2D translation aligning b onto a. Returns (frame_diff, best_diff, dx, dy).
    Generalizes games/pokemon_red/perceiver._best_shift (kept game-agnostic here)."""
    H, W = a.shape
    fd = float(np.abs(a - b).mean())
    best, bdx, bdy = fd, 0, 0
    for dy in range(-MAX_SHIFT, MAX_SHIFT + 1, STEP):
        for dx in range(-MAX_SHIFT, MAX_SHIFT + 1, STEP):
            oa = a[max(0, dy):min(H, H + dy), max(0, dx):min(W, W + dx)]
            ob = b[max(0, -dy):min(H, H - dy), max(0, -dx):min(W, W - dx)]
            if oa.size < 0.4 * H * W:
                continue
            d = float(np.abs(oa - ob).mean())
            if d < best:
                best, bdx, bdy = d, dx, dy
    return fd, best, bdx, bdy


def frac_changed(a, b):
    """Fraction of CELL-sized grid cells whose mean-abs-diff exceeds MOVE_EPS (A4 locality proxy:
    small => a local sprite moved on a static screen; large => the whole frame moved)."""
    H, W = a.shape
    d = np.abs(a - b)
    ny, nx = H // CELL, W // CELL
    d = d[:ny * CELL, :nx * CELL].reshape(ny, CELL, nx, CELL).mean(axis=(1, 3))
    return float((d > MOVE_EPS).mean())


def transition_feats(prev, cur):
    """Button-agnostic motion features for one transition (used by the class classifier)."""
    fd, bd, dx, dy = best_shift(prev, cur)
    resid = bd / (fd + 1e-6)              # A3: low => a rigid 2D translation explains the motion
    return {
        "frame_diff": fd,
        "shift_x": float(dx), "shift_y": float(dy),
        "shift_mag": float(np.hypot(dx, dy)),
        "residual": resid,
        "frac_changed": frac_changed(prev, cur),  # A4
        "expansion": expansion_flow(prev, cur),    # 3D advance
        "flow_x": xcorr_shift_x(prev, cur),        # 3D turn (signed horizontal column shift)
    }


FEAT_KEYS = ["frame_diff", "shift_mag", "abs_sx", "abs_sy", "residual", "frac_changed", "expansion", "abs_flowx"]


def feat_vector(f):
    return [f["frame_diff"], f["shift_mag"], abs(f["shift_x"]), abs(f["shift_y"]),
            f["residual"], f["frac_changed"], f["expansion"], abs(f["flow_x"])]


# ---------- load transitions per run, with the correct per-source timing ----------

def load_run(run, source):
    """Returns list of dicts: {feats, buttons (the CAUSE), prev_row, cur_row}. Samples N_SAMPLE
    transitions uniformly. buttons is the action that CAUSED the prev->cur transition."""
    bpath = os.path.join("runs", run, "buttons.jsonl")
    rows = [json.loads(l) for l in open(bpath, encoding="utf-8")] if os.path.exists(bpath) else None
    n_frames = len([f for f in os.listdir(os.path.join("runs", run)) if f.startswith("frame_")])
    n = min(n_frames, len(rows)) if rows is not None else n_frames
    ks = np.unique(np.linspace(1, n - 1, min(N_SAMPLE, n - 1)).astype(int))
    out = []
    for k in ks:
        prev, cur = _gray(run, k - 1), _gray(run, k)
        if source == "vizdoom":
            if rows is not None and k >= 1:
                # drop episode-reset transitions (huge position jump)
                p0, p1 = rows[k - 1].get("pos"), rows[k].get("pos")
                if p0 and p1 and (abs(p0[0] - p1[0]) + abs(p0[1] - p1[1])) > 60.0:
                    continue
            cause = rows[k - 1].get("buttons", []) if rows is not None else []
            gt = (rows[k - 1], rows[k]) if rows is not None else None
        else:  # gb: frame_k saved AFTER act_k
            cause = rows[k].get("buttons", []) if rows is not None else []
            gt = None
        out.append({"feats": transition_feats(prev, cur), "buttons": cause, "gt": gt})
    return out


# ---------- the four button-grounded signature axes (per game) ----------

def gb_signature(trans):
    """A1/A2/A3/A4 for a GB game. Returns dict of scalar summaries."""
    none = [t for t in trans if not t["buttons"]]
    moved = [t for t in trans if t["feats"]["frame_diff"] > MOVE_EPS]
    # A1: motion with no input
    a1_fd = np.median([t["feats"]["frame_diff"] for t in none]) if none else float("nan")
    a1_sh = np.median([t["feats"]["shift_mag"] for t in none]) if none else float("nan")
    # A2: per-direction shift-consistency (resultant length of unit shift vectors, scrolled presses only)
    res_lens = []
    for d, delta in _GB_DIR.items():
        vs = []
        for t in trans:
            if d in t["buttons"] and t["feats"]["shift_mag"] > DIR_EPS:
                v = np.array([t["feats"]["shift_x"], t["feats"]["shift_y"]], float)
                vs.append(v / (np.linalg.norm(v) + 1e-9))
        if len(vs) >= 5:
            res_lens.append(float(np.linalg.norm(np.mean(vs, axis=0))))
    a2_coupling = float(np.mean(res_lens)) if res_lens else float("nan")
    # vertical vs horizontal scroll share (separates topdown from side-scroll), moving presses only
    sx = np.array([abs(t["feats"]["shift_x"]) for t in moved]) if moved else np.array([0.0])
    sy = np.array([abs(t["feats"]["shift_y"]) for t in moved]) if moved else np.array([0.0])
    vshare = float(sy.sum() / (sx.sum() + sy.sum() + 1e-9))
    # A3 residual + A4 locality on moving transitions
    a3 = np.median([t["feats"]["residual"] for t in moved]) if moved else float("nan")
    a4 = np.median([t["feats"]["frac_changed"] for t in moved]) if moved else float("nan")
    return {"A1_fd": a1_fd, "A1_shift": a1_sh, "A2_coupling": a2_coupling, "vshare": vshare,
            "A3_residual": a3, "A4_locality": a4, "n_none": len(none), "n_moved": len(moved)}


# ---------- ViZDoom ground-truth anchor (validate the 3D signatures, pose = non-leaking oracle) ----------

def vizdoom_anchor(trans):
    L = [t for t in trans if "TURN_LEFT" in t["buttons"] and "TURN_RIGHT" not in t["buttons"]]
    R = [t for t in trans if "TURN_RIGHT" in t["buttons"] and "TURN_LEFT" not in t["buttons"]]
    F = [t for t in trans if "MOVE_FORWARD" in t["buttons"] and "TURN_LEFT" not in t["buttons"]
         and "TURN_RIGHT" not in t["buttons"]]

    def angdelta(t):
        a, b = t["gt"][0]["angle"], t["gt"][1]["angle"]
        return (b - a + 180.0) % 360.0 - 180.0

    def posdelta(t):
        p0, p1 = t["gt"][0]["pos"], t["gt"][1]["pos"]
        return float(np.hypot(p1[0] - p0[0], p1[1] - p0[1]))

    lr = L + R
    ylr = np.array([0] * len(L) + [1] * len(R))          # 0=LEFT 1=RIGHT
    flow = np.array([t["feats"]["flow_x"] for t in lr])
    # In-sample SEPARABILITY, not a held-out accuracy: max() picks whichever sign convention scores higher
    # on this same data, so it is >=50% by construction (a ceiling). The convincing evidence is the gap in
    # the per-class flow_x means (TURN_LEFT vs TURN_RIGHT), reported alongside.
    sign_sep = max((( flow > 0).astype(int) == ylr).mean(),
                   ((flow <= 0).astype(int) == ylr).mean()) if len(lr) else float("nan")
    # forward: advance (gt pos moved) should raise the expansion score
    fmoved = np.array([posdelta(t) for t in F]) if F else np.array([])
    fexp = np.array([t["feats"]["expansion"] for t in F]) if F else np.array([])
    exp_corr = float(np.corrcoef(fmoved, fexp)[0, 1]) if len(fmoved) > 2 else float("nan")
    return {"nL": len(L), "nR": len(R), "nF": len(F),
            "turn_sign_sep": float(sign_sep),
            "gt_turnL_flowx": float(np.mean([t["feats"]["flow_x"] for t in L])) if L else float("nan"),
            "gt_turnR_flowx": float(np.mean([t["feats"]["flow_x"] for t in R])) if R else float("nan"),
            "fwd_expansion_corr": exp_corr}


# ---------- leave-one-UNIT(game)-out class separability (nearest standardized class centroid) ----------

def logo_separability(per_run):
    """Hold out one GAME (unit) at a time -- ALL its runs go to test, none to train -- so a class with a
    single game (topdown=pokemon, 3d=vizdoom) is a true SINGLETON (no sibling to memorize from) and only
    classes spanning >=2 DIFFERENT games (side, fixed) count as genuine cross-game tests."""
    runs = [r[0] for r in RUNS]
    cls = {r[0]: r[1] for r in RUNS}
    unit = {r[0]: UNIT[r[0]] for r in RUNS}
    X = {g: np.array([feat_vector(t["feats"]) for t in per_run[g]], float) for g in runs}
    units = sorted(set(unit.values()))
    unit_cls = {unit[r]: cls[r] for r in runs}                  # each unit's runs share a class here
    cls_units = {c: sum(1 for u in unit_cls if unit_cls[u] == c) for c in unit_cls.values()}
    rows = []  # (unit, true_cls, pred_cls, novelty_ratio, is_singleton, acc)
    confusion = {c: {c2: 0 for c2 in CLASSES} for c in CLASSES}
    for held_u in units:
        tr_runs = [r for r in runs if unit[r] != held_u]       # NO same-game run leaks into train
        te_runs = [r for r in runs if unit[r] == held_u]
        Xtr = np.vstack([X[r] for r in tr_runs])
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
        cents = {}
        for r in tr_runs:
            cents.setdefault(cls[r], []).append(((X[r] - mu) / sd).mean(0))
        for c in cents:
            cents[c] = np.mean(cents[c], axis=0)
        # typical within-train per-point distance to own-class centroid (for the novelty ratio)
        typ = np.median([np.linalg.norm(z - cents[cls[r]]) for r in tr_runs
                         for z in (X[r] - mu) / sd])
        Zh = np.vstack([(X[r] - mu) / sd for r in te_runs])
        cnames = list(cents.keys())
        d = np.stack([np.linalg.norm(Zh - cents[c], axis=1) for c in cnames], axis=1)
        pred = [cnames[i] for i in d.argmin(1)]
        true_c = unit_cls[held_u]
        is_singleton = cls_units[true_c] == 1
        vals, cnts = np.unique(pred, return_counts=True)
        pred_c = vals[cnts.argmax()]
        novelty = float(np.median(d.min(1)) / (typ + 1e-9))
        for p in pred:
            confusion[true_c][p] += 1
        rows.append((held_u, true_c, pred_c, novelty, is_singleton,
                     float((np.array(pred) == true_c).mean())))
    return rows, confusion


def main():
    from eval.dataset_split import is_heldout_run
    runs = [r for r in RUNS if not is_heldout_run(os.path.join("runs", r[0]))]
    skipped = [r[0] for r in RUNS if r not in runs]
    if skipped:
        print(f"leakage guard: skipped held-out runs {skipped}")

    print(f"loading {len(runs)} runs x ~{N_SAMPLE} transitions (cheap numpy; ~1 min)...", flush=True)
    per_run = {}
    for run, cclass, source in runs:
        per_run[run] = load_run(run, source)
        print(f"  {run:18s} ({cclass:14s}) n={len(per_run[run])}", flush=True)

    # ---- per-game button-grounded signature table (GB) ----
    print("\n=== PER-GAME CAMERA SIGNATURE (button-grounded) ===")
    print(f"{'game':18}{'class':15}{'A1_fd':>7}{'A1_sh':>7}{'A2_coup':>8}{'vshare':>8}"
          f"{'A3_res':>8}{'A4_loc':>8}")
    for run, cclass, source in runs:
        if source != "gb":
            continue
        s = gb_signature(per_run[run])
        print(f"{run:18}{cclass:15}{s['A1_fd']:>7.1f}{s['A1_shift']:>7.1f}{s['A2_coupling']:>8.2f}"
              f"{s['vshare']:>8.2f}{s['A3_residual']:>8.2f}{s['A4_locality']:>8.2f}")
    print("  A1_fd/A1_sh = motion with NO button (idle).  A2_coup = D-pad->shift consistency (0..1, hi=scroll).")
    print("  vshare = vertical share of scroll (hi=topdown, lo=side).  A3_res = best-2D-translation residual")
    print("  (lo=rigid scroll).  A4_loc = fraction of frame that moved (hi=global/scroll, lo=local/fixed).")

    # ---- ViZDoom 3D anchor (pose oracle) ----
    for run, cclass, source in runs:
        if source != "vizdoom":
            continue
        a = vizdoom_anchor(per_run[run])
        print(f"\n=== 3D ANCHOR ({run}, pose = non-leaking oracle) ===")
        print(f"  turns: L n={a['nL']} flow_x={a['gt_turnL_flowx']:+.2f}  "
              f"R n={a['nR']} flow_x={a['gt_turnR_flowx']:+.2f}  "
              f"-> L/R sign SEPARABILITY={a['turn_sign_sep']:.0%} (in-sample, >=50% by construction; "
              f"the flow_x mean gap is the real evidence)")
        print(f"  forward: n={a['nF']}  corr(gt advance, expansion-flow)={a['fwd_expansion_corr']:+.2f}")
        print("  (frame-diff alone CANNOT tell rotation from translation; column-shift sign + expansion can.)")

    # ---- leave-one-UNIT(game)-out class separability ----
    rows, confusion = logo_separability(per_run)
    print("\n=== LEAVE-ONE-UNIT(GAME)-OUT CAMERA-CLASS SEPARABILITY (nearest standardized centroid) ===")
    print("(same-game runs = ONE unit: pokemon = red_random1 + red_smart1, so topdown has no cross-game sibling)")
    print(f"{'held-out unit':18}{'true class':15}{'predicted':15}{'per-frame acc':>14}{'note':>22}")
    sib_accs = []
    for held, true_c, pred_c, novelty, singleton, acc in rows:
        note = f"SINGLETON novelty x{novelty:.1f}" if singleton else ("OK" if pred_c == true_c else "MISS")
        if not singleton:
            sib_accs.append(acc)
        print(f"{held:18}{true_c:15}{pred_c:15}{acc:>13.0%} {note:>21}")
    print("\nconfusion (true rows -> predicted cols, per-frame):")
    print(f"{'':16}" + "".join(f"{c[:9]:>11}" for c in CLASSES))
    for c in CLASSES:
        tot = sum(confusion[c].values()) or 1
        print(f"{c:16}" + "".join(f"{confusion[c][c2] / tot:>11.0%}" for c2 in CLASSES))

    sib_mean = float(np.mean(sib_accs)) if sib_accs else float("nan")
    print("\n=== VERDICT ===")
    print(f"- CROSS-GAME class recognition (classes WITH a sibling: side kirby<->metroid, fixed "
          f"spaceinv<->gauntlet): mean per-frame acc {sib_mean:.0%} on games held out entirely.")
    print("- SINGLETON classes (topdown=red, 3d=vizdoom) have no same-class training game, so LOGO must "
          "MISS them by construction; the honest signal is the novelty ratio (held-out lands FAR from "
          "every known class = correctly flagged as a NEW camera model, not confidently mis-assigned).")
    print("- The per-game signature table is the descriptive core: A2/vshare/A3/A4 should cluster by class.")
    print("- 3D anchor confirms the ego-motion signatures are REAL (turn = column-shift sign; advance = "
          "expansion), grounded against the ViZDoom pose oracle -- not coincidence.")
    print(f"  Honest scope: {len(runs)} runs, 1-2 games/class, ~{N_SAMPLE} transitions each; frames "
          "normalized to 128x112 (ViZDoom aspect distorted). Decisive on THESE, not the held-out four.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
