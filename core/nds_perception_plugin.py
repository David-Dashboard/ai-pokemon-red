"""NDSPerceptionPlugin — PerceptionPlugin extended with `touch` + `touch_target` action tools.

Extends the agnostic PerceptionPlugin with NDS-specific touch input. The base class
handles all button presses and observe() (via the perceiver); this subclass adds:
  - `touch` ToolSpec in tools() (params: x 0-255, y 0-191) — raw stylus tap, fallback.
  - `touch_target` ToolSpec in tools() (params: id) — taps the id-th target detected by the
    last observe() (coarse, no raw coordinates on the wire; the ADR-003 "coordinate leak" fix).
  - Routes both ToolCalls -> the shared _tap() helper -> emulator.touch(x,y) + touch_release()
    after hold_frames ticks.

The emulator must be a DeSmuMEEmulator (or any object with .touch(x,y) and .touch_release()).
The perceiver must be an NDSPerceiver (so touch_targets land in spatial_memory).

Nothing in contracts.py is touched — touch/touch_target are just more tools/intents, identical
in shape to press_button.
"""
from __future__ import annotations

from typing import Optional

from core.contracts import ToolCall, ToolResult, ToolSpec
from core.nds_emulator import _TOUCH_SETTLE   # single definition, shared with touch_drag
from core.perception_plugin import PerceptionPlugin

# NDS bottom-screen coordinate bounds for validation.
_TOUCH_X_MAX = 255
_TOUCH_Y_MAX = 191
# Default stylus hold: comparable to a button press. (_TOUCH_SETTLE lives in core/nds_emulator.py
# so _tap() here and DeSmuMEEmulator.touch_drag() settle identically and can't drift apart.)
_TOUCH_HOLD = 6


class NDSPerceptionPlugin(PerceptionPlugin):
    """PerceptionPlugin + touch actions for NDS worlds.

    The `touch` tool issues a raw stylus tap at (x, y) on the BOTTOM NDS screen.
    The `touch_target` tool resolves a coarse id (from the last observe()'s touch_targets)
    to a tap, avoiding raw coordinates on the wire.
    All button-press tools, wait, and observe come from the base class unchanged.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Cache of the touch_targets from the most recent observe() — the resolution source for
        # touch_target(id). Kept fresh by the MCP driver (world_mcp.World.call), which re-observe()s
        # after EVERY action, so the cache always reflects the frame the brain last saw. (The tap
        # itself advances the frame; safety comes from that post-action re-observe, NOT from a static
        # frame — do not remove the driver's trailing observe().)
        self._last_touch_targets: list = []

    # -- GamePlugin surface (extend, not replace) ----------------------------

    def tools(self, agent_id: str) -> list[ToolSpec]:
        base = super().tools(agent_id)
        touch_spec = ToolSpec(
            name="touch",
            description=(
                "Tap the NDS bottom (touch) screen at pixel coordinates (x, y). "
                "x: 0–255 (left to right), y: 0–191 (top to bottom). "
                "Prefer touch_target(id) when the target is in observe()'s touch_targets; use raw "
                "coords only for targets the detector missed. "
                "Issues a stylus-down at (x, y), holds for a few ticks, then releases."
            ),
            schema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "minimum": 0, "maximum": _TOUCH_X_MAX},
                    "y": {"type": "integer", "minimum": 0, "maximum": _TOUCH_Y_MAX},
                    "hold_frames": {"type": "integer", "minimum": 1, "maximum": 60},
                },
                "required": ["x", "y"],
            },
            cost=1,
            mutating=True,
        )
        touch_target_spec = ToolSpec(
            name="touch_target",
            description=(
                "Tap the id-th detected touch target from observe()'s touch_targets list "
                "(0-based, area-sorted; 0 = largest). Preferred over touch(x,y) — no raw coordinates."
            ),
            schema={
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "minimum": 0},
                    "hold_frames": {"type": "integer", "minimum": 1, "maximum": 60},
                },
                "required": ["id"],
            },
            cost=1,
            mutating=True,
        )
        return [*base, touch_spec, touch_target_spec]

    def handle(self, call: ToolCall) -> ToolResult:
        if call.tool == "touch":
            try:
                return self._do_touch(call)
            except Exception as e:  # defensive: errors are observations, never crashes (base class invariant)
                return self._reject(call, f"touch: internal error: {e}")
        if call.tool == "touch_target":
            try:
                return self._do_touch_target(call)
            except Exception as e:  # defensive: errors are observations, never crashes (base class invariant)
                return self._reject(call, f"touch_target: internal error: {e}")
        return super().handle(call)

    def observe(self, agent_id: str):
        obs = super().observe(agent_id)
        sm = (obs.data or {}).get("spatial_memory") or {}
        self._last_touch_targets = list(sm.get("touch_targets", []))
        return obs

    # -- internals -----------------------------------------------------------

    def _tap(self, x: int, y: int, hold: int) -> None:
        """Issue a stylus-down at (x, y), hold, release, settle. Shared by touch and touch_target
        so the two tools can't drift apart."""
        self.emu.touch(x, y)
        self.emu.tick(max(1, min(hold, 60)))
        self.emu.touch_release()
        self.emu.tick(_TOUCH_SETTLE)

    def _do_touch(self, call: ToolCall) -> ToolResult:
        try:
            x = int(call.args.get("x", 0))
            y = int(call.args.get("y", 0))
            hold = int(call.args.get("hold_frames", _TOUCH_HOLD))
        except (TypeError, ValueError) as e:
            return self._reject(call, f"touch: bad args: {e}")

        if not (0 <= x <= _TOUCH_X_MAX and 0 <= y <= _TOUCH_Y_MAX):
            return self._reject(
                call,
                f"touch: coords ({x},{y}) out of range; x in [0,{_TOUCH_X_MAX}], y in [0,{_TOUCH_Y_MAX}]",
            )

        # Emulator must expose touch() / touch_release() (DeSmuMEEmulator does).
        if not (hasattr(self.emu, "touch") and hasattr(self.emu, "touch_release")):
            return self._reject(call, "touch: emulator does not support touch input")

        self._tap(x, y, hold)

        action = f"touch({x},{y})"
        return self._post_action(call, action=action)

    def _do_touch_target(self, call: ToolCall) -> ToolResult:
        targets = self._last_touch_targets
        if not targets:
            return self._reject(call, "touch_target: no touch targets from the last observe()")

        tid = int(call.args.get("id", -1))
        if not (0 <= tid < len(targets)):
            return self._reject(call, f"touch_target: id {tid} out of range [0,{len(targets) - 1}]")

        # Emulator must expose touch() / touch_release() (DeSmuMEEmulator does).
        if not (hasattr(self.emu, "touch") and hasattr(self.emu, "touch_release")):
            return self._reject(call, "touch_target: emulator does not support touch input")

        t = targets[tid]
        x, y = int(t["cx"]), int(t["cy"])
        hold = int(call.args.get("hold_frames", _TOUCH_HOLD))

        self._tap(x, y, max(1, min(hold, 60)))

        action = f"touch_target({tid})->({x},{y})"
        return self._post_action(call, action=action)
