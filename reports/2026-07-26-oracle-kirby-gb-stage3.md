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

**Where it stopped:** in the tower sub-area past the battlements (Kirby's in-room X saturates at
21). The Lololo & Lalala boss was never reached, so no Stage-2 → Stage-3 transition was observed,
so **the discriminating sample EX02 needs does not exist**. Same class of wall as PR #169 (Castle
Lololo navigation), several rooms further in.

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
   tower sub-area, where progress stops at in-room X 21. The exit is very likely reached by **swimming vertically** to the
   door visible at the room's bottom-left, which the sweep's "walk N frames then act" model cannot
   express.
5. Incidental but useful: **dying is a free full heal** (HP back to 6) at the cost of one life, and
   the respawn checkpoint is early enough that step 1 re-reaches the corridor end in ~10 seconds.

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
