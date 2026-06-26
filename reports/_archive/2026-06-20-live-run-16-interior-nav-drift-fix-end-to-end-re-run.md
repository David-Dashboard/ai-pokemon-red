# Live run #16 — interior-nav drift fix — end-to-end re-run (2026-06-20)

_The first paid test of the interior-navigation DRIFT fix (single-press autopilot + measured-distance
odometry). Run #15 wall-locked in the lab interior (pose-only map corrupted, all 100 wakes stuck). This
run re-runs the exact run-#15 config to see if the agent can now navigate the lab and reach Oak._

**TL;DR — the navigation fix WORKED; the bottleneck moved one step forward to AFFORDANCE discovery.**
The agent navigated cleanly from `start.state` through Pallet and **into the lab interior, all the way up
to Oak's tile (`40,4,2` — the top of the room)** — the exact spot run #15 could never reach. **Live
dead-reckoning drift was 2.9% vs run #15's 40.2%, and crucially only 4% across 149 same-segment move-pairs
INSIDE the tight lab (map 40)** — the room that corrupted before is now traversed accurately. But it
**never got the starter** (`in_battle` stayed 0 all run, budget-cap halt at 100 wakes): the agent reaches
Oak / the Pokéball table but has **no model of interactables** — the balls and Oak are non-walkable tiles,
so they read as *walls*, never as frontiers; the autopilot only chases frontiers (wanders), and the
text-only LLM confabulates "staircase / lab exit / maze" instead of "face the ball and press A." **Nav is
solved; the new wall is that the agent can't discover/transact a region of interest.** ~$0.6-0.8, 0 errors.

## Config
```
play_pokemon.py --rom roms/PokemonRed.gb --brain hybrid --perception --no-vision --backend aria \
    --load-state start.state --steps 1000 --max-llm-calls 100 --stuck-steps 250 \
    --out runs/run16 --record runs/run16.mp4
```
Identical to run #15 + the interior-nav drift fix (`ExploreBrain(single_step=True)` + measured-distance
odometry). Clean start: `reset_aria_memory.py --yes` (archive `iter-016_2026-06-20.zip`); aria credit-probed
healthy beforehand; `python -u`.

## Results (oracle-verified — auto-extracted; do not hand-edit the numbers)

| Metric | Value |
| --- | --- |
| Outcome | no battle this run |
| `in_battle` | start 0, values [0], sustained-exit @ — |
| Maps (trajectory) | 38→37→0→40 |
| Maps seen | [0, 37, 38, 40] |
| Oracle rows (steps) | 618 |
| Party level (start/end) | None / None |
| Badges (start/end) | 0 / 0 |
| LLM wakes | 100 |
| Auto-advances (free) | 139 |
| Errors (400 / crash / credit) | 0 |
| Episode summary | 100/618 wakes (16.2%), reward 3.0 |
| Cost | ~$0.6-0.8 |

## What worked

- **Interior-navigation drift is FIXED, live.** Measured the perceiver's dead-reckoned pose against the
  RAM oracle per step: **2.9% same-segment drift vs run #15's 40.2%** (`eval/replay_drift` methodology, run
  inline on run #16's oracle). The decisive number is **map 40 (the lab) = 6/149 = 4%** — run #15 corrupted
  in that exact room after a handful of moves; run #16 made **149 clean move-pairs** there. House 0%, Route 1
  0%, Pallet 3%. The single-press autopilot + measured-distance odometry hold on real hardware.
- **The agent reached the run-#15 wall and crossed it.** It navigated `38→37→0→40` and walked **up to Oak's
  tile at the top of the lab (`40,4,2`), exploring 41 distinct lab tiles** — purposeful interior traversal,
  the thing run #15 (all 100 wakes `[wake:stuck]`, never moved meaningfully in the room) could not do.
- **0 errors, breaker silent, credits healthy** — the pre-run credit probe + clean reset worked; aria held
  the whole run. Dialog auto-advance fired 139× (Oak's intro + Pallet signs). Auto-report hook fired.

## What broke / the new bottleneck — AFFORDANCE / region-of-interest discovery

- **The agent reaches Oak but can't TRANSACT the starter.** `in_battle` stayed 0 all 618 steps; it never got
  a Pokémon, never reached the rival battle; budget-cap halt at 100 wakes. Root cause is **structural, not a
  nav regression**: the perceiver models pure geometry (visited / walls / frontiers / portals) and has **no
  representation of interactables**. Oak and the three Pokéballs sit on non-walkable tiles, so they read as
  **walls** — never frontiers. The free autopilot only chases frontiers, so it **wanders the lab** and
  repeatedly exhausts them → `[wake:stuck]`. The text-only LLM, woken stuck with only geometry (no vision —
  disabled since it confabulates battle sprites — and no "there's a ball here" signal), **confabulates**:
  it narrates a "lab maze / staircase / overworld exit" and issues GOTOs to phantom cells. Neither layer ever
  tries the one correct action: **face a Pokéball and press A.**
- **This is the same shape as the nav wall, one level up.** Run #15: "can't navigate the interior." Run #16:
  "navigates the interior fine, but can't discover/act on what's IN it." The geometry model told the agent
  *where it can go*; nothing tells it *what it can act on*.
- *Watchdog note:* `--stuck-steps 250` didn't fire — the agent kept visiting new lab tiles (coverage ticks),
  so the no-progress fingerprint reset; the wake budget (100) was the real ceiling. Real movement ≠ progress,
  again.

## Next

1. **Interaction-discovery primitive (the affordance fix).** When the autopilot exhausts frontiers (today's
   `[wake:stuck]`), before waking the LLM, **systematically face each adjacent non-walkable tile and press A**;
   a resulting mode-change (dialog/menu/battle) or decoded text means that "wall" is an **interactable** — record
   it as an ROI in the map and wake the LLM with that context ("pressing A facing up opened a dialog"). Free,
   vision-free, world-agnostic (it encodes no Pokémon facts), and it *replaces* wasted stuck-wakes rather than
   adding cost. This is the precondition for the starter → rival → Route 1 — exactly the gap this run exposed.
2. Complementary, if needed: **overworld-only vision** (use the model's eyes where it's safe, keep text-only in
   battle) and **animation-saliency** NPC detection (a region that changes while the camera is static = a living
   entity). Lower priority than the probe.
3. The **learned blind-execute battle policy** stays queued behind affordance discovery (the battle is solved —
   runs #12/#13 — but still unreachable cold until the agent can get the starter).

---
_Artifacts: video `runs/run16.mp4`; oracle `runs/run16/oracle.jsonl`; archive `iter-016_2026-06-20.zip`._

<!-- DEFINITION OF DONE — after filling the TODOs above, also update: (2) reports/LEARNINGS.md (a dated bullet), (3) HANDOFF.md §2 status + NEXT, (4) memory/current-status.md. -->
