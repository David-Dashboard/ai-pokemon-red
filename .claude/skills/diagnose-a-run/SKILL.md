---
name: diagnose-a-run
description: Offline failure-triage playbook — when a paid brain run fails, looks wrong, or a scorer returns INSUFFICIENT_DATA, decide WHAT broke (perception vs brain vs world/emulator vs scorer taint) from the on-disk artifacts, WITHOUT spending another paid run. Invoke before proposing any re-run or vNext.
---

# Diagnose a run (offline, no re-spend)

A completed paid run is BANKED (paid-run-harness law 6, gate-methodology §4): you do NOT relaunch to
"get a better number". The job here is to explain the outcome from artifacts already on disk and to
separate a **real capability finding** from an **instrumentation artifact** — because those lead to
opposite next moves (redesign the world/predicate vs fix one line of the brief). Re-running to
diagnose is the mistake this skill exists to prevent.

## RULE 0 — probe-first: replay before you blame the perceiver

Before saying "the perceiver missed the entity / misread the HUD", REPLAY the run's own frames +
oracle offline. It is free and it is where most "perception bugs" turn out to be brain or scorer
bugs. See paid-run-harness ("Before blaming the perceiver: replay first"). Only after the replay
shows the perceiver genuinely wrong do you touch perception code.

## What every run leaves on disk (verified: `runs/brain_kirby_v3_1/`)

Under `runs/brain_<tag>/`:
| file | what it is | use in triage |
|---|---|---|
| `transcript.jsonl` | the BRAIN's stream — every `assistant` turn, tool call, and `user` tool-result. Last line is `type=result`. | did the brain act sensibly given what it saw? |
| `run.exit` | one line, `EXIT=<n>` (0=clean, 124=wall-clock timeout, 1=instant claude error) | infra death vs clean finish |
| `run.err` | claude/PyBoy stderr (empty or PyBoy noise on a good run) | claude crash lands here |
| `.mcp.json`, `CLAUDE.md`, `run.sh`, `seamcheck.sh` | launcher inputs (server def, the brief, launch line, seam check) | reproduce the exact wire |

Under `runs/brain_<tag>/world/`:
| file | what it is | use in triage |
|---|---|---|
| `oracle.jsonl` | RAM truth per step — **scoring/control only, NEVER an agent input**. Keys on a brain run: `step, t, frame, screen_path, patience_advances, perceived, watch`. `watch` = the RAM oracle (e.g. `{"hp": 6}`); `perceived` = what the perceiver reported. | did the event actually happen in RAM? was perception right? |
| `frame_000001.png … frame_NNNNNN.png` | per-step PNG (only if `--keep-frames`; 75 frames in the ref run) | the visual record to replay |
| `skills.jsonl` | `define_skill` / `redefine_skill` / `run_skill` records (name, steps, `stop_reason`, `executed_step_count`, `world_steps_used`, `iterations`) | did the skill machinery do what the brain intended? |
| `session.mp4` | full-session video (only if `--record`) | eyeball the whole episode fast |

`transcript.jsonl` type histogram on the ref run: `assistant` 191, `user` 73, `system` 282,
`result` 1, `rate_limit_event` 2. A `rate_limit_event` line = a 429 was hit mid-run (see decision tree).

## The decision tree — walk it top to bottom, STOP at the first NO

```
1. Did MCP connect?  (run.err mentions no MCP / EXIT=1 instantly / transcript has ~0 assistant turns
   or the brain emitted MCP_UNAVAILABLE)                         NO -> INFRA. Re-run the FREE seam check
   (paid-run-harness "FREE seam check"); fix .mcp.json/docker; relaunch is allowed (infra death). Not
   a capability finding.
2. Did frames advance?  (world/frame_*.png count > a handful AND oracle.jsonl step increments)
                                                                 NO -> WORLD/EMULATOR. Container crash,
   wrong --init-state, PyBoy stuck. Check run.err + session.mp4. Stale-image trap: rebuild after any
   core/ games/ world_mcp.py edit (paid-run-harness law 4) — stale perception looks like a brain bug.
3. Was it a 429 / wall-clock death?  (rate_limit_event lines; run.exit EXIT=124)
                                                                 YES + <~10 decisions -> INFRA, relaunch
   OK (law 6). YES + >=~10 decisions -> the attempt is SPENT: score what exists, bank the verdict.
4. Did the brain ACT SENSIBLY given only what it could see?  (read transcript.jsonl decisions against
   the same frames the brain had — NOT against oracle RAM, which the brain never sees)
                                                                 NO -> BRAIN bug (bad plan, ignored the
   brief, thrashed). This is a real capability finding about the brain — do NOT edit the brain to make
   one world pass (session-start North Star claim 2, Constancy); fix via the brief or bank the finding.
5. Did the perceiver report the world correctly?  (RULE 0 replay: compare perceived vs watch, and eyeball
   the frames)                                                   NO -> PERCEPTION bug. Now (and only now)
   perception code is implicated. HUD/oracle gotcha below.
6. Did the oracle RECORD the event the brain claims?  (grep watch/oracle.jsonl for the HP drop / state
   change the brain acted on)                                    NO -> either the event never happened
   (brain hallucinated) or the ORACLE is wrong (BCD gotcha below). Verify the oracle before trusting it.
7. Did the SCORER parse the brain's claims as intended?  (run the frozen scorer; read the exclusion
   counters below)                                               NO -> SCORER TAINT (instrumentation
   artifact, NOT a capability failure). This is the worked example. Fix the brief/scorer, not the brain.
```

Multiple things can be true at once. gate-methodology §6: separate INDEPENDENT failure modes explicitly —
fixing one does not fix the other — and record what VALIDATED despite the verdict.

## Offline tools (all free; Windows venv prefix shown)

Windows venv prefix (this host — bare `python3` hits the MS-Store alias trap):
`UV_PROJECT_ENVIRONMENT=.venv-win UV_NATIVE_TLS=true uv run --frozen python ...`

- **The gate scorer** (verdict + exclusion counters). Takes the RUN DIR (not the world/ subdir); it
  reads `<dir>/transcript.jsonl`, `<dir>/world/oracle.jsonl`, `<dir>/world/skills.jsonl`
  (`eval/score_entity_gate_v3.py` lines 671-674):
  ```
  UV_PROJECT_ENVIRONMENT=.venv-win UV_NATIVE_TLS=true uv run --frozen python eval/score_entity_gate_v3.py runs/brain_kirby_v3_1
  ```
  (Linux/WSL: drop the env prefix. Module form: `... uv run python -m eval.score_entity_gate_v3 runs/<dir>`.)
- **`eval/replay_tilemap.py`** — replays a run's REAL frames through the wired OverworldPerceiver and
  reports the tile→function recurrence curve + advisory-vs-behaviour agreement. This is the RULE-0
  perception replay for overworld games. CAVEAT: like `report_run`/`index_runs`, it reads a FLAT
  `<dir>/oracle.jsonl` (line 47, default arg `runs/fix4`) — it does NOT read a `brain_<tag>` run's
  `world/oracle.jsonl`, so on a brain run it hits `(skip <dir>: no oracle.jsonl)` and loads zero frames
  (a silent skip, NOT "perceiver replayed clean"). Built for the older flat `runs/run<ID>/` layout:
  ```
  UV_PROJECT_ENVIRONMENT=.venv-win UV_NATIVE_TLS=true uv run --frozen python -m eval.replay_tilemap runs/<dir>
  ```
  (Kirby is not overworld anyway. For non-overworld perception, eyeball `session.mp4`/frames vs
  `world/oracle.jsonl`'s `perceived` field directly.)
- **`eval/index_runs.py`** — catalogs every dir under `runs/` into `runs/INDEX.md` (date, steps, maps,
  battle, badges) from each run's `oracle.jsonl`. Orientation only. (Same layout mismatch as
  `report_run`: a `brain_<tag>` oracle lacks `map_id`/`in_battle`/`badges` and sits under `world/`, so
  brain-run rows show dashes/`NO oracle` — the map/battle/badge columns are Pokémon-Red-layout only.)
  ```
  UV_PROJECT_ENVIRONMENT=.venv-win UV_NATIVE_TLS=true uv run --frozen python -m eval.index_runs
  ```
- **`eval/report_run.py`** — scaffolds a per-run report from `<dir>/oracle.jsonl` + sibling
  `<dir>_console.log`: `... uv run --frozen python -m eval.report_run runs/<dir> --title "..." --cost "~$X"`.
  CAVEAT: it keys on `map_id`/`in_battle`/console-log lines, which the **Kirby brain-run oracle does
  NOT contain** (its keys are `step,t,frame,screen_path,patience_advances,perceived,watch`) — so on a
  `brain_<tag>` run it emits mostly empty rows. It is built for the older `runs/run<ID>/` Pokémon-Red
  layout, not the MCP brain runs. Use the gate scorer for brain-run verdicts.

## Reading a scorer verdict + the exclusion counters

The frozen scorer prints its verdict as the LAST block; quote it VERBATIM (gate-methodology §5). Then
read the exclusion counters — they are how the scorer says "I could not trust the claims", i.e. an
instrumentation problem masquerading as a capability outcome (`eval/score_entity_gate_v3.py`):
- **MALFORMED** — a protocol line the claim regex could not parse. `MALFORMED_MAX_FRACTION = 0.20`:
  `>= 20%` malformed → INSUFFICIENT_DATA before the bar is computed.
- **RETROACTIVE** — a NEAR line logged AFTER a later step's outcome was already observable (the brain
  could be back-filling). `RETROACTIVE_MAX_FRACTION = 0.20`: `>= 20%` retroactive → INSUFFICIENT_DATA.
- **macro-interior** — a claim whose step falls strictly INSIDE a `run_skill` span
  (`r.step - r.world_steps_used < n < r.step`); excluded from `ent_claims` (reported, not scored) so a
  claim "made" by a running macro can't be credited to the brain.
- **skill-mechanism guard** — needs `>= 1` qualifying-conditional `run_skill` call (predicate fired
  before `max_iters` AND `iterations >= 2`); `0` → INSUFFICIENT_DATA independent of the grounding bar.

INSUFFICIENT_DATA is a REAL verdict, not "try again" (gate-methodology §6): diagnose which counter
tripped, line-by-line, before proposing anything.

## WORKED EXAMPLE — entity v3.1: INSUFFICIENT_DATA was a scorer artifact, NOT a perception failure

Run `runs/brain_kirby_v3_1/` (2026-07-04, account-B, `EXIT=0`, `subtype: success`, 74 turns, $5.19).
Verdict report: **`reports/2026-07-04-entity-v3.1-verdict.md` — on branch `docs/entity-v3.1-prereg`
(PR #96), NOT in the working tree.** Read it with `git show origin/docs/entity-v3.1-prereg:reports/2026-07-04-entity-v3.1-verdict.md`
(`origin/` survives a missing local branch; if PR #96 has merged it is at that path in the tree). The
scorer command above reproduces the verdict verbatim, so it is the primary reproduction; the report is secondary.

Verbatim scorer output:
```
=== Entity-grounding gate v3 score (repaired bar + macro-interior exclusion + skill guard) ===
RETROACTIVE NEAR lines (logged after a later step's outcome was observable, excluded): 4

skill-mechanism guard: 7 run_skill call(s), 6 qualifying (executed_step_count >= 3), 0 qualifying-conditional (predicate fired before max_iters AND iterations >= 2) -- guard FAIL

VERDICT: INSUFFICIENT_DATA (4/13 NEAR lines are RETROACTIVE (logged after a later step's outcome was already observable) (>= 20% -- must stay below))
```

Walking the tree, it passes steps 1-6 (MCP connected, frames advanced, no 429, brain acted well,
perception was fine, oracle recorded the drops) and dies at step 7 — SCORER TAINT, two independent causes:

1. **Quoted-NEAR regex taint (fatal).** The scorer's `_NEAR_RE = re.compile(r"NEAR\s+id=(-?\d+)\s+step=(-?\d+)")`
   (line 113) is applied with `.search` over the WHOLE remember-line (line 357). The brain wrote
   bookkeeping like `DROP#1 at step=11 ... Covered by NEAR id=1 step=2,5` — and each of the 4 DROP notes
   re-matched as a NEAR claim. Being logged after the drop, all 4 counted RETROACTIVE → 4/13 = 30.8%
   `>= 20%` cap → unscorable. Verified line-by-line: the 4 retroactive lines are EXACTLY the 4 DROP
   notes; **zero genuine NEARs were late**. All 9 real NEARs were pre-approach; all 5 drops were covered
   in-window. Perception and grounding were fine — the CLAIM FORMAT collided with the scorer's regex.
   The brief mandated the NEAR shape but never forbade *quoting* it inside another note.
2. **`region_changed` degenerate vs converging enemies (independent).** Kirby's enemies walk toward
   you, so the suspect-box predicate fired after 1 press (`skills.jsonl` step 4:
   `region_changed(120,80,155,110) fired after 1 press(es) (1 iteration(s))`). The brain noticed and
   adaptively redefined the skill with `steps_elapsed(4)` (step 6 `redefine_skill`) — which the scorer
   discounts by design (a pure step-count loop never branches on world state). Result: 6 qualifying,
   0 qualifying-conditional → guard FAIL. A world-physics vs predicate-menu mismatch, not a brain bug.

The point: the run's headline was INSUFFICIENT_DATA, but BOTH pre-registered v3 fixes worked on-wire
(gate-methodology §6 "record what validated"). The correct next move is a brief/predicate fix
(v3.2 candidates (c) forbid quoting the claim shape; (d) a moving-target-safe predicate) — NOT a
perception change and NOT a re-run of v3.1. Deciding to spend on v3.2 is David's call, not the
diagnostician's (gate-methodology §6).

## HUD/oracle gotcha — verify the oracle before trusting step 6 (do NOT edit the brain for one world — Constancy)

If the oracle disagrees with what the HUD plainly shows, the ORACLE may be wrong, not the brain.
GB games store HUD numbers in **BCD** (one nibble per digit). Cave Noire current HP is BCD at
**0xC120** (`(b>>4)*10 + (b&0xF)`); the earlier `0xD389` claim was WRONG — a coincidental 2-anchor
match. When an oracle value looks off, test the BCD decode and check it against MANY displayed frames,
not 2. (Kirby's HP at `0xD086` is a plain int 0-5, so `_bcd()` is identity there — but never assume;
verify against the frames.) Full detail: memory `cave-noire-hp-oracle.md`.

## Sources
- `runs/brain_kirby_v3_1/` — artifact names/keys (`transcript.jsonl` types, `world/{oracle,skills}.jsonl`,
  `run.exit=EXIT=0`, 75 frames, `session.mp4`) verified on disk.
- `eval/score_entity_gate_v3.py` — `_NEAR_RE` (line 113), `.search` (line 357), `MALFORMED_MAX_FRACTION`/
  `RETROACTIVE_MAX_FRACTION = 0.20`, `MIN_NEAR = 3`, `B_K_CEILING = 0.70`, macro-interior exclusion,
  skill guard, run-dir arg (lines 671-674).
- `eval/replay_tilemap.py`, `eval/index_runs.py`, `eval/report_run.py`, `eval/README.md` — offline tools + usage.
- `reports/2026-07-04-entity-v3.1-verdict.md` (branch `docs/entity-v3.1-prereg`, PR #96) — the worked example, verbatim scorer output.
- `reports/2026-07-03-entity-v3-verdict.md` — the v3 prior (two independent failure modes; what validated).
- Memory: `entity-v3-verdict.md` (both failure modes), `cave-noire-hp-oracle.md` (BCD oracle gotcha),
  at `C:/Users/Succe/.claude/projects/E--AI-Personas-10-pokemon-and-chess-and-office/memory/`.
- Cross-reference (do not duplicate): `.claude/skills/gate-methodology/SKILL.md` (§5 scoring, §6 INSUFFICIENT_DATA),
  `.claude/skills/paid-run-harness/SKILL.md` (seam check, laws 4/6, replay-before-blaming).
