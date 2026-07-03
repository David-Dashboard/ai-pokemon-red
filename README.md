# ai-pokemon-red

Let an AI agent play **Pokémon Red** on a Game Boy emulator. The agent sees the
screen plus structured game state (party, HP, badges, position) and acts through
a small set of button-press tools, routed through a single gateway — so LLM
agents, RL policies, and classical search can all play through the same door.

> **You must supply your own legally-obtained Pokémon Red ROM (`.gb`).**
> No ROM is included, and none will be downloaded for you.
>
> ⚠️ This uses **PyBoy**, a Game Boy / Game Boy Color emulator. It plays the
> Gen-1 **Game Boy** game *Pokémon Red* (`.gb`). It does **not** run Game Boy
> Advance titles like *Pokémon FireRed* (`.gba`).

## Repo map

**Orient:** `ARCHITECTURE.md` · `ROADMAP.md` · `HANDOFF.md` (current thread) · `CLAUDE.md` (working rules) ·
`reports/` (living refs: INSIGHTS, LEARNINGS, CONTEXT-BRIEFING, constitution — history in `reports/_archive/`).

**The system:** `core/` (game-agnostic framework) · `games/<game>/` (per-world plugin + perceiver:
cave_noire, gauntlet, pokemon_red) · `tests/` · `datasets/` (hand-label ground truth).

**Run it:** `play_*.py` (per-game drivers) · `world_mcp.py` (MCP server — a Claude plays over MCP) ·
`human_play.py` / `new_game.py` / `make_state.py` (utilities) · `eval/` (measurement tools — see
[`eval/README.md`](eval/README.md); concluded one-off probes in `eval/_archive/`).

## Quickstart

With [uv](https://docs.astral.sh/uv/) (recommended — `uv sync` reads
`pyproject.toml`/`uv.lock` and builds an isolated, reproducible `.venv`):

```bash
uv sync                        # create .venv + install deps (incl. pytest)
# put your ROM at roms/PokemonRed.gb, then (free, no LLM):
uv run python play_generic.py --rom roms/PokemonRed.gb --steps 150
```

`play_generic.py` is the zero-model smoke test: the shared perceiver on any
GB/GBC/GBA ROM, scripted warmup + free exploration autopilot, headless by
default (`--window` for the SDL2 window, `--camera fixed|follow` to override
auto-detection). Per-game examples are in its docstring.

### LLM agent (a Claude plays over MCP)

The live LLM path is `world_mcp.py`: it exposes a world as an MCP (stdio)
server so a Claude Code instance is the System-2 brain — the free System-1
autopilot drives, and the LLM wakes only at decision points. It's an attended
test harness, not an unattended service. The full launch recipe (worlds,
start states, budgets) is in
[`reports/2026-06-26-mcp-claude-p-runbook.md`](reports/2026-06-26-mcp-claude-p-runbook.md).

> The earlier multi-backend driver (`play_pokemon.py` — Ollama / llama.cpp /
> aria over `/v1/chat/completions`) is archived in
> `games/pokemon_red/_archive/`, superseded by the MCP seam above.

### Starting past the intro

Pokémon Red's intro (Oak's speech + name entry) is unskippable, and a
button-mashing brain can't clear it. Generate a start state once, then boot the
agent straight into the overworld:

```bash
# auto-play past the intro, headless — no window, picks preset names RED/BLUE:
uv run python new_game.py --rom "roms/Pokemon Red.gb" --out start.state
# boot the agent from there:
uv run python play_generic.py --rom "roms/Pokemon Red.gb" --init-state start.state --steps 200
```

`new_game.py` is headless, so it needs no SDL2 window (and no `pysdl2-dll`).
Prefer to choose your own starting point (e.g. after getting a starter)? Use
`human_play.py` to play it yourself and save a state — that one opens an SDL2
window.

Save states are gitignored (they embed copyrighted game memory) — keep them local.

## How it's built

| Layer | What |
| ----- | ---- |
| `games/<game>/` | Per-world plugin + perceiver (cave_noire, gauntlet, pokemon_red). The heavy Red driver (reward shaping, `GamePlugin`) is archived in `games/pokemon_red/_archive/` — see its [README](games/pokemon_red/README.md). |
| `core/` | The shared machinery: gateway (single door), permission policies, runner loop, brains (scripted + LLM). |
| `core/contracts.py` | Frozen wire types every world and agent share. |
| `tests/` | Logic tests that run with no ROM and no PyBoy (the emulator is dependency-injected). |

Run the tests:

```bash
uv run pytest -q       # or: python -m pytest -q
```

## Which models can learn this

The agent only ever sees `(screen image, structured state)` and acts via 8
buttons, so the world is a shared benchmark for many learner families: LLM agent
loops, deep RL from pixels (PPO/DQN), RL from RAM features, model-based RL
(Dreamer/MuZero), imitation + offline RL, hierarchical/options, and classical
search for sub-problems (expectimax battles, A\* navigation). See
[`games/pokemon_red/README.md`](games/pokemon_red/README.md) for the full
breakdown.
