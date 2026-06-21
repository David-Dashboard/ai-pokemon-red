# HANDOFF — ai-pokemon-red

Read this first. It is the living summary of **what we're building, where we are, and what's next.**
Deeper detail lives in `reports/` — the consolidated report, `reports/LEARNINGS.md` (the chronological
per-iteration log), and **`reports/INSIGHTS.md` (the thematic synthesis of the ideas: the perception
seam, generalization from primitives, System-2→System-1 skill compilation, the learning-boundary law).**

_Last updated: 2026-06-20._

---

## 1. Overall goal (the north star)

This is **not** about beating Pokémon. Pokémon Red is the **first probe world** for the real goal:

> Build a **simple, generalizable** agent that acts on the world — generalizing across games and
> eventually reality — that is **cheap** and works from the **screen**, not privileged state.

**The destination, sharpened (2026-06-20 planning session):** the generalizable agent is a **decoupled
dual-process system** — `ai-aria` is the **BRAIN** (owns cognition + within-run memory; *authors its own
System 1 policies*; **acts on the world through tool use**), and a **WORLD** (Pokémon here; the companion's
digital life elsewhere) exposes **coarse skill-tools**. **System 1** drives cheaply; it defers **up to
System 2** only on *necessity* (novelty / low-confidence) or *override* (a surprise preempts). Pokémon is the
*entertaining testbed* for designing this harness — **not a game to beat**. The companion deployment already
embodies this (it acts on its world via real tools); the game drifted to a text-advisor — the plan below
realigns it. **The full multi-month arc (It1 Pokémon → It5 robot, + the orthogonal small-worker track) is
pinned in [`ROADMAP.md`](ROADMAP.md).**

**⇒ The repo-boundary CONTRACT is pinned in [`ARCHITECTURE.md`](ARCHITECTURE.md) (ADR-001, 2026-06-20) — read it
and don't drift from it:** `ai-pokemon-red` = the WORLD INTERFACE + **System 1** (perception + reflexive fast
loop + the oracle); `ai-aria` = the AGENT + **System 2** (deliberate reasoning + ALL memory + identity/
constitution). They meet at ONE frozen seam (`SymbolicState` → agent; an intent → world). Research-grounded
(SwiftSage; the 3-layer reactive/deliberative robotics architecture; "Distilling System 2 into System 1";
Voyager). Only revise on an empirical surprise, as a new ADR. Other architecture detail:
`ai-aria/PROMPT_ARCHITECTURE.md` + `memory/dual-process-architecture.md` + `knowledge-export/`.

Four constraints held on purpose (they're what makes the result transfer):
- **Generalize** — find the *smallest* increments that let the *same* agent act in a *different*
  world. Avoid Pokémon-specific hacks. (The brain, **ai-aria**, is a fully decoupled HTTP service.)
- **No ROM / privileged state** — plan from the **screen**. RAM exists only as a **non-leaking
  scoring oracle** (`oracle.jsonl`); it never enters the agent's input.
- **Cheap** — minimize API calls/tokens. A free local autopilot does routine work; wake the
  expensive LLM only at decisions.
- **Learning boundary (HARD LAW — revised for β, 2026-06-20):** *across-run* learning is
  **harness/code updates ONLY** (perception, brains, detectors) — the agent starts **blank every run**
  (archive + wipe before each). *Within-run* learning now has **two homes**: **(a) harness-only signals
  the brain can't derive** — the occupancy map, `OutcomeMemory`, the disconfirm detector, the
  auto-advanced **missed-text transcript** — live in `core/`, fresh per run, injected each wake,
  discarded at run end; **(b) under a memory-owning backend** (aria, `LLMButtonBrain(owns_memory=True)`)
  the brain's **own durable memory IS the authoritative within-run store** (the `<lesson>`/`<note>`/
  `<core_update>` it authors), persisted by aria through the run and **wiped before the next run by
  `reset_aria_memory.py`**. For a **memoryless backend** (`owns_memory=False`: ollama / default /
  injected) the harness keeps its own per-run `LESSON:` buffer (re-injected each wake, discarded at run
  end). **The no-across-run-leak invariant is now LOAD-BEARING on the reset:** the paid drivers refuse to
  start a *fresh* memory-owning run on un-reset aria memory (fail-loud `is_clean` guard; override
  `--allow-dirty-memory` for a resume), and `reset_aria_memory.py` **fails hard** if its git seed-revert
  can't run or doesn't verify. *(This deliberately revises the old letter — "never use aria's durable
  memory as the within-run store" — while keeping the intent: blank every run, no lesson bleeds across.
  β was David's call; see `ai-aria/PROMPT_ARCHITECTURE.md`. The law's planned It4 expiry — across-run
  learning — is a separate, later revision.)*

The whole framework is one small loop: `perceive → recall → decide → act → observe outcome → learn`.

## 2. Current status (2026-06-21)

**⇒ LATEST (2026-06-21) — read this first; the blocks below are layered history.**

**⇒ NEWEST (2026-06-21 night) — TASK #9 cross-tileset hash test RUN + ADVERSARIALLY VERIFIED; headline
CORRECTED (branch `feat/novelty-signal`, pushed).** Ran the hash leave-one-MAP-out on the new data (8817
faced-tiles, 10 runs) — it LOOKED great (Forest novel 3.3%, no map below baseline). A **5-agent verification
workflow OVERTURNED the strong claim:** leave-one-MAP-out hid a failure because a held-out indoor map kept a
**sibling** indoor map in the store. Under the honest **leave-one-TILESET-out** (`eval/_verify_tileset.py`,
independently reproduced): town wall-recall **84.7%** ✓, route **99.5%** ✓, but **INDOOR wall-recall = 0.0% —
449/449 walls miscalled WALKABLE @ conf 0.94** (the confident-mispredict failure the hash was supposed to
avoid). **Aggregate accuracy HID it** (indoor 80.7% > 67.2% baseline, because indoor is ~70% walkable) — the
metric that matters for a navigator is **WALL-RECALL.** Root cause = an **all-zeros dHash ALIAS** (flat/low-
contrast tiles → hash 0; 82% of the miscalls; 369 exact collisions to outdoor-walkable). Confounds CLEARED:
(4,4) edge-crop negligible (0.5% mis-crop — interiors pin the player centre + pad with void), labels/split
clean (98.9% RAM-agree). **Corrected headline: strong RECURRENCE within a tileset + safe NOVELTY on a new
tileset; NO indoor cross-tileset generalisation.** Two meta-lessons: **aggregate accuracy lies for nav —
measure wall-recall**, and **hold out the whole TILESET, not one map.** **⇒ REVISED NEXT (before any CLIP):
cheap fixes — (a) flatness/void guard (near-uniform → novel/low-conf, not walkable), (b) more-discriminative
hash (intensity bits) to break the collisions; re-measure indoor wall-recall on leave-one-tileset-out. The
overlap-window CLIP / hash⊕CLIP hybrid (task #9 step 2) is GATED behind those + a wall-recall≥~50% bar.** Full
record (verification update at top): `reports/2026-06-21-tile-fingerprint-map-and-cross-tileset-capture.md`.

**⇒ (2026-06-21 eve) — DATA-CAPTURE TOOLING + FIRST CROSS-TILESET DATA (free; branch `feat/novelty-signal`,
pushed).** To close the DATA GAP (we only had ~5 early maps that SHARE a tileset, which inflated the hash's
cross-map win), built three free tools: **`play_record.py`** — a windowed PyBoy session you GUIDE, with a `Tab`
toggle that hands control to the autopilot for hands-free dense sampling (WASD layout via in-place SDL2-keymap
mutation — the user's arrow keys are dead; `C`=checkpoint `.state`; records probe-compatible frames+oracle);
**`eval/auto_race.py`** — a headless free dumb auto-player (ExploreBrain + A-mash) for parallel data-gen / racing;
**`eval/index_runs.py`** — a non-destructive chronological catalog → `runs/INDEX.md`. **DATA NOW CAPTURED:** a guided
`runs/kanto1` (**1303 steps, 15 maps incl. Viridian City + its buildings, Route 1/2, and Viridian Forest (map 51) —
a genuinely NEW tileset**; 1145 manual / 160 auto) + 3 auto-races (`race1` trapped in the lab cluster; `race2`/`race3`
reached Route 1 + Viridian, 131/177 tile-types). **⇒ NEXT = task #9: re-run leave-one-MAP-out on these NEW tilesets
+ David's overlap-window CLIP + the hash⊕CLIP hybrid (BM25-style sparse+dense) — does the hash's recurrence win HOLD
off the shared early-game tiles?** (`.venv-probe4` for the CLIP arm.) The task-#7 nav-speedup A/B (below) stands behind it.

**⇒ (2026-06-21) — TILE-FINGERPRINT `tile→function` MAP + NOVELTY GATE: BUILT + FREE-VALIDATED (task #7
done; branch `feat/novelty-signal`, unpushed; 269 tests).** Executed the converged design (the block below). New
**`core/tilemap.py`** (world-agnostic `TileFunctionMap`: a 64-bit dHash perceptual fingerprint + behaviour-labelled
`observe`/`predict` with confidence + Hamming-tolerant recurrence + `is_novel`) wired into
**`games/pokemon_red/perceiver.py`**: it OBSERVES the faced tile on every move (walk→walkable, bump→blocked, cropped
from the clean PRE-move frame) and SURFACES advisory `tile_predictions` + `novel_tiles` + `tile_types_seen` as
**additive `spatial_memory` keys** (the frozen `core/contracts.py` is untouched). **Scope = map + novelty ONLY**
(David's call): NO autopilot behaviour change, NO paid run — the navigation-speedup A/B is the deferred follow-on.
Validated FREE + deterministically via **`eval/probe_tilemap.py`** (numpy+PIL only — **needs no torch/CLIP**)
replaying recorded oracles: **the cheap hash BEATS CLIP exactly where CLIP collapsed — leave-one-MAP-out held-out
lab 81% coverage @ 84% acc vs CLIP's 26.9%** (Gen-1 indoor maps share a literal tileset, so a hash recognises
literal tile identity where CLIP's lossy embedding blurred lab-floor toward house-walls). Temporal recurrence 99.7%
coverage / 92.6% acc-when-known. **Tolerance surprise (Q7): accuracy is FLAT ~92.5% across tol 0..12** — the
residual ~7% is **intrinsic tile/function AMBIGUITY** (same pixels seen both walkable & blocked), NOT hash
collisions; default tol=6 (calibrated just above the same-cell animation spread p90=5). ⇒ appearance alone can't
perfectly determine function even within one tileset — the behavioural veto (a real bump overrides) + scene-
conditioning (Q2) are the levers. **NEXT = the navigation-speedup A/B** (use predictions in the autopilot to skip
appearance-known walls; replay/live — OPEN QUESTIONS C.4). Detail: `reports/LEARNINGS.md` (the 2026-06-21
tile-fingerprint section) + [[vision-probe-findings]].

**⇒ (prior, now BUILT — see NEWEST above) — PERCEPTION ARCHITECTURE DECISION (design session; converged +
empirically grounded). Full record: [`reports/2026-06-21-perception-architecture-decision.md`](reports/2026-06-21-perception-architecture-decision.md)
+ [`reports/2026-06-21-vision-model-probe.md`](reports/2026-06-21-vision-model-probe.md).** We probed lightweight
off-the-shelf vision (MobileCLIP/SigLIP/Florence-2/RapidOCR/YOLO) on GB frames, ran 3 adversarial reviews, and
EMPIRICALLY tested the "CLIP-embedding spatial store" idea. **Decisive result** (`eval/probe_walkability_learn.py`,
behaviour-labelled store, oracle ground truth): the store predicts walkability **97.7%** on a temporal split — BUT
that's **near-exact tile RECURRENCE (memorisation), not generalisation**: leave-one-MAP-out **collapses** (held-out
lab **26.9%, below the 74.8% baseline**; accuracy by novelty: cosine `>0.97`→~100%, `<0.90`→≈chance). **CLIP
embedding captures APPEARANCE, not FUNCTION** — recognises recurring tiles, does NOT generalise walkability to new
tilesets. **⇒ CONVERGED DESIGN** (= David's "minimal-fixed version" = the fusion review, all agree): **world model =
an ONLINE behaviour-labelled `tile→function` map the agent builds AS IT PLAYS** (walk→walkable, bump→blocked,
probe→interactable; behaviour=truth), keyed by a **cheap tile FINGERPRINT (perceptual hash/template), NOT CLIP** (a
hash matches the only thing that works — exact recurrence — deterministically + free + CI-testable; this IS the
"don't walk every cell" speedup = touch each tile-type once, recognise it everywhere). **CLIP/embedding ONLY for
NOVELTY detection** (far-from-seen → "explore"); vision = ADVISORY, never committed/vote-fused (fusion review,
23/24 real: typed-evidence PRECEDENCE not weighted-vote; walkability movement-mono-source; no frozen-contract change
— advisory rides `spatial_memory`, state in `PerceptMemory`). **OCR = template-default + RapidOCR-fallback** (David
flipped from default-RapidOCR on evidence: gen1 dialog/battle = the 90% text where the template is free + ~100%).
**BUILT (off-by-default scaffolding, NOT wired):** `vision_service.py` (Flask sidecar) + `core/vision_client.py` +
~11 `eval/` probe scripts + 2 isolated venvs. Original "Phases 2–5" plan SUPERSEDED. **DATA GAP** (David flagged):
only ~5 early-game maps exist (no cities/routes; `red_play.mp4` empty; no save-states) — can't broad-validate, but
the online-build design needs no pre-gen data. **OPEN:** store persistence across runs = a learning-boundary
revision (defer to It4). **DEFERRED:** literature deep-research (hit web session-limit; retry to ground vs
self-supervised traversability / BADGR-WayFAST / Bayesian occupancy fusion / Cradle-Voyager / SwiftSage). **The
tile-fingerprint map + novelty gate is now BUILT (see NEWEST above); the remaining NEXT is the navigation-speedup
A/B** (use the advisory predictions in the autopilot to skip appearance-known walls). See [[vision-probe-findings]].

**⇒ (prior) — the ROBUSTNESS-FIRST pivot (measured reliability, fixed the #1 gap). Branch `feat/novelty-signal`
(NOT pushed; the whole session stacks here).** Single-run "successes" were hiding poor reliability, so we measured
it: a **3-run cold batch scored 0/3 STARTER**. A **6-agent diagnosis workflow OVERTURNED my "odometry is broken"
hypothesis** (`_best_shift` is sound) → the real gap is **BEHAVIORAL: the autopilot jams a blocked move 243× with
no breaker**, plus an **add-only occupancy** (`walls` never cleared) that a cutscene poisons. **FIX (committed
`4f4878d`):** (1) a **repeated-no-move breaker** (`_NO_MOVE_STALL=8` → a STEERED `nomove_note` wake instead of
repeating the dead move) + (2) **self-correcting occupancy** (clear walls on a CONFIRMED move). **PAID-CONFIRMED:
STARTER 0/3 → 4/5** (clean A/B, same config; ≥4/5 was the target). Fix #2 is the lever (runs now cover 41-42 lab
tiles vs 5-6); run 5 reached the rival battle. **⇒ DIRECT NEXT: the bottleneck moved DOWNSTREAM** — (a) a residual
walk-to-a-ball affordance miss (fix4 wandered 42 tiles, never transacted — 1/5), (b) post-starter (no Route 1 yet:
nickname keyboard / rival battle / lab exit). Also built this session (all on `feat/novelty-signal`): the
SEEN-STATES/NOVELTY signal (Oak dialog-trap fix, paid-validated below), the no-novelty STUCK-BREAKER, and
PERCEPTION-ESCALATION (`--vision-escalation`: a strong VLM grounds a confusing screen at stuck moments — built +
path-validated, not yet shown to change a paid outcome). **Meta-lessons: measure robustness with N runs not 1;
diagnose before fixing; free-validate every fix.** Detail: `reports/LEARNINGS.md` (the ROBUSTNESS-FIRST bullet).

The **FOUNDATION is DONE +
all paid-validated** (S1 cost-breaker, S2 constitution-first, S3 β within-run-memory, **[`ARCHITECTURE.md`](ARCHITECTURE.md)
(ADR-001) = the dual-process seam**; the constitution moved into aria's config). A long cold playthrough found the
**#1 BLOCKER: the OAK STARTER-DIALOG TRAP** — auto-advance mashes A forever on the "which POKéMON?" prompt (a
textbox A can't dismiss; in Red you must walk to a ball), so the agent never gets the starter. **⇒ NOW FIXED
+ PAID-VALIDATED LIVE, branch `feat/novelty-signal`, harness-only, ~$1.77 / 3 cold runs): a
SEEN-STATES / NOVELTY signal** (David's steer; the unifying signal behind the occupancy map + OutcomeMemory +
disconfirm). Data-first confirmed the trap is a **~6-state CYCLE, not a frozen frame** (settled "which POKéMON?"
recurs 10×, pose frozen, never battle), so a 1-step "did A advance?" check fails (text changes every press). The
fix counts **VISITS** (rising-edge — a held textbox is 1 visit, a loop is separate visits, so a legit dialog is
never mistaken for a cycle) to `(state_signature, screen_text)` and at **3 visits** stops auto-advancing and
**defers UP** to aria with a **pure-fact `cycle_note`** ("you are repeating a state you have already seen…") —
**System 1 detects, System 2 decides** (no harness steering; thin nudges stay out of `core/`). `core/novelty.py`
`NoveltyMemory` + the `HybridBrain` gate; **233 tests**; the SHIPPED gate replayed over the real 463-step run
trips **26× ALL in the lab trap (first @ step 416), 0 false positives** (`eval/inspect_longloop_trap.py` asserts
it). Deferred (recorded): semantic/embedding novelty — the key-building call site is the swap point if a run
shows decode noise fragmenting exact-match. **LIVE VALIDATION (3 cold runs from `start.state`): the agent got the starter (CHARMANDER) cold in ALL 3** (the
longloop NEVER did); **run 2 FROZE and the gate fired 11× `[wake:cycle]`** → aria reasoned *"A and B both repeat —
try a direction"* → walked to the Pokéballs → starter → reached the rival battle (`in_battle=2`); run 1 (no freeze)
confirms the gate stays **quiet on a moving agent** (the pose-inclusive key fires on a *frozen* cycle only). **⇒ NEW
DOWNSTREAM BOTTLENECK (separate from the trap) = the post-starter NICKNAME-ENTRY KEYBOARD:** run 3 got the starter
then stuck **44× `[wake:mode]`** on the nickname grid, which `detect_mode` **misreads as `battle`** (the known
full-screen-bright-menu limit); the rival-battle trigger is also non-deterministic. **⇒ FIXED (BUILT + free-validated,
`e960360`): a general no-novelty STUCK-BREAKER** (the seen-states principle generalized past the dialog cycle gate —
David's call on which approach serves the thesis). Key correction caught by checking the data first: the keyboard is a
**HELD state** (44 identical frames = 1 "visit"), which the cycle gate's rising-edge counting collapses — so the right
signal is **"decisions since the last NOVEL state"** (unifies a *cycle* and a *persistence*; self-clears on a real
battle's fresh narration, so it's robust to the `battle` mislabel). At `_STUCK_STALE=12` it hands aria the same
**pure-fact** seam (a `stuck_note`). Free-validated on the real oracles: fires **27× ALL in run 3's keyboard region
(first @ step 459, ~26 steps before the watchdog halt), 0 false-fires during run 2's real battle**; 238 tests. **→
DIRECT NEXT ACTION = PAID-validate the stuck-breaker** (does the bare fact let aria press B / back out of the
keyboard? — free validation proves the signal fires, NOT that aria recovers). Then **S5 (procedural memory)**.
*(Orthogonal cleanup still open: the perceiver's keyboard-as-`battle` misread — now non-blocking but worth fixing.
Honest cost: freeze-recovery is wake-heavy — 12 / 57 / 70 wakes across the 3 runs.)* Full detail:
`reports/2026-06-21-seen-states-validation.md`
+ `reports/LEARNINGS.md` + the `novelty-signal` memory.

**⇒ CURRENT TRUTH (2026-06-20): the project was RE-ARCHITECTED in a planning session — read the
"⚠ 2026-06-20 — RE-ARCHITECTURE + COST ROOT-CAUSE" block below + [`ROADMAP.md`](ROADMAP.md). Goal = the
brain + world-as-tools + dual-process architecture (`ROADMAP.md`). The run-history blocks below (run #17's
"place-detection is the #1 blocker / NEXT", etc.) are now CONTEXT — that nav work is S6 in the plan.**

**⇒ S1 + S2 are DONE + PAID-VALIDATED LIVE (built + free-validated + adversarially reviewed + a ~$0.07 paid
smoke run). α/β decided = β (aria owns within-run memory).** S1 (cost-breaker, branch `feat/cost-breaker`)
unblocked paid runs; S2 (constitution-first, harness branch `feat/constitution-first` + aria local) put
`POKEMON_SYSTEM` in aria's cached prefix. **The 2026-06-20 battle smoke run (from `rival_battle.state`)
confirmed BOTH live:** S1's `[tokens]` line + budget-cap halt + cost summary work against the real backend;
S2's constitution is honored (a "reply PONG" probe proved it), **THINK/MOVE adherence HELD** (the key risk —
cleared), and the per-wake prompt was lean **~4–8k** (vs the ~13–30k baseline), growing only ~300–500 tok/wake.
*(Caveats: aria's usage omits cache tokens so the `[tokens]` cost is a safe over-estimate; aria's Docker image
bakes in its src — `docker compose build aria` to pick up code changes; from `start.state` the autopilot ran
120 steps with 0 wakes, so use a fixture to exercise the brain cheaply.)*

**DIRECT NEXT ACTION: S3 (β)** — retire the harness's *duplicate* within-run store (LESSON buffer) in favour of
aria's native memory (wiped per run via `reset_aria_memory.py`), keeping the harness-only signals aria can't
derive (the auto-advanced **missed-text transcript**, OutcomeMemory/disconfirm). Then a **longer paid run** to
measure end-to-end cost/wake at steady state. S4 (world-as-tools) follows; S5/S6 are independent free wins.
See the S1 + S2 cards below.

**LATEST (2026-06-20, run #17): the AFFORDANCE LAYER is VALIDATED — the agent got the starter COLD and WON the
rival battle (first start→starter→win in one run). The bottleneck moved to PLACE-DETECTION reliability.**
Built two free, pixels-only signals to fix run #16's "navigates the lab but can't transact the starter" wall:
**motion-saliency** (camera-static frame-diff → idle-animating NPCs as ROIs; a cluster-size filter rejects
animated terrain — data-validated, Pallet water 35→7, lab NPCs kept) and the **interaction-probe** (out of
frontiers → face each WALL + press A; a reaction = an interactable, since NPCs/objects sit on non-walkable tiles
and read as walls). Surfaced as `spatial_memory.rois` + an LLM hint; both off by default in `core/`, on in the
Pokémon drivers. **Run #17 (cold from `start.state`, run-16 config + the layer): the probe fired 23× and got
SQUIRTLE, then WON the rival battle** (vs Bulbasaur, a type disadvantage; `in_battle` 2→0 sustained @842, stayed
on map 40 = no blackout) — **nav+starter cost only ~6 of 69 wakes** (the probe is free autopilot; 227 free
advances). Report `reports/2026-06-20-live-run-17-affordance-layer-probe-saliency-got-the-starter.md`, ~$0.6-0.8.
**Also built (groundwork, NOT yet effective): cross-place exploration** (when a room is exhausted, route through
a portal to a place that still has frontiers — the decode-aligned way to make "leave Pallet" emerge instead of
being told by `goals.md`). **185 tests.** **THE #1 BLOCKER IS NOW PLACE-DETECTION RELIABILITY:** the Phase-B
place-graph MISSES real warps (run #16 + the free `probe_loop` MERGED the lab into Pallet — area 0 — because the
warp completed on a non-directional action, and the transition is gated on `direction is not None`) AND mints
SPURIOUS places from dialog-flicker (run #15 FRAGMENTED the lab into 5 places). The drift fix made WITHIN-room
geometry trustworthy; BETWEEN-room identity is not — and that blocks cross-place + clean interior reasoning +
reliably leaving the lab post-battle. **NEXT: (1) fix place-detection (don't miss a non-directional warp; don't
mint from dialog-flicker — data-first, we have the frames); (2) investigate a NEW API error mode that halted run
#17 post-win — `invalid_request` (AnthropicException, NOT credits), the circuit breaker correctly caught 4 in a
row; (3) then cross-place lets the agent leave the lab and head for Route 1.** *Prompt audit (this session): both
`POKEMON_SYSTEM` and aria's seed (`goals.md`/`core_memory.md`/`lessons.md`) inject RECALL — the full Kanto route,
type chart, gym order — so "go north" is told, not decoded; cross-place is the decode-aligned fix (David's call
on stripping the seed).* Branch `feat/interior-nav-drift` (off `main`), pushed.

**⚠ 2026-06-20 — RE-ARCHITECTURE + COST ROOT-CAUSE (planning session). Full record: `knowledge-export/` +
`ai-aria/PROMPT_ARCHITECTURE.md`; cost detail `reports/2026-06-20-cost-investigation.md`.**

**Cost root-cause (CORRECTED — the earlier "aux ≈ half the spend" was WRONG):** the CONVERSATION prompt is
**~92% of tokens** (aux/reflection ~8%); aria re-sends the whole `POKEMON_SYSTEM` manual **~7×/wake** (harness
staples it into the USER message → aria journals it → replays the last 6), and caching is crippled because
aria's system prefix is **below Haiku-4.5's 4096-token cache floor** while the big stable content rides the
uncacheable user message. **~$1.2/run, ~$7–9/day.** The `invalid_request` halts were **OUT OF CREDITS**, not
prompt size. Confirmed Haiku-4.5 pricing: **$1 / $5 per MTok in/out, $0.10 cache-read.** **Do NOT run a paid
job until the cost-breaker (S1 below) is in.**

**THE PLAN — executable sessions (each a code-grounded card from the 2026-06-20 scoping workflow):**
- **S1 — Harness cost-breaker** *(ai-pokemon-red · FREE · no prereqs)* — **✅ DONE (built + free-validated,
  branch `feat/cost-breaker`; 193 tests).** Shipped all four: **(1)** per-call `prompt_tokens` to the console
  (`_openai_complete` now returns `(text, usage)` — the brain was discarding the usage block; `LLMButtonBrain`
  meters it and prints `[tokens] prompt=… (cached=…) completion=… ~$… | run ~$…` each wake); **(2)** per-wake
  prompt-token cap (`--max-prompt-tokens`, default 32000 — a runaway-bloat tripwire above the ~13k baseline);
  **(3)** estimated-spend circuit-breaker (`--max-cost-usd`; brain accrues `total_cost_usd` from real usage ×
  Haiku-4.5 pricing, injectable → brain-agnostic); **(4)** a wake-denominated watchdog (`--stuck-wakes`,
  default 30 — the honest complement to `--stuck-steps`, which run #15's aimless wandering placated). All four
  auto-enable for paid brains in both drivers; the wake-watchdog lives DRIVER-side (correlates `brain.woke`
  with the oracle), so RAM never enters the brain. **Unblocks every future paid run** — and the first guarded
  paid run is S1's own live validation (real usage in the `[tokens]` line + a guard that actually halts).
- **S2 — Constitution-first move** *(both repos · FREE · 1 session)* — **✅ DONE (built + free-validated +
  adversarially reviewed; harness branch `feat/constitution-first`, aria local on `pokemon-red-constitution`).**
  Resolved the "biggest unknown": **aria did NOT honor an inbound system message** (`handle()` took only the
  last user msg). So the mechanism is: aria now renders an inbound **system-role** message as a `constitution`
  block placed FIRST in `_STATIC` (cached prefix BP1, dormant when none sent → companion unchanged); the harness
  sends `POKEMON_SYSTEM` as a **system message** (openai/aria backends) instead of stapling it into the user
  turn. **POKEMON_SYSTEM stays single-source in the harness** (decoupled, over HTTP) yet now caches once instead
  of duplicating ~7×/wake. Runtime-traced end-to-end (constitution → `deps.static_prompt` → litellm
  `cache_control: role:system` → BP1). 211 harness tests + 9 new aria tests; companion byte-identical when
  dormant. **⚠ first paid run must re-validate THINK/MOVE adherence** (the contract moved from the user turn to
  the cached constitution — review MEDIUM-2; unprovable offline).
  **⇒ SUPERSEDED IN PART by the constitution-move (ADR-001):** "POKEMON_SYSTEM stays single-source in the
  harness, sent as a system message" is no longer true — the constitution now lives in **aria's config**
  (`pokemon-red-data/constitution.md`, read via `memory.read_constitution`); the harness sends `system=""`
  (nothing on the wire); the inbound-system-message path remains only as a fallback. The brain owns its
  identity (the world doesn't send it each wake). *(Code in place; aria rebuild + paid validation pending.)*
- **S3 — Within-run memory → aria (β)** *(harness-only · FREE · branch `feat/within-run-memory-beta`)* —
  **✅ DONE (built + free-validated; adversarial review cut off by a session limit → key risks self-verified
  instead).** `LLMButtonBrain(owns_memory=True)` (set by the aria drivers) retires the harness's DUPLICATE
  LESSON buffer — both its accumulation and re-injection are gated off, so aria's native `<lesson>`→`lessons.md`
  (re-injected by aria each turn, stripped server-side so THINK/MOVE is untouched) is the sole within-run lesson
  store; `POKEMON_SYSTEM` drops the `LESSON:` lines; the disconfirm SURPRISE note is channel-neutral. Memoryless
  backends (`owns_memory=False`) keep the harness buffer (byte-identical). **Kept (aria can't derive):** the
  missed-text transcript, OutcomeMemory, disconfirm. **No aria code change** (it already owns the machinery).
  **Leak-safety (β makes the reset load-bearing):** `reset_aria_memory.py` gained `is_clean()` + a **fail-hard
  git seed-revert (verified vs HEAD)**; both drivers **fail-loud abort** a fresh aria run on un-reset memory
  (`--allow-dirty-memory` overrides / play_loop skips on resume). The law was revised (§1 above). 219 tests.
  ⚠ **first paid run must check that the agent still authors lessons** (now via `<lesson>`; run-#3 had
  `LESSON:` 56× / `<lesson>` 0× — provable only live).
- **S4 — World-as-tools API (the realignment)** *(both · 2–3 sessions)* — harness exposes the world as an MCP
  server (start: `observe` + `move`); aria attaches it via its existing MCP toolset and **acts via tool-calls**
  instead of returning text. Minimal scripted slice first; the cheap-first System-1/2 re-integration is its own
  follow-on. **Direction confirmed: harness = MCP server, aria = client** (keeps the decoupling).
- **S5 — System-1 authoring (first rung)** *(ai-pokemon-red · FREE · 1 session)* — a within-run `PolicyMemory`:
  when System 2 makes the same battle decision twice, compile a blind-execute policy System 1 replays for free,
  deferring on novelty/no-progress. **In-memory only** (learning-boundary; no across-run persist).
  **Read first — prior art:** Cradle's **Skill Curation / skill-library** (Voyager-lineage) is the closest existing
  implementation of this self-authored-skill loop; see `ROADMAP.md` (Prior art — Cradle) + `cradle-prior-art` memory.
- **S6 — Place-detection reliability** *(ai-pokemon-red · FREE · 1 session)* — the entertaining-testbed thread.
  Fix the place-graph: fades warp even on a non-directional action (stop **lumping**); dialog-flicker stops
  minting spurious places (stop **fragmenting**). Replay-validated; unblocks leaving the lab → Route 1.

**Sequence:** **S1 is DONE** (free, unblocked paid). Next build = the spine **S2 → S3 (β) → S4 (realignment)**,
with **S5 + S6 as independent free wins** that also keep the game moving. S4 is the deepest; S2+S3 are its
foundation. **Paid runs are now unblocked** — the first guarded one doubles as S1's live validation.

**OPEN DECISIONS (recorded, not blocking S1):** (a) within-run memory owner **α vs β** — David leans **β**
(brain owns it); confirm before S2/S3 merge. (b) **within-run vs across-run** System-1 policy learning —
near-term **within-run** (S5); across-run would revise the learning-boundary HARD LAW (deliberate, later).

**(run #16): the run-#15 INTERIOR-NAVIGATION wall is BROKEN + PAID-VALIDATED; the bottleneck
moved to AFFORDANCE / region-of-interest discovery.** Run #15's #1 blocker was dead-reckoning DRIFT in tight
rooms. Measured it *directly* against the RAM oracle (run #15 logged both the perceiver pose and ground-truth
x/y): **40.2% of overworld moves drifted, 139/144 the exact "RAM moved 2 tiles, perceiver recorded 1" case.**
Root cause = a wrong MOVEMENT MODEL: the autopilot presses `[d,d]` and the code assumed GateWorld's *"turn, then
move = net 1 tile"*, but the **real emulator absorbs the turn within the held press**, so `[d,d]` moves **TWO**
tiles when open while the perceiver capped the cursor at one → ~1 tile lost per same-direction step → the interior
map corrupts. Verified the true mechanics on the live emulator (`eval/probe_step.py`): a **single `[d]` press =
exactly one tile** (even on a direction change; turn is free), `[d,d]` = two. **Fix (two halves):** (1)
`ExploreBrain(single_step=True)` — the Pokémon drivers press `[d]` (one tile/decision) so each move stays synced;
the **agnostic default stays `[d,d]`** (GateWorld untouched — step granularity is a per-world property the driver
injects, `core/` stays world-agnostic). (2) **measured-distance odometry** in the perceiver — advance the cursor
by the best-shift magnitude (clamped to the ±4-tile window), marking every traversed cell visited, instead of
capping at one. **Free-validated** on run #15's real frames (`eval/replay_drift.py`: 40.2% → 0) AND **paid-validated
live in run #16** (`reports/2026-06-20-live-run-16-interior-nav-drift-fix-end-to-end-re-run.md`): drift **2.9% vs
40.2%**, and **only 4% across 149 move-pairs INSIDE the lab (map 40)** — the room that corrupted before is now
traversed cleanly, and the agent walked **up to Oak's tile at the top of the lab**, past run #15's wall. **170
tests.** Committed on `feat/interior-nav-drift` (off `main`, NOT pushed/merged).
**NEXT — the bottleneck MOVED (run #16): AFFORDANCE / ROI discovery.** Run #16 navigated the lab fine but
**never got the starter** (`in_battle` 0 all 618 steps, budget-cap halt): the perceiver models pure GEOMETRY
(visited/walls/frontiers/portals) and has **no representation of interactables** — Oak and the Pokéballs are
non-walkable tiles, so they read as *walls*, never frontiers; the autopilot only chases frontiers (wanders) and
the text-only LLM confabulates ("lab maze / staircase / exit"). Neither layer tries *face a ball and press A*.
**(1) Build an interaction-discovery primitive:** when the autopilot exhausts frontiers (the `[wake:stuck]`
trigger), face each adjacent *wall* and press A — a mode-change/decoded-text means that wall is an INTERACTABLE
(record it as an ROI, wake the LLM with it). Free, vision-free, world-agnostic, *replaces* wasted stuck-wakes; the
precondition for starter → rival → Route 1. (2) Optional: overworld-only vision + animation-saliency NPC detection.
(3) The learned blind-execute battle policy stays queued behind. (Mandatory before any paid run:
`reset_aria_memory.py --yes`, credit probe, `python -u`.)

**(2026-06-17): the agent WINS the rival battle and progresses PAST it — Phase A "fight" is DONE,
end-to-end.** Run #12 (verified per-step): it beat Gary's Squirtle with Charmander despite the type
disadvantage, got the Pokédex, left the lab. The chain that got us here, all validated live: **confabulation
(the cheap model misreading low-res battle SPRITES) → fixed by running text-only + decoding clean state; move
selection (couldn't read which move was highlighted) → fixed by `decode_move_menu` (move list + ▶ cursor) →
won.** The recurring lesson all session: **decode the state, keep the agent constant, wake the model only when
it must decide.** **Read `reports/INSIGHTS.md`** for the conceptual synthesis (the perception seam,
generalization from primitives, System-2→System-1 skill compilation, the learning-boundary law). **158 tests.**
**NEXT (bottleneck has moved OFF fighting):** (1) ~~**battle auto-advance**~~ **DONE + VALIDATED LIVE (run #13,
2026-06-20).** Wake only at the action/move menus; auto-advance battle narration for free.
`textbox.battle_subscreen` (pixels-only) splits a SETTLED battle frame into `battle_text` (narration → press A
free) vs `battle` (the action/move menu → wake); the perceiver emits the finer `context`; `HybridBrain`'s
dialog auto-advance branch is widened by one predicate to also advance `battle_text`. **Safety = positive-ID-
for-advance, default-to-wake** (a mis-read MOVE menu would auto-pick GROWL — the catastrophic case — so the
move menu is detected FIRST and any ambiguity wakes). Plus a generic `_ADVANCE_FUSE=50` and a battle-aware
watchdog in BOTH drivers (no halt mid-fight). **Run #13 (text-only hybrid from `rival_battle.state`, the run #12
config + auto-advance) WON the rival battle with just 18 BATTLE wakes vs run #12's ~68 (~3.8× cheaper)** —
verified per-step (`in_battle` 2→0 sustained at step 72; SCRATCH ×12 / GROWL ×0; correct grounding, 0 confab,
0 errors); 22 wakes / 400 steps total (5.5%), post-battle nav cost only 4 wakes (it even left the lab + explored
Pallet). **Report `reports/2026-06-20-live-run-13-battle-auto-advance.md`**, video `runs/run13.mp4`, oracle
`runs/run13/`, archive iter-013. Branch `feat/battle-auto-advance` off
`main`, committed, **NOT pushed**. 158 tests. NEXT: (2) the **learned blind-execute battle policy** (skill
compilation, now feasible because the state is decoded — INSIGHTS §6; run #13's 7 identical "FIGHT→SCRATCH"
turns are the obvious thing to compile); (3) tighten **lab-exit / Pallet navigation** (the residual Phase-B gap).

**Run #14 (2026-06-20) — first integrated COLD-START end-to-end run; nav holds, credits ran dry (downstream
inconclusive). Report `reports/2026-06-20-live-run-14.md`.** From `start.state` (text-only, all current
capabilities) the agent reached **Oak's lab `38→37→0→40` by step 130 on 15 productive wakes** — Phase B
navigation validated COLD (past run #4's wall; run #5 only reached it before credits) — and auto-advanced Oak's
dialog (81 free) in the lab. **Then Anthropic credits hit zero at step 276** (litellm log: *"credit balance is
too low"*); the 65 later wakes were 400s, budget-cap halt at 80, never reached the starter. Same recurring
external blocker (runs #5/#6/#14), NOT a capability gap; spend ~$0.10. **So "where it breaks downstream of the
lab" is STILL open.** ⇒ The **immediate** next step is **(0) top up the Anthropic credits behind aria + probe,
then re-run this exact end-to-end test** (precondition for #1–#3). A harness gap the outage exposed: **no
API-error circuit breaker** — the harness retried each credit-400 and counted it against the wake budget, so an
outage burns the cap on no-ops; halting after N consecutive identical API errors would fail fast/cheap (optional
hardening). *Process win: the run-end auto-report hook (built this session) fired correctly — first live test.*

**Run #15 (2026-06-20) — CONCLUSIVE end-to-end re-run; the downstream wall is INTERIOR navigation (credits were
masking it). Report `reports/2026-06-20-live-run-15.md`.** Built an **API-error circuit breaker** first
(`API_ERROR_CIRCUIT_BREAKER=4`: the brain detects backend errors echoed as content + exceptions, counts
consecutive failures, both drivers halt fast with the real error — so an outage no longer burns the wake budget;
+4 tests, 167), **topped up credits**, and re-ran from `start.state`. With credits healthy (**0 errors, breaker
correctly SILENT** — first live proof it doesn't interfere), the agent again reached **Oak's lab cold
(`38→37→0→40` by step 130)** but then got **wall-locked navigating the lab INTERIOR to reach Oak** — **all 100
wakes were `[wake:stuck]`**, never got the starter, never reached the battle; budget-cap halt (~$0.6-0.8). The
**pose-only occupancy map drifts/corrupts in the tight lab room** (the agent self-diagnoses *"the wall map is
corrupt"*); the place-graph fixed BETWEEN-map nav, but WITHIN-room nav is still pose-only and drifts. **⇒ THE
#1 BLOCKER is now interior / short-range navigation — the residual Phase-B dead-reckoning drift that was
DEFERRED** (it blocks the starter → rival → Route 1, and it even defeats the stuck-watchdog, which is placated by
real-but-aimless wandering). **NEXT, reprioritized: (1) fix interior/short-range navigation** (measured-distance
odometry that the Phase-B notes deferred / an interior re-grounding / an occupancy reset on entering a small
room); (2) the **learned blind-execute battle policy** now queues BEHIND nav (the battle is already solved — run
#12/#13 — but the agent can't reach one cold until it can get the starter). Credits/circuit-breaker are no longer
the blocker.

**What works (built + tested, 158 tests pass, no ROM/PyBoy needed for tests):**
- **Perception module** (`core/perception.py` seam + `games/pokemon_red/perceiver.py`): pixels →
  role-named `SymbolicState`; odometry + occupancy map; `detect_mode` (overworld/menu/dialog/battle).
  **Validated on real pixels:** per-step walkability 99.3% (tuned), modes incl. a **real battle 8/8**,
  overworld-vs-non-overworld 97.7%. **Per-frame perception is essentially solved** — no Iteration-01
  confabulation.
- **Cheap event-driven loop** (`core/brains.py`): `ExploreBrain` (free frontier autopilot, BFS),
  `HybridBrain` (wake the LLM only on non-overworld mode OR stuck), `LLMButtonBrain` (talks to aria;
  injectable `system` prompt), `OutcomeMemory` (`core/outcome.py`), and `goto` (planner names a cell,
  autopilot drives there).
- **Gating probe** (`games/gateworld/`): a synthetic world that isolates means-ends reasoning and
  separates **reasoning from recall** (familiar vs novel skins). Runs the **same agent unchanged**.
  Free scripted-oracle solve passes both skins; the real LLM verdict is credit-gated.
- **Clean agnostic/Pokémon seam:** `core/` knows about no specific game (game prompts + sandboxes
  live in `games/<world>/`).
- **MP4 recording** (`--record`, `core/recorder.py`): **video + game audio** (just fixed — was
  video-only). Works headless or windowed.

**The live result + a sharper diagnosis:** The first credit-funded LLM run (2026-06-15, hybrid+aria)
cost ~$3 and made no progress (38↔37). Post-mortem: `reports/2026-06-15-live-run-01-postmortem.md`.
A **free oracle replay (2026-06-15)** then corrected the framing: the *free* autopilot actually
**leaves the house and reaches Pallet Town's doorstep on its own** — "can't leave the house" was
specific to the hybrid run. The real failures:
1. **Seam oscillation — NOW FIXED.** On a *detected* transition the perceiver discarded the whole map
   and reset to (0,0); the way-back then looked like the only frontier, so the autopilot **ping-ponged
   across the door (0↔37) forever**. Fix: seal the way-back as a non-frontier **portal**
   (`perceiver.py`). Validated free vs the oracle — it now crosses once and explores Pallet.
2. **The LLM layer made it WORSE.** Woken 351/400 (88%) on a stuck autopilot, it just bankrolled
   flailing. Mitigations shipped: a **progress watchdog** (`--stuck-steps`, halts on no oracle-progress)
   and a **loop-breaker replan nudge** in `HybridBrain` (tells a stuck LLM to change direction + record
   a lesson). The seam fix also restores the cost model — a competent autopilot wakes the LLM rarely.
3. **Still open:** **prompt caching off** (aria-side), **odometry drift** (autopilot exhausts ~10
   Pallet cells then hands off — Tier-2 #6), and an **inert learning loop** (aria wrote no `<lesson>`;
   the nudge now prompts for one).

**Live run #2 (2026-06-15, recorded, clean-start, guarded) — SUCCESS + a new wall.** Full report:
`reports/2026-06-15-live-run-02.md`. With the fixes, the agent **left the house, crossed Pallet Town,
and reached Oak's Lab** (maps 38→37→0→40, 57 cells) for **~$0.23** (30 bounded wakes, vs run #1's 351 /
~$3). The free autopilot drove 76/123 steps. Video: `runs/run2.mp4` (1:40, video+audio). The run-#1
spatial failure is **solved on real hardware**. But it then **couldn't get the starter**: the LLM
**hallucinated its location** (narrated "Viridian City"/"Gramps" while truly in Pallet→Oak's Lab) and
**flailed through Oak's forced dialog**. And it wrote **no lesson** — root cause (grounded in aria's
code): aria's `<lesson>` channel is LIVE (it parses lesson tags from every reply → `lessons.md`,
`aria/.../memory.py:245`), but our prompt **muzzles** it — `POKEMON_SYSTEM` says "reply EXACTLY
THINK/MOVE, nothing else" + `max_tokens=64`, so the model never emits one. Per the learning-boundary
law the fix is a HARNESS-owned `LESSON:` buffer, NOT aria's persisting `lessons.md`.

**Live run #3 (2026-06-16, recorded, clean-start, guarded) — SUCCESS, the run-#2 wall is BROKEN.** Full
report: `reports/2026-06-16-live-run-03.md`, video `runs/run3.mp4`. With steps 1–3 (the `LESSON:` buffer,
disconfirm detector, dialog auto-advance, textbox decoder), the agent **comprehended Oak's forced gate,
chose SQUIRTLE as its starter, and reached the rival battle** (vs BULBASAUR) — maps 38→37→0→40, 87 cells,
for **~$0.33** (40 wakes, budget-capped). **Dialog auto-advance handled 123 dialog frames for free** (the
gate that burned run #2's whole budget), waking the LLM only at the 5 real choices; the textbox decoder
grounded it in real on-screen text (decoded live: *"ASH received a SQUIRTLE!"* — no more location
hallucination). It halted **mid-rival-battle** on the budget cap.

**The headline:** perception-geometry, the door-seam, AND scripted-gate/menu transaction are now solved
on real hardware. The bottleneck **moved again** → **(1) battle-move decisions** (run #3 stopped inside
the rival battle; no battle policy yet) and **(2) a belief-update gap** — aria narrated *"Bulbasaur
received"* while it truly got **Squirtle**, ignoring the decoded *"Got Squirtle!"* on screen. The agent
can navigate, read the screen, and transact gates; it can't yet *fight*, and it doesn't yet let a fresh
observation overturn a prior decision (agnostic-feature #4).

**Spend:** run #1 ~$3; run #2 ~$0.23; **run #3 ~$0.33** (40 wakes; 73 aria calls, 446K in / 9.8K out);
**run #4 ~$0.11** (14 wakes; watchdog-halted in Pallet, never reached the lab); **run #5 ~$0.83** (100 wakes,
budget-capped; reached the lab, then the last ~55 wakes 400'd as the Anthropic credits ran out); **run #6 $0**
(all 30 wakes 400'd — zero credit balance); **#6b ~$0.25 / #7 ~$0.3 / #8 ~$0.4** (battle-policy tests from the
fixture, after credits were restored; #6b validated battle mechanics, #7 crashed at step 39, #8 clean cap-50 —
none won; the confabulation isn't fixed); **#9 ~$0.3 (no-vision → confab=image), #10 ~$0.3 (clean grounding),
#11 ~$0.3 (move-menu, all SCRATCH), #12 ~$0.5 (WON, cap 80)**; ~$0.66 across the free work before. Prompt caching now **partly engages** (run #3: 96K cached tokens, vs
0 before) — a bonus, still not the bottleneck at this wake volume.

**Phase A items 1+2 (2026-06-16, this session) — battle-move policy + belief re-grounding BUILT (harness-only,
free-validated; 143 tests, +14; committed `99e4c22` + docs on `feat/lesson-buffer`, NOT pushed).** The next
iteration's harness work is done and ready for a guarded paid re-run:
- **Battle settle (the real fix for "woke 40× and never reached the menu").** Battle animations run 100+
  frames, so the fixed 16-frame `press` settle was landing observations *mid-animation*. New
  `advance_until_static` + `PyBoyEmulator.settle` (`emulator.py`) advance until the screen holds STILL
  (a `window`=24 streak of sub-`eps`=2.0 frame-diffs; tolerates a blinking cursor's ~0.7 diff); the plugin
  calls it after any action **only when `detect_mode=="battle"`** (`_settle_if_battle` — a **pixels-only**
  gate, no RAM, so the no-leak posture holds). Validated **live but free** (no brain) via
  `eval/verify_battle_settle.py`: every settle returned True, the ~116-frame send-out animation collapsed
  into ONE observation, and it reached the **action menu + move-select in ~10 settled observations** (vs
  run #3's 40 wakes that never got there).
- **Battle-signature fix.** In battle the pose-based `state_signature` is frozen (the menu cursor isn't the
  world map), so `OutcomeMemory` was about to mark **A** ("attack/confirm") a dead/"avoid" action and the
  disconfirm detector fired a spurious `SURPRISE:` every few turns. `HybridBrain` now **skips the tally and
  clears the streak when `context=="battle"`** (like an auto-advanced dialog — battle progress is invisible
  to a pose signature). `screen_text` stays out of the signature (a test forbids it; dialog-flail detection
  depends on a constant sig).
- **Battle guidance** added to `POKEMON_SYSTEM`: FIGHT/PKMN/ITEM/RUN **positional** nav (d-pad + A), A
  advances battle text, "your first move is a fine default if unsure," can't RUN a trainer battle.
- **Belief-update nudge (agnostic-feature #4) — implemented as vision RE-GROUNDING, not the sketched lexical
  trigger.** When the wake carries decoded `screen_text`, `LLMButtonBrain` appends a `TRUST THE SCREEN` line
  so a fresh observation can overturn a stale belief (the run-#3 Bulbasaur/Squirtle confab). The original
  sketch (a harness `SURPRISE: screen says X, you said Y`) is **structurally doomed** — the decoder mangles
  the uppercase Pokémon names it would need to compare (`SQUIRTLE`→`?O??RT?E`) — but the **model's own vision
  reads them**, so we nudge it to trust the screen instead of building a text-matcher that can't see.
- **New eval scripts (untracked):** `eval/verify_battle_settle.py` (validates the production settle on a real
  battle), `eval/capture_battle.py` (reaches the rival battle, captures FIGHT-menu + move-select frames),
  `eval/inspect_battle.py` (detect_mode + decoder + region dump over battle frames).
- **Adversarial review is now COMPLETE — 0 confirmed bugs.** The first pass (5 dimensions) returned 0
  confirmed issues but lost 2 dimensions to session limits; both were **re-run** and came back clean:
  **signature-fix** found no bugs (the `ctx_label` move is behavior-preserving; battle→overworld exit is
  benign; `detect_mode=='battle'` empirically covers all 46 captured battle sub-screens incl. action-menu
  + move-select, and 0/348 non-battle frames mislabel as battle) with one *intended-tradeoff* note (in-battle
  SURPRISE is fully suppressed — the watchdog/budget are the real battle safety net). **test-coverage**
  verified (by actual revert) that all 4 change-parts are pinned by a revert-failing test, and flagged a few
  cheap gaps; I closed them with **+5 hardening tests** (133 total): `advance_until_static` boundaries
  (`diff==eps` strict, a None frame mid-stream, exact-window) + the belief-nudge edge cases (whitespace-only
  → no nudge; coexists with transcript + lessons).
- **Next: the guarded paid run #4** — bar = get *through* the rival battle. Mandatory `reset_aria_memory.py
  --yes` first. (Setup note: confirm `--stuck-steps` is generous enough that a multi-turn battle — which
  shows no map/badge oracle-progress — doesn't trip the watchdog before the fight ends.)

**Live run #4 (2026-06-17, recorded, clean-start, guarded) — navigation blocked the battle test; PIVOTING TO
PHASE B.** With Phase A committed, the bar was getting *through* the rival battle. Instead the agent **never
got the starter**: oracle trajectory `38→37→0→39` — it entered **map 39 (the rival's house), not map 40
(Oak's lab)**, wandered Pallet Town (270/398 steps), and the **watchdog halted it** (no progress for 120
steps). 14 wakes / 398 steps (3.5%), **~$0.11** — the guardrails worked exactly right (a stuck run stopped
cheaply, nowhere near the $0.83 cap). **The Phase A battle policy is unexercised, not refuted** — the failure
is entirely upstream at the **unreliable lab-entrance navigation** (run #2 failed here too; run #3 reaching the
battle was partly luck). Not a Phase A regression (settle is battle-only + pinned by a test; the signature
else-branch is unchanged; the always-on `TRUST THE SCREEN` nudge fires on `screen_text`, ~empty in plain
overworld). Root cause is the **dead-reckoning drift** the place-graph (Phase B) is meant to fix. **Decision:
do Phase B before re-testing the battle**, and when we do re-test, **isolate it with a pre-positioned
rival-battle `.state` fixture** (RAM sets up the fixture; the agent still acts from pixels) so flaky overworld
nav doesn't gate it. Video `runs/run4.mp4`; oracle `runs/run4/`; pre-wipe archive `iter-003_2026-06-17.zip`.

**Phase B (2026-06-17) — navigation rebuilt + VALIDATED live; the run-#4 wall is broken (uncommitted, 143 tests).**
The frame-diff area detector was missing 8/10 warps and lumping distinct maps into one corrupt occupancy
area (run #4's lab-entrance failure). Phase B replaced it:
- **Transition = ego-motion vs scene-cut (translation), with a fade backstop.** Within a map the camera
  scrolls a centered player, so consecutive frames align under some integer-tile shift (`_best_shift`); a
  warp aligns under none. Measured: same-map best-shift diff p90 ≈ 5.4, warps 55–77 — and it catches interior
  **stairs** (the fade misses those). The **fade** (`_is_fade`, std<6, watched intra-press → `context["transition"]`)
  is kept for the post-menu case translation can't see. Plus a `detect_mode` fix so a bright outdoor scene
  isn't mislabeled "menu" (that false-positive masked warps via a spurious resync).
- **Topological place-graph:** a warp crosses to a persistent PLACE; `_transit` reuses a KNOWN place
  (restoring its map) via a direction-independent door edge, else mints a new one — so a building round-trip
  returns to the same Pallet map. BOTH door cells are sealed (the autopilot can't ping-pong the doorway).
- **Odometry capped at 1 tile (drift fix DEFERRED).** The shift gives true distance, but feeding it raw
  broke the ExploreBrain's `[d,d]`=net-one-tile motion contract (overshoot/oscillate — caught by the
  closed-loop test). So the shift drives robust moved-vs-blocked detection but the cursor still advances one
  tile; the full measured-distance drift fix awaits a controller that understands variable steps.
- **Validated:** unit (143 tests) + real-data replay + a free autopilot closed-loop run (`38→37→0`, 0 lumping,
  0 ping-pong). New evals: `inspect_warp`, `inspect_translation`, `replay_perceiver`.

**Live run #5 (2026-06-17, recorded, guarded) — Phase B nav VALIDATED live; lab completion blocked because
aria RAN OUT OF ANTHROPIC CREDITS mid-run.** The clean map got the agent to **map 40 (Oak's lab)** —
`38→37→0→40` — **past run #4's Pallet wall**; perception held (0 ping-pong, 1 minor lump). It worked for ~45
wakes (reaching the lab), then aria/litellm 400'd the remaining ~55 wakes. **The error is a billing one** (from
the litellm container log): *"Your credit balance is too low to access the Anthropic API."* — NOT a context
limit, NOT the harness (transcript is capped+reset). The credits simply ran dry ~45 wakes in, so the agent
couldn't finish Oak's dialog → budget-cap halt (~$0.83 of the run was the last of the balance). **Run #6
(isolated battle test from `rival_battle.state`) then 400'd on ALL 30 wakes from the first** — zero balance
left — confirming the cause. Credits were **later restored** (verified with a probe); the retry **run #6b**
then ran clean and validated the battle MECHANICS — see the battle-policy section in §3. Video `runs/run5.mp4`,
oracle `runs/run5/`, archives iter-004/005.

## 3. Next steps (prioritized: stop the bleeding → fix the cause)

**DONE:** Tier-1 guardrails (watchdog + budget cap + loop-breaker), the seam/portal fix (validated
*live* in run #2), the clean-start + archive tool, the recorded paid run #2 itself, and **the entire
harness-only learning/dialog build — steps 1, 2, 3a, 3b** (the per-run `LESSON:` buffer, the
disconfirm/surprise detector, fail-safe dialog auto-advance, and the Gen-1 textbox decoder + on-screen
grounding + missed-text transcript). Branch `feat/lesson-buffer`, **PUSHED to origin** through commit
`8233a82` (PR not yet opened — `gh` isn't installed; one-click URL on the GitHub branch page; recommended
base `feat/perception-module`), **143 tests**, each step adversarially reviewed (the step-3 review found
no bugs, only a widen-the-choice-region hardening + test gaps, now fixed). Details in `LEARNINGS.md`.

**Now (run-#2-informed, cheapest first):**
1. ~~**Un-muzzle lessons into a HARNESS-owned per-run buffer.**~~ **DONE** (commit `45271c4`).
   `POKEMON_SYSTEM` drops the "nothing else" muzzle + advertises an optional `LESSON:` line (a plain
   line aria passes through — NOT the `<lesson>` tag, which persists across runs); `max_tokens` 64→128;
   `LLMButtonBrain` parses it (`_parse_lesson`) into a per-run buffer (`self.lessons`, cap 8, dedup),
   re-injects it each wake, discards it at run end. Free; validated by tests + an adversarial-review
   workflow (which also caught a spurious-button parse leak + a stale-`goto`/`lesson`-on-failure bug).
2. ~~**Disconfirm / surprise detector**~~ **DONE** (commit `7ae55ad`). New `core/disconfirm.py`
   `DisconfirmDetector` (harness-owned): counts consecutive no-progress decisions and, at the threshold,
   injects one `SURPRISE: …` note (with the perceiver's `blocked`/`changed-nothing` detail) that asks for
   a `LESSON:` → lands in step-1's buffer. It **replaced** the old inline loop-breaker and now also fires
   on the case that one missed — flailing inside a forced **dialog** (mode-wakes that change nothing, the
   run-#2 wall). World-agnostic; the "act → observe → learn" spine. Validated by tests + adversarial review.
3. **Dialog auto-advance + a Gen-1 textbox decoder** — split into 3a (done) and 3b (in progress):
   - ~~**3a. Fail-safe dialog auto-advance.**~~ **DONE** (commit `facd598`). Data-first: `eval/capture_dialog.py`
     captured real START-menu/YES-NO/keyboard/dialog frames. Finding — a YES/NO box sits in the upper-right
     OVER the textbox and `detect_mode` read it as "dialog", so the mode label alone is unsafe to auto-advance.
     Fix: `detect_mode` now flags a textbox carrying an upper-right selection box (midright near-white > 0.15)
     as "menu" (a choice → wake); plain dialog stays "dialog". `HybridBrain(advance_on_dialog=True)` (Pokémon
     drivers) presses A through plain dialog for FREE (resets the disconfirm streak — advancing IS progress),
     waking only at a choice/battle. Validated on 272 real frames (plain→advance, YES-NO/START menu→wake;
     keyboard→battle=also a wake). 53/272 frames became free auto-advances.
   - ~~**3b. Gen-1 textbox font decoder.**~~ **DONE** (commit `279dd9e`, hardened `a3e6dcd`).
     `games/pokemon_red/textbox.py` slices the 2×18 8×8 text grid (lines y=112/128, x0=8) and
     template-matches each cell against `gen1_font.json` (42 glyphs, calibrated from pixels by
     `eval/calibrate_font.py`; unknown→'?', the ▼ arrow→dropped). The perceiver attaches the decoded text
     as `SymbolicState.screen_text` (with a quality guard so non-textbox screens yield ""); the plugin
     surfaces it in `obs.text`; `HybridBrain` accumulates the auto-advanced text into a per-run transcript
     and injects it at the next wake. Decodes all 6 calibration frames AND a held-out frame at **100%**.
     This is the run-#2 hallucination fix — the LLM now reads the actual on-screen words instead of guessing.
     (Glyph coverage is the early-game charset; uncalibrated glyphs decode to '?' safely and the table grows
     via `calibrate_font.py`.)
4. ~~**Guarded, recorded PAID re-run Pallet→starter→Route 1.**~~ **DONE — SUCCESS** (run #3, 2026-06-16;
   report `reports/2026-06-16-live-run-03.md`, video `runs/run3.mp4`). The run-#2 wall is **broken**: the
   agent comprehended Oak's gate, **chose SQUIRTLE, and reached the rival battle** for **~$0.33** (40
   wakes, budget-capped). Dialog auto-advance handled **123 dialog frames for free** (only 5 menu-choice
   wakes); the textbox decoder grounded it in real on-screen text (decoded live: *"ASH received a
   SQUIRTLE!"*). It halted **mid-rival-battle** on the budget cap. Steps 1–3 validated **live**.

**NEXT — phased (run-#3 + run-#4-informed). ORDER CHANGED 2026-06-17: Phase B (navigation) comes BEFORE the
Phase A battle re-test** — run #4 showed the agent can't reliably even *reach* the battle (it stuck at the lab
entrance), so reaching it is the precondition for testing how it fights. Phase A code is built + committed +
reviewed; its **live re-test is DEFERRED** until Phase B lands (or do it now via an isolated rival-battle
`.state` fixture — see run #4 in §2).**

**Phase A — "fight and keep playing" (harness-only; BUILT + COMMITTED `99e4c22`, reviewed clean; live re-test
deferred behind Phase B or an isolated battle-state fixture):**
1. ~~**Battle-move policy.**~~ **DONE (built + committed `99e4c22`, free-validated; live-untested).** Two parts: (a) a
   **battle settle** so the agent observes a *stable* decision screen instead of a mid-animation frame
   (`advance_until_static`/`PyBoyEmulator.settle`, gated by `detect_mode=="battle"` — pixels only;
   `eval/verify_battle_settle.py` reached the FIGHT menu in ~10 settled observations vs run #3's 40 that
   never did); (b) **battle guidance** in `POKEMON_SYSTEM` (FIGHT/PKMN/ITEM/RUN positional nav + first-move
   default) and a **signature fix** so `OutcomeMemory`/disconfirm don't mark **A** dead or false-fire
   `SURPRISE:` while the pose-signature is frozen in battle. The LLM has vision, so it navigates the menu
   without full glyph coverage. See §2 for detail.
2. ~~**Belief-update nudge (agnostic-feature #4).**~~ **DONE (this session; uncommitted) — as vision
   RE-GROUNDING, not the sketched lexical trigger.** When the wake carries decoded `screen_text`,
   `LLMButtonBrain` appends a `TRUST THE SCREEN` line so a fresh observation can overturn a prior belief
   (the Bulbasaur/Squirtle confab). The originally-sketched harness `SURPRISE: screen says X, you said Y`
   is doomed — the decoder mangles the uppercase names it would compare — but the model's own vision reads
   them, so we nudge it to trust the screen. See §2.
3. **Font coverage — CONDITIONAL, and NOT via ROM extraction (decided 2026-06-16).** The decoder isn't
   unreliable, it's *under-calibrated*: an in-table glyph decodes **100% exactly** (fixed 8×8 tile font),
   uncalibrated ones → an honest `?` (mostly uppercase), never a wrong guess. **We are NOT doing ROM font
   extraction** — even at build time it uses the game file, which bends the "no ROM / plan from the
   screen" north star, and the battle policy doesn't strictly need it (vision + positional nav). IF
   move-reading proves unreliable, complete the table via **PURE pixel-calibration** (`calibrate_font.py`,
   on-screen captures only). ROM extraction stays a last resort, only with David's explicit OK. (Not
   off-the-shelf OCR either — worse on 8px bitmap fonts + adds deps; reconsider only for a *new game*.)

~~**Phase B — place-graph + fade-based transition detection.**~~ **DONE (2026-06-17) + validated live (run #5
reached the lab). See the Phase B block in §2 for the full build.** It replaced the brittle frame-diff area
detector (which missed 8/10 warps and lumped maps) with translation-based scene-cut detection + a fade
backstop + a topological place-graph. The run-#4 lab-entrance corruption is fixed. **Caveat / deferred:** the
*measured-distance* odometry (the complete dead-reckoning drift fix) is **capped at 1 tile** for now — feeding
the true distance broke the ExploreBrain's `[d,d]`=net-one-tile contract; the full fix needs a controller that
understands variable step sizes.

**Battle policy — MECHANICALLY VALIDATED live (run #6b, 2026-06-17, after credits were restored).** From the
`rival_battle.state` fixture (agent starts AT the rival battle), the reach+settle+act machinery worked: 0
errors, the agent stayed in the fight every turn on stable battle screens and recognized "Gary wants to
fight → FIGHT" — the first live proof of Phase A item 1 (runs #3–5 never got a testable battle). **But it did
NOT win** (in_battle stayed 2 all 30 wakes) — the bottleneck MOVED to two new constraints:
1. **Move selection — it mashed `A` every turn.** Mashing A alternated SCRATCH (attack) and GROWL (a
   non-damaging stat move), so half its turns did no damage, at a type disadvantage (it has CHARMANDER vs
   Gary's SQUIRTLE). *"First move is a fine default" does NOT guarantee an ATTACKING move* — the policy needs
   to deliberately pick a damaging move, not just press A.
2. **Confabulation / belief-update gap (agnostic-feature #4) STILL OPEN.** The agent narrated having Bulbasaur
   and "defeating Squirtle" while the decoded screen (`Go! CHARMANDER!`, `Enemy SQUIRTLE`) + RAM say it has
   Charmander and the fight is ongoing. The `TRUST THE SCREEN` nudge was injected but did NOT override the
   confab — too weak.

**Battle policy — RESOLVED; the agent now WINS the rival battle (runs #6b–#12, 2026-06-17; all committed).**
The path took several iterations and the right fix was *decode the state*, not nudge the prompt:
- **v2 prompt+nudge (runs #7/#8) did NOT work.** The agent confabulated a confident **INVERTED** identity
  (*"I'm Squirtle, I'll WATER GUN the Charmander"* while it WAS Charmander). Belief-grounding is deeper than a
  prompt — a cheap model builds an internally-consistent wrong world and reasons from it; a soft nudge can't
  overturn it.
- **Run #9 (`--no-vision`) proved the IMAGE was the confab source** — with the battle sprites off, the
  confabulation vanished (Haiku misreads low-res pixel-art — the Iteration-01 weakness, in the one place we'd
  never decoded). But text-only was unusable because the decoded names were garbled.
- **Completed the OCR (no ROM)** via `eval/calibrate_battle.py` (auto-calibrate from self-verified known
  words), fixed the text-only prompt (stop asking for a screenshot), and **run #10 confirmed CORRECT grounding**
  ("Charmander vs Squirtle, bad matchup"). Remaining gap = move EXECUTION (couldn't read the highlighted move).
- **`decode_move_menu`** (move list + ▶ cursor) closed it: **run #11** used SCRATCH ×7 / GROWL ×0 reading
  *"cursor on SCRATCH"*; **run #12 (cap 80) WON** (in_battle 2→0 sustained, progressed past the battle).
- *Lesson:* the reasoning was never broken; the **input** was. Decode the battle state → the agent fights and
  wins. *(Process: run #7 hard-crashed with no traceback because stdout was BUFFERED — run paid jobs `python -u`;
  the "context ceiling" diagnosis of run #5 was wrong, it was OUT OF CREDITS — read the litellm log.)*

**NEXT — the bottleneck has moved off fighting (see the LATEST block in §2):** (1) **battle auto-advance**
(wake at the action/move menus, auto-advance battle text — ~4× cheaper battles; the static first rung of skill
compilation); (2) the **learned blind-execute battle policy** (System-2→System-1, now feasible because the
state is decoded — `reports/INSIGHTS.md` §6); (3) tighten **lab-exit / Pallet navigation** (residual Phase-B
gap run #12 re-exposed). Then the credit-gated **gating-probe** verdict and continued play.

**Confirmed by the run-#3 memory audit (free):** the harness `LESSON:` buffer (step 1) **engaged live** —
the model emitted `LESSON:` 56× / `<lesson>` 0×, and prompts show the re-injection + the decoded
transcript. aria's reflection wrote to its durable `lessons.md`/`core_memory.md` during the run, but the
committed seed is clean and `reset` reverts them → **no cross-run leak** (the law holds; reset is
mandatory). **DONE:** `screen_text` is now logged to the oracle (`e546011`) for post-run auditing.

Steps 1–3 were all **harness-only** (`core/` + `games/pokemon_red/`) — no aria changes — validated free;
step 4 (run #3) was the first (and so far only) credit spend (~$0.33).

**Deferred (NOT blocking):** prompt caching (aria-side; the unusual aria API path makes it its own
investigation — partly self-engaged in run #3, 96K cached), interior-stair detection (low-diff, didn't
block traversal; note **fade-detection won't catch stairs** — they don't fade). (Odometry drift / the
place-graph is now **Phase B** above, not merely deferred.) Also still open: extend the glyph table via
`calibrate_font.py` if not doing the ROM extraction.

**Run a clean paid iteration:** MANDATORY pre-run `uv run python reset_aria_memory.py --yes` (archives
→ wipes; zero accumulated experience, David's standing requirement), then the guarded recorded run
(`--max-llm-calls`, `--stuck-steps`, `--record`).

## 4. Architecture / orientation

- **`core/` — world-agnostic framework** (no game specifics): `contracts.py` (FROZEN wire types),
  `gateway.py`, `runner.py`, `permissions.py`, `perception.py` (the `SymbolicState` seam),
  `brains.py`, `outcome.py`, `recorder.py`.
- **`games/pokemon_red/`** — the Pokémon world: `plugin.py`, `perceiver.py`, `emulator.py` (the ONLY
  PyBoy import; also the wall-clock pacing governor + recording hook), `memory_map.py` (RAM→oracle),
  `reward.py`. Also `POKEMON_SANDBOX`, `POKEMON_SYSTEM`.
- **`games/gateworld/`** — the synthetic gating probe (a second world; agnostic generalization test).
- **`eval/`** — `score_perception.py`, `tune_threshold.py`, `capture_modes.py` (real battle/dialog
  capture), `gating_probe.py`. All $0.
- **`reports/`** — iteration reports, the consolidated report, specs, the live-run post-mortem, and
  `LEARNINGS.md` (running per-iteration log).
- **The brain is separate:** `ai-aria` (sibling repo) runs as a bearer-authed HTTP service; this repo
  imports none of its code and talks to it via `--backend aria`.

## 5. How to run

```bash
uv run pytest -q                 # 185 tests, no ROM/PyBoy needed

# watch the free autopilot (real-time + sound), record video+audio:
uv run python play_pokemon.py --rom roms/PokemonRed.gb --brain explore --perception \
    --load-state start.state --steps 150 --sound --watch-delay 90 --record runs/play.mp4

# score perception vs the oracle / capture real mode frames (free):
uv run python eval/score_perception.py runs/<run>/oracle.jsonl
uv run python -m eval.capture_modes

# the gating probe (free scripted oracle; --brain llm for the real, credit-gated verdict):
uv run python -m eval.gating_probe
```

**Live LLM run (needs aria up + credits):**
```powershell
# 0) START CLEAN — zero accumulated experience (mandatory before each paid iteration):
uv run python reset_aria_memory.py --yes
# 1) in ai-aria: docker compose up -d aria aria-litellm   (ARIA_DATA_DIR=./pokemon-red-data)
$env:ARIA_BEARER_TOKEN = ((Get-Content ..\ai-aria\.env | Where-Object { $_ -match '^BEARER_TOKEN=' }) -replace '^BEARER_TOKEN=','').Trim()
uv run python play_loop.py --rom "roms/PokemonRed.gb"        # headless, watchdog-guarded, persistent
```

**After the run — Definition of Done (document EVERY paid run; also in `CLAUDE.md`):**
```bash
# 1. the paid drivers AUTO-scaffold reports/<date>-live-run-<N>.md at run-end (scaffold_report: oracle-
#    verified facts + exact brain wake counts). To add a title/cost or the full console-log facts, re-run:
uv run python -m eval.report_run runs/run<N> --title "<what it tested>" --cost "~$X" --archive iter-<NNN>_<date>.zip --force
# 2. fill the report's TODO sections (TL;DR / what worked / broke / next) — grounded in the oracle, not narration.
# 3. add a dated bullet to reports/LEARNINGS.md.   4. update HANDOFF.md §2 (LATEST + NEXT) + memory/current-status.md.
```

**aria gotchas (have bitten us):** `ARIA_DATA_DIR` must point at `pokemon-red-data` (else Red runs
without its seed — verified in run #3 via the container's mount `pokemon-red-data → /app/data`); the
Anthropic key behind aria needs credits; prompt caching was off but **partly engaged in run #3** (96K).

## 6. Repo state

- **`feat/lesson-buffer` is the integration branch — everything stacks here** (Phase A + Phase B + all the
  battle-grounding/OCR/move-menu work + `reports/INSIGHTS.md`), as ~70 granular **per-feature** commits. It was
  **fast-forward-merged into `main`** (it was 0-behind / N-ahead, so the merge is a clean fast-forward with no
  conflicts) and **pushed** — `main` now has all the work. (`gh` is NOT installed, so the merge was a local
  fast-forward + push, not a GitHub PR.) Working tree clean except the untracked local helpers `make_state.py`
  + `rival_battle.state` (the battle-policy fixture). New branches off `main` from here for the next features.
- You supply your own legally-obtained `roms/PokemonRed.gb` (none is bundled). `start.state` (past the intro,
  in the bedroom) is generated by `make_state.py`; `rival_battle.state` (parked at the rival battle, for the
  isolated battle tests) by `eval/make_battle_state.py`. Both untracked/local.
- You supply your own legally-obtained `roms/PokemonRed.gb` (none is bundled). `start.state` (past
  the intro, in the bedroom) is generated by `make_state.py`.
- Windows + PowerShell host (a Bash tool is also available). Files under `runs/` are gitignored.

## 7. Project structure (file-by-file)

```
core/                      # WORLD-AGNOSTIC half of the WORLD INTERFACE (System 1 + the seam). NOT the agent — aria is (ADR-001).
  contracts.py             #   FROZEN wire types (ToolSpec/Call/Result, Event, Observation) + Protocols. Hash-pinned.
  gateway.py               #   the single door: permission check + deep-copy + dispatch to plugin
  runner.py                #   owns TIME / the ReAct loop: observe -> decide -> execute, N steps
  permissions.py           #   AllowAll / Allowlist policy classes (per-world sandbox INSTANCES live in games/)
  perception.py            #   the seam: SymbolicState (role-named) + Perceiver Protocol + PerceptMemory
  brains.py                #   ExploreBrain, HybridBrain (router + dialog auto-advance + LESSON/transcript), LLMButtonBrain, goto
  outcome.py               #   OutcomeMemory: per-(situation,action) "did it do anything" learning
  disconfirm.py            #   DisconfirmDetector: no-progress streak -> SURPRISE: + ask for a LESSON (within-run)
  recorder.py              #   VideoRecorder: frames(+audio) -> MP4 (lazy imageio; injectable writer)
games/pokemon_red/         # THE POKEMON WORLD (a GamePlugin; real-world regime, no reset/terminal)
  plugin.py                #   observe()/handle()/tools(); builds SymbolicState OR RAM obs; logs oracle.jsonl
  perceiver.py             #   OverworldPerceiver: odometry + occupancy map; detect_mode() (+choice detect); decodes textbox; NO RAM
  textbox.py               #   Gen-1 textbox decoder: pixels -> text via the glyph table (no RAM/VRAM)
  saliency.py              #   motion-saliency: camera-static frame-diff -> NPC/ROI candidates (terrain-filtered)
  gen1_font.json           #   the glyph asset (calibrated; extend via eval/calibrate_font.py)
  emulator.py              #   the ONLY PyBoy import; wall-clock pacing governor + recording hook
  memory_map.py            #   RAM addresses -> structured state (the ORACLE; never an agent input)
  reward.py                #   RewardTracker (maps-seen / badges) — for scoring/logging
  __init__.py              #   exports PokemonRedPlugin, POKEMON_SANDBOX, POKEMON_SYSTEM
games/gateworld/           # SYNTHETIC gating probe (a 2nd world; runs the SAME brains unchanged)
  world.py                 #   GateWorld plugin + themes (familiar/novel); turn-then-move semantics
  solver.py                #   ScriptedReasoner (free oracle stand-in for the LLM)
  __init__.py              #   exports GateWorld, FAMILIAR/NOVEL, ScriptedReasoner, GATEWORLD_SANDBOX
eval/                      # measurement harnesses (all $0; no ROM needed to import)
  score_perception.py      #   perception vs oracle (walkability/escape/drift)
  tune_threshold.py        #   pick move/area frame-diff thresholds from a logged run
  capture_modes.py         #   script the opening into real battle/dialog frames + grade detect_mode
  capture_dialog.py        #   capture real dialog/menu/CHOICE frames (+features) for the dialog/decoder work
  calibrate_font.py        #   build games/pokemon_red/gen1_font.json from pixels (read text off frames)
  verify_battle_settle.py  #   validate the production PyBoyEmulator.settle on a REAL battle (Phase A)
  capture_battle.py        #   reach the rival battle; capture FIGHT-menu + move-select frames (Phase A)
  inspect_battle.py        #   dump detect_mode + decoder + region features over battle frames (Phase A)
  inspect_warp.py          #   does a map warp emit a fade? per-frame std through a press (Phase B B0)
  inspect_translation.py   #   best-shift overlap diff: same-map vs transition separation (Phase B)
  replay_perceiver.py      #   replay a run's frames through the perceiver; check for map-lumping (Phase B)
  probe_step.py            #   live emu: confirm single [d] press = 1 tile, [d,d] = 2 (interior-nav drift fix)
  replay_drift.py          #   replay a run's frames; score perceiver pose-delta vs RAM per step (drift fix)
  inspect_motion.py        #   motion-saliency probe: per-map NPC ROIs vs animated terrain (affordance layer)
  probe_loop.py            #   FREE closed-loop (scripted-A fallback): validate probe+saliency+cross-place, no API
  gating_probe.py          #   run GateWorld both skins; reasoning-vs-recall verdict
  report_run.py            #   scaffold reports/<date>-live-run-<N>.md from a run's oracle.jsonl + log (Definition of Done step 1)
tests/                     # 185 tests, no ROM/PyBoy (FakeEmulator + synthetic frames + injected writers)
reports/                   # iteration reports, consolidated report, specs, live-run post-mortem, LEARNINGS.md
play_pokemon.py            # single-run driver (watch/record/--brain explore|hybrid|llm)
play_loop.py               # loop-safe driver: watchdog + budget guard + checkpointing (use for paid runs)
eval_haiku.py              # Iteration-01 direct-API harness (uses red_system_prompt.txt)
make_state.py              # generates start.state past the intro (untracked helper)
reset_aria_memory.py       # wipe aria's run-generated experience to a clean seed before a paid run
roms/PokemonRed.gb         # YOUR vanilla ROM (not bundled, gitignored)
```

## 8. Navigating the code (the data flow)

**Read in this order:** `HANDOFF.md` → `reports/2026-06-15-consolidated-report.md` →
`core/contracts.py` (the vocabulary) → `core/runner.py` (the loop) → `games/pokemon_red/plugin.py`
(a real world) → `core/brains.py` (decisions).

**One-sentence flow (per step):**
`runner.observe()` → plugin builds the observation (**perception path:** `perceiver` turns pixels
into a `SymbolicState`; RAM is logged to `oracle.jsonl` and NOT returned) → `brain.decide(obs, tools,
context)` returns a `ToolCall` → `gateway.execute()` (permission check + deep-copy) → `plugin.handle()`
→ `emulator` presses buttons → repeat.

**"Where is X?" index:** decision/routing logic → `core/brains.py` (`HybridBrain`); what the agent
sees → `plugin.observe()` + `perceiver.py`; ground truth & scoring → `memory_map.py` + `oracle.jsonl`
+ `eval/score_perception.py`; pacing / recording / the only PyBoy calls → `emulator.py`; the
cheap-vs-LLM split → `HybridBrain` wake logic.

**To add a new world:** implement `GamePlugin` (`tools/handle/observe/drain_events`) under
`games/<world>/`, **emit a `SymbolicState`-shaped observation** (so the existing brains run
unchanged), and add a `<WORLD>_SANDBOX` allowlist + (if LLM) a world prompt. `games/gateworld/world.py`
is the minimal template; `core/` must stay game-free.

## 9. Surprises & gotchas (hard-won — these cost us time/money)

- **PyBoy `set_emulation_speed(1)` does NOT throttle here** (measured: `tick(120)` = 16 ms, not ~2 s)
  across window backends → we own pacing with a frame-by-frame wall-clock governor in `emulator.py`.
  (This was the "watch-delay does nothing" bug.)
- **Frame-diff area-transition detection is unreliable and was the live-run killer:** interior
  stair-warps are *low*-diff (~13–29), **below** `area_threshold = 60`, so they're **missed** → the
  map never resets → drift → an unreachable phantom frontier. (Outdoor↔indoor is high-diff; interior
  stairs are not.) **Fade detection is the right signal** — and the near-uniform-frame guard already
  in `detect_mode` is the reusable building block.
- **`ExploreBrain`'s `[d,d]` = "turn, then move" (net 1 tile, Gen-1 semantics).** A new world MUST
  honor this motion contract or the autopilot overshoots and **oscillates forever** (the GateWorld
  bug). Match it (`facing` + turn-then-move) or change the brain.
- **`oracle.jsonl` is APPEND-mode** — multiple runs to the same `--out` accumulate. Isolate the
  latest run by segmenting on the `step` counter resetting (see the post-mortem's analysis snippet).
- **`detect_mode` quirks:** white/black **fades** (std≈0) once tripped the "battle" rule; real
  battles are *also* mostly-white (std > 65 from sprites), so a **uniformity guard** (`std < 6` →
  treat as transition) separates them. The Gen-1 **naming keyboard** still reads `battle` (full-screen
  bright menu) — harmless, since it's non-overworld either way (wake-correct).
- **Use a VANILLA ROM.** The "Colorization" ROM hack broke `new_game.py`'s intro-skip AND the RAM map
  (garbage telemetry). `start.state` is generated by `make_state.py` using `wMaxMenuItem` (`0xCC28`
  ≥ 3) to detect the name-entry menu.
- **Prompt caching:** was OFF in runs #1–2 (`cached_tokens = 0` — every call resent the full prompt);
  run #3 showed it **partly engaging** (96K cached). Still worth chasing as a cost win, but no longer
  "zero" and not the bottleneck at this wake volume.
- **`ARIA_DATA_DIR` must = `./pokemon-red-data`** or aria runs on its default dir without Red's seed
  (type chart / goals / curiosity) — *silently wrong*. Set in `ai-aria/.env`; recreate containers.
- **PyBoy audio:** `pb.sound.ndarray` = ~801 stereo **int8** samples/frame at **48 kHz**; works
  **headless** (`sound_emulated=True` regardless of window); read once per `tick(1)`; scale int8→int16
  (`<< 8`) for a WAV. `imageio` MP4: GB dims (160×144) and integer upscales are ÷16, so no padding.
- **`OutcomeMemory`'s signature is pose/area/context-only** → it MISSES inventory/state changes (an
  item pickup reads as "no effect"), and drift makes every situation look novel so it never flags a
  dead action. Progress must be tracked **globally**, not per-(situation,action).
- **`core/contracts.py` is FROZEN** (SHA pinned in `tests/test_contract_frozen.py`) — don't edit it.
- **`eval/` needs its `__init__.py`** (was an implicit namespace package) for unambiguous
  `python -m eval.<module>`.
- **Windows/encoding:** when reading `git show` output in Python, pass `encoding="utf-8"` or UTF-8
  bytes (é, em-dashes) get mangled to cp1252 and inflate string lengths (this caused a false
  "prompt drifted" scare). CRLF warnings on commit are benign (autocrlf).
- **`CLAUDE.md` is gitignored** by repo convention ("internal, not for publication") — it works as a
  local file regardless.
