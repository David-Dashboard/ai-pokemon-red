---
name: dev-workflow
description: The mandatory change workflow for ai-pokemon-red — plan, feature branch, Sonnet implementer agent, PR, adversarial review, David merges. Invoke before making ANY non-trivial code change in this repo.
---

# dev-workflow — how every change lands in ai-pokemon-red

Repo: `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red`
Remote: `https://github.com/David-Dashboard/ai-pokemon-red.git` (origin)
This workflow is mandatory for every non-trivial change (repo `CLAUDE.md` "Implementation workflow"). Trivial one-liners may skip the review fan-out but still go branch → PR → merge gate.

## The loop (checklist)

1. **Plan first.** Design the change in plan mode and get the plan agreed (with David) BEFORE any code is written. No plan, no code.
2. **Branch-scan before building.** Before planning any feature:
   ```
   git fetch
   git branch -r          # scan ALL origin branches for overlapping work
   ```
   Then claim the work in `HANDOFF.md`'s top block (or a GitHub issue) before writing code. Parallel sessions collide otherwise.
3. **Feature branch off `main`.** Never work on `main` directly — not even "small" commits.
   ```
   git checkout main && git pull
   git checkout -b fix/<thing>     # or feat/<thing>
   ```
4. **Delegate implementation to a Sonnet subagent.** The orchestrator (main loop) does NOT write the code itself — it orchestrates and reviews. Give the subagent a tight, bounded spec plus an explicit OUT-OF-SCOPE list. Direct edits by the orchestrator: trivial/glue only.
   - Dispatch-prompt gotcha: Sonnet implementers sometimes re-delegate to a background sub-agent and stop after ~1 tool call. Put "Do the work YOURSELF in the foreground; do NOT spawn background agents" in the dispatch prompt. If it happens anyway, resume the agent (SendMessage) with that instruction.
5. **Announce agent count BEFORE any multi-agent batch.** Tell David the expected number of agents and what drives it (e.g. "spawning 3 reviewers, one per angle") and let him weigh in before launching. Applies to implementer batches AND reviewer fan-outs.
6. **One git worktree per implementer agent** when agents mutate files in parallel. Two agents editing the main tree discard each other's edits (observed 2026-07-03).
   ```
   git worktree add ../ai-pokemon-red-agent1 <branch1>
   git worktree add ../ai-pokemon-red-agent2 <branch2>
   ```
7. **Open a PR** (`gh pr create`) once the implementation is complete and the test suite passes locally:
   ```
   uv run --frozen pytest -q      # Windows: set UV_PROJECT_ENVIRONMENT=.venv-win, UV_NATIVE_TLS=true
   ```
8. **Adversarial review: FEWER THAN 5 reviewers per PR** (typically 2–3, sized to the change). Each reviewer takes a distinct angle — consumer-impact, cross-game / shared-`core` assumptions, edge cases, safety/irreversibility — and POSTS its findings as comments on the PR (e.g. `/code-review --comment`, or spawn reviewer subagents that run `gh pr comment`).
   - Reviewer model: Sonnet by default; Opus only for risky shared-`core` changes (David, 2026-07-03).
   - **Review is 100% MANUAL — nothing auto-reviews your PR.** A WSL2 cron/sweep (`~/pr-review/sweep.sh`) was built for this but is **DEAD** (verified 2026-07-04: disabled in crontab since 2026-06-25, last ran 2026-06-25, current PRs got no bot comment). Do NOT wait for it or tell David a PR "will be auto-reviewed" — YOU spawn the reviewers. Re-enable only with David's explicit say-so.
9. **Posted review = merge gate.** No merge until the PR has a posted adversarial-review comment. Verify before requesting merge:
   ```
   gh pr view <num> --comments
   ```
   Post review comments by default — no need to ask.
10. **Triage findings yourself — verify each claim against the code before trusting it.** Reviewers hallucinate (past runs invented a nonexistent file and a false TOCTOU). Fix real findings (send them back to the implementer subagent so it keeps its context); skip false positives with a stated reason. Add a regression test for any bug the suite missed. The implementer addresses EVERY comment; repeat review → fix until confident.
11. **CI green before merge.** Two locally-green PRs merged red on 2026-07-03 (a cross-PR interaction only CI caught). Wait for the PR check, not just the local suite.
12. **ONLY DAVID MERGES.** The loop conditions (posted review, findings triaged with each claim verified, suite green, CI green) are prerequisites for *requesting* a merge from David — not for performing one yourself. The 2026-07-02/03 merge grant is contradicted by `claude-p-run-authorization.md` ("the no-self-merge rule is unchanged"); until David resolves that, the stricter rule holds: do not self-merge, request the merge. Surface contentious/large changes for David's eyes early, not at merge time. (Mirrors safety-invariants §4.)

## Subagent negative claims need receipts

A subagent saying "no X available" / "frozen" / "file doesn't exist" must list the EXACT paths/params it checked. The orchestrator verifies the claim itself before acting on it. Dispatches name the model explicitly ("dispatching Sonnet...").

## Quick allowed/needs-approval reference

May do without per-action approval: push branches (via the PowerShell tool — `Bash(git push*)` is deny-listed by design so pushes route through PowerShell's prompt; PROTOCOL.md §7's "push" clause is superseded for feature branches by this standing grant), open PRs, run the full test suite, `docker build`, read-only probes.
Needs David: **merging**, anything destructive/world-affecting beyond this repo, running on account A or a raw `ANTHROPIC_API_KEY` (real per-token spend), re-enabling the review cron, large/contentious changes.

## Session hygiene (from repo CLAUDE.md)

- Infra ops (model downloads, server hosting, benchmark sweeps) run in a background agent/script, never inline in the main context.
- Parallel work = clean session from `HANDOFF.md`, never a session fork.
- Session end: append `HANDOFF.md` top block (actual clock date), state done vs pending explicitly.
- Long-run work follows `.claude/PROTOCOL.md` (ledger + gates + delegation); `LEDGER.md` is current-run task state.

## Sources

- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/CLAUDE.md` (Implementation workflow + Session rules)
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/.claude/PROTOCOL.md`
- Memory: `C:/Users/Succe/.claude/projects/E--AI-Personas-10-pokemon-and-chess-and-office/memory/review-process.md`
- Memory: `.../memory/workflow-plan-branch-pr.md`
- Memory: `.../memory/delegate-implementation-to-agents.md`
- Memory: `.../memory/agent-count-heads-up.md`
- Memory: `.../memory/wsl-pr-review-cron.md`
- Memory: `.../memory/cross-console-run-launchers.md` (worktree-per-agent)
