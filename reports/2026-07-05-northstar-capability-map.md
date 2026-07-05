# North Star: capability map, method completion, and the fastest path — the master document

**Status:** strategic doc, written 2026-07-05 by the retiring lead; expanded same day at David's
direction to hold EVERYTHING in one place: (A) the six capabilities the North Star requires, each
with evidence, cheapest probe, and falsifier; (B) the method-completion checklist — the last 20%
that turns the working method into a complete one; (C) the fastest path — a two-track plan where
free work front-runs the paid bottleneck. Companion to the **world-lanes-frontier** skill (lanes =
where each WORLD stands; this doc = what each spend is FOR and where the road ends). Nothing here
is a pre-registration; every paid spend still goes through **gate-methodology** and David.

The North Star (HANDOFF §1): one agent — fixed brain + swappable perceiver — completing human-given
tasks at human-grade competence from the screen alone, across increasingly different worlds,
cheaply, without per-world training. Four claims: Capability, Constancy, Generality, Cheap.

**Honest position (2026-07-05): ~20% of the way in capabilities, ~80% in method.** Method compounds;
part B closes its gap to 100% almost for free. Part C is how the capability 20% grows fastest.

---

# A. The six capabilities

### A1. Real time (acting while the world moves — and while the brain thinks)

- **Why necessary:** every world beaten so far waits for the agent — the harness advances on
  press/tick, so System 2 deliberates against a frozen frame. MKDS ended that: idle change
  12.22%/frame mean with zero input (`runs/nds3d_probe/FINDINGS.md:329`). Live games, computer-use
  under real deadlines, and every robot rung are real-time. Claim 1 at human-grade is unreachable
  without it.
- **What exists:** the continuous-time `stop_when` bridge design
  (`reports/2026-07-04-continuous-time-stopwhen-design.md`, merged); the MKDS build plan + A/B
  pre-registration (`reports/2026-07-04-mkds-continuous-time-build-plan.md`).
- **The deeper cut:** the bridge handles *skills* in continuous time, not *deliberation* in
  continuous time. Today the world pauses while the brain thinks; real time removes the pause,
  which eventually makes the seam asynchronous (state stream up, intent stream down, System 1
  holding a safe default meanwhile). That is an ADR-level evolution of the frozen contract — the
  one place the contract should be EXPECTED to legitimately bend. Deliberate ADR, never a per-world
  hack.
- **Cheapest next probe (free):** scripted System-2 latency injection in MKDS — a scripted policy
  goes silent for N seconds mid-race; measure ruin vs N. The survivable-deliberation window is the
  requirements spec for how much reflex must be compiled (A5) before real time is attemptable.
- **Falsified if:** no achievable reflex layer can hold a nontrivial world stable across realistic
  LLM latencies even with compiled skills. Then screen-only + LLM-decisions cannot reach live
  worlds without a fundamentally different System 1 — amend the thesis, don't write a bigger brief.

### A2. Spatial reasoning — metric maps, place-graph, and the NAMED layer (the keystone)

- **Why necessary:** goal-directed tasks are referential — "go to Oak's lab", "fetch my mug".
  Three layers (reports/CONTEXT-BRIEFING.md "The frontier"): metric maps within a place (largely
  done in 2D), a topological place-graph across portals (fragile), a named/semantic layer binding
  language to places/objects (not built — the keystone gap). Instruction-following itself is
  trivial objective-injection; referential grounding is the real capability.
- **Sharpened diagnosis:** the missing thing is *addressability*, not reasoning power. The brain
  reasons fine; it has no stable structure to point at across warps. System 1 owns the structure;
  System 2 references it by name (don't leak cognition into the world).
- **Cheapest next probe (free, Pokémon Red):** within ONE run — can the brain coin a name for a
  place ("home", "lab") and can System 1 resolve that name back to a goto target after >=5 portal
  transitions? Warps are already recorded; score = oracle map-id vs resolved target, offline.
- **Falsified if:** name→place binding needs per-world ontology hand-authoring (breaches
  no-per-world-training in spirit) or only works with oracle map-ids on the wire (breaches
  screen-only). Either is a first-class finding.

### A3. Complex perception (free-form fonts, non-tile rendering, 3D projection, photoreal later)

- **Why necessary:** the three banked NDS breaks — free-form non-tile font/HUD, rotating minimap
  killing the tile-grid, continuous camera roll killing discrete facing
  (`runs/nds3d_probe/FINDINGS.md:353-372`) — are the first tier of every harder world's perception.
- **What exists:** the Realizer Ladder discipline (R0→R3, climb only on a measured failed bar —
  **perception-primitives**); glyph R1 designed with a pinned gate; yaw_flow/stationary_movers as
  the first 3D primitives.
- **The honest wager:** every ladder climb erodes claim 4 (Cheap). The bet that must survive: a
  SMALL set of primitives + RARE VLM escalation beats both a trained monolith and a per-world zoo.
  Track cost-of-perception per world class explicitly (see B4 ledger).
- **Cheapest next probes:** glyph R1 build against its pinned bar (recall >=0.85 / precision 0.90 /
  0 phantoms); a minimap-agnostic heading primitive probed offline on the banked MKDS frames.
- **Falsified if:** any world class forces an R3 model on the HOT PATH (every frame, not at stuck
  moments) to meet its capability bar — "cheap" is falsified for that class; bank the boundary.

### A4. Within-run long-horizon memory (the quiet killer)

- **Why necessary:** human-grade tasks run hours. The first long-horizon run
  (`runs/brain_kirby_longhaul`, 316 turns, $42.98) showed the failure shape: ~70M cache-read
  tokens, cost/turn ~2x the short-run rate, every remember-note re-injected verbatim forever, no
  compaction on the `claude -p` path (**long-horizon-runs**). Claim 4 dies of cost and claim 1
  dies of incoherence at exactly the scale that matters.
- **Law note:** within-run memory hygiene (the brain summarizing/indexing its own history —
  progressive disclosure applied to its own past) is learning-boundary-compliant; the
  segmented-chain ferry needs David's chain-as-one-run ruling first
  (**cheapness-skill-compilation** §4).
- **Cheapest next probe:** the 2-session segmented pilot (~$10-15) — checkpoint continuity + the
  ferry + the first decisions-per-milestone-over-time curve, in one pre-registration.
- **Falsified if:** the wakes-per-milestone curve NEVER bends within a run as skills/lessons
  accumulate — System-2→System-1 compilation would be decoration and the cost model linear in task
  length forever. The single most falsifiable near-term claim of the thesis; seek the answer.

### A5. Compiled conditional reflexes (the loop half — real time's secret dependency)

- **Why necessary:** batching passed (rung-1 2.94x) but a `stop_when` that genuinely branches on
  world state has NEVER fired in a paid run (every attempt degenerated —
  **cheapness-skill-compilation** §5, **diagnose-a-run** worked example). Without
  world-state-branching reflexes, System 1 cannot hold the fort at frame rate: A1 is blocked on
  this, not just the cost axis.
- **Cheapest next probes:** the doom scan-and-center port (gate MUST require the loop half —
  already pinned) and the MKDS A/B (continuous-time-native predicates sidestep the
  converging-enemy degeneracy that killed the Kirby attempts).
- **Falsified if:** with predicates matched to world physics, loops still collapse to one-shots or
  counters. Then the closed-enum design is too weak; escalation = a richer (still non-learned)
  predicate algebra, pre-registered, never silently widened.

### A6. Continuous action (the forgotten twin of complex perception)

- **Why necessary:** the action side degrades in parallel with the perception side: discrete
  buttons → touch coordinates (the NDS drag gap, `FINDINGS.md:216-219`) → hold-duration steering
  (MKDS) → analog sticks → joint torques. The harness speaks buttons and single touches; the
  embodiment ladder's upper half is mostly this capability.
- **Cheapest next probes:** the touch-drag helper the NDS findings flagged (world-side, free,
  testable offline); steering-by-hold-duration as the first analog dimension inside the MKDS lane.
- **Falsified if:** continuous control demands a learned policy (violates no-training) or
  per-world controller code that dwarfs the perceiver (violates constancy's "no hand-written
  System-1 per genre" clause, HANDOFF §1).

### The interlock (why no single capability is "the" blocker)

Real time (A1) demands compiled reflexes (A5); reflexes demand the loop half; task scale demands
memory hygiene (A4); everything referential demands the named layer (A2); both frontier axes
degrade perception (A3) and action (A6) together. The North Star falls not to one missing piece
but to a failed interlock. Retirement bets: **the named layer is the keystone** (hardest, least
prior art, most falsifying if it can't be cheap); **real time is the biggest architectural risk**
(the seam must bend by ADR without breaking constancy); **within-run memory is the most
underestimated** (it fails slowly and expensively instead of loudly).

---

# B. Method completion — the last 20%, mostly free

The method's working parts (probe-first, pre-registration, one-attempt banking, adversarial
verification, held-out hygiene, constancy audits) stay untouched. Five additions complete it:

### B1. The graduation exam (define NOW, run at phase exits only)

A held-out task battery with human baselines — the missing definition of "arrived" for claim 1.
Without it, gates can be won forever while the destination stays unmeasured.

- **Shape:** ~10 tasks, >=2 per world class, each a human-given instruction with an
  oracle-observable end state. Sketch (to be pinned in its own doc): GB — Red "get the first
  badge", Kirby "clear stage 3"; GBA/NDS — Emerald "reach the first town", MKDS "finish a race
  (any place)"; 3D — doom "find the exit"; computer-use — MiniWoB form-with-typing episode set;
  plus >=2 tasks on a NEVER-TOUCHED game (exam-held-out, same discipline as Crystalis).
- **Baselines:** David (or any human) plays each task once, cold; wall-clock + success recorded.
  Human-grade = success within ~2x human time. Crude is fine — the point is a fixed yardstick.
- **Rules:** tasks frozen once pinned (additions allowed, edits are a new exam version); never
  tuned on; run the battery ONLY at phase exits (C below), one attempt per task, banked verbatim;
  the score is reported as-is in HANDOFF even (especially) when embarrassing.
- **Cost:** definition free; a full run ~$50-100 at current prices — which is why it runs at phase
  exits, not per-gate.

### B2. The brain-size constancy axis

Constancy is tested across worlds but never across BRAIN SIZES — yet claim 4's endgame implies a
small brain must eventually ride the same harness. One probe: rerun two banked worlds (Red
starter, MiniWoB click-button) with a Haiku-class brain, zero harness changes, ~$2-5 total.
Either the scaffolding carries the small brain (major validation) or the capability cliff is
measured. Re-run at each phase exit alongside the exam. **Falsifier this adds:** if capability
only ever tracks frontier-brain scale, the architecture is a thin wrapper and claim 4 needs
restating.

### B3. Finish the drift-tripwire table

CONTEXT-BRIEFING's tripwire table still has ▶ (unbuilt) rows. Each is a small PR-sized task:
- Constancy counter: per-world "LOC changed outside the perceiver" check (a script over git diff,
  run at port PRs).
- Provenance field in run `meta.json` + a test refusing model-generated labels not oracle-checked.
- Confident-wrong-rate threshold alert on held-out wall-recall (extend `eval/cross_game.py`).
- The one-sentence rule as a review-checklist item in **dev-workflow** (prose, free).
(✅ already exist: contract hash, no-RAM-leak, import boundaries, cost breaker, lean-game fitness.)

### B4. The capability-evidence ledger (lives in THIS doc — update per gate)

| Capability | Status 2026-07-05 | Next evidence event |
|---|---|---|
| A1 real time | design only (bridge merged); no paid evidence | MKDS A/B |
| A2 named layer | nothing built; probe designed above | name→place probe (free) |
| A3 complex perception | 3 NDS breaks banked; glyph R1 designed | glyph R1 build; MKDS |
| A4 within-run memory | failure shape banked (longhaul); no mitigation | segmented pilot |
| A5 conditional reflexes | batching PASS; loop half 0-for-3 | MKDS A/B + doom port |
| A6 continuous action | touch gap documented; nothing built | touch-drag helper (free) |

**Process rule (already in force):** every gate pre-registration names which capability(ies) it
buys evidence about; a gate that buys none is not run. After each banked verdict, update this
table in the same PR as the verdict.

### B5. Paid-ledger by capability

The per-day paid ledgers in HANDOFF stay the source of record; add one line per entry naming the
capability bought (e.g. "MKDS A/B $9 → A1+A5"). Makes dollars-per-capability legible over months
— the number that tells you whether "fastest" (part C) is actually being achieved.

---

# C. The fastest path — two tracks, free front-runs paid

**The bottleneck is the paid track** (one account, ~$5-15 per gate, one attempt each, David's
authorization). Free work is effectively unlimited in parallel. So the plan is two tracks: the
paid track never waits for design, because the free track de-risks every gate before its turn.

### Track F (free, start ALL of these now, in parallel — no authorization needed)

1. **F1 Graduation-exam definition doc** (B1) — pure writing + one human-baseline session.
2. **F2 Brain-size probe prep** (B2) — launcher variants; the ~$2-5 run itself needs a nod.
3. **F3 Latency-injection probe in MKDS** (A1) — scripted policy, offline scoring; produces the
   survivable-deliberation window BEFORE the async-seam ADR is ever drafted.
4. **F4 Name→place probe on Red** (A2) — free run infrastructure exists; the keystone's riskiest
   assumption tested for $0 (usable with a scripted brain; a paid variant only if the free one is
   ambiguous).
5. **F5 Touch-drag helper** (A6) — small world-side PR + offline test.
6. **F6 Tripwire completion PRs** (B3) — constancy counter, provenance field, wall-recall alert.
7. **F7 Minimap-agnostic heading probe** on banked MKDS frames (A3).
8. **F8 Label the frontier data** (A3, A6; corpus-gap audit 2026-07-05) — the labels corpus is
   GB-only (v2: 13 games, 250 frames, 160x144). Label the banked MKDS probe frames
   (`runs/nds3d_probe`, continuous-time + free-form HUD ground truth) and one touch-driven NDS
   game (Phoenix Wright or Professor Layton — both on the shelf, both nearly pure reading/touch)
   via the standard `label_frames` → `snapshot_labels --version v3` pipeline
   (**eval-probes-and-datasets** §2).
9. **F9 Fill the OCR ground-truth hole** (A3, glyph lane) — v2's own manifest flags it: only
   48/661 text/health boxes carry read strings, "not yet cross-world." Backfill read-values across
   3-4 dev games so a cross-world reading claim has ground truth waiting when glyph R1 lands.
10. **F10 Name the exam reserve** (B1) — quarantine 2-3 never-touched titles for the graduation
    exam BEFORE the exam doc is pinned (same discipline as `HELDOUT`, separate list, separate
    purpose), including one non-ViZDoom 3D world — Doom is burned for 3D-primitive claims (the 3D
    lane calibrated on it). Also note two dev-corpus holes for acquisition when their axis matters:
    NO dev pseudo-3D example exists (F-1 Race is held-out and nothing else covers the axis —
    `dataset_split.py`'s "dev has an example of each axis" is false for pseudo-3D), and no
    isometric-view game exists anywhere in the corpus.

### Track P (paid, strictly serial, each gate pre-registered + David-authorized)

1. **P1 MKDS build + A/B** — buys A1, A3, A5, A6 at once; the densest evidence-per-dollar spend
   available. (Already NEXT 2; build spec merged.) F3/F5/F7 land before or during its build.
2. **P2 Doom scan-and-center port** — A5's cleanest shot at the loop half (stationary-target
   predicates; no converging-enemy degeneracy).
3. **P3 Segmented pilot** (after the ferry ruling) — A4 + the curve-bend measurement.
4. **P4 Named-layer gate** — only if F4 survives: "go to <named place>" from natural language,
   screen-only, on Red. If F4 fails, its diagnosis reroutes this slot (that's the probe working).
5. **P5 Glyph R1 gate** — A3; can swap earlier if MKDS blocks on David or the ferry ruling stalls
   P3 (the paid track should never idle waiting on a decision — pull the next unblocked gate).

### Phase exits (when the exam + brain-size probe run)

- **Exit 1 (after P1+P2):** conditional loop fired in a paid run AND unchanged brain progressed in
  a continuous-time world. → run exam v1 + brain-size probe. Expect a low exam score; it's the
  baseline.
- **Exit 2 (after P3 + one task-scale run):** wakes-per-milestone curve bent within a run. If it
  did NOT bend, STOP the ladder and re-derive — everything after assumes compilation compounds.
- **Exit 3 (after P4):** one referential instruction executed cold. → exam v2; if the exam's
  computer-use tasks moved, unlock the MiniWoB harder-tasks lane.
- **Exit 4:** sim-robot binding spike (new-world-port discipline: emulator-Protocol spike first,
  cheapest sim that gives framebuffer/state/save/input) + the async-seam ADR informed by F3's
  window. This is the embodiment jump — treat it like the 3D gate was treated: riskiest assumption,
  cheapest proxy, before any phase commitment.

### Cut / held (explicit, so successors don't re-litigate)

- **ARC breadth: cut from the critical path.** ARC bought its evidence (batching, 2.94x). More
  levels buy ~nothing against A1-A6. Idle-capacity work at most.
- **MiniWoB harder tasks: held until Exit 3** — form-filling is the named-layer problem in
  miniature; attacking it before A2 exists duplicates effort.
- **Async-seam ADR: held until F3's number exists.** Architecture without a requirements number is
  how constancy breaks.
- **Anything requiring across-run training: not on any track** (the law stands; revisiting it is
  David's explicit call, HANDOFF §1).

### Why this is fastest

Every paid gate arrives pre-de-risked by a free probe, so paid attempts spend on PROOF, never on
discovery (probe = prediction; paid run = proof — the slogan, applied to scheduling). The paid
track never idles on a blocked decision (pull-forward rule in P5). Evidence density is the
ordering criterion (P1 buys four capabilities). And the exam at phase exits keeps "fast" honest —
speed toward the North Star, not toward the most interesting frontier.

---

## Sources

- `HANDOFF.md` §1 (the four claims; "falsified if"), newest blocks (2026-07-04/05).
- `reports/CONTEXT-BRIEFING.md` (the frontier: three spatial layers; instruction-following ≈
  objective injection; probe-first; the drift-tripwire table with its ▶ rows).
- `runs/nds3d_probe/FINDINGS.md` (idle 12.22%/frame :329; 3 perception breaks :353-372; touch-drag
  gap :216-219) — on-disk, gitignored.
- `runs/brain_kirby_longhaul/` (316 turns / $42.98 / cache-read growth) — on-disk, gitignored.
- `reports/2026-07-03-skill-rung1-ab-verdict.md` (2.94x PASS; batching-only honest bound).
- `reports/2026-07-04-continuous-time-stopwhen-design.md`,
  `reports/2026-07-04-mkds-continuous-time-build-plan.md`.
- `reports/2026-07-03-glyph-r1-cache-driven-detection.md` (pinned R1 gate).
- Skills: **world-lanes-frontier**, **cheapness-skill-compilation**, **long-horizon-runs**,
  **perception-primitives**, **gate-methodology**, **new-world-port**, **dev-workflow**.
