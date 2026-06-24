"""Phantom-move probe (measure-first, for the false-MOVE asymmetry fix).

The foreground move signal (best_diff >= _FG_MOVE) trusts a move on ONE frame; idle animation pushes the
residual over threshold while the player is pinned at a wall, so the pose dead-reckons into phantom cells
(closed-loop: corridor 65/70 phantom). The earlier probe showed per-step residual magnitude CANNOT
separate real from phantom (they invert/interleave across runs). This tests a STRUCTURAL signal instead:
WINDOWED VISUAL DISPLACEMENT -- does the screen K steps ago differ from now? Real travel keeps changing the
view; a stuck flicker-loop returns to the same view, so displacement_K collapses even though per-step
residual stays high. RAM is the oracle (label only), never an input.

  uv run python -m eval.probe_phantom_move
"""
from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image

_DIRS = ("up", "down", "left", "right")
_NW, _NH = 128, 112


def _gray(p):
    return np.asarray(Image.open(p).convert("L").resize((_NW, _NH), Image.BILINEAR), np.float32)


def _wrap(d):
    return ((d + 128) % 256) - 128


def _dir(buttons):
    toks = [b for b in (buttons or []) if b in _DIRS]
    return toks[-1] if toks else None


def _auc(pos, neg):
    if not pos or not neg:
        return None
    a = np.array(pos)[:, None]; b = np.array(neg)[None, :]
    return float(((a > b).sum() + 0.5 * (a == b).sum()) / (a.size * b.size))


_W_MED = 6   # temporal-median window: flicker animates and averages out; the static wall/scene survives


def _score(name, steps):
    """steps[i] = (commanded_dir or None, moved_bool or None, frame_path). Consecutive = a play sequence."""
    cache = {}
    def g(p):
        if p not in cache:
            cache[p] = _gray(p) if os.path.exists(p) else None
        return cache[p]
    real = {"K3": [], "median": []}
    stuck = {"K3": [], "median": []}
    n_real = n_stuck = 0
    for i, (d, moved, fp) in enumerate(steps):
        if d is None or moved is None:
            continue
        cur = g(fp)
        if cur is None:
            continue
        bucket = real if moved else stuck
        if moved: n_real += 1
        else: n_stuck += 1
        if i - 3 >= 0 and (p3 := g(steps[i - 3][2])) is not None:
            bucket["K3"].append(float(np.abs(cur - p3).mean()))
        # displacement from the temporal MEDIAN of the prior W frames (flicker-robust background model)
        hist = [g(steps[j][2]) for j in range(max(0, i - _W_MED), i)]
        hist = [h for h in hist if h is not None]
        if len(hist) >= 3:
            med = np.median(np.stack(hist), axis=0)
            bucket["median"].append(float(np.abs(cur - med).mean()))
    print(f"  {name:14s} real-move steps={n_real:4d}  stuck steps={n_stuck:4d}")
    for sig in ("K3", "median"):
        rr, ss = real[sig], stuck[sig]
        if not rr or not ss:
            print(f"    {sig}: (insufficient)"); continue
        # best single-threshold balanced accuracy over a sweep
        thrs = sorted(set(np.round(rr + ss, 1)))
        best = max(((np.mean([v >= t for v in rr]) + np.mean([v < t for v in ss])) / 2, t) for t in thrs)
        print(f"    {sig:7s}: REAL med={np.median(rr):5.1f}  STUCK med={np.median(ss):5.1f}  "
              f"AUC={_auc(rr, ss):.2f}  best-balanced-acc={best[0]:.2f} @thr={best[1]:.1f}")


def corridor():
    """The closed-loop runaway (perceiver outcome + RAM watch)."""
    run = "runs/cn_explore_live2"
    rows = [json.loads(l) for l in open(os.path.join(run, "oracle.jsonl"), encoding="utf-8")]
    steps, prev = [], None
    for r in rows:
        st = r["step"]; p = r.get("perceived", {}); w = r.get("watch", {})
        d = _dir(str(p.get("action") or "").replace("+", " ").split())
        moved = None
        if prev and w:
            moved = (abs(_wrap(w["x"] - prev["x"])) + abs(_wrap(w["y"] - prev["y"]))) != 0
        steps.append((d, moved, os.path.join(run, f"frame_{st:06d}.png")))
        if w: prev = w
    return steps


def human():
    """David's hand-played dungeon recording: real moves AND natural wall-bumps, RAM-labeled."""
    run = "runs/2026-06-23_cavenoire_explore"
    ram = np.fromfile(os.path.join(run, "ram.bin"), dtype=np.uint8)
    n = ram.size // 8192; ram = ram[:n * 8192].reshape(n, 8192)
    btn = [json.loads(l) for l in open(os.path.join(run, "buttons.jsonl"), encoding="utf-8")][:n]
    steps = []
    for i in range(len(btn)):
        d = _dir(btn[i].get("buttons", []))
        moved = None
        if i > 0:
            dx = _wrap(int(ram[i, 0x504]) - int(ram[i - 1, 0x504]))
            dy = _wrap(int(ram[i, 0x503]) - int(ram[i - 1, 0x503]))
            moved = (abs(dx) + abs(dy)) != 0 and (abs(dx) + abs(dy)) <= 40
        steps.append((d, moved, os.path.join(run, f"frame_{i:06d}.png")))
    return steps


def main():
    print("=== PHANTOM-MOVE PROBE - does WINDOWED visual displacement separate real travel from a stuck loop? ===")
    print("(per-step residual could NOT separate them; AUC ~1.0 here = displacement_K tells real from stuck)")
    for name, loader in (("corridor", corridor), ("human-recording", human)):
        try:
            _score(name, loader())
        except FileNotFoundError as e:
            print(f"  {name}: missing ({e})")
    print("\nHigh AUC at K>1 => 'did the view change over the last K steps' recovers the phantom case the")
    print("per-step residual misses -> a stuck-loop guard (seal a direction when displacement_K collapses).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
