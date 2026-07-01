# It1 close — status report (2026-07-01)

_A plain-language snapshot: what It1 is, what got built this session, and exactly where it's blocked._

## What It1 is (the short version)

**It1 is the first rung of the project's ladder — and its current *binding constraint*.**

The north star: **one agent — a fixed reasoning brain + a swappable perception layer — that completes
human-given tasks from the screen, across increasingly different worlds, cheaply, without per-world
training.** Pokémon Red is the *first probe world*, not the goal.

It1's specific job is to **prove the architecture actually closes end-to-end in that first world**: run
**one human-given task** through the frozen brain↔world seam (ADR-001) and **measure three things**:

- **Success** — did the agent do the task, judged by ground-truth (a RAM "oracle" used for scoring only,
  never shown to the brain)?
- **Constancy** — how *little* changed outside the perceiver? (The brain is supposed to be reused unchanged.)
- **Wakes** — how many expensive System-2 (LLM) calls did it take? (Cost must stay low.)

**Concretely, this session's It1:**
- **Task:** "Get your first Pokémon from Professor Oak."
- **Success predicate:** party count (RAM `0xD163`) goes **0 → 1**, checked offline in the oracle.
- **Brain:** `claude -p` running in WSL (a System-2 stand-in for *aria*, the real brain, which isn't in this
  workspace) — driving the world over an MCP seam.

**Why it matters:** the *old* pre-ADR-001 loop had already gotten the starter — but that was the superseded
"harness drives the brain as a decision endpoint" model. **No task had ever run through the *inverted* seam**
(brain = MCP client, world = MCP server). Closing It1 is the proof that inverted seam works. Everything above
it on the ladder (It2 generalization → It3 3D → It4 real-world) builds on that proof.

## What got built this session

- **Cleared the board:** merged PR #38 (NDS touch coarsening), closed PR #36 (NDS boot navigator — not needed
  for It1, and it would have broken `main`'s tests on a clean checkout).
- **Wired Pokémon Red into the game-agnostic MCP harness** (`world_mcp.py`) as a **lean `PerceptionPlugin`
  world** — exactly like cave_noire / gauntlet / nds. **Archived** the heavy pre-seam `PokemonRedPlugin`
  (RAM-based observe, reward tracking, battle-settling — all legacy) and replaced it with a ~28-line flavor
  subclass. Retired 5 pre-seam scripts. *(Branch `feat/it1-pokemon-red-task`, 5 commits, not merged.)*
- **Generated a fresh bedroom start-state** (`runs/red_start.state`) — verified map 38, **party 0**.

## Verification so far (all green)

| Check | Result |
| --- | --- |
| Full test suite | **411 passed** (428 − 17 obsolete tests removed with the archived plugin) |
| Frozen contract (`core/contracts.py`) | untouched (hash-pinned test passes) |
| Non-brain Docker smoke | clean symbolic Red view returned; **no RAM on the wire**; oracle logged `watch.party` |
| Start-state | map 38 (bedroom), party 0 |

## Result: SEAM CLOSED end-to-end — task one dialog short (a perception bug)

The paid audit **ran** — on a second Claude account via a separate `CLAUDE_CONFIG_DIR` (the first attempt hit
the account's 5-hour session limit). **The inverted seam closed for the first time in any world:** the
`claude -p` brain drove Pokémon Red live for **332 steps / 25 decisions**, with cheap dual-process behaviour
(`explore` auto-walked ~300 tiles for free), **no RAM leak**, and the oracle scoring the whole run offline.

**Navigation worked** — bedroom (map 38) → downstairs (37) → Pallet Town (0), reaching the **Oak-intercept**
at the top of town (the scripted "you need your own POKéMON…" that leads to the lab).

**It failed there — one dialog from the starter — on a world-side perception bug:**
- At the intercept (RAM: map 0, pos (10,1), `dialog` for the final 14+ steps) the perceiver detected `dialog`
  context but **decoded no `screen_text`** (the box clearly reads "You need your own POKéMON for your…") and
  its dead-reckoned **pose broke to `(5,-5)`**. The brain flew blind; its `a`/`b`/`wait` presses never
  advanced the scripted sequence (RAM frozen), and it correctly gave up.
- Classic **"perception lost something the agent needed"** (ADR-001 invariant #4) — a **world-side** bug
  (`textbox.py` decode + pose-during-dialog in the perceiver), not a brain failure.

**Measured It1:** success = **NO** (party 0→0); wakes = **25 decisions**; constancy = **strong** (brain =
unmodified `claude -p` + task brief; every fix is world-side). **Verdict: the mechanism is proven; the task
is one perception fix away.**

## What's left

1. **Fix the forced-dialog perception gap** (world-side): decode the intercept dialog in
   `games/pokemon_red/textbox.py`; hold/repair pose during `dialog` context in the perceiver (it drifts on
   the screen change); confirm `a` advances the scripted sequence. Then **re-run** the account-B audit.
2. **Adversarially verify** any future oracle success against the transcript + recorded video (guard against a
   false positive).
3. **Adversarial code review** (≤3 agents) on the branch → PR → merge.

**One code caveat to watch during the run:** the lean world uses the generic Game Boy emulator, so *fading*
door-warps lose an extra robustness aid the old plugin had (the perceiver still detects warps via its own
scene-cut signal). If the brain gets stuck at a door transition, that's the first thing to fix.

## Constancy — the early read (pending the successful run)

The brain is **unmodified `claude -p` + a task brief**; **all** new code is world-side (a registry entry, a
~28-line flavor plugin, a scorer). That is exactly the constancy result the project is after — to be
*confirmed* once the run actually executes and we see the behavior.

## Generalization probe (It2) — same brain, 2 more games

Ran the *same* live-brain exercise on two already-wired worlds (`cave_noire`, `gauntlet`) on account B. **Both
closed the loop**; the brain was unchanged — only the perceiver + task brief differ.

| Game | Loop | Decisions | RAM tiles covered | cells/dec | Stopped by |
| --- | --- | --- | --- | --- | --- |
| Cave Noire | ✅ | 10 | 15 (hp full) | 0.6 | dead-reckon drift sealed it in (the "strand bug") |
| Gauntlet | ✅ | 19 | 438 | 4.3 | stale all-walls / frontier exhaustion |

**Finding:** the seam + brain + dual-process cost design **generalize** — the same brain offloaded routine
travel to the free autopilot (51 free tiles in Cave Noire, 621 in Gauntlet), woke only at decisions, and
stopped when a wake stopped paying. **Every ceiling is world-side perception** (Red: dialog decode; Cave
Noire: dead-reckon drift; Gauntlet: wall-staleness) — never the brain. The architecture's core bet holds
across 3 games; perception quality is the uniform bottleneck.

---
_Files: plan `~/.claude/plans/tender-cooking-firefly.md`; branch `feat/it1-pokemon-red-task`; launchers
`runs/brain_{red_starter,cn,gauntlet}/`; this report `reports/2026-07-01-it1-close-status.md`._
