# Kirby's Dream Land (GB) — Stage-3 attempt for the EX02 oracle (2026-07-26)

Status: **$0 local probe only, offline PyBoy, NO LLM, NO Docker, NO paid run.** Worktree
`probe/kirby-gb-stage3` (`../ai-pokemon-red-kirby3`). Continues
`reports/2026-07-25-oracle-kirby-gb-stage.md` (PR #169), whose banked next step was: *reach Stage 3
and see whether any of the 8 surviving bytes reads `2` (real stage counter) or stays `1`
(one-time "past Stage 1" latch).*

**Verdict: STAGE 3 NOT REACHED — EX02 REMAINS ORACLE_PENDING, unchanged.** The 8 survivors are
still exactly as ambiguous as PR #169 left them. What this session did produce is (a) a materially
better driving rig, (b) a **correction to PR #169's characterisation of `0xD052`/`0xD3EE`**, (c) a
newly identified pair of position bytes, and (d) a reproducible route to the point where progress
now stops. Nothing was wired; no scorer, `world_mcp.py`, fixture or pinned file was touched.

## What was actually reached

Started from `D:/ai_pokemon_runs/2026-06-23_kirby_play/checkpoint_01.state` — the confirmed Stage-2
savestate (score 39460, ~200 steps into Castle Lololo) that PR #169 identified. Progress made this
session, all eyes-on and screenshot-verified:

- Cleared the corridor Kirby was penned in at the checkpoint (score 39460 → 43160).
- **Found and reproduced a room transition**: the corridor's left-end door, reproduced three times
  and confirmed by the screen-blank detector, landing in a previously-unvisited **water/moat room**.
- Established that Castle Lololo's corridor here is a **multi-floor shaft** — floating up moves
  Kirby between floors (this is what `0xD052` tracks, see below).
- Two deaths + respawns survived (lives 5 → 3 as displayed).

- **Reached a new, verified-legitimate area beyond the water room**: the castle **battlements /
  tower exterior** (score 44560), via a proper door transition, confirmed by replaying the exact
  input sequence and watching it happen (`REPLAY_montage.png`) with an intact HUD throughout. This
  is deeper into Castle Lololo than any prior session got.

- **★ Reached the end of Castle Lololo and the boss area.** Past the towers the game takes over:
  Kirby rides a **warp star** right across a sky of clouds and mountains, crashes through the castle
  wall and lands in the boss room, where the HUD's score row is replaced by a **boss health meter**
  and an enemy pushes **blocks along horizontal tracks** — Lololo. Verified frame-by-frame
  (`transition_zoom.png`): score row intact throughout the flight, Kirby controllable on arrival.

**Where it stopped: the Lololo boss fight, at 1 HP.** The route arrives with hp=1, and the fight
needs several inhale-a-block-and-spit-it-back cycles; 300 fight-biased randomised trials landed
minor hits (best score gain 400) but never won. So no Stage-2 → Stage-3 transition was observed and
**the discriminating sample EX02 needs still does not exist**. This is a much better place to be
stuck than PR #169's (which never left the first corridor), and the remaining gap is one won boss
fight.

⚠ **RETRACTED — "savestates yield a frozen Kirby" was my second wrong mechanism claim here.** I
reported that savestate-chaining produced a Kirby who could not move horizontally. It did not. Two
separate measurement bugs produced that illusion:
1. **A hardcoded Kirby sprite-tile set.** I identified Kirby by tiles `{0,1,2,3,16,...,51}`, which
   covers only some of his animation frames. When he walked he switched to tiles outside the set and
   read as "not on screen" or as a stale position — so he looked stationary while actually moving.
2. **Pressing into a wall.** Boss-room states have Kirby at screen x≈148 (the right edge) or x≈4
   (the left edge). I tested `right` at the right wall and `left` at the left wall and read "no
   movement" as "frozen".

Corrected method: identify Kirby by *which sprites respond to input*, not by a tile whitelist, and
always test **both** directions. Savestate-chaining is fine and remains the right technique.

The general lesson is the same one as the "corruption" retraction earlier in this document, and it
has now cost this session twice: **I inferred a broken mechanism from a measurement I had not
validated.** Both times the cheap check — vary the suspected cause and see whether the effect
follows — settled it in one run.

## ★ The 8 survivors narrow to 5 (and a false alarm I raised and then withdrew)

**Result: `0xC057`, `0xC073`, `0xC07B` are ELIMINATED. They vary WITHIN Stage 2.**

Measured across ordinary play (60 sampled intervals of `right`/`a` input, one continuous run in the
post-battlements area, score constant at 44560, no stage change):

| Address | values observed within Stage 2 |
|---|---|
| `0xC057` | `1`, `32`, `33` |
| `0xC073` | `0`, `1` |
| `0xC07B` | `0`, `1` |
| `0xD03B`, `0xD19F`, `0xD3A9`, `0xD3BA`, `0xD3CD` | `1` only |

PR #169 recorded that all 8 "move in perfect lockstep across every sample gathered ... most likely
several are mirrors of one value". That holds for the five `0xD0xx`/`0xD3xx` bytes but **not** for
the three `0xC0xx` ones — the earlier hunt simply never sampled a state where they diverge. They
are almost certainly sprite/scratch bytes in the `0xC0xx` block that happened to read `0`/`1` in
the states sampled.

**The live candidate list for EX02 is therefore 5, not 8:**
`0xD03B, 0xD19F, 0xD3A9, 0xD3BA, 0xD3CD`. Those five still read `1` in every legitimate Stage-2
state sampled this session, and still cannot be told apart from a "past Stage 1" latch.

### The false alarm, recorded because the reasoning error is the useful part

I first saw the `0xC0xx` divergence in states reached by randomised search, noticed those states'
HUD was missing its `Sc: NNNNN` row, concluded the search had driven the game into a **corrupted**
state, declared the divergence void, and built a "validity guard" (dark-pixel count in the HUD score
row: 161-177 "legit", 104 "corrupt"). I banked that in commit `da908f6`. **It was wrong.**

What actually happens: the room transition plays KDL's **warp-star animation** (Kirby flies right
across a scrolling sky on a star), and the area it lands in draws a **different, legitimate HUD
row** — a Kirby-face icon and three small boxes in place of the score. Caught it by letting a state
idle with *no input at all* and screenshotting the whole sequence: the "corruption" appeared
spontaneously, on a state nothing was doing to it, which is not how input-induced corruption
behaves. Kirby walks, enemies move, HP/lives/score stay sane throughout.

Lessons, which are the opposite of the ones I first wrote down:
1. **"The screen looks wrong" is not evidence of an invalid state.** I inferred corruption from one
   unfamiliar HUD row and then built a detector that encoded the mistake, which made every
   subsequent measurement agree with it. A guard built on an unverified assumption launders it into
   apparent confirmation — 200 trials "confirmed" the wrong conclusion.
2. The check that broke it was cheap and should have come first: **remove the suspected cause** (run
   the state with no input) and see whether the effect persists.
3. The `bruteforce.py` guard is now **off by default** and documented as unreliable.

## The correction to PR #169 (the substantive finding)

PR #169's candidate table lists `0xD052` and `0xD3EE` as *"ELIMINATED — volatile, not a stage
index; mostly `5`, but drops to `1` around the death/continue event (step ~850) and briefly
elsewhere."* The elimination verdict is right, but **the stated behaviour is wrong, and the reason
matters**:

`0xD051` (mirrored at `0xD3ED`) and `0xD052` (mirrored at `0xD3EE`) are **Kirby's position**, not
volatile noise.

Measured this session (`findpos.py`, then a clean 120-frame time series per condition):

| Condition | `0xD051` / `0xD3ED` | `0xD052` / `0xD3EE` |
|---|---|---|
| corridor, holding `right` 120f | `7 → 14`, monotone rising | constant `5` |
| corridor, no input 120f | constant `7` | constant `5` |
| water room, no input 120f | constant `1` | constant `1` |
| corridor, floating upward | — | steps `5 → 4 → 3 → 2 → 1` |

- `0xD051` = Kirby's X within the current area: **rises holding `right`, falls holding `left`,
  perfectly still with no input** (the three-branch test in `findpos.py` — a frame counter or
  animation byte passes none of those simultaneously). **Verified.**
- `0xD052` = a **vertical band / screen index**: rock-stable during horizontal movement, and it is
  what changes as Kirby floats up through the corridor's floors. **Verified** (stability and the
  float-driven stepping were both observed directly).
- **Inference, not verified:** PR #169's "drops to `1` around the death/continue event" is the
  respawn *relocating Kirby to a different band*, not death touching the byte. That reading fits
  every observation here, but I did not re-run the specific step-850 death PR #169 recorded.

This matters beyond bookkeeping: it means **two of the three bytes PR #169 eliminated were
eliminated for the wrong stated reason**, and it retires the "volatile" label on a pair that is
actually a usable position signal. It is also the second time in this lane a byte was
characterised from too few conditions (cf. the Cave Noire `0xD389` and Emerald outdoor `map_num`
cases) — the fix each time is the same: vary the input deliberately rather than sampling a
trajectory.

## The 8 survivors — status unchanged, plus extra falsification

The five surviving bytes `0xD03B, 0xD19F, 0xD3A9, 0xD3BA, 0xD3CD` read **`1` in every sample taken
this session** — across ~40 driven bursts, several deaths + respawns, multiple confirmed room
changes (corridor → water room, corridor upper floors → battlements → warp-star area),
multi-floor climbing, >900 savestate-chained sweep trials and >900 randomised trials. That rules out
"changes on room transition", "changes on floor change" and "changes on death/respawn". The other
three (`0xC057/0xC073/0xC07B`) are eliminated — they vary within Stage 2 (see above).

It does **not** discriminate the two live hypotheses (real incrementing stage index vs one-time
past-Stage-1 latch), because both predict `1` everywhere inside Stage 2. **Do not wire any of
them.** The falsifying test is unchanged and still unrun: reach Stage 3 and read them.

## Rig improvements (the reusable part)

`reports/probes/2026-07-26-kirby-gb-stage3/`:

- **`kdrive.py`** — the driver. The important change over `nav_step.py`:
  `core.gb_emulator.PyBoyEmulator.press()` drives **one button at a time**, so it physically cannot
  hold `right` while tapping `a`. Kirby's float needs exactly that, which is a plausible
  contributor to the 2026-07-25 session's stall. `kdrive.py` talks to PyBoy directly and takes a
  script of `frames:button+button` steps, so any combination can be held. It also emits a labelled
  **montage filmstrip** (one Read shows a whole burst), per-shot score/HP/lives/X, and saves a
  savestate per burst so any burst can be rewound.
- **Screen-blank room detector.** Every RAM byte tried as a room id was position-dependent and
  misled me twice. KDL blanks the screen between rooms, so `kdrive.py`/`doorsweep.py` flag a
  near-uniform frame as a room change. **Validated against the one transition known to have
  happened** (fired exactly once, at f118, on the corridor→water door).
- **`doorsweep.py`** — the search that replaced guesswork. For each horizontal offset it reloads the
  *same* savestate, walks that far, tries an exit action, and reports transitions. Savestate-chained
  so trials cannot drift into each other.
- **`findpos.py`** / **`roomid.py`** — the position-byte finder, and a room-id finder that
  **failed** (29 surviving bytes, all noise — recorded so nobody re-runs it).
- **`bruteforce.py`** — randomised action search with the room detector as oracle **and the HUD
  validity guard** described above. Deterministic (trial `i` = `seed+i`), so any hit replays
  exactly. Use it to find candidate routes, then **always replay the winning seed through
  `kdrive.py` and look at the montage** before believing the destination.
- **`grid.py`** — renders a savestate at 5x with a labelled 16px grid so room geometry can be
  *measured*. Eyeballing raw 160x144 frames is what made the first dozen navigation guesses wrong.
- **`route.py`** — automates the death → respawn → autopilot → door approach back to the water room.
  Works, but the corridor is not deterministic (enemies knock Kirby around), so it retries door
  offsets and still fails some passes; rerun it rather than debugging it.

## Route knowledge, so the next session starts where this one ended

1. From the respawn checkpoint, `','.join(['50:right','20:right+a']*8)` (560 frames) reaches the
   corridor's right end reliably.
2. `700:left` from there reaches the corridor's **left end**, where a door sits behind a `?` block.
3. **The door cannot be reached by walking** — the `?` block stops Kirby, and every walk-then-`up`
   sweep found nothing. It needs a **jump over the block first**: `doorsweep.py`'s `hop_left_up`
   action at walk offset 52 lands the transition (verified, `1 ROOM CHANGE`).
4. That puts Kirby in the water/moat room. Its exit resisted 332 directed sweep trials **and** 370
   randomised ones; what does work is **hugging the ceiling** (alternate `up` and `up+right`), which
   crosses the Gordo-infested column corridor taking **zero damage**. Kirby's in-room X saturates
   at 7 there, and that is genuinely the end of it — the room is a dead end for this rig.
5. The real way on is **not** through the water room. From the corridor's **upper floors** (float up
   from the lower floor; `0xD052` counts the floor down 5→1) a door leads to the **battlements**.
   Reproducible: `bruteforce.gen(7178, 900)` replayed from `u01.state` gets there — transition at
   f650, confirmed legitimate.
6. From the battlements, `float-right` (alternate `8:a` and `14:right`) advances damage-free to the
   tower sub-area. **68 repetitions of that from `REPLAY.state`, then ~1000 idle frames, and the
   game flies Kirby to the Lololo boss room on a warp star.** Run it continuously (see the gotcha
   above) — `cont_boss2.state` is the banked, controllable boss-room arrival, at hp=1.
7. Doors are now a lookup, not a search: `doorscan.py` finds them from the tilemap and `enter.py`
   walks to one and enters it. Validated against a door already known to work (`D01.state`: reported
   `dx=+24px`, entered first try) and against the water room, where it found both doors including
   the unreachable one. The exit is very likely reached by **swimming vertically** to the
   door visible at the room's bottom-left, which the sweep's "walk N frames then act" model cannot
   express.
5. Incidental but useful: **dying is a free full heal** (HP back to 6) at the cost of one life, and
   the respawn checkpoint is early enough that step 1 re-reaches the corridor end in ~10 seconds.

## ★★ THE LOLOLO FIGHT IS WON — and the five candidates still read `1` on the far side

**Beaten** (`beat_lololo.py`, seed 600000 from `boss_fresh.state`): boss meter 72 → 0, screen
transition, Kirby alive at hp 3 / 3 lives, score 49960. Banked as `LOLOLO_WIN.state`.

Three things made the difference, after 948 trials of blind search had landed zero damage:
1. **Match Kirby's HEIGHT to the ledge the block is on before inhaling.** He had been inhaling into
   empty air one ledge below the block the whole time. This alone produced the first-ever hit.
2. **Start at full HP.** The route arrives at 1-2 HP; dying in the boss room respawns Kirby at hp 6
   *and resets the boss to full*, so a fresh death is the cheapest full-health start
   (`boss_fresh.state`).
3. **All three hits must land on one life** — because dying resets the boss meter to 72. Verified by
   a control run: letting Kirby die with **no input at all** leaves the meter at 72, which also
   proves the meter drops were real hits and not a death artifact.

### What happens after the win, and why the verdict is still open

- **There is no stage-clear sequence.** Idling 2400 frames after the win does nothing: Kirby is
  parked in a doorway, score frozen at 49960. So **Lololo here is a mid-stage encounter, not Castle
  Lololo's final boss** — or the stage's end is several rooms further on. Either way, beating it did
  not end Stage 2.
- **Input is ignored for a few hundred frames after the win.** Every exit tried immediately
  (`up` in the doorway, walk left/right, float right) moved nothing; the same inputs work after
  ~600 idle frames. Settle before acting, or a room will look like a dead end when it isn't.
- **`advance.py` chained forward 5 further rooms** (score 49960 → 51240 → 51660 → 52460 → 53260),
  each time by searching for a transition, taking it, and re-searching. It stalls every few rooms and
  needs a new angle each time.
- **Through every one of those rooms the five candidates read `1`.**

⚠ **This is NOT the answer, and must not be recorded as one.** "The bytes stayed 1 after the boss"
is only evidence about *rooms still inside Stage 2*. Concluding "therefore they are a latch" would
be exactly the too-few-anchors error this lane has now made three times (Cave Noire `0xD389`,
Emerald outdoor `map_num`, and PR #169's own lockstep claim). **The verdict stays OPEN until a
sample from an actual Stage 3 exists.**

## The Lololo fight, as characterised before it was won

Everything below is measured, and it is the state of the art for whoever picks this up.

- **The arena.** One screen, no scroll. Three horizontal ledges (tile rows 2, 6, 10) over a solid
  floor (rows 14-15). Kirby arrives at the right edge (screen x≈148).
- **The boss meter is real and it is the reward signal.** The score row is replaced by a skull icon
  plus **3 boxes** (screen x 44-80, y 128-136; 72 dark px at full health). Confirmed by zooming the
  HUD strip against a normal room, which shows `Sc: NNNNN` in the same place.
- **The pattern.** Lololo enters from the RIGHT pushing a block LEFTWARD along one ledge, exits
  left, returns rightward, then repeats on a *different* ledge (observed order y=64 → 96 → 32).
  Touching either costs Kirby 1 HP.
- **Sprites:** Kirby is a 2-sprite pair with tiles ≤60 (walk pairs 0/16, 2/18, 4/20, 6/22, 8/24;
  inhale 36/38/52/54); the **block** is a pair of tile-230 sprites; **Lololo** is the animated pairs
  248/250, 236/240, 234/242. ⚠ Kirby and Lololo look alike on screen and their tile ranges are not
  cleanly separable in every frame — this misidentification is what produced the retracted
  "frozen Kirby" claim, so treat sprite classification here as unreliable and cross-check it.
- **Inhale demonstrably works**: holding `b` visibly drags objects toward Kirby (traced, a target
  moved 65→122 px toward him over 72 frames).

**What has been tried and has NOT damaged the boss (meter never left 72):**

| approach | trials | result |
|---|---|---|
| uniform random input | 560 | 0 damage; score gains only from eating ordinary enemies |
| structured cycles (reposition → inhale → spit), `bossfight.py` | 260 | 0 damage, best score gain 1600 |
| reactive controller, camp-right, `lololo.py` | 40 | 0 damage |
| reactive controller, camp-LEFT so the block arrives before Lololo | 88 | 0 damage |

A RAM sweep for a monotonically-decreasing small byte across a whole fight found **exactly one**:
`0xD086`, Kirby's own HP. So the boss really is taking no damage — this is not a reward-detection
problem.

**Honest read on why:** the route arrives with 1-2 HP, Kirby dies in ~1000 frames, and the
inhale-then-spit has to land on a specific ledge with correct facing inside that window. The
remaining work is a genuine game-playing problem, not an instrumentation one.

## The one thing left: win the Lololo fight

The hunt is now **one boss fight** from the Stage-3 sample. Concretely, for the next session:

- Start from `cont_boss2.state` (banked boss-room arrival, controllable) or re-derive it with the
  continuous route in step 6 above.
- **Arrive with more than 1 HP.** The route loses HP crossing the battlements; a damage-free
  crossing, or a health item, is worth more than a better fight policy.
- The fight is **inhale the block Lololo pushes along a track, then spit it back at him** — Kirby
  must be on the same track as the block. Random search will not find this reliably (300 trials
  did not); it needs a policy that reads the block's position off the tilemap (Lololo and the
  blocks are **background tiles, not sprites** — `get_sprite` shows only Kirby and the HUD).
- Winning ends Castle Lololo. Read `0xD03B, 0xD19F, 0xD3A9, 0xD3BA, 0xD3CD` on the other side: if
  any reads `2`, it is a real stage counter and EX02's oracle is found; if they all stay `1`, they
  are a past-Stage-1 latch and the hunt restarts on a different byte.

## Recommended next step (not taken here — needs David)

PR #169 already named the fastest path and this session is evidence for it: **a human plays Castle
Lololo with RAM sampling on.** The recorder already supports it — `2026-06-23_kirby_ramplay` was
captured with `"ram": true`. A few minutes of human play through Lololo & Lalala and into Float
Islands produces the Stage-3 sample directly, and the 8 survivors resolve to "counter" or "latch"
by inspection.

The alternative — continuing the scripted/eyes-on hunt — is what this session did, at length. The
honest read: it works, it just costs a lot per room (each new sub-area took roughly 8-12 directed
iterations to map and cross), the areas kept coming, and the automated fallback that would have
sped it up turns out to corrupt the game. Castle Lololo's boss is still an unknown number of rooms
away.

⚠ The paid-brain option (let the agent play it) would also produce a genuine brain-capability
datapoint, but it needs a pre-registration first per gate-methodology, and the one existing datapoint
(`runs/brain_kirby_longhaul`: 316 turns, $42.98, did not clear Stage 1) is not encouraging for
clearing three stages.

## Safety

No brain / `core/` / `core/contracts.py` / tool-schema / `world_mcp.py` / pinned-Gate-0-file /
held-out-game edit. No oracle address wired. No scorer or fixture touched — `eval/score_exam_kirby_
stage3.py` still refuses unconditionally with `ORACLE_PENDING`, which remains correct. $0: offline
PyBoy only, no paid call, no Docker. Scratch savestates/screenshots stayed in the session scratchpad
per the convention of the two prior hunts; nothing written under `runs/`.
