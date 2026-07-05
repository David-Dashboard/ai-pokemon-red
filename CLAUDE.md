# ai-pokemon-red

LLM agent plays Pokémon Red. Architecture: `ARCHITECTURE.md`. Continuity: `HANDOFF.md`. Plan: `ROADMAP.md`.
Repo map / where things live: `README.md` (`## Repo map`). Global working rules live in `~/.claude/CLAUDE.md`;
this file adds project principles only.

## North Star guardrails (every model, every session — added 2026-07-05 by the retiring lead)

**The goal (HANDOFF §1, do not paraphrase-drift):** ONE fixed brain + a swappable perceiver, completing
human-given tasks at human-grade competence from the SCREEN ONLY, across increasingly different worlds,
cheaply, without per-world training. Pokémon Red and every other game are PROBES, not the goal.

STOP conditions — when about to do any of these, invoke the named skill FIRST (`.claude/skills/README.md`):
- Edit the brain / `core/contracts.py` / tool schema to make a world work → **architecture-and-seam** (that edit falsifies Constancy for ALL worlds).
- Spend money / launch a paid run → **safety-invariants** + **gate-methodology** (+ **long-horizon-runs** past ~100 turns). Every gate pre-reg names which capability it buys: `reports/2026-07-05-northstar-capability-map.md`.
- Re-run a failed/odd run → **diagnose-a-run**. Banked = banked; INSUFFICIENT_DATA is a verdict, not "try again".
- Write new perception code → **perception-primitives** (probe first; the primitive likely exists).
- Tune/calibrate anything → check the HELD-OUT list first (**eval-probes-and-datasets** §3). Never touch Crystalis/Zelda-LA/SML/F-1/Doom during development.
- New game/environment class → **new-world-port** + a lane check in **world-lanes-frontier**.

Epistemics: trust RUNS over comments, docstrings, and memories — when they disagree, re-run and believe
the run (a docstring lied to us on 2026-07-05; the scorer settled it). Negative claims need receipts
(exact paths checked). Every "done" needs evidence produced this session.

Long-run work: follow @.claude/PROTOCOL.md (ledger + gates + delegation) — `LEDGER.md` is current-run task state; `HANDOFF.md` is the cross-session narrative.

## Implementation workflow (follow for every change)
1. **Plan with Opus.** Design the change in Opus (plan mode) and get the plan agreed before any code is written.
2. **Feature branch.** Cut a branch off `main` before implementing — never work on `main` directly.
3. **Implement with a Sonnet agent.** Hand the agreed plan to a Sonnet subagent to do the build.
4. **PR + review loop before merge.** Open a PR, then send out review agents (**fewer than 5**) to critique it
   adversarially / as code review — each posts its findings as comments on the PR (e.g. `/code-review --comment`,
   or spawn reviewer subagents). The implementer addresses every comment, then repeat review → fix until we're
   confident it's safe. Only then merge to `main`.

## Session rules (added 2026-07-03, from the thread/repo review)
- **Infra ops out of the main thread.** Model downloads, llama-server hosting, health polling, benchmark
  sweeps: background agent or script with a check-in — never inline in the Opus main context.
- **Branch-scan before building.** Before planning any feature: `git fetch`, scan all origin branches for
  overlapping work, claim the work in HANDOFF's top block (or a GitHub issue) before writing code.
- **Posted review = merge gate.** No merge until the PR has a posted adversarial-review comment; the
  implementer verifies with `gh pr view --comments` before requesting merge. Post review comments by
  default — no need to ask.
- **Parallel work = clean session from HANDOFF**, never a session fork (forks inherit a nearly-full context).
- **Session end:** append HANDOFF top block (date = actual clock, check it), state done vs pending explicitly.
- **Subagent negative claims need receipts.** "No X available" / "frozen" must list the exact paths/params
  checked; the orchestrator verifies before acting on it. Dispatches name the model ("dispatching Sonnet...").


