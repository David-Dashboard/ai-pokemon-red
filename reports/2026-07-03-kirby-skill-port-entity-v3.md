# 2026-07-03 — Kirby skill port + entity-grounding gate v3 (repaired bar, conditional-half evidence)

Design + gate pre-registration only — **no primitives are built by this pass**, per ADR-002 §11
("build ONLY the primitives the gate needs") and the house pre-registration style of
`reports/2026-07-03-entity-gate-v2-plan.md` / `reports/2026-07-03-skill-compilation-design.md`. This
doc is deliberately ONE pre-registration covering TWO things that turn out to be the same build: the
Kirby GB port of `define_skill`/`run_skill` (the second port named by
`reports/2026-07-03-skill-rung1-ab-verdict.md`'s NEXT-implications section) and entity-gate v3 (the
grounding metric that needs that port's exposure-control macro to exist at all). Evidence base: the
rung-1 design doc, the rung-1 A/B verdict (PASS, 2.94x, both merged), the entity-gate v2 plan + its FAIL
synthesis (`HANDOFF.md` 2026-07-04 blocks), and `world_mcp.py` (read directly for every wire fact cited
below — no predicate here is asserted without a line reference).

## 1. Why these are one doc, not two

Entity-gate v2 FAILed for a *mechanism* reason, not a metric reason: "the brain never designed exposure
contrast... the grounding loop needs an EXPERIMENT-DESIGN skill... not just honest logging"
(`reports/2026-07-03-entity-gate-v2-plan.md`'s FAIL synthesis, `HANDOFF.md` 2026-07-04). The rung-1
skill-compilation formalism was purpose-built to supply exactly that shape (design doc §5: "the v2 FAIL's
own language calls for... rung 1's formalism supplies exactly that shape via the loop construct"). The
rung-1 A/B verdict PASSed on ARC but **explicitly left the conditional half untested** ("Honest bounds":
0 of 15 skill definitions used `repeat_until`/`stop_when`; the PASS "validates the BATCHING half... NOT
the conditional-loop half — that half remains untested in any paid run", and names the Kirby exposure
macro as the port that "REQUIRES the loop construct this run never exercised"). So: the Kirby port cannot
be gated on ARC's metric (wrong world), and entity-gate v3 cannot re-run without the exposure-control
mechanism (v2's own diagnosis) — the two are the same next paid step, scored by one instrument. Building
them separately would either duplicate the port-build PR or duplicate the gate PR; this doc pins both in
the one place a reviewer needs to read to authorize the run.

## 2. Kirby port scope (define_skill/run_skill on GB Kirby)

**Build scope: `kirby_dreamland` ONLY**, mirroring rung 1's own scoping law ("Rung 1 ships exactly ONE
executor... GB, Kirby, doom, and miniwob ports are later rungs, each with its own pinned per-world
predicate enum and its own build PR" — design doc §6). This is that later rung's build PR, for exactly
one world.

**Where it lives, architecturally.** `kirby_dreamland` is NOT a standalone session class like
`ArcAgi3Session` — it runs through the generic `World` class (`world_mcp.py:626`), the same
`Gateway`+`GamePlugin` dispatch every other GB world uses (`world_mcp.py:175-178`: `PerceptionPlugin` +
`FollowCameraPerceiver` + the generic-GB sandbox, `watch={"hp": 0xD086}` for the oracle only). `define_skill`/
`run_skill` therefore get added to `World`'s tool surface and `World.call` dispatch
(`world_mcp.py:692-699`, `876-915`), not to a new session class — same seam-tool-pair shape as
`ArcAgi3Session`'s (design doc §3), different host class. `kirby_dreamland` already has `read_region`/
`whats_changed` (it is in `_REGION_TOOL_WORLDS`, `world_mcp.py:94`) and `explore`/`goto` (the free
autopilot) — the skill tools are additive, not a rebuild of the observe/action surface.

**Arm-isolation env var: `KIRBY_SKILLS`, not a shared `SKILLS_WORLDS`.** Decision of record — one flag
per world, matching the ARC precedent exactly (`ARC_SKILLS`, `world_mcp.py:537-541`, gated in
`_arcagi3_static_tools`). Justification: (1) a shared flag (`SKILLS_WORLDS=arcagi3,kirby_dreamland`)
would require parsing a CSV env var and threading a world-membership check through both `_static_tools`
(pre-boot) and the live tool surface (post-boot, `World.tools()`) — more surface for a seam-isolation bug
than the ARC precedent has; (2) the two worlds' skill tool specs and `stop_when` enums are entirely
different (ARC's `steps` are `act`-payloads keyed on `ACTION1-7`; Kirby's are `press_button`/`wait`
payloads keyed on GB buttons) — a single shared flag would still need per-world dispatch tables
underneath it, so the "shared" flag buys no real code reuse, only a shorter env-var name; (3) per-world
flags are independently auditable in a transcript (`env | grep SKILLS` on a Kirby run shows exactly
`KIRBY_SKILLS`, never an ARC flag that happens to also be set) — cleaner for the seam-validation check
below. **Stricter-only rule inherited:** if a future third port wants skill tools, it gets its own flag
too; this is not revisited to "simplify" into a shared var after the fact.

**Seam-isolation is checkable via `tools/list`, exactly like the ARC arm.** `_static_tools("kirby_dreamland")`
(`world_mcp.py:576-591`) must return the base nav+action tool list when `KIRBY_SKILLS` is unset, and
`[*nav_and_action, define_skill, run_skill]` when `KIRBY_SKILLS=1` — an MCP client's `tools/list` response
is inspectable BEFORE any brain session starts, same as the ARC arm's pre-registered check ("a
seam-validation transcript confirming Arm A could not see the skill tools at all", rung-1 verdict). This
is gate 4 below (§6), not asserted here — it must be run and pass before any paid launch.

**Executor mechanism (pinned after PR #92 review, SEV-1: per-press re-observation).** The ARC executor
can check `stop_when` after every primitive because `act` returns the grid inline and `_apply_frame`
(`world_mcp.py:1389-1410`) updates the diff state per press. `World` has no such hook: raw presses
dispatch through `self.gw.execute()` (`world_mcp.py:910`), which never touches `_frame_hist`/perceiver
state — only `_content()` does (`world_mcp.py:733-751`), and only once per top-level tool call. As
originally written, §3's pixel-diff and move-outcome predicates were unimplementable mid-loop.
**Decision of record: the Kirby executor performs a lightweight re-observation after EACH inner press**
— it calls `self.plugin.observe(_AGENT)` per press (the exact per-step pattern `World._run_autopilot`
already uses for the free autopilot, `world_mcp.py:841`), then the `_track_frame()` frame-pair update
(`world_mcp.py:757-769`), and evaluates `stop_when` from the fresh `sym.last_action["outcome"]` /
tracked-frame MAD. Honest accounting (same correction shape rung 1's own §3 made for its dispatcher):
this is NEW executor code — a per-press observe-and-check loop — not a reuse of `_content()`; what IS
reused is the perceiver/diff machinery each predicate reads (§3's line citations trace FIELD sources,
not an existing per-press loop). Two pinned consequences: (1) **step alignment** — `observe()`
increments `_obs_count` and writes one oracle row per call (`core/perception_plugin.py:290-317`), so a
per-press-observing macro produces exactly one oracle row per press, the same step granularity as manual
play; drop steps INSIDE a macro span stay individually detectable by the scorer. (2) **cost is UNKNOWN
until measured** — a perceiver pass per press is CPU-side, not API-side, so §5.5's $ model is
unaffected, but the wall-clock overhead is unbudgeted today; free pre-check gate 2 (§6) measures it on
recorded frames and pins the budget: **mean <= 150 ms/press over the recorded-frame corpus, else the
port design is revisited before any build proceeds.** The revisit path is pinned now, not improvised
later: narrow the enum to `steps_elapsed` + `move_blocked`/`move_succeeded` (which need only the
per-press observe, no frame diff) and drop `region_changed` from skills. The alternative design (narrow
the enum pre-emptively and skip the perf gate) was considered and rejected: `region_changed` is the
exposure macro's primary approach predicate after §3's entity demotion — narrowing it away before
measuring would gut the macro this port exists to serve. Measure first; narrow only if forced.

## 3. GB/Kirby `stop_when` enum (closed, wire-only, verified against world_mcp.py)

Rung 1's rule carries over unchanged: **never an oracle/RAM/score field, never anything not already
derivable from data the brain already receives via `observe`/`whats_changed`/the action-result text**
(design doc §3). Every predicate below is checked against the actual field or string it derives from —
no GB predicate ships that isn't traceable to a specific line.

- **`steps_elapsed(n)`, `n <= 50`.** Identical shape to ARC's (design doc §3) — a world-step counter
  `run_skill` already tracks (`world_mcp.py:1706-1708`'s `world_steps_used` bookkeeping, mirrored for
  Kirby). Not derived from any wire field; it is the loop's own step counter.
- **`move_blocked`.** Fires when the most recent action's outcome is `"blocked"`. Derived from
  `core/grid_perceiver.py:294-299`'s `outcome = "blocked"` (persistent no-move -> wall) surfaced verbatim
  in `obs.text` as `"Last move '<action>' -> BLOCKED: you did NOT move; that direction is a wall. Choose
  a DIFFERENT direction."` (`core/perception_plugin.py:375-377`; the non-free-movement variant at line
  351-352 is the same field). The brain already reads this string every observe; the predicate is a
  world-side check of the identical `sym.last_action["outcome"]` field the text was rendered from
  (`core/perception_plugin.py:307-310`'s oracle record, and the same `la.get("outcome")` the renderer
  reads at line 350/374) — no new channel. **Fragility note (pinned after review):** `outcome ==
  "blocked"` fires only after `wall_confirm = 3` consecutive no-move presses at the same dead-reckoned
  (cell, direction) key (`core/grid_perceiver.py:294-297`, `WALL_CONFIRM` default 3 at
  `core/grid_perceiver.py:30`) — a `move_blocked` stop fires on the THIRD blocked press, not the first,
  and the underlying dead-reckoning is the same side-scroller-unreliable state machine that disqualifies
  `screen_scrolled` below (same caveat family). Why it is still acceptable where `screen_scrolled` is
  not: the predicate is only ever consulted INSIDE a `repeat_until` bounded by `max_iters <= 8` and the
  50-step ceiling — a mis-tracking `move_blocked` cannot wedge the executor (the loop terminates via
  `max_iters` and logs that stop reason honestly), whereas a scroll predicate would have been
  load-bearing for claims about world state with no such bound. Pre-check gate 6 (§6) verifies the
  3-press firing latency through the seam.
- **`move_succeeded`.** The complementary case, `outcome == "moved"` (`core/perception_plugin.py:353-354,
  378-379`, `"Last move '<action>' -> moved."`). Needed so a `repeat_until` can be phrased either "walk
  until blocked" (hit a wall/enemy) or "walk until you actually moved" (recover from a stuck state) —
  both directions of the same field.
- **`region_changed(x0,y0,x1,y1)`**, capped at the same `_REGION_MAX_SIDE=96` source-pixel box
  `read_region`/`whats_changed` already enforce (`world_mcp.py:243-245, 771-782`). Derived from
  `_whats_changed`'s own mean-abs-diff-over-threshold computation
  (`world_mcp.py:823-827`: `mad = mean(|prev-curr|)`, `changed = mad >= 2.0`) — the world already computes
  this cheaply from the last two tracked frames (`_track_frame`, `world_mcp.py:757-769`); the predicate
  reuses the identical dead-zone constant (`2.0`) so a skill's stop condition and a manual `whats_changed`
  call agree bit-for-bit. This is the Kirby analogue of ARC's `grid_changed_in_region` (design doc §3) —
  same shape (diff of two observations the brain already receives verbatim), different underlying
  representation (pixel MAD vs. cell-grid diff). Per-press evaluation is §2's executor mechanism's NEW
  code — the MAD formula and dead-zone are reused; the per-press frame-tracking loop is not.

**DEMOTED to candidate predicate (review finding — NOT in the pinned enum):** `entity_count_changed`
(fires when the `sm.get("entities")` count differs from the count at loop start,
`core/perception_plugin.py:386-389`'s `"Entities on screen (sprites/enemies/items): ..."` line). The
original rationale stands on paper — a contact-kill removes the enemy sprite, so a count drop is a
wire-visible contact proxy without touching the hp oracle, and the v2 run brief called the entities line
"the part you can trust" (`runs/brain_kirby_entity/CLAUDE.md:32`) — but the adversarial review checked
all four `runs/brain_kirby_entity/` transcripts and found **ZERO "Entities on screen" lines in any of
them**: the line renders only when the detector returns a non-empty list
(`core/perception_plugin.py:387`, `if entities:`), so the entity channel has never once fired on real
Kirby frames. The "trustworthy" claim was brief prose, not observed data. `core/entities.py::
EntityDetector.detect()` also has no temporal smoothing/hysteresis, so per-frame GB sprite flicker is an
untested count-flapping risk. **Admission rule, pinned:** `entity_count_changed` joins the enum ONLY if
free pre-check gate 3 (§6) shows the ACTUAL detector firing non-spuriously — stable counts, no
frame-to-frame flapping — on a REAL recorded enemy-approach frame sequence; decided before the paid run,
never mid-run. Until and unless it passes, the exposure macro's approach half uses `region_changed`
(§4).

**Explicitly NOT pinned (rejected, with reasons):** `screen_scrolled` — an earlier draft (rung-1 design
doc §5) listed this as illustrative, but no wire field reports scroll state for the generic-GB
`FollowCameraPerceiver` path the way `sym.pose`/`walls_here` do for top-down worlds; the v2 run brief
itself says "the position/walls part of `observe` is unreliable here... your reported position may stick
at (0,0)" (`runs/brain_kirby_entity/CLAUDE.md:26-28`) — pinning a predicate on data the brief itself
disqualifies would violate the "never anything not already derivable" rule in spirit even where a field
technically exists. If a later pass finds a reliable scroll signal, it is added at THAT pass, never
retrofitted here. **`hp_dropped` is explicitly rejected** — hp is oracle/RAM-only (`watch={"hp": 0xD086}`,
scoring-only, never returned by any tool per the no-leak law stated at the top of `world_mcp.py`); a
`stop_when` keyed on it would be exactly the "oracle/RAM/score field" rung 1's non-goals forbid (design
doc §6: "No reward-driven anything").

## 4. The exposure-control macro (expressed in the formalism)

This is the mechanism v2 lacked, named explicitly in its own FAIL synthesis: "the grounding loop needs an
EXPERIMENT-DESIGN skill... be measurably away from the suspect during ordinary time" (`HANDOFF.md`
2026-07-04). Expressed with §3's enum:

```
define_skill("approach_suspect", steps=[
  {"repeat_until": {"steps": [{"button": "right", "hold_frames": 30}],
                    "stop_when": "region_changed(x0,y0,x1,y1)", "max_iters": 8}}])
define_skill("retreat_to_benign", steps=[
  {"repeat_until": {"steps": [{"button": "left", "hold_frames": 30}],
                    "stop_when": "steps_elapsed(8)", "max_iters": 8}}])
```

`(x0,y0,x1,y1)` is the box around the tracked suspect from the brain's immediately-prior `read_region`
look — the same box as its `ENT` line. Approach walks right and stops the moment the watched box's
pixels change (the suspect moving into/out of it, a contact, a kill) — a qualifying `run_skill` call.
(`entity_count_changed` is the candidate UPGRADE for this half if its §6 gate-3 admission check passes;
`region_changed` is the pinned default.) Retreat is a FIXED step count (`steps_elapsed`, deliberately
unconditional) toward the benign cluster — a second qualifying call. The alternation ITSELF is not a
single `repeat_until` (design doc §3: no nesting, no cross-skill looping construct) — the brain
re-invokes each skill per cycle, which is exactly the right granularity: each call is one paid decision,
and the brain still chooses HOW MANY cycles to run, informed by its own drop count so far.

**The claim protocol (pinned after PR #92 review, SEV-1 — claims never ride inside macros).** One cycle
is mechanically:

1. manual `read_region`/`whats_changed` on the suspect's box — this reveals the CURRENT step `step=<N>`
   and advances the watermark to it — then `remember "NEAR id=<threat> step=<N>"` if the suspect is
   near (the PRE-approach claim; it is what covers any drop landing inside the coming approach span,
   since `W = 15 >=` the approach's `<= 8` steps);
2. `run_skill("approach_suspect")`;
3. manual `read_region`/`whats_changed` again — reveals the post-macro CURRENT step — then the
   post-approach `NEAR` claim at exactly that step, if warranted;
4. `run_skill("retreat_to_benign")`;
5. manual look + the benign entity's `NEAR` claim at ITS current step; dwell; repeat from 1.

`NEAR`/`ENT` claims are only valid BETWEEN skill calls and may only name the CURRENT step — the step
revealed by the most recent watermark-advancing look, which after a macro is the post-macro step at
which the brain regained control. A claim naming any step INTERIOR to a `run_skill` span is excluded by
the scorer mechanically (§5.6), not just discouraged by the brief.

**The pinned expectation this macro must satisfy: it DRIVES `b_k` DOWN.** v2's arm (a) FAILed because
`b_k = 0.812` — the threat was near during 81% of ordinary (non-drop) steps, because the brain "just
plays" near it continuously (camping). A macro that mechanically alternates fixed approach/retreat
phases forces measurable away-time INTO the session structure — the retreat phase's `steps_elapsed(8)`
floor guarantees at least 8 world-steps per cycle where the brain is NOT near the threat (assuming the
retreat direction is genuinely away, which the post-run audit below checks). This is not asserted as
automatic; it is the testable claim §5's `b_k` ceiling precondition exists to enforce.

## 5. Entity gate v3 pre-registration

Same NEAR/watermark/dedupe/conflict machinery as v2 (`reports/2026-07-03-entity-gate-v2-plan.md`,
carried over unchanged per its own stricter-only clause), with three changes: the repaired bar, a `b_k`
sanity precondition, and a new skill-mechanism guard.

### 5.1 Machinery carried over unchanged from v2

- BCD-identity hp oracle at `0xD086` (plain int 0-5, `world_mcp.py:170-174`'s documented identity-decode
  note — the v2 scorer's `_bcd()` needs no change).
- `WINDOW = 15`, watermark rule (revealed-step watermark from `read_region`/`whats_changed`
  `step=<N>` tokens only — bare `observe()` does not advance it, per v2's documented residual leak,
  self-mitigated the same way — and now EXTENDED, stricter-only, by §5.6's macro-interior exclusion:
  the v2 watermark alone cannot police claims against steps hidden inside a multi-step `run_skill`
  span), dedupe (first-wins), `UNMATCHED_MAX_FRACTION = 0.05`,
  `MALFORMED_MAX_FRACTION = 0.20`, `RETROACTIVE_MAX_FRACTION = 0.20`, `MIN_NEAR = 3`,
  `MIN_TOTAL_STEPS = 30`, `MIN_SESSION_DROPS = 5`, the CONFLICTING-declaration guard (`NO_DECLARE`).
- Verdict vocabulary: `PASS / FAIL / INSUFFICIENT_DATA / INSUFFICIENT_DROPS / NO_DECLARE`, now extended
  with the skill-guard's own `INSUFFICIENT_DATA` trigger (§5.4).

### 5.2 The repaired bar (bounded form — Decision of record)

**The flaw:** v2's `GROUNDED` test was `q_k >= b_k + 0.30`. With the observed `b_k = 0.812`, the bar
becomes `q_k >= 1.112` — but `q_k` is a coverage PROPORTION, `q_k <= 1.0` by construction (it's `#drops
covered / #drops`, both non-negative integers with the numerator bounded by the denominator). **The bar
was arithmetically unreachable the moment `b_k` crossed `0.70`.** This is not a close call the brain
narrowly missed; `q_k = 0.800` was in fact the SECOND-HIGHEST possible value short of perfect coverage,
and it still could not have passed even at `q_k = 1.0` (`1.0 < 1.112`). No brain behavior could have
produced a PASS once camping pushed `b_k` that high — the metric was broken independent of the evidence.

**Options considered:**

1. **Odds-ratio bar:** `odds(q_k) / odds(b_k) >= R` for some ratio `R`, where `odds(p) = p/(1-p)`. Bounded
   correctly (odds ratio has no upper-bound-collision issue since both odds diverge together as p→1), but
   introduces a new functional form with no precedent anywhere else in the repo's gates (HUD gate, GATE-3D,
   rung-1 skill gate all use additive margins or straight ratios of BOUNDED-below quantities) — a reviewer
   auditing this gate would need to reason about odds-ratio behavior near p=1 from scratch. Rejected: not
   wrong, but adds unfamiliar machinery for no benefit over option 2 below.
2. **Capped additive margin:** `q_k >= min(b_k + 0.30, 0.5 + b_k/2)`. The second branch is a compromise
   curve that asymptotically approaches 1.0 as `b_k -> 1.0` but never exceeds it — bounded by
   construction. But: the crossover point (`b_k + 0.30 = 0.5 + b_k/2` at `b_k = 0.40`) means for ANY
   `b_k > 0.40` the effective bar is the second, unfamiliar branch — i.e. the "capped" branch is doing
   ALL the work for exactly the regime (high camping) where this bug bit. That is backwards: it makes the
   bar LOOSER precisely where v2's failure mode was baseline inflation (at `b_k=0.812`, this formula's bar
   is `0.5+0.406=0.906` — still tighter than `q_k<=1.0` allows it to fail by definition, so it is
   reachable, but it rewards exactly the high-`b_k` regime with a shallower climb: going from `b_k=0.5`
   to `b_k=0.9` only raises the bar from 0.65 to 0.95, a smaller marginal cost per unit of camping than a
   flat +0.30 would impose in the reachable zone). Workable, but it treats the symptom (unreachable bar)
   without addressing the cause (camping should be diagnosed and rejected, not accommodated by a softer
   curve).
3. **Absolute-bar-plus-margin AND a `b_k` ceiling, camping diagnosed as INSUFFICIENT_DATA:**
   `q_k >= 0.80` (absolute) AND `q_k - b_k >= 0.15` (margin, loosened from 0.30 in raw terms but now
   COMBINED with the absolute floor so it cannot be gamed by inflating both `q_k` and `b_k` together) —
   gated behind a **precondition**: `b_k <= 0.70` for the entity to be scoreable on the GROUNDED test at
   all; `b_k > 0.70` reports that entity as `INSUFFICIENT_DATA` (camping detected — the session failed to
   produce exposure contrast, not a grounding failure) rather than computing a doomed ratio.

**Decision of record: option 3, with a b_k ceiling, not option 1 or 2.** Justification: v2's own language
diagnosed the ROOT CAUSE as "the brain never designed exposure contrast" — the fix belongs at the
precondition layer (refuse to score a session that never achieved contrast) rather than at the
bar-shape layer (accommodate a session that never achieved contrast with a softer curve). A ceiling also
gives §4's exposure macro a concrete, falsifiable target: the macro's job is to keep `b_k <= 0.70`, and
if it fails to (the brain still camps despite having the tool), that failure is now VISIBLE as
`INSUFFICIENT_DATA` instead of silently producing an unreachable bar that looks like ordinary evidence.
**Pinned numbers:**

- **`B_K_CEILING = 0.70`.** An entity with `b_k > 0.70` is reported `INSUFFICIENT_DATA` for that entity
  (not scored GROUNDED or FAIL) — camping made the session uninformative about that entity, full stop.
  Chosen because it sits strictly below v2's observed failure value (`0.812`), so this run's own data
  would have been caught by the precondition rather than silently producing a broken ratio — the ceiling
  is set to actually FIRE on the evidence that motivated it, not placed comfortably above it.
- **`GROUNDED` (threat), replacing v2's `q_k >= b_k + 0.30`:**
  `q_k >= 0.80` (absolute floor) **AND** `q_k - b_k >= 0.15` (margin, halved from v2's 0.30 — justified
  below) **AND** `b_k <= 0.70` (the ceiling precondition) **AND** `|N_k| >= 3` (unchanged `MIN_NEAR`).
  All four required; failing the ceiling precondition reports `INSUFFICIENT_DATA` for that entity before
  the other three are even evaluated (order matters for the report, not for correctness — all four must
  hold for GROUNDED regardless of evaluation order).
- **Why the margin is 0.15, not 0.30, and why that is not "loosening":** v2's stricter-only clause
  binds future amendments of the SAME metric, not a metric REPLACEMENT that repairs a structural flaw —
  and this doc's own machinery is still, if anything, tighter in the regime that matters: the absolute
  floor `q_k >= 0.80` is NEW (v2 had no absolute floor at all — a threat with `q_k=0.31, b_k=0.00` would
  have passed v2's bar, which this doc's floor now blocks). At `b_k=0.812` (v2's actual observed value),
  v3's ceiling would have fired `INSUFFICIENT_DATA` before evaluating the margin at all — the 0.15 number
  is only reachable in the `b_k <= 0.70` regime the ceiling now enforces, where a 0.15 margin on top of a
  hard 0.80 floor is a real, visible effect (e.g. `b_k=0.70` requires `q_k>=0.85`; `b_k=0.40` requires
  `q_k>=0.80` from the floor alone, the margin already implied). The combination (floor + margin + ceiling)
  is strictly harder to satisfy by accident than v2's single additive-margin test, even though the raw
  margin constant is smaller in isolation.
- **`CORRECTLY REJECTED` (benign), mirrored:** a benign/rejected entity `j` is correctly rejected iff it
  is scoreable (`|N_j| >= 3`, `b_j <= 0.70` — same ceiling; a benign candidate that itself got camped near
  is equally uninformative) and NOT (`q_j >= 0.80` AND `q_j - b_j >= 0.15`).
- **Arithmetic check (the whole point of this section):** the new bar is satisfiable for every `b_k` in
  `[0, 0.70]` — at `b_k = 0.70`, `q_k >= max(0.80, 0.85) = 0.85 <= 1.0`, reachable. At `b_k = 0`,
  `q_k >= max(0.80, 0.15) = 0.80 <= 1.0`, reachable. No `b_k` in the scoreable range produces a bar above
  1.0. **This property (bar strictly `<= 1.0` for all admissible `b_k`) is the pinned correctness
  criterion for the repaired metric and must be checked into the scorer as an assertion, not just argued
  in prose.**
- **Inclusivity, pinned explicitly (review finding — pinned the way v2 pinned `n==s-15` covers,
  `n==s-16` does not):** every comparison in this gate is inclusive exactly as written, `>=`/`<=`
  throughout, no exceptions. `q_k = 0.80` exactly passes the floor; `q_k - b_k = 0.15` exactly passes
  the margin; `b_k = 0.70` exactly is scoreable (the ceiling excludes only strictly greater). Worked
  probe: `q_k = 0.80, b_k = 0.65` → floor met (`0.80 >= 0.80`), margin met (`0.15 >= 0.15`), ceiling
  met (`0.65 <= 0.70`) → GROUNDED-eligible (subject to `MIN_NEAR`).
- **Overall verdict combination (restated in v3's own text, unchanged from v2 — review finding):**
  `PASS` = `>= 1` declared threat GROUNDED **AND** `>= 1` declared-benign/REJECTed entity correctly
  rejected. Both arms required. `NO_DECLARE` if either declaration side is missing entirely; an id
  declared both ways is CONFLICTING — excluded from both arms, and if the exclusion starves an arm the
  verdict is `NO_DECLARE` naming the conflict.
- **Downward-gaming `b_k` via extreme retreat — closed by inherited machinery, walked explicitly
  (review finding 4):** a brain that retreats so far/so often that it is never NEAR anything in
  ordinary time starves the BENIGN entity of accepted NEARs too (`MIN_NEAR = 3` is per-entity,
  inherited from v2 verbatim), routing the benign arm to `INSUFFICIENT` — no false PASS is reachable
  through absence alone; and the threat arm still needs `q_k >= 0.80`, which demands real presence in
  drop windows. Retreat only helps by creating CONTRAST (away in ordinary time, near at consequences),
  which is grounding, not gaming.

### 5.3 The `b_k` ceiling as a stated exposure-macro target

`B_K_CEILING = 0.70` is doing double duty: it is both a scoring precondition (§5.2) and the pinned
success criterion for whether §4's macro did its job. If the macro is used (per §5.4's guard) and `b_k`
STILL exceeds 0.70, that is itself a reportable finding for the run write-up ("the macro existed but the
brain didn't use it enough / used it wrong"), distinct from a `FAIL` (which requires the ceiling to be
cleared and the margin/floor to fail) or an `INSUFFICIENT_DATA` (the ceiling itself firing).

### 5.4 The new skill-mechanism guard (the conditional-half evidence rung 1's verdict lacked)

Per the rung-1 A/B verdict's own NEXT-implications: "a future port's gate should consider pinning
something like 'at least 1 qualifying call whose `stop_when` fired before max steps' so the conditional
half is verified, not just permitted... Stricter-only, to be pinned fresh in that port's own
pre-registration." This is that pinning.

- **Qualifying skill call (carried from rung 1):** a `run_skill` call with logged `executed_step_count >=
  3` (`eval/score_skill_rung1.py`'s `QUALIFYING_MIN_EXECUTED_STEPS`, reused verbatim, not re-derived).
- **NEW: qualifying-conditional call.** A qualifying call whose logged `stop_reason` shows the
  `repeat_until`'s `stop_when` fired BEFORE `max_iters` was reached — i.e. `stop_reason` matches one of
  `move_blocked`, `move_succeeded`, `region_changed(...)` fired (plus `entity_count_changed` if
  admitted per §3/§6 gate 3) — world_mcp.py's `_check_stop_when`/`repeat_until_summary` shape
  (`world_mcp.py:1653-1675`, ported to Kirby's enum) — NOT
  `"reached max_iters=N without stop_when firing"` and NOT `steps_elapsed(n)` alone (a pure step-count
  loop is conditional in NAME only — it never actually branches on world state, so it does not count as
  conditional-half evidence; this mirrors why `steps_elapsed` is listed in §3 as a legitimate predicate
  for the RETREAT half but does not itself satisfy this guard). **AND (review finding — the
  single-iteration laundering hole): the firing `repeat_until`'s logged iteration count must be
  `>= 2`** (the `"iterations"` field in the executed record, `world_mcp.py:1675`'s
  `"iterations": iters_done`, carried unchanged into the Kirby log schema). A `max_iters=1` skill
  whose `move_blocked` fires deterministically against a wall the brain already knows about is a
  pre-known one-shot dressed as a loop — the same spirit-violation as bare `steps_elapsed`, laundered
  through a predicate name. `iterations >= 2` means the loop genuinely re-checked its predicate at
  least once on world state the brain had not yet seen — cheap, mechanical, checkable against the
  already-logged field.
- **PINNED GATE:** `>= 1` qualifying-conditional call, or the run is `INSUFFICIENT_DATA` (skill-mechanism
  half untested) — reported separately from, and prior to, the GROUNDED/FAIL computation. This gate must
  be checked FIRST: if it fails, the GROUNDED/rejection numbers are still computed and reported (for
  completeness/audit) but the overall verdict is `INSUFFICIENT_DATA`, not `PASS`/`FAIL`, exactly as v2's
  own `MIN_SESSION_DROPS` guard pre-empts a PASS/FAIL computation.
- **Auditability:** every `define_skill`/`run_skill` record is logged verbatim to `skills.jsonl`
  (`world_mcp.py:1376-1377`'s stated discipline, inherited unmodified for Kirby), so the post-run audit
  can mechanically verify which calls were conditional and which fired early — reuse
  `eval/score_skill_rung1.py::audit_skill_log`'s shape (not its ARC-specific fixture) for this check.

### 5.5 One-attempt rule, `--max-turns`, $ target (from the v2 run 11 ledger)

- **One attempt, pinned.** Same discipline as v2 and rung 1: ONE paid attempt under this
  pre-registration. An infra death (MCP/seam failure, credit exhaustion) before **N=10 decisions** may be
  relaunched once; at or after 10 decisions, or a second infra death, the run banks `INSUFFICIENT_DATA`.
  A completed run's verdict is banked, never informally re-attempted.
- **`--max-turns`:** v2's verdict run (`runs/brain_kirby_entity/run4_v2_FAIL/`) cost **$3.056472** at
  **66 `num_turns`** (verified directly against `transcript.jsonl`'s final `total_cost_usd`/`num_turns`
  fields) under the brief's own "cap ~50 decisions" instruction (prose, not enforcement — the actual
  `num_turns` ran past that, the exact protocol-breach lesson GATE-3D already taught: "briefs are not
  budget enforcement"). **Pinned: `--max-turns 90`, a hard mechanical cap** — headroom above the 66
  observed turns for a brief that now ALSO needs skill-tool calls (define_skill once or twice, several
  run_skill calls) layered onto the same NEAR/ENT/DECLARE protocol, without re-inflating to GATE-3D's
  1000-turn failure mode.
- **$ target:** linearly scaling run 11's $3.056/66-turns to a 90-turn cap gives **~$4.17**, called
  **$5 TARGET, not enforcement** — per the same protocol-breach lesson, the turn cap is what actually
  bounds spend; the dollar figure is informational.
- **Press physics / wall-clock (corrected after review — the "24-frame" figure was the wrong constant
  for this world):** a GB press costs `hold_frames + 16` settle frames (`core/gb_emulator.py:114`
  defaults `hold=8, settle=16` = the 24-frame figure from the Cave Noire lesson). The seam-validated
  KIRBY recipes use `hold_frames=30` (walk) and `hold_frames=20` (jump/mount) → **46 and 36 frames per
  press**, not 24. Recomputed arithmetic: worst-case `run_skill` (50-step ceiling, all walking presses)
  = 2,300 frames ≈ 38 s of GAME time; one full §4 approach+retreat cycle (`<= 16` presses) ≈ 736 frames
  ≈ 12 s. Wall-clock is NOT a cost concern and is now stated instead of left open: headless sessions
  run `_realtime=False` (`core/gb_emulator.py:78, 92-93`), so ticks are unpaced `pyboy.tick()` calls —
  seconds of CPU per macro. The run's $ cost remains driven by API turns, which §2's per-press
  re-observation mechanism does not touch (it is emulator/CPU-side only; its own overhead is bounded
  separately by gate 2's 150 ms/press budget).
- **Amendment rule:** stricter-only. `B_K_CEILING`, the `0.80`/`0.15` bar, the skill-mechanism guard
  (incl. `iterations >= 2`), the macro-interior exclusion + its 0.20 cap, the turn cap, and the
  one-attempt rule may be tightened by a future pass but never loosened to rescue a marginal result —
  identical clause to v2's and rung 1's.

### 5.6 Macro-time vs claim-time: the macro-interior exclusion (new in v3 — closes PR #92's SEV-1 claim hole)

v2's watermark was designed against single-step `observe`/`read_region` calls; a `run_skill` can advance
the world by up to 16+ steps between brain-visible frames, and on the `World` path its trailing content
renders through `_content()`, which emits NO step token (`world_mcp.py:733-751`) — so a macro neither
advances the watermark nor pins which interior step a post-macro NEAR may name. Left unaddressed, the
brain could run a 16-step macro, feel the outcome, and retroactively pick whichever interior step best
decorates its chosen threat — the watermark only rejects steps ABOVE what has been revealed, not
favorable steps inside an un-observed span. Closed mechanically, three rules:

1. **Claims only between skill calls, current step only.** A `NEAR`/`ENT` claim is valid only when
   logged between top-level tool calls (mechanically guaranteed — the brain has no execution inside a
   `run_skill`) and may only name the CURRENT step: the step revealed by the brain's most recent
   `read_region`/`whats_changed` (the only watermark-advancing calls, unchanged from v2), which after a
   macro is the post-macro step at which the brain regained control. §4's claim protocol is the
   run-brief statement of this rule.
2. **Scorer exclusion (new class, alongside retroactive/unmatched):** a claim naming step `n` is
   **MACRO-INTERIOR** iff some `run_skill` record `r` in `skills.jsonl` satisfies
   `r.step - r.world_steps_used < n < r.step` — the record's `step` field is the world step at result
   logging time (macro end) and `world_steps_used` is the span length (both fields already in the log
   schema, `world_mcp.py:1705-1708`, carried unchanged into the Kirby port), so span boundaries are
   exact and mechanical, no transcript heuristics. Macro-interior claims are excluded from scoring,
   counted, and reported; `MACRO_INTERIOR_MAX_FRACTION = 0.20` of all NEAR lines (same constant shape
   and taint semantics as `RETROACTIVE_MAX_FRACTION`) → `INSUFFICIENT_DATA`. The span's START step
   (`r.step - r.world_steps_used`, the pre-macro current step) and END step (`r.step`) remain claimable
   — they are exactly the boundary steps rule 1 permits.
3. **Coverage is preserved for the pinned macro, shown not assumed:** a drop landing mid-approach at
   step `s` is covered by the PRE-approach NEAR at the approach's start step `n` whenever
   `s - n <= W = 15`, and the approach span is `<= 8` steps — so boundary-only claiming costs zero
   coverage for the §4 macro. A macro longer than `W` would open a real coverage hole; that is one more
   reason the 50-step ceiling stays and the exposure macro stays short.

Stricter-only relative to v2 (a new exclusion class + cap; nothing loosened). The scorer build PR must
carry a unit test pinning both directions: an interior-step claim is excluded; the exact end-step claim,
made after a watermark-advancing look, is accepted.

## 6. Free pre-checks first (numbered gates, before any paid run)

1. **`eval/score_skill_rung1.py`-style `--dry` extended to the Kirby executor.** A canned-frame driver
   exercising `World._define_skill`/`_run_skill` (once ported) against scripted frame sequences standing
   in for: an approach that ends in `region_changed` firing, a retreat that ends in `steps_elapsed(8)`,
   a `move_blocked` case (walk into a wall — must fire on the THIRD blocked press per §3's
   `wall_confirm=3` note, and the scenario pins that latency), and a `max_iters` cap-out (stuck loop).
   Each scenario pins its expected `stop_reason` substring + `executed_step_count` + `iterations`,
   checked mechanically — same shape as `eval/score_skill_rung1.py::run_dry`'s fixture-driven scenarios,
   ported to Kirby's predicate names and `press_button` step shape instead of ARC's `act` payloads.
   **Honest scoping note (review finding): no Kirby-shaped fixture exists today** —
   `eval/fixtures/` holds only the ARC push-macro fixture and an unrelated title-menu PNG pair; building
   this fixture is the build PR's work, correctly listed here as unbuilt.
2. **Per-press executor overhead budget (NEW — pinned by §2's executor decision).** Measure the
   wall-clock cost of one per-press re-observation (`plugin.observe()` + `_track_frame()` + predicate
   check) over `>= 100` recorded Kirby frames (the `runs/brain_kirby_entity/run*/world/` PNG corpora
   exist and are free). **Budget: mean `<= 150 ms/press`.** Over budget → the port design is revisited
   before any build proceeds, taking §2's pinned fallback (narrow the enum to `steps_elapsed` +
   `move_blocked`/`move_succeeded`, drop `region_changed` from skills) — never shipping an unmeasured
   hot loop into a paid run.
3. **`entity_count_changed` admission check (NEW — the §3 demotion's exit door).** Run the ACTUAL
   `core/entities.py::EntityDetector.detect()` against a REAL recorded enemy-approach frame sequence
   (recorded fresh through the seam if the archived run frames lack an approach segment — the archived
   transcripts contain zero entity-line firings, which is the finding that forced this gate). PASS =
   the detector (a) fires at all on approach frames, and (b) shows no frame-to-frame count flapping
   (sprite-flicker check: count stable across consecutive frames of a stationary scene). Only on PASS
   is `entity_count_changed` promoted from candidate (§3) into the enum — decided before the paid run,
   never mid-run. FAIL costs nothing: the macro's approach half already uses `region_changed`.
4. **`tools/list` seam-isolation check.** With `KIRBY_SKILLS` unset, confirm `define_skill`/`run_skill`
   are absent from `_static_tools("kirby_dreamland")`'s response; with `KIRBY_SKILLS=1`, confirm they are
   present with the pinned Kirby `stop_when` enum documented in their tool description (mirrors the ARC
   arm's pre-registered seam-validation transcript check, rung-1 verdict).
5. **`assert_action_tools_fresh`-style drift check**, confirming the added `define_skill`/`run_skill`
   specs match whatever the live `World.tools()` actually serves once the port lands — same discipline
   `world_mcp.py:594-618` already enforces for the press-button surface, extended to cover the two new
   tools so a schema edit can't silently drift.
6. **Seam-press physics re-validation.** The v2 FAIL synthesis flags that recipes "MUST be validated
   through the seam — a direct-PyBoy-verified recipe failed live" (the Cave Noire lesson: 24-frame
   default presses meant the enemy AI's first strike landed at pass #17, not where a direct-emulator
   test predicted). Corrected constants for THIS world (review finding): the Kirby recipes use
   `hold_frames=30`/`20`, i.e. **46/36 frames per press** (hold + 16 settle,
   `core/gb_emulator.py:114`), not the 24-frame default. Before the paid run: replay the §4 macro's
   presses through the actual MCP seam (not a bare PyBoy script) and confirm (a) `region_changed` fires
   at the 46-frames-per-press cadence the design assumes, and (b) `move_blocked`'s 3-press
   `wall_confirm` latency (§3) matches on-seam. **Prep note (review finding): no saved emulator state
   for the v2 start position exists in `runs/brain_kirby_entity/`** — this gate needs a seed state
   re-derived from ROM boot (or a recorded mid-run frame), listed here so it isn't discovered as a
   surprise blocker.
7. **`audit_skill_log`-shape auditability check** on the gate-1 dry-run's own `skills.jsonl`,
   confirming every `define_skill` row carries a verbatim definition and every `run_skill` row carries
   `executed`/`executed_step_count`/`stop_reason`/`world_steps_used` (and the `iterations` field §5.4's
   guard reads) — the same fields `eval/score_skill_rung1.py::audit_skill_log` already checks, run here
   against the Kirby log before trusting it as the source for §5.4's conditional-call guard and §5.6's
   span-boundary exclusion on the REAL paid run.

**All seven must pass before the paid run is scheduled** — same discipline as GATE-3D-A3-PC gating PR-H
and rung-1's §4.0 free instrument gating its own paid A/B.

## 7. Honest bounds + non-goals

- **No other GB games.** This build scope is `kirby_dreamland` only. Cave Noire (the v1/early-v2
  instrument, retired per `HANDOFF.md` 2026-07-04: "wrong instrument, not wrong metric") is not touched
  or re-instrumented by this doc.
- **No cross-run skills.** Skills defined this run die at run end, identical to rung 1's `remember()`-
  lifetime law (design doc §6). A macro that seems to generalize (e.g. `approach_suspect` itself) is
  a hand-curation CANDIDATE for design-space (ii) in the rung-1 doc, never auto-carried forward by this
  pass.
- **The per-press executor is NEW code with unmeasured cost until gate 2.** §2's re-observation loop has
  no existing implementation to inherit performance numbers from; the 150 ms/press budget is a design
  bound, not a measurement. If the budget fails, the pinned fallback (narrowed enum) ships instead — an
  untested hot loop never reaches a paid run.
- **v3 is one paid attempt.** Per §5.5 — a completed run banks its verdict; there is no "best of N" or
  informal re-launch.
- **The `b_k` ceiling is a diagnostic, not a guarantee the macro works.** §5.3 already flags this: if the
  brain uses the macro and `b_k` STILL exceeds 0.70, that is itself the finding, reported honestly (not
  papered over by loosening the ceiling after the fact — the amendment rule in §5.5 forbids that).
- **The skill-mechanism guard (§5.4) can independently sink the run to `INSUFFICIENT_DATA` even if the
  grounding numbers would otherwise PASS or FAIL cleanly** — by design: this run is doing double duty
  (grounding gate + conditional-half evidence for rung 1's formalism), and a run that produced clean
  grounding data via flat, non-conditional skill calls (or no skill calls at all) has NOT satisfied the
  second purpose, regardless of the first.
- **One game, one attempt, no variance estimate.** Same accepted limitation as rung 1's own A/B (design
  doc, verdict's Honest bounds) — this is not a repeated-trial design; it trades variance information for
  cost and pre-registration cleanliness.
- **No promotion, no learned predicates, no reward-driven anything** — rung 1's §6 non-goals apply
  unchanged to this port: nothing here writes to `core/`/`games/`, `stop_when` stays a fixed closed enum
  (§3), and no oracle/RAM signal (hp included) ever becomes a `stop_when` predicate or a runtime reward.

## 8. Decided vs open

- **DECIDED (this doc, as amended by the PR #92 review fix round):** Kirby port = `define_skill`/
  `run_skill` added to `World` (`world_mcp.py:626-915`), gated behind `KIRBY_SKILLS` (one-flag-per-world,
  not a shared var); executor = per-press re-observation (`plugin.observe()` + `_track_frame()` per inner
  press, the `_run_autopilot` pattern), NEW code with a pinned 150 ms/press mean budget (gate 2) and a
  pinned fallback (narrow the enum, drop `region_changed`) if the budget fails. Kirby's PINNED `stop_when`
  enum = `steps_elapsed(n<=50)`, `move_blocked` (fires on the 3rd consecutive blocked press,
  `wall_confirm=3`), `move_succeeded`, `region_changed(x0,y0,x1,y1)` (MAD>=2.0, same dead-zone as
  `whats_changed`) — each traced to a specific `world_mcp.py`/`core/perception_plugin.py`/
  `core/grid_perceiver.py` line above; `entity_count_changed` is DEMOTED to candidate (zero firings in
  all four archived Kirby transcripts), admitted only if gate 3's recorded-frame flicker check passes;
  `screen_scrolled` and any oracle-keyed predicate (incl. `hp_dropped`) are explicitly rejected. Claim
  protocol: NEAR/ENT only BETWEEN skill calls, current (post-macro) step only; macro-interior claims
  excluded mechanically via `skills.jsonl` span boundaries (`r.step - r.world_steps_used < n < r.step`),
  `MACRO_INTERIOR_MAX_FRACTION = 0.20` taint. Entity gate v3's bar = `q_k >= 0.80` AND
  `q_k - b_k >= 0.15` AND `b_k <= 0.70` (all four incl. `MIN_NEAR>=3`, inclusive `>=`/`<=` throughout),
  bounded-by-construction property asserted in the scorer; PASS combination restated (>=1 GROUNDED threat
  AND >=1 correctly-rejected benign, both arms). Skill-mechanism guard: `>=1` qualifying-conditional
  `run_skill` call — stop_when fired before max_iters AND `iterations >= 2` — or `INSUFFICIENT_DATA`.
  Press physics: 46/36 frames per press (hold 30/20 + 16 settle), not 24; wall-clock a non-issue
  (headless `_realtime=False`, unpaced ticks). Seven free pre-check gates, all before any paid run.
  `--max-turns 90` (hard cap), `$5` target (informational), one-attempt rule with the 10-decision
  infra-relaunch carve-out, stricter-only amendment rule.
- **OPEN (flagged, not resolved here):** whether the four pinned predicates (plus `entity_count_changed`
  if admitted at gate 3) are sufficient for the brain to express a good exposure macro on its first
  attempt without a redesign mid-run (rung 1's own ARC enum needed no additions in its one paid run, but
  Kirby's side-scroller physics are less explored); whether the gate-2 measurement will hold the 150
  ms/press budget on the real perceiver stack (the fallback is pinned but shrinks the macro's conditional
  vocabulary); and whether a second Kirby port attempt (if this one lands `INSUFFICIENT_DATA` on the
  skill-mechanism guard specifically, with grounding otherwise clean) should get a narrow, pre-registered
  SECOND attempt scoped ONLY to re-exercising `repeat_until` — left for the triage after this run's
  result, not decided in advance (the one-attempt rule in §5.5 governs unless and until a separate
  pre-registration amends it).

---

# AMENDMENT A1 (2026-07-03) — §5.4 multi-`repeat_until` combination rule (pre-scoring, stricter-only)

Appended per the house stricter-only discipline: the original text above is LAW as written and is not
edited; this amendment supersedes it only where explicitly stated. Trigger: the PR #94 scorer build
found a genuine ambiguity in §5.4 — the section names the top-level `stop_reason` and "the
`iterations` field in the executed record", but per `world_mcp.py:1147` `iterations` lives on the
INNER `repeat_until` sub-record inside `executed` (not on the top-level `run_skill` record), and
nothing in the doc forbids a skill's top-level `steps` list containing more than one sibling
`repeat_until` block (§4's "no nesting, no cross-skill looping construct" rules out nesting and
cross-skill loops only). The doc did not pin how to combine iteration counts across multiple sibling
blocks in one call; the PR #94 adversarial review ruled the builder's stricter reading correct and
required it written down here BEFORE the real run is scored.

**Amendment (2026-07-03, pre-scoring, stricter-only): when a `run_skill` record contains multiple
`repeat_until` sub-records, ONLY the final one (the one credited in the top-level `stop_reason` —
`executed[-1]["repeat_until_summary"]` is what `world_mcp.py` copies up) is evaluated for the
qualifying-conditional test (fired predicate + `iterations >= 2`). Iteration counts are never
summed/OR'd across multiple sibling blocks. This is a strict subset of any-sub-record readings** — an
early, unrelated loop's iteration count can never paper over a laundered single-iteration (or
`steps_elapsed`-terminated) final loop, so no run that fails this reading could pass a looser one in
a direction that rescues a verdict. §5.5's amendment rule is satisfied: stricter-only, pinned before
`runs/brain_kirby_v3` is scored.
