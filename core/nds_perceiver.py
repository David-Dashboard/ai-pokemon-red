"""Agnostic NDS spatial perceiver — routes GridPerceiver to the DISCOVERED gameplay screen.

The screen whose behaviour reads as "gameplay" (via ScreenRoleDiscovery) receives the spatial
pipeline; the other is treated as symbolic. Which screen that is is not hard-coded: the discovery
runs purely from pixels + commands, top-bias-free, and re-evaluates on every call so it can
adapt to games that transition between modes.

Usage (in a PerceptionPlugin or a live NDS session):

    from core.nds_perceiver import NDSPerceiver
    from core.grid_perceiver import CameraScrollSignal

    perceiver = NDSPerceiver(move_signal=CameraScrollSignal())
    sym = perceiver.perceive(dual_frame, memory, context={"last_action": "right"})

`dual_frame` is the (384, 256, 3) array from DeSmuMEEmulator.screen_ndarray() (top=[:192], bottom=[192:]).
`context["last_action"]` is the button string used by the upstream plugin, same as for GridPerceiver.

The adapter is intentionally thin: it slices the dual frame, runs discovery, and delegates
everything else to GridPerceiver unchanged. 256×192 NDS screens vs 160×144 GB screens are
handled by passing nw/nh to GridPerceiver so best_shift and grid-math are correct.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np

from core.grid_perceiver import CameraScrollSignal, GridPerceiver, MoveSignal
from core.perception import JSON, PerceptMemory, SymbolicState
from core.screen_role import ScreenRoleDiscovery

# NDS screen dimensions (each half of the 384×256 dual buffer).
_NDS_H = 192
_NDS_W = 256

# best_shift normalisation for 256×192 (scale the GB 128×112 by the NDS/GB ratio; keep aspect).
# GB: 160×144 -> normalised 128×112 (ratio ~0.80).  NDS: 256×192 -> use 160×140 (~0.625).
# Rounded to be divisible by the 8-cell grid used in grid_max_change.
_NW = 160   # 256 * 0.625
_NH = 120   # 192 * 0.625  (nearest multiple of 8 = 120)
# best_shift search range on the normalised frame: NDS maps scroll more per step, so open it up.
_MAX_SHIFT = 24
_STEP = 2


class NDSPerceiver:
    """Agnostic NDS perceiver. Routes the spatial pipeline to whichever screen discovery picks.

    Parameters
    ----------
    move_signal:
        The per-world MoveSignal, same as GridPerceiver. Defaults to CameraScrollSignal
        (correct for top-down/side-scroll games like Pokémon/NSMB). Override for touch games.
    discovery_window:
        Rolling-window size for ScreenRoleDiscovery.
    discovery_min_steps:
        Steps before discovery commits. Frames before commitment are routed to top (safe default
        for boot frames, but the perceiver will self-correct as evidence accumulates).
    fallback_screen:
        Which screen to use before discovery commits (or on low confidence). "top" matches
        the historical majority of NDS games and is the right bootstrap for NSMB; overrideable.
    """

    def __init__(
        self,
        move_signal: Optional[MoveSignal] = None,
        *,
        discovery_window: int = 8,
        discovery_min_steps: int = 3,
        fallback_screen: str = "top",
    ) -> None:
        if move_signal is None:
            move_signal = CameraScrollSignal()
        self._grid = GridPerceiver(
            move_signal, max_shift=_MAX_SHIFT, step=_STEP, nw=_NW, nh=_NH
        )
        self._discovery = ScreenRoleDiscovery(
            window=discovery_window, min_steps=discovery_min_steps
        )
        self._fallback = fallback_screen
        self._last_role: dict = {"gameplay": None, "symbolic": None, "confidence": 0.0}

    # -- Perceiver Protocol --------------------------------------------------

    def perceive(
        self,
        frame: Any,
        memory: PerceptMemory,
        context: Optional[JSON] = None,
    ) -> SymbolicState:
        """Perceive from a dual NDS frame (384,256,3) or a single screen (192,256,3).

        If `frame` is the full dual buffer, the adapter slices it and runs discovery.
        If it is already a single screen (192 rows), it is passed directly (legacy/test path).
        """
        ctx = context or {}
        action = ctx.get("last_action")

        if frame is None:
            # No frame: delegate directly so GridPerceiver can handle the first-frame path.
            return self._grid.perceive(frame, memory, context)

        arr = np.asarray(frame)

        # --- slice into top / bottom ---
        if arr.ndim == 3 and arr.shape[0] == 2 * _NDS_H:
            # Full dual buffer (384, 256, 3).
            top_frame = arr[:_NDS_H]
            bot_frame = arr[_NDS_H:]
        elif arr.ndim == 3 and arr.shape[0] == _NDS_H:
            # Caller already sliced — treat as the gameplay frame directly (skip discovery).
            return self._grid.perceive(frame, memory, context)
        else:
            # Unknown shape: pass through and let GridPerceiver deal with it.
            return self._grid.perceive(frame, memory, context)

        # --- update discovery ---
        role = self._discovery.update(top_frame, bot_frame, action)
        self._last_role = role

        gameplay_screen = role.get("gameplay") or self._fallback
        gameplay_frame = top_frame if gameplay_screen == "top" else bot_frame

        # Attach discovery metadata to context so GridPerceiver / callers can log it.
        enriched_ctx = dict(ctx)
        enriched_ctx["screen_role"] = role

        return self._grid.perceive(gameplay_frame, memory, enriched_ctx)

    @property
    def last_role(self) -> dict:
        """Most recently determined role assignment (without advancing state)."""
        return self._last_role

    @property
    def discovery(self) -> ScreenRoleDiscovery:
        """Direct access to the discovery object (for tests / introspection)."""
        return self._discovery
