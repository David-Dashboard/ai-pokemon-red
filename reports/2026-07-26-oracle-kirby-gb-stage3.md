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

**Where it stopped:** inside the water/moat room, unable to find its exit. The Lololo & Lalala boss
was never reached, so no Stage-2 → Stage-3 transition was observed, so **the discriminating sample
EX02 needs does not exist**. This is the same class of wall PR #169 hit (Castle Lololo navigation),
one room further in.

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

`0xC057, 0xC073, 0xC07B, 0xD03B, 0xD19F, 0xD3A9, 0xD3BA, 0xD3CD` read **`1` in every single sample
taken this session** — across ~24 driven bursts, 2 deaths + respawns, 2 confirmed room changes,
multi-floor climbing, and >500 savestate-chained sweep trials. That is additional evidence they are
stable within Stage 2, and it rules out "changes on room transition" and "changes on floor change".

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

## Route knowledge, so the next session starts where this one ended

1. From the respawn checkpoint, `','.join(['50:right','20:right+a']*8)` (560 frames) reaches the
   corridor's right end reliably.
2. `700:left` from there reaches the corridor's **left end**, where a door sits behind a `?` block.
3. **The door cannot be reached by walking** — the `?` block stops Kirby, and every walk-then-`up`
   sweep found nothing. It needs a **jump over the block first**: `doorsweep.py`'s `hop_left_up`
   action at walk offset 52 lands the transition (verified, `1 ROOM CHANGE`).
4. That puts Kirby in the water/moat room. **Its exit was not found**: 332 sweep trials from two
   different in-room states, both directions, and four action patterns (`up`, `down`,
   `hop_left_up`, `hop_right_up`, offsets 0-200) produced zero transitions. The exit is very likely reached by **swimming vertically** to the
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

The alternative — continuing the scripted/eyes-on hunt — is the option this session tested, and the
honest read is that it costs a lot per room and the water room is not obviously the last one. I do
not recommend a third scripted attempt without the vertical-navigation gap in `doorsweep.py` being
closed first.

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
