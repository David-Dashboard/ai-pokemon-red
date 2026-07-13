# Ledger - MKDS continuous-time A/B verdict banked (ai-pokemon-red)

<!-- SCOPE SPLIT: CURRENT-RUN task state ONLY. Cross-session narrative → HANDOFF.md. Prior run
     (entity-gate v4, CLOSED (c) 2026-07-11) is fully banked in HANDOFF + reports/2026-07-11-entity-v4-verdict.md. -->

## Goal
Bank the pre-registered MKDS continuous-time A/B
(`reports/2026-07-04-mkds-continuous-time-build-plan.md` section 7) after David's explicit paid-run go
and default `~/.claude` fallback authorization. Current next work is the v5 entity-bar redesign design doc
($0, no code/run); no paid run is armed.

## Current status (2026-07-13)
- David gave explicit go for the paid A/B on 2026-07-13; cost/agent-count heads-up was given
  (2 agents, <=$10 planned).
- Prechecks passed: Docker image `sha256:dfd12eac87bb...`; seamcheck 3/3 PASS; no prior Arm A/B run
  artifacts existed; launch briefs did not expose RAM/oracle address.
- Arm A artifacts: `runs/brain_mkds_armA/transcript.jsonl`, `run.exit`, `run.err`.
- Arm A result: `run.exit` = `EXIT=1`; `run.err` empty; no `world/` dir; result
  `api_error_status=429`, `duration_api_ms=0`, `num_turns=1`, `total_cost_usd=0`.
- Reset text: `You've hit your weekly limit - resets Jul 16, 8pm (Europe/Stockholm)`.
- Report: `reports/2026-07-13-mkds-ab-blocked.md`.
- Next: wait until **2026-07-16 20:00 Europe/Stockholm**; then, if David still wants the A/B,
  launch Arm A first under the same discipline. Arm B is unstarted.

## Current status update (2026-07-13 default account)
- David authorized using the default `~/.claude` account/config after the account-B cap.
- Default-account A/B completed in separate dirs: `runs/brain_mkds_armA_default/` and
  `runs/brain_mkds_armB_default/`.
- Verdict: **FAIL primary batching bar**, **PASS conditional guard**.
- Arm A: 2984 oracle frames / 13 in-world decisions = 229.538 frames/decision; cost `$0.77483`.
- Arm B: 2365 oracle frames / 10 in-world decisions = 236.500 frames/decision; cost `$0.7740115`.
- Ratio: `1.030x`, below required `1.300x`.
- Arm B conditional guard: PASS (`skills.jsonl`: 10 `run_skill`, 9 `stop_when_fired=true`).
- Caveat: checkpoint RAM byte `0x022C8090` was not logged in either `oracle.jsonl`; do not claim
  RAM-confirmed checkpoint/lap progress.
- Report: `reports/2026-07-13-mkds-ab-verdict.md`.
- Next: v5 entity-bar redesign design doc ($0, no code/run).

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
- SIDE-THREAD (NEXT #4 pulled forward while MKDS awaits David): glyph R1 BUILT + gated in worktree
  ../ai-pokemon-red-glyphr1 (branch feat/glyph-r1-build off main) → **KILL at its own pinned bar**
  (precision 0.283 ≤ 0.49 kill floor; GBA anti-aliased fonts blow the glyph vocabulary 191-989 keys vs
  Gen-1's 46 → R0's collision mode returns). One attempt of 2 allowed, no tuning, detector unwired.
  PR #103 open (kill banked like R0's #52: harness+fixture = the reusable R2 bar). Review round DONE:
  code/consistency APPROVE (0 findings); verdict-audit VERDICT-STANDS (independently reproduced all gate
  numbers incl. per-game + the MD5 exclusion + the vocabulary blowup; 2 immaterial minors, e.g. excluding
  the 4/5-warm SMA2 still kills at 0.241). **#103 merge gate SATISFIED — awaits David.** Worktree removed
  (branch pushed). Suite 1089 passed. Verdict: reports/2026-07-11-glyph-r1-verdict.md.

## Constraints
- NO paid run without David's explicit go (pre-reg §7). NO oracle/RAM on the wire. Arm A/B isolation
  (NDS_SKILLS flag). Blank-agent wipe. One attempt per arm. Bar pinned: ≥1.3x frames-per-decision AND
  ≥1 qualifying-conditional (stop_when fires before F/max_iters).
- Do not edit merged world code; launch surface = new files only.

## Tasks
- [x] scout lane state → gaps mapped (evidence above)
- [x] (agent A) oracle FOUND+verified (reports/2026-07-11-mkds-oracle-hunt.md): **0x022C8090 u8, absolute,
      no pointer chase** — 0 through count-in, ticks 1→2 on confirmed forward progress, flat when stalled;
      byte-identical across 2 independent re-runs. TAS pointer chain (0x021755FC) DEAD in GP mode (TT-only,
      confirmed inert ~125s) — the verify-against-run law caught it, wiki alone would have shipped a dead
      oracle. Caveats: semantics not disassembly-confirmed; 2 ticks observed (no full blind lap); verified
      for this savestate/track only. Sufficient for the A/B (primary metric is frames-per-decision; oracle
      scores the secondary task-progress event).
- [x] (agent B) launch surface DONE (reports/2026-07-11-mkds-launch-surface.md): image rebuilt
      (sha256:dfd12eac87bb, NDS_SKILLS x16 verified in-image; stale latest replaced); seamcheck 3/3 PASS
      (NDS_SKILLS=1 → tools present / unset → absent / KIRBY_SKILLS=1 cross-flag → absent);
      runs/brain_mkds_armA|armB/ created (blank-wipe, --max-turns 90, no --record on nds — SystemExit,
      --keep-frames only). runs/ is GITIGNORED → launchers live on disk only, report is the tracked record.
      Cost estimate for the A/B: 2 agents, one attempt each, ≲$5/arm (≲$10 total).
- [x] reports committed on feat branch (runs/ launchers gitignored by convention — on-disk only, reports
      are the tracked record; no separate PR needed for gitignored launchers)
- [x] HANDOFF updated + go/no-go package handed to David (2026-07-11): READY — seam 3/3, oracle verified,
      briefs on disk, 2 agents, one attempt each, --max-turns 90, ≲$10 total
- [x] (DAVID) explicit go received 2026-07-13; Arm A launched first and blocked before MCP/world connection by account-B weekly-limit 429.

## Blocked status appended 2026-07-13
- [x] Explicit go received 2026-07-13; launch discipline used: Arm A first, --max-turns 90, account-B.
- [x] Pre-launch seamcheck re-run 2026-07-13: 3/3 PASS.
- [x] Arm A launched first; blocked before MCP/world connection by account-B weekly-limit 429; $0; not a scored A/B attempt.
- [x] Default `~/.claude` account authorized and used in separate `_default` dirs.
- [x] Arm A default completed.
- [x] Arm B default completed.
- [x] A/B verdict banked: FAIL primary bar, PASS conditional guard.
