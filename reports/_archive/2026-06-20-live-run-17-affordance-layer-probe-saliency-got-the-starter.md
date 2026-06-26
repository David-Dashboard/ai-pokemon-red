# Live run #17 — affordance layer (probe+saliency) — got the starter (2026-06-20)

_The first paid test of the AFFORDANCE LAYER (interaction-probe + motion-saliency ROIs), cold from
`start.state`. Run #16 reached Oak's lab but couldn't transact the starter (interactables read as walls).
This run adds the probe + ROI hints and asks: can the agent now get the starter, cold?_

**TL;DR — YES, and it WON the rival battle. The first cold-start run to go start → starter → win.** From
`start.state` the agent navigated to Oak's lab, the **interaction-probe (23 fires) + motion-saliency ROI
hints got it the starter (Squirtle)**, it reached the rival battle (vs Bulbasaur, a bad matchup) and **WON**
(`in_battle` 2→0 sustained at step 842, stayed on map 40 = no blackout; the battle policy from runs #12/#13
held). Navigation + the starter cost only **~6 of 69 wakes** (the probe is FREE autopilot; 63 wakes were the
battle), with **227 free dialog/battle auto-advances** — the cheap-first thesis, end to end. **The affordance
layer is validated: it directly closed the run-#16 bottleneck.** Two caveats: the **place-graph stayed
unreliable** (it merged the lab into Pallet, area 0 — see run #16/the free probe_loop) yet the agent
succeeded ANYWAY, and the run **halted on the circuit breaker** — 4 consecutive `invalid_request` API errors
(a backend hiccup, NOT credits) that hit AFTER the win while it was re-stuck in the lab post-battle. ~$0.6-0.8.

## Config
```
play_pokemon.py --rom roms/PokemonRed.gb --brain hybrid --perception --no-vision --backend aria \
    --load-state start.state --steps 1500 --max-llm-calls 100 --stuck-steps 250 \
    --out runs/run17 --record runs/run17.mp4
```
Run-16 config + the affordance layer (auto-on in the drivers: `ExploreBrain(single_step=True,
probe_interactables=True)` + motion-saliency ROIs). Clean start: `reset_aria_memory.py --yes` (archive
`iter-017_2026-06-20.zip`); aria credit-probed healthy; `python -u`.

## Results (oracle-verified — auto-extracted; do not hand-edit the numbers)

| Metric | Value |
| --- | --- |
| Outcome | **WON** — `in_battle` 2→0 sustained at step 842 |
| `in_battle` | start 0, values [0, 2], sustained-exit @ 842 |
| Maps (trajectory) | 38→37→0→40→0→40 |
| Maps seen | [0, 37, 38, 40] |
| Oracle rows (steps) | 857 |
| Party level (start/end) | None / None |
| Badges (start/end) | 0 / 0 |
| LLM wakes | 69 (63 in battle) |
| Auto-advances (free) | 227 |
| Errors (400 / crash / credit) | 5 |
| Episode summary | 69/857 wakes (8.1%), reward 8.0 |
| Cost | ~$0.6-0.8 |

## What worked

- **The affordance layer closed the run-#16 bottleneck — cold.** Run #16 reached Oak's lab and stalled
  (no starter, all wakes stuck). Run #17, same config + the probe + ROI hints, **got the starter and won the
  rival battle from a cold `start.state`** — `38→37→0→40` (with a `40→0→40` Oak-escort blip), starter at the
  lab, `in_battle` 763→sustained-exit 842. **First time start → starter → rival win in one run.**
- **The interaction-probe is the engine, and it's FREE.** 23 probes fired (run #16: 0); navigation + the
  starter cost only **~6 LLM wakes** (the probe is autopilot, not a wake), plus 227 free auto-advances. 63 of
  the 69 wakes were the battle itself. This is the cheap-first thesis proven across the whole opening.
- **The battle policy held cold** (Squirtle vs Bulbasaur is a type DISadvantage, yet it ground it out with
  Tackle and won) — runs #12/#13's win reproduced from a cold start, not a fixture.
- **The circuit breaker worked** — when the backend began erroring post-battle, it halted at 4 consecutive
  fast instead of burning the budget on no-ops.

## What broke / the bottlenecks

- **The place-graph is still unreliable — and this run proves the agent can succeed DESPITE it, not because
  it's fixed.** The perceiver **merged the lab into Pallet** (`area` stays 0 across the 0→40 warp; confirmed
  in run #16 and the free `probe_loop`, where run #15 instead FRAGMENTED the lab into 5 places). So the
  cross-place groundwork couldn't engage (no clean place boundary), and the agent got **re-stuck in the lab
  post-battle** (the LLM confabulating a "lab grid loop"). **Place-detection reliability is the confirmed #1
  nav blocker** — it misses real warps (merge) and invents false ones (fragment). The drift fix made WITHIN-room
  geometry trustworthy; BETWEEN-room identity is not.
- **A new API failure mode: `invalid_request` (not credits).** The 4 consecutive 400s that halted the run were
  `litellm.BadRequestError: AnthropicException - invalid_request`, not "credit balance." Likely a malformed/over-
  long request building up late in the run (transcript/lessons growth?). Worth a look — distinct from the
  recurring credit outages.
- *The agent still doesn't reliably LEAVE the lab after the battle* — same exploration-completeness gap
  cross-place is meant to fix, but it needs a reliable place-graph first.

## Next

1. **Fix place-detection reliability (the #1 nav blocker).** Make the warp/transition signal robust: don't miss
   a warp that completes on a non-directional action (the lab merge — the transition is gated on `direction is
   not None`), and don't mint spurious places from dialog-flicker / high-diff non-move frames (the fragmenting).
   This is a focused, data-first Phase-B revisit (we have run #15/#16/probe_loop frames). It's the precondition
   for the cross-place groundwork to pay off and for clean interior reasoning.
2. **Investigate the `invalid_request` API errors** — reproduce and find what makes the request malformed late
   in a run (prompt growth?); cheap reliability win.
3. Then the cross-place explorer (already built) should let the agent leave the lab post-battle and continue
   toward Route 1 — the next forward progress.

---
_Artifacts: video `runs/run17.mp4`; oracle `runs/run17/oracle.jsonl`; archive `iter-017_2026-06-20.zip`._

<!-- DEFINITION OF DONE — after filling the TODOs above, also update: (2) reports/LEARNINGS.md (a dated bullet), (3) HANDOFF.md §2 status + NEXT, (4) memory/current-status.md. -->
