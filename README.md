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

## Quickstart

```bash
pip install -r requirements-pokemon.txt        # installs PyBoy + deps
# put your ROM at roms/PokemonRed.gb, then:
python play_pokemon.py --rom roms/PokemonRed.gb --brain scripted --steps 50
```

`--brain scripted` is a zero-model smoke test. For an LLM agent via a local
Ollama vision model:

```bash
python play_pokemon.py --rom roms/PokemonRed.gb --brain llm \
    --model llama3.2-vision --steps 200 --window
```

## How it's built

| Layer | What |
| ----- | ---- |
| `games/pokemon_red/` | The world plugin: emulator wrapper, RAM memory-map, reward shaping, `GamePlugin` (see its [README](games/pokemon_red/README.md)). |
| `core/` | The shared machinery: gateway (single door), permission policies, runner loop, brains (scripted + LLM). |
| `core/contracts.py` | Frozen wire types every world and agent share. |
| `tests/` | Logic tests that run with no ROM and no PyBoy (the emulator is dependency-injected). |

Run the tests:

```bash
python -m pytest -q
```

## Which models can learn this

The agent only ever sees `(screen image, structured state)` and acts via 8
buttons, so the world is a shared benchmark for many learner families: LLM agent
loops, deep RL from pixels (PPO/DQN), RL from RAM features, model-based RL
(Dreamer/MuZero), imitation + offline RL, hierarchical/options, and classical
search for sub-problems (expectimax battles, A\* navigation). See
[`games/pokemon_red/README.md`](games/pokemon_red/README.md) for the full
breakdown.
