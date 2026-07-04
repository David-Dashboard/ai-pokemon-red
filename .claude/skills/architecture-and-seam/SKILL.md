---
name: architecture-and-seam
description: The conceptual map of the project — the fixed brain, the swappable perceiver, and the world, and where the seam between them is. Read before reasoning about a CONSTANCY failure, before "fixing a world," or whenever tempted to edit the brain.
---

# Architecture & the seam — the load-bearing mental model

The whole project is ONE claim: **a fixed reasoning brain + a swappable perception layer that plays
any world from the screen alone.** If you can't say which of the three parts a file belongs to, you
can't safely change it. This skill is the map. (Contract of record: `ARCHITECTURE.md` ADR-001,
Accepted 2026-06-20, revised by ADR-002 2026-07-03 — read it before any structural change.)

## The three parts (and the seam between them)

```
   BRAIN  (System 2)            SEAM              WORLD  (System 1 + perception)
   the reasoner        ==== the MCP wire ====     perceiver + emulator + game
   reused UNCHANGED     SymbolicState  → agent     re-fitted per world
   across all worlds    an intent/action → world
```

1. **The brain = the reasoner (System 2).** Deliberate reasoning, planning, ALL memory,
   identity/constitution. It lives in a **separate repo, `ai-aria`** (a fully decoupled service) — it
   is NOT in this tree (`ls` the repo root: there is no `ai-aria/` dir here). In the *current live
   path* the brain is simply an external **Claude Code instance driven by `claude -p`** that BEs the
   System-2 agent over MCP (`world_mcp.py` docstring, top; README "LLM agent (a Claude plays over
   MCP)"). The older in-repo driver path (`LLMButtonBrain` at `core/brains.py:683`, driven by the
   `/v1/chat/completions` `complete_fn` helper `_openai_complete` at `core/brains.py:622`, talking to
   aria) is the same seam from the code side, now superseded by the MCP harness. **Either way the brain is world-agnostic and reused unchanged.**
2. **The perceiver = the per-world perception layer.** Pixels → a role-named `SymbolicState`
   (`core/perception.py:23`: pose / spatial_memory / affordances / context / screen_text /
   last_action / confidence). This is the ONLY thing that legitimately changes per world. Concretely:
   a per-world `Perceiver` (`core/perception.py:60` Protocol) — either a game package
   (`games/<game>/perceiver.py`, e.g. `games/pokemon_red/perceiver.py:OverworldPerceiver`) or the
   shared `core/grid_perceiver.py:FollowCameraPerceiver` for lean worlds — plus a per-world entry in
   the `GAMES` registry (`world_mcp.py:114`).
3. **The world = the game + emulator + System-1, exposed over MCP as screen-only tools.**
   `world_mcp.py` is the MCP (stdio) server; the emulator is one of `core/gb_emulator.py`,
   `core/gba_emulator.py`, `core/nds_emulator.py` (dispatched by ROM extension); the free System-1
   autopilot (`core/brains.py:ExploreBrain`) drives routine movement and hands back at decisions.

**The seam is the MCP wire.** `core/contracts.py` holds the frozen wire types (`ToolCall`,
`ToolResult`, `ToolSpec`) — "a ToolSpec already IS an MCP tool, a ToolResult already IS a JSON
result" (`world_mcp.py` docstring). World→agent = the `SymbolicState`; agent→world = an intent (a
button / sequence / `goto`, coarse skill-calls as it matures) (`ARCHITECTURE.md` "The seam").

## Screen-only / no privileged channel — what it means concretely

- **IN to the brain:** the pixels-derived `SymbolicState` (+ an OPTIONAL debug PNG only behind
  `--with-screenshot`, never the primary input — a raw screenshot would reopen the confabulation
  failure, `INSIGHTS.md` §4). Human-grade controls only: buttons, or mouse/keyboard.
- **OUT of the brain:** actions (`press_button`, `press_sequence`, `goto`, `act`, …).
- **OFF the wire, always:** RAM / the oracle / the score. `watch` RAM values go to `world/oracle.jsonl`
  on disk for **offline scoring only** and are NEVER returned by any tool (`world_mcp.py` docstring
  "No-leak"; `ARCHITECTURE.md` invariant #3; safety-invariants law 5). No RAM, no DOM, no
  accessibility tree, no API into the brain (`HANDOFF.md` §1 claim #1).
- Leaking oracle truth onto the agent wire **invalidates the entire screen-only claim** — treat it as
  a correctness bug, not a shortcut.

## Which directory is which (grep-verified — do not guess)

| Part | Where | Constancy rule |
|---|---|---|
| **Brain (reasoner)** | external `ai-aria` repo / the `claude -p` agent | never edited per world |
| **Brain-side framework** (game-agnostic) | `core/contracts.py`, `core/gateway.py`, `core/runner.py`, the LLM/scripted brains in `core/brains.py`, `world_mcp.py`'s tool-dispatch | stays constant; edits here are *framework* changes, never "make world X work" |
| **Perceiver** (per-world) | `games/<game>/perceiver.py` (cave_noire, gauntlet, pokemon_red) **or** `core/grid_perceiver.py` / `core/nds_perceiver.py`; the `GAMES` entry in `world_mcp.py:114` | THE thing you re-fit for a new world |
| **Shared perception primitives** | `core/` L1/L2 signal code — `core/egomotion.py`, `core/localize*.py`, `core/text_regions.py`, `core/glyph_cache.py`, `core/screen_role.py`, `core/tilemap.py`, `core/blob.py` … | shared *perceiver-side* toolkit; lift a primitive here the 2nd time a world needs it (`INSIGHTS.md` §2) |
| **World** | `world_mcp.py`, `core/gb_emulator.py` / `core/gba_emulator.py` / `core/nds_emulator.py`, the game plugin | per-world; add a console = a new `Emulator` impl |
| **Oracle** (scoring only) | `watch` RAM → `world/oracle.jsonl` | never crosses the seam |

Caveat that trips people up: **`core/` is NOT all "the brain."** `core/` holds *both* the fixed
brain-side framework (contracts, gateway, runner, the brains) *and* the shared perceiver-side
primitives. The *reasoning brain itself* is `ai-aria` / the external agent — not a file in this repo.
So "don't edit the brain" ≠ "don't touch `core/`": you may add/upgrade a **perception primitive** in
`core/`; you may not edit the **reasoner** or bend the **frozen seam** (`core/contracts.py`, the tool
schema) to make one game pass.

## The 4 North Star claims → the three parts (`HANDOFF.md` §1)

- **Capability** — human-grade task success *from the screen*. Lives at the **seam + perceiver**: the
  brain only ever gets `SymbolicState`; capability is bounded by how faithful the perceiver is.
- **Constancy** — the brain doesn't change; a new world swaps only the **perceiver (+ per-world
  config/constitution)**. *This is the core claim and the one most likely to be false.* Success =
  how little changes outside the perceiver.
- **Generality** — the same brain across increasingly-different worlds (2D→3D→sim→robot; and the
  computer-use track). Every new world is a new **perceiver + world**, never a new brain. Constancy
  now spans GB/GBA/NDS/browser(MiniWoB)/ARC-grid with **zero brain edits** (`HANDOFF.md`).
- **Cheap** — free System 1 (`ExploreBrain`) does routine work in the **world**; the costly System 2
  brain wakes only at decisions. Measured as cost/task and wakes/task.

## The constancy tripwire (STOP condition)

> A new world swaps **only the perceiver (+ its per-world config)**. If you find yourself editing the
> **brain** — the `ai-aria` reasoner, the brain's prompt/tools, or the **frozen seam**
> (`core/contracts.py`, the MCP tool schema) — **to make a world work: STOP.** That edit *falsifies
> the core Constancy claim* for every world at once.

When a run exposes a problem, **classify the fix before writing it** (`ARCHITECTURE.md` invariant #5):
- world-specific (perception can't see something, System-1 misbehaves) → fix **world-side**
  (perceiver / `world_mcp.py` / emulator). This is the common case: *every prior game's ceiling was
  world-side perception, never the brain* (`HANDOFF.md`; safety-invariants law 7).
- a genuinely **general agent** improvement → belongs in `ai-aria`, and is a deliberate, separate
  change — not a quiet edit to pass game X.

Decision tree for "the brain did the wrong thing in world X":
1. Did the brain get a **faithful `SymbolicState`**? If perception dropped/fabricated what it needed →
   perceiver bug (world-side). *(Invariant #4: "perception lost something the agent needed" is a
   first-class failure mode.)*
2. Was it a **decision the brain should own** but System-1 took it wrongly (confidently wrong)? →
   System-1 gate is over-reaching; make it defer up (world-side, `core/brains.py` gate / plugin).
3. Only if the brain reasoned wrongly **from faithful clean state** is it a brain concern — and even
   then the fix goes to `ai-aria` as a general improvement, deliberately, **never** as a per-world
   patch here. "The reasoning was never broken; the *input* was" (`INSIGHTS.md` §0, §4) is the prior.

## Related skills
- **new-world-port** — the mechanical how-to for adding a world (registry entry, launcher, emulator
  Protocol, first constancy audit). This skill is the *why*; that one is the *how*.
- **safety-invariants** — law 7 "No brain edits (constancy)" and law 5 "oracle off the wire" are the
  enforcement side of this map.

## Sources
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/ARCHITECTURE.md` (ADR-001: the dual-process seam, the seam contract, invariants #3/#4/#5)
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/HANDOFF.md` §1 (the north star + the 4 testable claims; "zero brain edits"; constancy across 5 world classes)
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/reports/INSIGHTS.md` §0–§4 (the perception seam IS the generalization mechanism; primitives-not-bespoke-code; confabulation = bad input not bad reasoning)
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/reports/north-eye-perception-constitution.md` (L0–L3 stack; the perceiver-side primitive contract; the Realizer Ladder)
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/README.md` ("Repo map"; MCP is the live LLM path; `core/` game-agnostic, `games/<game>/` per-world, `core/contracts.py` frozen wire types)
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/world_mcp.py` (docstring: WORLD=MCP server, AGENT=Claude; no-leak; `GAMES` registry at line 114; tool surface `observe`/`act`/`explore`/`goto`/`press_*`/`read_region`/`whats_changed`/`remember`)
- `E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red/core/` (verified layout: `perception.py` SymbolicState/Perceiver, `grid_perceiver.py` FollowCameraPerceiver, `brains.py` ExploreBrain/LLMButtonBrain, `contracts.py`, `gateway.py`)
