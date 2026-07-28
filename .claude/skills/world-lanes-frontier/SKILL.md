---
name: world-lanes-frontier
description: The per-lane frontier map — for each world class beyond plain GB (ARC-AGI-3, VizDoom/3D, NDS/continuous-time, MiniWoB/computer-use, glyph/text) what is BANKED, what is OPEN, and the pinned next step. Invoke when a session is pointed at any non-GB lane, when a NEW environment class arrives, or when choosing which lane advances Generality next.
---

# World-lanes frontier map

Generality (North Star claim #3, **session-start**) runs on two axes: the embodiment ladder
(2D → 3D → sim robot → robot) and the computer-use track (mouse+keyboard+screen). Each lane below is
one rung. The law that binds them all: a lane advances by PERCEIVER/WORLD-side work only — the brain
is never edited to win a lane (**architecture-and-seam**; constancy already spans five world classes
with zero brain edits, `HANDOFF.md`). This skill exists so a cheap session does not re-derive lane
state from 200KB of HANDOFF, or re-run an experiment whose verdict is already banked. Verify the
"pinned next" lines against HANDOFF's newest `⇒ NEXT` list — this map was frozen 2026-07-04 and
**refreshed 2026-07-25** (glyph R1 ran and was KILLED; the MKDS A/B ran and is banked FAIL; the
ARC/NDS "conditional-loop half never fired" bound was falsified and corrected; ARC breadth was cut
from the critical path 2026-07-05; VizDoom's held-out conflict is now flagged. MiniWoB was not
re-verified this pass). The numbered `⇒ NEXT (N)` references below that predate 2026-07-25 are from
a 2026-07-05 snapshot and are superseded — check HANDOFF's CURRENT top-of-file `⇒ NEXT` block, not
the number.

| Lane | Banked headline | Open | Pinned next |
|---|---|---|---|
| ARC-AGI-3 | skill rung-1 A/B PASS 2.94x | breadth **cut from the critical path** (2026-07-05) | none — do not buy more wa30 runs without a new mechanism |
| VizDoom/3D | ⚠ **BLOCKED (held-out conflict)** — GATE-3D FAIL K=4.074; ceiling says bar reachable (7.333); A3-PC PASSED offline | **HELD-OUT conflict unresolved** (no carve-out exists) | none actionable without David's sign-off first; only then: brief edit, paid A3 re-run (pre-registered, HELD) |
| NDS/continuous | MKDS A/B **RAN, banked FAIL** (1.030x vs 1.3x bar); FAIL diagnosed STRUCTURAL 2026-07-25 (v2-design DRAFT) | perception breaks; progress-oracle wiring | none — v2 re-run of this instrument NOT recommended; David's call |
| MiniWoB | 5/5 click-button PASS $1.36 (2026-07-04); Gate-0 checkboxes 4/5 reward 1.0 (2026-07-25) | forms/typing; paid-seed human baseline | **HARD BLOCKER** — capture the human baseline (current top `⇒ NEXT` (1)) |
| Glyph/text | R0 FAIL banked; **R1 ran and is KILLED** at its own bar (PR #103) | R1.1 NOT decided (3 candidates) | none — David picks among vNext candidates |

## ARC-AGI-3 (abstract grid; the skill-compilation proving ground)

- **Adapter:** `core/arcagi3_world.py` — thin REST client for three.arcprize.org; the returned grid
  IS the symbolic state (no perceiver); `levels_completed` is oracle-only, never on the wire
  (`:13-16`); 250ms client throttle (`:49`); actions `ACTION1..7`, `ACTION6` takes coordinates.
  Skill tools gated behind `ARC_SKILLS=1` (`world_mcp.py:585`). **Live-run caveat:** the ARC API key
  is sourced WSL-side only (`runs/brain_arcagi3/.mcp.json` → `source /home/nvidia/.env`), not
  reachable from the Windows checkout.
- **Banked:** skill-compilation rung-1 A/B **PASS 2.94x** vs pinned 1.3x bar
  (`reports/2026-07-03-skill-rung1-ab-verdict.md`): Arm A 1/9 levels, 50 decisions, $7.78; Arm B 2/9
  levels, 34 decisions, $8.83 — the wa30 level-2 wall fell. **Honest bound, corrected 2026-07-25 (a
  cold session must read all three parts, not just part 2):**
  1. **Batching half — validated.** ARC rung-1, 2.94x. Unchanged by anything below.
  2. **Loop CONSTRUCT firing — the OLD "never fired" claim is DEAD.** It has now fired in two paid
     runs: Kirby (`steps_elapsed`, `runs/brain_kirby_v3_1`) and NDS MKDS (`elapsed_frames`, 9/10
     `run_skill` calls, 2026-07-13). The NDS firing cleared that build's own pre-registered
     conditional-half guard (`reports/2026-07-04-mkds-continuous-time-build-plan.md` §5: "a real
     predicate branch, not a ceiling timeout") — see `reports/2026-07-13-mkds-ab-verdict.md`
     §"Arm B conditional evidence".
  3. **World-state-BRANCHING predicates — attempted TWICE, ZERO qualifying evidence, two different
     failure modes.** Kirby's `region_changed` FIRED but DEGENERATELY, at iteration 1 (below the
     `iterations>=2` bar — "a one-shot dressed as a loop", **gate-methodology**'s "Known scorer/world
     gotchas" section `:115-119`;
     Kirby's enemies walk toward the avatar, so the watched box triggers on the first press). NDS's
     `idle_settled` NEVER FIRED — it ran to its `max_iters=8` ceiling without ever seeing 4
     consecutive under-threshold samples (`reports/2026-07-25-mkds-ab-v2-design.md` §5, quoting
     `skills.jsonl` step 6 verbatim). **No world-state predicate has produced qualifying conditional
     evidence in any paid run to date** (ARC 0/15 loop constructs at all; Kirby's one branching
     attempt degenerate; NDS's one branching attempt never fired). See **cheapness-skill-compilation**
     §5 and `reports/2026-07-25-mkds-ab-v2-design.md` §5 for the full receipts on both docs' sides of
     this correction.
  **Remedy for any NEW port's gate:** requiring the loop half to fire is not enough — it must require
  a QUALIFYING world-state-branching firing (`iterations>=2`, genuine screen-dependence). Do not
  default to a naive `region_changed`-style "box around a target" against a target that moves toward
  the avatar — that is the exact degenerate case above. Prefer `move_blocked`, a box AHEAD of the
  avatar's own heading, or gating on a STATIONARY target (`gate-methodology` `:119-122`).
- **Open:** breadth — one game (wa30), one attempt per arm. **Cut from the critical path 2026-07-05**
  (`reports/2026-07-05-northstar-capability-map.md:267-268`: "More levels buy ~nothing against
  A1-A6. Idle-capacity work at most.") — `HANDOFF.md:851`: "Do not buy more wa30 runs without a new
  mechanism." ARC does not appear in HANDOFF's current top-of-file `⇒ NEXT` block.
- **Pinned next:** none standing — idle-capacity work only, David's call, not on the priority path.

## VizDoom / 3D (the embodiment rung)

- **⚠ HELD-OUT CONFLICT — no carve-out exists, flagged prominently 2026-07-25.**
  `eval/dataset_split.py:30-36` lists `"Doom"` in `HELDOUT` ("3D first-person (ViZDoom) -- matches
  the `vizdoom_*` run dir"); this project's `CLAUDE.md` STOP condition is unqualified ("Never touch
  Crystalis/Zelda-LA/SML/F-1/Doom during development"); **eval-probes-and-datasets** §3 names only
  `eval/cross_game.py` and `eval/verify_heldout.py` as sanctioned held-out consumers. Yet the lane
  already calibrated on it — `core/yaw_flow.py:4-7` pins its P1 floors from `runs/vizdoom_precheck/`
  — and `reports/2026-07-05-northstar-capability-map.md:233` states "Doom is burned for 3D-primitive
  claims." Two later sessions explicitly routed AWAY from Doom on held-out grounds
  (`reports/2026-07-05-entity-v4-design.md:129`: "NOT doom — doom is HELD-OUT per PR #101's CLAUDE.md
  / eval-probes-and-datasets §3"; `reports/2026-07-13-entity-v5-candidate-shortlist.md`'s
  Doom/VizDoom row: "Do not use for v5 development"). **No documented carve-out exempting the
  GATE-3D lane from the held-out law exists.** Treat this as: VizDoom work requires David's explicit
  sign-off; a cold session must NOT start it unattended.
- **Adapter:** `core/vizdoom_world.py` (TURN_LEFT/TURN_RIGHT/ATTACK, 4-tic steps). Perception
  primitives: `core/yaw_flow.py` (P1 ego-rotation, R0-validated: sign-agreement 0.964, None-rate
  0.201, `:1-8`) and `core/stationary_movers.py` (P2, only valid on ego-stationary pairs — see
  **perception-primitives**). Free probes: `eval/vizdoom_flow_ceiling.py`, `eval/ceiling_gate3d.py`.
- **Banked:** paid GATE-3D run **FAIL, K = 4.074 vs bar 5.61** (`runs/brain_gate3d/run3_v_FAIL` —
  also the most expensive run ever, $82.86; see **long-horizon-runs**). The free ceiling test then
  answered the prior question: a perfect azimuth-seeker reaches **K = 7.333** at 8px tolerance —
  "**No re-pin is needed; the bar stands**" (`reports/2026-07-03-gate3d-ceiling-test.md:128,:130`);
  at 25px tolerance even the ceiling fails (K = 3.433), so tolerance is the lever. The onset-scoring
  fix (A3-PC) already **PASSED offline** (`HANDOFF.md:842`, 2026-07-05: "A3-PC PASS"); the paid A3
  re-run is pre-registered (`reports/2026-07-05-p1-clutter-redesign.md:312-325`) but still HELD
  pending David's go (`HANDOFF.md:842-846`) — no paid A3 attempt has run as of 2026-07-25.
- **The "tolerance tightening" knob is a BRIEF edit, not a code parameter:**
  `runs/brain_gate3d/CLAUDE.md:37`, the hunt-loop's `|x-160| ≲ 25` centering tolerance, `25` → `~8`.
  **A2.2 forbids softer re-runs**: "loosening is forbidden, period... never a softer bar"
  (`reports/2026-07-04-vizdoom-3d-floor-design.md:526-528`) — the tightening only ever moves the bar
  stricter.
- **Open:** closing the 4.074 → 5.61 gap is brief/tolerance work, not perception work; AND the
  held-out conflict above must be resolved with David before any further Doom work.
- **Pinned next:** brief-side tolerance tightening (the `CLAUDE.md:37` edit above) BEFORE any paid
  re-run; then the doom scan-and-center macro port — its gate must require the conditional-loop half
  (see the ARC section's corrected bound above). Both require David's explicit sign-off given the
  unresolved held-out conflict.

## NDS / continuous time (the hardest perception frontier)

- **Adapter:** `core/nds_emulator.py` + `core/nds_perceiver.py` (ScreenRoleDiscovery routes the
  grid perceiver to the discovered gameplay screen; touch tools via `core/nds_perception_plugin.py`).
  NDS skill tools (`define_skill`/`run_skill`) are gated behind `NDS_SKILLS=1`, scoped to
  `_NDS_SKILLS_WORLDS` (gate fn `world_mcp.py:847-854`, checked at `:905`). **Open PR #138** adds an
  NDS touch-drag helper primitive (the A6 continuous-action gap), gated off by default
  (`HANDOFF.md:99`).
- **Banked:** the 3D probe (`runs/nds3d_probe/FINDINGS.md`, on-disk) — MKDS race reached
  vision-guided; savestate `mkds_race_start.state` banked; **idle change 12.22%/frame mean vs 33.23%
  accelerating** (`:329-330`) — the world changes without input, breaking the discrete-step
  assumption; three perception breaks documented (free-form non-tile font/HUD, rotating minimap
  kills tile-grid, continuous chase-cam roll kills discrete-facing). The `stop_when` bridge design
  (`reports/2026-07-04-continuous-time-stopwhen-design.md`) and the MKDS build spec + A/B
  pre-registration (`reports/2026-07-04-mkds-continuous-time-build-plan.md`) both merged 2026-07-04.
- **The paid A/B RAN 2026-07-13 and is banked FAIL** (`reports/2026-07-13-mkds-ab-verdict.md`; the
  first account-B launch hit a weekly cap 429 at $0 before MCP connect, banked separately in
  `reports/2026-07-13-mkds-ab-blocked.md`; David then authorized the default-account relaunch).
  **Primary batching bar: FAIL — 1.030x observed vs 1.300x required** (Arm A 229.538 frames/decision
  @ $0.77483; Arm B 236.500 @ $0.7740115; total $1.5488415). The build's own pre-registered
  conditional-half guard PASSED (`run_skill`=10, `stop_when_fired`=9/10 — see the ARC section above
  for the full 3-part reading of what kind of predicate actually fired). The build plan's §4
  `s=24/k=10` sizing is **STALE — shipped code pins `_NDS_SKILL_SAMPLE_STRIDE=4`**
  (`world_mcp.py:793`; noted in `HANDOFF.md:587`).
- **Deeper diagnosis, 2026-07-25** (`reports/2026-07-25-mkds-ab-v2-design.md`, DRAFT/NOT AUTHORIZED —
  a design response to the FAIL, not a v2 pre-registration): the FAIL is structural, not a usage
  fluke. Arm A's always-on `press_sequence` primitive and Arm B's `run_skill` batch to near-identical
  per-call frame ceilings on this task (288 vs 280 frames/call) — "racing two batchers whose caps are
  the same order of magnitude." **Recommendation of record: (e) bank the FAIL, do not design a v2
  re-run of this instrument** — removing `press_sequence` from Arm A to manufacture a gap is
  explicitly REJECTED ("the same class of error as loosening a numeric bar"). If this lane reopens,
  the named preconditions are: (1) VizDoom's `mover_visible` scan-and-center port is a fairer,
  already-queued instrument for the conditional-loop claim (not cap-matched to a batching primitive
  the way `elapsed_frames`/`press_sequence` are); (2) a $0 offline probe of whether `idle_settled` (or
  a successor) fires reliably on ANY reachable perception-free MKDS transition during real gameplay,
  before spending on this world again.
- **Progress-oracle status, merged 2026-07-23** (`reports/2026-07-23-oracle-mkds-lap.md`,
  load-bearing for any future task-progress metric here): `0x022C8090` re-verified live and is
  **checkpoint-index-within-lap, BIDIRECTIONAL** — it decrements on a confirmed wrong-way U-turn, not
  monotonic as the 2026-07-11 hunt assumed. Companion `0x022C8094` did not decrement on that same
  event (one data point, unconfirmed lead). **Lap-count byte: NOT FOUND** — no "LAP 1/3 → LAP 2/3"
  transition was observed. Neither byte is wired into `GAMES["nds"]["watch"]`, still `{}`
  (`world_mcp.py:172`) — off the agent wire.
- **Live-state caveat, checked at edit time:** unlike the clean/idle state reported earlier this PR,
  `ai-pokemon-red-mkds` (branch `probe/mkds-lap-oracle`) now shows an untracked, in-progress probe
  directory — a lap-oracle hunt is active in a parallel worktree as of 2026-07-25. Re-run
  `git worktree list` / `git status` yourself before assuming this section's state; do not rely on a
  point-in-time snapshot for an actively-touched lane.
- **Open:** the three perception breaks (each needs a primitive, not a hack —
  **perception-primitives** extension rules); wiring the (now bidirectional) progress oracle into
  `watch` if a task-progress metric is ever wanted for this world.
- **Pinned next:** none standing for a same-instrument v2 — the pre-registered A/B is spent
  (one-attempt rule, **gate-methodology** §4) and a same-instrument re-run is explicitly NOT
  recommended (diagnosis above). If budget is spent on this axis at all, the v2-design doc's own
  reading of priority order puts VizDoom brief-tightening ahead of any further MKDS spend. David's
  call either way.

## MiniWoB / computer-use (the second Generality axis)

- **Adapter:** `core/miniwob_world.py` — Selenium/Chromium; DOM withheld, pixels + task utterance
  only; reward is oracle-side (`:1-12`). Image pinned in `Dockerfile.miniwob`.
- **Banked:** first brain run **5/5 click-button episodes, reward 1.0 each, $1.36, pixels-only**
  (`runs/brain_miniwob/`; `HANDOFF.md:935-942`) — the browser rung of "constancy now holds across
  FOUR world classes" (`HANDOFF.md:940`).
- **Checkboxes RAN, 2026-07-25 (corrects this map's own prior "harder tasks: not yet attempted"):**
  Gate-0 Arm W, held-out seeds 1000-1004 (`HANDOFF.md:23-28`,
  `reports/2026-07-24-gate0-paired-verdict.md`) — 5 episodes, `abandoned==False` throughout, **4/5 at
  reward 1.0**, seed 1001 a genuine partial at 0.6667; 97 actions / 295.594s, $1.02958. Frozen
  predicate `_miniwob_success = (False, ['miniwob_episode_1_terminal_not_success'])` — the episode
  rewards are real per-episode measurements; the paired Gate-0 verdict itself is
  `CONSTANCY_BREACH`/`NO_GO` for reasons spanning both Gate-0 arms, not specific to MiniWoB
  (`reports/2026-07-24-gate0-paired-verdict.md`).
  **VOID AS GATE-0 EVIDENCE** (breach stands, cause proven benign — fixture placeholder lifecycle): `reports/2026-07-28-gate0-constancy-breach-addendum.md`; applies equally to this map's MiniWoB lane row (:27) and to the Gate-0 citations at :258 / :267.
- **Open:** forms/typing (the only MiniWoB task classes still untried); the paid-seed human baseline.
  **MiniWoB is currently the project's stated HARD BLOCKER**, not an idle lane: capturing the
  MiniWoB paid-seed human baseline is item (1) on HANDOFF's CURRENT top-of-file `⇒ NEXT` list
  (`HANDOFF.md:95`: "HARD BLOCKER — capture the MiniWoB paid-seed human baseline... before any future
  Gate-0 verdict can be clean"), required before Gate-0 can produce a clean verdict.
- **Pinned next:** capture the MiniWoB paid-seed human baseline (David's — see `HANDOFF.md:95`).

## Glyph / text (reading, the cross-cutting perception lane)

- **State:** R0 text-region detector **FAILED its gate and the FAIL is banked** (recall 0.27,
  precision 0.49, 5 phantom boxes vs pinned 0.85/0.70/0 — `reports/2026-07-03-glyph-r1-cache-driven-
  detection.md:5`; the module stays as a documented-honest failure, **perception-primitives**).
  `core/glyph_cache.py` (Gate 2, the cache-hit mechanism) PASSED at 96.9% frac_free and is unaffected
  by the R1 result below — it remains reusable on its own.
- **R1 build RAN and is banked KILL, 2026-07-11** (`reports/2026-07-11-glyph-r1-verdict.md`, PR
  #103, $0 — an offline scoring attempt against an existing fixture, no paid brain run). Pooled
  **precision 0.283 ≤ the 0.49 kill floor** (R0's own failed precision; pooled recall also 0.283).
  All 4 qualifying GBA games (DBZ, FFVI, Zelda Minish Cap, SMA2) individually verdict KILL. Per the
  verdict doc verbatim: "this is attempt 1 of 2 with a clean result — no second attempt is warranted
  or permitted by the stricter-only amendment rule" (a kill is not "missed the bar," it's the floor).
  **Mechanism:** GBA's anti-aliased fonts blow the confirmed-glyph vocabulary to 191–989 keys from
  just 5 warmup frames (vs Gen-1's 46 keys, the configuration under which Gate 2 passed) — under
  Hamming≤4 tolerant matching, R0's collision-mode failure returns. The detector code is merged but
  **UNWIRED** — do not lift `core/text_regions_r1.py` into a wired path; the harness + fixture stay
  banked, on-disk, reusable if a future attempt is authorized. **The fallback of record is
  brain-driven `read_region`, unassisted** (no detector).
- **Open:** whether to pursue an R1.1 at all — **NOT decided, David's call.** Three vNext candidates
  are listed in the verdict doc (`...verdict.md:163-172`): (1) score against a crisp-font game (Gen-1
  Pokémon) to isolate the anti-aliasing diagnosis from the small-warmup-sample variable; (2) a
  stricter Hamming tolerance (a stricter-only amendment, needs its own dated doc, counts against the
  2-attempt cap); (3) accept the fallback and do not pursue R1.1. NDS caveat unchanged: the cache
  does not transfer to DS free-form fonts (`runs/nds3d_probe/FINDINGS.md`).
- **Pinned next:** none standing — R1 is spent (KILL, one-attempt cap effectively reached per the
  verdict's own reading). Wait for David to pick among the vNext candidates above before any further
  glyph-lane build.

## Also live (not owned here)

The first long-horizon run (`runs/brain_kirby_longhaul/`, 2026-07-04, 316 turns / $42.98) is a
LENGTH experiment on the GB lane, not a new world class — **long-horizon-runs** owns it.

## Picking a lane / handling a NEW environment class

- Default: HANDOFF's `⇒ NEXT` priority order — take (1) unless David redirects (**session-start**).
- Strategic companion: `reports/2026-07-05-northstar-capability-map.md` — the six capabilities the
  North Star still requires, each with its falsifier and cheapest probe; every gate pre-reg should
  name which capability it buys evidence about. Lanes = where each WORLD stands (this skill);
  the map = what each spend should be FOR.
- A genuinely NEW environment class (new console, new input modality, new world shape) gets the
  **new-world-port** treatment: binding spike → registry → free probes → constancy audit. Then add
  a lane section HERE in the same PR (this map must not rot — a lane missing from this file will be
  re-derived expensively by the next cold session).
- Before ANY paid spend in a lane: check its "Banked" row — re-running a banked experiment without a
  fresh pre-registration violates the one-attempt rule (**gate-methodology** §4).
- The lane-priority question is David's when it involves spend; your job is to surface the frontier
  state, not to pick the spend.

## Sources

- `core/arcagi3_world.py`, `core/vizdoom_world.py`, `core/miniwob_world.py`, `core/nds_emulator.py`,
  `core/glyph_cache.py`, `core/yaw_flow.py`, `world_mcp.py` (`:585` ARC_SKILLS, `:847-854`/`:905`
  NDS_SKILLS arm isolation, `:793` `_NDS_SKILL_SAMPLE_STRIDE`) — adapters/flags/line numbers
  re-verified 2026-07-25 (previous pin of `:541`/`:629-632` had drifted).
- `reports/2026-07-03-skill-rung1-ab-verdict.md`, `reports/2026-07-03-gate3d-ceiling-test.md`,
  `reports/2026-07-03-glyph-r1-cache-driven-detection.md`,
  `reports/2026-07-04-continuous-time-stopwhen-design.md`,
  `reports/2026-07-04-mkds-continuous-time-build-plan.md`,
  `reports/2026-07-04-vizdoom-3d-floor-design.md` (A2.2 no-softening rule, `:526-528`),
  `reports/2026-07-05-p1-clutter-redesign.md` (A3 re-run conditions, `:312-325`),
  `reports/2026-07-05-northstar-capability-map.md` (ARC cut from critical path, `:267-268`; "Doom is
  burned", `:233`), `reports/2026-07-11-glyph-r1-verdict.md` (R1 KILL, PR #103),
  `reports/2026-07-13-mkds-ab-blocked.md`, `reports/2026-07-13-mkds-ab-verdict.md` (MKDS A/B FAIL),
  `reports/2026-07-25-mkds-ab-v2-design.md` (structural-confound diagnosis + the 3-part loop-half
  correction, §5), `reports/2026-07-23-oracle-mkds-lap.md` (bidirectional progress byte, lap-count
  NOT FOUND), `reports/2026-07-24-gate0-paired-verdict.md` (MiniWoB Gate-0 Arm W),
  `reports/2026-07-05-entity-v4-design.md:129`, `reports/2026-07-13-entity-v5-candidate-shortlist.md`
  (both route away from Doom on held-out grounds) — banked verdicts/designs.
- `eval/dataset_split.py:30-36` (`HELDOUT` includes Doom); **eval-probes-and-datasets** §3 (the
  sanctioned held-out consumers, `cross_game.py`/`verify_heldout.py`).
- `runs/nds3d_probe/FINDINGS.md`, `runs/brain_miniwob/`, `runs/brain_gate3d/run3_v_FAIL/`,
  `runs/brain_gate3d/CLAUDE.md:37` (the tolerance-tightening knob), `runs/brain_arcagi3/.mcp.json`
  (ARC API key sourced WSL-side only) — on-disk, gitignored; present only in the main checkout, not
  in worktrees cut from origin.
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/HANDOFF.md` — `:23-28` (Gate-0 Arm W /
  MiniWoB checkboxes), `:95` (current top-of-file `⇒ NEXT`, the MiniWoB HARD BLOCKER), `:99` (open PR
  #138), `:587` (code pins `s=4` vs the build plan's `s=24`), `:842` (A3-PC PASS), `:851` (ARC cut),
  `:935-942` (first MiniWoB banked run + "constancy now holds across FOUR world classes"). Line
  numbers in a file that grows by prepending drift fast — **this map's own previous pins (`:213`,
  `:242`, `:283`, `:289`) had already drifted onto unrelated Gate-0/Cheap/test-verification prose by
  2026-07-25**, which is why every pin above was re-verified against the current file rather than
  carried forward. The numbered `⇒ NEXT (N)` this map cited before 2026-07-25 are from the 2026-07-05
  snapshot and are superseded — read HANDOFF's CURRENT top-of-file `⇒ NEXT` block, not a number.
- Cross-refs: **architecture-and-seam** (constancy law), **new-world-port** (mechanics),
  **gate-methodology** (one-attempt), **cheapness-skill-compilation** (loop-half bound, corrected
  2026-07-25), **perception-primitives** (primitive extension rules), **long-horizon-runs** (the
  length axis).
