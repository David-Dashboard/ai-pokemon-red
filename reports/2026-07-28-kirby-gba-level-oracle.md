# Kirby GBA (EX04) level-oracle hunt — stage 1-1 CLEARED, one candidate, **not settled** (2026-07-28)

Status: **$0, offline, no paid run, no LLM, no network.** Supersedes the Kirby half of
`reports/2026-07-25-oracle-gba-exam-hunts.md` (PR #170), which ended NOT-FOUND with the level
unbeaten. Nothing is wired: `world_mcp.py`, every `watch` dict, `core/contracts.py`, tool schemas and
`eval/score_exam_kirby_gba_level1.py` are **untouched** — deliberately, per the task's hard
constraint (edits to `world_mcp.py` cascade into the frozen Gate-0 pins).

## Verdict in one line

**Candidate found, NOT confirmed as a counter.** `0x030023ec` (u8, IWRAM) reads **0** in every
observed stage-1-1 state and **1** in every observed stage-1-2 state, is the **only** index-shaped
address in either RAM region with that behaviour, and holds across 222 hand-checked samples
(457/457 of the full corpus) spanning ~15,700 frames of ordinary play — but only **TWO distinct
values were reachable**, so the task's own three-anchor rule is **not met**: a 1-bit "you are not in
the level's first stage" flag is not excluded.

Two bounds, both found by adversarial review of the first revision of this report and both now
load-bearing: the value means **"most recently entered stage"**, not "stage you are inside" (it
reads 1 on the GAME OVER menu — an earlier revision of the trace table got this backwards), and it
survives the uniqueness sweep **only** when game-over frames are grouped with stage 1-2. Grouping
them the other way leaves zero survivors in all of RAM.

## Game and ROM

`kirby_gba` in `world_mcp.py:182-186` → `roms/gba/Kirby - Nightmare in Dreamland (U) [!].gba`
(8 MiB, gitignored, read from the primary checkout; not committed). Structure: **Level 1 = Vegetable
Valley** (the HUD banner reads `LEVEL 1: VEGETABLE VALLEY`), containing numbered **stages** 1, 2, …
entered from a walkable world map. EX04's "Level 1-1" is Vegetable Valley **stage 1**.

## Did the GBA harness run on this Windows host? — **YES**

The WSL mgba spike from `reports/2026-06-29-gba-mgba-recipe.md` is intact and works here:
`~/gba-spike/{libmgba_patched.so.0.10.2, .venv/bin/python3, mgba-build/python/lib.linux-x86_64-3.8}`
all present; `core/gba_emulator.GBAEmulator` loads the ROM, ticks, reads RAM, screenshots and
round-trips savestates unmodified. Every number below came from real emulation on this machine.
(mgba still logs BIOS SWI chatter to **stdout**, interleaving with the driver's JSON — expected,
per the recipe.)

## New tooling (the reason this hunt got further than the last one)

1. **Savestate RAM layout — measured, not assumed.** An mgba raw GBA state is 0x61000 bytes. Both
   RAM regions sit at fixed file offsets, so every `.state` on disk is a complete RAM snapshot that
   can be swept **offline on Windows with no emulator at all**:

   | region | GBA address | savestate file offset | length |
   |---|---|---|---|
   | IWRAM | `0x03000000` | `0x19000` | `0x8000` |
   | EWRAM | `0x02000000` | `0x21000` | `0x40000` |

   Verified by reading 7 probe words live through `GBAEmulator.read()`
   (EWRAM `0x02000000/0x02020000/0x0203FFFC/0x02006020`, IWRAM `0x03000000/0x03004000/0x03007FFC`)
   and matching them byte-exact against the file at those bases. Two alternative IWRAM bases
   (`0x1000`, `0x800`) were tested and **rejected** — this is a measurement, not a guess.
   **Both regions were swept**, always.
2. **Button combos.** `reports/probes/2026-07-28-kirby-gba-level-oracle/kgba_drive.py` adds a
   `combo:` action driving `set_keys(raw=...)` with an OR-ed bitmask. The Emulator Protocol's
   `press()` is one button at a time, which cannot express "hold right while tapping A" — the only
   way Kirby crosses anything. This reaches into the private `_core` and is confined to the probe;
   `core/` is untouched, and no oracle claim depends on it (combos change **which** states we reach,
   never what RAM says once there).
3. **Offline sweeper** `kgba_ram.py` with a `cands` mode: given groups of states, keep addresses
   **constant within every group and distinct across groups**. Within-group variation kills timers,
   RNG, camera/physics scratch and animation counters with no hand-picked whitelist.

## The play breakthrough — the 2026-07-25 blocker was a door, not a hazard

PR #170 stopped at "a stationary dark object, likely a Gordo-type hazard" at score 2800 and
eliminated `right`, jumps at varied heights, and `down`. Loading that exact banked state
(`gbaexam0725_kirby/gr7.state`) and zooming shows the object is the room's **exit door** — a black
arch ringed with sparkles — sitting immediately to Kirby's **left**, with Kirby having walked past
it to the level's right boundary (evidence `01_...png`). Doors are entered with **`up` while
standing aligned with them**; #170's own list of what it eliminated at that spot is "ground-level
`right`, jumping at various heights/arcs, and crouching (`down`)" — `up` is absent from it. Walking
left 22–34 frames then `up` transitions the room every time (`02_...png`); 14–18 frames does not,
so the door has a narrow alignment window either way.

With that, stage 1-1 was played to completion for the first time in this project: 3 doors, the goal
door, the star/goal sequence, and the `LEVEL 1: VEGETABLE VALLEY` world map
(`03_...png`, `04_...png`). Stage 1-2 was then entered from the map (`05_...png`).

**Door detector, and its assumption tested separately.** Transitions were detected by counting
changed EWRAM 32-bit words between the pre-press and post-press states. The threshold was **not**
chosen to make the answer come out — it was calibrated first against four already-eyes-on-verified
presses:

| press | churn (changed EWRAM words) |
|---|---|
| door 1 entered | 1572 |
| door 1, 8px short — no entry | 2 |
| door 2 entered | 1452 |
| door 2, overshot — no entry | 14 |
| goal door entered | 3538 |
| goal door, overshot — no entry | 12 |

Three orders of magnitude of separation. **Where it fails, stated plainly:** churn cannot separate
"door" from "died and the room reloaded" — in the stage-1-2 sweep four presses scored 627–2970 and
turned out on inspection to be falls into a pit. The detector is a *screening* tool; every
transition claimed above was confirmed by looking at the frame.

## The candidate

**`0x030023ec` — u8, IWRAM.**

### Value trace

| anchor | scene | `0x030023ec` |
|---|---|---|
| stage 1-1, first playthrough (5 rooms, score 0→8800) | in-stage | **0** |
| stage 1-1 goal / star sequence | clear cutscene | **0** |
| Vegetable Valley map, immediately after clearing 1-1 | map | **0** |
| Vegetable Valley map, after a GAME OVER → CONTINUE | map | **0** |
| **stage 1-1 re-entered from the map after clearing it** | in-stage | **0** |
| post-continue `LEVEL 1: VEGETABLE VALLEY` title card | title card | **0** |
| stage 1-2 (entry, mid-stage, deep rooms, mini-boss arena) | in-stage | **1** |
| **GAME OVER menu, after dying in stage 1-2** | menu | **1** |

> **Correction (2026-07-28, post-review).** An earlier revision of this table claimed the GAME OVER
> screen reads **0**. That was **wrong** — it came from reading `b1_r25.state`, which is the
> *post-continue level title card*, and mislabelling it "GAME OVER screen". The actual GAME OVER
> menu frames (`b1_r18`–`b1_r23`, the ones in `evidence/07_gameover_continue.png` and
> `evidence/08_gameover_frames_read_1.png`) all read **1**. Re-verified two ways: savestate
> file-offset reads of all six, and the frame-by-frame `b1_r17`→`b1_r25` sequence, which shows the
> value flipping 1→0 only at `b1_r24`, the fade back to the world map. The corrected reading is
> **"the most recently entered stage"**, not "the stage you are currently inside" — see
> "What is NOT established" §4.

The **re-entry row is the load-bearing one**: it eliminates the "past the first level" latch the task
warns about. A latch set by clearing 1-1 would still read 1 when 1-1 is replayed; this reads 0 again.
It also shows the address is a **current-stage index, not a stages-cleared count** — it is 0 on the
map *after* the clear.

### Uniqueness — the whole of both RAM regions, at three widths

Exact group membership is committed in `reports/probes/2026-07-28-kirby-gba-level-oracle/groups.md`
so these counts are checkable, not merely reproducible in spirit. Three groups:

- **S11** (23 states, all read 0) — 5 distinct rooms of stage 1-1, the goal sequence, both world-map
  states, the stage-1-1 replay *after* clearing it, and the post-continue title card.
- **S12** (21 states, all read 1) — stage 1-2 across four independent playthroughs incl. the
  mini-boss arena.
- **GO** (6 states, all read 1) — the GAME OVER menu after dying in stage 1-2.

Because the GAME OVER menu reads **1**, which side it belongs on is a real modelling choice, and the
answer differs sharply. **Both designs are reported:**

| design | zero side | one side | u8 | u16 | u32 | index-shaped `[0,1]` |
|---|---|---|---|---|---|---|
| **A** — GO grouped with stage 1-2 ("most recently entered stage") | S11 | S12 + GO | **4** | **3** | **2** | **1** — `0x030023ec` |
| **B** — GO grouped with the zero side ("game over is not in a stage") | S11 + GO | S12 | **0** | **0** | **0** | none |

**Design B kills the candidate — and every other address.** Zero survivors across 288 KB of RAM at
all three widths means no address anywhere behaves that way: "game over is not in a stage" is simply
not a distinction this game's RAM draws. That is a **bound on the candidate, stated plainly**:
`0x030023ec` survives *only* under the Design-A reading, and anyone wiring it must accept that
reading. It is not a disqualification, but it is not free either.

Under Design A the three non-candidate u8 survivors are `0x03006b29` and `0x03006b2b` (bytes 1 and 3
of the 32-bit field at `0x03006b28`, `0x1600` → `0x1200`) plus `0x03006b2c` (byte 0 of the
**adjacent** field at `0x03006b2c`) — two neighbouring struct fields, not one, and neither
index-shaped. (An earlier revision said "three non-zero bytes of a single 32-bit field at
`0x03006b28`"; that was wrong — `0x03006b2c` is outside that word.)

For contrast: with only the two in-stage groups and no map/replay/title-card states in the zero
group, 402 u8 addresses survive — most of them one-way "has-been-initialised" latches. Adding scenes
from *later* in the session to the zero group is what collapses 402 → 4.

### Sustained hold — 222 samples, not 4 frames

Not a transient title-card id. Every savestate in five dense chains of ordinary scripted play was
read:

| chain | scene | n | values seen |
|---|---|---|---|
| a1, a2, a3, a4 | stage 1-1, four consecutive room-crossing runs | 98 | `{0: 98}` |
| rp2 | stage 1-1 replayed after clearing | 9 | `{0: 9}` |
| c1 (two segments), c2, s12, bx | stage 1-2, four independent runs incl. mini-boss | 115 | `{1: 115}` |

222/222 consistent, spanning emulator frames 7,670 → 23,414 (~15,700 frames, ~4.4 min of gameplay),
across room changes, deaths, damage, a game-over/continue, and a mini-boss fight.

Widening to **every savestate on disk** (all 457, no grouping, no cherry-picking) the tally is
**255 × `1` / 202 × `0`** — still exactly two values, never a third. The 222-sample figure above is
the conservative subset restricted to states whose scene was individually eyeballed.

## What is NOT established — read this before trusting the address

1. **Only two distinct values were reached (0 and 1).** The task's three-anchor rule is **not met**.
   `0x030023ec` is consistent with a 0-indexed current-stage counter *and* with a 1-bit flag
   ("current stage is not the level's first"), and nothing here separates them. Calling it a
   counter now would repeat exactly the error the EX02 hunt made.
2. **Stage 1-3 was not reached** — it needs stage 1-2 cleared, and 1-2 was not cleared. Scripted
   play crossed 1-2's opening rooms, reached the Poppy-Bros-Sr.-type **mini-boss** (BOSS bar on
   screen), and died there. A greedy scripted search (10 macros/iteration, objective = Kirby's world
   X at `0x030021ce` u16, itself identified this session) walls at X=991 on 1-2's upper route.
   **This is the same wall PR #171 already named: the Kirby lane is gated on play capability, not on
   RAM hunting.** One stage of that gate has now been broken; the next has not.
3. **No "stages cleared" progress value was identified.** A separate sweep for a value that changes
   *because* 1-1 was cleared (before-group = pre-clear 1-1 states, after-group = map + 1-2 + replay +
   game-over) leaves **888 u8 candidates** — no identification. This design cannot exclude one-way
   initialisation latches, because the before-group is by construction all early states. Reported as
   NOT-FOUND rather than guessed.
4. **Consequence for the EX04 scorer — WHEN you sample is load-bearing.** (Corrected post-review;
   also lifted into the PR body and `HANDOFF.md`, because a wiring session that reads only the PR
   would otherwise miss it.)

   The correct reading is **"the most recently entered stage"**, *not* "the stage you are currently
   inside" — it still reads 1 on the GAME OVER menu after dying in 1-2, when Kirby is inside no
   stage at all. Two consequences, and they pull in opposite directions:

   - **The good half.** `== 1` is still *sound evidence that 1-1 was cleared*, because stage 1-2's
     map node cannot be entered until stage 1 is cleared. The inference "value is 1 ⇒ the agent
     entered 1-2 ⇒ the agent cleared 1-1" holds on every state observed, including the game-over
     frames.
   - **The dangerous half.** The byte is **not a latch** — it returns to 0 on the world map, which
     is exactly where the agent lands the instant it clears 1-1. So a "did the agent clear 1-1"
     predicate built on it is **sampling-time dependent**, and a scorer that polls at the wrong
     moment reads 0 on a run that genuinely succeeded.

   | predicate | verdict |
   |---|---|
   | `any(row == 1 for row in the whole run's oracle log)` | **SAFE** — monotone in evidence; one sighting of 1 anywhere proves 1-2 was entered, hence 1-1 cleared. This is the predicate to wire. |
   | sampled **at end of run** only | **UNSAFE** — reads 0 if the run ends on the world map, on the title card, or before re-entering a stage |
   | sampled **on the world map** | **UNSAFE** — always 0 there, including immediately after the clear |
   | sampled **once, at the moment 1-1 is cleared** | **UNSAFE** — 0 at the goal sequence *and* 0 on the map afterwards; the clear itself is never marked |
   | `== 1` read as "currently inside stage 1-2" | **WRONG** — also true on the GAME OVER menu |

   Note what the SAFE predicate actually scores: "cleared 1-1 **and then entered** 1-2". That is
   strictly stronger than EX04 as written, and whether to accept it is a decision for whoever
   freezes the exam, not for this probe.

### Alternative hypotheses this hunt could NOT exclude

| hypothesis | status |
|---|---|
| 1-bit "not the first stage of the level" flag | **NOT excluded** — the core gap; needs a stage-1-3 anchor |
| room index within a stage | **excluded** — held 0 across 5 distinct rooms of 1-1 and 1 across ≥4 distinct rooms of 1-2 |
| "past the first level" latch | **excluded** — reverts to 0 when 1-1 is replayed after being cleared |
| "levels cleared" counter | **excluded** — 0 on the map after 1-1 was cleared, and a game-over/continue did not change it |
| music track id | **not excluded** — 1-1 and 1-2 plausibly use different tracks; no music anchor was taken |
| tileset / graphics bank id | **weakened, not excluded** — 1-1 and 1-2 share the grass and rocky/waterfall tilesets and the value did not follow the tileset, but the value is also constant per stage, so a per-stage asset-set id is still consistent |
| checkpoint counter | **not excluded** — no mid-stage checkpoint was crossed twice |
| stack/scratch coincidence (IWRAM `0x030023ec`) | **not excluded** — it is IWRAM; a stable-looking value could be a live struct field rather than a persistent global |

## Reproduce

Scripts: `reports/probes/2026-07-28-kirby-gba-level-oracle/`
(`kgba_drive.py`, `run_kgba.sh`, `kgba_ram.py`). Curated frames: `.../evidence/`.
**Exact group membership for every count above: `.../groups.md`.**
Savestates (457 of them) live in this session's throwaway scratch dir, per convention — not
committed, not under `runs/`; `groups.md` names the ones each count depends on.

```
# drive (WSL): wsl.exe -e bash run_kgba.sh --plan /mnt/c/.../plan.json
# sweep (Windows, no emulator):
python kgba_ram.py cands u8 "<zero-group states>" "<one-group states>"
python kgba_ram.py trace 0x030023ec:u8 <states...>
```

## Next step

Clear Vegetable Valley **stage 1-2** (mini-boss + the rooms past it + its goal door), enter stage
1-3, and read `0x030023ec` there. If it reads **2**, it is a stage counter and EX04 has an oracle.
If it reads 1 or 0, it is a flag and the hunt continues. Everything else — uniqueness, sustained
hold, latch elimination, both-region sweep — is already done and banked here.
