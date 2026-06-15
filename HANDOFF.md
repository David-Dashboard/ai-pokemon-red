# HANDOFF — ai-pokemon-red

Read this first. It is the living summary of **what we're building, where we are, and what's next.**
Deeper detail lives in `reports/` (start with the consolidated report) and `reports/LEARNINGS.md`.

_Last updated: 2026-06-15._

---

## 1. Overall goal (the north star)

This is **not** about beating Pokémon. Pokémon Red is the **first probe world** for the real goal:

> Build a **simple, generalizable** agent that acts on the world — generalizing across games and
> eventually reality — that is **cheap** and works from the **screen**, not privileged state.

Three constraints held on purpose (they're what makes the result transfer):
- **Generalize** — find the *smallest* increments that let the *same* agent act in a *different*
  world. Avoid Pokémon-specific hacks. (The brain, **ai-aria**, is a fully decoupled HTTP service.)
- **No ROM / privileged state** — plan from the **screen**. RAM exists only as a **non-leaking
  scoring oracle** (`oracle.jsonl`); it never enters the agent's input.
- **Cheap** — minimize API calls/tokens. A free local autopilot does routine work; wake the
  expensive LLM only at decisions.

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

**What's broken / the live result:** The first credit-funded LLM run (2026-06-15) **never left the
starting house** and cost ~$3. Full post-mortem: `reports/2026-06-15-live-run-01-postmortem.md`.
Root cause (data-confirmed): **interior stair-warps are low-diff (~13–29), below the area-reset
threshold (60), so the perceiver never reset its map** — it dead-reckoned ONE drifting frame across
two floors → a **permanent unreachable phantom frontier at (0,0)** → autopilot "stuck" every step →
**LLM woken 351/400 (88%)**, flailing. Compounded by: **no progress watchdog in `play_pokemon.py`**,
an **anti-loop hole** (unreachable frontier ≠ no frontier), **prompt caching off**, and an **inert
learning loop** (aria wrote no `<lesson>`, didn't flag the goal blocked, and its recap *rationalized*
the loop as "mapped 16+ tiles").

**The headline:** the bottleneck **moved** from *perception* (Iter 01) to **spatial-memory
integration across transitions + grounded progress/learning** (this run).

**Spend:** ~$3 this run; ~$0.66 across everything before. **Prompt caching is OFF** (`cached_tokens=0`)
— the biggest cheap win available.

## 3. Next steps (prioritized: stop the bleeding → fix the cause)

**Tier 1 — cheap guardrails (do BEFORE any further paid run; $0 to build):**
1. Port the **progress watchdog** from `play_loop.py` into `play_pokemon.py` (halt on no global
   progress for N steps).
2. **Frontier-abandonment / loop-breaker:** drop a frontier that stays unreachable after K tries
   (halt if none remain); feed "no progress for N steps" to the LLM as a *replan* signal; and **write
   it to memory** (force a `<lesson>` / flip the goal to *blocked*) so the agent learns instead of
   rationalizing.
3. **Enable prompt caching** on the aria/Haiku calls (stable system+memory prefix → ~10% billing).

**Tier 2 — fix the actual cause (spatial memory):**
4. **Reliable transition detection** — diff-threshold misses interior stairs; use a **fade-to-
   black/white detector** (reuse the near-uniform-frame guard already in `detect_mode`) and
   **reset/branch the coordinate frame** on a detected warp.
5. **Place-graph, not one drifting grid** — keep a per-area map and *link* areas by the transition
   used, so returning to a known area restores its map instead of merging it (also gives real
   landmarks: "this frontier is the door to outside").
6. **Curb odometry drift** — make `[d,d]` net exactly one tile, or re-anchor on features.

**Tier 3 — validate, then resume the mission:** re-run the bedroom→Pallet slice (Tier-1 guarded);
success = leaves the house and reaches Pallet within a bounded $/step budget. Then the credit-gated
**gating-probe verdict** (`--brain llm`) and the first **battle**.

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
# in ai-aria: docker compose up -d aria aria-litellm   (ARIA_DATA_DIR=./pokemon-red-data)
$env:ARIA_BEARER_TOKEN = ((Get-Content ..\ai-aria\.env | Where-Object { $_ -match '^BEARER_TOKEN=' }) -replace '^BEARER_TOKEN=','').Trim()
uv run python play_loop.py --rom "roms/PokemonRed.gb"        # headless, watchdog-guarded, persistent
```

**aria gotchas (have bitten us):** `ARIA_DATA_DIR` must point at `pokemon-red-data` (else Red runs
without its seed); the Anthropic key behind aria needs credits; **prompt caching is off** (cheap win).

## 6. Repo state

- Branch: **`feat/perception-module`** (pushed; **PR open** against `main`).
- You supply your own legally-obtained `roms/PokemonRed.gb` (none is bundled). `start.state` (past
  the intro, in the bedroom) is generated by `make_state.py`.
- Windows + PowerShell host (a Bash tool is also available). Files under `runs/` are gitignored.
