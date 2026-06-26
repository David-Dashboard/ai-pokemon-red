# 2026-06-21 — Seen-states / novelty gate: paid validation (3 cold runs)

**TL;DR.** The seen-states cycle gate (branch `feat/novelty-signal`) was validated live across three cold
runs from `start.state`. **The #1 blocker (the Oak starter-dialog trap) is BROKEN: the agent got the starter
(CHARMANDER) cold in all three runs — the longloop never did.** The cycle gate fired live when aria froze
(run 2: 11× `[wake:cycle]`) and the pure-fact `cycle_note` was enough for aria to reason its way out to the
Pokéballs. A **new, separate downstream bottleneck** surfaced: the post-starter **nickname-entry keyboard**
(misdetected as `battle`), plus a non-deterministic rival-battle trigger. Total spend ~$1.77.

## What was tested

The fix: `core/novelty.py` `NoveltyMemory` counts VISITS (rising-edge) to `(state_signature, screen_text)`;
`HybridBrain` stops auto-advancing and wakes System 2 with a pure-fact `cycle_note` when a dialog state is
revisited `_CYCLE_REVISITS=3` times. Goal of the runs: confirm the agent escapes Oak's "which POKéMON?" loop
that froze the longloop run (auto-advance mashing A on a textbox A can't dismiss).

## Results (oracle-verified, not narration)

| | Run 1 `novelty_val` | Run 2 `novelty_val2` | Run 3 `novelty_val3` |
|---|---|---|---|
| Cost / wakes | $0.12 / 12 | $0.75 / 57 | $0.90 / 70 |
| Nav to lab cold (`38→37→0→40`) | ✅ | ✅ | ✅ |
| **Starter (CHARMANDER) acquired** | ✅ | ✅ | ✅ |
| aria froze (cycling Oak dialogue) | no | **yes** | yes |
| `[wake:cycle]` fired | 0 | **11** | 5 |
| aria broke freeze via `cycle_note` | n/a | ✅ | ✅ |
| Rival battle reached (`in_battle`) | ❌ | ✅ (=2) | ❌ |
| Halt cause | stuck-steps 150 (at nickname) | cost cap $0.75 (mid-battle) | nickname-keyboard stuck (40-wake watchdog) |

### The headline: the gate works, live
Run 2, on a `[wake:cycle]` wake, aria's own reasoning (verbatim from the log):
> *"…the same line I've seen cycle before. The text box is still active and repeating. I need to try a
> different button — not A. Let me try pressing B…"* → then
> *"I'm stuck in a dialogue loop — A and B both repeat the same text. I need to try a direction button instead
> to break out of this state or navigate away."* → `up+up+up`, and
> *"The three POKéBALLs are on the table directly in front of me… navigate left… then press A to confirm."*

This is the dual-process seam working live: **System 1 detected the cycle and reported only the fact; System 2
decided the recovery.** No game-specific steering in the harness.

### The pose-inclusive key is correct (run 1 confirms)
Run 1, aria navigated out of the lab dialogue on its own (no freeze); the prompt appeared at *different*
perceiver poses, so the gate correctly **did not fire** (`0 [wake:cycle]`). The gate keys on pose+text, so it
fires on a *frozen* cycle (longloop, run 2) and stays silent while the agent is moving/escaping — it never
interrupts a self-recovering agent.

## New bottleneck (downstream, separate from the Oak trap)

Run 3 got the starter (step 434) then **stuck on the nickname-entry keyboard**: it answered YES to "give a
nickname to CHARMANDER?", and the keyboard grid (steps 447–485) is **misdetected as `battle`** context (the
known full-screen-bright-menu limitation in `detect_mode`; see Iteration-03 learnings). aria woke **44×
`[wake:mode]`** cycling *"Nickname grid open… DONE is to the right… navigate down then right"* and never
escaped; the wake-watchdog halted it. The "map 1" blip at step 446 was a 1-frame perceiver misread, not a real
Route 1 visit. The rival-battle trigger is also non-deterministic (reached run 2, not run 3).

## Honest cost note

The gate kills the *infinite* freeze (the longloop never escaped) but **recovery from a freeze is wake-heavy**:
clean nav (run 1) = 12 wakes; freeze→recover (run 2) = 57; run 3 = 70. ~40–50 of those are "struggle" wakes
while aria probes its way out. A stronger "the Pokéballs are here" affordance hint would cut this.

## Next

1. **The nickname keyboard** (the immediate downstream blocker): answer NO to nicknaming, OR fix
   `detect_mode`'s keyboard-as-`battle` misread, OR — the unifying fix that extends this work — a general
   "no-novelty across N wakes → press B / try something else" stuck-breaker (the novelty signal applied beyond
   dialog auto-advance) that would catch the 44× keyboard revisit.
2. The rival-battle win itself is a proven capability (runs #11–13); the blocker is *reaching* it reliably.

Artifacts: oracles `runs/novelty_val{,2,3}/oracle.jsonl`; videos `runs/novelty_val{,2,3}.mp4`; code
`core/novelty.py` + the `HybridBrain` gate; free regression `eval/inspect_longloop_trap.py`.
