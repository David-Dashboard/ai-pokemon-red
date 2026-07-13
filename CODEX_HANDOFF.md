# Codex handoff — next 24h plan (written 2026-07-13 00:07, by the Claude session, at David's request)

You are a Codex agent working in `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red`
(WSL path `/mnt/e/...`). This doc is your task list for the next ~24h, in priority order.
Read it fully before acting. When it conflicts with the repo, trust the repo.

## 0. Ground rules (non-negotiable, they exist because each one was paid for)

1. **Read order at session start:** `HANDOFF.md` topmost `⇒⇒ NEWEST` block (position wins, not date) →
   `LEDGER.md` → the report the newest block points at. `CLAUDE.md` + `.claude/PROTOCOL.md` are law.
   The `.claude/skills/` library (15 skills, just merged in #101) is written exactly for you — a
   non-originating agent. `.claude/skills/README.md` is the index; invoke-by-reading before the
   matching move (esp. `safety-invariants`, `gate-methodology`, `paid-run-harness`, `dev-workflow`).
2. **Shared checkout etiquette:** other sessions (Claude) work in this SAME directory. Never assume
   the branch you left is the branch you're on — `git branch --show-current` before EVERY commit.
   Prefer `git worktree` isolation for any multi-step build. Do not rebase/reset branches you didn't
   create. (A mid-session branch switch already caused a misplaced commit once — 2026-07-11.)
3. **Money:** NO paid run (`claude -p`, account-B, any API spend) without David's EXPLICIT go for that
   specific run. $0 work never needs permission.
4. **Merges:** David merges, or explicitly delegates a named merge. Every PR needs a posted
   adversarial-review comment before merge (CLAUDE.md session rules).
5. **Science:** screen-only to the brain, oracle/RAM never on the wire; frozen scorers stay frozen;
   banked verdicts stay banked (INSUFFICIENT_DATA is a verdict, not "retry"); never touch the
   held-out games (Crystalis / Zelda-LA / SML / F-1 / Doom); every "done" needs evidence produced
   in-session; negative claims need exact paths checked; absolute dates only.

## 1. State as of 2026-07-13 00:00 (all verified, receipts in reports/)

- **main = `ce1f6da`**: #101 (15-skill library), #102 (entity-v4 typed-claims instrument, gated off
  by default), #103 (glyph R1 kill + reusable harness) all merged.
- **Entity lane CLOSED at v4** without paid attempt (`reports/2026-07-11-entity-v4-verdict.md`):
  the frozen bar + Kirby instrument pair is honest-hostile. Do NOT reopen with the old bar.
- **Glyph lane:** R1 cache-driven detection KILLED at its own gate
  (`reports/2026-07-11-glyph-r1-verdict.md`); fallback = brain-driven `read_region`. R2 would need a
  new design vs the merged harness (`eval/score_glyph_r1.py`); not scheduled.
- **MKDS continuous-time A/B: LAUNCH-READY, waiting only on David's go.**
  `reports/2026-07-11-mkds-{launch-surface,oracle-hunt}.md`. Launchers/briefs live UNTRACKED at
  `runs/brain_mkds_armA/` + `runs/brain_mkds_armB/` (runs/ is gitignored — do not delete them).
- Known repo quirks: `LEDGER.md` on main is one step stale (#101/#102/#103 now all merged; MKDS go
  is the only open David item). Untracked `spanish_teacher.*`, `AGENTS.md`, `.codex/`, `.agents/`
  files at root are yours.

## 2. The 24h plan (priority order)

### Task 1 — MKDS continuous-time A/B (paid, ~≲$10) — ONLY IF DAVID SAYS GO
The single highest-value item: it tests the CONDITIONAL half of skill compilation (rung-1 validated
only batching) on a continuous-time world. Pre-reg: `reports/2026-07-04-mkds-continuous-time-build-plan.md`
§7. **If David has not said "go" in your session, skip to Task 2 — do not launch.**

If GO:
1. Re-read `.claude/skills/paid-run-harness/SKILL.md` + `gate-methodology` + `run-brief-authoring` end to end.
2. Re-run `runs/brain_mkds_armA/seamcheck.sh` against image `gb-mcp-world:latest`
   (must be the 2026-07-11 rebuild, `sha256:dfd12eac87bb...`; if `docker images` shows older, rebuild
   first: `docker build -t gb-mcp-world .` from repo root in WSL). All 3 assertions must PASS
   (NDS_SKILLS=1 → skill tools present; unset → absent; KIRBY_SKILLS=1 cross-flag → absent).
3. Launch **Arm A first** (`runs/brain_mkds_armA/run.sh`): baseline, NO skill tools, `--max-turns 90`,
   account-B, blank-agent memory wipe lines already in the script — verify they're present before
   running. Bank the transcript + oracle under the arm dir. One attempt. Whatever happens is banked.
4. Then Arm B (`runs/brain_mkds_armB/run.sh`): `NDS_SKILLS=1`, same caps, one attempt.
5. Score: pinned metric = world-frames advanced per decision, bar **Arm B ≥ 1.3× Arm A**, AND Arm B
   needs **≥1 qualifying-conditional** `run_skill` call (its `stop_when` fired BEFORE hitting
   F=300/max_iters=8 — a real predicate branch, not a timeout). Task-progress oracle (scoring only,
   NEVER on the wire): RAM `0x022C8090` u8 — 0 during count-in, ticks up on real forward progress
   (verified twice; note: semantics beyond "monotonic progress tick" unconfirmed — treat exact lap
   boundaries with care, `reports/2026-07-11-mkds-oracle-hunt.md` has the caveats).
6. Write `reports/2026-07-13-mkds-ab-verdict.md` (numbers verbatim, honest bounds, costs), append the
   HANDOFF top block, PR the report, get an adversarial review posted, leave the merge for David.
   Budget guard: if Arm A alone exceeds ~$10, STOP before Arm B and report.

### Task 2 — v5 entity-bar redesign design doc ($0, no code, no run)
The entity lane is suspended pending a BAR REDESIGN — this is design-writing only.
Deliverable: `reports/2026-07-13-entity-v5-bar-redesign.md` + PR + ≥1 posted adversarial review.
Must address (all pinned in `reports/2026-07-11-entity-v4-verdict.md` "What a v5 must change"):
- Replace the forward-only coverage window `[n, n+15]` (candidates: backward windows `[n-W, n]`
  anchored on drops — matches the consequence-anchored intent; or exposure-normalized b_k that only
  counts brain-initiated approach phases; or an instrument whose threats are visible at range).
- Carry the two inherited-math exploit closures as MANDATORY brief clauses: forbid reactive
  same-step NEARs (the `revealed_at == step` boundary is legal in the frozen v3 math); cap NEAR cadence.
- PIN the press cadence (24 f/press seam vs 46 f/press `hold_frames=30` change visibility windows 4x).
- Inherit the #102 typed-claims instrument as-is (it is reviewed and gated off; do not redesign it).
- Name which North Star capability the gate buys (per `reports/2026-07-05-northstar-capability-map.md`).
A new bar = a NEW gate: fresh pre-registration, free pre-checks re-run, no "stricter-only" carryover
claims from v3/v4. Do NOT schedule any paid v5 run in this doc — design only.

### Task 3 — hygiene ($0, quick)
1. Refresh `LEDGER.md` to current truth (#101/#102/#103 merged; only-open David item = MKDS go;
   if you executed Task 1, re-arm the ledger for it). Branch + small PR, not direct-to-main.
2. Remind David in your summary: the 2026-07-04 leaked `settings.local.json` bearer token rotation is
   STILL OPEN (rotation is his action; never print the token value anywhere).

### Task 4 — OPTIONAL, only if Tasks 1-3 are done: $0 Kirby door-sub-room probe
Only relevant if your v5 design (Task 2) retains Kirby. The unverified lead: a door+enemy sub-room
past the pillar wall (`reports/2026-07-11-entity-v4-instrument-hunt.md`), previously reached only at
hp 2-3. Craft/find a healthier-hp savestate, measure: enemy visibility lead (presses), respawn
behavior, wall for move_blocked, retreat geometry. Report ≤80 lines to reports/, no code changes.

## 3. Do-NOT list for this 24h window
- No paid runs beyond Task 1's two arms (and those only on David's explicit go).
- No re-runs of any banked verdict (entity v1-v4, glyph R0/R1, GATE-3D run3, ARC wa30 depth).
- No edits to: the brain, `core/contracts.py`, frozen scorers (`eval/score_entity_gate_v3.py`,
  `eval/score_gate3d.py`, ...), existing tool schemas, anything under the held-out list.
- No touching `runs/` history or `runs/brain_mkds_arm*/` contents except by executing Task 1.
- Do not "fix" `HANDOFF.md` history blocks; append-at-top only.

## 4. End-of-window handoff (mandatory)
Append a new `⇒⇒ NEWEST (2026-07-13/14)` block to HANDOFF.md: DONE with evidence paths + costs,
PENDING explicitly, next list. Update LEDGER.md. Commit on a feature branch, push, PR anything
substantive with a posted review. State every claim with its receipt. If a task is blocked, say
by what — an unfinished silent stop is the only unacceptable outcome.
