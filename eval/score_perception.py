"""Score perception against the RAM oracle (Iteration 03, Step 1 — the measurement rig).

Reads a paired oracle.jsonl (truth ⟂ perceived) from the plugin's perception path and grades
the perceiver WITHOUT the agent ever seeing RAM. Headline metric: walkability accuracy — did the
frame-diff `moved/blocked` verdict match whether RAM position ACTUALLY changed? ("blocked" here
means "position unchanged" — a wall or a turn-in-place; both are correctly "did not move".)

Measure it FREE (no API) with a scripted brain:
    uv run python play_pokemon.py --rom roms/PokemonRed.gb --brain scripted --perception \
        --load-state start.state --steps 150 --out runs/percep_bench
    uv run python eval/score_perception.py runs/percep_bench/oracle.jsonl
"""
from __future__ import annotations

import json
import sys


def load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _truth_pos(r: dict):
    return (r.get("map_id"), r.get("x"), r.get("y"))


def score(records: list[dict]) -> dict:
    records = sorted(records, key=lambda r: r.get("step", 0))
    n = len(records)
    tp_move = tp_block = false_move = false_block = 0  # confusion on the moved/not-moved verdict
    perceived_moves = 0
    true_tiles = 0  # RAM tiles moved over scored same-map steps (odometry undercount diagnostic)

    for prev, cur in zip(records, records[1:]):
        outcome = (cur.get("perceived") or {}).get("outcome")
        if outcome not in ("moved", "blocked"):
            continue  # not a scored directional move (first step / non-directional action)
        (pm, px, py), (cm, cx, cy) = _truth_pos(prev), _truth_pos(cur)
        truth_moved = (pm, px, py) != (cm, cx, cy)
        perceived_moved = outcome == "moved"
        if perceived_moved and truth_moved:
            tp_move += 1
        elif not perceived_moved and not truth_moved:
            tp_block += 1
        elif perceived_moved and not truth_moved:
            false_move += 1   # said moved; RAM didn't move
        else:
            false_block += 1  # said blocked; RAM moved (a MISSED move)
        if perceived_moved:
            perceived_moves += 1
        if truth_moved and pm == cm:
            true_tiles += abs(cx - px) + abs(cy - py)

    scored = tp_move + tp_block + false_move + false_block
    acc = (tp_move + tp_block) / scored if scored else None
    block_prec = tp_block / (tp_block + false_block) if (tp_block + false_block) else None
    block_rec = tp_block / (tp_block + false_move) if (tp_block + false_move) else None

    maps = [r.get("map_id") for r in records]
    start_map = maps[0] if maps else None
    escape_step = next((records[i]["step"] for i, m in enumerate(maps) if m != start_map), None)

    return {
        "steps": n,
        "scored_moves": scored,
        "walkability_accuracy": acc,
        "confusion": {"true_moved": tp_move, "true_blocked": tp_block,
                      "false_moved": false_move, "false_blocked_missed_move": false_block},
        "blocked_precision": block_prec,
        "blocked_recall": block_rec,
        "escaped_start_map": escape_step is not None,
        "escape_step": escape_step,
        "maps_visited": sorted({m for m in maps if m is not None}),
        "tiles_per_perceived_move": (true_tiles / perceived_moves) if perceived_moves else None,
    }


def format_report(m: dict) -> str:
    def pct(x):
        return "n/a" if x is None else f"{100 * x:.1f}%"

    und = m["tiles_per_perceived_move"]
    return "\n".join([
        "=== perception score (vs RAM oracle) ===",
        f"steps: {m['steps']}   scored directional moves: {m['scored_moves']}",
        f"walkability accuracy: {pct(m['walkability_accuracy'])}",
        f"  blocked precision: {pct(m['blocked_precision'])}   recall: {pct(m['blocked_recall'])}",
        f"  confusion: {m['confusion']}",
        f"escaped start map: {m['escaped_start_map']}  (step {m['escape_step']})",
        f"maps visited: {m['maps_visited']}",
        f"odometry undercount: ~{und:.2f} real tiles per perceived move" if und is not None
        else "odometry undercount: n/a",
    ])


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: score_perception.py <oracle.jsonl>", file=sys.stderr)
        return 2
    recs = load(argv[0])
    if not any(r.get("perceived") for r in recs):
        print("no `perceived` block in the log — run the episode with --perception.", file=sys.stderr)
        return 1
    print(format_report(score(recs)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
