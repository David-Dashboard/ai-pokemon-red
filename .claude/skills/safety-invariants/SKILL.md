---
name: safety-invariants
description: The hard laws that must NEVER break in this project — read at session start and before any destructive, external, paid, or merge action; when in doubt about whether an action is allowed, invoke this first.
---

# Safety invariants — the laws

These are absolute. No deadline, no "obvious fix", no plausible shortcut overrides them.
If following one blocks your task, STOP and surface the conflict to David — that IS the correct outcome.

## 1. Destructive / world-affecting actions: show, then WAIT

Anything that sends, deletes, writes outside this repo, spends money, or publishes to a shared
place: show exactly what you would do and wait for David's explicit OK. Always.
(Source: David's global CLAUDE.md "Safety"; `.claude/PROTOCOL.md` §7 "Autonomy boundary".)

- Reversible, in-scope actions: proceed without asking (asking is a stall failure).
- Irreversible / external / scope-changing: show and wait (not asking is a safety failure).

**Standing exceptions (already granted — do not re-ask):**
- Account-B subscription `claude -p` game audits: pre-authorized 2026-07-02, run without per-run
  approval (`CLAUDE_CONFIG_DIR=/home/nvidia/.claude-b`). Does NOT extend to account A or any
  `ANTHROPIC_API_KEY` run — those are per-token spend and need David first.
- Pushing branches, opening PRs, posting adversarial review comments, running the test suite,
  `docker build`, read-only probes: established workflow, no per-action approval needed.

Prevents: unrecoverable external damage (a sent message, a spent dollar, a deleted file cannot be un-done).

## 2. Raw data / journals / oracle logs are APPEND-ONLY

Raw data, journals, and oracle logs (e.g. `world/oracle.jsonl`, `transcript.jsonl` run outputs)
are the source of truth. Never rewrite, edit, or delete them. Everything else must be derived
from them and reproducible. (Source: David's global CLAUDE.md.)

Prevents: silent corruption of the only ground truth — every verdict and report downstream becomes unfalsifiable.

## 3. Identity / persona data is hand-curated

Persona files are versioned, hand-curated data. Never let an LLM auto-mutate them.
(Source: David's global CLAUDE.md.)

Prevents: drift of the persona into something no human chose or reviewed.

## 4. Only David merges

Do not self-merge. The loop conditions — PR opened → adversarial review posted → findings triaged
with each claim verified against the code → full suite green → **CI green on the PR check** (two
locally-green PRs merged red on 2026-07-03; local green is not enough) — are prerequisites for
*requesting* a merge from David, not for performing one. Two memories conflict on this
(`review-process.md` reads the 2026-07-02/03 grant as self-merge authority; `claude-p-run-authorization.md`
says "the no-self-merge rule is unchanged"); until David resolves that, the stricter rule wins — no
self-merge. Genuinely contentious or large changes go to David's eyes first regardless. Never commit
to `main` directly. (Source: memories `review-process.md` + `claude-p-run-authorization.md`; repo
`CLAUDE.md` "Posted review = merge gate". Mirrors dev-workflow §12.)

Prevents: an unreviewed regression landing on `main` (a reviewer caught a shared-`core` guard on
2026-07-02 that would have broken cave_noire/gauntlet).

## 5. Paid runs: account B, blank agent, one attempt, oracle off the wire

- **Account B only.** `CLAUDE_CONFIG_DIR=/home/nvidia/.claude-b`. A 429 = account-level 5-hr cap:
  wait for reset, don't hammer, don't switch to account A or an API key.
- **Blank-agent memory wipe FIRST.** Every launcher `run.sh` must wipe account-B **client
  auto-memory** before launch — the `rm -rf .../.claude-b/projects/*/memory` line (see the
  paid-run-harness skill, law 2); that auto-memory once persisted cross-run via the shared
  repo-root project dir and contaminated verdicts. (Separate system: the Red *brain's* aria memory
  is reset via `reset_aria_memory.py` and only Pokémon-Red runs use it — don't conflate the two.)
- **One-attempt rule.** Pre-registered runs are banked as-is — one attempt per arm/seed; never
  relaunch to rescue a marginal result (only exception: infra death before the run produced data,
  where the pre-registration explicitly allows one relaunch).
- **Oracle/RAM/score never on the agent wire.** `watch` values (x/y/map/party/badges, HP) go to
  `world/oracle.jsonl` for offline scoring ONLY. The brain sees the screen. Leaking RAM truth to
  the agent invalidates the entire screen-only claim.
- **Never print `.env` contents.** They hold live bearer tokens; `Read(./.env)` is deny-listed in
  `.claude/settings.local.json`. Load values into env vars; never echo them.

Prevents: burned quota/money, contaminated experiments, and cherry-picked results that lie to you.

## 6. System-1 agents must escalate irreversible actions

A task-executing System-1 (masher, autoplayer, computer-use executor) must never blindly confirm
consequential prompts (erase / overwrite / delete / buy / send). Escalate to System-2 or take the
cancel/safe default. The blind `core/autoplay.ModalAutoPolicy` escape-ladder is acceptable ONLY
for `autoplay.py` throwaway data collection. (Source: memory `system1-reversibility-guard.md` —
Mario Kart DS blind-tapped "erase all saved data → OK".)

Prevents: an automation layer destroying state no one asked it to touch.

## 7. No brain edits (constancy)

The North Star is one fixed brain + swappable perceivers, screen-only. Game-specific fixes go
world-side (perceiver/world server), never into the brain. Every prior game's ceiling was
world-side perception, never the brain (HANDOFF.md, 3-console audit). Editing the brain to pass
one game falsifies the constancy claim for all of them.
(Source: memory `north-star-mandate.md`; `HANDOFF.md` "zero brain edits".)

Prevents: quietly converting the generalization experiment into a pile of per-game hacks.

## 8. Disabled/renamed things stay disabled

If David disarmed or renamed something — e.g. `LEDGER.md.disarmed` at the repo root, a hook, a
config — do NOT re-enable, rename back, or recreate it, even if the protocol says it "should"
exist. The disarmed state is a deliberate decision you may not have context for. Ask if it matters.

Prevents: silently reversing a human decision because a doc made re-enabling look like a fix.

## 9. Permission denials mean STOP, not route-around

The deny floor in `.claude/settings.local.json` currently blocks `Bash(git push*)` and
`Read(./.env)`; the `pretool_commit_gate.py` hook denies commits when the three fast invariant
tests fail. When the harness denies an action, do not dodge it via another shell, another tool, a
copy of the file, or a reworded command. Surface the denial and why you wanted the action; let
David decide.

**Carve-out — pushing a feature branch is allowed workflow, not a route-around.** The
`Bash(git push*)` deny exists to force pushes through the PowerShell tool (which prompts); pushing a
feature branch via PowerShell is the sanctioned route and is NOT a §9 violation. `Read(./.env)`, the
commit gate, and any other denial have no such carve-out. (See dev-workflow §12, session-wrap-up
step 5.)

Prevents: the enforcement layer becoming decorative — every other law here is only as strong as this one.

## Quick pre-action checklist

- [ ] External / destructive / spend? → show and wait (unless a standing exception above, verbatim).
- [ ] Touching raw data, journals, oracle logs? → append only.
- [ ] About to merge? → don't; those loop conditions gate *requesting* a merge from David, not doing it.
- [ ] Paid run? → account B, memory wiped, one attempt, oracle off the wire.
- [ ] Hook/permission just blocked you? → stop, report, don't work around.

## Sources

- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/.claude/PROTOCOL.md` (§7 Autonomy boundary)
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/CLAUDE.md`
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/HANDOFF.md` (blank-agent hole 2026-07-05; constancy audits; oracle "never on the wire")
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/.claude/settings.local.json` (deny list, hooks)
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/.claude/hooks/pretool_commit_gate.py`
- David's global `~/.claude/CLAUDE.md` (send/delete/append-only/identity laws)
- Memory: `system1-reversibility-guard.md`, `claude-p-run-authorization.md`, `review-process.md`, `north-star-mandate.md`, `mcp-claude-p-harness.md` (in `C:/Users/Succe/.claude/projects/E--AI-Personas-10-pokemon-and-chess-and-office/memory/`)
