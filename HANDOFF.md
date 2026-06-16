# HANDOFF — ai-pokemon-red

Read this first. It is the living summary of **what we're building, where we are, and what's next.**
Deeper detail lives in `reports/` (start with the consolidated report) and `reports/LEARNINGS.md`.

_Last updated: 2026-06-15._

---

## 1. Overall goal (the north star)

This is **not** about beating Pokémon. Pokémon Red is the **first probe world** for the real goal:

> Build a **simple, generalizable** agent that acts on the world — generalizing across games and
> eventually reality — that is **cheap** and works from the **screen**, not privileged state.

Four constraints held on purpose (they're what makes the result transfer):
- **Generalize** — find the *smallest* increments that let the *same* agent act in a *different*
  world. Avoid Pokémon-specific hacks. (The brain, **ai-aria**, is a fully decoupled HTTP service.)
- **No ROM / privileged state** — plan from the **screen**. RAM exists only as a **non-leaking
  scoring oracle** (`oracle.jsonl`); it never enters the agent's input.
- **Cheap** — minimize API calls/tokens. A free local autopilot does routine work; wake the
  expensive LLM only at decisions.
- **Learning boundary (HARD LAW — do not drift):** *across-run* learning is **harness/code updates
  ONLY** (perception, brains, detectors) — the agent starts **blank every run** (archive + wipe before
  each). *Within-run* learning lives in the **harness** (`core/`): the occupancy map, `OutcomeMemory`,
  the disconfirm detector, any LLM-authored `LESSON:` — fresh per run, injected into the LLM's context
  each wake, **discarded at run end**. aria *authors* lessons; the harness *persists + re-injects* them
  within the run. Never use aria's durable memory as the within-run store; never let a lesson bleed
  into the next run.

The whole framework is one small loop: `perceive → recall → decide → act → observe outcome → learn`.

## 2. Current status (2026-06-15)

**What works (built + tested, 73 tests pass, no ROM/PyBoy needed for tests):**
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
~$0.66 across the free work before. Prompt caching now **partly engages** (run #3: 96K cached tokens, vs
0 before) — a bonus, still not the bottleneck at this wake volume.

## 3. Next steps (prioritized: stop the bleeding → fix the cause)

**DONE:** Tier-1 guardrails (watchdog + budget cap + loop-breaker), the seam/portal fix (validated
*live* in run #2), the clean-start + archive tool, the recorded paid run #2 itself, and **the entire
harness-only learning/dialog build — steps 1, 2, 3a, 3b** (the per-run `LESSON:` buffer, the
disconfirm/surprise detector, fail-safe dialog auto-advance, and the Gen-1 textbox decoder + on-screen
grounding + missed-text transcript). Branch `feat/lesson-buffer`, **local-not-pushed**, 9 commits
(`45271c4`→`a3e6dcd`), **119 tests**, each step adversarially reviewed (the step-3 review found no bugs,
only a widen-the-choice-region hardening + test gaps, now fixed). Details in `LEARNINGS.md`.

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

**NEXT — two walls run #3 revealed (battle moves + belief-update), then the gating probe:**
1. **Battle-move decisions.** Run #3 stopped inside the rival battle — we have **no battle policy** (pick
   FIGHT/move/switch from the battle menu). Likely the same pattern: wake the LLM at the battle menu with
   the decoded battle text + options + a cheap default.
2. **Belief-update gap (observation-grounded belief check, agnostic-feature #4) — the deeper one.** Run
   #3's journal shows aria narrated *"Bulbasaur received"* while it truly got **Squirtle**; even though the
   decoder fed it *"Got Squirtle!"*, it kept its prior intention and mis-attributed the evidence. The
   decoder fixed *reading the screen* but not *letting an observation overturn a prior decision*. Needs a
   harness nudge that surfaces the contradiction (e.g. a `SURPRISE:`-style "the screen says X, you said Y").
3. Then the credit-gated **gating-probe** verdict (means-ends reasoning) and continued play.

**Confirmed by the run-#3 memory audit (free):** the harness `LESSON:` buffer (step 1) **engaged live** —
the model emitted `LESSON:` 56× / `<lesson>` 0×, and prompts show the re-injection + the decoded
transcript. aria's reflection wrote to its durable `lessons.md`/`core_memory.md` during the run, but the
committed seed is clean and `reset` reverts them → **no cross-run leak** (the law holds; reset is
mandatory). **DONE:** `screen_text` is now logged to the oracle (`e546011`) for post-run auditing.
Still open: extend the glyph table's uppercase via `calibrate_font.py`.

Steps 1–3 were all **harness-only** (`core/` + `games/pokemon_red/`) — no aria changes — validated free;
step 4 was the first (and so far only) credit spend (~$0.33).

**Deferred (NOT blocking):** prompt caching (aria-side; the unusual aria API path makes it its own
investigation — not blocking at this wake volume), full place-graph + odometry drift (Tier-2; the
autopilot hands off to the LLM at a healthy point), interior-stair detection (low-diff, didn't block
traversal; note **fade-detection won't catch stairs** — they don't fade).

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
uv run pytest -q                 # 73 tests, no ROM/PyBoy needed

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

**aria gotchas (have bitten us):** `ARIA_DATA_DIR` must point at `pokemon-red-data` (else Red runs
without its seed); the Anthropic key behind aria needs credits; **prompt caching is off** (cheap win).

## 6. Repo state

- Branch: **`feat/perception-module`** (**PR open** against `main`). NOTE: the seam-fix + Tier-1
  guardrail commits are **local only — not yet pushed** (push when David asks).
- You supply your own legally-obtained `roms/PokemonRed.gb` (none is bundled). `start.state` (past
  the intro, in the bedroom) is generated by `make_state.py`.
- Windows + PowerShell host (a Bash tool is also available). Files under `runs/` are gitignored.

## 7. Project structure (file-by-file)

```
core/                      # WORLD-AGNOSTIC framework (the reusable agent). No game specifics.
  contracts.py             #   FROZEN wire types (ToolSpec/Call/Result, Event, Observation) + Protocols. Hash-pinned.
  gateway.py               #   the single door: permission check + deep-copy + dispatch to plugin
  runner.py                #   owns TIME / the ReAct loop: observe -> decide -> execute, N steps
  permissions.py           #   AllowAll / Allowlist policy classes (per-world sandbox INSTANCES live in games/)
  perception.py            #   the seam: SymbolicState (role-named) + Perceiver Protocol + PerceptMemory
  brains.py                #   ExploreBrain (free autopilot), HybridBrain (router), LLMButtonBrain (aria), goto
  outcome.py               #   OutcomeMemory: per-(situation,action) "did it do anything" learning
  recorder.py              #   VideoRecorder: frames(+audio) -> MP4 (lazy imageio; injectable writer)
games/pokemon_red/         # THE POKEMON WORLD (a GamePlugin; real-world regime, no reset/terminal)
  plugin.py                #   observe()/handle()/tools(); builds SymbolicState OR RAM obs; logs oracle.jsonl
  perceiver.py             #   OverworldPerceiver: odometry + occupancy map; detect_mode(); NO RAM
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
  gating_probe.py          #   run GateWorld both skins; reasoning-vs-recall verdict
tests/                     # 73 tests, no ROM/PyBoy (FakeEmulator + synthetic frames + injected writers)
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
- **Prompt caching is OFF in the aria stack** (`cached_tokens = 0`) — every LLM call resends the full
  prompt uncached. The single biggest cheap cost win (a paid run cost ~$3 partly for this).
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
