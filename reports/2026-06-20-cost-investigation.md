# Cost investigation — credit exhaustion 2026-06-20 (GROUNDING for the in-depth dive)

_Read-only investigation triggered by: "between 9 AM and 11 AM today we exhausted all the credits."
This captures the HARD DATA + the causes found so far, and scopes the in-depth (Ultracode, post-compaction)
investigation so it starts grounded. No code changed; no fixes applied yet._

## Hard data (from aria's `usage.jsonl`, the per-call token log)

Model behind `aria-brain` (litellm-config.yaml): **`anthropic/claude-haiku-4-5`** (also `small-worker` +
`aria-brain-fallback`). Archives hold the PREVIOUS run's usage (reset archives-then-wipes); `usage.jsonl`
current = run #17.

| run | conv calls | **aux calls** | prompt_tokens | completion | ~cost* |
| --- | --- | --- | --- | --- | --- |
| #12 | 51 | 44 | 510,185 | 11,533 | $0.45 |
| #13 | 73 | 66 | 675,781 | 10,723 | $0.58 |
| #14 | 22 | 15 | 203,693 | 3,161 | $0.18 (hit zero ~10:40) |
| #15 | 80 | 9 | 161,295 | 2,490 | $0.14 |
| #16 | 103 | **96** | **2,517,992** | 46,894 | $2.20 |
| #17 (in archive) | 101 | **94** | **2,835,305** | 37,396 | $2.42 |
| #17 (current log) | 69 | 58 | 1,514,655 | 26,900 | $1.32 |
| **TODAY TOTAL** | | | **8,418,906** | **139,097** | **~$7.3*** |

*Cost is a ROUGH estimate at assumed Haiku rates ($0.8/M in, $4/M out) — **the exact Haiku-4.5 price must
be verified in the deep dive**; the TOKEN counts are ground truth. At a higher real price this is ~$8–10.

- Run #17 average prompt: **11,926 tokens/call**; largest prompts **~30,000 tokens**; cached **~32%**.
- Timezone: `usage.jsonl` ts are UTC; archive mtimes are local (CEST, UTC+2). The user's **9–11 AM local
  window = runs #13–#14**; **run #14 drained the first balance to zero ~10:40** (the documented
  "credit balance too low"). After a top-up, the afternoon runs **#15–#17 burned the bulk (~$6)**.

## Causes found (preliminary — to be confirmed in depth)

1. **Aria roughly DOUBLES the calls with internal overhead.** ~1 `aux` call per `conversation` call
   (run #16: 103 conv + 96 aux). `aux` = aria's memory system (reflection / digest / retrieval re-rank via
   the `small-worker` Haiku model — see `memory.yaml`: episodic digests, notes archiving, hybrid retrieval).
   ~Half of every run's spend is machinery unrelated to choosing a button.
2. **Prompts BALLOON to ~30K tokens (avg ~12–14K), only ~32% cached.** Aria injects its growing memory +
   the large recall seed (`goals.md`/`core_memory.md`/`lessons.md`) every turn; context grows with run
   length. The **stuck-in-the-lab runs (#16/#17) were the worst** (long run → huge context → 2.5–2.8M tokens
   each). Same ballooning almost certainly caused run #17's `invalid_request` halt.
3. **Caching is mostly OFF (~32%)** — a long-standing known issue; most input is re-sent every call.

## Open questions for the IN-DEPTH (Ultracode) investigation

- **Exact $:** confirm Haiku-4.5 pricing and compute real spend per run + today total.
- **`aux` calls:** what precisely are they (reflection cadence, retrieval re-rank, digest)? Can they be
  throttled/disabled for game runs without breaking play? Quantify their share of tokens (not just calls).
- **Prompt ballooning:** decompose a 30K prompt — how much is the recall seed, how much aria's growing
  memory (episodic/journal/notes), how much the harness transcript/lessons? Where's the cap that should exist?
- **Caching:** WHY only 32%? (Is the changing observation/context busting the cacheable prefix? Is caching
  configured at all for this litellm path?) Full caching is a ~3–4× input-cost lever.
- **`invalid_request`:** exact cause (prompt size limit? malformed message? empty content?) — reproduce.
- **Runaway check:** confirm aux/retries don't scale super-linearly (they looked ~1:1, not exponential).

## Levers (to design in the deep dive)

**Harness-side (this repo — protective, low-risk):** a cost/prompt-size circuit-breaker (halt on a token or
estimated-spend cap; would've stopped the 30K-prompt runs early and pre-empted `invalid_request`); lower
default `--max-llm-calls`; treat "stuck N wakes" as a hard halt (stuck runs were the costliest); log
per-call prompt_tokens to the run console for visibility.

**Aria-side (the brain repo — the big wins, David's call):** throttle/disable reflection (`aux`) during game
runs (~halves tokens); cap injected context + trim the recall seed (kills the 30K prompts); turn on prompt
caching (~3–4× input cost).

## Status

NO fixes applied — read-only. **Recommendation: no more paid runs until at least the harness cost-breaker
is in.** The in-depth multi-agent investigation (read aria's reflection + retrieval + caching paths, decompose
a real 30K prompt, confirm pricing, propose concrete fixes) runs post-compaction with Ultracode on.
