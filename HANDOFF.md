# HANDOFF — ai-pokemon-red

Read this first. It is the living summary of **what we're building, where we are, and what's next.**
Deeper detail lives in `reports/` — the consolidated report, `reports/LEARNINGS.md` (the chronological
per-iteration log), and **`reports/INSIGHTS.md` (the thematic synthesis of the ideas: the perception
seam, generalization from primitives, System-2→System-1 skill compilation, the learning-boundary law).**

_Last updated: 2026-07-03 (IT1 TASK COMPLETE — party 0→1 oracle-verified; same brain played GB+GBA+NDS live; #43/#44 merged, #45 open)._

---

## 1. Overall goal (the north star)

This is **not** about beating Pokémon. Pokémon Red is the **first probe world** for the real goal.

**THE GOAL (canonical, 2026-06-22):**
> Build **one agent — a fixed reasoning brain + a swappable perception layer — that completes human-given
> tasks at human-grade competence using only the screen and human-grade controls, across increasingly
> different worlds, cheaply, and without per-world training.**

**Unpacked into testable claims** (each separately checkable — that's what makes it a goal, not a vibe):
1. **Capability — human-grade task success from the screen.** Pixels in, human-grade actions out (buttons, or
   mouse/keyboard); **no privileged channel** (no RAM, no DOM, no accessibility tree, no API). Measured as
   task-success-rate vs. a human baseline. ("Could pass for a human" is a *symptom* of clearing this bar,
   never the objective — and we evaluate only on sanctioned/permitted targets.)
2. **Constancy — the brain doesn't change.** A new world swaps only the **perceiver** (+ a per-world config/
   constitution); the brain (`ai-aria`) is reused unchanged. Success = *how little changes outside the
   perceiver.* This is the core claim and the one most likely to be false.
3. **Generality — across two axes of increasingly-different worlds:**
   - **Embodiment ladder** (one self, locomotion, learns from its own motion): 2D game → 3D game → sim robot
     → physical robot.
   - **Computer-use track** (mouse+keyboard+screen, indirect/many-entity control, no single self):
     strategy/builder games (a safe, *scored* sandbox) → permitted desktop/web tasks. (Pixels-only is primary;
     the a11y-tree is at most an optional second condition for productivity apps — never the thing we claim on.)
4. **Cheap.** Free fast System 1 does routine work; the costly System 2 (LLM) wakes only at decisions.
   Measured as cost/task and wakes/task, held low.

**Falsified if:** constancy breaks (a new world forces brain edits or a new System-1 per genre); OR pixels-only
can't reach human-grade where a privileged-channel version can; OR it only works on the easy slice and
collapses on the held-out worlds. **The full multi-month arc (It1 Pokémon → It5 robot, + the computer-use
track) is in [`ROADMAP.md`](ROADMAP.md).**

**⇒ The repo-boundary CONTRACT is pinned in [`ARCHITECTURE.md`](ARCHITECTURE.md) (ADR-001, 2026-06-20) — read it
and don't drift from it:** `ai-pokemon-red` = the WORLD INTERFACE + **System 1** (perception + reflexive fast
loop + the oracle); `ai-aria` = the AGENT + **System 2** (deliberate reasoning + ALL memory + identity/
constitution). They meet at ONE frozen seam (`SymbolicState` → agent; an intent → world). Research-grounded
(SwiftSage; the 3-layer reactive/deliberative robotics architecture; "Distilling System 2 into System 1";
Voyager). Only revise on an empirical surprise, as a new ADR. **Methods, principles, preferences + drift
tripwires:** [`reports/CONTEXT-BRIEFING.md`](reports/CONTEXT-BRIEFING.md). Other architecture detail:
`ai-aria/PROMPT_ARCHITECTURE.md` + `memory/dual-process-architecture.md` + `knowledge-export/`.

The invariants that make a win *count* (held on purpose — they're what makes the result transfer):
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

## 2. Current status (newest block first — read the TOP block)

**⇒ Read the TOP block first — this section is append-on-top (newest → oldest). Picking up COLD? `git fetch` +
check `origin/main` and `gh pr list --state all` before trusting local branch state (a squash-merge orphans the
source branch's commits → "N ahead of main" can mean already-merged).**

**⇒⇒ NEWEST (2026-07-02, later session) — "PATIENCE" AUTO-ADVANCE REFLEX BUILT (the 07-02-designed System-1
gated-static skip). Branch `feat/patience-auto-advance`, off `origin/main` at `5216153`; PR TBD.**

- **What landed:** `core/patience.py` (new) — `classify(context) -> {"gated-static","choice","free-control"}`
  + `AdvanceLearner` (per-run, blank-every-run control-grounded button memory) + `Patience.advance()` (the
  loop). Wired into `core/perception_plugin.py::observe()`: after the normal perceive, if the frame classifies
  gated-static, auto-press (candidate-then-learned button) and re-perceive in a loop, capped at
  `DEFAULT_BUDGET=40`, before ever returning to the brain. `Observation.data["patience_advances"]` +
  `oracle.jsonl`'s `patience_advances` carry the free-advance count (traceability). On by DEFAULT (a bare
  `PerceptionPlugin(...)` now gets `Patience()`) — safe because `classify()` only fires on contexts positively
  known to be gated-static; every other context (including any world's plain `"menu"`) defaults to `"choice"`
  and the loop never runs.
- **State classifier:** `GATED_STATIC_CONTEXTS = {"dialog", "battle_text", "static"}` (Red's decoder-backed
  `dialog`/`battle_text` — its `detect_mode` already keeps a YES/NO choice OUT of these labels via the
  upper-right-box heuristic — plus the generic `core/modality.py` `"static"` frozen-screen label for
  text-less worlds/titles). `CHOICE_CONTEXTS = {"menu", "battle"}` — Red's real decision surfaces, AND a
  generic world's `"menu"` (deliberately included: `detect_modality` cannot distinguish a plain textbox from
  a YES/NO choice the way Red's heuristic can, so its `"menu"` must fail safe to "might be a choice"). Anything
  else (`"unknown"`, a future world's novel label) also defaults to `"choice"` — the fail-safe/erase-save guard.
- **Learned-button mechanics:** `AdvanceLearner` cycles a candidate ladder (`a`, `start`, `b`) per press; the
  first button whose press produces an OBSERVED change (not just "pressed") gets `confirm()`ed and reused for
  the rest of the run. "Observed change" needed to be more than the bare context label — two consecutive
  dialog LINES both read `context=="dialog"` — so `_press_and_reperceive` in `perception_plugin.py` compares
  `screen_text` (Red's decoded line) first, then falls back to a strict raw-pixel-equality check
  (`_is_frame_equal`) for text-less gated-static screens (a generic title/naming screen with no decoder) — this
  is the exact Emerald-naming-screen case (`a` loops silently, `start` confirms) reproduced as a scripted test.
- **Validation done (free, no ROM needed in this sandbox):** unit tests on `classify`/`AdvanceLearner`/
  `Patience.advance()` + 2 tests against REAL recorded frames (`eval/fixtures/starter_cutscene_pose/`,
  `detect_mode` on an actual Oak-cutscene dialog frame) + a scripted closed-loop proof through the real
  `PokemonRedPlugin.observe()` (no ROM/LLM, a `_ScriptedDialogEmulator`/`_ScriptedPerceiver` test double): a
  12-line dialog chain auto-advances to completion in ONE `observe()` call (`patience_advances == 12`), stopping
  exactly at a `"menu"` (choice) frame with zero further auto-advances; a budget-exhaustion case; the
  Emerald-style a-loops/start-confirms case. Full suite: **460 passed, 4 skipped** (baseline was 436 passed, 4
  skipped — same skip count, so cross-world regression on cave_noire/gauntlet/nds is intact).
- **Deviations from the brief:** the mandated **live/ROM closed-loop proof on `runs/red_start.state`** (task
  item #2) was NOT run — no ROM or `.state` file is present in this sandbox (`roms/`/`*.state` are gitignored
  and this worktree has neither); substituted a scripted no-ROM closed-loop proof through the real plugin
  instead (above). The `kirby_title_menu` fixture and `runs/brain_emerald/world/` frames named in the task also
  don't exist in this checkout (not committed) — the Emerald a-loops/start-confirms case is covered by a
  scripted reproduction, not real recorded Emerald frames. **⇒ NEXT (if picking this up): run the real
  `red_start.state` closed-loop wake-count comparison (with/without patience) on a machine with the ROM +ES,
  and carve the real Emerald fixture, to close this gap for real.**

**⇒⇒ NEWEST (2026-07-03, overnight autonomous session) — IT1 TASK COMPLETE (party 0→1, ORACLE-VERIFIED) +
THE SAME BRAIN PLAYED GB + GBA + NDS LIVE THROUGH ONE SEAM. PRs #43 + #44 MERGED (main `5d9f26d`);
PR #45 (Dockerfile NDS libs) OPEN for David. This supersedes the 07-02 block below. ⇒⇒**

- **IT1 CLOSED (audit #5, account B, $3.66, 77 decisions): `watch.party` 0→1 at oracle step 380**, nickname
  declined, back in free movement, clean stop on evidence. Run artifacts: `runs/brain_red_starter/`. It took
  5 paid runs (~$13.4 total); each failed one rung HIGHER: #1 pose corruption (fixed in code, #44) → #2 object
  grounding ("which tile is a ball?" — bridged in the brief; the REAL fix is the referential/semantic layer,
  the documented keystone gap) → #3 stopped at the stats screen on a wrong inference → #4 travel variance ate
  the 60-cap → #5 done at cap 90. **Residual known gaps, deliberately brief-bridged, NOT solved:** static-object
  perception (the Poké-Ball tiles), and premature-stop/confabulated-success (fixed with an evidence-only stop
  rule in the brief; a harness-side success-predicate check would be the durable fix).
- **PR #44 (merged) — the interior-pose fix, live-validated:** pose held stable through the entire lab
  cutscene/dialog in all 4 post-fix runs (the 07-02 (0,0)+mis-walled corruption is GONE). Design: transitions
  now require FADE-CONFIRMED + single-unambiguous-direction (`_single_dir`); a residual-only scene cut → pose
  LOST (no wall/cell/edge writes) → ONE deliberate re-anchor to a fresh place on a settled single-dir step with
  `frames_advanced > 0`; the fade flag `ctx["transition"]` is now actually WIRED live (a cheap fade watch in
  `core/perception_plugin.py` samples action ticks — it never was before, the whole flag path was dead);
  reverse-edge reuse gated (bogus mints can't capture later scene changes); stranded places filtered from
  advertised frontiers. Golden replay fixture `eval/fixtures/starter_cutscene_pose/` + regression tests.
  2 adversarial reviewers (one REPRODUCED a surviving bug variant through the fixture — single-dir cutscene
  steps could still mint; fixed via the fade gate) + a Sonnet re-review of the shared-core fade watch (clean;
  open empirical gap: fade false-positive rate on dark caverns unmeasured). Stairs (no fade) now re-anchor
  honestly instead of transiting — a known, accepted behavior change.
- **PR #43 (merged) — GBA + NDS wired into `world_mcp`:** emulator dispatch by ROM extension (.nds→DeSmuME,
  .gba→mgba `GBAEmulator`, lazy imports), fixed the live-confirmed bug that `--game nds` built a PyBoy and died;
  `kirby_gba`/`emerald_gba` registered (`FollowCameraPerceiver` in `core/grid_perceiver.py`); GBA 10-button set
  (incl. l/r); `--record` fails loud for injected emulators (`--keep-frames` works — plugin-side); --rom/--game
  family validation; ROM-gated test skips (CI green). 424+ tests.
- **CROSS-GAME LIVE AUDITS (the constancy bet, 3 consoles, same brain, zero brain edits):**
  - **Emerald (GBA, $1.31):** booted title→naming→brief free movement (9 auto-walked tiles) via the WSL
    `~/gba-spike` env (launcher `runs/brain_emerald/`; mgba NOT in Docker). Ceiling: Emerald's long scripted
    intro chain (truck→mom→clock) ate the 40-cap — exactly the designed-but-unbuilt "patience/auto-advance"
    System-1 reflex. Also: naming screen needed `start` to confirm (`a` loops) — learned live by the brain.
  - **Kirby Super Star Ultra (NDS, $0.83 + $0.42 failed 1st try):** gameplay in ~16 decisions THROUGH the
    touch-driven save menus (`touch_target`), then real platforming (jump/inhale/float). **World-side gap it
    flagged: the NDS `observe` render is nearly EMPTY** (a context word; no touch_targets list/walls/outcome
    despite tool descriptions promising them) — the brain tapped save menus blind. Fix the NDS symbolic render
    next; also the side-scroller mismatch of the top-down grid autopilot is confirmed live.
  - **Docker image now supports NDS** (PR #45: libglib2.0-0/libSDL2/libgl1 + `SDL_VIDEODRIVER=dummy` —
    py-desmume imports fine but DeSmuME init dlopens these; found by iterating a FREE in-container JSON-RPC
    probe, each error naming the next lib). Image rebuilt locally with the fix; **merge #45** to make it stick.
- **⇒ NEXT (in order of leverage):** (1) **NDS symbolic render** — surface touch_targets/walls/outcome in
  `observe` (the Kirby audit's #1 gap; world-side, small). (2) **"Patience" auto-advance reflex** (designed
  2026-07-02, now demanded by TWO worlds: Emerald's intro chain + Red's cutscene cost). (3) **Static-object/
  referential grounding** (the keystone: "the Poké Ball", "Oak's lab" — the It1 bridge was brief-side, not
  perception). (4) Un-bridge the Red brief (remove the table-location hint) once (3) exists and re-audit.
- **Ops:** account-B runs tonight totaled ≈ $16 across 8 sessions, no 429s. Reviewer-model policy (David):
  Sonnet by default, Opus for risky shared-core. Merge policy: David authorized #43/#44 explicitly; new PRs
  (e.g. #45) still need his click or per-PR authorization. Agent-teamwork gotcha: two implementers sharing the
  main working tree collided (branch switches discard sibling edits) — use `git worktree` per agent, always.

**⇒⇒ (2026-07-02) — IT1 DIALOG-PERCEPTION FIXED + VALIDATED END-TO-END; PR #41 MERGED (main `2360713`).
Brain now clears Oak's whole intro cutscene and reaches the lab + starter prompt. Party still 0 — remaining
blocker is the INTERIOR POSE bug (task #7). This supersedes the 07-01 "task one dialog short" item below. ⇒⇒**

- **Root cause found by measuring, not guessing.** The 07-01 stall ("brain flew blind at Oak's intercept") was
  NOT a decoder problem. An offline probe on the recorded frames (`runs/brain_red_starter/world/frame_*.png`)
  showed `textbox.decode()` reads the intercept text **perfectly**. The real bug: `core/perception_plugin.py::`
  `_render_symbolic` **never surfaced `sym.screen_text`** (a regression from the lean-plugin migration #39) — the
  decoded dialog was computed and silently dropped before reaching the brain. Every "decode is broken → use OCR/
  VLM/upscale/auto-calibrate the font" hypothesis was DISPROVEN by the probe. **Lesson: probe recorded frames
  before building.**
- **The fix (PR #41, merged):** `_render_symbolic` now routes a `_TEXT_CONTEXTS` allowlist
  (`dialog/menu/battle/battle_text`) to a text render (decoded text + a decision hint, no stale spatial lines);
  `screen_text` is logged to `oracle.jsonl` for verification. Review caught a **cross-game regression** (my spec's
  `!= "overworld"` would have collapsed cave_noire/gauntlet's exploration render — grid perceivers emit
  `gameplay/static/menu/unknown`, never `overworld`); fixed via the allowlist + a regression test. 412 tests.
- **Validated e2e (account B, $2.21, 53 decisions, clean):** `screen_text` populates live (26 steps); the brain
  **read Oak's entire cutscene** ("…Don't go out!" → "You need your own POKéMON…" → "Here, come with…" → lab:
  "GARY? Gramps!") and **reached map 40 = Oak's Lab + the "which POKéMON do you want?" prompt** (last run died at
  map 0). Nav 0→37→38→40. The exact 07-01 blocker is GONE.
- **⇒ NEXT (task #7 — the binding work): the INTERIOR DEAD-RECKONING/POSE bug.** At the starter table the pose
  resets to (0,0) with `up` mis-walled, so the brain can't align onto a specific Poké Ball tile — every `up`+`a`
  re-triggers Oak's generic prompt instead of a ball's YES/NO. Same false-transition/pose-corruption family as the
  07-01 `(5,-5)` break and Cave Noire's drift. Fix pose stability in interiors (hold/repair during scene changes;
  stop minting bogus places), build it so a later absolute localizer (the `AvatarLocalizer`, PR #21) can replace
  it, then re-run the account-B audit to score **party 0→1**.
- **Design decided this session (NOT built — gated follow-ups):** (1) **"Patience" = a System-1 auto-advance
  reflex**, not a brain trait: settle-to-stable before perceiving (also fixes the pose churn), then mash the
  world's advance-input through plain no-choice dialog WITHOUT waking the brain — keyed on STATE (gated-static /
  choice / free-control), not a hardcoded button; the advance button LEARNED by control-grounding (same thesis as
  button↔effect / AvatarLocalizer); **never auto-commit a choice** (default-to-wake, the erase-save guard). Lift
  `battle_subscreen` to `core/` as its base. (2) **Dialog-text generalization = auto-calibrate the font**
  (cluster recurring text tiles → one-time VLM/OCR label → cheap template match at runtime), NOT hardcode a
  per-game table and NOT a per-frame VLM — build when a novel-font held-out world forces it (climb the North Eye
  ladder on measured need).
- **Ops:** account-B subscription `claude -p` runs are **pre-authorized** (run without per-run approval — see the
  `claude-p-run-authorization` auto-memory); infra confirmed ready (WSL claude + `~/.claude-b` + Docker up).
  Rebuild the `gb-mcp-world` image after any code change before a run (it COPYs `core/`/`games/`).

**⇒⇒ (2026-07-01, night) — IT1 SEAM *CLOSED* END-TO-END + GENERALIZED TO 3 GAMES; PR #39 MERGED.
This SUPERSEDES the cold-start bridge below (its "loop NOT closed / #38+#36 open" is now stale). ⇒⇒**

- **The loop is CLOSED.** For the first time in any world, a real System-2 brain (`claude -p`) drove a game
  live through the inverted ADR-001 MCP seam **end-to-end**. On **Pokémon Red**, then **generalized live to
  Cave Noire and Gauntlet** with the SAME brain (only the perceiver + task brief differ) — the north-star
  constancy bet, validated across 3 games. Dual-process cost held (the free `explore`/`goto` autopilot did the
  routine travel; the brain woke only at decisions and stopped when a wake stopped paying).
- **It1's *mechanism* is proven; its *task* is NOT yet complete.** Red reached Oak's intercept but stalled one
  dialog short (party stayed 0). **Every game's ceiling was world-side PERCEPTION, never the brain:** Red =
  dialog decode fails + pose breaks during `dialog` (the perceiver's `context['transition']` fade signal isn't
  wired through the lean path); Cave Noire = dead-reckon drift sealed it in (the strand bug); Gauntlet =
  wall-staleness. Full write-up + numbers: **`reports/2026-07-01-it1-close-status.md`**.
- **Merged this session:** **#38** (NDS touch coarsening → `main`); **#39** (Pokémon Red wired into
  `world_mcp.py` as a lean `PerceptionPlugin` world — heavy `PokemonRedPlugin` archived to
  `games/pokemon_red/_archive/`, 5 pre-seam drivers retired, `eval/score_red_task.py` added; reviewed, 411
  tests). **Closed:** **#36** (NDS navigator — not needed for It1; it broke clean-checkout tests). Red is now a
  registered game: `GAMES["pokemon_red"]`, `watch` = x/y/map/party/badges → oracle only, never on the wire.
- **⇒ NEXT (task #5 — the binding work):** the **perception fix** — decode the forced-dialog text
  (`games/pokemon_red/textbox.py`), hold/repair pose during `dialog` context, and wire the
  `context['transition']` fade signal (the lean generic `core/gb_emulator` lacks `faded()`). Then **re-run the
  account-B audit to complete It1's task (party 0→1)**. Cave Noire's drift is the same perception family.
- **Ops (new):** paid `claude -p` runs go on a **2nd Claude account** via `CLAUDE_CONFIG_DIR=~/.claude-b`
  (account A hit its 5-hr session cap; the limit is account-level). A fresh config treats the workspace as
  untrusted → pass `--mcp-config .mcp.json` + pre-set `projects[<cwd>].hasTrustDialogAccepted`. See the
  `mcp-claude-p-harness` auto-memory. Make Pokémon start-states with `make_state.py` (robust), not `new_game.py`.
- **Still open (low priority):** `chore/archive-report-run` branch (report_run archive) has **no PR yet**;
  README's dead `play_pokemon.py` refs + stale eval scorers (`score_perception`/`tune_threshold` still read the
  old *flat* oracle schema, broken since the nested-`watch` seam) — noted, not urgent.

**⇒⇒ COLD-START BRIDGE (2026-07-01 session end) — READ FIRST if resuming with no chat history. ⇒⇒**
The chat history was wiped; this block + the ones below are the only continuity. Run `git fetch origin` +
`gh pr list --state all` before trusting local state.

- **Three open threads (all 2026-07-01):**
  - **PR #38 (OPEN, merge-ready) — THIS branch `feat/touch-target-coarsening`:** the `touch_target(id)`
    coarsening (Stage-1-front). Block directly below. 428 tests, frozen untouched, reviewed.
  - **PR #37 (MERGED → `main`):** ADR-003, the embodiment north-star contract (doc-only). Block below.
  - **PR #36 (OPEN, merge-ready) — branch `feat/nds-reachability`:** the boot-to-gameplay navigator arc +
    UI-TARS hybrid, LIVE-VALIDATED across 27 games (the biggest recent chunk). ⚠ **Its HANDOFF detail — the
    06-29/06-30/07-01 hybrid + validation blocks, the `a`-collapse finding, the env/server notes — is NOT on
    this branch or `main`. Read it: `git show origin/feat/nds-reachability:HANDOFF.md`.**
  - **⇒ Merging #36 then #38 to `main` consolidates all three arcs' HANDOFF onto `main` (fixes this
    fragmentation). David's call — do NOT self-merge.**
- **Servers (WSL, user `nvidia`, RTX-3080):** **UI-TARS-2B is UP on `:8080`** (`UI-TARS-2B-SFT-Q4_K_M` +
  `mmproj-Qwen2-VL-2B-Instruct-f16`, `--image-min-tokens 1024`); text `:8081` DOWN; the two original 3Bs
  stopped. Health-check `curl :8080/v1/models`. Restore UI-TARS (from WSL, detached):
  `setsid nohup /home/nvidia/llama.cpp/build/bin/llama-server -m /home/nvidia/models/UI-TARS-2B-SFT-Q4_K_M.gguf
  --mmproj /home/nvidia/models/mmproj-Qwen2-VL-2B-Instruct-f16.gguf -ngl 99 --host 127.0.0.1 --port 8080 -c 4096
  --no-webui --image-min-tokens 1024 >/tmp/uitars.log 2>&1 &`. ⚠ Drive WSL via a script file + PowerShell, not
  inline (the `wsl-command-quoting` auto-memory has the pattern).
- **North-star position:** the on-ramp is built (GB/GBA/NDS world-interfaces, a System-1 perception + reflex
  floor, the `ai-aria`-over-MCP seam) but **the loop is NOT closed — no human-grade task has been run
  end-to-end through the aria brain in any world.** Migration: Stage 0 done (#37), Stage-1-front done (#38); the
  rest is gated on It2/It4. **Binding constraint = close It1** (Pokémon Red · the `ai-aria` brain · one task ·
  measure success / constancy / wakes). Everything else — including all three PRs above — is scaffolding for that.
- **Gone with the wipe (session-local scratchpad):** the sweep / montage / server-launch scripts + the 27 hybrid
  strips. The 3 hybrid contact-sheets ARE committed (on #36 at `reports/assets/2026-07-01-hybrid-validation/`);
  re-derive sweeps from `eval/bakeoff.py`.

**⇒ NEWEST (2026-07-01, evening) — STAGE-1 FRONT: NDS touch coarsened to `touch_target(id)` (soft, no contract
change). On branch `feat/touch-target-coarsening`, off `origin/main`; PR #38 (merge-ready).**
- **What landed:** a coarse `touch_target(id)` tool on `NDSPerceptionPlugin` (`core/nds_perception_plugin.py`) —
  resolves a 0-based id against the perceiver's already-surfaced `spatial_memory["touch_targets"]` (area-sorted)
  → the target's center → the existing tap machinery (extracted to a shared `_tap()`). No raw coordinates on the
  wire. Wired end-to-end: advertised in `tools()`, mirrored into `world_mcp._NDS_ACTION_TOOLS` (freshness) + the
  NDS sandbox allowlist (`_nds_sandbox`) so the Gateway permits it. Raw `touch(x,y)` KEPT as a fallback (the blob
  detector misses some targets).
- **Why:** the Stage-1-front skill-coarsening from ADR-003 — fixes the "coordinate leak" (blind touch coords are
  exactly what tapped Mario Kart DS through "erase all save → OK" in the hybrid validation). Same coarsening as
  `goto`/`navigate`.
- **Guardrails:** frozen `core/contracts.py` UNTOUCHED (soft; empty diff verified throughout). 428 tests (+13).
- **Reviewed (merge-ready):** adversarial review DISPROVED a cache-staleness/TOCTOU risk — the MCP driver
  re-`observe()`s after every action (`world_mcp.World.call`), so `_last_touch_targets` can't go stale. Gating
  parity + freshness + all reject-paths confirmed. Two low-severity fixes applied (count `touch_target` as a wake;
  correct a misleading cache comment). *(Implementer crashed mid-run on a transient API overload; resumed cleanly,
  no work lost.)*
- **Caveat:** `touch_target` is wired through the full contract surface but NOT yet exercised by a live agent
  (no aria Brain wired to a game — that's It1); cache-resolution correctness is covered by an e2e unit test.
- **⇒ NEXT:** merge #38; then the migration is parked at the gate again — the rest of Stage 1 (full
  skill-coarsening: `navigate_to`/`interact`) and Stages 3–4 wait on It2/It4. Binding constraint remains
  closing **It1**.

**⇒ NEWEST (2026-07-01, later) — STAGE 0: embodiment north-star contract recorded (ADR-003, doc-only). On
branch `docs/adr-003-embodiment-contract`, off `origin/main`.**
- **What landed:** ADR-003 (`reports/_archive/2026-07-01-adr-003-embodiment-north-star-contract.md`) records
  the externally-designed Embodiment Universal Contract (UEC) as the documented north-star target; the UEC
  scaffold is vendored read-only at `reports/_archive/embodiment-stone-layer-v0.2/`; the originating migration
  analysis is internalized at `reports/_archive/2026-07-01-migration-embodiment-contract.md`.
- **The key correction:** the migration doc's "~80% congruent, ONE delta" claim was **understated** — this
  session's line-by-line comparison found **~4 real structural deltas** (cost scalar→vector; reversibility
  semantics inverted; params JSON-Schema→type-strings; events stream→soft observatory), not one. ADR-003 is now
  the authoritative mapping.
- **Guardrails:** the frozen v1 (`core/contracts.py`, `CONTRACT_VERSION = 1`, hash-pinned in
  `tests/test_contract_frozen.py`) is **untouched** — this is doc-only. Deltas are gated to the roadmap rung
  that forces each: skill-handle coarsening at **It2**, the reversibility cost-vector (first
  `CONTRACT_VERSION = 2`) at **It4**. Nothing lands speculatively before its rung.
- **Collision fix:** the vendored scaffold ships its own `tests/` package, which pytest's rootdir-relative
  import would otherwise resolve to the same dotted module name as this repo's `tests/test_contract_frozen.py`
  and abort collection repo-wide. Added `reports/_archive/embodiment-stone-layer-v0.2` to
  `[tool.pytest.ini_options] norecursedirs` in `pyproject.toml` — verified collection count unchanged
  (415 tests, identical IDs, before/after).
- **⇒ NEXT:** nothing until It2 forces skill-coarsening (or It4 forces the cost-vector). ADR-003 stays
  PROPOSED in `reports/_archive/` — not promoted into `ARCHITECTURE.md` — until its gate passes.

**⇒ NEWEST (2026-06-26, late) — AVATAR-LOCALIZATION BAKE-OFF (the baseline wins) + the RELATIVE-MOTION pipeline
as the next build. Branch `feat/avatar-localization` (commit `4ef895b`; off `main`, NOT PR'd). SIBLING work on
PR #25 (`feat/adr-002-gate`): the cross-game consequence study + perception-needs report — `git fetch` +
`gh pr list --state all` to see both.**

- **Why we got here:** the cross-game consequence study (PR #25) + mining the play-subagent transcripts
  reprioritized the roadmap toward avatar-localization + blob-segment (the agents' #1/#3 blind spots were
  self-localization/walkability + mode-detection — `reports/2026-06-26-perception-needs-from-play-transcripts.md`).
  A deep-research sweep then grounded the methods.
- **RESEARCH GROUNDING (`reports/2026-06-26-avatar-localization-blob-segmentation-research.md`):** our
  `AvatarLocalizer` action-correlation IS the canonical method (Bellemare *contingency*, AAAI 2012); `best_shift`
  is the RIGHT ego-motion for flat pixel art (do NOT switch to ORB/homography). Blobs = connected-components on a
  foreground mask. Climb to a learned model only on MEASURED failure (VLM grounding is documented to fail; Cradle
  uses SAM only for hi-res desktop, not 160×144).
- **THE BAKE-OFF (`eval/compare_localizers.py`):** implemented + scored 4 methods vs `datasets/labels/v2`.
  **Baseline WINS — fixed 36% / follow 21% in-box, wins 7/10 games, Cave Noire 56%/4px. None beat it:** Bayes
  (28/9 — ties on fixed but costlier; caught+fixed a log-vs-prob-blur bug), Blob (29/17 but bg-sub floods
  spurious blobs, precision 6% — useful only as an AUXILIARY: entity bboxes / a peak-veto), Scroll (13/9 —
  counterproductive: `best_shift` strips the avatar's own motion). New code: `core/blob.py` (pure-numpy CC —
  scipy NOT installed, don't add it; no OpenCV), `core/localize_{bayes,blob,scroll}.py`, 20 tests, 370 green.
- **THE STRUCTURAL FINDING (the "wall"):** all 4 are MOTION localizers → they need the avatar to move ON SCREEN.
  Works for FIXED-camera (avatar moves on a still screen); FAILS for FOLLOW-camera (avatar stays centered, the
  WORLD scrolls → no motion to ground → ≈0% on Gold/Space Invaders). Not a method flaw — follow-camera
  localization is a DIFFERENT problem: world-position via ego-motion integration, not sprite-finding.
- **⇒ NEXT BUILD = the RELATIVE-MOTION pipeline (`reports/2026-06-26-relative-motion-pipeline.md`):** ① camera
  motion (`best_shift`) → world position (sum it) + a fixed/follow router; ② object motion = the RESIDUAL after
  camera-compensation → control-correlation picks the avatar, blob → entities; ③ fuse (Kalman/odometry + occasional
  absolute fixes for drift). UNIFIES both camera classes (camera term = 0 → fixed; ≠ 0 → follow — one pipeline).
  **The one hard part = a CLEAN residual in ② (compensation noise + animation flicker + scroll-edge reveals = the
  blob-precision problem).** Don't build a fancier screen-localizer.
- **DECISION:** keep the baseline as the fixed-camera localizer; bank the bake-off by-products (`core/blob.py`,
  `compare_localizers.py`, tests); the 3 losing localizer variants are experiments (PR-or-archive TBD, David's call).
  Aim next effort at the relative-motion pipeline + walkability/mode-detection.

**⇒ NEWEST (2026-06-26, latest) — AVATAR LOCALIZER BUILT + CROSS-GAME VALIDATED (the strand fix's foundation).
PR #21 OPEN (`feat/avatar-localizer`). Merged this session: #18, #19 (North Eye constitution), #20 (label
dataset + tooling). `main` = `f4be920`. Picking up COLD? `git fetch` + `gh pr list --state all` first.**

- **The strand bug ROOT CAUSE (RAM-proven, then acted on).** The occupancy map dead-reckons a *noisy binary
  move-signal* with no absolute correction → unbounded drift → the strand. The cheap **"entry-openness"
  wall-guard was built, closed-loop tested, and REVERTED** as a band-aid (it turned the give-up into a
  *livelock* — same 7 RAM tiles; proof in the cn_open closed-loop run). Root cause = the move detector, not the
  wall logic. David's call: **build the foundational fix, not more band-aids.**
- **The foundational fix = ABSOLUTE AVATAR LOCALIZATION (`core/localize.py`, PR #21).** Control-grounded, per
  the North Eye constitution: *the avatar is the thing your buttons move.* Each commanded step, accumulate a
  **decaying per-cell heatmap of the motion EXPLAINED BY the commanded direction**; the peak is the avatar
  (enemies/animation move uncommanded → wash out); **hold** when stationary. Output `(col,row,conf)` or `None`
  (never fabricates). R0 numpy, **no RAM**. *(A first TLD/NCC-template version was built and REJECTED BY
  MEASUREMENT — locked early + drifted, 0% in-box; a diagnostic showed action-correlation alone localizes to
  1–15px, so the decaying-heatmap, no NCC, is the design — 7s/game.)*
- **VALIDATED vs the hand-label GT (`eval/validate_localizer` on `datasets/labels/v2`):** **Cave Noire
  59% in-box / 4px** (beats the motion-centroid baseline 41%/12px — and bounded → **no drift → kills the
  strand**), SML 42%/9px. **Works for fixed-camera + avatar-moves-on-screen; FAILS on follow-camera** (the
  command scrolls the *whole screen* → world-position there is **ego-motion `best_shift`**, not
  avatar-localization — honest camera-class scope, not papered over). Cross-game motion baseline
  (`eval/score_localize`): `avatar=mover` 2–5% in 9/10 games → motion localization is Cave-Noire-only;
  control-grounding is what generalizes.
- **HAND-LABEL DATASET (PR #20, merged) — the GT for all perception primitives.** `datasets/labels/v1` (110
  frames) + **`v2` (13 games · 250 frames · 1146 boxes)**. Tooling: **`eval/label_frames.py`** (interactive:
  per-frame **mode** + bounding boxes for avatar/enemy/item/text/health/exit/npc; text/health carry the **read
  value** = OCR GT; **varied farthest-point sampling**), **`eval/snapshot_labels.py`** (versioned freeze +
  manifest — cut the next with `--version v3`). Caveats: `red_resume` is 100% menu (re-record into gameplay);
  OCR-value coverage is sparse (7%, early games only).
- **NORTH EYE CONSTITUTION (PR #19, merged) — `reports/north-eye-perception-constitution.md`.** Marr-for-
  embodiment + a **7-slot primitive contract** + the **Realizer Ladder** (R0 cheap pixel ops → R1 classical/
  tiny-learned → R2 fine-tunable small CNN → R3 zero-shot VLM; climb only on a *measured* bar). Design
  discipline, NOT a build order; the AvatarLocalizer is its first L2 instance (R0).
- **⇒ NEXT (task #14 — the strand-fix payoff):** **wire the AvatarLocalizer into the Cave Noire perceiver** as
  an absolute pose source (replace the dead-reckoned cursor in the `GridPerceiver`/`MoveSignal` path) →
  **closed-loop on `cn_open.state`** (cover >7 RAM tiles, no strand/livelock) → then re-run the clean model
  comparison (real numbers + `--record` videos). **DEFERRED:** the follow-camera dual (avatar = the region that
  *stayed put while the background scrolled* + a center prior; world-pos there stays `best_shift`); and an R1
  appearance climb only if a future primitive measurably needs it.
- **KEY FILES:** `core/localize.py` · `eval/validate_localizer.py` (GT scorer) · `eval/score_localize.py`
  (motion baseline) · `eval/probe_avatar_localize.py` (earlier RAM probe) · `eval/label_frames.py` +
  `eval/snapshot_labels.py` + `datasets/labels/` · `reports/2026-06-26-avatar-localizer.md`. **341 tests green;
  import-boundary + no-leak intact; `core/contracts.py` untouched.** Many stale local branches exist (merged) —
  safe to prune.

**⇒ (2026-06-26) — PERCEPTION CONSTITUTION (MERGED: PR #19): `reports/north-eye-perception-constitution.md`.**
A timeless design discipline for perception primitives — Marr's
three levels updated for embodiment (closed-loop grounding, coupled/time-bound implementation, minimal
task-sufficient signal, movable fixed↔learned boundary, probabilistic outputs) + a **7-slot primitive contract**
+ the **Realizer Ladder** (R0 cheap pixel ops → R1 classical/tiny-learned → R2 fine-tunable small CNN → R3
zero-shot VLM; climb only on a measured bar). It's a **constitution, not a build order** (gate-first still
governs). Frames the `MoveSignal` camera-class split as the canonical violation and the `AvatarLocalizer` work as
its first L2 instance. (Status SUPERSEDED — see the TOP block: the `AvatarLocalizer` is built + validated on
PR #21.)

**⇒ (2026-06-25) — TWO THINGS: (A) the S4 MCP HARNESS IS BUILT + END-TO-END VERIFIED; (B) a MAJOR NEW
DIRECTION is set — ADR-002 (PROPOSED, gated): self-built ontology. Landed on `main` via PR #16 (harness) + PR #17 (direction).**

**▶ MCP HARNESS DOCKERIZED + FIRST MODEL COMPARISON (2026-06-25, on PR #18 `docs/phase-a-and-mcp-testing`; not yet merged).**
- **`world_mcp.py` runs as a Docker container** (`gb-mcp-world`, `docker run -i`) — fixes a Windows node-spawn
  failure ("filename/directory/volume syntax incorrect") that made the server show "not connected" in Claude
  Code. Now GAME-AGNOSTIC via `--game` (cave_noire+gauntlet registry), `--record` (MP4 → `<out>/session.mp4`),
  lazy emulator boot (instant `initialize`), plugin-close on stdin EOF (finalizes the recording). ROMs mounted
  ro (not baked in); `runs/` mounted. The portable brain↔world seam: Claude Code now, **ai-aria later, same `docker run -i`**.
- **Testing method = Claude-over-MCP:** a real Claude (**headless `claude -p`**, `CLAUDE_CODE_OAUTH_TOKEN` from
  `../aria-mcp-test/.env`, `--allowedTools mcp__cave-noire-world` = sandboxed to the 7 game tools) IS the
  System-2 brain. Launcher dir: `../aria-mcp-test/` (`.mcp.json` + brief). Per-model configs: `runs/mcp_cfg_*.json`.
- **First comparison (opus/sonnet/haiku):** harness VALIDATED end-to-end, but the result is **CONFOUNDED by a
  WORLD STRAND-BUG** — all 3 trapped identically by the first `explore` into a walled pocket (Opus diagnosed it:
  *"frontiers listed-but-unreachable, start cell mislabeled-unexplored"*). NOT a clean ranking (qualitatively
  Opus led: 7 decisions, correct diagnosis, stopped cleanly). Report: `reports/_archive/2026-06-25-model-comparison-mcp.md`.
- **Per-session MEMORY (retrospective) IS persisted:** each run dir `runs/2026-06-25_cavenoire_mcp_{opus,sonnet,haiku}/`
  holds `oracle.jsonl` (game record) + `run.log` (final narration) + **`transcript.jsonl` (the FULL brain transcript
  — every turn, tool call, and `remember` lesson).** Claude Code auto-saves these in `~/.claude/projects/E--…-aria-mcp-test/`;
  co-located here for review. (Future runs: copy the newest `.jsonl` from there, or launch with `--output-format stream-json`.)
- **⇒ OPEN (the real blocker): the STRAND BUG** — occupancy-map says frontiers exist but they're unreachable +
  the start cell is mislabeled unexplored (likely the dead-reckoning / false-MOVE family). Fix it OR capture a
  more-open `cn_open.state`, then a clean `--record` re-run per model = real numbers + videos. Score with
  `eval/_archive/score_mcp_runs.py`. PR #18 also carries ADR-002 Phase A (life oracle `0xD389`) — merge when ready.

**▶ STARTING WORK? The active task is the ADR-002 GATE PROBE (see (B) + ⇒NEXT below). Before writing ANY code,
read `reports/_archive/2026-06-25-adr-002-ontology-discovery.md` — §9 (the gate) and §11 (anti-drift tripwires). The MCP
harness (A) is DONE and verified — do not rebuild it. Do not start the re-architecture until the gate PASSES.**

**▶ PHASE A DONE (2026-06-25) — `reports/_archive/2026-06-25-phase-a-hud-grounding-precheck.md`. 2 of 3 gate
pre-conditions met; the gate's SHAPE is NOT yet confirmed (Check 2 is the keystone and is AMBER). GREEN: HUD =
DIGITS visible during gameplay ("HP 8/10 ENEMY 1/3 B 2F") → `read_text` is right, life groundable continuously;
the LIFE ORACLE EXISTS, found `0xD389` (the unique byte matching visible HP 7@f100/10@f500 — reproduce from a
clean checkout via the committed fixture `eval/_archive/find_hp_addr eval/fixtures/cavenoire_hp_oracle --anchors 0:7 1:10`;
caveat: reads 15 on 4/4000 transition frames, single-run → clamp to ≤max when scoring),
now wired `watch={...,"hp":0xD389}` (oracle.jsonl only). Decoys (enemy/floor counters) are *enumerable* but not
usable until Check 2. AMBER/keystone = Check 2: a pixels-only consequence INDEPENDENT of the HP digits is NOT
isolated (≥1 of 29 HP-drops is transition-confounded; frequency unmeasured) → without it §9's decoy-rejection
arm can't be scored, so NO promotion/claim. Phase A itself was OFFLINE RAM/frame inspection (no MCP, no Claude
brain). The gate RUN (Phase D) WILL use a real Claude over MCP (`world_mcp.py`, not scripted brains): the brain
hypothesizes "region R = my life"; its detector is scored vs the `hp` oracle. Next = Phase B (operationalize
§9's metric/threshold), then Phase C (build `read_text`/`whats_changed`/`consequence`).**
- **(A) S4 MCP server — `world_mcp.py` (PR #16, open).** Exposes Cave Noire as an MCP stdio server (stdlib, NO
  new dep) so a FRESH Claude Code instance is the System-2 brain (ADR-001 S4 realized). Tools: `observe`
  (symbolic-only — no pixels) · `explore`+`goto` (free System-1 autopilot; dual-process — woken at decisions,
  not every tile) · `press_*`/`wait` · `remember` (within-run lessons) + a wakes-per-progress (cells/decision)
  cost signal. No-leak (RAM → oracle.jsonl only). **4 adversarial reviews, all findings addressed.** END-TO-END
  VERIFIED: a real MCP-client session ran handshake→tools→decision-loop→world-responds, 0 protocol errors, on an
  OPEN cavern (`runs/cn_open.state`, hand-captured + verified; cells/decision climbs as `explore` covers ground).
  Launcher (a clean-slate fresh-Claude-Code brain) lives OUTSIDE the repo: `../aria-mcp-test/` (`.mcp.json` +
  thin brief), wired to `cn_open.state`. **To run it: open a fresh Claude Code in `../aria-mcp-test/`, approve
  the `cave-noire-world` server, say "observe, then explore."**
- **(B) ADR-002 (PROPOSED, GATED) — `reports/_archive/2026-06-25-adr-002-ontology-discovery.md`. The direction; NOT yet
  built.** Move the hand-code/learn boundary DOWN: a small fixed `core/` **sensorimotor floor** (change · motion ·
  ego-motion · blob-segment · track · recognition-hash · glyph-read · emit-input · action↔effect · **consequence
  detector**) + a per-world ontology the **BRAIN hypothesizes** from priors and **BEHAVIOUR grounds** (=truth),
  compiled to System-1 skills. Seam → **queryable** (interrogate perception). Constancy → **the loop, not the
  schema**. Existence proof: the tile→function map already does this for walkability. **ADR-001 stays Accepted
  until grounded.** Memory: `architecture-v2-ontology-discovery`.
- **⇒ NEXT (agreed sequence):** (1) **roadmap/plan v2 — DRAFTED (PROPOSED, gated):**
  `reports/_archive/2026-06-25-roadmap-v2-discovery-loop.md` — recasts the per-world UNIT from *"hand-build a perceiver"* to
  *"run the discovery loop"* (the ladder/discontinuities/invariants are unchanged); 4 rungs, gate-first (Rung 0 =
  the probe; PASS→promote, FAIL→fall back to ADR-001 cheap). Does NOT touch `ROADMAP.md`. (2) **minimal e2e = THE
  GATE PROBE (Rung 0 — the active build)** — evolve `world_mcp.py` into the sensorium
  (add `read_text` + `whats_changed` + a `consequence` signal + a thin hypothesize/confirm surface), then run the
  **HUD-grounding probe**: brain hypothesizes *"region R = my life"*, **SCORE its grounded life-detector vs the
  RAM oracle** as it plays. PASS → promote ADR-002 + generalize to entities; FAIL → the direction dies cheap.
- **⇒ DON'T DRIFT (full tripwire table: ADR-002 §11):** GATE FIRST — build / promote / claim NOTHING until the
  HUD probe PASSES vs the oracle. Build the discovery **LOOP, not a bespoke Cave Noire combat perceiver** (that
  per-game pattern is the exact drift ADR-002 kills). Only the **2–3 primitives the gate needs**, not the whole
  floor. ADR-002 stays **PROPOSED** — do NOT overwrite `ARCHITECTURE.md`/`ROADMAP.md`. The `consequence` signal
  is **pixels-only** (oracle = scorer, never a sense, never the grounding signal). Within-run only (blank every
  run). Keep `world_mcp.py` symbolic-only — no screenshot-to-brain.
- **⇒ DESIGN BACKLOG (2026-06-25 brainstorm — future visits/experiments, all gate-sequenced):**
  `reports/_archive/2026-06-25-design-backlog-future-experiments.md` — the senses toolbox, `focus`/foveated attention, the
  spatial scratchpad (L1 grounded / L2 hypothesis), entity-via-motion, the fit-method-to-data law, and the PARKED
  It3+ items (action-chunking + VLA distillation, "time-in-world → speed"). Includes the cheap-probe list. Nothing
  there is a build order — it's all behind the Rung-0 gate.
- **OPEN PRs/issues:** PR #16 (`world_mcp.py`) · issue #15 (false-MOVE backstop residual: fixed-lag-4, blind to
  period-3 animation). PR #14's false-MOVE-shipped HANDOFF block was **folded into this doc** (the block directly
  below) and #14 closed. For David's merge/triage.

**⇒ (2026-06-25) — THE CAVE NOIRE FALSE-MOVE RUNAWAY IS FIXED + SHIPPED (PR #13, squash-merged to `main`
2026-06-24 as `06dc9dd`; 341 tests green, re-confirmed 2026-06-25). SUPERSEDES the part-2 ⇒FOUND/⇒OPEN items
below — the false-MOVE blocker is CLEARED.**
- **The fix = two parts, both in `core/grid_perceiver.py`, both closed-loop validated (NOT either/or).** The
  part-2 ⇒FOUND guess (a "structural translation-check") was REFINED by a measure-first probe
  (`eval/probe_phantom_move.py` + `eval/_archive/probe_spatial_move.py`, RAM = oracle): (1) **grid-max move signal** — the
  per-step signal is now the max per-cell change on an 8×8 grid (`ForegroundSignal(fg_grid=58)`; Cave Noire wires
  `_FG_GRID=58`), which localizes the sprite spike the whole-frame residual DILUTES (AUC **0.99 vs 0.86**, pure
  numpy, no deps — "measure WHERE the change is, not how much," minus the CNN); (2) **no-progress backstop**
  (`_RUN_GUARD=4, _PROG_W=4, _PROG_MIN=4.0`) — grid-max still leaves a ~33% runaway tail no per-step pixel signal
  can catch, so a sustained same-direction run that isn't visually progressing is demoted to a no-move → the
  existing wall-confirmation seals it. Constants grounded on the corridor regime (stuck p90 3.86 < 4.0 < real p10
  6.45); false-wall rate measured 1.5%.
- **Results:** closed-loop corridor phantom **65→0**, pose `[0,-70]`→`[-1,-3]` (runaway gone); offline replay drift
  **0.06→0.02** (better); Gauntlet unchanged (backstop inert — camera-scroll = progress). The probe rejected the
  fancy options (CNN/embedding = invariance machine, OOD on pixel-art; per-cell SSIM ties grid-max, no win) —
  survey in `reports/_archive/2026-06-24-visual-embedding-models-survey.md`. Full record: `reports/_archive/2026-06-24-phantom-move-probe.md`.
- **Open caveat (carried, not blocking):** `_FG_GRID=58` and the 0.99 AUC derive from a SINGLE human recording;
  generalization to a different dungeon / flicker level / session is unvalidated — treat 58 as a calibration
  constant to re-check on new corpora. The closed-loop corridor is `n_real=1` for discriminability (it validates
  the phantom RATE, not separability).
- **Nav goal now PARKED** behind the ADR-002 gate (the active NEXT is the TOP block's gate probe). The false-MOVE
  blocker is cleared; a hand-played in-cavern save-state (`human_play.py` → `--init-state`) exists if nav is revisited.

**⇒ (2026-06-21 and earlier) — layered history below; the TOP block above is current.**

**⇒ NEWEST (2026-06-24, part-2) — SHARED PERCEPTION INFRA LIFTED TO `core/`; Gauntlet + Cave Noire are now
THIN CONFIG; Cave Noire live loop CLOSED; an anti-drift guardrail added. On a PR branch
(`feat/core-perceiver-extraction`, PR #12); 338 tests green; both OFFLINE replay oracles re-run post-refactor
and unchanged → behavior-preserving on the oracle (verbatim output committed in
`reports/_archive/2026-06-24-part2-replay-revalidation.md`). Closed-loop surfaced a real defect the replay masks (below).**
- **The ossification debt is paid (INSIGHTS §2).** The occupancy-grid perceiver, the GB emulator, and the
  perception-only plugin were duplicated 3× across `games/`; they now live ONCE in `core/`: `core/grid.py`
  (DIRS/DELTA/BACK/EGO2DIR/DIR2EGO), `core/gb_emulator.py` (the generic PyBoy wrapper), `core/perception_plugin.py`
  (`PerceptionPlugin` — perception-only, watch→oracle, injectable flavor text), `core/grid_perceiver.py`
  (`GridPerceiver` + a `MoveSignal` strategy: `CameraScrollSignal` / `ForegroundSignal`). Gauntlet + Cave Noire
  perceivers/`__init__` are now ~25-line config (move signal + calibration + prompt). Pokémon stays the rich
  OUTLIER (place-graph/tilemap + reward/battle/fade) — deliberately not migrated. Deleted `games/gauntlet/{emulator,plugin}.py`.
- **Anti-drift GUARDRAIL (the lesson David forced).** The drift = building world #2/#3 by copying the Pokémon
  package instead of lifting primitives. New tripwire `tests/test_import_boundaries.py::test_lean_games_do_not_carry_their_own_infra`
  (no `emulator.py`/`plugin.py` outside `pokemon_red`) + a "primitive ossification" row in CONTEXT-BRIEFING's
  drift table + a laziness-ladder line in CLAUDE.md ("copying a sibling file = the lift signal").
- **Cave Noire live closed-loop wired (the unfinished half of PR #10).** `play_cave_noire.py` + the no-RAM-leak
  sentinel wall in `tests/test_cave_noire.py`. The unchanged `ExploreBrain`/`core/` ran the Cave Noire stack
  end-to-end IN-CAVERN — i.e. the ARCHITECTURAL constancy (brain code untouched when adding a world) holds by
  construction. **Task-level success is NOT shown** (a handful of confirmed moves, then dead-end / phantom
  runaway) — see the OPEN item.
- **⇒ FOUND (closed-loop) — the false-MOVE asymmetry BITES; a fix is the next follow-up (NOT in PR #12).**
  Two ExploreBrain runs from hand-played in-cavern save-states, scored vs the RAM oracle (`x=0xC504 y=0xC503`):
  open corridor **65 of 70** perceiver-"moves" were PHANTOM (idle animation pushed the foreground residual over
  `_FG_MOVE=1.5`; pose dead-reckoned to `[0,-70]` while the player was pinned at a wall); tight pocket 2/3.
  (An earlier N=4 run showed 0 phantom — but P(0|bug)≈0.86⁴≈0.55, statistical noise; that "did-not-bite" claim
  is RETRACTED.) **Measure-first probe killed the easy fixes:** real vs phantom residual INVERT and interleave
  across runs (real `{2.1,2.5}` < idle-phantom `{3.8}` < real `{6.0}` ≪ big-event phantom `{57,71}`), so no
  static threshold/band separates; `context==gameplay` catches only the menu phantom. The reliable fix is
  STRUCTURAL (translation-direction check or move-persistence confirmation, the twin of wall-confirmation) —
  its own probe + closed-loop validation. Evidence: `reports/_archive/2026-06-24-part2-replay-revalidation.md`.
- **⇒ OPEN — autonomous deep-dungeon nav** still needs the false-MOVE fix above + a navigation goal. The random
  `ScriptedBrain` can't traverse the JP hub menus to reach a cavern (watch registers frozen at the hub); a
  hand-played in-cavern save-state (`human_play.py` → `--init-state`) is the entry point and now exists.

**⇒ PRIOR (2026-06-24) — CONSTANCY VALIDATED ACROSS 3 WORLDS / 3 CAMERA CLASSES (brain + `core/` UNCHANGED).
`main` had Pokémon + Gauntlet + Cave Noire perceivers; PRs #7/#8/#9/#10 ALL MERGED. (part-2 core extraction, above, now done.)**
- **The thesis ("swap only the perceiver; reuse the brain") is demonstrated on 3 camera classes, brain code
  untouched:** Pokémon (follow-CENTERED, the original), **Gauntlet** (follow-SCROLL, PR #9), **Cave Noire**
  (FIXED camera, PR #10). The existing `ExploreBrain`/`Gateway`/`run_episode` drive each via only a new
  `games/<world>/` perceiver+plugin + a thin prompt. No RAM leak (fitness wall extended per world); import
  boundary green; frozen `core/contracts.py` intact.
- **Gauntlet (PR #9, merged) — follow-scroll, pose from `best_shift` camera motion.** Live closed-loop run
  (autonomous: `ScriptedBrain` mashes past the title → `--save-state` → `--brain explore`) NAVIGATED
  (RAM-confirmed) but surfaced the **camera DEAD-ZONE false-walls**: 95% of `blocked` outcomes were real moves
  the follow-camera hid (`best_shift≈0` when the player slides in the dead-zone). Fix `_WALL_CONFIRM=3`
  (seal a wall only after N persistent no-scrolls): traversal up in all 5 runs, moves +73%, phantom walls −40%.
  Pose stepped in EGO space (best_shift dominant axis, not last-pressed token: 0.31→0.02 drift); walls now
  bookkept in the SAME ego space (desync fix). `eval/_archive/replay_gauntlet_pose` = 83% heading / 0.02 drift.
- **Cave Noire (PR #10, merged) — FIXED camera, pose from FOREGROUND motion (the missing half of ego-motion).**
  `find_ram_addr` found player regs X=`0xC504` Y=`0xC503`; `best_shift` is 99% camera-static there (fixed cam),
  so the Gauntlet recipe maps nothing. **`eval/probe_foreground_motion`:** the camera-compensated RESIDUAL
  (best_shift's `best_diff`) is FOREGROUND/sprite motion — it separates a real move from a wall-bump when the
  camera is blind (AUC **0.86** Cave Noire / **0.76** Gauntlet). It's the COMPLEMENT to `best_shift`:
  `move = camera scrolled OR foreground residual high`. Camera-static share of real moves: Gauntlet 24% /
  Metroid 19% / Kirby 9% / Pokémon ~0% (always-centered = immune, why this never bit before). Cave Noire
  perceiver = Gauntlet structure with the move signal swapped to foreground + direction from the commanded
  button (4-dir turn-based). `eval/_archive/replay_cave_noire_pose` = **99%(W1)→85%(W40) net-dir, 0.06 drift** (offline).
  **Live closed-loop run NOT done** (no plugin/emulator/driver yet).
- **⇒ NEXT — PART 2 (now UNBLOCKED; both PR reviews endorse the exact design):** extract a SHARED `core/`
  occupancy-grid perceiver base parameterized by a **`move_signal(prev, cur, action) -> (moved, direction)`**
  strategy, and migrate the lean new perceivers onto it. The 3 new-style perceivers are **byte-identical except
  (a) the move signal** (camera-scroll vs foreground-residual) **and (b) the direction source** (ego token vs
  commanded button) — everything else (occupancy grid, frontiers, `_WALL_CONFIRM`, `affordances`, `_grays`,
  `_dominant_dir`, `_DIRS`/`_DELTA`/`_BACK`, `SymbolicState` assembly, the stripped emulator/plugin/`_render_symbolic`)
  is duplicated 3×. The extraction also resolves the **dead-zone + false-move residuals** (the move_signal can
  combine best_shift + foreground), the **copy-drift**, and `_DIRS`/`_DELTA` → a `core/grid.py`. (Pokémon's
  perceiver stays separate — it has the richer place-graph/tilemap; the shared base is for the lean perceivers.)
- **Live-run watch-items (carry forward):** (1) **Cave Noire live closed-loop** is the unfinished half — build
  plugin/emulator/driver + `ExploreBrain`; **false-MOVE asymmetry** (a move is trusted on a single foreground
  frame while a wall needs 3 → idle animation can false-step; candidate fix = symmetric move-confirmation, to be
  CLOSED-LOOP validated); **`CaveNoirePlugin` must ship the no-leak RAM-sentinel test** like Gauntlet's. (2)
  Gauntlet 8-way exploration via a 4-cardinal `ExploreBrain` (fix via LLM diagonal sequences, NOT a `core/` edit).
- **Reports:** `reports/_archive/2026-06-24-gauntlet-constancy.md`, `2026-06-24-cave-noire-fixed-camera.md`. Side-scrollers
  (Kirby/Metroid, 1D/warps) + 3D (Doom) remain later phases. Guardrails unchanged (held-out never tuned; corpus
  gitignored on D:; GBC banked WRAM).

**⇒ NEWEST (2026-06-23, latest) — CROSS-GAME RAM-GROUNDED EGO-MOTION (Eval C) DONE; the P1 cross-game thread is
CLOSED. `best_shift` recovers self-motion DIRECTION on 3 NON-Pokémon games. `main` = `2e10e18`, 308 green; Eval C
+ report are LOCAL/UNCOMMITTED (see ⇒NEXT — needs a commit/PR, ask David first).**
- **What's new:** `cross_game_ram_truth()` (Eval C) added to `eval/probe_egomotion.py`, reusing `best_shift`.
  Ran on David's hand-recorded `runs/2026-06-23_{gauntlet,kirby,metroid}_ramplay` (665/419/947 frames, each with
  a matching `oracle.jsonl` `watch` field). Report: `reports/_archive/2026-06-23-cross-game-ram-grounded-egomotion.md`.
- **Result (dominant-axis sign match vs RAM Δ; moves filtered `1≤|Δpos|≤40`; single-byte wrap-corrected):**

  | game | all (incl. camera-static) | camera-scrolled (honest metric) |
  |---|--:|--:|
  | gauntlet (player x,y — follow, dead-zone) | 59% | **79%** |
  | kirby (camera scroll_x — side, edge-locked) | 89% | **98%** |
  | metroid (screen×256+pixel — room/side) | 67% | **85%** |

  All 3 registers came out **aligned** with the ego convention (east+x→+dx, south+y→+dy) — no per-game sign flip.
- **The "all vs camera-scrolled" gap IS the camera-vs-player insight, now cross-game + RAM-grounded:** `best_shift`
  = CAMERA motion, a register = PLAYER motion; they agree only when the camera moves with the player. Gauntlet's
  follow-camera dead-zone (sprite slides at screen-center, camera holds) makes many player-moved steps
  camera-STATIC → `best_shift=0` → counted as misses → 59% "all" vs 79% scrolled. Kirby's scroll register has
  almost no static steps (89≈98). Pokémon's 98% (Eval A) is the limit case: overworld always centers the player,
  so its "all" == "scrolled". The dead-zone is the only thing between 59% and 98% — NOT an estimator weakness.
  (This is the clean human-recorded version of the earlier autonomous-Gauntlet 33%/74% probe.)
- **P2 DONE (built + verified, LOCAL/UNCOMMITTED):** extracted **`core/egomotion.py`** (world-agnostic, numpy-only
  `best_shift(a,b,*,max_shift,step,min_overlap,tie_break)`) as the SINGLE source; **consolidated BOTH prior copies**
  — `games/pokemon_red/perceiver._best_shift` (now a thin wrapper, `tie_break=1e-3`) and
  `eval/probe_camera_model.best_shift` (thin wrapper, `tie_break=0`). Surfaced additively via the overworld
  `SymbolicState.spatial_memory["ego_motion"]` (`core/contracts.py` UNTOUCHED). Verified
  **behavior-preserving**: tests green AND Eval A/B/C numbers byte-identical to pre-refactor (the unification is
  exact — `fd`-seed reproduces the probe at tie_break=0 and the perceiver at tie_break=1e-3; tie/seed edge cases
  worked through). NOTE: `eval/_archive/_edge_confound.py` still has its own one-off `_best_shift` (out of scope — an
  exploratory script, left alone).
- **Review addressed (PR #7, reviewer's 3 items) — 312 green:** (1) the seam no longer exposes the raw pixel shift —
  it emits a DIRECTION token via new `core.egomotion.direction(dx,dy)` (`spatial_memory["ego_motion"]` =
  `"east"`/`"west"`/`"north"`/`"south"`/`"none"`, dominant axis) so the unreliable magnitude can't be over-read;
  (2) the Eval C report + `core/egomotion` docstring now lead with BOTH numbers and label that "camera-scrolled"
  conditions on `best_shift` having fired (so it also excludes the estimator's OWN false-negatives, not only the
  dead-zone); (3) added a direct unit test `tests/test_egomotion.py` (exact-shift recovery / identical→(0,0) /
  tie_break / direction). Gotcha fixed: `perceive()` has a local `direction = _dominant_dir(...)`, so the import is
  aliased `ego_direction` to avoid the shadow.
- **⇒ NEXT:**
  1. **Commit + push/PR** (David commits/pushes only when asked — confirm first). Clean split into TWO PRs:
     (a) Eval C — `eval/probe_egomotion.py` + `reports/_archive/2026-06-23-cross-game-ram-grounded-egomotion.md` (closes the
     "cross-game pending" item from PR #5); (b) P2 — `core/egomotion.py` + the two thin-wrapper repoints +
     `spatial_memory["ego_motion"]`.
  2. **P3 (downstream): let System-2 (aria) actually USE `ego_motion`** + P4 end-to-end verify. Magnitude/metric
     distance stays deferred (direction/sign is what's reliable). Held-out (Crystalis/Zelda/SML/F-1/Doom) stay
     never-tuned-on; GBC banked WRAM (fixed addr unreliable) — prefer DMG titles; corpus gitignored (D:), regen via
     `eval/collect_corpus.md` §7.
- Reports: `reports/_archive/2026-06-23-cross-game-ram-grounded-egomotion.md` + `2026-06-23-egomotion-probe-P1.md`;
  LEARNINGS 2026-06-23 entries.

**⇒ NEWEST (2026-06-23, latest) — P1 EGO-MOTION PROBE: 2D direction recovery is RAM-validated at 98%. Branch
`feat/egomotion-probe` (off `main`).** First step of the generalizable ego-motion estimator (System-1 "how did I
move"). `eval/probe_egomotion.py` (reuses `best_shift`) measures DIRECTION (sign) recovery; metric distance is
deferred.
- **A. RAM ground-truth** (Pokémon Gen-1, ~1618 overworld RAM-moved steps): `best_shift` (dx,dy) matches RAM
  Δ(x,y) **98%** (per-run 97–100%). The estimator's direction recovery is validated against truth.
- **B. button-grounding** (cross-game 2D-scroll, no RAM): partial — metroid 2/2 clean, kirby 1/2, gauntlet 2/4,
  gold n<5 (escape-ladder-polluted: Gold reads "menu" to the Red-tuned detector). Cross-game cue holds on clean
  recordings; recording-quality-limited otherwise (same control/data theme as the held-out work).
- **⇒ NEXT = P2: extract `core/egomotion.py`** (world-agnostic, reuse `best_shift`, consolidate the duplicate
  `games/pokemon_red/perceiver._best_shift`); surface additively via `spatial_memory["ego_motion"]` (unfrozen
  `SymbolicState` seam — never touch `core/contracts.py`). Then P3 perceiver integration / P4 verify. Full
  record: `reports/_archive/2026-06-23-egomotion-probe-P1.md`; LEARNINGS (2026-06-23, 6th entry); plan in the approved
  P1 plan file.

**⇒ NEWEST (2026-06-23, latest) — HELD-OUT VERIFICATION: per-run classifier generalizes zero-shot; the gate is
autonomous CONTROL, not perception. Branch `feat/heldout-verification` (off `main`).** Built
`eval/verify_heldout.py` — the per-RUN camera classifier (`[scrollPrev, A4, vshare]`) + a HANDS-OFF zero-shot test
on the held-out set. Held-out games recorded AUTONOMOUSLY (`--explore`, NO human — human-playing a verification
game defeats the zero-shot test + risks leakage).
- **Dev per-run leave-one-unit-out = 7/7** (vs 45% per-frame — per-run aggregation is the closer; but near-
  tautological: the features were chosen on these units. Real evidence is out-of-corpus).
- **Held-out zero-shot (N=1 conclusive, by construction):** only **1 of 4 was drivable hands-off** — **Crystalis →
  follow_scroll**, nearest by a **×1.8 margin** over side (win metric = class margin, NOT distance-from-corpus).
  **SML / Zelda / F-1** are low-motion: INCONCLUSIVE if a scroller was predicted but the driver stalled (SML),
  AMBIGUOUS if `fixed` (Zelda flip-screen may be correctly fixed; F-1's car never accelerated). They test the
  DRIVER, not the perceiver — **F-1 `fixed` is NOT a perception concern.**
- **The real bottleneck = autonomous CONTROL of non-top-down games** (a competent controller = the agent itself,
  the project's end goal); camera-model PERCEPTION is verified-good where drivable. The HANDS-OFF discipline is
  what surfaced this. Full record: `reports/_archive/2026-06-23-heldout-verification.md`; LEARNINGS (2026-06-23, 5th entry).
- **⇒ NEXT unchanged: the generalizable ego-motion estimator** (fixed→none / 2D-scroll→`best_shift` / 3D→flow),
  on the drivable games; held-out re-runs cleanly once autonomous control improves.

**⇒ NEWEST (2026-06-23, latest) — ODOMETRY CORPUS REBUILT (locomotion fix) + DOOM HELD-OUT. Branch
`feat/odometry-corpus` (off `main`).** Acted on the camera-model probe's corpus-limited verdict: a 4-agent
diagnosis pinned the limiter to LOCOMOTION sparsity (jittery auto wiggles the avatar in place → camera never
pans → A3 residual ~1.0). Fixes: new opt-in `record.py --explore` (direction-persistent walk, `--hold 16`) +
HUMAN play (`--mode human`) for side-scrollers (auto can't run+jump; `--explore` gets them stuck). Added
`scrollPrev` to the probe + a held-out zero-shot test; **Doom (ViZDoom) registered HELD-OUT** in `dataset_split`
(matched by run-dir name — the 3D recorder writes no meta ROM).
- **`scrollPrev` cleanly separates SCROLL (21–58%) vs FIXED (0–2%)** cross-game; per-frame sib-mean 29%→45%;
  fixed classifies 83–96%. Follow-vs-side still confused (both scroll). **Held-out Doom NOT flagged novel**
  (×1.3 → scroll_side: a 3D turn ≈ a 2D side-pan in whole-frame flow) — but 3D ego-motion is oracle-verified
  (turn-sign 95%, advance-corr +0.47).
- **Corpus is gitignored (lives on D:); regenerate via `eval/collect_corpus.md`.** Full record:
  `reports/_archive/2026-06-23-odometry-corpus-and-doom-heldout.md`; LEARNINGS (2026-06-23, 4th entry).
- **⇒ NEXT = build the generalizable ego-motion / odometry estimator** (the System-1 "how did I move" the probe
  was measuring readiness for): a per-camera-class branch (fixed→none; 2D-scroll→best-shift dx,dy; 3D→optical-flow
  turn+advance), developed on the dev corpus, verified on the held-out games incl. Doom. Cheaper sub-step first:
  the per-RUN `scrollPrev`/`A4` classifier to close the camera-model verdict.

**⇒ GIT/STATE (2026-06-23) — PR #1 MERGED to `main`; camera-model probe on its own branch. ANOTHER MACHINE
PICKS UP HERE.**
- **`main` = `3ecb853`** (PR #1 merged): the modality/auto-play foundation (`f53096d`), appearance/OCR probe +
  ADR-001 inv#6 calibrated-deferral (`c143230`), date-prefix recorder (`1a347df`), MIGRATION.md + probe-venv
  reqs (`df76b65`), and the autoplay escape-ladder fix (`9874034`). `feat/cross-game-perception` is now merged
  and stale — safe to delete.
- **Branch `feat/camera-model-probe`** (rebased onto `main`; **1 commit** = the probe + report + this HANDOFF):
  `eval/probe_camera_model.py`, `reports/_archive/2026-06-23-camera-model-probe.md`. PR #2 not opened yet.

**▶ HOW A FRESH SESSION (e.g. the desktop) PICKS UP:**
1. `git fetch origin && git checkout feat/camera-model-probe` (or merge it to `main` first; it's 1 clean commit).
2. **Local-only artifacts must be present** (NOT in git — see `MIGRATION.md`): `roms/` (the GB ROMs) and `runs/`
   (the recorded corpus + `runs/kanto1/checkpoint_02.state`). Needed to record new data and to re-run the probe.
3. `uv sync` (main env). **The recorder AND the camera-model probe run in the MAIN env (numpy+PIL only) — you do
   NOT need `.venv-probe4`** (that's only for the CLIP/OCR appearance probe).
4. Sanity: `uv run pytest -q` (expect 304 green) and `uv run python -m eval.probe_camera_model` (reproduces the
   table below on the existing corpus).

**▶ NEXT = BUILD THE ODOMETRY CORPUS, THEN RE-RUN THE PROBE (David greenlit running the heavy collection on the
desktop).** The probe defined exactly what the corpus needs: sustained gameplay + ≥2–3 games per camera class +
correct labels. Corrected dev taxonomy & targets:
- **follow_scroll** (camera tracks the avatar across a larger map): Pokémon Red, Pokémon Gold, **Gauntlet II**
  (multidir — was mislabeled "fixed"), Cave Noire.
- **side_scroll**: Kirby, Metroid II.   **fixed**: Space Invaders, **Tetris Plus** (the needed 2nd truly-fixed game).
- **fp3d**: ViZDoom my_way_home (a 2nd 3D scene is a later add).
- **Held-out — NEVER record-for-dev/tuning** (final verification only): Crystalis, Zelda LA, Super Mario Land, F-1 Race.

Heavy-compute collection (cold-boot action games; `record.py` auto-prefixes the run dir with today's date):
```
uv run python record.py --rom "roms/Gauntlet II (USA, Europe).gb"            --name gauntlet_auto --mode auto --smart-auto --ram --steps 8000
uv run python record.py --rom "roms/Kirby's Dream Land (USA, Europe).gb"     --name kirby_auto    --mode auto --smart-auto --ram --steps 8000
uv run python record.py --rom "roms/Metroid II - Return of Samus (World).gb" --name metroid_auto  --mode auto --smart-auto --ram --steps 8000
uv run python record.py --rom "roms/Space Invaders (USA) (SGB Enhanced).gb"  --name spaceinv_auto --mode auto --smart-auto --ram --steps 8000
uv run python record.py --rom "roms/Tetris Plus (USA, Europe) (SGB Enhanced).gb" --name tetris_auto --mode auto --smart-auto --ram --steps 8000
```
RPGs need to START in real gameplay (smart-auto can't cross a hard scripted intro) → checkpoint-resume:
```
uv run python record.py --rom roms/PokemonRed.gb --name red_resume --mode auto --smart-auto --ram --steps 8000 --load-state runs/kanto1/checkpoint_02.state
```
Gold/Cave-Noire: make a checkpoint ONCE (`--mode human`, play into gameplay, press `C`), then `--load-state` it.
Gate every run for sustained gameplay (drop menu-polluted ones): `uv run python -m eval.corpus_activity --max-frames 2000`.
Then update the `RUNS` list + camera-class labels in `eval/probe_camera_model.py` and **re-run** it for the
cross-game separability verdict. (Heavy disk/CPU: ~8 runs × 8000 steps; trim step-count/games if needed.)

**⇒ NEWEST (2026-06-23, latest) — CAMERA-MODEL PROBE BUILT + RUN (offline, free). 3D ego-motion is REAL and
ORACLE-VERIFIED; 2D camera-class ID is CORPUS-limited, not feature-limited.** `eval/probe_camera_model.py`
(numpy+PIL, main `uv` env): per transition, cheap pixels-only motion features + four **button-grounded** axes
(A1 no-input / A2 sign / A3 residual / A4 locality), with **per-source frame↔button timing** (GB: transition
i-1→i caused by buttons[i]; ViZDoom: buttons[i-1] — the off-by-one fixed). DEV corpus = red×2 / kirby+metroid /
spaceinv+gauntlet / vizdoom (pose = non-leaking oracle).
- **3D (the win): turn-direction from column-shift sign = 95% L/R SEPARABILITY** (in-sample, ≥50% by
  construction — the real evidence is the flow_x mean gap: TURN_LEFT −10.79 vs TURN_RIGHT +14.45);
  **forward advance vs expansion-flow corr +0.42** against ground-truth Δpos. Reproduces the flow-ceiling result;
  ego-motion-as-discrete-classifier has legs.
- **2D: cross-game camera-CLASS classification NOT yet demonstrated (leave-one-UNIT-out sib-mean 44%; Pokémon =
  ONE unit so topdown is a singleton) — but the probe diagnosed WHY,
  and it's the CORPUS:** (1) my a-priori label was wrong — **Gauntlet II is a follow-SCROLLER, not fixed**
  (A4=0.86 vs truly-fixed Space Invaders A4=0.19); (2) **`red_smart1` is polluted** (stuck in Red's intro, not
  overworld); (3) **`kirby_auto1` barely scrolls** (A4=0.08). The per-game signatures are interpretable; a thin
  1–2-games/class centroid classifier just can't extract a clean class yet.
- **⇒ NEXT (refined by this probe): build the ODOMETRY CORPUS with these requirements, THEN re-run the probe:**
  (a) **sustained-gameplay** recordings only — gate with `eval/_archive/corpus_activity.py`, drop menu-polluted runs,
  checkpoint-resume RPGs into real gameplay; (b) **≥2–3 games per camera class** (esp. a 2nd truly-fixed game,
  eventually a 2nd 3D scene) so class-ID is testable for every class; (c) **correct camera-class labels** (and
  likely a coarser camera-MOTION-type taxonomy {fixed / rigid-2D-scroll / nonrigid-3D-flow} — what odometry
  actually branches on). Heavy compute/disk → **confirm corpus scope/step-count with David first.** Full record:
  `reports/_archive/2026-06-23-camera-model-probe.md`; LEARNINGS (2026-06-23, 3rd entry).

**⇒ NEWEST (2026-06-23, later) — APPEARANCE/OCR vs cheap modality classification: FAIR cross-game probe RUN;
decision = STOP (cheap menu-detection is a dead end; behavioral handling stands). Branch
`feat/cross-game-perception`, UNCOMMITTED.** David rejected the under-proven "appearance can't classify modality
cross-game" claim and demanded the probe. `eval/_archive/probe_modality_appearance.py` (+ `eval/_modality_probe_run.py`,
run under `.venv-probe4`): ~190 hand-labeled GAMEPLAY-vs-NOT frames, **leave-one-GAME-out (pokemon = ONE unit —
leakage guard)**, comparing CLIP MobileCLIP2-S0 / OCR-text-amount / cheap-numpy / flat-only (numpy logistic +
cosine centroid/kNN; balanced accuracy). **The test corrected BOTH sides:** CLIP **GENERALIZES for
gameplay-vs-title** (mean **83%**, ~100% on kirby/metroid/gauntlet) → the blanket "appearance is useless" is
**REFUTED**; **BUT** on the two real-menu folds it's near chance (**pokemon 55%, spaceinv 64%**) → menu/dialog/UI-
vs-gameplay does **NOT** generalize cross-game (claim holds for the hard part); and **OCR-text-amount is a POOR
menu cue** (40% mean, 0% Gauntlet — GB gameplay HUDs are text-heavy too, so "text=menu" is wrong; OCR's only value
would be reading CONTENT to navigate, not classifying). Caveat: kirby/metroid/gauntlet had 1 boot NOT-frame so
their ~100% is gameplay-recognition (MEAN optimistic); pokemon/spaceinv are the honest folds; small N.
**DECISION (David): STOP** — a generalizable cheap menu-detector is a dead end; keep the **behavioral escape
ladder** (easy titles) + **checkpoint/LLM fallback** (hard scripted intros like Red name-entry). Full record:
`reports/LEARNINGS.md` (2026-06-23, 2nd entry). **NEXT unchanged ⇒ the ODOMETRY CORPUS + camera-model probe**
(see the block below).

**⇒ NEWEST (2026-06-23) — GENERALIZABLE MODALITY DETECTION + MODE-AWARE AUTO-PLAY (built + validated; the
nudging crutch removed for the common case). Branch `feat/cross-game-perception`, UNCOMMITTED.** David
redirected the odometry plan: instead of *nudging* (a human hand-playing each game past its menus to collect
gameplay), build the capability the goal demands — an agent that handles menus from the screen itself.
- **Built (all world-agnostic, `core/`, numpy-only; 21 new tests, 304 total green; frozen contract untouched —
  `SymbolicState.context` already carries mode):** `core/modality.py` (`detect_modality(prev,curr,buttons) →
  (static|menu|gameplay|unknown, conf)`), `core/autoplay.py` (`ModalAutoPolicy`: gameplay→random breadth;
  else an escape ladder), `record.py --smart-auto` (opt-in; default random unchanged), `eval/_archive/corpus_activity.py`
  (readiness/validation gate + `--anchor` Pokémon check).
- **Validated (free, grounded):** Pokémon anchor (`--anchor runs/kanto1`): **overworld+MOVED → "gameplay" 98%**
  (buttons ground it, no GT). Cross-axis (`corpus_activity`): smart-auto flips **Kirby random THIN→READY
  (active 44%→62%)** cold-boot; Space Invaders (static-sprite, extracted from `roms/`), Gauntlet (follow),
  Metroid (side) all READY → **all 4 camera-model axes now have gameplay data**.
- **Honest limits (measured, not hidden):** (1) **menu *classification* by appearance does NOT generalize**
  (anchor: menu/dialog/battle read as low-conf "gameplay"; the hash-cross-tileset lesson again) → menu
  *handling* is **behavioral** (repeat an escape move while the screen changes, rotate when it stops), not
  label-driven. (2) **smart-auto does NOT crack a hard scripted intro** — Red cold-boot stays THIN (name-entry
  keyboard needs a goal-directed sequence) → hard RPGs use the **checkpoint/LLM fallback** (Red has
  `runs/kanto1/checkpoint_02.state`), the "rare residual" the plan anticipated. (3) `active%` is inflated by
  **cutscenes** (Oak's intro animates → "gameplay") → use **`maxRun`** (longest streak) as the "reached real
  play" signal. Full record: `reports/LEARNINGS.md` (2026-06-23).
- **⇒ NEXT (pick up here): build the ODOMETRY CORPUS, then the camera-model probe.** (a) Bulk-collect with
  `record.py --mode auto --smart-auto --ram --steps 8000` cold-boot on the action games (Kirby, Metroid,
  Gauntlet, Space Invaders, Tetris, Mortal Kombat — heavy background compute/disk, so confirm scope/step-count
  with David first); checkpoint-resume the RPGs (Red from its checkpoint; Gold/FF-Adventure/Sword-of-Hope need
  a one-time `--mode human` `C`-checkpoint = the rare residual). Gate each with `corpus_activity`. (b) Then the
  **camera-model / odometry probe** (`eval/probe_camera_model.py`, design ready in the plan file): pixel-grained
  2D shift+residual (generalize `perceiver._best_shift`), button-grounded A1 no-input / A2 sign / A3 residual /
  A4 locality, honest model-class-separability verdict. Held-out (Zelda-LA/SML/Crystalis/F-1) stays untouched.

**⇒ (2026-06-22 late) — GOAL CANONICALIZED + GOVERNANCE LAYER SHIPPED + INTEGRATED TO `main`. Next =
START the generalizable-odometry build.** A planning/governance session (no game runs):
- **Goal canonicalized** in §1 (ONE agent = fixed brain + swappable perceiver; human-grade task success from
  the screen alone; two axes = embodiment ladder + **computer-use track** [strategy/builder games → permitted
  desktop/web, pixels-only]; cheap; no per-world training; with falsification criteria). The portable "how we
  work" doc is **`reports/CONTEXT-BRIEFING.md`** (methods/principles/preferences + **drift tripwires** +
  progressive disclosure + Sense A/B + the self-improvement loop).
- **Research grounding** (`reports/_archive/2026-06-22-plan-grounding-and-failure-modes.md` + research-takeaways +
  prior-art scan): every component anchored in real systems (Voyager/Reflexion/Huang "LLMs can't self-correct"/
  VO-SLAM/ObjectNav/computer-use) with failure modes. **Our verified findings independently match the
  textbook** (3D: rotation+textureless = the classic monocular-VO failures = our frame-diff/dark-wall result;
  spatial memory: ObjectNav "stuck in visually-similar-but-wrong regions" = our hash-alias + portal bug).
- **Enforcement layer SHIPPED** (principles → automated, the drift-detection you asked for): **CI**
  (`.github/workflows/ci.yml`, full suite on push/PR), **pre-commit** (full suite before every commit;
  installed), **fitness tests** (`tests/test_import_boundaries.py` = core↛games + no-aria-import + games
  isolated; `tests/test_no_ram_leak.py` = only role keys cross the seam). Claude hooks (SessionStart auto-orient
  / PreCompact notes-reminder / PreToolUse commit-gate) live in **gitignored `.claude/`** (local tooling).
- **Integrated:** `main` **fast-forwarded** to `a368195` (== feature, linear, no merge commit); 9 stale feature
  branches deleted. **Unpushed** (main ahead of origin by 60). Open: `git push origin main` + enable branch
  protection (require `ci`) when ready; remote `origin/feat/*` branches still exist (offered to prune).
- **⇒ NEXT — the build starts now: GENERALIZABLE ODOMETRY.** A camera-model detector
  (follow-scroll / static-sprite / forced-scroll / fixed) + self-motion estimator, developed **OFFLINE on the
  DEV corpus only**, verified on the held-out 4 via `eval/cross_game.py`. **Per the 3D verdict: ego-motion is a
  DISCRETE classifier built from OPTICAL FLOW** (column-shift sign → turn; expansion/radial flow → advance),
  **NOT scalar frame-diff and NOT metric distance.** **FIRST STEP (cheap, grounding-first):** a *camera-model
  detection probe* over the recorded DEV runs (Kirby×2, Metroid-II×2, Gauntlet-II exist) — can we classify each
  game's camera model from raw `(frame, buttons, next-frame)` cheaply? — before building the estimator. Need
  more dev games nudged into gameplay first (open items below). `record.py` is the substrate; `eval/cross_game.py`
  + `eval/dataset_split.py` are the harness.
- **Open data items:** download **Super Mario Land** (held-out side-scroller); human-nudge RPG/menu games into
  gameplay + `C` checkpoint (Gold, FF-Adventure, Cave-Noire, Sword-of-Hope, Tetris) then bulk-auto; confirm
  Zelda held-out vs swap to Cave-Noire (`eval/dataset_split.py`).

**⇒ (2026-06-22) — NEW PHASE: CROSS-GAME PERCEPTION GENERALIZATION (branch
`feat/cross-game-perception`, off `feat/novelty-signal`).** The Pokémon tile-map line (tasks #7→#9→#8) is
built, verified, fixed, and the speedup measured — now we test the real thesis: does the core + brain
generalize to OTHER games? David downloaded a ladder of GB ROMs chosen so each isolates ONE new
perception/odometry axis (web-verified catalog: `reports/_archive/2026-06-22-gb-perception-test-suite.md`; we own
Red/Gold/Zelda-LA/Kirby; acquisition order Lolo→Zelda-Oracle→FF-Adventure→Crystalis→Metroid-II→Q*bert→
F-1-Race→Sword-of-Hope-II). **Decomposition:** per-game = perceiver (odometry/affordance/mode/OCR/entity/
action-contract); INVARIANT (protect) = the brain + core learning + the SymbolicState seam — success =
how LITTLE the brain changes. **Data strategy:** record the RAW substrate `(frame, exact buttons,
next-frame, optional RAM)` game-agnostically, defer odometry/labeling to OFFLINE replay (don't bake the
Pokémon perceiver's camera-scroll/(4,4) assumptions into the data). **Build sequence + full plan:**
`reports/_archive/2026-06-22-cross-game-phase-plan.md`.

**STATUS (2026-06-22, end of session — SAFE TO COMPACT):**
- **Recorder BUILT** (`record.py`, task #13 done): game-agnostic, any GB ROM → `runs/<name>/{frame_*.png,
  buttons.jsonl, meta.json, ram.bin?}`; modes `--mode auto` (headless random policy incl. Start) &
  `--mode human` (SDL window, WASD/arrows, TAB=auto, C=checkpoint). Smoke-tested on Gold/Kirby/Zelda.
- **12 ROMs extracted** to `roms/` (gitignored): Red, Gold, Crystalis, Gauntlet II, Zelda-LA, FF-Adventure,
  Cave-Noire, Kirby, Metroid-II, F-1-Race, Sword-of-Hope-II, Tetris-Plus. (Colorization Red hack SKIPPED.)
- **HELD-OUT split LOCKED** (`eval/dataset_split.py`, NEVER tune on these): one per axis = Crystalis
  (follow), Zelda-LA (flip), **Super Mario Land (side — ROM NOT yet downloaded)**, F-1-Race (pseudo-3D).
  Dev (9) = Red, Gold, Gauntlet II, FF-Adventure, Cave-Noire, Kirby, Metroid-II, Sword-of-Hope, Tetris.
- **Collected (dev, auto):** Kirby×2, Metroid-II×2, Gauntlet-II×1 (raw frames+buttons+RAM in `runs/`).
- **OPEN DECISIONS for next session:** (a) confirm Zelda held-out vs swap to dev (then hold out Cave-Noire);
  (b) David to download **Super Mario Land**; (c) human-nudge the RPG/menu games into gameplay + `C`
  checkpoint (dev: Gold, FF-Adventure, Cave-Noire, Sword-of-Hope, Tetris; held-out: Zelda, Crystalis, F-1)
  so auto-collection can resume from a gameplay state; then bulk-auto from checkpoints.
- **3D GATE → GREENLIT It3 (verified, 2026-06-22):** `eval/_archive/vizdoom_smoke.py` (`uv run --with vizdoom`)
  recorded `my_way_home` (700 steps; raw frames+actions+GT pos/angle in `runs/vizdoom_mywayhome/`). A
  5-agent adversarial verification UPHELD the greenlight — and the headline got STRONGER: the smoke test
  had an **off-by-one action-frame bug** (filtered pure-forward on action row *i*, but the *i-1→i* change
  is caused by row *i-1*; now FIXED). Corrected (pure-forward n=424, majority 66.0%): advance-vs-blocked
  **96.9%** (not 83.7%), corr **+0.59** (not +0.37). GT proof the bug was the limiter: under correct
  alignment FORWARD→Δangle 0.000°(std0), LEFT→+10.36°, RIGHT→−9.62°. **REAL:** behaviour=truth holds in 3D
  (clean) + a cheap pixels-only advance/stuck detector (survives 5-fold CV; brightness-residualized still
  94.8% so it's NOT a lighting artifact). **HONEST FRAMING (don't overclaim):** binary advance/stuck +
  turn-direction classifier, NOT metric odometry (graded-distance corr ≈ +0.02); whole-frame frame-diff
  CANNOT tell rotation from translation → the real perceiver = **OPTICAL FLOW** (column-shift sign → turn
  dir ~90–95%; expansion flow → advance; 2-feat → 98.3%). Reusable ceiling probe:
  `eval/vizdoom_flow_ceiling.py`. Untested: corridor/room base-rate, dark-wall FNs (3.8%), non-random
  policy, fwd+turn steps. ViZDoom installs cleanly headless (1.3.0, GT position oracle). Full verdict +
  honest 3D section: `reports/_archive/2026-06-22-cross-game-phase-plan.md` ("3D — GREENLIT this iteration").
- **PRIOR-ART scan** (`reports/_archive/2026-06-22-prior-art-scan.md`): closest = **Cradle** (screen-only general
  control, GPT-4o — its perception/object-localization limitation VALIDATES our perception-first thesis) +
  **Wild Visual Navigation / V-STRONG** (robotics behaviour-grounded traversability that generalizes — the
  analog of our tile→function map; they make embeddings work ONLINE where we found a hash beats CLIP).
  Dual-process (SwiftSage/DPT-Agent) is well-trodden; cross-game generalists (NitroGen/GATO/PORTAL) use
  big behaviour-cloning. **Our gap = cheap + screen-only + ONLINE/no-training + behaviour=truth + dual-
  process + explicit cross-GAME held-out generalization.** Adopt: WVN online supervision, Cradle skill
  curation; Avoid: GPT-4o-every-step, internet-scale behavior cloning.
- **⇒ NEXT BUILD = the GENERALIZABLE ODOMETRY** — a camera-model detector (follow-scroll / static-sprite /
  forced-scroll / fixed) + self-motion estimator, developed OFFLINE against the DEV corpus only, verified
  on the held-out 4 via `eval/cross_game.py`. (David said "continue" → start this next session.)

**⇒ (2026-06-22) — TASK #8 nav-speedup WIRED + closed-loop A/B (the offline ceiling did NOT
translate; closed-loop earned its keep).** Wired the tile-map's advisory into the autopilot:
`ExploreBrain(use_predictions=, pred_min_conf=, skip_flat_pred=)` treats predicted-BLOCKED unvisited cells
as SOFT-WALLS (skip the bump) with a two-pass FALLBACK (no useful frontier → ignore predictions & bump, so a
wrong skip DELAYS not strands) and the behavioural veto authoritative; the perceiver now tags each prediction
`is_flat`. **Offline** (`eval/_archive/probe_navsave.py`, fixed recorded trajectory): skipping avoids **~76% of bumps
@ <1% wrong-skip** — but that's a CEILING. **Closed-loop** (`eval/_archive/closed_loop_ab.py`, headless autopilot
DRIVING the emulator, no LLM, path DIVERGES): **naive skipping STRANDS the agent** (42 vs 134 cells — it learns
"dark tile=wall" from one bump then skips look-alike flat DOORWAYS/stairs and seals itself in). **`skip_flat`
FIXES it:** no strand, explores MORE than baseline (160 vs 134 cells), bump-rate **27.9% → 18.0% (~35% fewer
bumps/step)**. **Lesson: an offline metric on a FIXED trajectory overstates — only closed-loop (where the agent's
own sparse map feeds back into its path) reveals the self-reinforcing strand; and don't trust FLAT-tile
predictions for navigation (a flat tile may be a door).** Safe config = `use_predictions=True, skip_flat_pred=True`
(NOT auto-enabled in the paid drivers — David opts in; defaults off, agnostic worlds unchanged). 277 tests.
**⇒ NEXT: enable the safe config in the Pokémon drivers + a guarded PAID live run to confirm the speedup
end-to-end (the first paid validation of the whole tile-map line); the It2+ CLIP arm stays deferred.**

**⇒ (2026-06-22) — CHEAP HASH FIX LANDED (the indoor failure addressed without CLIP; branch
`feat/novelty-signal`).** Folded a richer key into `core/tilemap.py`: **horizontal + VERTICAL gradient +
a 4-bit brightness BUCKET**, with **structured matching** (intensity gated within ±1 band, Hamming tol on
the 128-bit gradient only) + two consumer abstain knobs `predict(min_conf=, skip_flat=)`. Results
(`eval/probe_tilemap.py` + `eval/_archive/_verify_tileset.py`, reproduced): **temporal acc-when-known 90.9% → 97.8%**
(coverage held 98.6% — a strict win, the all-zeros alias is gone); leave-one-MAP-out lab flipped from
confident-wrong 78.6%cov/77.7%acc → **11%cov/98.9%acc** (now reads NOVEL, safe); town wall-recall 84.7% →
**89.9%**. Indoor leave-one-TILESET-out wall-miscalls **449 → 297** at default, **→ 2 with `skip_flat=True`**
(295 flat collisions become "novel→explore"). The residual is the *physics* (appearance ≠ function
cross-tileset; a flat tile can't be told wall-vs-floor by looks) — so it's a **coverage⇄safety DIAL**, not a
bug. 277 tests. **CLIP DEFERRED** to It2+/complex environments (its real jobs: graded-novelty distance,
semantic/entity ID, natural images — not GB walkability). **⇒ NEXT = task #8: navigation-speedup A/B** — wire
predictions into the autopilot, set the abstain dial (min_conf/skip_flat) by the metric that matters
(steps-saved vs wrong-bumps), behavioural veto stays authoritative.

**⇒ (2026-06-21 night) — TASK #9 cross-tileset hash test RUN + ADVERSARIALLY VERIFIED; headline
CORRECTED (branch `feat/novelty-signal`, pushed).** Ran the hash leave-one-MAP-out on the new data (8817
faced-tiles, 10 runs) — it LOOKED great (Forest novel 3.3%, no map below baseline). A **5-agent verification
workflow OVERTURNED the strong claim:** leave-one-MAP-out hid a failure because a held-out indoor map kept a
**sibling** indoor map in the store. Under the honest **leave-one-TILESET-out** (`eval/_archive/_verify_tileset.py`,
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
record (verification update at top): `reports/_archive/2026-06-21-tile-fingerprint-map-and-cross-tileset-capture.md`.

**⇒ (2026-06-21 eve) — DATA-CAPTURE TOOLING + FIRST CROSS-TILESET DATA (free; branch `feat/novelty-signal`,
pushed).** To close the DATA GAP (we only had ~5 early maps that SHARE a tileset, which inflated the hash's
cross-map win), built three free tools: **`play_record.py`** — a windowed PyBoy session you GUIDE, with a `Tab`
toggle that hands control to the autopilot for hands-free dense sampling (WASD layout via in-place SDL2-keymap
mutation — the user's arrow keys are dead; `C`=checkpoint `.state`; records probe-compatible frames+oracle);
**`eval/_archive/auto_race.py`** — a headless free dumb auto-player (ExploreBrain + A-mash) for parallel data-gen / racing;
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
empirically grounded). Full record: [`reports/_archive/2026-06-21-perception-architecture-decision.md`](reports/_archive/2026-06-21-perception-architecture-decision.md)
+ [`reports/_archive/2026-06-21-vision-model-probe.md`](reports/_archive/2026-06-21-vision-model-probe.md).** We probed lightweight
off-the-shelf vision (MobileCLIP/SigLIP/Florence-2/RapidOCR/YOLO) on GB frames, ran 3 adversarial reviews, and
EMPIRICALLY tested the "CLIP-embedding spatial store" idea. **Decisive result** (`eval/_archive/probe_walkability_learn.py`,
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
trips **26× ALL in the lab trap (first @ step 416), 0 false positives** (`eval/_archive/inspect_longloop_trap.py` asserts
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
`reports/_archive/2026-06-21-seen-states-validation.md`
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
advances). Report `reports/_archive/2026-06-20-live-run-17-affordance-layer-probe-saliency-got-the-starter.md`, ~$0.6-0.8.
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
`ai-aria/PROMPT_ARCHITECTURE.md`; cost detail `reports/_archive/2026-06-20-cost-investigation.md`.**

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
map corrupts. Verified the true mechanics on the live emulator (`eval/_archive/probe_step.py`): a **single `[d]` press =
exactly one tile** (even on a direction change; turn is free), `[d,d]` = two. **Fix (two halves):** (1)
`ExploreBrain(single_step=True)` — the Pokémon drivers press `[d]` (one tile/decision) so each move stays synced;
the **agnostic default stays `[d,d]`** (GateWorld untouched — step granularity is a per-world property the driver
injects, `core/` stays world-agnostic). (2) **measured-distance odometry** in the perceiver — advance the cursor
by the best-shift magnitude (clamped to the ±4-tile window), marking every traversed cell visited, instead of
capping at one. **Free-validated** on run #15's real frames (`eval/_archive/replay_drift.py`: 40.2% → 0) AND **paid-validated
live in run #16** (`reports/_archive/2026-06-20-live-run-16-interior-nav-drift-fix-end-to-end-re-run.md`): drift **2.9% vs
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
Pallet). **Report `reports/_archive/2026-06-20-live-run-13-battle-auto-advance.md`**, video `runs/run13.mp4`, oracle
`runs/run13/`, archive iter-013. Branch `feat/battle-auto-advance` off
`main`, committed, **NOT pushed**. 158 tests. NEXT: (2) the **learned blind-execute battle policy** (skill
compilation, now feasible because the state is decoded — INSIGHTS §6; run #13's 7 identical "FIGHT→SCRATCH"
turns are the obvious thing to compile); (3) tighten **lab-exit / Pallet navigation** (the residual Phase-B gap).

**Run #14 (2026-06-20) — first integrated COLD-START end-to-end run; nav holds, credits ran dry (downstream
inconclusive). Report `reports/_archive/2026-06-20-live-run-14.md`.** From `start.state` (text-only, all current
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
masking it). Report `reports/_archive/2026-06-20-live-run-15.md`.** Built an **API-error circuit breaker** first
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
cost ~$3 and made no progress (38↔37). Post-mortem: `reports/_archive/2026-06-15-live-run-01-postmortem.md`.
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
`reports/_archive/2026-06-15-live-run-02.md`. With the fixes, the agent **left the house, crossed Pallet Town,
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
report: `reports/_archive/2026-06-16-live-run-03.md`, video `runs/run3.mp4`. With steps 1–3 (the `LESSON:` buffer,
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
  `eval/_archive/inspect_battle.py` (detect_mode + decoder + region dump over battle frames).
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
   report `reports/_archive/2026-06-16-live-run-03.md`, video `runs/run3.mp4`). The run-#2 wall is **broken**: the
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
  isolated battle tests) by `eval/_archive/make_battle_state.py`. Both untracked/local.
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

**Read in this order:** `HANDOFF.md` → `reports/_archive/2026-06-15-consolidated-report.md` →
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
