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
# put your ROM at roms/PokemonRed.gb, then:
uv run python play_pokemon.py --rom roms/PokemonRed.gb --brain scripted --steps 50
```

Or with pip:

```bash
pip install -r requirements-pokemon.txt
python play_pokemon.py --rom roms/PokemonRed.gb --brain scripted --steps 50
```

`--brain scripted` is a zero-model smoke test. For an LLM agent, point it at a
local model server:

```bash
# Ollama (default backend):
uv run python play_pokemon.py --rom roms/PokemonRed.gb --brain llm \
    --model llama3.2-vision --steps 200 --window

# llama.cpp (llama-server, OpenAI-compatible; start it with --mmproj for vision):
uv run python play_pokemon.py --rom roms/PokemonRed.gb --brain llm --backend llamacpp \
    --steps 200 --window
```

`--backend llamacpp` talks to `http://localhost:8080/v1/chat/completions` by
default (override with `--llm-url`). Vision needs a multimodal model; otherwise
add `--no-vision` for a text-only prompt.

### Playing through a decoupled agent (`ai-aria`)

The agent's "brain" is fully decoupled from this project: any server that speaks
the OpenAI `/v1/chat/completions` shape can drive the game. [`ai-aria`](https://github.com/David-Dashboard/ai-aria)
is one such agent — it runs as its **own** service (its own repo + Docker) and we
only ever speak HTTP to it; none of its code is imported here.

Start aria separately (see its README — `docker compose up -d`, listens on
`:8001`, bearer-authed), then point the game at it:

```bash
# token comes from $ARIA_BEARER_TOKEN, or pass --llm-token
ARIA_BEARER_TOKEN=your-token uv run python play_pokemon.py \
    --rom roms/PokemonRed.gb --brain llm --backend aria \
    --load-state start.state --steps 200 --window
```

`--backend aria` defaults to `http://localhost:8001` and model `aria` (override
with `--llm-url` / `--model`). It's the same OpenAI wire format as `llamacpp`,
just with an `Authorization: Bearer` header. aria is a vision-capable companion,
so screenshots are sent by default; add `--no-vision` for a text-only prompt.
(Note: aria is a memory-keeping *companion*, not a tuned game policy — every turn
writes to her journal and runs her full agent loop, so expect higher per-step
latency than a bare model server.)

Example GPU server (Docker + CUDA) serving a vision model — `--jinja` enables the
chat template, `-ngl 99` offloads all layers to the GPU:

```bash
docker run --gpus all -p 8080:8080 -v llama-cache:/root/.cache/llama.cpp \
    ghcr.io/ggml-org/llama.cpp:server-cuda \
    -hf unsloth/Qwen3-VL-8B-Instruct-GGUF:Q4_K_M --jinja -ngl 99 -c 16384
```

### Starting past the intro

Pokémon Red's intro (Oak's speech + name entry) is unskippable, and a
button-mashing brain can't clear it. Generate a start state once, then boot the
agent straight into the overworld:

```bash
# auto-play past the intro, headless — no window, picks preset names RED/BLUE:
uv run python new_game.py --rom "roms/Pokemon Red.gb" --out start.state
# boot the agent from there:
uv run python play_pokemon.py --rom "roms/Pokemon Red.gb" --load-state start.state --brain scripted --steps 200
```

`new_game.py` is headless, so it needs no SDL2 window (and no `pysdl2-dll`).
Prefer to choose your own starting point (e.g. after getting a starter)? Use
`human_play.py` to play it yourself and save a state — that one opens an SDL2
window.

Save states are gitignored (they embed copyrighted game memory) — keep them local.

## How it's built

| Layer | What |
| ----- | ---- |
| `games/pokemon_red/` | The world plugin: emulator wrapper, RAM memory-map, reward shaping, `GamePlugin` (see its [README](games/pokemon_red/README.md)). |
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
