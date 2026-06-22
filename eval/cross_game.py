"""Cross-GAME / cross-dataset generalisation verdict: build the tile->function map on STORE runs, then
test it on held-out TEST runs (a different game, or a never-seen tileset). The honest generalisation
question: on tiles it has NEVER seen, does the hash FAIL SAFE (low coverage = 'novel -> explore') rather
than confidently mispredict walls as walkable? Reports coverage / acc-when-known / WALL-RECALL (the
metric that matters for navigation) for default vs skip_flat. Free, no torch.

    uv run python -m eval.cross_game --store runs/fix1 runs/fix2 --test runs/kanto2
    (when a 2nd-game ROM is recorded: --store runs/<all pokemon> --test runs/<gen2-or-zelda>)
"""
from __future__ import annotations
import argparse
from collections import Counter
from core.tilemap import TileFunctionMap
from eval.probe_tilemap import gather


def evaluate(store, test, skip_flat):
    tmap = TileFunctionMap()
    for fp, lab, *_ in store:
        tmap.observe(fp, lab)
    known = correct = 0
    w_ok = w_novel = w_bad = 0
    for fp, lab, *_ in test:
        pred = tmap.predict(fp, skip_flat=skip_flat)
        if pred is not None:
            known += 1
            correct += (pred[0] == lab)
        if lab == "blocked":
            if pred is None:
                w_novel += 1
            elif pred[0] == "blocked":
                w_ok += 1
            else:
                w_bad += 1
    n = len(test)
    cov = known / n if n else 0.0
    acc = correct / known if known else float("nan")
    wr = w_ok / (w_ok + w_bad) if (w_ok + w_bad) else float("nan")
    return cov, acc, wr, (w_ok, w_novel, w_bad), len(tmap)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", nargs="+", required=True, help="runs the map LEARNS from (game A)")
    ap.add_argument("--test", nargs="+", required=True, help="held-out runs to PREDICT (game B / new tileset)")
    args = ap.parse_args()
    store = gather(args.store)
    test = gather(args.test)
    print(f"store: {len(store)} faced-tiles ({args.store})")
    print(f"test : {len(test)} faced-tiles ({args.test})   label dist {dict(Counter(s[1] for s in test))}")
    if not store or not test:
        print("need samples in both (recorded runs with oracle.jsonl + frames). no-op."); return
    print(f"\n{'setting':12} {'coverage':>9} {'acc-known':>10} {'wall-recall':>12}  walls ok/novel/MISCALLED  store-types")
    for name, sf in (("default", False), ("skip_flat", True)):
        cov, acc, wr, (ok, nov, bad), types = evaluate(store, test, sf)
        print(f"{name:12} {cov:>9.1%} {acc:>10.1%} {wr:>12.1%}  {ok}/{nov}/{bad:<6}        {types}")
    print("\nGENERALISES SAFELY = LOW coverage on a never-seen game/tileset (reads novel -> explore) and few "
          "MISCALLED walls. High coverage + miscalled walls = confident cross-domain mispredict (the failure).")


if __name__ == "__main__":
    main()
