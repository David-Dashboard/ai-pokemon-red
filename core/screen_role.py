"""Agnostic NDS screen-role discovery — assigns "gameplay" vs "symbolic" from BEHAVIOUR, no priors.

NDS has two screens (top 256×192, bottom 256×192). Which one is the spatial gameplay surface varies by
game: top for Pokémon/NSMB, bottom for touch games like Phoenix Wright, split for Mario Kart. This
module discovers the role purely from observable signals, the same way the project grounds camera class
from pixels. No prior toward top or bottom is encoded here; priors can be layered on top later.

Signals (both numpy-only, both per-screen):
  1. Modality: run detect_modality per screen. The screen that reads "gameplay" (widespread change) is
     the spatial candidate; a "menu"/"static" screen is symbolic. This is already proven for GB worlds.
  2. Control-correlation: when a movement or button command is issued, measure how much each screen
     changes (mean-abs frame-diff). The screen whose change tracks the commands is the gameplay screen.
     We use a simple, cheap approach: compare mean-abs-diff under commanded actions vs under idle/no-action
     frames. The gameplay screen's diff rises more under commands. This reuses the egomotion best_shift
     idea (control-correlated change) without needing to run it twice per frame — a coarser but sufficient
     signal for role assignment.

Decision protocol:
  - Accumulate evidence over a rolling window before committing (no single-frame decisions).
  - Return {"gameplay": "top"|"bottom"|None, "symbolic": "top"|"bottom"|None, "confidence": float}.
  - Ties and ambiguity → None, low confidence; never fabricate a pick.

Complexity: O(H*W) per step; no persistent allocations; pure numpy.
"""
from __future__ import annotations

from typing import Literal, Optional

import numpy as np

from core.modality import detect_modality

# --- tuning constants -------------------------------------------------------
# Minimum steps before we commit to a role; avoids boot-frame noise.
_MIN_STEPS = 3
# Rolling window size for evidence accumulation.
_WINDOW = 8
# A screen wins control-correlation if its mean diff under commands is this many times
# larger than the other screen's (or the idle baseline).
_CORR_RATIO = 1.25
# Modality vote weight vs correlation vote weight when combining evidence.
_MODAL_W = 0.6
_CORR_W = 0.4
# Confidence threshold below which we report None (ambiguous).
_CONF_THRESHOLD = 0.40

# Movement/direction buttons that are unambiguous spatial commands.
_MOVEMENT = frozenset(("up", "down", "left", "right"))
# All NDS buttons considered "input" (for idle vs commanded diff).
_ALL_BUTTONS = frozenset(("a", "b", "x", "y", "l", "r", "start", "select",
                           "up", "down", "left", "right"))


def _gray(frame: np.ndarray) -> np.ndarray:
    """(H,W,3|4) or (H,W) -> float32 grayscale."""
    a = np.asarray(frame, dtype=np.float32)
    if a.ndim == 3:
        return a[..., :3].mean(axis=2)
    return a


def _mean_diff(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> float:
    """Mean absolute difference between two same-shape arrays; 0.0 if either is None."""
    if a is None or b is None:
        return 0.0
    return float(np.abs(a.astype(np.float32) - b.astype(np.float32)).mean())


class ScreenRoleDiscovery:
    """Rolling-window agnostic NDS screen-role classifier.

    Usage:
        disc = ScreenRoleDiscovery()
        for top_frame, bottom_frame, action in history:
            result = disc.update(top_frame, bottom_frame, action)
        # result = {"gameplay": "top"|"bottom"|None, "symbolic": ..., "confidence": float}

    `action` is a string like "right", "a", "right+b", or None/empty for idle.
    All state is in-process numpy arrays; no disk IO, no external deps beyond numpy + modality.
    """

    def __init__(self, window: int = _WINDOW, min_steps: int = _MIN_STEPS) -> None:
        self._window = window
        self._min_steps = min_steps
        # Rolling history: lists of (prev_top, prev_bot) and (cur_top, cur_bot) gray frames,
        # modality votes, diff-under-command, and whether step had a command.
        self._prev_top: Optional[np.ndarray] = None
        self._prev_bot: Optional[np.ndarray] = None
        self._steps = 0

        # Per-screen modality score accumulators (higher = more "gameplay").
        # We store the raw (label, confidence) tuples and score them.
        self._modal_top: list[float] = []   # +1 gameplay, -1 menu/static, 0 unknown; weighted by conf
        self._modal_bot: list[float] = []

        # Diff under commanded actions (for control-correlation).
        self._diff_top_cmd: list[float] = []
        self._diff_bot_cmd: list[float] = []
        self._diff_top_idle: list[float] = []
        self._diff_bot_idle: list[float] = []

        self._last_result: dict = {"gameplay": None, "symbolic": None, "confidence": 0.0}

    def update(
        self,
        top_frame: np.ndarray,
        bottom_frame: np.ndarray,
        action: Optional[str] = None,
    ) -> dict:
        """Ingest one (top, bottom, action) step and return the current role assignment.

        `action` is a button string like "right", "a+b", or None/empty for idle/no-input.
        Returns {"gameplay": "top"|"bottom"|None, "symbolic": "top"|"bottom"|None, "confidence": float}.
        """
        top_g = _gray(top_frame)
        bot_g = _gray(bottom_frame)
        self._steps += 1

        # --- per-screen modality ---
        top_label, top_conf = detect_modality(self._prev_top, top_g)
        bot_label, bot_conf = detect_modality(self._prev_bot, bot_g)

        def _modal_score(label: str, conf: float) -> float:
            if label == "gameplay":
                return conf
            if label in ("menu", "static"):
                return -conf
            return 0.0  # "unknown"

        self._modal_top.append(_modal_score(top_label, top_conf))
        self._modal_bot.append(_modal_score(bot_label, bot_conf))
        # Keep only the rolling window.
        self._modal_top = self._modal_top[-self._window:]
        self._modal_bot = self._modal_bot[-self._window:]

        # --- control-correlation (diff under MOVEMENT commands vs idle) ---
        # Only direction presses are unambiguous spatial commands; menu buttons (start/select/a/b)
        # also drive title/menu animations which corrupt correlation for role detection.
        toks = str(action or "").replace("+", " ").split()
        is_movement = any(tok in _MOVEMENT for tok in toks)
        is_idle = not bool(action)

        diff_top = _mean_diff(self._prev_top, top_g)
        diff_bot = _mean_diff(self._prev_bot, bot_g)
        if is_movement:
            self._diff_top_cmd.append(diff_top)
            self._diff_bot_cmd.append(diff_bot)
        elif is_idle:
            self._diff_top_idle.append(diff_top)
            self._diff_bot_idle.append(diff_bot)
        # Non-movement button presses (a/b/start/select) are not tracked:
        # they may cause menu transitions on either screen and don't reliably indicate
        # which screen is spatial.

        self._diff_top_cmd = self._diff_top_cmd[-self._window:]
        self._diff_bot_cmd = self._diff_bot_cmd[-self._window:]
        self._diff_top_idle = self._diff_top_idle[-self._window:]
        self._diff_bot_idle = self._diff_bot_idle[-self._window:]

        self._prev_top = top_g
        self._prev_bot = bot_g

        # --- decide ---
        self._last_result = self._decide()
        return self._last_result

    def _decide(self) -> dict:
        """Combine modality and control-correlation evidence into a role assignment."""
        if self._steps < self._min_steps:
            return {"gameplay": None, "symbolic": None, "confidence": 0.0,
                    "_debug": {"reason": "insufficient_steps", "steps": self._steps}}

        # --- modality vote ---
        avg_modal_top = float(np.mean(self._modal_top)) if self._modal_top else 0.0
        avg_modal_bot = float(np.mean(self._modal_bot)) if self._modal_bot else 0.0
        # Normalize to [-1, 1] each; top wins modality if avg_modal_top > avg_modal_bot.
        modal_margin = avg_modal_top - avg_modal_bot  # >0 favors top, <0 favors bottom

        # --- control-correlation vote ---
        # The gameplay screen changes MORE under commanded actions (relative to its idle baseline).
        # Correlation score for each screen = mean_diff_commanded / (mean_diff_idle + ε)
        _eps = 0.5
        top_cmd_mean = float(np.mean(self._diff_top_cmd)) if self._diff_top_cmd else 0.0
        top_idle_mean = float(np.mean(self._diff_top_idle)) if self._diff_top_idle else _eps
        corr_top = top_cmd_mean / (top_idle_mean + _eps) + _eps

        bot_cmd_mean = float(np.mean(self._diff_bot_cmd)) if self._diff_bot_cmd else 0.0
        bot_idle_mean = float(np.mean(self._diff_bot_idle)) if self._diff_bot_idle else _eps
        corr_bot = bot_cmd_mean / (bot_idle_mean + _eps) + _eps

        # We care about which screen has HIGHER corr, and by how much.
        corr_margin = corr_top - corr_bot  # >0 favors top, <0 favors bottom

        # --- combine: weighted sum of normalized margins ---
        # Normalize each margin to [-1, 1] loosely (clamp).
        def _clamp(x: float) -> float:
            return max(-1.0, min(1.0, x))

        modal_norm = _clamp(modal_margin)

        # If no movement-command data has been collected yet (e.g. we are still in title screens
        # pressing Start/Select), do not let the zero-baseline correlation corrupt the decision.
        # Fall back to modality-only until we have seen at least one movement command.
        has_movement_data = bool(self._diff_top_cmd or self._diff_bot_cmd)
        if has_movement_data:
            corr_norm = _clamp(corr_margin / max(abs(corr_top), abs(corr_bot), 1.0))
            combined = _MODAL_W * modal_norm + _CORR_W * corr_norm
        else:
            corr_norm = 0.0
            # Modality-only; scale confidence down a bit since we lack the second signal.
            combined = _MODAL_W * modal_norm

        # Map combined score to a winner and confidence.
        # combined > 0 → top is more gameplay; < 0 → bottom.
        confidence = min(1.0, abs(combined))

        debug = {
            "modal_top": round(avg_modal_top, 3),
            "modal_bot": round(avg_modal_bot, 3),
            "modal_margin": round(modal_margin, 3),
            "corr_top": round(corr_top, 3),
            "corr_bot": round(corr_bot, 3),
            "corr_margin": round(corr_margin, 3),
            "combined": round(combined, 3),
            "confidence": round(confidence, 3),
            "steps": self._steps,
        }

        if confidence < _CONF_THRESHOLD:
            # Both screens look the same, or not enough evidence — could be boot/transition.
            return {"gameplay": None, "symbolic": None, "confidence": round(confidence, 3),
                    "_debug": {**debug, "reason": "low_confidence"}}

        if combined > 0:
            gameplay, symbolic = "top", "bottom"
        else:
            gameplay, symbolic = "bottom", "top"

        return {"gameplay": gameplay, "symbolic": symbolic,
                "confidence": round(confidence, 3), "_debug": debug}

    @property
    def result(self) -> dict:
        """The most recent role assignment without advancing state."""
        return self._last_result

    def reset(self) -> None:
        """Clear all accumulated evidence (e.g. on a scene transition)."""
        self.__init__(self._window, self._min_steps)
