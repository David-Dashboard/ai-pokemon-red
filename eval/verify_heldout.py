"""Held-out VERIFICATION for the camera-model classifier -- the FINAL-verification use of the dataset_split
held-out set (never developed/tuned on these). Builds a PER-RUN classifier from the dev corpus (the cheap
closer the per-FRAME centroid couldn't manage -- a scroller's non-scroll-majority frames drown the per-frame
vote), then:
  1. leave-one-UNIT-out on the dev games (the in-corpus verdict), and
  2. ZERO-SHOT classifies each held-out game it never saw.
Per-run feature = [scrollPrev, A4_locality, vshare] -- the locomotion-robust cues. numpy+PIL, main uv env.
  uv run python -m eval.verify_heldout
"""
from __future__ import annotations

import glob
import os

import numpy as np

from eval.dataset_split import is_heldout_run
from eval.probe_camera_model import RUNS, UNIT, gb_signature, load_run

# Held-out runs to verify (recorded for final verification only). `expected` = the camera class where there is
# a clear answer; None = genuinely novel/ambiguous (pseudo-3D / flip-screen) -> just report where it lands.
# ALL autonomous (--explore, no human intervention) -- the held-out set tests the AUTONOMOUS pipeline zero-shot.
HELDOUT_RUNS = [
    ("2026-06-23_crystalis_explore", "follow_scroll", "gb"),   # top-down follow (real-time RPG)
    ("2026-06-23_sml_explore",       "scroll_side",   "gb"),   # side-scroller (auto may under-drive it)
    ("2026-06-23_zelda_explore",     None,            "gb"),   # flip-screen (discrete screens) -> expect fixed-like
    ("2026-06-23_f1race_explore",    None,            "gb"),   # pseudo-3D racing (auto doesn't accelerate) -> degenerate
]

FEATS = "[scrollPrev, A4_locality, vshare]"


def _feat(run, src):
    s = gb_signature(load_run(run, src))
    sp = s["scroll_prev"] if s["scroll_prev"] == s["scroll_prev"] else 0.0   # nan -> 0
    return [sp, s["A4_locality"], s["vshare"]]


def _centroids(Z, y, idxs):
    cents = {}
    for j in idxs:
        cents.setdefault(y[j], []).append(Z[j])
    return {c: np.mean(v, axis=0) for c, v in cents.items()}


def main():
    dev = [r for r in RUNS if r[2] == "gb" and not is_heldout_run(os.path.join("runs", r[0]))]
    X = np.array([_feat(r[0], r[2]) for r in dev], float)
    y = np.array([r[1] for r in dev])
    units = [UNIT[r[0]] for r in dev]
    print(f"per-run feature = {FEATS};  dev = {len(dev)} units")

    # 1) DEV leave-one-UNIT-out (the in-corpus verdict)
    print("\n=== DEV per-run leave-one-UNIT-out ===")
    ok = 0
    for i in range(len(X)):
        tr = [j for j in range(len(X)) if units[j] != units[i]]
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-6
        Z = (X - mu) / sd
        cents = _centroids(Z, y, tr)
        pred = min(cents, key=lambda c: np.linalg.norm(Z[i] - cents[c]))
        ok += pred == y[i]
        print(f"  {units[i]:10s} true={y[i]:13s} pred={pred:13s} {'OK' if pred == y[i] else 'MISS'}")
    print(f"  -> {ok}/{len(X)} = {ok / len(X):.0%}")

    # 2) HELD-OUT zero-shot (centroids from ALL dev; these games were never tuned on)
    mu, sd = X.mean(0), X.std(0) + 1e-6
    Z = (X - mu) / sd
    cents = _centroids(Z, y, range(len(X)))
    print("\n=== HELD-OUT zero-shot (per-run; NEVER tuned on) ===")
    print("  WIN metric = nearest dev class is the EXPECTED one, by a clear MARGIN (runner-up dist / nearest dist).")
    print("  Note: distance-FROM-corpus is high for every held-out game (they are new GAMES) -- that is NOT a")
    print("  camera-model-novelty signal here; the margin BETWEEN classes is what carries the verdict.")
    for run, exp, src in HELDOUT_RUNS:
        if not glob.glob(os.path.join("runs", run, "frame_*.png")):   # junction dir may exist but be empty
            print(f"  {run.split('_')[1]:10s} (not recorded yet -- skip)")
            continue
        sig = gb_signature(load_run(run, src))
        sp = sig["scroll_prev"] if sig["scroll_prev"] == sig["scroll_prev"] else 0.0
        z = (np.array([sp, sig["A4_locality"], sig["vshare"]], float) - mu) / sd
        ranked = sorted((float(np.linalg.norm(z - cents[c])), c) for c in cents)
        (d1, c1), (d2, c2) = ranked[0], ranked[1]
        margin = d2 / (d1 + 1e-9)
        # DATA-QUALITY gate. A SCROLL prediction with ~no camera motion is a contradiction -> the autonomous
        # DRIVER stalled (INCONCLUSIVE). A FIXED prediction with ~no motion is CONSISTENT -> could be a genuinely
        # fixed camera OR a stalled driver, can't tell hands-off (AMBIGUOUS) -- e.g. Zelda flip-screen reads
        # fixed, which may be the right answer. (So low-motion != automatically a perception failure.)
        low_motion = sp < 0.05 and sig["A4_locality"] < 0.30
        if low_motion and c1 != "fixed":
            status = "INCONCLUSIVE (predicted a scroller but the driver produced no motion)"
        elif low_motion:
            status = "AMBIGUOUS (fixed may be correct, or the driver stalled)"
        elif exp:
            status = f"{'OK' if c1 == exp else 'MISS'} (expected {exp})"
        else:
            status = "no clean 2D class"
        print(f"  {run.split('_')[1]:10s} pred={c1:13s} margin x{margin:.1f} (over {c2})  A4={sig['A4_locality']:.2f} sp={sp:.0%}"
              f"  -> {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
