"""PerceptionPlugin — a perception-only GamePlugin for the lean worlds (the constancy infra).

Lifted from games/gauntlet/plugin.py the second time it was needed (Gauntlet + Cave Noire): NO RAM in the
observation (a perceiver is required), no reward tracker, no map-warp/fade handling, no Gen-1 battle
settling. The agent sees a `SymbolicState` (pixels-derived); RAM, if a `watch` map is supplied, goes ONLY
to oracle.jsonl for offline scoring and NEVER into Observation.data (the no-leak rule, structural). The
emulator is injected, so the class is exercisable with a FakeEmulator and no ROM. The only per-world bits
are flavor text (button descriptions + the render header) — injected, not subclassed.
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

from core.contracts import Event, Observation, ToolCall, ToolResult, ToolSpec
from core.gb_emulator import BUTTONS, Emulator, PyBoyEmulator
from core.perception import PerceptMemory, Perceiver

_DEFAULT_BUTTON_DESC = ("Press one Game Boy button (a, b, start, select, up, down, left, right). "
                        "The d-pad moves; A/B act; START advances menus/titles.")
_DEFAULT_SEQUENCE_DESC = ("Press several buttons in order in one call — efficient for walking a few "
                          "steps. Diagonals are two presses (e.g. up then left).")
_DEFAULT_RENDER_HEADER = "Top-down maze exploration. Perception is approximate; a screenshot is attached."


class PerceptionPlugin:
    """One live perception-only Game Boy session driven through button-press tool calls."""

    def __init__(
        self,
        rom_path: Optional[str] = None,
        emulator: Optional[Emulator] = None,
        out_dir: str = "runs/perception",
        headless: bool = True,
        init_state: Optional[str] = None,
        perceiver: Optional[Perceiver] = None,
        watch: Optional[dict] = None,
        sound: bool = False,
        record_path: Optional[str] = None,
        record_fps: int = 30,
        record_scale: int = 3,
        button_desc: str = _DEFAULT_BUTTON_DESC,
        sequence_desc: str = _DEFAULT_SEQUENCE_DESC,
        render_header: str = _DEFAULT_RENDER_HEADER,
    ) -> None:
        if perceiver is None:
            raise ValueError("PerceptionPlugin is perception-only — pass a perceiver")
        if emulator is None:
            if rom_path is None:
                raise ValueError("provide either rom_path or an emulator instance")
            emulator = PyBoyEmulator(rom_path, headless=headless, sound=sound,
                                     record_path=record_path, record_fps=record_fps,
                                     record_scale=record_scale)
        self.emu = emulator
        if init_state is not None:
            self.emu.load_state(init_state)
        self.out_dir = out_dir
        os.makedirs(self.out_dir, exist_ok=True)

        self._events: list[Event] = []
        self._obs_count = 0
        self.perceiver = perceiver
        self._percept_memory = PerceptMemory()
        self._oracle_path = os.path.join(self.out_dir, "oracle.jsonl")
        self._watch = dict(watch or {})        # name -> WRAM addr; RAM goes to the oracle log ONLY
        self._last_action: Optional[str] = None  # fed to the perceiver for odometry
        self._extra_context: dict = {}           # transient caller-injected context (e.g. goto_fails)
        self._button_desc = button_desc
        self._sequence_desc = sequence_desc
        self._render_header = render_header

    # -- GamePlugin surface --------------------------------------------------

    def _buttons(self) -> tuple:
        """Button set for this emulator — sourced from the injected emulator if it exposes BUTTONS,
        otherwise falls back to the GB 8-button set. This lets NDS emulators advertise x/y/l/r."""
        return getattr(type(self.emu), "BUTTONS", None) or getattr(self.emu, "BUTTONS", None) or BUTTONS

    def tools(self, agent_id: str) -> list[ToolSpec]:
        button_enum = {"type": "string", "enum": list(self._buttons())}
        return [
            ToolSpec(
                name="press_button",
                description=self._button_desc,
                schema={"type": "object",
                        "properties": {"button": button_enum,
                                       "hold_frames": {"type": "integer", "minimum": 1, "maximum": 120}},
                        "required": ["button"]},
                cost=1, mutating=True,
            ),
            ToolSpec(
                name="press_sequence",
                description=self._sequence_desc,
                schema={"type": "object",
                        "properties": {"buttons": {"type": "array", "items": button_enum, "maxItems": 16}},
                        "required": ["buttons"]},
                cost=1, mutating=True,
            ),
            ToolSpec(
                name="wait",
                description="Advance the game without input — let an animation finish or an enemy move.",
                schema={"type": "object",
                        "properties": {"frames": {"type": "integer", "minimum": 1, "maximum": 600}},
                        "required": []},
                cost=1, mutating=True,
            ),
        ]

    def handle(self, call: ToolCall) -> ToolResult:
        try:
            if call.tool == "press_button":
                return self._do_buttons(call, [call.args.get("button")],
                                        hold=call.args.get("hold_frames", 8))
            if call.tool == "press_sequence":
                buttons = call.args.get("buttons")
                if not isinstance(buttons, list) or not buttons:
                    return self._reject(call, "buttons must be a non-empty list")
                return self._do_buttons(call, buttons, hold=8)
            if call.tool == "wait":
                frames = int(call.args.get("frames", 24))
                self.emu.tick(max(1, min(frames, 600)))
                return self._post_action(call, action=f"wait {frames}")
            return self._reject(call, f"unknown tool: {call.tool}",
                                extra={"available": ["press_button", "press_sequence", "wait"]})
        except Exception as e:  # defensive: never raise across the gateway boundary
            return self._reject(call, f"internal error: {e}")

    def observe(self, agent_id: str) -> Observation:
        self._obs_count += 1
        screen_path = os.path.join(self.out_dir, f"frame_{self._obs_count:06d}.png")
        try:
            self.emu.save_screen(screen_path)
        except Exception:
            screen_path = ""
        try:
            pixels = self.emu.screen_ndarray()
        except Exception:
            pixels = None
        context = {"frame_path": screen_path, "last_action": self._last_action, **self._extra_context}
        self._extra_context = {}   # consumed — clear so it doesn't leak to the next observe()
        sym = self.perceiver.perceive(pixels, self._percept_memory, context)
        self._log_oracle(screen_path, sym)
        data = sym.to_dict()
        data["step"] = self._obs_count
        data["screen_path"] = sym.raw_ref  # alias so an image-capable brain still finds the frame
        return Observation(data=data, text=self._render_symbolic(sym), agent_id=agent_id, t=time.time())

    def _log_oracle(self, screen_path: str, sym) -> None:
        """Append a (truth ⟂ perceived) record for SCORING ONLY — never an agent input. The watched RAM
        (if any) is the truth; the perceiver's verdict goes under `perceived`. RAM never enters obs."""
        rec = {"step": self._obs_count, "t": time.time(), "frame": self.emu.frame,
               "screen_path": screen_path}
        if self._watch:
            try:
                rec["watch"] = {nm: int(self.emu.read(ad)) for nm, ad in self._watch.items()}
            except Exception:
                pass
        la = sym.last_action or {}
        rec["perceived"] = {"outcome": la.get("outcome"), "action": la.get("action"),
                            "diff": la.get("diff"), "pose": (sym.pose or {}).get("value"),
                            "context": sym.context, "confidence": sym.confidence,
                            "ego_motion": (sym.spatial_memory or {}).get("ego_motion")}
        try:
            with open(self._oracle_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except OSError:
            pass

    def _render_symbolic(self, sym) -> str:
        """Turn the SymbolicState into a navigation-useful prompt. Game-agnostic (reads only seam fields)."""
        pose = sym.pose or {}
        sm = sym.spatial_memory or {}
        la = sym.last_action or {}
        lines = [self._render_header]
        if pose.get("value") is not None:
            lines.append(f"Your position (dead-reckoned, approximate): {tuple(pose['value'])}.")
        action, outcome = la.get("action"), la.get("outcome")
        if action and outcome == "blocked":
            lines.append(f"Last move '{action}' -> BLOCKED: you did NOT move; that direction is a wall. "
                         f"Choose a DIFFERENT direction.")
        elif action and outcome == "moved":
            lines.append(f"Last move '{action}' -> moved.")
        if sm.get("walls_here"):
            lines.append(f"Known walls at this spot: {', '.join(sm['walls_here'])}.")
        if sym.affordances:
            lines.append(f"Unexplored/open directions from here (head toward these to make progress): "
                         f"{', '.join(sym.affordances)}.")
        lines.append(f"Cells explored in this area so far: {sm.get('visited', 0)}.")
        entities = sm.get("entities") or []
        if entities:
            ctrs = ", ".join(f"({e['centroid'][0]:.0f},{e['centroid'][1]:.0f})" for e in entities[:8])
            lines.append(f"Entities on screen (sprites/enemies/items): {len(entities)} at {ctrs}.")
        frontiers = sm.get("frontiers") or []
        if pose.get("value") is not None and frontiers:
            sample = ", ".join(f"{f[0]} {f[1]}" for f in frontiers[:6])
            lines.append(f"Unexplored frontier cells you can target (x y): {sample}. "
                         f"Add 'GOTO: x y' to have a free pathfinder walk you to one.")
        return "\n".join(lines)

    def drain_events(self) -> list[Event]:
        out, self._events = self._events, []
        return out

    # -- internals -----------------------------------------------------------

    def _do_buttons(self, call: ToolCall, buttons: list, hold: int) -> ToolResult:
        valid = self._buttons()
        for b in buttons:
            if not isinstance(b, str) or b.lower() not in valid:
                return self._reject(call, f"invalid button: {b!r}", extra={"valid_buttons": list(valid)})
        for b in buttons:
            self.emu.press(b.lower(), hold_frames=max(1, min(int(hold), 120)))
        return self._post_action(call, action="+".join(str(b) for b in buttons))

    def _post_action(self, call: ToolCall, action: str) -> ToolResult:
        self._last_action = action  # remembered so the next observe() can do odometry
        self._events.append(Event(type="tool_called", t=time.time(), agent_id=call.agent_id,
                                  data={"action": action, "frame": self.emu.frame}))
        return ToolResult(call_id=call.call_id, ok=True,
                          data={"action": action, "frame": self.emu.frame}, cost_charged=1)

    def _reject(self, call: ToolCall, reason: str, extra: Optional[dict] = None) -> ToolResult:
        data = {"valid_buttons": list(self._buttons())}
        if extra:
            data.update(extra)
        return ToolResult(call_id=call.call_id, ok=False, data=data, error=reason, cost_charged=1)

    def save_state(self, path: str) -> None:
        self.emu.save_state(path)

    def close(self) -> None:
        self.emu.close()
