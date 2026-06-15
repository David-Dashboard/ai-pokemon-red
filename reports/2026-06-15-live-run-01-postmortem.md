# Live-run post-mortem #1 — the agent that mapped a phantom for 351 turns (2026-06-15)

**The second deep report.** The first credit-funded, LLM-in-the-loop run of the full stack
(perception + hybrid autopilot + the decoupled aria/Haiku brain). It made **zero progress**, never
left the starting house, and cost **~$3**. This is why — and the why is a *good* result, because the
failure is precise, diagnosed, and not where we feared.

Command under analysis:
```
uv run python play_pokemon.py --rom roms/PokemonRed.gb --brain hybrid --backend aria \
    --perception --load-state start.state --steps 400 --record runs/red_play.mp4 [--sound --watch-delay 90]
```

---

## 1. What we were trying to do

First real test of the agent we spent Iterations 01–03 building: can the **same loop** (free
autopilot + wake-the-LLM-at-decisions, planning over the pixels-derived `SymbolicState`, RAM as a
non-leaking oracle) make autonomous forward progress in Pokémon Red — concretely, **leave the house,
cross Pallet Town, get the starter** (the first class-2 *gate*)? Secondary: confirm perception holds
up live (no Iteration-01 confabulation), and exercise the new `--record` and `goto` features.

## 2. How we did it (method)

- **Brain:** `HybridBrain(ExploreBrain, LLMButtonBrain→aria→Haiku)`. Autopilot does frontier
  exploration for free; the LLM is woken when perception reports a non-overworld mode **or** the
  autopilot is stuck (no reachable frontier).
- **Perception:** `OverworldPerceiver` — frame-diff odometry + a dead-reckoned occupancy map; area
  transitions are guessed from a large whole-frame diff (`area_threshold = 60`).
- **Boot:** `start.state` (the bedroom, map 38). 400-step cap. RAM logged to `oracle.jsonl` for
  scoring only. Recorded to `runs/red_play.mp4`.

## 3. Results (what happened)

| Metric | Value |
|---|---|
| Maps reached | **38 ↔ 37 only** (bedroom 2F ↔ house 1F), bounced **25 times**; never Pallet (0) or the lab |
| Badges / battles / starter | **0 / 0 / none** |
| Per-step perception (walkability) | **399/399 correct** — instantaneous perception was ~perfect |
| Perceived mode | `overworld` on **all 400** frames (correct) |
| Coordinate-frame resets | **0** (`perceived.area` = 0 for all 400 steps) |
| LLM wakes | **351 / 400 (87.8%)** — all `wake:stuck`; autopilot ran free only steps 0–48 |
| Tokens | **2.63M input + 102k output**, `cached_tokens = 0` (no prompt caching) |
| Wall time / cost | ~37.5 min / **~$3** (approx, at assumed Haiku in/out rates) |
| API errors | **0** (credits worked) |
| Recording | `runs/red_play.mp4`, 17.6 MB — worked |

**The behavior, from the trace:** steps 0–48 the autopilot explored the reachable cells normally.
From step **49 onward, every single step is `[wake:stuck]`** and every LLM reply targets the same
cell — `goto=[0, 0]` — reasoning "frontier (0,0) is north/south/east, moving there," while
oscillating forever among `(0,-2)…(1,-4)`. It **never reaches (0,0)**. The LLM even narrates the
trap ("Back at (0,-3) after cycling," "break out of the mapped loop," and at steps 97–105 "I see
Professor Oak's lab structure above") — it *sees* the loop and the lab, but has no tool to escape.

## 4. Root cause — a phantom, unreachable frontier born from a missed transition

The chain, each link backed by the data:

1. **Interior stair-warps are visually tiny.** The 25 real `38↔37` stair transitions produced
   frame-diffs of only **~13–29** — because you reappear on a similar-looking interior tile.
2. **So the perceiver never detected them as area changes** (`area_threshold = 60`; **0/25** cleared
   it) and **never reset its coordinate frame** (`area` stayed `0` for all 400 steps). It
   **dead-reckoned ONE map across both floors**, integrating odometry drift (the `[d,d]` turn-then-move
   moves 1 or 2 tiles depending on facing; odometry advances by 1) into a **geometrically impossible
   merged map** of 48 real cells crushed together.
3. **The start cell `(0,0)` stayed a frontier forever.** A frontier = a visited cell with an
   unconfirmed neighbor; `(0,0)`'s south neighbor was never resolved. But on the corrupted/merged
   map, **`(0,0)` is no longer reachable** (drift + conflated walls box it off), so BFS-to-frontier
   can never path to it to *clear* it.
4. **Permanent "stuck."** Once the genuinely-reachable cells were explored (~step 49), the only
   frontier left was the unreachable `(0,0)`. The autopilot returned `None` (stuck) **every step
   thereafter** → the LLM was woken **every step** (351×).
5. **The LLM couldn't help** — it was handed a corrupted map and an unreachable target; it dutifully
   recomputed "go to (0,0)" 351 times. Class-2 reasoning can't rescue a broken spatial substrate.

**Key distinction this surfaces:** *instantaneous* perception is solved (399/399 walkability, modes
correct, no geographic hallucination — the Iteration-01 disease is cured). What's broken is
**spatial-memory integration over time**: odometry drift + unreliable transition detection corrupt
the *accumulated map*, and the map is what navigation depends on. The bottleneck moved from
**seeing** (Iter 01) to **remembering where things are across transitions** (this run). This was
*foreseen* in LEARNINGS ("diff-magnitude can't separate transitions from big in-map moves; fade
detection is the proper future signal") — and is in fact worse than predicted: interior stairs are
*low*-diff, so they're **missed entirely**, not merely confused.

## 5. Why we wasted money (~$3 for zero progress)

Three failures compounded, none of them the LLM's "intelligence":

- **No global progress watchdog in `play_pokemon.py`.** `play_loop.py` has one (halts when
  badges/maps/level/coverage don't improve for N steps) and **would have stopped this around step
  ~60**. `play_pokemon.py` has none, so it ran the full 400 steps of flailing.
- **The anti-loop guarantee had a hole.** The autopilot is loop-free *when "stuck" means no
  frontier*. Here it had a frontier that was **unreachable**, so it reported stuck **every step** and
  delegated to the LLM every step — 351 paid calls — instead of recognizing "I keep failing to reach
  the same frontier → abandon it / halt."
- **Prompt caching was off** (`cached_tokens = 0`). Each of the 351 wakes resent ~6.7k input tokens
  uncached; most of that is a stable system+memory prefix that caching would bill at ~10%.

Net: 2.63M input tokens, ~$3, for a run that a single watchdog or a single "give up on an
unreachable frontier" check would have ended in pennies.

## 6. Conclusions

1. **Perception (per-frame) is no longer the bottleneck — spatial memory is.** We fixed Iteration
   01's confabulation; this run cleanly exposes the next wall: a drifting, never-resetting map.
2. **The map model is too fragile.** Dead-reckoning with diff-thresholded resets fails on the most
   common transition (interior stairs/doors are low-diff). It needs a transition signal that
   actually fires, and a map that *links* places instead of overwriting/merging them.
3. **The agent has no loop-breaker.** Neither the autopilot nor the LLM nor the outcome-loop
   detected "I am not making progress" — because drift made every step's `(situation)` look novel, so
   `OutcomeMemory` never flagged a dead action. Progress must be tracked *globally*, not per-tile.
4. **Cost guardrails must be on by default.** A watchdog + caching are not optional for paid runs.
5. **Good news to bank:** instantaneous perception 399/399, modes 100% correct, no confabulation, 0
   API errors, recording works, and the `goto` feature was exercised (the LLM emitted `GOTO` every
   turn — the plumbing is live; it was just pointed at an impossible target).

## 7. Next steps (prioritized: stop the bleeding → fix the cause)

**Tier 1 — cheap guardrails (do first; would have saved this $3):**
1. **Port the progress watchdog into `play_pokemon.py`** (halt on no global progress for N steps).
2. **Frontier-abandonment / loop-breaker:** if the autopilot is stuck on the *same* unreachable
   frontier K times, drop that frontier (and if none remain, halt) — and feed "no progress for N
   steps" into the wake/escalation logic so the LLM is asked to *replan*, not micro-navigate.
3. **Enable prompt caching** on the aria/Haiku calls — the single biggest cost win.

**Tier 2 — fix the actual cause (spatial memory):**
4. **Reliable transition detection.** Diff-threshold misses interior stairs. Use the right signal:
   a **fade-to-black/white transition detector** (the screen fades on every warp — and we already
   built a near-uniform-frame detector for the battle-fade fix; reuse it), or corroborate with "the
   player sprite/camera jumped." On a detected transition, **reset/branch the coordinate frame**.
5. **A place-graph, not one drifting grid.** Keep a per-area occupancy map and *link* areas by the
   transition used ("map A's stair ↔ map B's stair"), so returning to a known area restores its map
   instead of merging it. This also gives the planner real landmarks.
6. **Curb odometry drift:** make `[d,d]` net exactly one tile, or re-anchor on confident features.

**Tier 3 — validate:**
7. Re-run the same slice with Tier-1+2 in place; success = **leaves the house and reaches Pallet**
   within a bounded step/$ budget, watchdog-guarded. Then retry the starter gate.

The honest one-line verdict: **the brain was fine; the map lied to it, and nothing told it to stop.**
