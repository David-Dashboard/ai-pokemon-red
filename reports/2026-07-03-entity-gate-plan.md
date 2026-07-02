# 2026-07-03 — Entity-grounding gate: protocol + pre-pinned metric (FREE half)

Per ADR-002 §9's own instruction on PASS ("generalize to entities") and the design backlog's
"entity-via-motion" note (`reports/_archive/2026-06-25-design-backlog-future-experiments.md` §3). This
mirrors the proven HUD-grounding gate pipeline exactly (`reports/2026-07-03-adr002-gate-plan.md`,
`eval/score_gate_run.py`, `runs/brain_cn_gate/`): pin the metric + threshold BEFORE any paid run, build
the FREE scoring harness + launcher, do not touch the brain or `core/contracts.py`.

## The claim under test

**Load-bearing claim (generalizing ADR-002 §9 from HUD/life to entities):** the same hypothesize→ground
loop works for **entities** — the brain can hypothesize "THAT thing on screen is a THREAT (contact with
it drops my life)" and **ground it by behaviour/consequence** (contact correlates with hp drops
significantly more than chance), and it can **reject a decoy entity-claim** — something visible that does
NOT cause hp drops (an item, a wall/terrain feature, the exit) — because its contacts do NOT correlate.

**PASS** requires both arms, same shape as the HUD gate:
  (a) **grounds a threat** — a claimed-threat entity's contact-events correlate with hp drops well above
      the session's base rate.
  (b) **rejects a decoy** — a claimed-benign (or explicitly rejected) entity's contact-events do NOT show
      that correlation (its contact-conditional drop rate stays at-or-below the base rate, within margin).

**FAIL** = the direction dies cheap, here, before any rewrite (same posture as the HUD gate).

## World-side needs: ZERO new world/perception code

Checked what already exists before adding anything (bias: add nothing):

- `observe`'s symbolic view already surfaces **entities**: `core/entities.py`'s `EntityDetector` (rolling-
  background subtraction + connected-components on `core/blob.py`, general-purpose, no game-specific
  knowledge) runs inside `core/grid_perceiver.py::GridPerceiver.perceive` for every `GridPerceiver`-based
  world (Cave Noire included — `CaveNoirePerceiver` uses the default detector). Its output
  (`{"bbox": [...], "centroid": [...]}` per blob) is rendered into the brain's text by
  `core/perception_plugin.py::_render_symbolic` as: *"Entities on screen (sprites/enemies/items): N at
  (cx,cy), ..."* — meaning-free positions, exactly the ADR-002 §3 "blob-segment" primitive, exactly the
  substrate the entity gate needs (a brain-visible list of *things*, with no claim about what they are).
- `read_region` (a hypothesized-region crop, image) and `whats_changed` (region frame-diff, symbolic) —
  built for the HUD gate, PR #55 — let the brain zoom in on any one entity's screen position to confirm
  what it's looking at, and to notice contact (e.g. the entity's blob overlapping/adjacent to the avatar,
  or the region flashing on a hit).
- The `hp` oracle (BCD @ `0xC120`, `world_mcp.py`'s `GAMES["cave_noire"]["watch"]`) already exists,
  already never reaches the wire, already logs to `world/oracle.jsonl` keyed by exact world `step`
  (`plugin._obs_count`) — the same no-clock, no-leak alignment discipline as the HUD gate.
- The entities list has **no cross-frame identity** (each `observe()` call runs `detect()` fresh; there is
  a rolling background subtractor but no tracker/ID assignment). This is fine and expected: the HUD gate's
  own protocol has the brain self-assign an opaque key (a region's pixel coords) for whatever it's
  tracking — the entity gate does the same, with the brain assigning its own `id=<k>` per hypothesized
  entity and re-identifying it itself across frames by position/appearance (exactly the "appearance
  proposes, behaviour grounds" discipline in the design backlog §5 — aliasing risk is the brain's problem
  to manage via its own `ENT` log, not something a new tracking primitive should quietly solve for it).

**Verdict: add nothing.** `observe`'s entity list + `read_region` + `whats_changed` + the existing oracle
are suffient. No new tool, no new primitive, no `world_mcp.py` change, no `core/` change. This keeps
`core/contracts.py` untouched and matches the ADR-002 §11 tripwire ("don't over-build the sensorium before
the gate" / "don't hand-code a bespoke perceiver").

## The protocol — what the brain must LOG

Machine-parseable, `remember`-based, mirroring the HUD gate's `HYP`/`DECLARE`/`REJECT` lines exactly:

```
ENT id=<k> region=(x0,y0,x1,y1) step=<n> claim=threat|benign
CONTACT id=<k> step=<n>
DECLARE threat=<k>
DECLARE benign=<k>
REJECT id=<k> reason=<...>
```

- `ENT` — the brain's initial (or re-affirmed) hypothesis about entity `k`: its self-assigned integer id,
  the on-screen region it currently occupies (a `read_region`-style box, so a reviewer/scorer can see what
  it means by "entity k"), the step of the observation, and its *current* claim. An entity may get more
  than one `ENT` line over time (its box moves, or the brain updates its claim) — the scorer only reads
  the claim off `DECLARE`/`REJECT` lines, never off `ENT`, so `ENT` staying purely descriptive avoids
  parser ambiguity about "which claim is final."
- `CONTACT id=<k> step=<n>` — the brain asserts contact (adjacency/overlap with the avatar, or an
  immediately-following hit) with entity `k` at world step `n`. This is the event the scorer correlates
  against hp drops. Multiple `CONTACT` lines for the same `(id, step)` dedupe like the HUD gate's
  `(region, step)` dedupe (first occurrence wins, repeats reported, never double-counted).
- `DECLARE threat=<k>` / `DECLARE benign=<k>` — the brain's final verdict on entity `k`. At least one
  `threat=` and at least one `benign=` declaration are required for a full gate run (mirrors the HUD
  gate's truth+decoy two-arm requirement) — a run with only threats declared cannot exercise arm (b).
- `REJECT id=<k> reason=<...>` — same spirit as the HUD gate's `REJECT`: a candidate entity the brain
  looked at and explicitly ruled out (e.g. "never adjacent to me when hp dropped", "it's a wall
  decoration, never moves, never near me"). A `REJECT` is treated identically to `DECLARE benign=` for
  scoring purposes (both are "claimed not a threat") — the distinct verb just preserves the brain's own
  language for *why* (same UX as the HUD gate having both `DECLARE`-the-truth and `REJECT`-the-decoy).

## The pinned metric — grounding via base-rate comparison

**Exact formula**, decided BEFORE any paid run:

For a session with an oracle `hp` value at each world step (BCD-decoded, in-range [0,10], `None` = skip
as transition garbage — identical discipline to `score_gate_run.py::_oracle_hp_by_step`):

- **Drop step** = a step `s` with an oracle row AND a previous in-range oracle row at the immediately
  prior *oracle-recorded* step `s_prev` (whichever oracle row precedes `s`, not necessarily `s-1` — the
  oracle logs once per `observe()`, so consecutive oracle rows are consecutive *observed* steps, not
  necessarily consecutive raw frames), such that `hp(s) < hp(s_prev)`.
- **Base rate** `p_base = (# drop steps in the session) / (# oracle rows with a defined prior, i.e. total
  scoreable steps - 1)`. This is the unconditional probability that any given observed step is a
  damage step, over the whole session — the "how often do I take damage regardless of anything" rate.
- For a claimed entity `k`, let `C_k` = the deduped set of `CONTACT id=k step=n` steps that have a defined
  oracle row **and** a defined prior-oracle-row (i.e. are scoreable as a drop-step-or-not).
- **Contact-conditional drop rate** `p_k = (# steps in C_k that are drop steps) / |C_k|`.
- **GROUNDED (threat) test**: `p_k >= p_base + MARGIN` **AND** `|C_k| >= MIN_CONTACTS`, where
  `MARGIN = 0.30` (absolute probability points) and `MIN_CONTACTS = 3` (see variation-guard section).
  A margin (not a ratio) is used because `p_base` can be small or zero in a short low-combat session,
  where a ratio threshold (e.g. "3x base rate") blows up or divides by zero; an absolute margin degrades
  gracefully and is directly comparable to the HUD gate's own absolute-gap term (`gap >= 0.30`) — same
  unit, same magnitude, deliberately reusing the prior gate's pinned number rather than inventing a new
  one out of thin air.
- **REJECTED/benign entity test (arm b)**: for a claimed-benign or `REJECT`ed entity `j` with contact set
  `C_j`, the decoy is correctly rejected if **NOT** (`p_j >= p_base + MARGIN`) — i.e. its contact-
  conditional drop rate does NOT clear the same bar a real threat must clear. (This is the mirror of the
  HUD gate's `decoy_agreement <= DECOY_MAX`: the decoy must fail the SAME bar the truth arm requires,
  not some separately-invented easier bar.)

**PASS** = at least one declared/claimed `threat` entity is GROUNDED (per above) **AND** at least one
declared/rejected `benign` entity has its contact set score BELOW the grounding bar. Both arms required,
same letter as the HUD gate's SS9.

**FAIL** = a declared threat fails to ground (contact rate does not clear base rate + margin), OR every
claimed-benign entity's contact rate ALSO clears the bar (the loop cannot tell threats from decoys — the
exact "a gate that can't fail" failure mode SS11 warns about).

### Degenerate / insufficient outcomes (the variation-guard lesson, carried over)

The first live HUD-gate run scored a technically-passing but DEGENERATE result (constant matched
constant, zero hp variation) and had to be caught and re-run under a tightened guard (PR #56). The entity
gate pins the equivalent guards **before** its first paid run, not after:

- **`MIN_CONTACTS = 3`** — a threat (or benign) verdict from fewer than 3 deduped contact events for that
  entity is **INSUFFICIENT_DATA** for that entity (not scored either way). Mirrors the HUD gate's
  `DECOY_LOW_EVIDENCE_MIN = 3`, generalized to both arms here since "too few events" degrades both a
  threat claim and a benign claim identically.
- **`MIN_SESSION_DROPS = 1`** — a session with **zero** drop steps overall (the brain never took damage at
  all) cannot ground anything: `p_base` would be 0 and EVERY claimed threat would trivially clear "rate >
  base + margin" the moment it has even one drop-step contact, which is exactly the false-positive risk a
  zero-variation session creates (the flip side of the HUD gate's "all readings at hp=10" degenerate
  case). A session with zero drop steps scores **DEGENERATE_NO_DAMAGE** for every entity, no verdict
  computed, regardless of contact counts.
- **`MIN_TOTAL_STEPS = 10`** — same spirit as the HUD gate's `MIN_READINGS = 10`: a session with fewer
  than 10 scoreable oracle steps overall is **INSUFFICIENT_DATA** before any per-entity math runs.
- **Malformed / duplicate handling** — identical discipline to `score_gate_run.py`: reading tokens (here,
  there are no numeric readings to normalize, but `ENT`/`CONTACT`/`DECLARE`/`REJECT` lines with an
  unparseable id/region/step are counted as malformed and reported, never silently dropped); repeated
  `(id, step)` `CONTACT` encodings dedupe, first occurrence wins, repeats counted and reported (never
  double-counted toward `|C_k|`).
- **Unmatched steps** — a `CONTACT`/`ENT` line whose step has no oracle row is UNMATCHED, excluded from
  the metric, and reported; **`UNMATCHED_MAX_FRACTION = 0.05`** (same number, same rationale, as the HUD
  gate) — too many unmatched steps (would-be-gameable by dropping inconvenient contacts) refuses a
  verdict entirely (`INSUFFICIENT_DATA`).

### Tightening amendment (2026-07-03, sev-1 review on PR #59 — stricter, never looser): retroactive CONTACTs

The as-first-pinned metric had a hole: nothing checked WHEN a `CONTACT id=k step=n` was logged relative
to when the brain could have learned step `n`'s hp outcome. A brain that feels the hit first (observes
its life fall) can retroactively tag CONTACTs onto exactly the drop steps for its chosen "threat" id
(`p_k = 1.0` trivially) and never tag the benign id on a drop step — both arms faked by post-hoc
outcome-matching with zero predictive grounding. The HUD gate's `HYP` lines never had this hole because
each reading is tethered to the `read_region` result it was copied from; `CONTACT` needed an equivalent
ordering tether. Pinned fix (scorer-enforced, per the project's own PR #56 lesson that unenforced
protocol discipline gets gamed):

- **Reveal rule (exact):** the scorer walks the transcript in order, maintaining a *revealed-step
  watermark* = the highest world step any `observe`/`read_region`/`whats_changed` tool-result has
  reported so far. A `CONTACT id=k step=n` counts ONLY if, at its transcript position, the watermark is
  `<= n` (strictly-greater ⇒ RETROACTIVE). The result that reports step `n` itself is allowed — it is
  what gives the brain the step number to log at all; but once any LATER-step observation has arrived,
  the brain has had the opportunity to see step `n`'s consequence, and a contact logged after that is a
  post-hoc claim, not a predictive one.
- Retroactive contacts are counted, reported, and excluded from `C_k`; **`RETROACTIVE_MAX_FRACTION =
  0.20`** — retroactive lines at/above 20% of all CONTACT lines taint the whole contact log
  (`INSUFFICIENT_DATA`, no verdict), same shape as the malformed-fraction guard.
- **Residual leak, documented deliberately:** a `read_region` pointed at the HUD *within* step `n`'s own
  window could reveal hp before the CONTACT is logged. The scorer cannot know which pixel boxes carry hp,
  so this is closed belt-and-braces: the launcher brief mandates contact-first, hp-blind logging order
  (log the CONTACT the moment adjacency/attack animation is seen, BEFORE any further look), and a
  reviewer can audit the transcript for a same-window HUD read preceding a CONTACT. The strictly-greater
  rule closes the cheap mechanical exploit (observe outcomes later, back-tag earlier steps).

### Why an absolute margin instead of a formal significance test

A binomial/Fisher exact test was considered and rejected for this pass: (1) it needs a dependency
(`scipy`) this project doesn't otherwise use for scoring math — `score_gate_run.py` and
`score_hud_grounding.py` are both stdlib-only, and this mirrors that; (2) with `MIN_CONTACTS = 3` the
sample sizes are tiny, where a p-value is unstable and easy to satisfy by chance in either direction —
an absolute-margin-over-base-rate is coarser but transparent, directly inspectable by a reviewer, and
"pick the metric, hold the unit, let it fail" (SS11) favors a number a human can sanity-check over a
statistical test whose behavior at n=3 is itself questionable. This can be revisited (e.g. a proper exact
test) only as a **stricter** replacement post-PASS, never loosened.

## What PASS/FAIL means for ADR-002's entities generalization

**PASS** = behaviour CAN ground a brain-hypothesized entity-threat ontology (not just a HUD/life scalar):
the same hypothesize→ground loop that grounded "region R = my life" also grounds "entity K = a threat" and
correctly rejects a decoy entity-claim. This is direct evidence the ADR-002 loop is not a one-trick
HUD-specific mechanism — it generalizes to a structurally different kind of claim (a discrete, moving,
identity-bearing thing vs. a fixed scalar-bearing region).

**FAIL** = the loop grounds HUD/life claims but not entity claims — the generalization does NOT hold as
stated; ADR-002's entities extension would need rethinking (a different signal than raw contact/hp-drop
correlation, e.g. requiring the brain to also use `read_region`'s appearance to disambiguate, or a richer
contact signal than "adjacent this step") before another paid attempt.

**DEGENERATE_NO_DAMAGE / INSUFFICIENT_DATA** = the run cannot settle the question either way (same
posture as the HUD gate's own degenerate/insufficient outcomes) — re-run under the SAME pinned bar, do not
loosen it to manufacture a verdict.

## Build (this pass, free/offline only)

- `eval/score_entity_gate.py` — parser (`ENT`/`CONTACT`/`DECLARE`/`REJECT`) + the scorer above, mirroring
  `eval/score_gate_run.py`'s structure (same dedupe/malformed/unmatched discipline, same exact-step
  alignment, same PASS/FAIL/DEGENERATE/INSUFFICIENT_DATA verdict shape).
- `tests/test_score_entity_gate.py` — synthetic-fixture unit tests: parser extraction, PASS/FAIL,
  DEGENERATE_NO_DAMAGE, INSUFFICIENT_DATA (too few contacts, too few steps, too many unmatched/malformed),
  dedupe, the margin math at the boundary.
- `runs/brain_cn_entity/` — a NEW launcher dir, copying `runs/brain_cn_gate/`'s pattern: `.mcp.json`
  (same `cave-noire-gate` MCP server, its own `--out runs/brain_cn_entity/world`), `CLAUDE.md` (region-
  neutral AND entity-neutral brief — never says which on-screen sprite is dangerous; tells the brain the
  evidential minimums: `MIN_CONTACTS`, need >=1 threat AND >=1 benign/rejected claim, session must include
  actual damage), `run.sh` (account-B pattern, `timeout 1500`).

## Guardrails held

`core/contracts.py` untouched; no brain edits; oracle only ever read from `world/oracle.jsonl`; no new
world/perception code (verdict above); no new dependencies; threshold pinned in this report AND in the
scorer module docstring before any paid run; stricter-only from here.
