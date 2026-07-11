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

## Tasks
- [x] entity-v4-design workflow (17 agents; design + 10 red-team lenses + synth) → v4 design + 4-barrier map
- [x] DAVID (2026-07-05): Q1 = BUILD v4 now (APPROVED); Q2 = conditional-half decided AFTER the $0 probe
- [ ] build v4 infra (4 claim tools + note_reading + score_entity_gate_v4.py + 2 drift-guard tests), KIRBY_CLAIMS-gated
- [ ] $0 (d) probe on kirby_entity2.state + $0 coverage paper-check (BOTH gate the spend)
- [ ] v4 pre-reg (4 levers: instrumentation/camping/predicate/coverage) + PR + heavy adversarial review + triage
- [ ] (David) 1 gated paid attempt → verdict
