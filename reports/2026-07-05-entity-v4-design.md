# Entity-gate v4 — design of record + build spec (2026-07-05)

**Status:** design DONE (adversarially validated by the `entity-v4-design` workflow, 17 agents, 10 red-team
lenses). David APPROVED building the v4 infra (2026-07-05). This doc is the durable build spec — a fresh
instance (post full context clean) builds from THIS file + `LEDGER.md`. Branch: `feat/entity-gate-v4-structured-claims`.

## Why v4 exists (the one-paragraph version)
The entity-grounding gate has an LLM "brain" play Kirby and prove it can tell THREATS from BENIGN things.
Today the brain states claims as freeform text (`remember "NEAR id=1 step=2"`) and the frozen scorer
`eval/score_entity_gate_v3.py` scrapes that text with brittle regexes + a one-bucket-per-lesson if/elif
chain (`parse_transcript` ~340-393). That parser has FOUR failure modes and it killed BOTH prior paid runs
(v3 $4.32, v3.1 $5.19) BEFORE the bar was ever computed — **we have literally never observed the bar's
verdict on real behavior.** v4 replaces the *input pipe*: the brain calls STRUCTURED claim tools that write
typed records to a log; the v4 scorer reads DATA, not prose. Same bar math, reliable ingestion.

## THE BIG TRUTH — v4 fixes 1 of FOUR barriers (green scorer ≠ green gate)
Do not mistake "the scorer is now clean" for "the gate will pass." Four independent barriers:
1. **Instrumentation** → v4 fixes it structurally (this doc).
2. **Camping** (b_k > 0.70) → brief-only, tractable (see §Camping).
3. **(d) conditional predicate** → CONDITIONAL GO, needs a $0 probe on the RIGHT room (see §(d)). **If the
   probe is NO-GO, the gate cannot PASS regardless of v4.** Hard gate.
4. **Margin/coverage geometry** (NEW) → v3.1's real NEAR set scored margin −0.043 (fails q_k−b_k≥0.15).
   NEARs must be placed *covering drops*, which is **antagonistic** with camping. Brief lever; co-tune.

## Barrier 1 — the fix: structured claim tools + a v4 scorer

### Tool interface (add to the Kirby `kirby-gate` MCP surface in `world_mcp.py`)
Gate ALL of these behind a new **`KIRBY_CLAIMS`** env flag (sibling of `KIRBY_SKILLS`, for A/B arm
isolation). Wire at BOTH `tools()` (~world_mcp.py:901) AND `_static_tools` (~761) so `tools/list` cannot
drift. Put them on the decision-UNCOUNTED path (a claim is not a "wake"), clone the `remember` dispatch
(~world_mcp.py:1666-1672): bare `"Noted"` ack + the normal trailing observe, and **NO hp/drop/correctness
echo** (screen-only / oracle-off-the-wire). Each call appends ONE JSON record to `world/claims.jsonl`
(append-only sibling of `oracle.jsonl`/`skills.jsonl`, cloning the `_log_skill` pattern ~1046-1055).
**`world/claims.jsonl` is NEVER returned to the brain.**

    claim_entity(id:int, x0:int,y0:int,x1:int,y1:int, step:int, kind:'threat'|'benign')
        [amended 2026-07-11 post-review: `step:int` was omitted from this signature line but is a
        required tool-schema field and required record key below (R1 finding, PR #102) -- confirmed
        correct in the build, this line was just stale/incomplete]
        -> {event:'claim_entity', id, region:[x0,y0,x1,y1], step:<BRAIN-supplied>, revealed_at:<server _obs_count>, kind}
    claim_near(id:int, step:int)                      # THE load-bearing tool
        -> {event:'claim_near', id, step:<BRAIN-supplied>, revealed_at:<server _obs_count>}
    declare(id:int, kind:'threat'|'benign')           # exactly ONE verdict per call
        -> {event:'declare', id, kind}
    reject(id:int, reason:str)                        # reason is its own field, NEVER re-scanned
        -> {event:'reject', id, reason}
    note_reading(step:int, hud_life:int|null, drop_believed:bool, text:str)   # 5th tool, AUDIT-ONLY
        -> {event:'note_reading', ...}   # EXCLUDED from parse_claims' scored dispatch

`note_reading` gives the brain's off-wire HUD/drop belief a typed home so it never spills into freeform
prose (the surface that produced v3.1's taint); it also makes the brain's drop-count auditable (v3.1's was
WRONG: wrote DROP#1@step=11, oracle drop=7). ~10 LOC, scored-excluded.

### STEP SEMANTICS — the load-bearing decision (red-team caught a killer here; do NOT get this wrong)
`claim_near`/`claim_entity` carry TWO fields:
- **`step` = BRAIN-SUPPLIED** — the `read_region`/`whats_changed` frame token the brain is asserting the
  entity was near. This is IDENTICAL to how v3 works today (wire-legal; the brain already copies this token
  from tool results, world_mcp.py:1036). It is the SCORED quantity feeding dedupe/matched/macro-interior/
  coverage.
- **`revealed_at` = SERVER-STAMPED `_obs_count`** at call time (NEW value; `_obs_count` is the only
  reveal-ish counter that exists — there is NO pre-existing watermark, grep-confirmed).
- v4 retroactive test is then the **byte-identical** `revealed_at > step` (v3:361), and stays LIVE.

**DO NOT server-stamp `step := _obs_count`.** The red-team PROVED this is a killer: (a) `x > x` makes the
retroactive guard DEAD CODE, and (b) `_obs_count` increments on trailing observes, so two honest claims about
ONE frame get DIFFERENT steps → dedupe/coverage/macro-interior change → the bar is NOT byte-identical in
RESULT (reproduced a clean PASS→INSUFFICIENT_DATA flip, b_k 0.685→0.766). Brain-supplied `step` keeps prose-
taint dead anyway (a tool call is not scanned prose). OPTIONAL hardening: the tool rejects a `step` that
isn't the current wire-legal frame token the brain was just shown (arg-vs-wire compare — NOT oracle truth).

### The v4 scorer — `eval/score_entity_gate_v4.py` (NEW FILE; frozen v3 + v3/v3.1 data UNTOUCHED)
- **REUSED BYTE-IDENTICAL (import from v3, never re-type — the import also re-fires v3's import-time
  `_assert_bar_is_satisfiable_for_all_scoreable_b_k`):** every constant (`WINDOW=15, MIN_NEAR=3,
  MIN_SESSION_DROPS=5, MIN_TOTAL_STEPS=30`, all `*_MAX_FRACTION`, `Q_K_FLOOR=0.80, MARGIN=0.15,
  B_K_CEILING=0.70, QUALIFYING_MIN_*`) and every math/guard fn (`_bcd, load_jsonl, _oracle_hp_by_step,
  _drop_steps, macro_spans, _is_macro_interior, _coverage, _grounded, skill_guard,
  is_qualifying_conditional_call, _fired_real_predicate, _repeat_until_records`).
- **NEW code (the only new logic):**
  1. `parse_claims(claims, oracle, skills)` ~40 lines — dispatch on `record['event']`, read the already-typed
     integer fields, NO regex / NO if-elif chain. Emit the byte-identical 11-key parsed dict `score()`
     consumes (see v3:460-466). Apply the SAME imported `_is_macro_interior` + `macro_spans` + `(id,step)`
     dedupe + `revealed_at > step` retroactive test. `malformed` is HARD-ZERO by construction (out-of-enum /
     short args are rejected at TOOL time and never written); keep `MALFORMED_MAX_FRACTION` imported-but-
     unreachable.
  2. `score()`/`main()` reads `<dir>/world/claims.jsonl` and **FAILS LOUD if absent** (explicit "no
     claims.jsonl" — NEVER score an empty file as NO_DECLARE).
- **UNAVOIDABLE DUPLICATION (do NOT gloss it):** because v3's `score()` calls `parse_transcript` internally
  (~v3:460), v4's `score()` must **COPY v3.score()'s body from ~460 down VERBATIM**, swapping only the parse
  call. Do NOT refactor v3 into a shared helper — that edits the frozen file (hard-constraint violation).
- **MANDATORY drift-guard tests** (new `tests/test_score_entity_gate_v4.py`): (1) build one shared synthetic
  PARSED dict; assert v3's imported downstream and v4.score produce an IDENTICAL verdict. (2) feed a late
  `claim_near` (brain `step` < server `revealed_at`); assert v4 counts it retroactive exactly as v3 would
  (this is the drift-guard for the step-semantics decision).

### Why this kills all 4 instrumentation modes (by construction)
- taint / malformed / bundling / silent-loss all had one root: "one free-text string scanned by regex, one
  bucket per lesson." Structured tools make one claim = one typed record; prose is never scored; a `declare`
  call can't hide a second claim; a missing field is rejected at the tool, never mis-ingested.

## Barrier 2 — camping (brief-only; drop the mechanical floor)
b_k ≤ 0.70 is trivially clearable (5,760 distinct 3-NEAR placements clear the FULL bar on v3.1's oracle;
e.g. `{28,32,70}` → q_k=0.80, b_k=0.314, margin=0.486). Camping is NOT the hard part. Fix = a BRIEF change
(more retreat / one approach per cycle). The proposed mechanical `MIN_AWAY_STEPS~15` floor is REDUNDANT
(b_k≤0.70 already forces uncovered≥21>15) — ship it only as a clearer INSUFFICIENT_DATA diagnostic string,
never as a second threshold, never in the frozen bar math.
**GUARD-RAIL:** both prior runs banked EXACTLY 5 drops = `MIN_SESSION_DROPS` with zero slack, and drops are
contact-driven (a function of oracle HP, independent of NEAR count). The retreat lever must NOT cost a
contact. Brief line: *"banking ≥5 drops is the priority — take the contact if gap discipline would cost a drop."*
(Note: the camping analyst's headline examples were WRONG — `{5,25,72}`→q_k=0.60 FAILS; use verified-passing
targets like `{7,28,47,70}` → q_k=1.0, b_k=0.70, margin=0.30.)

## Barrier 3 — (d) conditional predicate: CONDITIONAL GO, gated on a $0 probe
- region_changed fires press-1 vs converging enemies (CONFIRMED, both runs' skills.jsonl). Enemies are ruled
  out (die on contact → never a durable wall). The step-up ledge IS a real stationary wall (Kirby X pinned
  108 samples in `runs/kirby_probe/kirby_walklog.txt`, no auto-mount) → move_blocked CAN seal at
  `WALL_CONFIRM=3`, but only from a fresh gap, and the gate-room perceiver is NOISY (blocked fires erratically
  at 1-2 presses). The only on-disk `guard_pass=True` was on `kirby_entity.state` (HP=5) — a DIFFERENT,
  cleaner room than the gate room `kirby_entity2.state` (HP=6). So there is ZERO verified qualifying-conditional
  in the actual gate room today.
- **PREDICATE MENU:** make **region_changed on a box AHEAD of Kirby toward the STATIONARY step-up/arch the
  PRIMARY** (no history-sensitivity, cannot be pre-consumed, zero machinery change); **move_blocked the
  fallback.** (The (d) analyst preferred move_blocked-primary; the probe settles the order.)
- **THE $0 PROBE (do BEFORE any spend, ~30-45 min, no API/quota):** reuse the PyBoy+World executor exactly as
  `eval/score_kirby_skill_precheck.py::check_seam_physics` does; `init_state=runs/kirby_entity2.state`
  (ASSERT `watch.hp==6` at step 1 so it cannot silently run the wrong room); score every record with the
  frozen `is_qualifying_conditional_call`. **GO only if** some predicate reaches `iterations>=2` AND
  `executed_step_count>=3` AND `guard_pass=True` in `kirby_entity2.state` AND is compatible with the drop-
  banking path. **NO-GO → do NOT spend** → route to the pre-registered **v3.2-(b) `min_iters=3` executor
  floor** (stricter-only machinery change, David's call). ⚠ **NOT doom** — doom is HELD-OUT per PR #101's
  CLAUDE.md / eval-probes-and-datasets §3; the older "doom exit" option is likely void (resolve vs #101).

## Sequence (David-approved shape)
1. **BUILD v4 infra now** (this doc) — 4 claim tools + `note_reading`, `score_entity_gate_v4.py`, drift-guard
   tests; `KIRBY_CLAIMS`-gated; ZERO frozen-code touch; reversible; reusable across future gates. Route:
   plan→branch→Sonnet implementer→heavy adversarial review→**David merges**. Re-run the free pre-checks (the
   seam changed: new tools).
2. **Gate the spend behind two $0 checks:** the (d) probe (above) + a $0 paper proof (frozen `_coverage`) that
   a passing coverage config is reachable under the intended brief.
3. **Spend only if BOTH green:** ONE gated paid attempt (likely 1, not the earlier "2 seeds") with a v4 brief
   carrying all four levers (structured claims / camping-retreat / proven (d) predicate / NEARs-cover-drops).
   Account-B, blank-agent wipe, banked as-is.

## Must-fold-in guardrails (from PR #101's new CLAUDE.md, 2026-07-05)
- The v4 pre-reg must NAME which capability it buys (`reports/2026-07-05-northstar-capability-map.md`).
- Trust RUNS over docstrings/comments/memories; negative claims need receipts (a docstring lied 2026-07-05).
- Doom / Crystalis / Zelda-LA / SML / F-1 are HELD-OUT — never touch during development.

## Killer findings (for the record — both FIXED by the step-semantics decision above)
Two HIGH breaks_design findings, both the same defect: server-stamping `step` kills the retroactive guard
and breaks byte-identical bar math. Fixed by brain-supplied `step` + separate server-stamped `revealed_at`.
The judge had picked the winning variant on a rationale ("a watermark the world already tracks") that was
FACTUALLY WRONG (no such watermark exists) — the red-team corrected it.

## Provenance
Full workflow synthesis (this session, may not survive a context clean): the `entity-v4-design` run,
`d['result']['synth']` + `d['result']['redteam']` (10 lenses). This doc distills it; where they differ, this
doc + the frozen scorer/source win (trust runs over prose).
