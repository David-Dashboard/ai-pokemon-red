# Pokémon Red world plugin

An emulator-driven Pokémon Red world for the Arena testbed. An agent plays the
*actual* game (via the PyBoy Game Boy emulator) by emitting button-press
ToolCalls through the gateway — the "Claude Plays Pokémon" setup, wired to the
contract.

## Contract posture

This is the testbed's stand-in for **the real desktop**, so it follows the
real-world rules in `CONTRACT.md`, not the simulated-world ones:

| Aspect              | Choice                                                              |
| ------------------- | ------------------------------------------------------------------ |
| Protocol            | `GamePlugin` **only** — no `Replayable`. An open-world RPG has no clean reset/terminal. |
| Time regime         | Real-world: `t` = unix epoch seconds (invariant 6).                |
| Errors              | Observations: a bad button → `ok=False` ToolResult with the legal buttons (invariant 2). |
| Screen on the wire  | None. The frame is saved to disk; `Observation.data["screen_path"]` carries the path (invariant 3). |
| Permissions         | `Allowlist`, **not** allow-all — it permits exactly the in-game button tools (honors the real-world hard rule, while the sandbox stays playable). |

## Setup

```bash
pip install -r requirements-pokemon.txt        # installs PyBoy + deps
```

Then **supply your own legally-obtained Pokémon Red ROM** (`.gb`). No ROM is
bundled with this project and none will be downloaded for you.

## Run

```bash
# Zero-model smoke test — proves the gateway→plugin→emulator pipeline:
python play_pokemon.py --rom path/to/PokemonRed.gb --brain scripted --steps 50

# LLM agent via a local Ollama vision model:
python play_pokemon.py --rom path/to/PokemonRed.gb --brain llm \
    --model llama3.2-vision --steps 200 --window
```

Point the LLM brain at any model by passing your own `complete_fn` to
`LLMButtonBrain` (e.g. the Claude API for a much stronger player).

## Files

| File            | Role                                                              |
| --------------- | ----------------------------------------------------------------- |
| `emulator.py`   | The **only** PyBoy import. Thin surface: press / tick / read / screen. |
| `memory_map.py` | Curated Pokémon Red WRAM addresses → structured state. Pure; no emulator. |
| `reward.py`     | Synthetic reward from state deltas (badges, levels, exploration). |
| `plugin.py`     | `PokemonRedPlugin(GamePlugin)`: tools / handle / observe / drain_events. |

The emulator is **dependency-injected**, so all logic is unit-tested against a
fake RAM with no ROM and no PyBoy (`tests/test_pokemon_red.py`).

> ⚠️ The memory addresses target the US/EN ROM revision. A wrong address yields
> wrong *telemetry*, not a crash — if a field looks bogus, suspect the address.

## Who (else) can learn to play this

The agent only ever sees `(screen_path, structured_state)` and acts via 8
buttons — a clean, model-agnostic interface. That makes this world a benchmark
many learner families can share through the same front door:

- **LLM agent loop** (what's wired here) — vision/text model reasons over the
  screen + state and picks a button. Add the KB reflection loop so it rewrites
  its own strategy between episodes. Strong at menus, dialog, and planning;
  weak at precise navigation and long-horizon credit assignment.
- **Deep RL from pixels** — PPO / DQN / Rainbow on the screen buffer with the
  shaped reward in `reward.py`. This is Peter Whidden's *PokemonRedExperiments*
  recipe. Wants the fast Gym path (contract invariant 9), then wraps the trained
  policy as a `Brain` to play through the gateway like everyone else.
- **RL from RAM features** — feed the structured state vector instead of pixels.
  Smaller nets, faster, but blind to anything not in the memory map.
- **Model-based RL / world models** (Dreamer, MuZero) — learn a latent dynamics
  model and plan inside it; suits the long horizons and sparse badges.
- **Imitation / behavior cloning + offline RL** — record human or strong-agent
  episodes (the event log is already replay-shaped) and train a policy to copy
  them; fine-tune with RL.
- **Hierarchical / options** — a high-level planner picks subgoals ("reach the
  gym") and low-level controllers (learned or scripted A\*) execute navigation.
  Often the most sample-efficient on a game this long.
- **Classical search for sub-problems** — battles are near-perfect-information
  turn games (expectimax/minimax over damage rolls); overworld navigation is
  A\* on the tile map. Hybrids that hand these to search and use the LLM/RL only
  for the open-ended glue tend to outperform any single method.
