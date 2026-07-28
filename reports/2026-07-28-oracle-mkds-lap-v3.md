# MKDS lap-count oracle hunt v3 — $0 offline. Verdict: **FOUND — but it is NOT a fixed address**

Third pass at the EX05 lap oracle, after `2026-07-11-mkds-oracle-hunt.md` (NOT FOUND),
`2026-07-23-oracle-mkds-lap.md` (NOT FOUND) and `2026-07-25-oracle-mkds-lap-v2.md` / PR #168
(NOT FOUND).

**The lap counter is found.** It is element 0 of an 8-element per-racer array of stride `0x8C`
(140 bytes) holding each racer's **current lap number** — the numerator of the on-screen
`LAP n/3`. For the banked savestate `runs/nds3d_probe/mkds_race_start.state` the player's byte
is at **`0x0236A7F2`**.

**But `0x0236A7F2` is not a constant.** Tested this session: after quitting to the menu and
entering a fresh race, the same array is at **`0x0237BED2`** — a shift of `0x114E0` (70,880
bytes). A hard-coded address would silently read garbage in any race other than the one the
savestate captures. What is portable is the *array's structure plus a causal confirmation step*,
not the number. §9 gives a working per-race locator; §11 gives the wiring consequences.

`eval/score_exam_mkds_lap.py` is **left unchanged** and still refusing (`ORACLE_PENDING`,
`main()` returns 1). Per this session's hard constraint, **nothing is wired**: no edit to
`world_mcp.py`, no `watch = {}` entry, no scorer change.

---

## 1. What unlocked it: stop driving, watch the CPUs

Every previous hunt failed for one reason, and it was never a RAM-analysis reason: **no lap
boundary was ever reached**, because a blind agent cannot drive Figure-8 Circuit. PR #168 burned
~15,000 frames and ~60 emulator invocations of vision-guided piloting and never got the player
past `LAP 1/3`, so there was nothing to diff.

But a Grand Prix has **eight** karts, and the seven CPU racers drive themselves. Left completely
alone, they complete all three laps in about three minutes of race time. **The lap counter can be
found without driving at all** — you only have to let the race run and watch the whole of RAM.
That turned a multi-session navigation problem into a ~6-minute sweep.

## 2. Harness ($0, offline, no Docker, no paid LLM, no network)

Same assets as the previous hunts: ROM `roms/nds/Mario Kart DS (USA) (En,Fr,De,Es,It).nds`,
savestate `runs/nds3d_probe/mkds_race_start.state` (Figure-8 Circuit, 50cc, GP standing start),
native `.venv-win` py-desmume, `core.nds_emulator.DeSmuMEEmulator`. ROM and savestates
referenced by absolute path in the primary checkout — never copied, never committed, and
**nothing under `runs/` was modified**. Worked in worktree `../ai-pokemon-red-mkds28` on branch
`probe/mkds-lap-oracle-2026-07-28` (the `../ai-pokemon-red-mkds` path was already occupied by
PR #168's worktree). One DeSmuME instance per process throughout.

Measured: **~114–127 fps** headless; a full 4 MB main-RAM slice read costs **~1.26 s**
(py-desmume reads it one ctypes call per byte), so full-RAM snapshots have to be budgeted;
`load_state` is cheap at **~78 ms**.

Probe scripts: `reports/probes/2026-07-28-mkds-lap-oracle/`.

## 3. The sweep

`sweep_pass1.py` ran the savestate forward **30,000 frames (~8 min race time) with zero input**,
sampling the **entire** `0x02000000`–`0x023FFFFF` region every 300 frames and keeping only
incremental per-address statistics (first/last/min/max/n-changes/never-decreased/max-step). A
lap counter must be monotone non-decreasing with very few ticks and a tiny span:

| filter | survivors of 4,194,304 |
|---|---|
| TIER-A: never decreased, 2–10 changes, every step exactly +1, span ≤ 8 | **34** |
| TIER-B: never decreased, 2–20 changes, step ≤ 3, span ≤ 12 | **52** |

Inside TIER-A sat an unmistakable periodic block — **seven** addresses at a constant stride of
`0x8C`, each tracing `1 → 2 → 3` with exactly two changes:

```
0x0236A87E  0x0236A90A  0x0236A996  0x0236AA22  0x0236AAAE  0x0236AB3A  0x0236ABC6
```

Seven racers, a three-lap race. The **eighth** slot is missing for the obvious reason: it is the
player's, the player never completed a lap, so it never changed and the `n_changes >= 2` filter
dropped it. One stride below the first hit is `0x0236A87E - 0x8C = 0x0236A7F2`, reading a
constant **1** — exactly `LAP 1/3`. One stride above the last hit (`0x0236AC52`) reads a constant
**0**, i.e. past the end of the array.

`pass2_window.py` then replayed the identical 30,000 frames recording a dense trace of
`0x0236A600`–`0x0236AE00` every 30 frames; §4–§6 come from that.

## 4. Evidence 1 — the value trace (three distinct values, seven independent racers)

| slot | address | trace |
|---|---|---|
| 0 (player) | **`0x0236A7F2`** | `1` for all 30,000 frames (player never completed a lap) |
| 1 | `0x0236A87E` | `1` → **`2` @f4080** → **`3` @f8280** |
| 2 | `0x0236A90A` | `1` → `2` @f3930 → `3` @f7590 |
| 3 | `0x0236A996` | `1` → `2` @f3630 → `3` @f7170 |
| 4 | `0x0236AA22` | `1` → `2` @f4050 → `3` @f8250 |
| 5 | `0x0236AAAE` | `1` → `2` @f3360 → `3` @f6990 |
| 6 | `0x0236AB3A` | `1` → `2` @f3750 → `3` @f7380 |
| 7 | `0x0236ABC6` | `1` → `2` @f3900 → `3` @f7560 |

Three distinct values, and the seven racers tick at seven **different, staggered** times spread
over ~700 frames — what a real race looks like, and what a global scene/mode/music id could not
look like. This clears the "a latch is not a counter" bar; see §8 for the honest caveat about
*whose* byte was observed doing it.

## 5. Evidence 2 — uniqueness: 1 address out of 4,194,304

`uniqueness.py` replayed the same deterministic trajectory, snapshotted the **entire 4 MB** at
ten anchor frames, and counted addresses matching slot 1's exact expected pattern:

```
frames   1500 3000 4050 | 4080 6000 8250 | 8280 12000 20000 29970
pattern     1    1    1 |    2    2    2 |    3     3     3     3
```

| after anchor | survivors |
|---|---|
| f1500 (`==1`) | 96,187 |
| f3000 (`==1`) | 96,023 |
| f4050 (`==1`) | 95,981 |
| **f4080 (`==2`)** | **2** |
| f8280 (`==3`) | 2 |
| f12000 (`==3`) | **1** |
| … through f29970 | **1** |

Final: **1 of 4,194,304** — `0x0236A87E`, the address itself. The single constraint "this byte
becomes 2 within a 30-frame window around f4080" collapses 96,000 candidates to 2; the full
pattern leaves exactly one.

## 6. Evidence 3 — sustained hold (not a transient)

| slot | holds `1` | holds `2` | holds `3` |
|---|---|---|---|
| 0 (player) | 30,000 f | — | — |
| 1 | 4,080 f | 4,200 f | 21,720 f |
| 2 | 3,930 f | 3,660 f | 22,410 f |
| 3 | 3,630 f | 3,540 f | 22,830 f |
| 4 | 4,050 f | 4,200 f | 21,750 f |
| 5 | 3,360 f | 3,630 f | 23,010 f |
| 6 | 3,750 f | 3,630 f | 22,620 f |
| 7 | 3,900 f | 3,660 f | 22,440 f |

Lap 1 and lap 2 each hold for 3,300–4,200 frames (≈56–70 s, a plausible 50cc Figure-8 lap), and
value `3` then holds for **21,700+ frames** — six minutes, well past the CPUs finishing. Not a
scene-transition id sampled for four frames.

## 7. Evidence 4 — which slot is the *player*, established by intervention

Slot 0 was picked by **elimination**, and elimination is not observation, so it was tested
directly. `verify.py` (machine-checked, all assertions pass):

```
PASS  fresh load: 0x0236A7F2 == 1
PASS  save/load round trip preserves value (1)
PASS  poke slot0=2 changes the LAP numerator glyph
PASS  poke slot0=3 changes it again (distinct from the =2 glyph)
PASS  poke slot0 back to 1 reproduces the untouched numerator exactly
PASS  CONTROL: poking CPU slot1=3 leaves the player's numerator byte-identical
```

Writing `2` into `0x0236A7F2` makes the top screen read **`LAP 2/3`**; `3` makes it read
**`LAP 3/3`**; `1` restores it. Writing `3` into CPU slot 1's byte leaves the player's HUD at
`LAP 1/3`. The player's lap display is rendered from **slot 0 specifically**, not from
"whichever lap byte".

A note on method, because the first version of this test was wrong: the LAP numerator box
overlays the live 3D scene, so two captures taken at *different* frames differ in the background
no matter what the glyph does. The committed test re-runs every poke from the **same savestate
for the same number of frames**, so the background is identical and the byte-comparison is
genuinely about the glyph. The naive first version produced two spurious FAILs — a defect in the
test, not in the address.

## 8. What was NOT observed — the honest gap

**The player's own byte was never seen ticking through genuine gameplay.** `0x0236A7F2` held `1`
for every frame of every run this session. The `1 → 2 → 3` traces in §4 are the **seven CPU
racers'** bytes; the player's byte was driven through 1/2/3 only by **poking** it.

Four drivers were built to close that gap; all four failed the way PR #168 did:

| driver | approach | result |
|---|---|---|
| `beam_drive.py` | 14 fixed policies × 150-frame bursts, savestate-backtracking greedy | ~100 s/step; reached checkpoint 2 in 3 steps; abandoned as too slow |
| `rollout_drive.py` | 8 random 900-frame steering programs per commit | reached checkpoint 2 by frame 3,600; ties collapsed to "hold accel"; abandoned |
| `unstick_drive.py` | closed-loop stuck detection → reverse+steer recovery, rotating steering bias | reached checkpoint 3, then wedged at checkpoint 1 from f≈10,000 to f≈21,000 |
| `bt_drive.py` | checkpoint the furthest state ever reached, retry with next bias on failure | advanced to ck94=1/ck90=2, then the **emulator process died silently (exit 1, no traceback)** on attempt 2 |

All four score **only** on the checkpoint counters `0x022C8090`/`0x022C8094` and the speed
oracle — never on the lap byte — so that a lap tick would remain an independent observation
rather than the thing the search was optimising. That rule is stated in each script's docstring.

The `bt_drive.py` crash is a **new, unexplained harness instability**: a long-lived py-desmume
instance doing repeated `load_state`/`save_state`/`save_screen` dies without a Python traceback.
`unstick_drive.py` died the same way once. Worth a bounded look before anyone builds a long
MKDS driving harness on this pattern.

Two incidental findings, both worth banking:

- **With zero input the player's kart still drives itself** out of the start and around the
  first bend, reaching checkpoint 10 by ~2 min of race time before wedging. The banked savestate
  has acceleration effectively held. This is why the coast run produces a real race at all, and
  it is what made the whole CPU-watching approach possible.
- **`0x022C8094` DOES decrement — PR #168's headline lead is dead.** That report kept
  `0x022C8094` alive as "the best surviving lead" specifically because it "stayed flat across
  every reset event". In this session's coast run it went **`3 → 1`** between f9,900 and
  f10,200, alongside `0x022C8090` going `10 → 1`. The non-decrement property that made it the
  lead is **false**. It is a checkpoint/respawn anchor, and it was never the answer.

## 9. The address MOVES between races — tested, and it fails

This was going to be filed as an untested risk. It got tested, and it is real.

From the banked savestate, `START` → `QUIT` → `SELECT MODE` → Grand Prix → character → kart →
cup → race (all via `menu_nav.py`, screenshots at every step) lands in a fresh race on Desert
Hills. In that race, `0x0236A7F2 .. +7*0x8C` reads **`[194, 0, 0, 1, 68, 205, 255, 17]`** — not
`[1,1,1,1,1,1,1,1]` — while the top screen plainly shows `LAP 1/3`. The old address is garbage.

`find_array.py` re-derives the array from scratch in any race state, in two stages:

1. **Structural**: find every offset where 8 bytes at stride `0x8C` all read the same plausible
   lap value and the 9th does not (so the run is exactly 8 long).
2. **Causal**: for each structural candidate, poke slot 0 and require the LAP numerator glyph to
   change, and poke slot 1 and require it *not* to. This is the §7 test, applied as a filter.

| state | structural candidates | causally confirmed |
|---|---|---|
| `mkds_race_start.state` (Figure-8) | 87 | **1** — `0x0236A7F2` |
| fresh race (Desert Hills) | 153 | **1** — `0x0237BED2` |

The structural signature alone is worth 87–153 candidates, i.e. nearly worthless on its own; the
causal poke test collapses it to exactly one both times. That the method independently
rediscovers `0x0236A7F2` on the original savestate is the check that it is not just fitting
noise.

Delta between the two races: `0x0237BED2 - 0x0236A7F2 = 0x114E0` (70,880 bytes). Whether the
base is a function of the *track* (different track data loaded) or is genuinely per-race
allocation is **NOT determined** — two races on the same track were not compared, because the
menu path taken landed on Flower Cup rather than Mushroom Cup. That distinction decides whether a
small per-track table would do or a real pointer chain is needed.

## 10. Semantics — what a scorer must not get wrong

The byte is the **current lap number**, 1-based, and it **saturates at the lap total**:

- Slot 1's byte went `1 → 2` @f4080 and `2 → 3` @f8280, then did **not** change at f11940 when
  that racer actually finished lap 3 and crossed the line. It stops at 3.
- So **"completed at least one lap" is `value >= 2`**, and **"finished the race" is NOT
  `value == 4`** — that never happens. A finish test needs a different field.

Also:

- **BCD vs plain int is moot.** The only values possible in a 3-lap GP are 1, 2, 3 — identical
  under both decodings. PR #168 left this "genuinely inconclusive"; it is inconclusive *and
  irrelevant* here, and would only matter on a hypothetical >9-lap mode.
- Companion fields at `lapfield-0x18` and `lapfield-0x0C` also count laps, and a per-lap time
  record sits at `lapfield-0x2E`. **Do not use them**: `lapfield-0x18` was inconsistent across
  slots (slot 1 ticked in sync with the lap field; slot 3's ticked a whole lap late,
  `0 →1 @f7170 →3 @f10950`). Only the `+0x18` column was uniform across all seven CPUs.
- The per-racer key-checkpoint bitmask is at `lapfield + 0x14` (player: `0x0236A806`), filling
  bits `1,2,4,…,128` across a lap. A within-lap progress signal, not a lap counter.

## 11. Alternative hypotheses

**Excluded by the evidence above:**

- *A "past the start line" latch* — excluded: three distinct values, `1 → 2 → 3`, on seven
  independent racers.
- *Checkpoint index* — excluded: `0x022C8090` reaches 10+ and resets; this byte takes exactly
  three values in a three-lap race, and poking it moves the LAP display.
- *"Laps remaining" countdown* — excluded: it counts **up**, and the poked value appears verbatim
  as the HUD numerator.
- *Race position / rank* — excluded: poking changes the LAP numerator glyph, not the position
  indicator; the player sat in 8th throughout while the byte stayed 1.
- *Global scene / mode / music-cue id* — excluded: it is per-racer (8 copies at fixed stride) and
  the copies tick at seven different frames.
- *Another racer's byte mistaken for the player's* — excluded by the poke + control test (§7),
  independently reproduced by `find_array.py` in two different races.
- *A transient* — excluded by the sustained-hold table (§6).
- *A stable global constant* — **excluded, and this one bites**: §9.

**NOT excluded — genuinely open:**

1. **Is the base a function of the track, or of the race instance?** Not determined (§9). Two
   races on the *same* track were never compared. This decides the wiring design.
2. **Whether slot 0 is always the human player**, or is "slot 0 = player" only for this
   character/kart/grid position. Not tested with a different character or starting position.
   (`find_array.py`'s causal step does not care — it finds whichever slot drives the HUD — but a
   hard-coded "slot 0" assumption would.)
3. **Whether the player's own byte increments like a CPU's.** The `1 → 2 → 3` traces are CPU
   bytes. Poking proves slot 0 *drives the display*; it does not prove the game writes slot 0 on
   the player's own lap crossing by the same code path — though array homogeneity plus the shared
   HUD makes any other arrangement contrived.
4. **Behaviour under a wrong-way line crossing.** `0x022C8090`/`0x022C8094` both decrement on
   wrong-way and stuck events; whether the lap field can be driven **backwards** across the line
   was not tested, because the player was never at the line. A scorer that latches once on
   `value >= 2` is safe regardless; one that reads it as a live counter is not obviously safe.
5. **Non-GP modes** (Time Trial, VS, Mission) and other engine classes — untested.
6. **A "lap total" field.** `3` is the saturation point because these tracks are 3 laps; whether
   the limit is read from a nearby field or from per-track data was not investigated.

## 12. Not wired — deliberately

No edit was made to `world_mcp.py`, to any `watch = {}` dict, or to
`eval/score_exam_mkds_lap.py`. `world_mcp.py` edits cascade into the frozen Gate-0 host/image
pins and force a re-pin plus an image rebuild, so wiring belongs in one batched PR with the other
worlds' oracles.

**And on this evidence the oracle must not be wired as a constant at all.** What to pin instead:

```
# MKDS lap oracle -- structure, not a constant.
#   8-racer array, stride 0x8C; element = current lap, 1-based, numerator of "LAP n/3".
#   completed >= 1 lap  <=>  value >= 2 .  Saturates at the lap total; never reaches 4.
#   BASE IS PER-RACE, NOT FIXED:
#     runs/nds3d_probe/mkds_race_start.state (Figure-8) -> player @ 0x0236A7F2
#     fresh race (Desert Hills)                          -> player @ 0x0237BED2
#   Locate per race with reports/probes/2026-07-28-mkds-lap-oracle/find_array.py
#   (structural stride scan + causal HUD-poke confirmation; 87/153 -> exactly 1, twice).
```

For EX05 specifically, the cheapest safe wiring is: the run always starts from one pinned
savestate, so resolve the base **once at world start** with the structural+causal locator and
carry it for the episode — rather than baking a literal into `world_mcp.py`. That keeps the
oracle correct if the savestate is ever re-captured.

## 13. Next attempt — sharpened pin

1. **Settle §11.1 first**: run two races on the *same* track and compare bases. Same base ⇒ a
   small per-track table suffices; different base ⇒ resolve at runtime (or find the pointer that
   holds the base — likely cheap now that two concrete bases are known to diff against).
2. Then wire, batched, using a resolved base rather than a literal.
3. If a player-driven lap is still wanted as belt-and-braces, the cheapest route is **not** better
   steering — it is capturing a savestate just before the finish line. None exists today;
   capturing one is a bounded one-off cost and would let every future MKDS lap experiment start a
   second from a lap boundary.
4. Before building any long MKDS driving harness, spend a bounded slot on the py-desmume
   silent-death under repeated `load_state`/`save_state`/`save_screen` (§8).
