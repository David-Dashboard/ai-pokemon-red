---
name: cost-blocker
description: Paid runs are expensive — ROOT-CAUSED 2026-06-20 (uncached conversation prompt, not aux); cost-breaker needed before any paid run
metadata:
  node_type: memory
  type: project
  originSessionId: 1b436777-2031-4eb5-bd24-c03e024f92da
---

**Credits exhausted 2026-06-20.** Today ≈ **10.3M input tokens ≈ $7–9** on Haiku-4.5. ROOT-CAUSED
(multi-agent dive): full evidence in `reports/2026-06-20-cost-investigation.md`.

**Confirmed Haiku-4.5 pricing:** $1.00/MTok in · $5.00/MTok out · $0.10/MTok cache-read · $1.25/MTok
5-min cache-write. Run #17 ≈ $1.21–1.33.

**REAL root cause (corrects my earlier WRONG note "aux ≈ half the spend"):** the cost is the
**conversation prompt**, ~92% of all tokens across all 17 archived runs (aux/reflection is only ~8% —
numerous but tiny; `reflection.py` is offline/cron, the per-turn aux is just the `earlier_today`
rolling recap). The conversation prompt is ~13K tok/wake, **only 34% cached**, so ~929K tok/run bill at
full $1/MTok. Drivers: (1) the transcript replays the harness's **`POKEMON_SYSTEM` game manual ~7×/wake**,
uncached (`prompt._transcript` replays 6 journal msgs, each = the harness's full payload); (2) caching is
crippled because the game agent's system prefix is **~1–2K tok — below Haiku's 4096-token cache floor**,
while the big stable content rides the **uncacheable user message**; (3) `memory_recall` ReAct loop
doubles ~60% of wakes (inflates token count, cheap in $ — the 2nd round is the cached part).

**The `invalid_request` halt was NOT prompt size — it was literally OUT OF CREDITS** (journal 400:
"credit balance is too low"). Non-retryable; harness circuit-breaker (=4) halted cleanly; ~0 token cost.

**Cache solution status:** David's v0.26.0 prompt-caching arc (v1+v2, measured ~80% on the companion) IS
active on the game branch `pokemon-red-constitution` (forked at the caching merge `6a268b1`; live config
has `cache_control_injection_points`). ai-aria is **NOT rebased on main** (8 behind = MCP+turn-deadline,
no newer caching; 9 ahead). It yields 34% not ~80% because the game agent's prompt is **INVERTED** vs the
companion (tiny cacheable prefix, huge volatile transcript). Fix direction = send `POKEMON_SYSTEM` as a
SYSTEM message (cacheable + lifts prefix over 4096) + stop replaying the manual in the transcript +
disable `memory_recall` for the game agent. See [[current-status]].

**HARD RULE: no more paid runs until a harness COST-BREAKER is in** (halt on prompt-token/spend cap;
hard "stuck N wakes" halt; log per-call prompt_tokens). Free work (perception, nav, affordance, tests)
unaffected. Aria-side changes are David's call (brain repo).
