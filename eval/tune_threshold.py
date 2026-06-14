"""Tune the perceiver's frame-diff thresholds against the RAM oracle (Iteration 03).

Reads a logged oracle.jsonl (with `perceived.diff`) and, using RAM as ground truth, finds:
  - the MOVE threshold that maximizes in-map walkability accuracy (moved iff diff > t), and
  - a sensible AREA threshold separating map-transition diffs from ordinary in-map moves.

No agent needed — gather data free with a scripted or explore brain:
    uv run python play_pokemon.py --rom roms/PokemonRed.gb --brain scripted --perception \
        --load-state start.state --steps 200 --out runs/tune
    uv run python eval/tune_threshold.py runs/tune/oracle.jsonl
"""
from __future__ import annotations

import json
import sys


def _truth(r):
    return (r.get("map_id"), r.get("x"), r.get("y"))


def rows(records: list[dict]) -> list[dict]:
    records = sorted(records, key=lambda r: r.get("step", 0))
    out = []
    for prev, cur in zip(records, records[1:]):
        diff = (cur.get("perceived") or {}).get("diff")
        if diff is None:
            continue
        (pm, px, py), (cm, cx, cy) = _truth(prev), _truth(cur)
        out.append({"diff": float(diff),
                    "moved": (pm, px, py) != (cm, cx, cy),
                    "map_changed": pm != cm})
    return out


def tune(records: list[dict]) -> dict:
    rs = rows(records)
    in_map = [r for r in rs if not r["map_changed"]]
    cands = sorted({round(r["diff"], 2) for r in rs})
    best_t, best_acc = None, -1.0
    for t in cands:
        if not in_map:
            break
        acc = sum(1 for r in in_map if (r["diff"] > t) == r["moved"]) / len(in_map)
        if acc > best_acc:
            best_t, best_acc = t, acc

    mc = sorted(r["diff"] for r in rs if r["map_changed"])
    mv = sorted(r["diff"] for r in in_map if r["moved"])
    still = sorted(r["diff"] for r in in_map if not r["moved"])
    # An area threshold that clears the biggest in-map move but sits below the smallest map change.
    area_lo = (max(mv) if mv else 0.0)
    area_hi = (min(mc) if mc else None)
    area_rec = round((area_lo + area_hi) / 2, 1) if area_hi is not None else None
    return {
        "n": len(rs), "in_map_n": len(in_map),
        "best_move_threshold": best_t, "best_in_map_accuracy": round(best_acc, 4),
        "in_map_still_diff": _span(still), "in_map_move_diff": _span(mv),
        "map_change_diff": _span(mc),
        "recommended_area_threshold": area_rec,
        "note": "area threshold must exceed the largest in-map move and stay below the smallest map change",
    }


def _span(xs):
    return None if not xs else {"min": round(min(xs), 2), "max": round(max(xs), 2), "n": len(xs)}


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: tune_threshold.py <oracle.jsonl>", file=sys.stderr)
        return 2
    with open(argv[0], encoding="utf-8") as f:
        recs = [json.loads(line) for line in f if line.strip()]
    if not any((r.get("perceived") or {}).get("diff") is not None for r in recs):
        print("no `perceived.diff` in the log — run with --perception after this change.", file=sys.stderr)
        return 1
    res = tune(recs)
    print("=== threshold tuning (vs RAM oracle) ===")
    for k, v in res.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
