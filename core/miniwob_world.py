"""miniwob_world.py — a thin adapter owning a MiniWoB++ gymnasium env, mirroring the emulator adapters'
shape (core/gb_emulator.py, core/nds_emulator.py, core/gba_emulator.py): reset/screenshot/act.

Why this exists (see runs/miniwob_probe/PROBE_REPORT.md for the free probe that proved the loop):
MiniWoB is a COMPUTER-USE world — a real (headless Selenium/Chromium) browser task, not a Game Boy ROM —
so it doesn't share PyBoy/DeSmuME/mgba's Emulator surface (no `press`, no BUTTONS, no frame ticks). This
adapter gives world_mcp.py the same kind of narrow seam anyway: own the env, expose pixels + a small
action vocabulary, and WITHHOLD `dom_elements`/`fields` entirely (never even stored) — only `utterance`
(the human-given task text) and `screenshot` (numpy RGB) are kept from MiniWoB's observation dict.

No-leak rule (ADR-001, mirrored here): reward and DOM are the "oracle" for this world — scoring only,
logged by the caller to oracle.jsonl, NEVER returned by any method here that the MCP layer might forward
to the brain. `act()`'s return value is deliberately just (screenshot, done) — no reward inside it — the
caller must go to `.last_info` explicitly (and only world_mcp's oracle logger does).

Lazy import: `import miniwob` happens inside __init__, not at module load, so world_mcp.py stays
importable (and its tools/list handshake instant) in any environment without miniwob/selenium installed
(the main project env never gets these — Docker-image-only, per Dockerfile.miniwob).
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np

# The probe's measured real clickable height in headless Chromium (see PROBE_REPORT.md "Screenshot /
# episode facts"): the nominal TASK_HEIGHT constant (210) is NOT the real clickable viewport — clicking
# near y=205 raised MoveTargetOutOfBoundsException. Clamp to this, not the nominal task height.
VIEWPORT_HEIGHT = 177
VIEWPORT_WIDTH = 160  # TASK_WIDTH; the probe found no width surprise (only height was short of nominal).

# miniwob 1.0's own env classes, keyed by the short task names this world serves (registry mirrors
# world_mcp.GAMES' one-entry-per-task convention). Extend this dict to add another miniwob task.
_TASK_ENV_CLASSES = {
    "click-button": "ClickButtonEnv",
    "click-checkboxes": "ClickCheckboxesEnv",
    "focus-text": "FocusTextEnv",
}


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


class MiniWobWorld:
    """One live MiniWoB++ episode. Owns the gymnasium env; exposes screenshot + a small action set.

    `dom_elements` and `fields` are never read from the underlying obs dict anywhere in this class —
    that is the whole no-leak guarantee for this adapter (nothing to grep for downstream; the data
    simply never gets assigned to an attribute)."""

    def __init__(self, task_name: str, headless: bool = True, seed: Optional[int] = None) -> None:
        if task_name not in _TASK_ENV_CLASSES:
            raise ValueError(f"unknown miniwob task {task_name!r}; known: {sorted(_TASK_ENV_CLASSES)}")
        import miniwob  # noqa: F401  (lazy; registers gymnasium envs / makes miniwob.envs importable)
        from miniwob.envs import miniwob_envs

        env_cls = getattr(miniwob_envs, _TASK_ENV_CLASSES[task_name])
        self.task_name = task_name
        self.env = env_cls(render_mode=None if headless else "human")
        self.last_info: dict = {}       # reward/done live here ONLY — caller (world_mcp) reads this for
                                        # oracle.jsonl logging; never forwarded to a tool result.
        self._utterance: str = ""
        self._screenshot: Optional[np.ndarray] = None
        self._seed_counter = seed if seed is not None else 0

    # -- lifecycle -------------------------------------------------------------

    def reset(self, seed: Optional[int] = None) -> np.ndarray:
        """Start a new episode; return the initial screenshot. `dom_elements`/`fields` are read from the
        obs dict here but immediately discarded — only utterance + screenshot survive onto self."""
        use_seed = seed if seed is not None else self._seed_counter
        self._seed_counter = use_seed + 1
        obs, info = self.env.reset(seed=use_seed)
        self.last_info = dict(info or {})
        self._utterance = str(obs.get("utterance", ""))
        self._screenshot = np.asarray(obs["screenshot"])
        return self._screenshot

    @property
    def utterance(self) -> str:
        return self._utterance

    @property
    def screenshot(self) -> np.ndarray:
        if self._screenshot is None:
            raise RuntimeError("MiniWobWorld.screenshot read before reset()")
        return self._screenshot

    # -- actions -----------------------------------------------------------------
    # Pixels-only action vocabulary (PROBE_REPORT.md (c)): CLICK_COORDS, TYPE_TEXT, PRESS_KEY. No
    # CLICK_ELEMENT/TYPE_FIELD/FOCUS_ELEMENT_* — those are DOM-ref-based and out of scope for computer-use.

    def click(self, x: int, y: int) -> tuple[np.ndarray, bool]:
        """Click at (x, y), CLAMPED to the real clickable viewport (0..VIEWPORT_WIDTH-1 x
        0..VIEWPORT_HEIGHT-1 — see the module docstring's viewport-height gotcha)."""
        cx = _clamp(int(x), 0, VIEWPORT_WIDTH - 1)
        cy = _clamp(int(y), 0, VIEWPORT_HEIGHT - 1)
        action = self.env.unwrapped.create_action("CLICK_COORDS", coords=np.array([cx, cy]))
        return self._step(action)

    def type_text(self, text: str) -> tuple[np.ndarray, bool]:
        action = self.env.unwrapped.create_action("TYPE_TEXT", text=str(text))
        return self._step(action)

    def press_key(self, key: str) -> tuple[np.ndarray, bool]:
        action = self.env.unwrapped.create_action("PRESS_KEY", key=str(key))
        return self._step(action)

    def _step(self, action: Any) -> tuple[np.ndarray, bool]:
        obs, reward, terminated, truncated, info = self.env.step(action)
        self.last_info = {**dict(info or {}), "reward": float(reward),
                          "terminated": bool(terminated), "truncated": bool(truncated)}
        self._utterance = str(obs.get("utterance", self._utterance))
        self._screenshot = np.asarray(obs["screenshot"])
        return self._screenshot, bool(terminated or truncated)

    def close(self) -> None:
        try:
            self.env.close()
        except Exception:
            pass
