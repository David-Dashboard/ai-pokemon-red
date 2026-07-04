# Continuous-time `stop_when`: bridging bounded skills from discrete worlds to NDS/3D

**Status:** design doc (no code, no paid run). Resolves HANDOFF NEXT #2 — "the `stop_when` bridge from
discrete-step to continuous-time worlds." Decisions here are pinned when the first continuous-time port
is *built* (its own PR pins the exact enum + thresholds from that world's wire); this doc fixes the shape.

## §0 The problem — one assumption, baked in, that continuous-time breaks

The rung-1 skill mechanism (`define_skill`/`run_skill` with a bounded `repeat_until` loop and a closed
`stop_when` enum) assumes **the world is quiescent between actions**: one action advances the world one
step, nothing changes until the next action. This is true for every world we have shipped — ARC-AGI-3
(one `act` = one grid step), Game Boy / Kirby (one `press_button` = one framed update). It is written
into the executor: `world_mcp.py:1293` — "one LLM decision buys up to `_KIRBY_SKILL_MAX_WORLD_STEPS`
presses" — and every `stop_when` predicate evaluates against the observation taken *after* a discrete
step, whose only cause of change is the player's action.

NDS/3D worlds violate this. Measured on the banked Mario Kart DS race savestate
(`runs/nds3d_probe/mkds_race_start.state`, HANDOFF 2026-07-03): the screen changes **12.2% mean per
frame with ZERO player input** during the countdown, and 33% while accelerating. The world advances
every frame regardless of whether the brain acts. "One press = one world step" is simply false; the
world moves *during* an action, *between* actions, and *while the brain is thinking*. Every predicate
premised on "nothing changed ⇒ my action caused nothing" and "something changed ⇒ my action caused it"
is now unsound.

This doc does NOT add a perception layer for 3D (that is a later, failure-triggered climb per
`reports/nds-emulation-plan.md` §Δ3). It resolves only the **control/skill-budget** bridge: what
`stop_when` predicates and what budget model let a bounded skill remain useful when the world never stops.

## §1 Inherited UNCHANGED (do not re-litigate)

- **The mechanism shape**: `define_skill(name, steps, {repeat_until:{steps, stop_when, max_iters}})` →
  `run_skill`. Proven at 2.94× over primitive-spam (`reports/2026-07-03-skill-rung1-ab-verdict.md`).
- **Closed, per-world predicate enum** — no learned/invented predicates; each world port pins its own
  set in its build PR (ARC's enum ≠ Kirby's enum: `world_mcp.py:1885` vs `:943`). Continuous-time adds
  predicates to a *new* world's enum; it does not touch the GB/ARC enums.
- **No new channels on the wire** — predicates compute from the screen the brain already sees
  (`core/contracts.py` Observation). Oracle/RAM stays off the wire (screen-only claim).
- **Bounded and blank** — a hard per-call ceiling stays; skills live only within a run, never promoted
  without a held-out gate (the learning-boundary law).

## §2 The central move — split the decision budget from the world-time budget

Discrete worlds conflate two budgets because they coincide: `max_iters` loop iterations = actions
issued = world steps elapsed. Continuous time forces them apart:

- **Decision budget** — how many inner actions the brain's skill issues. Stays `max_iters ≤ 8`
  (`_SKILL_MAX_ITERS`, `world_mcp.py:492`). This bounds *reasoning cost*, unchanged.
- **World-time budget** — how many emulator **frames** elapse. In discrete worlds this equalled the
  action count; here it must be counted separately, because frames advance without actions.

**Decision of record:** a continuous-time port pins a **resolution `r`** = frames advanced per inner
action-tick (the ViZDoom `tics` idea, `reports/2026-07-04-vizdoom-3d-floor-design.md` §2.1 — an action
executes N frames, brain still sees one-decision-per-action). `run_skill` is then bounded by BOTH:
`max_iters` (decisions) AND a **frame ceiling `F`** (world-time). `_SKILL_MAX_WORLD_STEPS = 50`
(`world_mcp.py:495`) is reinterpreted for these worlds as a **frame** ceiling, not a press count.
Whichever bound trips first ends the call. This keeps reasoning-cost and wall-clock both bounded.

## §3 The continuous-time `stop_when` family (decision of record)

Add these to a continuous-time world's enum (screen-only, closed set). Signatures pinned; thresholds
pinned per world at build time from that world's wire:

1. **`elapsed_frames(n)`** — fires after `n` emulator frames elapse (the world-time counterpart to
   `steps_elapsed(n)`, which now counts *actions* not frames). The honest "run this for ~n frames" bound.
2. **`idle_settled(threshold, k)`** — fires when whole-frame pixel-change < `threshold` for `k`
   consecutive sampled frames. This is the load-bearing new primitive: "wait until the world stops
   moving" — countdown→GO, menu/scene transitions, load screens. It is the continuous-time dual of
   ARC's `grid_unchanged_for(k)` (`world_mcp.py` ARC enum), generalized from grid-equality to a
   pixel-change threshold because 3D frames are never bit-identical.
3. **`region_settled(x0,y0,x1,y1, threshold, k)`** / **`region_active(x0,y0,x1,y1, threshold)`** —
   foveated versions: settle/activity inside a box (e.g. the HUD lap counter), ignoring the moving
   background. Reuses the `region_changed` box syntax already parsed for Kirby (`world_mcp.py:960`).

`region_changed(box)` is NOT reused verbatim — under continuous time it fires on the first sampled
frame (the background is always changing), the exact degeneracy entity-gate v3.1 hit in *discrete* GB
against moving enemies (`reports/2026-07-04-entity-v3.1-verdict.md`: `region_changed` fired at press 1).
`region_active`/`region_settled` replace it with a **threshold + dwell (`k`)**, which is what makes them
robust to per-frame drift.

## §4 The idle threshold must be pinned per world, above its drift floor

`idle_settled`/`region_*` need a `threshold`. The world's idle-drift floor sets the minimum usable value
— MKDS idles at 12.2%/frame, so an `idle_settled(threshold=0.05, …)` would **never** settle there.

**Decision of record:** pin the threshold **per world at define/build time from an oracle-measured idle
baseline** (measure idle-drift on a banked savestate once, freeze it), NOT via an online estimator on the
wire. This matches the "closed per-world enum, pinned in the build PR" discipline and keeps no learned
state on the agent wire. Rule: **`threshold` must sit above the world's measured idle floor** (MKDS:
> 0.122). A window-relative "settle = change dropped below X% of the recent max" variant is noted as a
fallback if a fixed threshold proves brittle across a game's screens, but is NOT adopted now (it adds an
online baseline estimator — defer until a fixed threshold is shown to fail).

## §5 Observation sampling under a loop

Discrete `_run_skill` re-observes once after each action. Under a resolution `r`, one action spans `r`
frames, so a predicate like `idle_settled(…, k)` needs frame-level samples *within* an action, not only
at action boundaries. **Decision of record:** the executor samples the screen every `s` frames (a pinned
per-world **sample stride**, `s ≤ r`) for predicate evaluation; the brain still receives one Observation
per action (cost unchanged). This is a world-side implementation detail behind the seam — no new wire
type. `k` in `idle_settled` counts *sampled* frames (spacing `s`), so its wall-time meaning is `k·s`
frames; the build PR documents `s` so `k` is unambiguous (the same disambiguation `max_iters`-vs-frames
needs).

## §6 Worked sketch — a first MKDS skill, honestly decomposed

Goal off the start line: "wait for GO, then accelerate straight." The naive single skill is degenerate —
a skill whose only body is "wait" does nothing (see §7). Honest decomposition:
- The brain *observes* the countdown itself (one decision), then defines `launch = repeat_until(
  steps=[{button:A}], stop_when=elapsed_frames(90), max_iters=…)` to hold accelerate for ~1.5 s across
  the GO, and `steer_to_center = repeat_until(steps=[{button:left|right}],
  stop_when=region_settled(<minimap-heading box>, threshold, k))`.
- `idle_settled` earns its keep on *transitions the brain must not act through* — a lap-complete banner,
  a rubber-band catch-up freeze, a results screen — where the correct behavior is "hold until the world
  resumes," and the alternative (spamming actions blind) wastes budget or misfires.

## §7 Degenerate guards (carried from rung-1, extended)

- **The no-op wait.** `idle_settled` invites a skill that issues no real action and just waits out
  frames — that is not compilation, it is a `wait()` tool call. Guard: inherit the rung-1 **qualifying
  call** rule (`executed_step_count ≥ 3` real actions before the stop fires; `score_skill_rung1.py`
  degenerate-strategy guard, and the entity-gate skill guard) and require, for a continuous-time skill
  to *count as evidence*, that its inner `steps` issue buttons — a body of only waits is rejected at
  define time.
- **Threshold gaming.** A `threshold` set at/below the idle floor makes `idle_settled` fire never (hangs
  to the frame ceiling) or always (fires frame 1). Guard: build-PR asserts `threshold >` measured idle
  floor and `<` the world's action-driven change rate (MKDS: 0.122 < threshold < ~0.33).
- **Frame-ceiling overflow = clean abort.** If no `stop_when` fires within `F`, the call ends and logs
  the reason (exactly as discrete `max_iters` exhaustion does today, `world_mcp.py:1108`), never a silent
  hang.

## §8 Reuse vs rethink (honest bounds)

| Rung-1 element | Continuous time |
|---|---|
| `define_skill`/`run_skill`, `repeat_until`, `max_iters ≤ 8` | **Reuse unchanged** (decision budget) |
| closed per-world enum, no wire channels, blank-agent | **Reuse unchanged** |
| `steps_elapsed(n)` as a *world-step* count | **Rethink** → `elapsed_frames(n)` (world-time) + `steps_elapsed` re-scoped to *actions* |
| `region_changed(box)` | **Replace** → `region_active`/`region_settled` (threshold + dwell) |
| `grid_unchanged_for(k)` (bit-equality) | **Generalize** → `idle_settled(threshold,k)` (pixel-change threshold) |
| one budget (`_SKILL_MAX_WORLD_STEPS = 50` presses) | **Split** → decision budget (iters) + frame ceiling `F` |
| observe once per action | **Add** world-side sample stride `s` for predicate eval (no wire change) |

**Riskiest claim (the thing a gate must test):** a *screen-only* `{idle_settled, elapsed_frames,
region_settled}` trio plus the decision/frame budget split is enough to make a bounded skill genuinely
useful in a continuous-time world — with NO new privileged channel and NO 3D perception layer. If a first
MKDS build cannot clear a pinned batching-benefit bar (à la rung-1's 1.3×) using only these, the deficit
localizes to *perception* (the 3D primitives), not to the skill/budget model — which is the whole point
of resolving this bridge cheaply first.

## §9 What this unblocks / next step

The **build PR** for the first continuous-time port (MKDS, off the banked race savestate) pins: the
world's idle floor (measured), the three thresholds, `r`, `s`, `F`, and the exact enum strings — then
runs the free seam check and a pre-registered A/B (skills vs primitives) exactly as rung-1 did. This doc
is the shared shape that PR implements; it does not itself authorize any paid run.

## Sources
- `world_mcp.py` — skill executor + budget constants (`:492`, `:495`, `:569`, `:571`), stop_when parsers
  (`:943` Kirby, `:1885` ARC), discrete decision assumption (`:1293`), clean-abort (`:1108`).
- `runs/nds3d_probe/FINDINGS.md` — MKDS race idle 12.2%/frame, perception breaks; `mkds_race_start.state`.
- `reports/2026-07-03-skill-compilation-design.md` — rung-1 mechanism + `repeat_until` formalism.
- `reports/2026-07-03-skill-rung1-ab-verdict.md` — the 2.94× batching result + qualifying-call guard.
- `reports/2026-07-04-vizdoom-3d-floor-design.md` — `tics` (frames-per-action) precedent; 3D perception is a later climb.
- `reports/2026-07-04-entity-v3.1-verdict.md` — `region_changed` degeneracy against a moving target (the discrete preview of this problem).
- `reports/nds-emulation-plan.md` — dual-screen/touch deltas; 3D perception failure-triggered (Δ3).
- `core/contracts.py` — Observation/ToolResult wire types (no new type introduced).
