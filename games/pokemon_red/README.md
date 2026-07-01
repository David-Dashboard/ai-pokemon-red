# Pokémon Red world

A Pokémon Red world for the game-agnostic MCP harness (`world_mcp.py --game pokemon_red`), same lean
`PerceptionPlugin` shape as `games/cave_noire` / `games/gauntlet`. An agent (or `claude -p` MCP brain)
plays the *actual* game (via the PyBoy Game Boy emulator) by emitting button-press ToolCalls through the
gateway — the "Claude Plays Pokémon" setup, wired to the contract.

## Contract posture

Ships per-world CONFIG only (see `__init__.py` / `plugin.py`): the sandbox and a `PokemonRedPlugin`
(`core.perception_plugin.PerceptionPlugin` wired with Pokémon's flavor text). The brain (`core/`) and the
world-interface infra (the plugin body) are reused UNCHANGED.

| Aspect              | Choice                                                              |
| ------------------- | ------------------------------------------------------------------ |
| Perception          | Pixels-derived `SymbolicState` only (`perceiver.py`'s `OverworldPerceiver`) — no RAM in the observation. |
| Time regime         | Real-world: `t` = unix epoch seconds (invariant 6).                |
| Errors              | Observations: a bad button → `ok=False` ToolResult with the legal buttons (invariant 2). |
| Screen on the wire  | None by default. The frame is saved to disk; `Observation.data["screen_path"]` carries the path (invariant 3). |
| Permissions         | `Allowlist`, **not** allow-all — it permits exactly the in-game button tools. |

## Setup

Supply your own legally-obtained Pokémon Red ROM (`.gb`) at `roms/PokemonRed.gb`. No ROM is bundled with
this project and none will be downloaded for you.

## Run

```bash
# Build a gameplay start-state (mashes the unskippable intro headless):
python new_game.py --rom roms/PokemonRed.gb --out runs/red_start.state

# Serve it over MCP for a claude -p brain (see reports/2026-06-26-mcp-claude-p-runbook.md and
# runs/brain_red_starter/ for the full task-brief recipe):
python world_mcp.py --game pokemon_red --init-state runs/red_start.state --out runs/mcp_world
```

## Files

| File            | Role                                                              |
| --------------- | ----------------------------------------------------------------- |
| `__init__.py`   | `PokemonRedPlugin` (the lean `PerceptionPlugin` subclass) + `POKEMON_SANDBOX`. |
| `perceiver.py`  | `OverworldPerceiver`: pixels → `SymbolicState` (odometry + occupancy map + textbox decode). |
| `textbox.py`    | Gen-1 dialog/menu glyph decoding, used by the perceiver. |
| `saliency.py`   | Motion-saliency (NPC/ROI detection), used by the perceiver. |
| `emulator.py`   | Pokémon's own PyBoy wrapper (fade detection + battle-settle pacing). Not currently wired into the MCP seam (`world_mcp.World` builds the generic `core.gb_emulator.PyBoyEmulator`); kept for direct/injected use. |
| `memory_map.py` | Curated Pokémon Red WRAM addresses → structured state. Pure; no emulator. Source of truth for `world_mcp.py`'s `watch` map (scoring oracle only). |
| `_archive/`     | The pre-seam heavy `GamePlugin` (`plugin.py`: RAM observe, reward shaping, battle-settle wiring) and `reward.py`. Superseded by the lean plugin above; kept for reference, excluded from pytest collection. |

The emulator is **dependency-injected**, so all logic is unit-tested against a
fake RAM with no ROM and no PyBoy (`tests/test_pokemon_red.py`, `tests/test_perception.py`,
`tests/test_no_ram_leak.py`).

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
