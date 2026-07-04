---
name: session-start
description: Invoke at the start of any new session in ai-pokemon-red (or after compaction/resume) to orient, state the task, and pick the next piece of work toward the North Star.
---

# Session start — orient, confirm, then act

## The North Star (do not paraphrase-drift it)

Pokémon Red is a **probe world**, not the goal. Canonical goal (HANDOFF.md §1, pinned 2026-06-22):

> Build **one agent — a fixed reasoning brain + a swappable perception layer — that completes
> human-given tasks at human-grade competence using only the screen and human-grade controls,
> across increasingly different worlds, cheaply, and without per-world training.**

Four testable claims (each separately checkable):
1. **Capability** — pixels in, human-grade actions out; NO privileged channel (no RAM/DOM/a11y/API).
2. **Constancy** — a new world swaps only the perceiver (+ per-world config); the brain (`ai-aria`) is reused UNCHANGED. Core claim, most likely to be false. Never edit the brain to make a world work.
3. **Generality** — two axes: embodiment ladder (2D game → 3D game → sim robot → physical robot, i.e. GB → GBA → NDS → beyond) and computer-use track (mouse+keyboard+screen).
4. **Cheap** — free System 1 does routine work; the LLM (System 2) wakes only at decisions; cost/task and wakes/task held low.

Invariant: no across-run training — the agent starts blank each run; skills are promoted to the library only on held-out proof.

## Read order (before doing ANYTHING)

All paths relative to repo root `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red`.

1. **`HANDOFF.md` — the top `⇒⇒ NEWEST` block first.** HANDOFF is append-at-top: the first `⇒⇒ NEWEST (date)` block is current state; blocks below it are history. Block dates are NOT monotonic (some historical blocks were misdated) and several are labeled `NEWEST` — position wins, always: take the literal topmost block, ignore the dates for ordering. Read the newest block + its `⇒ NEXT (priority order)` list + the paid-ledger line. (~first 120 lines is usually enough.)
2. **`LEDGER.md` if it exists** ("armed") — current-run task state per `.claude/PROTOCOL.md` §3. It does not always exist; absence is normal between long runs. If present: read it, state where things stand in one line, continue from its "Next". If it is absent or disarmed (a `LEDGER.md.disarmed` file), David disabled it deliberately — do NOT re-arm or rename it; recover mid-task state from HANDOFF's newest block + `git status`/`git log` on the current branch + any in-flight `runs/` artifacts.
3. **Latest verdict/report the NEWEST block points at** — verdicts live in `reports/` named `reports/YYYY-MM-DD-<topic>-verdict.md` (e.g. `reports/2026-07-03-skill-rung1-ab-verdict.md`, `reports/2026-07-03-entity-v3-verdict.md`). Read only the one(s) relevant to the task you're about to pick.
4. **`.claude/PROTOCOL.md`** — the working contracts (turn-ending, grounded progress, ledger discipline, bounded steps, delegation, anti-thrash, autonomy boundary). Skim it once per session; treat a hook firing as evidence you broke it.
5. Cold on the project? `reports/CONTEXT-BRIEFING.md` is the self-contained explainer (method, glossary, drift tripwires). `CLAUDE.md` at repo root has the implementation workflow and session rules.

## Then: state the task and WAIT

Per `~/.claude/CLAUDE.md` (David's global rules): **state the task in 1–2 sentences and wait for David's confirmation before acting.** Do not start implementing on your own reading of HANDOFF.

Exception: if David has already given the task in this session's opening message, restate it in 1–2 sentences and proceed only if unambiguous — on any ambiguity, ask ONE sharp question instead of picking a likely reading.

## Choosing the next work

- **Default source: HANDOFF's `⇒ NEXT (priority order)` list** in the newest block. Take item (1) unless David redirects.
- **Check the awaiting-David items** in project memory `C:/Users/Succe/.claude/projects/E--AI-Personas-10-pokemon-and-chess-and-office/memory/MEMORY.md` (e.g. promotion PRs, pre-registrations awaiting sign-off). Anything blocked on David: surface it, don't do it.
- **Gate-first:** build/promote/claim NOTHING until the relevant gate is defined and (for paid gates) pre-registered. A result without a pinned bar is not a result.
- **Probe-first / cheap-first:** probe = capability prediction; paid run = capability proof; minimize proof, maximize prediction. A paid end-to-end run is an expensive audit, invoked only when a probe leaves real uncertainty.
- **Branch-scan before building** (CLAUDE.md session rules): `git fetch`, scan origin branches for overlapping work, claim the work in HANDOFF's top block or a GitHub issue before writing code.
- **Workflow for any change** (CLAUDE.md): plan with Opus → feature branch off `main` (never work on `main`) → implement via a Sonnet subagent (do not implement in the main loop) → PR → fewer-than-5 adversarial reviewer agents post comments → address all → David merges.

## David's interaction style

- **Concise by default.** Summaries = files touched + what changed. No reasoning paragraphs, no verbose dumps, no emojis, no flattery.
- **Blunt; push back early and hard.** "I'm not sure, here are two options" beats confident wrong.
- **Ambiguity → ONE sharp question.** Never pick a likely reading and run.
- **Terse/short reply from David = something's off.** Stop and ask; do not keep tweaking.
- **Scope:** do exactly what was asked, then stop. Notice something else wrong → one line at the end, don't touch it.
- **Destructive/external/spend actions:** show what you'd do and wait for OK. Always. (Paid runs: account-B only, pre-authorized per memory `claude-p-run-authorization.md`; announce expected agent counts before multi-agent batches.)
- **Session end:** append a new top block to `HANDOFF.md` (date = actual clock — check it), state done vs pending explicitly. Absolute dates only (2026-07-04, never "yesterday").

## Session-start checklist

```
[ ] Read HANDOFF.md newest block + NEXT list
[ ] Read LEDGER.md if it exists
[ ] Read the verdict/report the newest block points at (if relevant to the task)
[ ] Skim .claude/PROTOCOL.md contracts
[ ] Check MEMORY.md for awaiting-David items
[ ] State the task in 1-2 sentences → WAIT for David's confirmation
[ ] git fetch + branch-scan before any build
[ ] Cut a feature branch; delegate implementation to a Sonnet subagent
```

## Sources
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/HANDOFF.md` (top blocks + §1 goal, lines 414-438)
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/CLAUDE.md` (workflow + session rules)
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/.claude/PROTOCOL.md` (working contracts)
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/reports/CONTEXT-BRIEFING.md` (method, probe-first, glossary)
- `C:/Users/Succe/.claude/projects/E--AI-Personas-10-pokemon-and-chess-and-office/memory/MEMORY.md` + `north-star-mandate.md` (mandate, review process, run authorization)
- `C:/Users/Succe/.claude/CLAUDE.md` (David's global interaction rules)
