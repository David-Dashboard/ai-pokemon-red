# EX03 Emerald "reached Oldale Town" oracle hunt — 2026-07-28

Status: **$0, offline, no paid run, no LLM call, no network.** Driven directly against
`core.gba_emulator.GBAEmulator` (unmodified) under the WSL mgba 0.10.2 rig
(`reports/2026-06-29-gba-mgba-recipe.md`). Builds on — and does not redo —
`reports/2026-07-23-oracle-emerald-hunt.md` and `reports/2026-07-25-oracle-gba-exam-hunts.md` (PR #170).

**Verdict, up front:**

| question | answer |
|---|---|
| monotone latch ("has ever reached Oldale") at a fixed address | **NOT FOUND — and structurally blocked**, see §5 |
| correct fixed-address map identity, replacing the falsified `map_num` | **FOUND**: `mapNum` `0x02037359` (u8), `mapGroup` `0x0203735A` (u8), `regionMapSectionId` `0x0203732C` (u8) |
| Oldale's values | `(mapGroup, mapNum) = (0, 10)`, `regionMapSectionId = 1` — derived from the ROM (§4), **never read live** |
| Oldale reached in-game | **NO** — hard story gate, §6 |
| GBA harness ran on this Windows host | **YES** (Windows → `wsl.exe` → `~/gba-spike` mgba) |

Nothing was wired. `world_mcp.py`, every `watch = {}`, `core/contracts.py` and
`eval/score_exam_emerald_oldale.py` are untouched.

---

## 1. Why `map_num` failed — root cause, not just the symptom

The banked hunt proposed `map_num = 0x0203735C`, `map_group = 0x02037340`, then falsified `map_num`
by observing 10/12/14 for one visually-contiguous outdoor Littleroot, with `(2,14)` colliding
against the bedroom. That falsification was right. The mechanism is now pinned:

`gObjectEvents[0]` (the player's object-event slot, fixed BSS) starts at **`0x02037350`**. Its
layout, recovered from this session's dumps, is

```
+0x08 localId (0xFF = OBJ_EVENT_ID_PLAYER)   +0x0C initialCoords .x/.y     <- 0x0203735C / 0x0203735E
+0x09 mapNum                                 +0x10 currentCoords .x/.y     <- 0x02037360 / 0x02037362
+0x0A mapGroup                               +0x14 previousCoords .x/.y
```

So **`0x0203735C` is `initialCoords.x` — the x-coordinate at which the player *entered* the map he
is standing on.** That single fact explains every banked observation at once:

* It is rock-stable while you walk (you are not re-entering the map), which is exactly why the
  banked hunt's 12 snapshots looked consistent.
* It changes when you re-enter *the same* map through a *different* door. Measured live this
  session, all six of these are the same map, outdoor Littleroot Town:

  | outdoor anchor | how the map was entered | `0x0203735C` |
  |---|---|---|
  | beside the moving truck | truck cutscene | 10 |
  | in front of the player's house | out of player's house | 12 |
  | town centre-north | out of May's house | 21 |
  | at Birch's Lab door | out of the Lab | 14 |
  | north-west corner (walked from the Lab door) | out of the Lab | 14 |
  | at the Route 101 hedge gap (walked from the Lab door) | out of the Lab | 14 |

  Four different values for one map — one more than the banked hunt saw.
* It collides across genuinely different maps whenever their entry-x happens to match: bedroom = 14
  = outdoor-near-Lab (the banked collision, reproduced), and truck interior = 9 = May's House 1F
  (a second collision the banked hunt never saw).

`0x02037340` is not `mapGroup` either: it reads **2** in all six Littleroot maps and 0 in the truck,
whereas the real `mapGroup` reads 0 / 1 / 25 for those maps. It is a constant that merely looked
plausible because all four banked anchors sat inside one town.

**The real fields are 3 and 26 bytes away from the banked guesses.** Full value trace,
12 anchors, `reports/probes/2026-07-28-emerald-oldale-oracle/sweep2.py`:

```
anchor            truck out_truck house1f  bed2f out_own  may1f  may2f out_N out_lab out_nw out_gap  lab
0x02037359 mapNum    40         9       0      1       9      2      3     9       9      9       9    4
0x0203735A mapGroup  25         0       1      1       0      1      1     0       0      0       0    1
0x0203732C mapsec    84         0       0      0       0      0      0     0       0      0       0    0
0x0203735C  (banked)  9        10      15     14      12      9      8    21      14     14      14   13
0x02037340  (banked)  0         2       2      2       2      2      2     2       2      2       2    2
```

`mapNum`/`mapGroup` are bit-identical across all six outdoor anchors and take a distinct value on
each of the six maps — the exact property the banked byte lacked. The interior values 0,1,2,3,4 of
group 1 are the five Littleroot buildings in map-table order, and `(0, 9)` for the town matches the
ROM (§4) exactly.

## 2. Uniqueness

Counting addresses whose 12-anchor value vector is bit-identical to the candidate's
(both regions swept in full: EWRAM `0x02000000`+256 KB, IWRAM `0x03000000`+32 KB):

| candidate | EWRAM twins | IWRAM twins | twin addresses |
|---|---|---|---|
| `mapNum` `0x02037359` | 3 | 1 | `0x020322E5`, `0x02037359`, `0x0203BC81`, `0x03005E58` |
| `mapGroup` `0x0203735A` | 3 | 1 | `0x020322E4`, `0x0203735A`, `0x0203BC80`, `0x03005E59` |

Four mutually-agreeing copies, adjacent in pairs — i.e. the game keeps redundant `(group, num)`
mirrors and they never disagreed. The pairs are internally consistent in a way that is evidence
rather than coincidence: `0x020322E4/E5` and `0x0203BC80/81` are ordered **group-then-num**, while
`0x02037359/5A` is **num-then-group** — exactly the field order of a `WarpData` struct versus an
`ObjectEvent` struct. Two different record types holding the same map identity, each in its own
declared order, is what a correct hit looks like; a coincidental byte pattern would not respect
that. Small and structured, not a haystack. For contrast, **250 716 of
262 144 EWRAM bytes are bit-stable across the six outdoor anchors alone** — "stable within a map" is
almost no evidence at all, which is precisely how the banked hunt landed on the wrong byte.

## 3. Transient / sustained-hold check (the "~4 frames" trap)

`etrace.py` samples all five bytes **every frame** across three real door warps
(outside→Birch's Lab, outside→player's house, May's House 1F→2F), 400 frames each:

```
outside -> Lab      mapNum   9 x97  -> 4 x303       mapGroup  0 x97 -> 1 x303      mapsec 0 x400
outside -> house    mapNum   9 x87  -> 0 x313       mapGroup  0 x87 -> 1 x313      mapsec 0 x400
May 1F  -> May 2F   mapNum   2 x53  -> 3 x347       mapGroup  1 x400               mapsec 0 x400
```

Two runs per byte, no third value, **zero transient/garbage frames** during the warp. The byte is
not a 4-frame artefact.

Caveat, stated because it matters: all six maps I could reach share `mapsec = 0`, so I frame-traced
`0x0203732C` only for *stability*, never across an actual mapsec change. I could not reproduce the
truck→town transition (it is a scripted cutscene; holding `a` or `left` for 900 frames from the
truck-interior state does nothing).

Assumption tested, not assumed: `gObjectEvents[0]` is the player because
`gPlayerAvatar.objectEventId` (`0x02037595`) reads **0 in all 12 anchors**. Only tested inside one
town.

## 4. Oldale's values — derived from the ROM, with stated assumptions

I have no network, so no *value* here was looked up — but the derivation is **not** assumption-free,
and saying otherwise would be an overclaim. `rom_maps.py` hardcodes four pieces of pokeemerald
domain knowledge: that Littleroot is map number **9** of group 0 (`g0 = refs[0] - 9*4`), the
`MapHeader` field offsets (`mapsec` at +0x14, `map_type` at +0x17), the **12-byte** `MapConnection`
stride, and the magic window `0x08480000 <= ptr <= 0x08490000` used to decide where the group table
ends. Those are assumed, then checked — not derived. What rescues the derivation from circularity is
that the assumptions are *over-determined* by two independent checks (both `assert len(...) == 1`
below, and the mapsec-0 census in step 5 landing on exactly the six maps I had already visited
live). Read step 3's "confirming Littleroot = map (0,9)" as **assumed-then-corroborated**, and read
"518 maps" as "the maps reachable through that magic window" — the census is only as complete as
that bound, which I did not verify independently.

`rom_maps.py` anchors on live RAM and walks the ROM's own tables:

1. Live `gMapHeader` (fixed EWRAM `0x02037318`) in outdoor Littleroot gives the ROM pointer quad
   `(0x083EA284, 0x08527840, 0x081E7DCB, 0x0848660C)`.
2. Those 16 bytes occur **exactly once** in the ROM → Littleroot's `MapHeader` is at `0x084825B4`.
3. **Exactly one** u32 in the ROM points at it → that word is `gMapGroups[0][9]`, pinning the group-0
   header table at `0x08485D60` and confirming Littleroot = map `(0, 9)`.
4. Following `connections`: `(0,9) --N--> (0,16)`; `(0,16) --N--> (0,10)`, `--S--> (0,9)`;
   `(0,10) --N--> (0,18)`, `--S--> (0,16)`, `--W--> (0,17)`. That is Littleroot → Route 101 → Oldale,
   and Oldale's three-way topology (Route 103 north, Route 101 south, Route 102 west) is a
   non-trivial consistency check that it landed on the right map.
5. `regionMapSectionId` census over all 34 groups / **518 maps**:
   * `mapsec 0` → exactly 6 maps: `(0,9)` + `(1,0..4)` — which is **exactly the six maps I visited
     live and read `mapsec = 0` in**. The ROM walk and the live dumps cross-validate.
   * `mapsec 1` → exactly 6 maps: `(0,10)` + `(2,0..4)` = Oldale Town and its five buildings, and
     nothing else in the game.

**So: `0x0203732C == 1` is true in Oldale Town and its five interiors and in no other map of the
518** — ***but this is UNCONFIRMED-LIVE. It is a ROM-table derivation; no one has ever stood in
Oldale and read that byte. Confirm it with a single live read before wiring anything.***
`(mapGroup, mapNum) == (0, 10)` for outdoor Oldale carries the same UNCONFIRMED-LIVE status.

## 5. The monotone latch: NOT FOUND, and why a fixed address cannot express it

The right signal for "has *reached* Oldale" is the visited-town flag bit in
`gSaveBlock1Ptr->flags`. It is unreachable as a `watch` entry, for a reason that was not previously
recorded anywhere in this repo and that invalidates any future absolute-address plan for Emerald
progress state:

**Emerald relocates SaveBlock1 across map transitions.** (Seven distinct bases over roughly eleven
transitions — enough to establish that it moves, *not* enough to establish "on every one"; I did not
instrument each transition individually. The conclusion below survives either way.)
`gSaveBlock1Ptr` lives at a fixed IWRAM address `0x03005D8C`, but its *target* moved across this
session's states:

```
0x02025A14  0x02025A28  0x02025A30  0x02025A40  0x02025A44  0x02025A58  0x02025A7C
```

Seven distinct 4-byte-aligned bases, a 0x68 span. Characterised: from one state, 2 / 600 / 2000
idle frames and 3 / 6 walking steps **all leave the pointer unchanged**; it moves when the map
changes (e.g. `s16 → s17`, the May's-House stairs warp, `0x02025A30 → 0x02025A14`).

Consequences:
* Every SaveBlock1 field — flags, badges, party, Pokédex, `location`, `lastHealLocation` — is at a
  **moving** absolute address. I caught this the hard way: a `watch` on the SaveBlock1 position pair
  read `(9,4)` correctly, then read `(2304, 255)` after a warp.
* `GAMES[...]["watch"]` is a flat `name -> absolute address` dict (`world_mcp.py:158-235`,
  consumed at `:997`). It cannot express `u32 @ 0x03005D8C, then +offset`. **Wiring any Emerald
  flag/latch oracle needs a `watch` schema change first** — that is a contract decision, not a
  hunt result, and it is exactly the kind of thing that must not be smuggled in silently.

Two traps in that reader that whoever wires this must know about:

1. **A mis-wired `watch` fails SILENTLY, not loudly.** `core/perception_plugin.py:302-305` wraps the
   whole read in a bare `except Exception: pass`:
   ```python
   if self._watch:
       try:
           rec["watch"] = {nm: int(self.emu.read(ad)) for nm, ad in self._watch.items()}
       except Exception:
           pass
   ```
   So a callable, a tuple, or any pointer-indirection value does not raise into the log — the
   `watch` key is simply **absent from every observe record**. A wrong oracle would present as *a
   world with no oracle at all*, which is far worse than a crash: a scorer would emit
   `INSUFFICIENT_DATA` and a reader would blame the world, not the address. Anyone extending the
   schema must fix this swallow in the same PR.
2. **Reads are u8 only.** `core/gba_emulator.py:99` returns a single byte, and the dict comprehension
   above calls `int(self.emu.read(ad))` once per name. So my own re-derived **u16** `x = 0x02037360`
   / `y = 0x02037362` cannot be wired faithfully as-is; they need the hi/lo split the Red arm already
   uses (`world_mcp.py:178` `party_hp_hi` / `party_hp_lo`) and a scorer-side recombination. The §1
   map-identity bytes are unaffected — `mapNum`, `mapGroup` and `regionMapSectionId` are all u8.
* By contrast the §1 candidates (`gObjectEvents`, `gMapHeader`) are in fixed BSS *outside* the
  relocating blocks, so they are safe at absolute addresses. The 2026-07-23 report's proposed
  `x`/`y` at `0x02037360`/`0x02037364` are likewise in fixed BSS and are fine (I re-derived
  `x = 0x02037360`, `y = 0x02037362` as u16 by direct single-step action correlation; the pair at
  `0x02037364/66` is `previousCoords`, a lagging mirror, not a second copy of the live position).

## 6. Falsification attempt for the latch — could not be run

The task asks for an anchor that tries to set the latch *without* arriving. **I could not run it,
because I never arrived.** Being blunt: with no Oldale sample there are no arrival anchors, no
before/after diff, no latch bit, and therefore no falsification result. Everything in §1–§4 is about
a *positional* signal; none of it is a latch.

Route 101 is sealed by a static NPC in the single hedge gap north of Littleroot
(`evidence/01`, `evidence/02`: *"Um, hi!"* → *"There are scary POKéMON outside! I can hear their
cries!"* → *"I want to go see what's going on, but I don't have any POKéMON…"* →
*"Can you go see what's happening for me?"*). PR #170 reported the same wall. This session got
strictly further and **eliminated two new candidate triggers**:

* **Completed the rival introduction.** Entered May's house, met her mother, went up to her room
  (empty), came back down and got the full scripted May intro — *"Um… I'm MAY. Glad to meet you"* →
  *"I have this dream of becoming friends"* → *"Oh, no! I forgot!"* (`evidence/03`). Re-approached
  the gap: **dialogue byte-identical, still blocked.**
* **Talked to the Lab aide.** Entered Prof. Birch's Lab, full conversation — *"The PROF's away on
  fieldwork. Ergo, he isn't here."* (`evidence/04`). Re-approached the gap: **dialogue
  byte-identical, still blocked.**

Also completed but insufficient: the clock-setting flow (the *"Is this the correct time?"* prompt
defaults its cursor to **NO** — confirmed again), Mom's post-clock TV scene, and exiting the house.
The remaining canonical unlock is Birch's Route 101 rescue → starter Pokémon, which cannot happen
because the NPC blocks the only tile onto Route 101. Whatever flag moves her, this session did not
find it.

## 7. Is the §1 candidate salvageable for EX03? Stated condition, and what it does not survive

`0x0203732C` is **not monotone**. A run that walks into Oldale and back out reads `1` and then `0`
again. It is only usable under a condition that must be stated rather than assumed:

> The scorer takes **∃ over the append-only `oracle.jsonl`** ("some logged row has
> `regionMapSectionId == 1`"), not a read of the final frame. The latch then lives in the log, not
> in RAM.

That shifts the risk to sampling: if oracle rows are written per agent *decision* rather than per
frame, a fast transit could in principle produce zero rows inside Oldale. I could not measure the
row cadence against a real Oldale transit and will not guess at it.

## 8. Alternative hypotheses this data does not exclude

1. **`mapsec == 1` may be reachable without "reaching Oldale" in the intended sense** — the census
   says the six `mapsec 1` maps are Oldale's, but I never verified that no script, cutscene, or
   Fly/teleport path loads an Oldale map without the player meaningfully arriving. Untested.
2. **`0x0203735C = initialCoords.x` is a *fit*, not a proof.** It matches all 10 observations
   (4 outdoor entry doors + 6 interiors) and the struct offsets, but I never watched the byte change
   at the instant of a warp *and* compared it to the spawn tile. A rival reading — some other
   per-map-load scalar that happens to correlate with entry x — is not excluded.
3. **`gObjectEvents[0]` = player** is verified across 12 anchors in one town only. If a map ever
   assigns the player a different slot, `0x02037359` reads an NPC's home map.
4. **The four `(group, num)` mirrors** were never observed disagreeing — but they were never
   stressed by a battle, a Fly, a save/reload of the *game* (as opposed to a savestate), or a
   cutscene warp. A mirror that lags by one map would be indistinguishable in my data.
5. **The SaveBlock1 relocation trigger** is characterised as "on map transition" from six
   transitions. Saving, healing at a Pokémon Center, or a battle may move it too; and its full range
   is unknown (0x68 span observed, not a bound).
6. **Oldale's `(0,10)` / `mapsec 1` are ROM-derived, never read live.** The derivation
   cross-validates against six live Littleroot maps, which is strong, but the specific claim
   "standing in Oldale makes `0x0203732C` read 1" has never been observed. **It must be confirmed by
   one live read before anything is wired.**

## 9. Next step

1. Break the Route 101 gate (the only real blocker), then take before/at/after-Oldale dumps and
   (a) confirm `0x0203732C == 1` live, (b) diff SaveBlock1-relative bytes to locate the
   `flags` array offset and the visited-Oldale bit.
2. Separately, and before any Emerald flag oracle is wired: decide whether `watch` gains a
   pointer-indirect form (`u32 @ 0x03005D8C` + offset). Without it, only fixed-BSS bytes are
   wireable for Emerald.
3. Wiring stays batched with the next Gate-0 world-image rebuild (`world_mcp.py` is untouched here).

## Reproduce

```
reports/probes/2026-07-28-emerald-oldale-oracle/
  edrive.py     drive a savestate with button/wait/shot tokens; dump full EWRAM+IWRAM
  etrace.py     frame-by-frame trace of the five candidate bytes across a transition
  sweep.py      12-anchor sweep: current-map candidates and region candidates
  sweep2.py     value trace + twin count for the pinned candidates
  rom_maps.py   ROM map-table walk (§4); run it with the ROM path, needs nothing else
  run_edrive.sh WSL launcher (LD_LIBRARY_PATH / PYTHONPATH per the 2026-06-29 recipe)
  evidence/     7 curated screenshots (gate dialogue, May intro, Lab aide, outdoor anchors)
```

**Which numbers are checkable, and which are not — read this before citing anything above.**

| claim | reproducible from committed artifacts? |
|---|---|
| §4 ROM derivation: Oldale `(0,10)`, mapsec 1, the 518-map census, the connection walk | **YES** — `rom_maps.py` needs only the ROM path |
| §1 12-anchor value trace, §2 twin counts, §3 frame traces, §5 SaveBlock1 relocation | **NO — scratchpad-only measurements** |

`sweep.py` / `sweep2.py` read `dumps/A_*.bin` and `etrace.py` writes a JSON trace; none of those
24 raw region dumps, the savestates that produced them, or the trace JSONs are committed (they are
throwaway per repo convention, and the savestates depend on a ~48 000-frame scripted intro run).
The scripts are committed so the *method* is auditable and re-runnable, but the specific numbers in
§1/§2/§3/§5 are **not independently checkable from this PR** — re-deriving them means replaying the
drive. That is a real gap, not a formality: treat those numbers as this session's measurements
pending a second run, and treat only §4 as reproducible on the spot.

All location and dialogue claims in this report are **model-graded from screenshots**, pending
David's validation.
