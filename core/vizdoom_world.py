"""vizdoom_world.py -- a thin adapter owning a live vizdoom.DoomGame, mirroring the shape of the other
per-world adapters (core/miniwob_world.py, core/gb_emulator.py): reset/step/screen, nothing more.

Design: reports/2026-07-04-vizdoom-3d-floor-design.md S3 (seam mapping) + AMENDMENT A1.3/A1.4 (the
re-pinned dtc_gate scenario). Probe facts carried forward (runs/vizdoom_precheck/PRECHECK_REPORT.md,
the 2026-07-03 free pre-check that is this adapter's only live-vizdoom evidence so far):
  - `get_state()` returns None after `is_episode_finished()` -- every state read MUST guard it (every
    method below that reads state does so).
  - Button/variable arrays are ORDER-SENSITIVE -- `set_available_buttons`/`set_available_game_variables`
    fix an order at init time; this adapter builds its action vectors and reads variables by NAME
    lookup against that same fixed order, never a hard-coded positional index (the probe's own
    gotcha, called out again in the design doc S3.2).
  - Frame alignment convention used throughout this project's fixtures: frame_i is the state BEFORE
    action_i (i.e. reset()/step() both return the CURRENT screen, matching what an agent would have
    seen before choosing the next action) -- kept here so oracle rows line up with the exact frame the
    brain (or a scripted baseline) was reasoning from.

Lazy import: `import vizdoom` happens inside __init__, not at module load, so world_mcp.py (and any
test importing this module) stays importable in any environment without vizdoom installed -- vizdoom
lives ONLY in Dockerfile.vizdoom, mirroring core/miniwob_world.py's lazy-import discipline for
miniwob/selenium. vizdoom==1.3.0 pinned (the probe's proven recipe; PRECHECK_REPORT.md, the design
doc S0/S2.1).

No-leak law (unchanged): HEALTH/AMMO2/KILLCOUNT are the oracle for this world -- `game_variables()`
returns them to the CALLER (world_mcp's session class), which is responsible for writing them to
oracle.jsonl ONLY and never forwarding them into a tool result. This module does not know about
oracle.jsonl at all -- that responsibility sits one layer up, same separation as MiniWobWorld/
MiniWobSession.

Action grain (design AMENDMENT A1.3, A1.4 -- pinned, not a parameter): every `step()` call executes
with `tics=TICS_PER_STEP` FIXED. There is no variable-tics knob on this adapter or its MCP tools --
brain and scripted baselines must share the identical action grain (the gate's equivalence pin).
"""
from __future__ import annotations

import os
from typing import NamedTuple, Optional

import numpy as np

TICS_PER_STEP = 4   # FIXED per design AMENDMENT A1.3/A1.4 -- not a caller-supplied parameter.

# dtc_gate's pinned button set (design AMENDMENT A1.3): TURN_LEFT, TURN_RIGHT, ATTACK -- dtc's native
# set, no strafes/no translation, so "ego-stationary" for P2 reduces to "did not turn".
BUTTON_NAMES = ("TURN_LEFT", "TURN_RIGHT", "ATTACK")
# Oracle-side-only game variables (design S2.1/S3.3): HEALTH/AMMO2/KILLCOUNT. KILLCOUNT is NOT in
# defend_the_center.cfg's default variable list (probe fact) -- must be added explicitly.
GAME_VARIABLE_NAMES = ("HEALTH", "AMMO2", "KILLCOUNT")


class StepResult(NamedTuple):
    """What one step() (or reset()) hands back to the caller. `screen` is None exactly when
    `episode_finished` is True and `get_state()` returned None (the probe's episode-boundary guard) --
    the caller must never treat a None screen as "no change", only as "episode over, read no further"."""
    screen: Optional[np.ndarray]     # (H, W, 3) uint8 RGB, or None at/after episode end
    episode_finished: bool
    tic: int                         # last known tic (0 if never observed this episode)


class VizdoomWorld:
    """One live vizdoom.DoomGame session for a single scenario .cfg. Owns the game; exposes
    reset(seed)/step(action_name, repeat)/screen/game_variables()/get_state()-guarded episode status.

    One-attempt-per-seed enforcement (design A1.4's "one attempt per seed" degenerate guard) is a
    HARNESS-level responsibility, not this adapter's -- this class does not track "have I already
    attempted seed X"; it simply starts whatever seed `reset()` is given. The brief is explicit that
    the scorer relies on the harness (world_mcp's session class, mirroring MiniWobSession's shape)
    enforcing "new_episode before done => this seed's episode is abandoned, KILLCOUNT recorded at
    abandonment", NOT on this module refusing a reset. See core/vizdoom_world.py's caller
    (world_mcp.DoomDtcSession) for where that enforcement actually lives.
    """

    def __init__(self, cfg_path: str, *, window_visible: bool = False) -> None:
        import vizdoom as vzd   # lazy: only paid on first construction, never at module import time
        self.cfg_path = cfg_path
        game = vzd.DoomGame()
        game.load_config(cfg_path)
        # dtc_gate.cfg's `doom_scenario_path = defend_the_center.wad` names the STOCK wad bundled
        # inside the vizdoom package (no .wad is committed to this repo, per the brief) -- resolve it
        # explicitly against vzd.scenarios_path via the API rather than relying on load_config's
        # relative-path handling, so this works regardless of cwd or vizdoom's own path-resolution
        # rules for a cfg living outside its scenarios/ directory.
        game.set_doom_scenario_path(os.path.join(vzd.scenarios_path, "defend_the_center.wad"))
        game.set_screen_format(vzd.ScreenFormat.RGB24)
        game.set_screen_resolution(vzd.ScreenResolution.RES_320X240)
        game.set_window_visible(window_visible)
        game.set_available_buttons([getattr(vzd.Button, n) for n in BUTTON_NAMES])
        game.set_available_game_variables([getattr(vzd.GameVariable, n) for n in GAME_VARIABLE_NAMES])
        game.init()
        self.game = game
        # Name-keyed action vectors -- built from get_available_buttons() by NAME, never a hard-coded
        # positional index (the probe's order-sensitivity gotcha, S3.2).
        live_buttons = [str(b).rsplit(".", 1)[-1] for b in game.get_available_buttons()]
        self._button_index = {name: live_buttons.index(name) for name in BUTTON_NAMES}
        self._n_buttons = len(live_buttons)
        live_vars = [str(v).rsplit(".", 1)[-1] for v in game.get_available_game_variables()]
        self._var_index = {name: live_vars.index(name) for name in GAME_VARIABLE_NAMES}
        self._tic = 0
        self._episode_index = -1

    # -- action vector construction (by name, per BUTTON_NAMES order actually reported live) ----------

    def _action_vector(self, button_name: str) -> list[int]:
        vec = [0] * self._n_buttons
        vec[self._button_index[button_name]] = 1
        return vec

    # -- lifecycle ------------------------------------------------------------------------------------

    def reset(self, seed: Optional[int] = None) -> StepResult:
        """Start a new episode on `seed` (pinned-seed harness discipline: the caller supplies the
        seed; this adapter never invents one). Returns the initial screen."""
        if seed is not None:
            self.game.set_seed(int(seed))
        self.game.new_episode()
        self._episode_index += 1
        self._tic = 0
        return self._read_state()

    def _read_state(self) -> StepResult:
        """Guarded state read (probe integration fact: get_state() is None after episode end)."""
        if self.game.is_episode_finished():
            return StepResult(screen=None, episode_finished=True, tic=self._tic)
        s = self.game.get_state()
        if s is None:
            return StepResult(screen=None, episode_finished=True, tic=self._tic)
        self._tic = int(s.tic)
        return StepResult(screen=np.asarray(s.screen_buffer), episode_finished=False, tic=self._tic)

    def step(self, button_name: str, repeat: int = 1) -> StepResult:
        """Execute `button_name` (must be one of BUTTON_NAMES) `repeat` times (System-1 grain, design
        A1.3: "a `repeat: 1..10` parameter ... the same single action executed repeat times at
        tics=4 each"), each execution ticking TICS_PER_STEP (FIXED — never a caller-supplied tics).
        Stops early if the episode ends mid-repeat. Returns the state AFTER the last execution."""
        if button_name not in BUTTON_NAMES:
            raise ValueError(f"unknown button {button_name!r}; must be one of {BUTTON_NAMES}")
        vec = self._action_vector(button_name)
        for _ in range(max(1, min(int(repeat), 10))):
            if self.game.is_episode_finished():
                break
            self.game.make_action(vec, TICS_PER_STEP)
        return self._read_state()

    def screen(self) -> Optional[np.ndarray]:
        """Current screen without stepping (guarded the same way as reset/step)."""
        return self._read_state().screen

    def game_variables(self) -> Optional[dict]:
        """Oracle-side values ONLY (design no-leak law: HEALTH/AMMO2/KILLCOUNT never cross the MCP
        wire — the caller is responsible for routing this dict to oracle.jsonl and nothing else).
        Returns None when the episode has ended (guarded — game_variables() on a dead game raises in
        some vizdoom builds; probe-consistent with every other state read here)."""
        if self.game.is_episode_finished():
            return None
        try:
            raw = self.game.get_state()
        except Exception:
            return None
        if raw is None:
            return None
        gv = raw.game_variables
        return {name: float(gv[idx]) for name, idx in self._var_index.items()}

    @property
    def episode_finished(self) -> bool:
        return bool(self.game.is_episode_finished())

    @property
    def tic(self) -> int:
        return self._tic

    @property
    def episode_index(self) -> int:
        return self._episode_index

    def close(self) -> None:
        try:
            self.game.close()
        except Exception:
            pass
