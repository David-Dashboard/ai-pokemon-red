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
(`runs/nds3d_probe/mkds_race_start.state`, `FINDINGS.md:329`): the screen changes **~12% mean per frame
during the count-in with zero player input** (count-in animation — a clean *in-gameplay* idle number is
not yet measured, `FINDINGS.md:166`), and ~33% while accelerating. The world advances
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
action-tick (the ViZDoom frames-per-action precedent, `reports/2026-07-04-vizdoom-3d-floor-design.md`
§2.1+§3.2 — an action executes N frames, brain still sees one-decision-per-action). `run_skill` is then bounded by BOTH:
`max_iters` (decisions) AND a **frame ceiling `F`** (world-time). `_SKILL_MAX_WORLD_STEPS = 50`
(`world_mcp.py:495`) is reinterpreted for these worlds as a **frame** ceiling, not a press count.
Whichever bound trips first ends the call. This keeps reasoning-cost and wall-clock both bounded.

## §3 The continuous-time `stop_when` family (decision of record)

**First rung = the perception-free subset.** Two predicates, both computed from the whole frame with no
notion of *what* is on screen (screen-only, added to a new world's closed enum):

1. **`elapsed_frames(n)`** — fires after `n` emulator frames elapse (the world-time counterpart to
   `steps_elapsed(n)`, which now counts *actions* not frames). The honest "run this for ~n frames" bound.
2. **`idle_settled(threshold, k)`** — fires when whole-frame pixel-change < `threshold` for `k`
   consecutive sampled frames. The continuous-time dual of ARC's `grid_unchanged_for(k)`, generalized
   from bit-equality to a threshold (3D frames are never bit-identical). **It is a TRANSITION detector,
   not a steady-play tool:** it earns its keep where the correct behavior is "hold until the world
   resumes" — count-in→GO, a lap/results banner, a load or catch-up freeze. During active play the
   whole-frame change never drops near zero, so `idle_settled` simply will not fire there (by design).

**Deferred to the 3D-perception climb (NOT this rung):** foveated `region_settled(box,threshold,k)` /
`region_active(box,threshold)` (pixel-activity in a sub-box, reusing the `region_changed` box syntax at
`world_mcp.py:960`). The *predicate* is cheap pixel math, but its *usefulness* — "settle on the minimap
heading," "wait for the lap counter" — presupposes knowing which box is meaningful and reading it, which
the perceiver provably cannot do yet (rotating non-tile minimap + broken glyph cache,
`runs/nds3d_probe/FINDINGS.md`). Bundling them here would smuggle a perception dependency into a rung
meant to isolate the skill/budget question. They join the enum in the port that ships 3D perception.

Why `region_changed(box)` is replaced, not reused: under continuous time it fires on the first sampled
frame (the background always moves) — the same degeneracy entity-gate hit in *discrete* GB against a
moving enemy (`reports/2026-07-03-entity-v3-verdict.md:109`: "`region_changed` fired on the first (or
second) press almost every time"; the fuller v3.1 write-up is on `main` via PR #96,
`reports/2026-07-04-entity-v3.1-verdict.md`). Threshold + dwell (`k`) is the fix — carried by
`idle_settled` in this rung and by the deferred `region_*` later.

## §4 The idle threshold — pinned per world, but only after a real in-gameplay measurement

`idle_settled` needs a `threshold`, and the world's idle-drift floor sets its minimum usable value.
**We do not yet have that floor for any 3D world.** The only MKDS number in hand — ~12% mean/frame — is
the count-in pass, contaminated by the count-in animation (`FINDINGS.md:329-331`); FINDINGS' own headline
caveat is that no true *in-gameplay* idle was ever measured (`:166`). So this doc pins a PROCEDURE, not
a number.

**Decision of record:** (i) a build-PR prerequisite is an **offline in-gameplay idle measurement** —
pixel-change over idle frames during actual play on the banked savestate (a screen measurement frozen to
a constant; NOT the RAM oracle; nothing reaches the agent wire). (ii) the `threshold` is pinned from it,
above the measured steady-idle ceiling and below the action-driven change rate. (iii) **if those two
overlap** — a non-stationary idle floor, which the data already hints at (Spirit Tracks idles ~11.9% in
one screen, `FINDINGS.md:74`) — a fixed threshold cannot separate settle from play, and the
**window-relative** variant (settle = change dropped below X% of the recent rolling max) becomes
REQUIRED, not optional. Its cost is small and does not touch the invariants: the rolling max is a
world-side statistic behind the seam, not a new wire channel and not learned cross-run. So "defer
self-calibration" is a *measurement* call, not an invariant one.

## §5 Observation sampling under a loop

Discrete `_run_skill` re-observes once after each action. Under a resolution `r`, one action spans `r`
frames, so a predicate like `idle_settled(…, k)` needs frame-level samples *within* an action, not only
at action boundaries. **Decision of record:** the executor samples the screen every `s` frames (a pinned
per-world **sample stride**, `s ≤ r`) for predicate evaluation; the brain still receives one Observation
per action (cost unchanged). This is a world-side implementation detail behind the seam — no new wire
type. `k` in `idle_settled` counts *sampled* frames (spacing `s`), so its wall-time meaning is `k·s`
frames; the build PR documents `s` so `k` is unambiguous (the same disambiguation `max_iters`-vs-frames
needs).

**Budget invariant (assert at define time):** `s ≤ r` and `F ≤ max_iters · r`, and every predicate must
be satisfiable within budget — `elapsed_frames(n)` needs `n ≤ F`, `idle_settled(…,k)` needs `k·s ≤ F`.
Otherwise the loop can never fire its stop and always burns to the ceiling. This is the continuous-time
analogue of the "box that can never fire" checks the code already runs at define time
(`world_mcp.py:963-971`): reject an unsatisfiable skill at define, don't discover it at runtime.

## §6 Worked sketch — a first MKDS skill, honestly decomposed (perception-free)

Off the start line: "hold accelerate through GO, don't act through the count-in." Decomposition using
ONLY this rung's two predicates:
- The brain *observes* the count-in itself (one decision), then `launch = repeat_until(
  steps=[{button:A}], stop_when=elapsed_frames(~90), max_iters=…)` — hold accelerate for ~1.5 s across
  GO. `elapsed_frames` (not `idle_settled`) is correct here: the body is *acting*, so the frame keeps
  changing; a time bound is what "hold for a beat" means.
- `wait_out_banner = repeat_until(steps=[{button:none}], stop_when=idle_settled(threshold, k))` — for a
  lap/results/catch-up freeze the brain must not steer through, coast until the screen settles. Here the
  body is *not* driving frame-change, so `idle_settled` can actually fire.

The split of labor matters: `idle_settled` governs **hold-through-a-transition** loops (passive body);
`elapsed_frames` governs **do-something-for-a-beat** loops (active body). The two are NOT meant to be
paired in one loop — a button-issuing body keeps resetting a whole-frame `idle_settled` streak, so
`idle_settled` + an acting body is self-defeating (§7). Steering-by-minimap is deliberately absent: it
needs the deferred `region_*` and 3D perception.

## §7 Degenerate guards (requirements for the build PR — not yet in code)

None of these exists today; the build PR implements and pre-registers them.

- **The no-op "wait" skill.** `idle_settled` invites a skill whose body issues nothing and just burns
  frames — a `wait()` call, not compiled behavior. The rung-1 `executed_step_count ≥ 3` guard
  (`score_skill_rung1.py`) does NOT catch this cleanly here: a hold-through-transition loop's body is
  legitimately passive, and rung-1's own verdict flags that count-based guard as blind to the
  conditional half (`skill-rung1-ab-verdict.md:104-110`) — which is exactly `idle_settled`. So the port
  pins the **stricter conditional gate** instead: a skill counts as evidence only if **≥1 `run_skill`
  call has its `stop_when` fire before the frame ceiling / `max_iters`** (a real predicate branch, not a
  timeout), evaluated at **skill granularity**. A passive-body `idle_settled` loop that genuinely detects
  a transition qualifies; a body-and-stop pair that never depends on world state does not.
- **Threshold gaming.** A `threshold` at/below the idle floor makes `idle_settled` fire never (burns to
  the ceiling) or always (fires frame 1). Guard: the build PR asserts the pinned `threshold` sits
  strictly between the measured steady-idle ceiling and the action-driven rate (§4), or uses the
  window-relative form when they overlap. (No numeric window is pinned here — §4: it needs the
  in-gameplay measurement first.)
- **Frame-ceiling overflow = clean abort.** If no `stop_when` fires within `F`, the call ends and logs
  the reason (as discrete `max_iters` exhaustion does today — Kirby `world_mcp.py:1108`, ARC `:2023`),
  never a silent hang.

## §8 Reuse vs rethink (honest bounds)

| Rung-1 element | Continuous time |
|---|---|
| `define_skill`/`run_skill`, `repeat_until`, `max_iters ≤ 8` | **Reuse unchanged** (decision budget) |
| closed per-world enum, no wire channels, blank-agent | **Reuse unchanged** |
| `steps_elapsed(n)` as a *world-step* count | **Rethink** → `elapsed_frames(n)` (world-time) + `steps_elapsed` re-scoped to *actions* |
| `region_changed(box)` | **Replace** → threshold+dwell; foveated `region_*` **deferred** to the 3D-perception rung |
| `grid_unchanged_for(k)` (bit-equality) | **Generalize** → `idle_settled(threshold,k)` — **transition** detector only, not steady play |
| one budget (`_SKILL_MAX_WORLD_STEPS = 50` presses) | **Split** → decision budget (iters) + frame ceiling `F` |
| observe once per action | **Add** world-side sample stride `s` for predicate eval (no wire change) |

**Riskiest claim (what a gate must test):** the *perception-free* pair `{elapsed_frames,
idle_settled(whole-frame)}` plus the decision/frame budget split is enough to make a bounded skill useful
in a continuous-time world — no new privileged channel, no 3D perception. Because this rung deliberately
excludes the foveated `region_*`, its reach is bounded: it can time-bound actions and hold through
transitions, but NOT steer by an on-screen element. So the honest gate is a **batching-benefit** bar (à
la rung-1's 1.3×) on tasks reachable with hold/time primitives alone; if even that fails, the deficit is
in the budget/predicate model (cheap to fix). Tasks needing `region_*` are out of scope until 3D
perception ships — the point of isolating the bridge here is to NOT let a perception gap masquerade as a
skill-model failure.

## §9 What this unblocks / next step

The **build PR** for the first continuous-time port (MKDS, off the banked race savestate) pins: the
world's idle floor (measured), the three thresholds, `r`, `s`, `F`, and the exact enum strings — then
runs the free seam check and a pre-registered A/B (skills vs primitives) exactly as rung-1 did. This doc
is the shared shape that PR implements; it does not itself authorize any paid run.

## Sources
- `world_mcp.py` — skill executor + budget constants (`:492`, `:495`, `:569`, `:571`), stop_when parsers
  (`:943` Kirby, `:1885` ARC), discrete decision assumption (`:1293`), define-time "can't fire" checks
  (`:963-971`), clean-abort (Kirby `:1108`, ARC `:2023`). Reuse story is Kirby-derived.
- `runs/nds3d_probe/FINDINGS.md` — MKDS race idle 12.2%/frame, perception breaks; `mkds_race_start.state`.
- `reports/2026-07-03-skill-compilation-design.md` — rung-1 mechanism + `repeat_until` formalism.
- `reports/2026-07-03-skill-rung1-ab-verdict.md` — the 2.94× batching result + qualifying-call guard.
- `reports/2026-07-04-vizdoom-3d-floor-design.md` §2.1+§3.2 — frames-per-action (tics / `repeat`) precedent; 3D perception is a later climb.
- `reports/2026-07-03-entity-v3-verdict.md:109` — `region_changed` degeneracy against a moving target (the discrete preview of this problem; on this branch + `main`). Fuller v3.1 write-up on `main` via PR #96: `reports/2026-07-04-entity-v3.1-verdict.md`.
- `reports/nds-emulation-plan.md` — dual-screen/touch deltas; 3D perception failure-triggered (Δ3).
- `core/contracts.py` — Observation/ToolResult wire types (no new type introduced).
