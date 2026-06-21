---
name: dual-process-architecture
description: David's intended cognitive architecture — aria=brain (System 2) that authors its own System 1 policies; ai-pokemon-red=world exposing coarse skill-tools; defer up on necessity/override
metadata:
  node_type: memory
  type: project
  originSessionId: 1b436777-2031-4eb5-bd24-c03e024f92da
---

**David's intended cognitive architecture (clarified 2026-06-20), the project's destination — guard
against drift:**

**GENERAL, not game-specific (David emphasized):** this is aria's universal agent architecture for
EVERY deployment, not a Pokémon-harness pattern. The "world" generalizes — companion = David's digital
life via gmail/gcal/web/filesystem tools; Pokémon = the emulator via skill-tools; reality =
sensors/actuators. ONE brain, swappable worlds-as-tool-APIs. NB: the **companion already embodies this**
(it acts on its world through real tools — `aria/src/aria/tools/*`); the **GAME deployment is the one
that drifted** to a text-in/text-out advisor. So the realignment = make the trainer act via tools the
way the companion already does. Same dual-process loop, same constitution-first spine, every world.

- **ai-aria = the BRAIN.** Owns cognition + within-run memory, and (future) **authors its own System 1
  policies**. ai-aria interacts with the world **through tool use** (it is the ACTOR, not a text
  advisor).
- **ai-pokemon-red = the WORLD.** Exposes **coarse skill-tools** (e.g. observe / move / go_to /
  advance_text / choose_move) — NOT per-button. Coarse granularity is the decision (keeps cheap-first
  while making aria the driver). The world is just an environment + tool API.
- **Control loop:** **System 1** (fast, cheap, aria-authored policy) DRIVES the world via skill-tools,
  autonomously. It **defers UP to System 2** (aria deliberate reasoning) only on **necessity** (novelty
  / low confidence / policy exhausted) or **override** (a surprise/event/goal-change preempts the running
  policy). Cost scales with NOVELTY, not steps — the cure for the cost crisis ([[cost-blocker]]).
- **aria authors System 1:** System 2 watches itself succeed, distills a fast skill, hands it to System 1.
  This is the System-2→System-1 compilation ladder already in `reports/INSIGHTS.md`.

**Drift being corrected:** today System 1 (the autopilot) is HUMAN-authored and lives in ai-pokemon-red
(`core/brains.py`); aria is a text-in/text-out advisor with NO world tools (the harness parses its
"MOVE: up" text). Target flips both: aria holds the policies + memory and ACTS via world tools.

**Seeds already present:** "aria authors lessons" (text, harness-stored) → matures into "aria authors
POLICIES" (executable, brain-owned); the surprise/disconfirm/outcome channels → the OVERRIDE mechanism;
the planned "learned blind-execute battle policy" = the first concrete rung.

**CRITICAL open decision vs the [[learning-boundary]] HARD LAW (agent starts blank every run):**
within-run policy compilation (compile during a run, discard at run end) is CONSISTENT with the law;
**across-run** persistent policy improvement would be a DELIBERATE REVISION of the law (ends "blank every
run"). Near-term = within-run; across-run is a later, explicit choice — NOT to be done by drift.

**Foundations/rungs toward this (all compatible, already decided):** constitution-first spine
[[unified-prompt-architecture]] + aria owns within-run memory (decision 2 = β) + coarse skill-tool world
API. See also [[project-north-star]].
