# 2026-06-25 — Opus vs Sonnet vs Haiku as the System-2 brain (dockerized MCP world)

First end-to-end model comparison on the new harness. **The harness is validated; the comparison itself is
confounded by a world strand-bug, so it is NOT a clean model ranking** — recorded honestly.

## Setup
- **World:** `world_mcp.py` (Cave Noire) as an MCP **stdio** server, run as a **Docker container**
  (`docker run -i`) — a clean spawn that fixed the Windows `python.exe` MCP-spawn failure. RAM (`x,y,hp`
  via `watch`, hp=`0xD389`) is the scoring oracle, logged to `oracle.jsonl`, **never on the wire**.
- **Brain:** each model = a **headless Claude Code** instance (`claude -p`, `CLAUDE_CODE_OAUTH_TOKEN`,
  `--allowedTools mcp__cave-noire-world` so it can ONLY touch the 7 game tools). Same `cn_open.state`,
  same 20-decision comparison task, same brief.
- **Models:** Opus 4.8 · Sonnet 4.6 · Haiku 4.5. Scored with `eval/score_mcp_runs.py`.

## Results (RAM ground truth)
| model | cells | steps | moved | blocked | wall% | real-move% | hp end/min | dmg | self-reported |
|---|--:|--:|--:|--:|--:|--:|--:|--:|---|
| **opus** | 7 | 46 | 8 | 15 | 65% | 50% | 7/7 | 0 | 9 cells, **7 decisions**, 1.3 cells/dec |
| **sonnet** | 8 | 75 | 10 | 24 | 71% | 50% | 7/7 | 0 | 10 cells, 0.5 cells/dec |
| **haiku** | 7 | 49 | 8 | 13 | 62% | 50% | 7/7 | 0 | 9 cells, 1.0 cells/dec |

## The confound (why this is not a ranking)
**All three were trapped identically:** the first `explore` auto-walked each into a sealed, walled-off
pocket they could not leave — so the coverage numbers are ~equal (7–8 cells) because everyone hit the
*same wall*. **Opus diagnosed it and flagged it unprompted:** *"this looks like an environment/seam bug —
autopilot stranded me in a fully-walled pocket with the listed frontiers unreachable and the start cell
mislabeled unexplored — so this isn't a clean comparability data point."* (Frontiers listed-but-unreachable
+ start cell mislabeled-unexplored = a perceiver/occupancy-map bug, likely the dead-reckoning-drift family
in the cramped `cn_open.state`.)

## Qualitative signal (despite the confound)
- **Opus** — sharpest: **7 decisions**, recognized the trap fastest, **root-caused it correctly**, stopped
  cleanly instead of flailing.
- **Sonnet** — flailed most (75 steps, 24 wall-bumps), spent its budget diagnosing/recovering.
- **Haiku** — gave up ("failed catastrophically"), least insight.

Even on a broken task, Opus led on efficiency + diagnosis. But the cells numbers are too close + the task
too broken to call a winner.

## What's needed for a clean comparison
The blocker is the **world, not the model**: `cn_open.state` + the explore/perceiver interaction strands the
agent. Re-run after either (a) capturing a more-open in-cavern start state, or (b) fixing the strand bug Opus
flagged (frontiers-unreachable / start-cell-mislabeled). Until then, no model ranking is defensible.

## Raw data
`runs/2026-06-25_cavenoire_mcp_{opus,sonnet,haiku}/` (oracle.jsonl + frames) + the per-run `*_run.log`
(each model's narration + final report). Re-score: `uv run python -m eval.score_mcp_runs <dirs> --labels ...`.
