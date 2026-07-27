# GBA exam-oracle hunts: Emerald Oldale (EX03) + Kirby GBA Level 1-1 (EX04) — 2026-07-25

Status: **$0, offline, no paid run, no LLM.** Both hunts driven by direct Python scripts against
`core.gba_emulator.GBAEmulator` (mgba) under the proven WSL rig
(`reports/2026-06-29-gba-mgba-recipe.md`). Builds on, and does **not** redo, the verified parts of
`reports/2026-07-23-oracle-emerald-hunt.md` and `reports/2026-07-23-oracle-kirby-hunt.md`. Neither
oracle is wired into `world_mcp.py` — see "Next step" at the bottom; that file, `core/contracts.py`,
tool schemas, and both exam scorer stubs were **not touched**.

## Harness

- ROMs: `roms/gba/Pokemon - Emerald Version (U).gba`, `roms/gba/Kirby - Nightmare in Dreamland (U) [!].gba`
  (primary checkout's gitignored `roms/gba/`, read-only, not committed).
- Emulator: WSL `~/gba-spike` mgba 0.10.2 build, driven via `core.gba_emulator.GBAEmulator`
  (imported unmodified — no edits to `core/`).
- Driver/probe scripts (committed, this session): `reports/probes/2026-07-25-gba-exam/gba_drive.py`
  (generic load-state → apply button/wait tokens → screenshot + save-state + optional watch-address
  dump) and `run_gba.sh` (thin launcher setting `LD_LIBRARY_PATH`/`PYTHONPATH` per the recipe).
- A large trove of the **prior** 2026-07-23 session's own save-states and screenshots turned out to
  still be sitting in this machine's shared scratch temp dir (`emerald_hunt/oh/*.state`,
  `kirby/*.state` — not part of the repo, throwaway per convention). Where reusing one of those
  checkpoints saved re-driving an already-verified intro segment, this hunt loaded it directly
  (e.g. `emerald_hunt/oh/s26.state` = outside Littleroot post-truck, `kirby/gplay1.state` = start of
  Level 1-1 gameplay) instead of re-scripting the same button sequence from a blank boot.
- All screenshots in this report were read visually (eyes-on grading, David-authorized this
  session) — every location/verdict claim below is **model-graded, pending David's validation**,
  per the task's method discipline.
- Curated evidence screenshots are committed under
  `reports/probes/2026-07-25-gba-exam/evidence/{emerald,kirby}/`.

## Hunt 1 — EX03: Emerald, (map_group, map_num) for Oldale Town — **NOT FOUND (Oldale unreached); one new finding, one new caveat**

### What was re-confirmed (matches the 2026-07-23 banked report exactly)

| location | map_group | map_num | notes |
|---|---|---|---|
| truck interior | 0 | 9 | matches banked `{0,9}` |
| Littleroot outside (near truck, early) | 2 | 10 | matches banked `{2,10}` |
| house 1F | 2 | 15 | matches banked `{2,15}` |
| bedroom (house 2F) | 2 | 14 | matches banked `{2,14}` |

### New: Birch's Lab interior — FOUND
| location | map_group | map_num |
|---|---|---|
| Prof. Birch's Lab (interior) | 2 | 13 |

Reached by: exiting the house (see "drive path" below), routing around the two houses, entering
Birch's Lab building from the south door. Verified via screenshot (lab equipment, assistant NPC,
"Hunh? PROF. BIRCH... The PROF's away on fieldwork..." dialogue) — `evidence/emerald/05_lab_interior_num13.png`.

### New, important finding: **outdoor "Littleroot Town" map_num is NOT a stable single value**

This is the headline result of this hunt, and it's the reason Oldale's own value can't yet be
trusted even if reached: standing in different parts of the *same, visually contiguous* Littleroot
Town exterior gave **three different `map_num` readings**, while `map_group` stayed `2` throughout:

| outdoor location (still Littleroot, still outside) | map_group | map_num |
|---|---|---|
| next to the truck, right after emerging (early game) | 2 | 10 |
| between the two houses / in front of own house, post clock-set | 2 | 12 |
| directly outside Birch's Lab door | 2 | **14** |

The third row is a genuine collision: **outside-near-the-lab reads the identical `(2, 14)` pair as
the bedroom interior**, confirmed by two independent fresh reads
(`evidence/emerald/04_bedroom_num14.png` vs `evidence/emerald/06_outside_near_lab_num14_collision.png`)
each re-verified after an extra settle wait (not a mid-transition artifact — both screenshots show
fully-rendered, unambiguous scenes: one is clearly the upstairs bedroom, the other is clearly
outdoor grass next to the lab's telescope-dome roof).

Every value was reproducible on repeat sampling at its own location (stable across multiple
re-reads with waits in between), so this is **not** frame noise — the address is locally stable but
**not globally unique to "the current map"**. No mechanism is claimed here (candidates like "nearest
warp/door target" were considered but not conclusively tested) — this is reported as an open,
falsifying observation per the project's Cave Noire lesson: a coincidental 2-sample match on the
interiors did NOT extend to the exterior, and that must be flagged, not glossed over.

**Consequence for EX03:** even if Oldale is reached and yields a clean-looking `(map_group,
map_num)` reading, that reading cannot be trusted as "this means Oldale" without the exact
same falsification battery applied to Littleroot's own outdoor value — which this hunt shows is
necessary and was previously skipped (the 2026-07-23 report's "12 snapshots" were all interiors +
one early outdoor sample; it never varied the outdoor sampling location).

### Drive path (this session)

Truck → exit into Littleroot outside (reused `emerald_hunt/oh/s26.state`, itself reached via the
2026-07-23 session's own boot→intro→truck-exit sequence) → **into the player's house** (a scripted
event — the house entry is not skippable, confirmed by testing all 4 directions from the truck-exit
doorstep: every one leads inside) → talked to Mom, went upstairs, **set the clock** (the "Is this
the correct time?" Yes/No prompt defaults its cursor to **NO** — same UI trap as the Mom dialogue
below; confirming requires pressing Up once before A) → back downstairs → Mom's post-clock dialogue
(TV interview about Dad) → **exited the house successfully** (Mom no longer blocks the door once the
clock flow completes — this differs from the 2026-07-23 report's stuck point, which never got this
far) → into Littleroot Town proper, freely walkable → routed to Birch's Lab (confirmed interior) →
approached the single gap in the north hedge line (the only connection toward Route 101; west and
east edges of town were explicitly walked and are solid hedge, no other gap exists).

### Blocked: Route 101 entrance — a hard, in-game story gate, not a navigation puzzle

The one hedge gap north is permanently occupied by an NPC (the player's neighbor/rival) who repeats,
on every approach and interaction: *"Um, um, um!♥"* → *"If you go outside and go in the grass... it's
dangerous if you don't have your own POKéMON."* (`evidence/emerald/07_route101_gate_blocked_dialogue.png`,
`08_route101_gate_blocked_dialogue2.png`). Tested and eliminated:
- Approaching from every reachable column of the gap (left-of-center, center, right-of-center):
  always ends adjacent to her, dialogue repeats verbatim.
- Waiting stationary up to 3000 frames (~50s) at the gap and in town center: no scripted
  Birch/Zigzagoon cutscene fires on a timer.
- Visiting Birch's Lab first (learning "PROF's away on fieldwork") then re-approaching: no change.
- Talking to her via direct `A` vs. bump-walking into her: same dialogue either way.
- 5 repeated approach/retreat cycles: dialogue never varies or advances a hidden counter.

This matches Emerald's actual game design: Oldale Town is unreachable until the player obtains a
starter Pokémon via Prof. Birch's rescue event (normally triggered on Route 101 itself, which this
NPC's fixed position blocks entirely). That event requires a wild-Pokémon battle — a materially
larger quest than "drive through the intro," and was not completed this session.

### Verdict: NOT-FOUND (Oldale)
Oldale Town's `(map_group, map_num)` remains unpinned. Emerald's Littleroot-area interiors
(truck/house1F/bedroom/lab) are solid; Littleroot's *outdoor* `map_num` is shown unstable/context-
dependent and must not be trusted as a "current town" oracle without further work. Reaching Oldale
requires completing the starter-Pokémon acquisition sequence first — flagged as the concrete next
step, not attempted further this session due to time budget.

## Hunt 2 — EX04: Kirby GBA, what marks LEVEL 1-1 COMPLETE — **NOT FOUND (goal door unreached)**

### Re-verified via live continuous play (stronger than the banked snapshot evidence)

The 2026-07-23 report anchored `score @ 0x02006020` (u32) and the `world` candidate
`@ 0x02006014` (u8, constant `=1`) from **disconnected** RAM snapshots (score 0 / 1600 / 2600 taken
from separately-reached states, not one continuous run). This session drove Level 1-1
**continuously** from the reused `kirby/gplay1.state` checkpoint (score 0, full HP,
`evidence/kirby/01_level1_1_start_score0.png`) forward through real scripted play (right + jump/float
via repeated `A` taps — `A` is jump/float in this game, not `B`; `B` presses alone produced no visible
effect, consistent with `B` being inhale with nothing in front of Kirby to inhale):

| checkpoint | score | world | notes |
|---|---|---|---|
| level start | 0 | 1 | `evidence/kirby/01_level1_1_start_score0.png` |
| after first enemy/item | 600 | 1 | |
| further right | 1200 | 1 | `evidence/kirby/02_score1200.png` |
| past a tall solid-wall obstacle (cleared via sustained float over it) | 2200 → 2800 | 1 | `evidence/kirby/03_score2800_cleared_wall.png` |
| stuck point (see below) | 2800 | 1 | `evidence/kirby/04_stuck_at_obstacle_score2800.png` |

`world` stayed bit-exact `=1` across every one of these live, continuously-advancing samples —
strictly stronger confirmation than the banked report's snapshot-based reading, but it still says
nothing about level-completion since the level was never cleared.

### Blocked: a solid obstacle at score 2800, mirroring the banked GB-version precedent

After clearing one tall wall by floating over it (repeated `A` taps → sustained altitude → hold
`right`), a second obstacle (a stationary dark object, likely a Gordo-type hazard) at score 2800
could not be passed: neither ground-level `right`, nor jumping over it at various heights/arcs, nor
crouching (`down`), advanced Kirby's position or score in ~10 varied attempts
(`evidence/kirby/04_stuck_at_obstacle_score2800.png` — same frame repeats across attempts). This
directly parallels the 2026-07-23 report's own finding for the **GB** Kirby's Dream Land version
("a tall solid-wall obstacle... resisted scripted flight"), and the cited prior **paid $43 Opus
587-decision run** that also never beat GB Stage 1 — corroborating that this class of obstacle is a
genuinely hard scripted-play problem, not specific to one console version or one session's
technique.

### Verdict: NOT-FOUND (level-1-1-complete marker)
The level's end (goal/door) was not reached, so `0x02006014` could not be tested for an
increment-on-clear, and no RAM diff across a level-complete transition could be taken (there was no
transition to diff). Per the task's own instruction, this is reported as NOT-FOUND rather than
guessed: the `world`-index candidate is **re-confirmed stable through deeper live play** but
**remains unverified as a level-complete flag** — a future attempt needs either a better scripted
platforming pass (or a save-state placed just before the goal door, if one exists in this machine's
scratch history — none was found among the reused `kirby/*.state` checkpoints, all of which sit
strictly before or at this session's own stopping point).

## What was eliminated (both hunts)

- Emerald: static-NPC route block is not resolved by waiting, by re-approaching, by talking vs.
  bumping, or by visiting the Lab first — eliminated as candidates for "the trigger."
- Emerald: outdoor `map_num` single-value hypothesis — falsified (3 different values for one
  visually-contiguous outdoor area).
- Kirby GBA: `B` as the primary action button — eliminated (no observed effect without an
  inhale target); `A` confirmed as jump/float.
- Kirby GBA: ground-level walk/jump past the score-2800 obstacle — eliminated after ~10 attempts
  at varied jump timings/heights.

## IMPORTANT — oracles NOT wired

Per the task, `world_mcp.py`'s `GAMES[...]["watch"]` for `emerald_gba` and `kirby_gba` was **not**
touched, `core/contracts.py` / tool schemas were not touched, and both exam scorer stubs
(`eval/score_exam_emerald_oldale.py`, `eval/score_exam_kirby_gba_level1.py`) were **not** edited —
neither oracle in this report is confirmed enough to wire in anyway (both hunts ended NOT-FOUND on
their primary target). Wiring is a separate, later, batched step timed with the next Gate-0 world-
image rebuild, same as the emerald/kirby `map_group`/`map_num`/`x`/`y`/`world`/`score` fields banked
2026-07-23.

## Next step (for whoever picks this up)

1. **Emerald:** complete the starter-Pokémon acquisition (Birch/Zigzagoon rescue on Route 101) from
   a fresh Littleroot-outside state, then re-run the outdoor-map_num falsification battery (multiple
   locations, save/reload) at Oldale specifically before trusting any reading there.
2. **Kirby GBA:** either grind past the score-2800 obstacle with a more careful frame-by-frame
   platforming pass, or locate/create a save-state positioned closer to Level 1-1's goal door to
   avoid re-doing the same early obstacles every attempt.

## Suite

Full repo suite green after this change (2026-07-25), run from the `probe/gba-exam-oracles`
worktree:
```
1592 passed, 16 skipped in 61.81s
```
