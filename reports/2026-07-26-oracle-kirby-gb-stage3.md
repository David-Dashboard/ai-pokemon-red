# Kirby's Dream Land (GB) — Stage-3 attempt for the EX02 oracle (2026-07-26)

# ★★★ ANSWERED (2026-07-28): the EX02 stage oracle is `0xD03B`

`0xD03B` is Kirby's **0-indexed stage index**, and the game reads it to decide which stage to load.
Two independent legs:

1. **Observational** — a human (David) played Castle Lololo to its end and into Stage 3 with RAM
   sampling on (`record.py --mode human --ram --watch ...`, **1,128 sampled rows across two recording
   segments**, run `runs/2026-07-28_kirby_stage3_human/`).
2. **★ Causal** — writing `0xD03B` before a stage load *determines which stage loads*
   (`evidence/causal_map.png`), and the value then survives live play untouched — **9,000 frames** in
   Float Islands (`==2`), **4,740 frames** in Bubbly Clouds (`==3`, to the title-screen reset).

| stage | `0xD03B` | the four candidates | how established |
|---|---|---|---|
| Green Greens (1) | `0` | all `1` when re-entered; all `0` at cold boot | causal write + sustained live play + fresh boot |
| Castle Lololo (2) | `1` | all `1` | human run + causal write |
| **Float Islands (3)** | **`2`** | all `1` | human run (the 1→2 flip) + causal write + 9,000 live frames |
| Bubbly Clouds (4) | `3` | all `1` | causal write + 4,740 live frames + CONTINUE |
| Mt. Dedede (5) | `4` | — | causal write |

★ `0xD03B` = **STAGE INDEX (0-indexed), the byte the game itself reads.**
`0xD19F`, `0xD3A9`, `0xD3BA`, `0xD3CD` = **ELIMINATED — stale "past Stage 1" latches** that do not
track the current stage (they read `1` even in Green Greens).
`0xC057`, `0xC073`, `0xC07B` = **ELIMINATED** earlier this session (they vary *within* Stage 2).

Evidence from that one human run. What is **committed** is the
sampled oracle log `reports/probes/2026-07-26-kirby-gb-stage3/evidence/human_stage3_oracle.jsonl`
(1,128 rows across two recording segments; the step index restarts `257 → 0` at file row 258, so
`step` is not a unique key and the max `step` is 869 — index by file row). The full 8 KB-per-step WRAM
dump was checked **offline** against the run's `ram.bin`; **that dump is not committed** — it lives
under `runs/`, which `.gitignore:27` excludes, and no committed script reads it. Column → address
mapping, its empirical confirmation, and a re-derivation script that uses the committed JSONL alone:
`reports/probes/2026-07-26-kirby-gb-stage3/evidence/README.md` + `evidence/verify.py`.

- `0xD03B` (column `c1`) takes **only** the values `{1, 2}` across all 1,128 committed rows and changes
  **exactly once**, at file row 1082 (`step 824`).
- The change lands on the Stage-2 → Stage-3 boundary: the flip is on the blanked transition frame
  (`step 824`) and the **"STAGE 3 FLOAT ISLANDS" title card** is on screen at `step 828`, two sampled
  frames later — both panels are in `evidence/stage3_title_card.png`.
- **It survives two deaths without moving** — the exact falsification that killed the 2026-07-23
  candidates `0xD052`/`0xD3EE`. ⚠ ⓤ This one rests on the **uncommitted** `ram.bin`: the committed JSONL
  has **no HP/lives/death column**. Offline, Kirby's HP byte (`0xD086`) reaches `0` around file rows
  ~414 and ~766 — both inside Stage 2 — and `c1` does not move across either.
- The other four (`c2..c5`) are constant `1` across all 1,128 rows, *including inside Stage 3* — though
  in this recording only the **last ~46 rows** are inside Stage 3. **That short window is no longer
  the binding constraint**: the 2026-07-28 follow-up probe (below) watched them across 9,000 frames of
  live Float Islands play and, decisively, across 9,000 frames of live *Green Greens* play where they
  still read `1` while `0xD03B` read `0`.

## ★ The claim is now CAUSAL, not correlational (2026-07-28 follow-up probe)

Three tests, all $0 offline PyBoy. Artifacts under
`reports/probes/2026-07-26-kirby-gb-stage3/evidence/`; `verify.py` re-derives the log-based parts from
the committed files alone.

> **ⓤ = derived from an artifact that is NOT committed** (frames or `ram.bin` under `runs/`, or the
> savestate scratchpad — `.gitignore:27` and `:31`). Marked so a reader never has to guess which numbers
> a clean checkout can reproduce. None of the ⓤ figures is load-bearing for the verdict: the causal map
> and the `test1b` tables carry it, and both are reproducible from committed files (the causal map needs
> only the ROM). The ⓤ items are: the boss kill at file row 1018 (read off run frames), the Test 2
> 64-step gap that rests on it, the `meter_darkpx` figures in retraction #3, the two-deaths falsification
> (`ram.bin`), and the 1,098-savestate scan.

**1. `0xD03B` DETERMINES which stage loads** (`causal_map.py`, `causal_map.png`). From a Castle Lololo
state, write `0xD03B = V`, force a game over, take CONTINUE, and screenshot what loads:

| written | stage that loads |
|---|---|
| `0` | Green Greens |
| `1` | Castle Lololo |
| `2` | Float Islands |
| `3` | Bubbly Clouds |
| `4` | Mt. Dedede |
| *(no write — control)* | Castle Lololo (i.e. `1`, the value already there) |

This is the strongest result in the hunt. The game itself reads this byte to decide which stage to
load, so it is a **stage selector/index**, not a bystander that happens to correlate.

Two things make this cleaner than it looks. The **write precedes the load**, and the stage identity is
read off the *rendered frame*, not off RAM — so there is no way for the measurement to assume its own
conclusion. And `causal_map.py:40` re-asserts the value at the CONTINUE prompt "just in case": that
line turns out to be a **no-op** — the game had never cleared the value, so the re-assert cannot be
masking a reset. The single pre-load write is doing all the work.

**2. Sustained hold across live play** (`test1b.py`, `test1b_v{0,2,3}.{jsonl,png}`). 300 samples over
9,000 frames each, with liveness proven per run (Kirby controllable, `0xD051` taking many distinct
values, HP and lives moving):

| stage | `0xD03B` | transitions | the four latches |
|---|---|---|---|
| Green Greens | `{0}` | 0 | all `{1}` |
| Float Islands | `{2}` | 0 | all `{1}` |
| Bubbly Clouds | `{3}` → `0` at the end | 1 (the title-screen reset after lives ran out) | `{1}` → `0` at the same reset |

The Bubbly Clouds run is the one exception to "9,000 frames": the `3` holds for **4,740 frames /
159 sampled rows**, then lives run out and the title screen resets it. The two **9,000**-frame figures
are the Float Islands (`==2`) hold and the Green Greens reverse-dissociation run below.

**3. ★ The reverse dissociation — the strongest elimination evidence.** In the Green Greens run
`0xD03B` reads `0` while all four candidates read `1`. They are **stale latches that do not track the
current stage**: they say "past Stage 1" about a *history* that is no longer true of the *present*.
A cold boot (`freshboot.py`, `freshboot.png`) shows the other half: at a genuine first-ever Green
Greens all five read `0`. So the four only ever ratchet up, and never come back down.

So PR #169's two competing hypotheses are now separated: **one byte was the index and four were
latches.** A wired oracle built on any of the four would have silently passed EX02 the moment Kirby
left Green Greens.

⚠ **HOW Float Islands and Bubbly Clouds were REACHED — state this plainly, do not bury it.** They were
reached **by writing `0xD03B`** (plus `0xD086`/`0xD089` to force the game overs), because an
input-only Lololo kill was never achieved by the automation (see the retraction below). So
"`0xD03B` == 2 throughout Float Islands" is **partly by construction** — we put the `2` there.

What is **not** circular, and is the actual load-bearing evidence:
- The game **chose Float Islands because of that value**. The write happened *before* the stage load;
  which stage loaded was the game's decision, not ours. A bystander byte cannot do that.
- Across thousands of frames of real play afterwards — 9,000 in Float Islands, 4,740 in Bubbly Clouds
  — with deaths, respawns, room changes and a full life cycle, **the game never overwrote the value**.
  If it were scratch space, it would have been clobbered.
- **The four candidates stayed at `1` through a full stage load** into a stage that is neither Stage 1
  nor the stage they latched on.
- `0xD03B` was **written only during setup, never during any measurement run** (`test1b.py` performs no
  RAM writes at all).

⚠ **Still NOT wired, deliberately.** Editing `world_mcp.py` cascades into the frozen Gate-0
host/image pins (same reason PR #138 is deferred). Wiring belongs in ONE batched PR with the other
`watch = {}` worlds, timed with the next world-image rebuild.
*(Update 2026-07-28: that batched PR happened — **PR #180 wired `stage: 0xD03B` and rebuilt/re-pinned
both world images**. So "still not wired" is stale as of PR #180; the paragraph is kept because it is
why the wiring was batched. It stays wired — see the retraction below, which is about a bound's
status, not about the oracle.)*

## ⚠⚠ RETRACTED — "THE STAGE-4 BOUND IS DISCHARGED" (retracted 2026-07-28, my FOURTH wrong claim here)

**What I claimed** — here, in `HANDOFF.md`, and out loud when merging PR #173 — was that the
2026-07-26 bound (*"confirm `0xD03B` reads `3` at the Stage-3 → Stage-4 boundary before wiring"*) was
**MET**, and that the "one more anchor first" gate was **discharged**.

**What is actually true: the Stage-3 → Stage-4 boundary was never crossed.** Nobody cleared Float
Islands — not the automation, not the human run. What happened instead is a substitution: `0xD03B` was
**written** to `3`, the game loaded Bubbly Clouds, and the value then **held for 4,740 frames of live
play** (159 sampled rows of `test1b_v3.jsonl`, `t` 0 → 4,740), survived the CONTINUE prompt when lives
ran out, and reset to `0` only at the title screen.

**Why the substitution is still meaningful evidence — and why it does not satisfy the bound as
written.** It is strong evidence about what the byte *does*: the game chose Bubbly Clouds *because of*
the value, so `0xD03B` is demonstrably the stage selector, and 4,740 frames of untouched live play show
the game does not treat it as scratch. But the bound was not asking what the byte selects. It existed
to check that the byte **increments correctly on a real stage transition** — and a value we put there
ourselves, however well it holds, cannot answer that. The increment has been observed **exactly once**
(`1 → 2`, human run, file row 1082), not twice. Writing `3` and watching it stay `3` is a different
measurement wearing the bound's clothes.

**The bound is therefore STILL OPEN.** Precisely what discharges it: observe `0xD03B` transition
`2 → 3` across a real Stage-3 → Stage-4 completion, **with no memory write anywhere in the run**. That
requires actually clearing Float Islands, which has not been done.

**What is NOT affected, so nobody over-reads this.** The finding stands and the oracle stays wired.
The causal map (`0`–`4`, each value determining which stage the game loads), the 9,000-frame Float
Islands hold, the 9,000-frame Green Greens reverse dissociation, and the elimination of the four
latches are all independent of this bound. Five stage values are still anchored, four of them causally.
This retraction is about **one bound's status**, not about `0xD03B`.

⚠ **The claim propagated into `world_mcp.py` before it was caught, and is deliberately left there.**
The `kirby_dreamland` registry comment says the byte was *"confirmed reading 4 at Stage 4"* — wrong
twice over (`0xD03B` reads `3` at Stage 4, and nothing was confirmed at a boundary). `world_mcp.py` is
**byte-pinned** by `eval/fixtures/gate0_expected_pins*.json` (`host_code_sha256` `b4ae7cf3…`), so even
a comment-only edit breaks Gate-0 host/image parity and needs a world-image rebuild. Correct it in the
next batched world PR, not in a documentation change.

⚠ **The one wiring caveat that remains — `0` is not a positive signal.** `0xD03B` reads `0` in genuine
Green Greens, but it *also* reads `0` at cold boot before the game is initialised at all
(`freshboot.py`: at frame 10, `0xD03B`=0 with `hp`=0 and `lives`=0), and again at the title screen
after a game over. **`0` is indistinguishable from "not yet set".** Whoever wires EX02: a predicate
keyed on `== 0` is unsafe and will fire on boot and on the title screen; a predicate keyed on `>= 2`
is meaningful. Gate any read on the game actually being in play (e.g. `lives > 0`).

### Test 2 — "stage index" vs "stages cleared" DID NOT DISCRIMINATE

Recorded honestly because a null result is a result. The plan was: force a game over, take CONTINUE,
and see whether `0xD03B` matches the stage resumed into (index) or keeps counting (cleared-counter).
**It cannot separate them** — KDL's CONTINUE restarts the **same** stage, where both readings predict
the same value. `test2_continue.py` / `test2_boss_fresh.png` ran it; the test is simply not
discriminating, and no conclusion is drawn from it.

Weak supporting evidence for "index" that is *not* nothing: in the human run the boss kill is at file
row **1018** ⓤ, and `0xD03B` flips 1→2 at row **1082** — **64 record-steps later**, at the Stage-3 title
card. A "stages cleared" counter should have incremented **at the kill**. It did not; it incremented
when the next stage loaded. Real, but weak — a cleared-counter written slightly late would look the
same. **The causal map is much stronger evidence for "selector/index" anyway**, and that is what the
verdict rests on.

### Two incidental findings worth recording

- **No Stage-3 savestate existed anywhere before this.** ⓤ `scan_states.py` (committed) read `0xD03B` out
  of all **1,098** savestates in the session scratchpad and found `1` in every one but a single
  exception. The hunt was never one savestate away from the answer; the sample genuinely did not exist.
  ⚠ The scratchpad corpus is **not committed** (`.gitignore:31` excludes `*.state`), so the script is
  auditable but the count is not re-derivable from this checkout.
- **⚠ The human recording is NOT replayable.** `record.py --mode human` stores the **union** of buttons
  held across each 12-frame sampling window, not their timing (`record.py`, `_run_human`: `active` is a
  `set` accumulated over `args.sample_every` ticks). Replaying that button list diverges from the
  original — observed to diverge by step 38. Do not assume a human `buttons.jsonl` can be re-executed
  to reproduce the run; it is a *record*, not a *script*.

---

> ## ⚠ SUPERSEDED AS OF 2026-07-28 — everything below is the 2026-07-26 hunt narrative
>
> Everything from here down was written on **2026-07-26**, before David's human run. It is kept because
> the record of *how* the answer was reached — and of the two wrong claims made along the way — is the
> useful part. **Its verdict is wrong.** Where a section's conclusion was overturned it carries its own
> `SUPERSEDED` marker; read the header above for the current state.
>
> **FOUR claims of mine have now been retracted in this document.** The **fourth** is in the header
> above and is a *different* failure mode — not a bad detector but a **bad discharge**: I accepted a
> substituted measurement (write the byte, watch it hold) as satisfying a bound that asked for a real
> boundary crossing. The other three are all one failure mode — an unvalidated screen-region detector
> turning a rendering artifact into a game event:
> 1. *"randomised search corrupts the game"* (the HUD "validity guard") — retracted 2026-07-26.
> 2. *"savestates yield a frozen Kirby"* (the sprite-tile whitelist) — retracted 2026-07-26.
> 3. *"the automation beat the Lololo boss"* (the boss-meter dark-pixel reader) — **retracted
>    2026-07-28**; a blanked room-transition screen reads as an empty meter. The human beat Lololo;
>    the hill-climb did not.
>
> All three of those retractions are kept in full below. They are the load-bearing part of this
> document's honesty, and none of the four affects the `0xD03B` verdict.

Status: **$0 local probe only, offline PyBoy, NO LLM, NO Docker, NO paid run.** Worktree
`probe/kirby-gb-stage3` (`../ai-pokemon-red-kirby3`). Continues
`reports/2026-07-25-oracle-kirby-gb-stage.md` (PR #169), whose banked next step was: *reach Stage 3
and see whether any of the 8 surviving bytes reads `2` (real stage counter) or stays `1`
(one-time "past Stage 1" latch).*

**Verdict as of 2026-07-26 — ⚠ SUPERSEDED 2026-07-28 (the oracle is `0xD03B`; see header):
STAGE 3 NOT REACHED — EX02 REMAINS ORACLE_PENDING, unchanged.** The 8 survivors were, at that
point, still exactly as ambiguous as PR #169 left them. What this session did produce is (a) a materially
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
minor hits (best score gain 400) but never won. So no Stage-2 → Stage-3 transition was observed **at
this point in the session**, and the discriminating sample EX02 needs did not yet exist. This is a much
better place to be stuck than PR #169's (which never left the first corridor), and the remaining gap is
one won boss fight. *(The automation never won it — see the retraction "THE LOLOLO FIGHT IS WON" below.
David beat Lololo himself during the 2026-07-28 human run, and that is where the sample came from; see
the header.)*

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

## The 8 survivors — status as of 2026-07-26 (⚠ SUPERSEDED 2026-07-28), plus extra falsification

The five surviving bytes `0xD03B, 0xD19F, 0xD3A9, 0xD3BA, 0xD3CD` read **`1` in every sample taken
this session** — across ~40 driven bursts, several deaths + respawns, multiple confirmed room
changes (corridor → water room, corridor upper floors → battlements → warp-star area),
multi-floor climbing, >900 savestate-chained sweep trials and >900 randomised trials. That rules out
"changes on room transition", "changes on floor change" and "changes on death/respawn". The other
three (`0xC057/0xC073/0xC07B`) are eliminated — they vary within Stage 2 (see above).

It does **not** discriminate the two live hypotheses (real incrementing stage index vs one-time
past-Stage-1 latch), because both predict `1` everywhere inside Stage 2. **Do not wire any of
them.** The falsifying test was, as of 2026-07-26, unrun: reach Stage 3 and read them.

⚠ **SUPERSEDED 2026-07-28.** That test was run — David's human play-through into Float Islands. It
came out **`0xD03B` = counter, the other four = latches** (header). The "do not wire" instruction still
stands, but now for an entirely different reason: `world_mcp.py` edits cascade into the frozen Gate-0
pins, and `0xD03B` still needs its Stage-3 → Stage-4 anchor.
*(2026-07-28: this sentence's second half is the one that held up, and for a while it sat here
contradicting the header, which had declared the same anchor discharged — see the retraction in the
header. **The Stage-4 anchor bound is still OPEN.** The first half is superseded: PR #180 did wire the
oracle, as part of the batched world rebuild that re-pins Gate-0.)*

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

## ⚠⚠ RETRACTED — "THE LOLOLO FIGHT IS WON" (retracted 2026-07-28, my THIRD wrong claim here)

**What I claimed:** that `beat_lololo.py` (seed 600000 from `boss_fresh.state`) beat Lololo — "boss
meter 72 → 0, screen transition, Kirby alive at hp 3 / 3 lives, score 49960", banked as
`LOLOLO_WIN.state`.

**What is actually true: the automation never beat Lololo. The human did.** Checked directly on
2026-07-28 by loading the banked savestates and rendering them:

| state | `0xD03B` | meter region dark px | rendered room |
|---|---|---|---|
| `cont_boss2` | 1 | 72 | boss room (skull + 3 boxes, no score row) |
| `boss_room_left` | 1 | 72 | boss room |
| `boss_fresh` | 1 | 72 | boss room |
| `LOLOLO_WIN` | 1 | **86** | **corridor with a `?` block, normal `Sc: 49960` row** |
| `post_boss_final` | 1 | **86** | **byte-identical screen to `LOLOLO_WIN`** |

`LOLOLO_WIN.state` and `post_boss_final.state` render the **same frame** (identical screen MD5) and
differ by only **78 WRAM bytes**. Neither is the boss room: both show an ordinary corridor with the
score row restored. So `post_boss_final` is also not the far end of the "5 further rooms" chain.

**Why I believed it — the same error, a third time.** `beat_lololo.py` reads the boss meter as *dark
pixels in x 44-80, y 128-136*. That region is only a meter **while the boss HUD is up**; in a normal
room it holds the `Sc:`/`KIRBY` text, and on a **blanked screen it reads 0**. Measured on the human
run's own frames ⓤ:

    step 752 (boss room, boss at 1 box):  meter_darkpx =  24
    step 760 (boss dead, score row back): meter_darkpx =  81
    step 772 (room-transition blank):     meter_darkpx =   0   <-- "win"
    step 824 (stage-transition blank):    meter_darkpx =   0

So "meter 72 → 0" was **Kirby walking through a door and the screen blanking** — precisely the
room-transition signature this very report documents ("KDL blanks the screen between rooms"). The
hill-climb then saved the room on the other side and called it a victory. The "control run" that
supposedly proved the drops were real hits only showed that *idling* does not blank the screen.

**This is the third instance of one failure mode in this document**, and by now it is the finding:
*a detector defined by a fixed screen region, never validated against the negative case, converts a
rendering artifact into a game event.* The HUD "validity guard" did it, the Kirby sprite-tile
whitelist did it, and the boss-meter reader did it. Each time the cheap check — look at the actual
frame — settled it immediately.

**What survives:** the boss room *was* legitimately reached (`cont_boss2`, `boss_room_left`,
`boss_fresh` are all genuine boss-room arrivals, verified above), and the fight characterisation below
is measured and stands. What does not survive is the win, and everything downstream of it.

The three "unlocks" below are therefore **unvalidated** — they were credited for a win that did not
happen. Kept as hypotheses, not results:
1. **Match Kirby's HEIGHT to the ledge the block is on before inhaling.** He had been inhaling into
   empty air one ledge below the block the whole time. This alone produced the first-ever hit.
2. **Start at full HP.** The route arrives at 1-2 HP; dying in the boss room respawns Kirby at hp 6
   *and resets the boss to full*, so a fresh death is the cheapest full-health start
   (`boss_fresh.state`).
3. **All three hits must land on one life** — because dying resets the boss meter to 72. ⚠ The
   "control run" cited for this proves nothing: letting Kirby idle leaves the meter at 72 because
   idling never blanks the screen, not because the drops were hits.

### ⚠ RETRACTED with the win — "what happens after the win"

Everything in this subsection described a state that was never post-win. Struck, and corrected:

- ❌ *"There is no stage-clear sequence... Lololo here is a mid-stage encounter, not Castle Lololo's
  final boss."* **FALSE.** The human run shows the real thing: the boss HUD is up at steps 752-756,
  the score row returns at step 760 (the kill, file row 1018 ⓤ, with the stage-clear bonus), Kirby exits,
  and by step 776 he is on the **warp-star flight over the sky** — which lands in the Stage-3 title
  card at step 828. **Beating Lololo DOES end Castle Lololo.** I concluded the opposite from a state
  where the boss had never been fought.
- ❌ *"Input is ignored for a few hundred frames after the win."* Not a post-win observation; it was a
  freshly-loaded room. No claim retained.
- ⚠ *"`advance.py` chained forward 5 further rooms (49960 → 51240 → ... → 53260)"* — the chaining
  happened, but from a **mid-Castle-Lololo corridor**, not from past the boss. Note `post_boss_final`
  reads score 49960, i.e. it is *not* the end of that chain despite its name.
- ✅ *"Through every one of those rooms the five candidates read `1`."* True, and unaffected — those
  were ordinary Stage-2 rooms, which is exactly what the five reading `1` predicts.

The 2026-07-26 warning attached here — *"this is NOT the answer; the bytes staying 1 after the boss is
only evidence about rooms still inside Stage 2"* — was **correct, and is the one thing in this section
that held up.** It is the reason the wrong win did not become a wrong verdict.

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

## ⚠ SUPERSEDED — "The one thing left: win the Lololo fight"

**Kept as the plan that was never executed.** The automation never won this fight (see the retraction
above); the Stage-3 sample came from David playing it himself on 2026-07-28 (header). Ironically this
section's own framing was the accurate one — winning Lololo *does* end Castle Lololo, exactly as the
last bullet predicts. Read the list below as an unexecuted plan, not as work outstanding.

The hunt was, at the time, genuinely **one boss fight** from the Stage-3 sample. Concretely:

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

## Recommended next step — ★ TAKEN on 2026-07-28, and it is what answered the hunt

*(Written 2026-07-26 as "not taken here — needs David". David took it two days later; this
recommendation is the direct provenance of the header's verdict.)*

PR #169 already named the fastest path and this session is evidence for it: **a human plays Castle
Lololo with RAM sampling on.** The recorder already supports it — `2026-06-23_kirby_ramplay` was
captured with `"ram": true`. A few minutes of human play through Lololo & Lalala and into Float
Islands produces the Stage-3 sample directly, and the 8 survivors resolve to "counter" or "latch"
by inspection.

The alternative — continuing the scripted/eyes-on hunt — is what this session did, at length. The
honest read: it works, it just costs a lot per room (each new sub-area took roughly 8-12 directed
iterations to map and cross), and the areas kept coming.

⚠ The original 2026-07-26 text continued: *"...and the automated fallback that would have sped it up
turns out to corrupt the game. Castle Lololo's boss is still an unknown number of rooms away."* **Both
halves are wrong and are struck.** The first re-asserted the *"randomised search corrupts the game"*
claim that this very document had already **RETRACTED** — see "The false alarm, recorded because the
reasoning error is the useful part" above: the states were legitimate and the HUD "validity guard"
laundered my own error into apparent confirmation. The second was overtaken later the same session:
the boss room **was** reached (`cont_boss2`/`boss_room_left`/`boss_fresh`, all verified genuine). It was
**not** beaten by the automation — see retraction #3. David beat Lololo himself on 2026-07-28.

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

**Updated 2026-07-28.** The follow-up probe wrote to RAM (`0xD03B`, `0xD086`, `0xD089`) **in an
offline PyBoy process only**, to reach Float Islands / Bubbly Clouds for measurement. No savestate
under `runs/` was modified, no scorer or oracle was wired, and no measurement run performed any write
(`test1b.py` is read-only w.r.t. RAM). Still $0.

Three things above need amending for the human run and the report revision:
- The 2026-07-28 human session **did** write under `runs/` — `runs/2026-07-28_kirby_stage3_human/`, a
  new append-only recording. Nothing existing under `runs/` was modified or deleted. That directory is
  gitignored (`.gitignore:27`) and is **not** in this repo; only the sampled oracle rows and one
  montage PNG were copied out into `reports/probes/2026-07-26-kirby-gb-stage3/evidence/`.
- **`record.py` was edited** — the only production file this branch touches. Three changes: the `C`
  (checkpoint) hotkey wrote to `runs/<name>/` instead of the date-prefixed run dir and crashed the
  session with `FileNotFoundError`; `meta.json` now persists the `--watch` mapping (without it an
  `oracle.jsonl`'s column names are unresolvable after the fact — the gap this revision had to close by
  reconstruction); and the checkpoint counter and step index are now seeded from what is already on
  disk, so a second same-day session cannot silently overwrite `checkpoint_01.state` or the first
  segment's frames. Still no brain / `core/` / contracts / tool-schema / `world_mcp.py` / scorer /
  fixture / held-out edit, and still no oracle address wired.
