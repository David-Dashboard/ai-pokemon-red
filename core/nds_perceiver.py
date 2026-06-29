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

Touch-target detection
----------------------
When a full dual-frame is processed, the SYMBOLIC (non-gameplay) screen — typically the touch
surface — is analysed for candidate tap points. Distinct blob-like regions (detected via a simple
foreground-mask + connected-components pass, numpy-only) are returned as a list of dicts:

    [{"cx": int, "cy": int, "bbox": [x0, y0, x1, y1], "area": int}, ...]

These are stored in `SymbolicState.spatial_memory["touch_targets"]` so a brain can pick one and
call the `touch` tool with its (cx, cy). No OCR — purely structural blob detection.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Optional

import numpy as np

from core.blob import connected_components  # 4-connected CC on a set of (x,y) coords
from core.grid_perceiver import CameraScrollSignal, GridPerceiver, MoveSignal
from core.perception import JSON, PerceptMemory, SymbolicState
from core.screen_role import ScreenRoleDiscovery

# ---------------------------------------------------------------------------
# Blob segmentor — reuses _clusters from saliency.py (no third CC implementation).
# ---------------------------------------------------------------------------

# Ignore blobs smaller than this (noise, single pixels, compression artefacts).
_MIN_BLOB_AREA = 64
# Cap the number of targets returned (a menu rarely has >20 distinct elements).
_MAX_TARGETS = 24


def _detect_touch_targets(frame: np.ndarray) -> list[dict]:
    """Return candidate touch targets from a (H, W, 3) uint8 screen frame.

    Strategy: convert to greyscale, compute edge magnitude (simple Sobel-style via
    numpy diff), threshold → foreground mask, convert foreground pixels to a set of
    (x, y) coords, then delegate to _clusters() for 4-connected components.
    Returns each blob as {cx, cy, bbox:[x0,y0,x1,y1], area}.

    Reuses core.blob.connected_components to avoid a third CC implementation.
    """
    if frame is None or frame.size == 0:
        return []

    arr = np.asarray(frame, dtype=np.float32)
    if arr.ndim != 3 or arr.shape[2] < 3:
        return []

    # Greyscale (luminance weights).
    gray = arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114

    # Sobel-like gradient magnitude (3×3 approximation via numpy slicing).
    gx = np.abs(gray[1:-1, 2:] - gray[1:-1, :-2])
    gy = np.abs(gray[2:, 1:-1] - gray[:-2, 1:-1])
    mag = gx + gy                           # (H-2, W-2)

    # Threshold at half the median of non-zero gradient values.
    nz = mag[mag > 0]
    if nz.size == 0:
        return []
    thresh = float(np.median(nz)) * 0.5
    # +1 offset: mag is (H-2, W-2), so pixel coords in the original frame are +1.
    ys, xs = np.where(mag > thresh)
    if ys.size == 0:
        return []
    # Build a set of (x, y) tuples for _clusters — note: _clusters uses (x, y) = (col, row).
    pixel_set = {(int(xs[i]) + 1, int(ys[i]) + 1) for i in range(len(ys))}

    blobs: list[dict] = []
    for comp in connected_components(pixel_set):
        area = len(comp)
        if area < _MIN_BLOB_AREA:
            continue
        cxs = [p[0] for p in comp]
        cys = [p[1] for p in comp]
        x0, x1 = int(min(cxs)), int(max(cxs))
        y0, y1 = int(min(cys)), int(max(cys))
        blobs.append({
            "cx": x0 + (x1 - x0) // 2,
            "cy": y0 + (y1 - y0) // 2,
            "bbox": [x0, y0, x1, y1],
            "area": area,
        })

    blobs.sort(key=lambda b: b["area"], reverse=True)
    return blobs[:_MAX_TARGETS]

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
        symbolic_screen = "bottom" if gameplay_screen == "top" else "top"
        gameplay_frame = top_frame if gameplay_screen == "top" else bot_frame
        symbolic_frame = bot_frame if symbolic_screen == "bottom" else top_frame

        # Attach discovery metadata to context so GridPerceiver / callers can log it.
        enriched_ctx = dict(ctx)
        enriched_ctx["screen_role"] = role

        sym = self._grid.perceive(gameplay_frame, memory, enriched_ctx)

        # --- touch-target detection always on the BOTTOM physical screen ---
        # Touch coordinates are physical bottom-screen coordinates (the hardware stylus maps to
        # the bottom screen unconditionally). Detecting on the "symbolic" screen would produce wrong
        # coordinates whenever gameplay=bottom (the role-flip case). Always use bot_frame here.
        targets = _detect_touch_targets(bot_frame)
        if targets:
            # SymbolicState is frozen; use dataclasses.replace to clone with augmented spatial_memory.
            sm = dict(sym.spatial_memory) if sym.spatial_memory else {}
            sm["touch_targets"] = targets
            sym = dataclasses.replace(sym, spatial_memory=sm)

        return sym

    @property
    def last_role(self) -> dict:
        """Most recently determined role assignment (without advancing state)."""
        return self._last_role

    @property
    def discovery(self) -> ScreenRoleDiscovery:
        """Direct access to the discovery object (for tests / introspection)."""
        return self._discovery
