"""NDSPerceptionPlugin — PerceptionPlugin extended with a `touch` action tool.

Extends the agnostic PerceptionPlugin with NDS-specific touch input. The base class
handles all button presses and observe() (via the perceiver); this subclass adds:
  - `touch` ToolSpec in tools() (params: x 0-255, y 0-191)
  - Routes `touch` ToolCall -> emulator.touch(x,y) + touch_release() after hold_frames ticks

The emulator must be a DeSmuMEEmulator (or any object with .touch(x,y) and .touch_release()).
The perceiver must be an NDSPerceiver (so touch_targets land in spatial_memory).

Nothing in contracts.py is touched — touch is just another tool/intent, identical in shape
to press_button.
"""
from __future__ import annotations

from typing import Optional

from core.contracts import ToolCall, ToolResult, ToolSpec
from core.perception_plugin import PerceptionPlugin

# NDS bottom-screen coordinate bounds for validation.
_TOUCH_X_MAX = 255
_TOUCH_Y_MAX = 191
# Default stylus hold and settle: comparable to a button press.
_TOUCH_HOLD = 6
_TOUCH_SETTLE = 4


class NDSPerceptionPlugin(PerceptionPlugin):
    """PerceptionPlugin + touch action for NDS worlds.

    The `touch` tool issues a stylus tap at (x, y) on the BOTTOM NDS screen.
    All button-press tools, wait, and observe come from the base class unchanged.
    """

    # -- GamePlugin surface (extend, not replace) ----------------------------

    def tools(self, agent_id: str) -> list[ToolSpec]:
        base = super().tools(agent_id)
        touch_spec = ToolSpec(
            name="touch",
            description=(
                "Tap the NDS bottom (touch) screen at pixel coordinates (x, y). "
                "x: 0–255 (left to right), y: 0–191 (top to bottom). "
                "Use coordinates from observe()'s touch_targets list. "
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
        return [*base, touch_spec]

    def handle(self, call: ToolCall) -> ToolResult:
        if call.tool == "touch":
            return self._do_touch(call)
        return super().handle(call)

    # -- internals -----------------------------------------------------------

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

        self.emu.touch(x, y)
        self.emu.tick(max(1, min(hold, 60)))
        self.emu.touch_release()
        self.emu.tick(_TOUCH_SETTLE)

        action = f"touch({x},{y})"
        return self._post_action(call, action=action)
