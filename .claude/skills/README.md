# Skill library — ai-pokemon-red

Fifteen skills so that a junior engineer or a Sonnet/Opus-class session can carry this project to the
North Star without its original lead. Each is self-contained; every command/path/number in them was
verified against the repo at authoring time (2026-07-04) and the set was adversarially reviewed
(accuracy + usability-as-a-weaker-model) plus scenario-audited.

Read order for a cold session: **session-start → safety-invariants**, then the one matching your task.

## Process — how work happens here

| Skill | Invoke when |
|---|---|
| [session-start](session-start/SKILL.md) | Any new session / after compaction: orient, state the task, pick next work |
| [safety-invariants](safety-invariants/SKILL.md) | Before any destructive, external, paid, or merge action; when unsure what's allowed |
| [dev-workflow](dev-workflow/SKILL.md) | Before any non-trivial code change: plan → branch → Sonnet implementer → PR → review → David merges |
| [session-wrap-up](session-wrap-up/SKILL.md) | Ending a session: HANDOFF, memory, summary, commit/push |

## Concepts — the load-bearing mental models

| Skill | Invoke when |
|---|---|
| [architecture-and-seam](architecture-and-seam/SKILL.md) | Reasoning about constancy failures, "fixing a world", or tempted to edit the brain |
| [cheapness-skill-compilation](cheapness-skill-compilation/SKILL.md) | Advancing the cost axis; designing/porting skill tools; the System-2→System-1 promotion law |
| [world-lanes-frontier](world-lanes-frontier/SKILL.md) | Pointed at any non-GB lane (ARC, 3D, NDS, MiniWoB, glyph); a NEW environment class arrives; picking the next Generality rung |

## Measurement — free before paid

| Skill | Invoke when |
|---|---|
| [eval-probes-and-datasets](eval-probes-and-datasets/SKILL.md) | Designing any experiment/probe, adding a scorer, labeling data, touching a held-out game |
| [gate-methodology](gate-methodology/SKILL.md) | Designing, pre-registering, scoring, or banking any capability gate |
| [diagnose-a-run](diagnose-a-run/SKILL.md) | A paid run failed / looks wrong / INSUFFICIENT_DATA: triage offline before proposing any re-run |

## Building — perception and worlds

| Skill | Invoke when |
|---|---|
| [perception-primitives](perception-primitives/SKILL.md) | Perception breaks on any world; a perceiver needs a signal; BEFORE writing any new perception code |
| [new-world-port](new-world-port/SKILL.md) | Adding a game/console world; first constancy audit |

## Paid runs — spend without waste

| Skill | Invoke when |
|---|---|
| [paid-run-harness](paid-run-harness/SKILL.md) | Before ANY live `claude -p` brain run (account-B law, seam check, one-attempt rule) |
| [run-brief-authoring](run-brief-authoring/SKILL.md) | Before writing or editing any `runs/<tag>/CLAUDE.md` brief or kickoff `-p` prompt |
| [long-horizon-runs](long-horizon-runs/SKILL.md) | Before planning/launching/monitoring any paid run beyond ~100 turns |

Maintenance: when a law changes (David's word or a banked verdict), update the skill in the same PR
that changes the underlying doc — a stale skill is worse than none. Safety rules are deliberately
restated across several skills; if you change one, grep the library for its copies. A new world
class gets a lane section in world-lanes-frontier in the same PR that ports it.
