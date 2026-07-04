# Skill library — ai-pokemon-red

Seven skills so that a junior engineer or a Sonnet/Opus-class session can carry this project to the
North Star without its original lead. Each is self-contained; every command/path/number in them was
verified against the repo at authoring time (2026-07-04) and the set was adversarially reviewed
(accuracy + usability-as-a-weaker-model) plus scenario-audited.

Read order for a cold session: **session-start → safety-invariants**, then the one matching your task.

| Skill | Invoke when |
|---|---|
| [session-start](session-start/SKILL.md) | Any new session / after compaction: orient, state the task, pick next work |
| [safety-invariants](safety-invariants/SKILL.md) | Before any destructive, external, paid, or merge action; when unsure what's allowed |
| [dev-workflow](dev-workflow/SKILL.md) | Before any non-trivial code change: plan → branch → Sonnet implementer → PR → review → David merges |
| [paid-run-harness](paid-run-harness/SKILL.md) | Before ANY live `claude -p` brain run (account-B law, seam check, one-attempt rule) |
| [gate-methodology](gate-methodology/SKILL.md) | Designing, pre-registering, scoring, or banking any capability gate |
| [new-world-port](new-world-port/SKILL.md) | Adding a game/console world; first constancy audit |
| [session-wrap-up](session-wrap-up/SKILL.md) | Ending a session: HANDOFF, memory, summary, commit/push |

Maintenance: when a law changes (David's word or a banked verdict), update the skill in the same PR
that changes the underlying doc — a stale skill is worse than none. Safety rules are deliberately
restated across several skills; if you change one, grep the library for its copies.
