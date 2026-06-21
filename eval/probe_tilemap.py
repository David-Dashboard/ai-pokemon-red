"""Offline probe: does the CHEAP perceptual-hash tile->function map deliver the recurrence win that
CLIP did — for free, deterministically, no torch?

Mirror of eval/probe_walkability_learn.py (the CLIP experiment), but the store is the production
`core.tilemap.TileFunctionMap` keyed by a perceptual hash instead of a MobileCLIP embedding. Same
behavioural ground truth from the oracle (NO live RAM): the player is centre-screen at cell (4,4);
the FACED tile (cell (4,4)+dir) in the PRE-move frame is WALKABLE if the move succeeded ('moved')
else BLOCKED. We then ask three questions the design rests on:

  Q5  RECURRENCE (temporal split): on held-out tiles, how OFTEN does the map already recognise the
      appearance (coverage = the 'don't walk every cell' speedup rate), and how ACCURATE is it when
      it does? (Compare to the CLIP probe's 97.7% / near-1.0-cosine temporal recurrence.)
  Q6  ROBUSTNESS: the SAME world tile seen across frames (animation / palette / sub-tile noise) —
      does it hash to one stable key? (Tunes the Hamming tolerance.)
      GENERALISATION sanity (leave-one-MAP-out): on a tileset never seen, the hash should report
      NOVEL (low coverage) rather than confidently MISPREDICT — the failure mode that sank CLIP
      (held-out lab 26.9% < baseline). Low coverage on a held-out map is the CORRECT behaviour here.

Runs in the MAIN uv env (numpy + PIL only) — a feature, not an accident: the recurrence signal needs
no GPU/torch. Usage:  uv run python -m eval.probe_tilemap runs/fix2 [runs/fix4 ...]
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np
from PIL import Image

from core.tilemap import TileFunctionMap

RUN_DIRS = sys.argv[1:] or ["runs/fix2", "runs/fix4", "runs/novelty_val"]
PLAYER = (4, 4)
CELL = 16
OFF = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


def dir_of(action):
    if not action:
        return None
    a = str(action).split("+")[0].strip().lower()
    return a if a in OFF else None


def label_of(outcome):
    if not outcome:
        return None
    o = str(outcome).lower()
    if o == "moved":
        return "walkable"
    if o in ("blocked", "changed-nothing", "no-move", "stuck", "unchanged"):
        return "blocked"
    return None


def _safe(s):
    return str(s).encode("ascii", "replace").decode()


def gather(run_dirs):
    """Behaviour-labelled faced-tile samples: (fingerprint, label, map_id, faced_world_cell, gstep)."""
    samples = []
    gstep = 0
    for run in run_dirs:
        opath = os.path.join(run, "oracle.jsonl")
        if not os.path.exists(opath):
            print(_safe(f"  (skip {run}: no oracle.jsonl)"))
            continue
        rows = [json.loads(l) for l in open(opath, encoding="utf-8")]
        for i in range(1, len(rows)):
            cur, prev = rows[i], rows[i - 1]
            p = cur.get("perceived", {})
            if p.get("context") != "overworld" or cur.get("in_battle"):
                continue
            d, lab = dir_of(p.get("action")), label_of(p.get("outcome"))
            if d is None or lab is None:
                continue
            fpath = os.path.join(run, f"frame_{prev['step']:06d}.png")
            if not os.path.exists(fpath):
                continue
            cx, cy = PLAYER[0] + OFF[d][0], PLAYER[1] + OFF[d][1]
            img = np.asarray(Image.open(fpath).convert("RGB"))
            tile = img[cy * CELL:(cy + 1) * CELL, cx * CELL:(cx + 1) * CELL]
            if tile.shape[:2] != (CELL, CELL):
                continue
            fp = TileFunctionMap.fingerprint(tile)
            # faced world cell from the PRE-move RAM truth (oracle only; never enters the agent)
            wcell = (prev.get("map_id"), (prev.get("x", 0) + OFF[d][0], prev.get("y", 0) + OFF[d][1]))
            gstep += 1
            samples.append((fp, lab, cur.get("map_id"), wcell, gstep))
    return samples


def temporal_recurrence(samples):
    """Q5: store = first 60%, test = last 40%. Report coverage (how often the test tile's appearance is
    already known = the speedup rate) and accuracy on those known tiles, plus the majority baseline."""
    n = len(samples)
    k0 = int(n * 0.6)
    store, test = samples[:k0], samples[k0:]
    tmap = TileFunctionMap()
    for fp, lab, *_ in store:
        tmap.observe(fp, lab)
    known = correct = 0
    forced_correct = 0
    for fp, lab, *_ in test:
        pred = tmap.predict(fp)
        if pred is not None:
            known += 1
            correct += (pred[0] == lab)
        else:
            forced_correct += (lab == "walkable")     # if forced to guess majority on a novel tile
    maj = max(Counter(s[1] for s in test).values()) / len(test)
    print(f"\n=== Q5 temporal recurrence ===  store n={len(store)}  test n={len(test)}")
    print(f"  coverage (appearance already known): {known}/{len(test)} = {known/len(test):.1%}")
    if known:
        print(f"  accuracy WHEN known:                 {correct}/{known} = {correct/known:.1%}")
    overall = (correct + forced_correct) / len(test)
    print(f"  overall acc (known + majority-guess novel): {overall:.1%}   (majority baseline {maj:.1%})")
    print(f"  distinct tile-types learned: {len(tmap)}")


def tol_sweep(samples):
    """Q7 tolerance calibration: the Hamming tol trades COVERAGE (animation collapses to one key) for
    PRECISION (distinct tiles stop colliding). Sweep it on the temporal split to find the knee."""
    n = len(samples)
    k0 = int(n * 0.6)
    store, test = samples[:k0], samples[k0:]
    print(f"\n=== Q7 tolerance sweep (temporal split, store n={len(store)} test n={len(test)}) ===")
    print("  tol  coverage  acc-when-known  tile-types")
    for tol in (0, 2, 4, 6, 8, 12):
        tmap = TileFunctionMap(tol=tol)
        for fp, lab, *_ in store:
            tmap.observe(fp, lab)
        known = correct = 0
        for fp, lab, *_ in test:
            pred = tmap.predict(fp)
            if pred is not None:
                known += 1
                correct += (pred[0] == lab)
        cov = known / len(test)
        acc = (correct / known) if known else 0.0
        print(f"  {tol:>3}  {cov:>7.1%}  {acc:>13.1%}  {len(tmap):>9}")


def robustness(samples):
    """Q6: group faced-tiles by (map_id, world cell). A cell revisited across frames (animation/scroll
    noise) should hash to ONE key — report the max in-group Hamming spread so the tolerance is grounded."""
    groups = defaultdict(list)
    for fp, lab, mp, wcell, gs in samples:
        groups[wcell].append(fp)
    spreads = []
    for fps in groups.values():
        if len(fps) < 2:
            continue
        uniq = list(set(fps))
        spread = max(bin(a ^ b).count("1") for a in uniq for b in uniq) if len(uniq) > 1 else 0
        spreads.append(spread)
    print(f"\n=== Q6 fingerprint robustness (same world-cell across frames) ===")
    if not spreads:
        print("  (no cell revisited >1x in this data)")
        return
    sp = np.array(spreads)
    stable = int((sp == 0).sum())
    print(f"  revisited cells: {len(sp)}   identical-hash: {stable} ({stable/len(sp):.0%})")
    print(f"  in-cell Hamming spread: min {sp.min()} median {int(np.median(sp))} "
          f"p90 {int(np.percentile(sp, 90))} max {sp.max()}  (lower = more stable; tune tol above p90)")


def leave_one_map_out(samples):
    """Q6 sanity: hold out each map; the hash should mostly report NOVEL (low coverage) on the unseen
    tileset rather than confidently mispredict — the safe failure CLIP lacked (it 'recognised' lab
    floor as a wall at 26.9%). Low coverage on a held-out map = correct (defers to the novelty gate)."""
    by_map = Counter(s[2] for s in samples)
    print(f"\n=== leave-one-map-out (coverage should be LOW on an unseen tileset) ===  maps: {dict(by_map)}")
    for held in sorted(by_map, key=lambda m: -by_map[m]):
        test = [s for s in samples if s[2] == held]
        store = [s for s in samples if s[2] != held]
        if len(test) < 20 or len(store) < 20:
            continue
        tmap = TileFunctionMap()
        for fp, lab, *_ in store:
            tmap.observe(fp, lab)
        known = correct = 0
        for fp, lab, *_ in test:
            pred = tmap.predict(fp)
            if pred is not None:
                known += 1
                correct += (pred[0] == lab)
        cov = known / len(test)
        acc = (correct / known) if known else float("nan")
        print(f"  hold map {held}: test n={len(test)}  coverage {cov:.1%}  acc-when-known "
              f"{acc:.1%}" if known else f"  hold map {held}: test n={len(test)}  coverage 0.0% (all novel)")


def main():
    print(_safe(f"runs: {RUN_DIRS}"))
    samples = gather(RUN_DIRS)
    print(f"labelled faced-tile samples: {len(samples)}  "
          f"label dist: {dict(Counter(s[1] for s in samples))}")
    if len(samples) < 40:
        print("too few samples (need recorded runs/<run> with oracle.jsonl + frame_*.png); "
              "this probe is a no-op without data.")
        return
    temporal_recurrence(samples)
    tol_sweep(samples)
    robustness(samples)
    leave_one_map_out(samples)


if __name__ == "__main__":
    main()
