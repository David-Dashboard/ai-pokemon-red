# Ledger — entity-gate v4 (structured claims) — build-signoff gate (ai-pokemon-red)

<!-- SCOPE SPLIT: CURRENT-RUN task state ONLY. Cross-session narrative → HANDOFF.md. Ledger hooks
     re-inject this after compaction + gate the Stop; keep it short, current, truthful. -->

## Goal
Fix the entity-grounding gate FULLY (David: "commit"), v4-scale. The `entity-v4-design` workflow
(17 agents, ~2.15M tok) is DONE. Now: get David's sign-off on the v4 design → build the infra →
gate the paid spend behind $0 checks → (if green) one paid run → verdict.

## Handoff (update before every stop)
- State: workflow COMPLETE → distilled into the durable build spec `reports/2026-07-05-entity-v4-design.md`
  (READ THAT FIRST to build). (Raw workflow result was tasks/w0gk1gl7f.output, session-scoped, won't survive a clean.) Verdict:
  v4 DESIGN SOUND; red-team caught 2 KILLERS (both the step-stamping trap → server-stamping `step` kills
  the retroactive guard + breaks byte-identical bar; reproduced a PASS→INSUFFICIENT_DATA flip). FIX folded:
  claim_near(id, step)=BRAIN-supplied step + SEPARATE server-stamped `revealed_at` (from _obs_count, seam-
  clean). Design = 4 typed claim tools (claim_entity/claim_near/declare/reject) + note_reading audit tool →
  world/claims.jsonl; new eval/score_entity_gate_v4.py imports v3 math BYTE-IDENTICAL, swaps only the parser;
  KIRBY_CLAIMS-gated; ZERO frozen-code touch. BIG TRUTH: v4 fixes only 1 of FOUR barriers (green scorer ≠
  green gate; we've never seen the bar's verdict on real behavior).
- FOUR barriers: (1) instrumentation → v4 fixes it. (2) camping (b_k) → brief-only, tractable (ceiling easily
  clearable). (3) (d) predicate → CONDITIONAL GO: stationary step-up ledge is a real wall (enemies die on
  contact → can't be), but UNPROVEN in kirby_entity2.state + perceiver noisy → needs a $0 probe; NO-GO there
  = no PASS. (4) NEW margin/coverage geometry: NEARs must COVER drops (v3.1 scored margin −0.043) — ANTAGONISTIC
  with camping; co-tune in the brief.
- Next: David's calls (below) → BUILD v4 infra (orchestrated, plan→branch→Sonnet→heavy review→David merges) →
  $0 (d) probe on kirby_entity2.state (assert hp==6) + $0 paper coverage-reachability check → spend only if
  both green (likely 1 gated attempt, not 2).
- David ANSWERED (2026-07-05): Q1 = BUILD the v4 infra now (APPROVED). Q2 = decide the conditional-half
  (Kirby-v4 vs doom) AFTER the $0 (d) probe. David will COMPACT before the build begins.
  → NEXT ACTION (after a FULL context CLEAN): build the v4 infra per the DURABLE build spec
  **`reports/2026-07-05-entity-v4-design.md`** (repo file — survives the clean; has the full tool interface,
  scorer plan, step-semantics killer-fix, camping fix, the (d) $0-probe, and the sequence). The session file
  tasks/w0gk1gl7f.output will NOT survive a clean — do NOT rely on it. Already on branch
  feat/entity-gate-v4-structured-claims. Follow plan→branch→Sonnet→heavy adversarial review→David merges.
- ⚠ GUARDRAIL CONFLICT (PR #101's new CLAUDE.md): "Never touch … Doom during development" (held-out,
  eval-probes-and-datasets §3) contradicts HANDOFF's old NEXT #3 "doom port" + my Q2 "doom exit" option.
  If doom is truly held-out, the (d) NO-GO fallback is NOT doom — it's the pre-registered v3.2-(b)
  min_iters=3 executor floor or a non-held-out world. RESOLVE vs #101's HANDOFF before offering doom.
- Also new (CLAUDE.md #101): every gate pre-reg must NAME the capability it buys (reports/2026-07-05-
  northstar-capability-map.md); trust RUNS over docstrings/memories. Fold both into the v4 pre-reg.
- SIDE-THREAD: PR #101 (docs/skill-library — skills 10→15 + guardrails + capability map + hooks) is OPEN,
  MERGEABLE, CI green, but 0 posted adversarial reviews → NOT merge-ready per the gate. David asked me to
  check it (done). Offered a heavy adversarial review; awaiting his go. David merges.

## Constraints
- Frozen v3 scorer + v3/v3.1 data UNTOUCHED. v4 = new scorer + new tools + own pre-reg + re-run free
  pre-checks (seam changed). v4 bar math imported BYTE-IDENTICAL; the brain-supplied-step decision is what
  KEEPS it byte-identical (do NOT server-stamp step). Screen-only + oracle-off-wire hold (claims.jsonl never
  returned to brain; no oracle auto-populate).
- Spend GATED behind two $0 checks ((d) probe + coverage paper-check). (d) is a hard PASS gate. Account-B,
  blank wipe, banked as-is. Only David merges + authorizes spend.

## Decisions
- [2026-07-05] Step semantics [recommended, pending David Q1]: claim_near carries BRAIN-supplied `step`
  (= v3's scored quantity) + SEPARATE server-stamped `revealed_at`. Keeps retroactive guard live + bar
  byte-identical + prose-taint dead. (Server-stamping step was a red-team-proven killer.)
- [2026-07-05] Reframed as FOUR barriers (added margin/coverage geometry, antagonistic with camping).
- [2026-07-05] Include the 5th note_reading audit tool (off-wire drop/HUD belief has a typed home → last
  freeform-taint surface closed). Predicate menu: stationary-target region_changed / ledge move_blocked —
  the $0 probe settles the order.
- [2026-07-11] $0 (d) probe verdict: predicate = **move_blocked PRIMARY**; region_changed is dead in Kirby
  (whole-screen change on walk/scroll → press-1 fire in all 6 boxes). Barrier (3) = GO. Pre-reg must use
  move_blocked wording + avoid the right_third watch box.

## Tasks
- [x] entity-v4-design workflow (17 agents; design + 10 red-team lenses + synth) → v4 design + 4-barrier map
- [x] DAVID (2026-07-05): Q1 = BUILD v4 now (APPROVED); Q2 = conditional-half decided AFTER the $0 probe
- [x] build v4 infra → commit b28a735 (Sonnet-built, worktree-isolated): world_mcp.py +220 purely additive
      (5 claim tools, KIRBY_CLAIMS gate mirroring KIRBY_SKILLS, acks only, decision-uncounted, no oracle
      leak), eval/score_entity_gate_v4.py (v3 math imported unmodified, parser-only swap, fails loud w/o
      claims.jsonl), tests/test_score_entity_gate_v4.py (2 drift guards). Full suite 1073 passed 13 skipped.
      Frozen files diff-checked untouched. FLAG for review: spec line 36 omits `step` in claim_entity's
      param list but the record schema requires it — builder added step:int (matches v3 ent_claims); confirm.
- [x] $0 (d) probe on kirby_entity2.state → **GO via move_blocked PRIMARY** (reports/2026-07-05-entity-v4-d-probe.md):
      hp==6 asserted; move_blocked 4/4 directions fires at press 3-7 (never <3), all 4 pass the frozen
      v3 is_qualifying_conditional_call guard_pass=True; region_changed DEAD in Kirby (fires press 1 in
      6/6 box placements — walk anim/camera scroll, worse than design assumed); right_third box unsafe
      (6/6 idle false fires). Open brief question: move_blocked-primary vs the drop-banking path.
- [x] $0 coverage paper-check → **REACHABLE-ONLY-IF** (reports/2026-07-11-entity-v4-coverage-papercheck.md):
      scorer-verified full PASS EXISTS (q_k=1.0 b_k=0.638 threat + benign both arms) but ONLY under
      disciplined minimal-window NEARs (≤4 threat NEARs, one per drop-cluster, logged as EARLY as the
      entity is genuinely visible). Honest/natural timing FAILS the 0.70 ceiling every way tried
      (NEAR-at-drop b_k=0.710; v3.1 real NEARs b_k=0.855; span-start b_k=0.768) — forward-only windows
      [n,n+15] bleed ~15 non-drop steps per cluster. UNVERIFIED ONLY-IF condition: early visibility of
      the threat in the gate room → $0 follow-up probe in flight. Pre-reg must teach the capped
      early-NEAR discipline explicitly; geometry finding is a David flag (bar is honest-hostile).
- [x] $0 early-visibility follow-up → **PARTIAL** (reports/2026-07-11-entity-v4-visibility-probe.md):
      cluster 1 = ~8 presses honest lead (early NEAR grounded); cluster 2 = ~1 press; cluster 3 = ~0;
      threat leaves frame during retreat (early NEAR impossible until re-entry). The paper-check's PASS
      schedule is honestly groundable for cluster 1 ONLY → the ≤4-early-NEARs discipline is at real risk
      on kirby_entity2.state. SPEND PICTURE: instrumentation GO (pending #102 review fixes) + predicate
      GO, but coverage geometry honest-hostile + thin visibility → PASS probability LOW on this savestate.
      DAVID DECISION before any spend: (a) hunt a better room/savestate (slower/ranged enemies = wider
      visibility windows, $0), (b) attempt anyway eyes-open, (c) bank the geometry finding as the verdict.
- [ ] v4 pre-reg (4 levers: instrumentation/camping/predicate/coverage) + PR + heavy adversarial review + triage
- [ ] (David) 1 gated paid attempt → verdict
