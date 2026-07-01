"""Score the It1 human-given task: "get your first Pokémon from Professor Oak" (Iteration 03).

Reads a `claude -p` MCP run's `world/oracle.jsonl` (+ optional `transcript.jsonl`) and reports:
  * success  — did `watch.party` go 0 -> 1 (oracle-only; never the agent's input, so it can't be gamed)
  * wakes    — decision tool-calls up to (and including) the success step, from the transcript's
               "Cost so far: N decision(s)" tally (the same string world_mcp.py's preamble emits)
  * tiles    — cells explored at that point (from the transcript's "X per decision" tally)
  * cost_usd — the run's `total_cost_usd` (the transcript's final `result` event; None if absent/free)

    uv run python -m eval.score_red_task runs/brain_red_starter/world/oracle.jsonl \\
        runs/brain_red_starter/transcript.jsonl
"""
from __future__ import annotations

import json
import re
import sys

_COST_SO_FAR = re.compile(r"Cost so far: (\d+) decision\(s\).*?Progress: (\d+) cells explored")


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _party_success_step(oracle: list[dict]) -> int | None:
    """The oracle `step` at which `watch.party` first reads >= 1, given it started at 0."""
    oracle = sorted(oracle, key=lambda r: r.get("step", 0))
    baseline_seen = False
    for rec in oracle:
        party = (rec.get("watch") or {}).get("party")
        if party is None:
            continue
        if not baseline_seen:
            if party != 0:
                return None  # didn't start at 0 -> not a valid oracle for this task's success predicate
            baseline_seen = True
        elif party >= 1:
            return rec["step"]
    return None


def _cost_tally_at_or_before(transcript: list[dict], step: int | None) -> tuple[int | None, int | None]:
    """(wakes, tiles) from the LAST "Cost so far: N decision(s) ... M cells explored" tally seen in the
    transcript's tool_result text — the running preamble world_mcp.py prepends to every result. Without a
    step to bound it, uses the final tally seen (the whole run's cost). The oracle `step` and the brain's
    own decision count aren't the same clock (auto-walked tiles also advance `step`), so this is a
    same-ballpark cross-check, not an exact per-step alignment."""
    wakes = tiles = None
    for msg in transcript:
        for block in (msg.get("message") or {}).get("content") or []:
            text = block.get("text") if isinstance(block, dict) else None
            if not text:
                continue
            m = _COST_SO_FAR.search(text)
            if m:
                wakes, tiles = int(m.group(1)), int(m.group(2))
    return wakes, tiles


def _run_cost_usd(transcript: list[dict]) -> float | None:
    for msg in transcript:
        if msg.get("type") == "result":
            return msg.get("total_cost_usd")
    return None


def score(oracle: list[dict], transcript: list[dict] | None = None) -> dict:
    success_step = _party_success_step(oracle)
    wakes, tiles = _cost_tally_at_or_before(transcript or [], success_step)
    return {
        "success": success_step is not None,
        "success_step": success_step,
        "wakes": wakes,
        "tiles_explored": tiles,
        "cost_usd": _run_cost_usd(transcript or []) if transcript else None,
        "oracle_steps": len(oracle),
    }


def format_report(m: dict) -> str:
    lines = [
        "=== It1 score: get your first Pokémon from Professor Oak ===",
        f"success (party 0->1): {m['success']}" + (f"  (oracle step {m['success_step']})" if m["success"] else ""),
        f"wakes (decision tool-calls): {m['wakes'] if m['wakes'] is not None else 'n/a (no transcript)'}",
        f"tiles explored (System-1 + brain): {m['tiles_explored'] if m['tiles_explored'] is not None else 'n/a'}",
        f"est. cost: ${m['cost_usd']:.2f}" if m["cost_usd"] else "est. cost: n/a (free sub run, or no transcript)",
        f"oracle steps logged: {m['oracle_steps']}",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: score_red_task.py <oracle.jsonl> [transcript.jsonl]", file=sys.stderr)
        return 2
    oracle = load_jsonl(argv[0])
    transcript = load_jsonl(argv[1]) if len(argv) > 1 else None
    print(format_report(score(oracle, transcript)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
