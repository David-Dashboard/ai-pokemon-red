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
is gate 5 below (§7, pre-check #5), not asserted here — it must be run and pass before any paid launch.

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
  reads at line 350/374) — no new channel.
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
  representation (pixel MAD vs. cell-grid diff).
- **`entity_count_changed`.** Fires when the `sm.get("entities")` count differs from the count at loop
  start (`core/perception_plugin.py:386-389`'s `"Entities on screen (sprites/enemies/items): {len(entities)}
  at {ctrs}."` line — the ONLY field the v2 run brief itself called "the part you can trust" for this
  side-scroller, `runs/brain_kirby_entity/CLAUDE.md:32`). A contact-kill in Kirby removes the enemy sprite,
  so an entity-count drop is a wire-visible proxy for "contact happened" without reading hp (which stays
  oracle-only, never on the wire, per the no-leak law) — useful for the exposure macro's approach half
  ("push toward the entity until its count changes or you're blocked").

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
define_skill("approach_and_retreat", steps=[
  {"repeat_until": {"steps": [{"button": "right", "hold_frames": 30}],
                    "stop_when": "entity_count_changed", "max_iters": 8}},
  {"repeat_until": {"steps": [{"button": "left", "hold_frames": 30}],
                    "stop_when": "steps_elapsed(8)", "max_iters": 8}}
])
```

Approach the tracked entity (walk right, stop the moment its count changes — a contact/kill event, or
`move_blocked` if it turns out to be a wall) — this is one qualifying `run_skill` call. Retreat a FIXED
step count (`steps_elapsed`, not a condition) toward the benign cluster, logging its NEARs there — a
second qualifying call. Alternate by calling both skills back-to-back; the alternation ITSELF is not a
single `repeat_until` (design doc §3: `repeat_until` is not nested, and rung 1 ships no cross-skill
looping construct) — the brain re-invokes `run_skill("approach_and_retreat")` then
`run_skill("retreat_to_benign")` each cycle, which is exactly the right granularity: each call is one
paid decision, the brain still chooses HOW MANY cycles to run (informed by its own drop count so far),
and the mandatory `NEAR`/`ENT` logging happens in the brain's own `remember` calls between skill calls,
unchanged from v2's protocol.

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
  self-mitigated the same way), dedupe (first-wins), `UNMATCHED_MAX_FRACTION = 0.05`,
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
  `move_blocked`, `move_succeeded`, `region_changed(...)`, `entity_count_changed` fired (world_mcp.py's
  `_check_stop_when`/`repeat_until_summary` shape, `world_mcp.py:1653-1675`, ported to Kirby's enum), NOT
  `"reached max_iters=N without stop_when firing"` and NOT `steps_elapsed(n)` alone (a pure step-count
  loop is conditional in NAME only — it never actually branches on world state, so it does not count as
  conditional-half evidence; this mirrors why `steps_elapsed` is listed in §3 as a legitimate predicate
  for the RETREAT half but does not itself satisfy this guard).
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
- **Amendment rule:** stricter-only. `B_K_CEILING`, the `0.80`/`0.15` bar, the skill-mechanism guard, the
  turn cap, and the one-attempt rule may be tightened by a future pass but never loosened to rescue a
  marginal result — identical clause to v2's and rung 1's.

## 6. Free pre-checks first (numbered gates, before any paid run)

1. **`eval/score_skill_rung1.py`-style `--dry` extended to the Kirby executor.** A canned-frame driver
   exercising `World._define_skill`/`_run_skill` (once ported) against scripted `observe`/`whats_changed`
   sequences standing in for: an approach that ends in `entity_count_changed` firing, a retreat that ends
   in `steps_elapsed(8)`, a `move_blocked` case (walk into a wall), and a `max_iters` cap-out (stuck
   loop). Each scenario pins its expected `stop_reason` substring + `executed_step_count`, checked
   mechanically — same shape as `eval/score_skill_rung1.py::run_dry`'s fixture-driven scenarios, ported
   to Kirby's predicate names and `press_button` step shape instead of ARC's `act` payloads. Must PASS
   before gate 2.
2. **`tools/list` seam-isolation check.** With `KIRBY_SKILLS` unset, confirm `define_skill`/`run_skill`
   are absent from `_static_tools("kirby_dreamland")`'s response; with `KIRBY_SKILLS=1`, confirm they are
   present with the pinned Kirby `stop_when` enum documented in their tool description (mirrors the ARC
   arm's pre-registered seam-validation transcript check, rung-1 verdict). Must PASS before gate 3.
3. **`assert_action_tools_fresh`-style drift check**, confirming the added `define_skill`/`run_skill`
   specs match whatever the live `World.tools()` actually serves once the port lands — same discipline
   `world_mcp.py:594-618` already enforces for the press-button surface, extended to cover the two new
   tools so a schema edit can't silently drift.
4. **Seam-press physics re-validation.** `runs/brain_kirby_entity`'s `CLAUDE.md`/`run.sh` and the v2 FAIL
   synthesis both flag that Cave Noire's recipes "MUST be validated through the seam — a direct-PyBoy-
   verified recipe failed live" (24-frame press timing meant the enemy AI's first strike landed at pass
   #17, not where a direct-emulator test predicted). Before the paid run: replay the exposure macro's
   `press_button right/left hold_frames=30` steps through the actual MCP seam (not a bare PyBoy script)
   and confirm the `entity_count_changed`/`move_blocked` predicates fire at the frame counts the design
   in §4 assumes — free, since this uses the same emulator session any dry-run already boots.
5. **`audit_skill_log`-shape auditability check** on the gate-2/gate-4 dry-run's own `skills.jsonl`,
   confirming every `define_skill` row carries a verbatim definition and every `run_skill` row carries
   `executed`/`executed_step_count`/`stop_reason`/`world_steps_used` — the same fields
   `eval/score_skill_rung1.py::audit_skill_log` already checks, run here against the Kirby log before
   trusting it as the source for §5.4's conditional-call guard on the REAL paid run.

**All five must pass before the paid run is scheduled** — same discipline as GATE-3D-A3-PC gating PR-H
and rung-1's §4.0 free instrument gating its own paid A/B.

## 7. Honest bounds + non-goals

- **No other GB games.** This build scope is `kirby_dreamland` only. Cave Noire (the v1/early-v2
  instrument, retired per `HANDOFF.md` 2026-07-04: "wrong instrument, not wrong metric") is not touched
  or re-instrumented by this doc.
- **No cross-run skills.** Skills defined this run die at run end, identical to rung 1's `remember()`-
  lifetime law (design doc §6). A macro that seems to generalize (e.g. `approach_and_retreat` itself) is
  a hand-curation CANDIDATE for design-space (ii) in the rung-1 doc, never auto-carried forward by this
  pass.
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

- **DECIDED (this doc):** Kirby port = `define_skill`/`run_skill` added to `World`
  (`world_mcp.py:626-915`), gated behind `KIRBY_SKILLS` (one-flag-per-world, not a shared var); Kirby's
  `stop_when` enum = `steps_elapsed(n<=50)`, `move_blocked`, `move_succeeded`, `region_changed(x0,y0,x1,y1)`
  (MAD>=2.0, same dead-zone as `whats_changed`), `entity_count_changed` — each traced to a specific
  `world_mcp.py`/`core/perception_plugin.py`/`core/grid_perceiver.py` line above; `screen_scrolled` and
  any oracle-keyed predicate (incl. `hp_dropped`) are explicitly rejected. Entity gate v3's bar =
  `q_k >= 0.80` AND `q_k - b_k >= 0.15` AND `b_k <= 0.70` (all four incl. `MIN_NEAR>=3`), with the bounded-
  by-construction property checked as an assertion in the scorer. New skill-mechanism guard: `>=1`
  qualifying-conditional `run_skill` call (stop_when fired before max_iters) or `INSUFFICIENT_DATA`.
  `--max-turns 90` (hard cap), `$5` target (informational), one-attempt rule with the 10-decision
  infra-relaunch carve-out, stricter-only amendment rule — all carried/adapted from v2 and rung 1
  unchanged in spirit.
- **OPEN (flagged, not resolved here):** whether the five enum predicates in §3 are sufficient for the
  brain to express a good exposure macro on its first attempt without a redesign mid-run (rung 1's own
  ARC enum needed no additions in its one paid run, but Kirby's side-scroller physics are less explored);
  whether `entity_count_changed` is reliable enough given the v2 brief's own warning that pose/walls data
  is unreliable in this side-scroller (the entities line was the ONE channel v2 called trustworthy — this
  doc leans on that same channel, but it has not been stress-tested as a `stop_when` predicate, only as
  human-readable text); and whether a second Kirby port attempt (if this one lands `INSUFFICIENT_DATA` on
  the skill-mechanism guard specifically, with grounding otherwise clean) should get a narrow, pre-
  registered SECOND attempt scoped ONLY to re-exercising `repeat_until` — left for the triage after this
  run's result, not decided in advance (the one-attempt rule in §5.5 governs unless and until a separate
  pre-registration amends it).
