# Cost investigation — credit exhaustion 2026-06-20 (ROOT-CAUSED)

_Triggered by: "between 9 AM and 11 AM today we exhausted all the credits."
**Status: in-depth investigation COMPLETE** (multi-agent, 2026-06-20, Ultracode). This file was a
read-only grounding doc; it has been **rewritten with the evidence-based root cause** — the first
draft's central cause (below, "Superseded") was WRONG. No fixes applied yet; solution directions at
the end. Token counts are ground truth (aria `usage.jsonl` + the 17 archived `iter-*.zip`); dollars
use **confirmed** Haiku-4.5 pricing._

## Bottom line

The ~$6 was **not** aria's reflection/memory machinery. It was the **conversation prompt itself** —
a ~13K-token prompt billed at near-full price on *every* game wake because almost none of it caches,
then *doubled* on ~60% of wakes by the agent's own `memory_recall` ReAct loop. The single biggest
chunk is aria **re-sending the harness's entire game manual (`POKEMON_SYSTEM`) ~7× per wake**.

## Hard data (aria `usage.jsonl` run #17 + all 17 archived runs)

Model behind BOTH `aria-brain` and `small-worker` = **`anthropic/claude-haiku-4-5`**
(`litellm-config.yaml`). The live `usage.jsonl` only ever holds the latest run (reset wipes it, after
archiving to `aria_memory_archives/iter-NNN_<date>.zip` — every run IS recoverable there).

**Run #17 token attribution (the clean, complete log):**

| source | calls | input tok | **% input** | avg/call | cached |
| --- | --- | --- | --- | --- | --- |
| **conversation** | 69 (4 failed) | 1,416,757 | **93.5%** | 20,533 | 34.4% |
| **aux (rolling recap)** | 58 | 97,898 | **6.5%** | 1,688 | 0% |

**Across ALL 17 archives (13.66M input tok):** conversation **92.1%**, aux **7.9%** — rock-steady.
The two stuck-in-lab runs (`iter-016` 2.52M + `iter-017` 2.84M, avg prompt 23–26K) are **61% of
today's burn**. Caching was effectively OFF most of the day (`0%` on most runs; only `iter-016/017`
reached 36–41%) → overall only **17.4%** of conversation input was ever cache-read.

## Real cost (CONFIRMED pricing)

Haiku 4.5 (Anthropic docs, fetched 2026-06-20): **$1.00/MTok in · $5.00/MTok out · $1.25/MTok 5-min
cache-write · $0.10/MTok cache-read.** (The first draft assumed $0.8/M in — real is 25% higher.)

- **Run #17 ≈ $1.21–1.33** (conversation $1.06 = $0.93 uncached + $0.05 cache-read + $0.08 output; aux $0.15).
- **Today ≈ $7–9** (~10.3M input tok: 8.83M archives + 1.5M live). "~$6" ≈ the post-top-up portion.

## Root cause — the causal chain (ranked by $)

1. **Uncached round-1 prompt — ~$0.93/run = 77% of cost.** Of run #17's 1.42M conv tokens, **929K
   billed at full $1/MTok** (only 487K were $0.10 cache-reads). That uncached 929K *is* the first full
   prompt of each wake (~13K × 65), which never caches across turns (see #3).
2. **The transcript replays the harness's whole game manual ~7× per wake (uncached).** The transcript
   block is **71% of one round (~12.7K tok)**. `prompt._transcript()` replays the last 6 journal
   exchanges verbatim, and *each stored `message` is the harness's full payload* — embedding the
   ~475-token `POKEMON_SYSTEM`. So that static manual is paid once as the live observation **+ 6× in
   the transcript**, every wake, all uncached. This is the bulk of the uncached 929K.
3. **Caching is structurally crippled for THIS agent.** `cache_control` is on `role=system` only
   (`litellm-config.yaml:17`), but the game agent's system blocks are only **~1–2K tok — below Haiku's
   4096-token minimum cacheable prefix**, so the system prefix *never caches*. The ~13K of real content
   rides in the **user message** (no `cache_control`) and churns every turn → never byte-identical →
   never cached. The only caching that happens is *intra-turn* (round-2 re-reads round-1 on tool wakes):
   0% on no-tool wakes, ~44% on tool wakes → **34.4% blended**.
4. **The "30K prompt" is half illusion — the `memory_recall` ReAct loop.** The agent's one enabled tool
   fires on **42/69 wakes**, each forcing a 2nd model round that re-sends the whole prompt (usage is
   bimodal 14K/28K = exactly 1.99×). It inflates the token *count* but costs little in $ (the 2nd round
   is the cached part). Real money is still the uncached round-1.
5. **aux/reflection — a red herring.** ~8% of tokens across all runs (~$0.15/run). ~1 call/wake (the
   `recap.earlier_today_summary` rolling recap) but each is tiny (~1.7K). `reflection.py` is offline/cron
   (digests only *past* days) — it does NOT fire per-turn.

## Why the v0.26.0 cache solution delivers 34% here, not the measured ~80%

**It IS active** — ai-aria's game branch `pokemon-red-constitution` forked from main *at the
prompt-caching merge* `6a268b1` (PR #27); `e641741` (v1 byte-stable system) + `651f311` (v2 2nd
breakpoint) are in the branch; the live config has `cache_control_injection_points`. **The branch is
NOT rebased on main** (8 behind = v0.26.1 MCP + v0.26.2 turn-deadline, *no newer caching*; 9 ahead =
the constitution). Rebasing would NOT help caching.

The solution was designed + measured (~80%) for the **companion** prompt shape: a LARGE stable system
prefix (persona + accumulated core_memory/lessons, well over 4096 tok) and a SMALL per-turn user
message. The **game agent inverts that**: a near-empty post-reset memory → tiny ~1–2K system prefix
(below the 4096 floor → cache never even writes), and a huge volatile user message (the 6× game-manual
transcript). So the cacheable slot is too small to cross the floor while the big, stable content sits
in the uncacheable slot. **Correct mechanism, wrong calibration for an inverted prompt.**

## Corrections to the first draft (now known-wrong)

1. ~~"Aux roughly DOUBLES the calls / ~half of every run's spend is machinery."~~ **FALSE.** Half the
   *calls*, but **~8% of tokens / ~13% of cost**. aux is not the driver.
2. ~~"Same ballooning almost certainly caused run #17's `invalid_request` halt."~~ **FALSE.** The
   journal shows the literal 400: *"Your credit balance is too low to access the Anthropic API."* It's
   non-retryable, so `num_retries:3` did NOT amplify; the harness circuit-breaker
   (`API_ERROR_CIRCUIT_BREAKER=4`) halted cleanly after 4 failures. The failures cost **~0 tokens**.
3. Images are NOT implicated — runs #13–#17 ran `--no-vision`; a frame is ~31 tok anyway. Bloat is 100% text.
4. One investigator disagreement resolved: `memory_recall` fires on ~60% of wakes (direct bimodal +
   journal-histogram evidence), NOT "rarely" — but its *retrieval* is local (no extra Anthropic call);
   the cost is the 2nd model round it triggers.

## Solution directions (identified; not yet built — for the design discussion)

**Aria-side (restores the cache + kills the duplication — biggest wins; David's repo):**
- **Send `POKEMON_SYSTEM` as a SYSTEM message, not inside the user turn.** The harness currently sends
  ONE user message, 0 system messages (`core/brains.py:452`); aria wraps it. Riding the system role
  would (a) let the existing `cache_control` catch the manual and (b) lift the cacheable prefix over the
  4096 floor → the v0.26.0 solution starts working as designed.
- **Stop journaling/replaying the static manual.** The harness stores its full payload in aria's
  `journal.message`, so the transcript replays the manual 6×. Logging only the state *delta* would cut
  ~7K tok/wake.
- **Disable `memory_recall` for the game agent** (near-empty memory to recall; it's the only enabled
  tool) → removes the 2nd ReAct round on ~60% of wakes.

**Harness-side (this repo — protective, the standing precondition):**
- A prompt-token / estimated-spend circuit-breaker + a hard "stuck-N-wakes" halt + per-call
  `prompt_tokens` logged to the console. Would have stopped the 30K-prompt runs early and pre-empted the
  credit-out. **No paid runs until this is in.**

## Status

Root-caused; **no fixes applied.** Token counts ground-truth; pricing confirmed; cache underperformance
explained (inverted prompt shape, solution active but miscalibrated). Solution directions above await the
design discussion.

<!-- Superseded first-draft cause (kept for the record): "aux ≈ half the spend" + "ballooning caused
the invalid_request". Both disproven above. -->
