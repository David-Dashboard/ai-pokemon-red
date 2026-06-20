# Live runs #4–#12 — the navigation & battle arc (digest, 2026-06-17 → 2026-06-20)

_Backfill. Runs #1–#3 and #13 have standalone reports; #4–#12 were recorded only as `LEARNINGS.md`
entries while the work moved fast (a dozen runs in four days). This digest gives each a dedicated,
uniformly-structured section. **Every quantitative claim here is re-verified from that run's own
`runs/runN/oracle.jsonl` and `runs/runN_console.log`** (the RAM oracle is control/scoring only — never
an agent input). Deeper narrative lives in `LEARNINGS.md`; the conceptual synthesis in `INSIGHTS.md`._

**The arc in one paragraph.** Run #3 reached the rival battle but couldn't fight. Run #4 showed it
couldn't even reliably *reach* the battle — navigation, not fighting, was the wall — so we built **Phase
B** (translation odometry + a topological place-graph) and **run #5** validated it live (reached Oak's
lab) before aria's Anthropic **credits ran dry** mid-run. Runs **#6/#6b** isolated the battle with a
`.state` fixture: the fight *mechanism* worked but the agent **confabulated a confident, inverted
world-model** (believed it was Squirtle) and mashed A. Prompt fixes (**#7/#8**) failed — the confab was
too coherent for a nudge. **#9** (`--no-vision`) proved the **battle image** was the confab source;
**#10** (clean OCR, text-only) fixed the grounding; **#11** (decoded move menu) fixed move execution;
**#12 WON** — the first end-to-end rival-battle victory. Each step was the same move: **decode the
state, don't make the model read pixels.**

| Run | Date | What it tested | Oracle-verified outcome | Wakes | Cost |
|----|------|----------------|-------------------------|-------|------|
| #4  | 06-17 | Phase A battle (live) | **nav wall** — reached map 39 not 40, watchdog-halted | 14 / 398 | ~$0.11 |
| #5  | 06-17 | Phase B navigation | **reached Oak's lab (40)**; then 110 credit-out 400s | ~45 ok / 100 | ~$0.83 |
| #6  | 06-17 | isolated battle (fixture) | **all 30 wakes 400'd** — out of credits ($0 work) | 30 (all 400) | $0 |
| #6b | 06-17 | isolated battle (retry) | battle **mechanism works**; did NOT win (mashed A) | 30 | ~$0.25 |
| #7  | 06-19 | battle policy v2 | **crashed @ step 39** (buffered, no traceback) | — | ~$0.3 |
| #8  | 06-19 | battle policy v2 (clean) | **inverted confab**; didn't win (transient `in_battle`=0 glitch) | 50 | ~$0.4 |
| #9  | 06-19 | `--no-vision` A/B | **proved confab source = the battle IMAGE** | 50 | ~$0.3 |
| #10 | 06-20 | text-only + clean OCR | **confab FIXED** (correct grounding); didn't win (move exec) | 50 | ~$0.3 |
| #11 | 06-20 | + decoded move menu | move exec FIXED (**SCRATCH ×7, GROWL ×0**); cap-halted | 50 | ~$0.3 |
| #12 | 06-20 | higher cap | **WON** — `in_battle` 2→0 sustained @ step 70 | 73 / 300 | ~$0.5 |

All runs: clean-start (`reset_aria_memory.py --yes`, archived to `aria_memory_archives/iter-NNN`), the
decoupled aria/Haiku brain, screen-only perception. Runs #4–#8 ran with the battle image ON; #9–#12
`--no-vision`.

---

## Run #4 — the navigation wall (2026-06-17)

**TL;DR.** With Phase A (battle settle + belief nudge) committed, the bar was getting *through* the
rival battle. Instead the agent **never got the starter** — it walked into the wrong building and the
watchdog halted it. The battle policy was left **unexercised, not refuted**; the real wall was upstream
navigation.

**Config.** `play_pokemon.py --brain hybrid --perception` from `start.state`, watchdog on, recorded.

**Result (oracle `runs/run4/`, 398 rows).** `in_battle` 0 throughout (**never reached a battle**). Maps
seen `[0, 37, 38, 39]` — it entered **map 39 (the rival's house), not map 40 (Oak's lab)**, wandered
Pallet (270 of 398 steps), and the watchdog halted it after no map/cell/level/badge progress. **14
wakes / 398 steps (3.5%), 0 errors, ~$0.11** — guardrails worked exactly right (a stuck run stopped
cheaply, far under the $0.83 cap).

**What this established.** The failure was entirely the **dead-reckoning drift** in the occupancy map
(the pose-only model can't reliably pinpoint the single lab-door tile) — run #2 also failed to get the
starter here; run #3 reaching the battle was partly luck. **Decision: do Phase B (navigation) before
re-testing the battle**, and isolate the eventual battle test with a `.state` fixture.

**Artifacts.** `runs/run4.mp4`, `runs/run4/oracle.jsonl`, archive `iter-003_2026-06-17.zip`.

---

## Run #5 — Phase B navigation validated; credits ran dry (2026-06-17)

**TL;DR.** The rebuilt navigation (translation odometry + topological place-graph) **got the agent to
Oak's lab** — past run #4's wall — then aria's Anthropic credits ran out ~45 wakes in.

**Config.** `play_pokemon.py --brain hybrid --perception` from `start.state`, `--max-llm-calls 100`,
recorded.

**Result (oracle `runs/run5/`, 371 rows).** Maps `[0, 37, 38, 40]` — **reached map 40 (Oak's lab)**,
the run-#4 wall broken; perception held live (0 ping-pong, 1 minor {0,40} lump). It worked for ~45
wakes, then **110 credit-out 400s** in the console log (`"Your credit balance is too low to access the
Anthropic API"`) — no starter, budget-cap halt. ~$0.83 (the last of the balance).

**Honesty note (recorded as a methodology lesson).** In the moment I diagnosed the 400-burst as an
"aria context ceiling (~45 wakes)" *from the wake count alone* and committed that — **wrong**. Reading
the litellm container log (run #6) showed credit exhaustion. *Verify-before-claiming applies to your
own diagnoses: a wake-count correlation is not a root cause — read the actual error.*

**Artifacts.** `runs/run5.mp4`, `runs/run5/oracle.jsonl`, archives `iter-004/005`.

---

## Run #6 — isolated battle test; confirmed the credit exhaustion (2026-06-17)

**TL;DR.** Built `rival_battle.state` (a fixture parked at the rival battle) to test the battle policy
in a short run. **All 30 wakes 400'd from the first** — zero balance left after run #5.

**Config.** `play_pokemon.py --brain hybrid --perception` from `rival_battle.state`, cap 30.

**Result (oracle `runs/run6/`, 30 rows).** `in_battle` 2 throughout (parked at the battle), map 40.
Console log: **60 error hits** (all wakes 400'd). **$0 of useful work.** This both confirmed the run-#5
cause was *credits, not context* (a fresh tiny-context battle observation still 400'd instantly) and
left the battle policy validated only by the free `eval/verify_battle_settle.py`. Blocker: top up the
Anthropic account behind aria.

**Artifacts.** `runs/run6.mp4`, `runs/run6/oracle.jsonl`.

---

## Run #6b — battle mechanism validated; new bottleneck found (2026-06-17)

**TL;DR.** Credits restored. The reach+settle+act machinery **works** — the agent fought every turn on
stable battle screens — **but it did not win**: it mashed A and confabulated its own Pokémon.

**Config.** From `rival_battle.state`, cap 30. Image ON.

**Result (oracle `runs/run6b/`, 30 rows).** `in_battle` stayed **2** all 30 wakes (no win), 0 errors,
~$0.25. The first live proof of Phase A item 1 (runs #3–5 never got a testable battle). Two failures
the decoded text exposed: (1) **it mashed A** → alternated SCRATCH (attack) and GROWL (non-damaging) at
a type disadvantage (CHARMANDER vs SQUIRTLE) — *"first move default" ≠ an attacking move*; (2) the
**confabulation / belief gap** — it narrated having **Bulbasaur** and "defeating Squirtle" while the
decoded screen said `Go! CHARMANDER!` / `Enemy SQUIRTLE`. The `TRUST THE SCREEN` nudge didn't override
it.

**Takeaway.** Battle *mechanism* solved; battle *strategy* (pick a damaging move) and *belief-grounding*
are the next constraints — exactly what a probe should surface.

**Artifacts.** `runs/run6b.mp4`, `runs/run6b/oracle.jsonl`, archive `iter-006`.

---

## Run #7 — battle policy v2; crashed mid-run (2026-06-19)

**TL;DR.** A buffered stdout crash at step 39 lost the run's evidence — the process lesson that paid
runs must be unbuffered.

**Config.** v2 prompt (name your mon + pick a damaging move; stronger nudge) from `rival_battle.state`.
Image ON.

**Result (oracle `runs/run7/`, 39 rows).** `in_battle` 2; the run **hard-crashed at step 39 with no
traceback** because stdout was buffered. ~$0.3 spent, no clean verdict. From the salvaged 39 steps I
briefly saw all-SCRATCH and over-claimed "move-selection validated" — a lucky highlighted-move streak,
corrected by run #8.

**Lesson (recorded).** Run paid jobs with `python -u` so a crash leaves a traceback; verify-before-
claiming applies to your *own* preliminary read, not just the agent's narration.

**Artifacts.** `runs/run7.mp4.video.mp4`, `runs/run7/oracle.jsonl`.

---

## Run #8 — battle policy v2 (clean); the confab is a confident *inverted* world-model (2026-06-19)

**TL;DR.** The prompt fixes did **not** close the gap. The agent believed — confidently — that it was
the *water* type and reasoned from the inverted world. A north-star finding: a coherent wrong prior
can't be dislodged by a nudge.

**Config.** v2 prompt, clean, cap 50, from `rival_battle.state`. Image ON.

**Result (oracle `runs/run8/`, 50 rows).** It reasoned *"Water beats Fire — I'll use WATER GUN to
finish Charmander"* while the decoded screen said **its own mon is CHARMANDER, the foe is SQUIRTLE** —
identities **fully inverted**. It still mashed A (so the game used Charmander's real SCRATCH+GROWL under
a WATER-GUN fantasy). **Did not win.** *Honesty note:* the oracle shows `in_battle` touched 0
**transiently but never sustained** (`exit@None`) — that single-frame blip is the "win" I once
over-claimed; the data corrected it. 0 errors, ~$0.4.

**The deeper lesson.** Belief-grounding is harder than a prompt: the model builds an internally
consistent wrong model ("rival battle → I should have the type advantage → I'm water") and reasons from
it. Move selection is downstream of the confab. *Next lever:* the decoder reads the real names — so the
fix is to feed **clean state**, not nudge harder.

**Artifacts.** `runs/run8.mp4`, `runs/run8/oracle.jsonl`, archive `iter-008`.

---

## Run #9 — `--no-vision` A/B: the confab source is the battle IMAGE (2026-06-19)

**TL;DR.** The decisive experiment. With the battle image OFF and everything else identical, the
confident inverted confab **vanished** — proving Haiku was confabulating from the low-res sprites.

**Config.** Run #8's config **with `--no-vision`** (image off), cap 50, from `rival_battle.state`.

**Result (oracle `runs/run9/`, 50 rows).** `in_battle` 2 throughout (still grinding, no win). The
*content* is the result: the agent said **CHARMANDER ×19** (correctly, from decoded text) and **0**
"WATER GUN"/"Squirtle"/"water" — vs run #8's confident Squirtle belief. So the battle **image** was the
confab source (the founding Iteration-01 weakness — "Haiku confabulates from raw pixels" — resurfacing
in the one place we'd never decoded). **But text-only was unusable too:** the prompt still referenced a
screenshot (it kept saying *"I cannot see the screenshot"*) and the decoded enemy name was garbled
(`?O??RT?E`). *Conclusion: neither raw-image (confabulates) nor raw-text (garbled) works — the cure is
CLEAN DECODED TEXT.* 0 errors, ~$0.3.

**Follow-on (free, no ROM).** Completed the battle OCR via `eval/calibrate_battle.py` (auto-calibrate
from self-verified known words; +7 glyphs G/F/I/L/Q/S/U) and found the real stability bug — the
Hamming-`tol=4` fallback was misreading uncalibrated glyphs as confident wrong chars (Q→O); exact-only
gives an honest `?`.

**Artifacts.** `runs/run9.mp4`, `runs/run9/oracle.jsonl`, archive `iter-007`.

---

## Run #10 — text-only + clean OCR: confabulation FIXED (2026-06-20)

**TL;DR.** Image off + completed OCR + a text-only banner → the agent grounds **correctly**. The
bottleneck narrowed from "wrong world" to "can't operate the move menu."

**Config.** `--no-vision` + completed battle OCR + text-only banner, cap 50, from `rival_battle.state`.

**Result (oracle `runs/run10/`, 50 rows).** `in_battle` 2 (no win yet). Grounding is now correct — the
agent's own words: *"I'm sending out **Charmander** against Gary's **Squirtle** (bad matchup — Water
beats Fire)"*, *"Charmander wasted a turn on GROWL… pick **Scratch**."* The inverted confab is **gone**
(WATER GUN: 0). 0 errors, ~$0.3. **Remaining gap:** move EXECUTION — it understood the goal but the
menu nav still landed on GROWL ~2:1 over Scratch because it couldn't tell which move was **highlighted**.

**Confirms.** The battle image was the confab source; the cure is clean decoded **state**, not prompt-
nudging — the same move the project made for navigation.

**Artifacts.** `runs/run10.mp4`, `runs/run10/oracle.jsonl`, archive `iter-009/010`.

---

## Run #11 — decoded move menu: move execution FIXED (2026-06-20)

**TL;DR.** `decode_move_menu` (move list + ▶ cursor from pixels) let the agent see which move was
highlighted. It deliberately attacked — **SCRATCH ×7, GROWL ×0** — but the 50-wake cap halted it before
the type-disadvantaged grind finished.

**Config.** `--no-vision` + clean OCR + **decoded move menu**, cap 50, from `rival_battle.state`.

**Result (oracle `runs/run11/`, 50 rows).** `in_battle` 2 (cap-halted, not a loss). The agent reasoned
*"Move menu open with SCRATCH highlighted; pressing A to attack"* and used **SCRATCH ×7 / GROWL ×0** (vs
run #10's GROWL 29 / Scratch 12) — it read the decoded cursor and chose the damaging move every time.
Didn't win only because the fight is a slow type-disadvantaged grind at ~5 wakes/turn (battle woke every
step) → ~8–10 turns > 50 wakes. 0 errors, ~$0.3.

**Artifacts.** `runs/run11.mp4`, `runs/run11/oracle.jsonl`, archive `iter-011`.

---

## Run #12 — WON the rival battle, first time ever (2026-06-20)

**TL;DR.** Same config as #11 with a higher cap. The agent **beat Gary's Squirtle with Charmander
despite the type disadvantage**, got the Pokédex, and left the lab. Phase A "fight" is DONE end-to-end.

**Config.** `--no-vision` + clean OCR + decoded move menu, **cap 80**, from `rival_battle.state`.

**Result (oracle `runs/run12/`, 300 rows).** **`in_battle` 2→0 sustained at step 70** (the real win — a
sustained exit, not run #8's blip), then 230 steps of overworld; maps `[0, 37, 39, 40]` — beat Squirtle,
left the lab, explored Pallet. **73 wakes total, 0 errors, ~$0.5.** The full chain validated live:
confab (image) fixed → move selection (cursor) fixed → won → progressed past the battle.

**Two things the win also confirmed.** (a) **Battle is wake-heavy as predicted** — **~68 of the 73
wakes were the battle alone** (woken every step); the entire post-battle overworld cost ~5. *This is the
exact cost shape that battle auto-advance (run #13) targets.* (b) Post-battle it hit the **old lab-exit /
Pallet navigation wall** again (`[wake:stuck]` "trapped indoors") — the residual Phase-B gap, cleanly
separate from the now-solved battle.

**Artifacts.** `runs/run12.mp4`, `runs/run12/oracle.jsonl`, archive `iter-012`.

---

## What the arc proves (and where it points)

1. **The recurring fix is one principle:** *decode the state, keep the agent constant, wake the model
   only when it must decide.* Navigation (Phase B), confabulation (image→clean text), move selection
   (cursor decode), and cost (run #13 auto-advance) were all the same move at different layers.
2. **A small model builds internally-consistent wrong worlds** (run #8's inverted identity) that a soft
   prompt nudge cannot overturn — the lever is clean perceived state, not persuasion.
3. **Process discipline earned its keep:** verify against the oracle not the narration (and not your own
   preliminary read — runs #5, #7, #8 each corrected an over-claim); run paid jobs unbuffered; read the
   actual error (credits, not "context").
4. **Next:** the **learned blind-execute battle policy** (System-2→System-1; run #12/#13's repeated
   FIGHT→SCRATCH turns are the compile target) and a robust **lab-exit / Pallet navigation** pass.

_For run #13 (battle auto-advance, validated) see `2026-06-20-live-run-13-battle-auto-advance.md`._
