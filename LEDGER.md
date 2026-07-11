# Ledger — MKDS continuous-time A/B: $0 launch-surface prep (ai-pokemon-red)

<!-- SCOPE SPLIT: CURRENT-RUN task state ONLY. Cross-session narrative → HANDOFF.md. Prior run
     (entity-gate v4, CLOSED (c) 2026-07-11) is fully banked in HANDOFF + reports/2026-07-11-entity-v4-verdict.md. -->

## Goal
Get the pre-registered MKDS continuous-time A/B (reports/2026-07-04-mkds-continuous-time-build-plan.md §7)
to launch-ready with $0, then STOP: the paid run itself needs David's explicit go + cost/agent-count
heads-up (pre-reg §7 — this overrides the general account-B pre-authorization).

## Handoff
- Lane state (scout, 2026-07-11): #100 build MERGED + verified (NDS_SKILLS tools, enum pinned IN CODE:
  elapsed_frames ≤ F=300; idle_settled threshold∈(0.005,0.06), k≥1, k*s≤F with s=4, max_iters=8; 98 tests
  pass fresh). Idle pre-check DONE (runs/nds3d_probe/idle_measurement.md, band [0.5%,6%] clean).
  ⚠ plan doc §4 says s=24/k=10 — STALE, code (s=4) is authoritative (world_mcp.py:749).
- 3 gaps found → 2 agents in flight: (A) lap/checkpoint RAM oracle hunt (offline, verify-against-run
  mandatory — Cave Noire 0xD389 lesson); (B) launch surface: Docker image rebuild (both tags stale —
  latest predates the whole NDS build!), runs/brain_mkds_armA|armB/ launchers+briefs (blank-wipe lines,
  --max-turns 90, Arm A never sees skill tools or the bar), seamcheck.sh 3 assertions vs fresh image.
- Entity v4: CLOSED (c). #102 open, merge gate satisfied, awaits David (still merge-worthy: v5 instrument).

## Constraints
- NO paid run without David's explicit go (pre-reg §7). NO oracle/RAM on the wire. Arm A/B isolation
  (NDS_SKILLS flag). Blank-agent wipe. One attempt per arm. Bar pinned: ≥1.3x frames-per-decision AND
  ≥1 qualifying-conditional (stop_when fires before F/max_iters).
- Do not edit merged world code; launch surface = new files only.

## Tasks
- [x] scout lane state → gaps mapped (evidence above)
- [ ] (agent A) MKDS lap/checkpoint oracle: FOUND+verified / NOT FOUND → report
- [ ] (agent B) Docker rebuild + brain_mkds_armA|armB launchers/briefs + seamcheck 3/3 PASS → report
- [ ] commit launch surface + reports on feat branch (or fresh branch if cleaner) + PR? (small, review-light:
      launchers are runs/ scripts — check whether runs/ launchers historically went through PRs)
- [ ] update HANDOFF + hand David the go/no-go package (cost estimate, agent count, oracle status)
- [ ] (DAVID) explicit go → launch discipline: Arm A first, --max-turns 90, account-B, banked as-is
