"""PokemonRedPlugin — the Pokémon Red world, as a GamePlugin.

Contract posture (see CONTRACT.md):
  * GamePlugin ONLY. No reset/step/terminal/snapshot — an open-world RPG has
    no clean terminal, so it is classed with the real desktop, not with the
    Replayable sims (chess, ecology).
  * Time regime = real-world: Event.t / Observation.t are unix epoch seconds
    (invariant 6).
  * Errors are observations: a bad button or unknown tool comes back as an
    ok=False ToolResult carrying the legal options, never an exception
    (invariant 2).
  * JSON wire only: the screen is written to disk and its *path* travels in
    Observation.data; pixels never cross the boundary (invariant 3).

The emulator is dependency-injected, so the whole class is exercisable with a
FakeEmulator and no ROM.
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

from core.contracts import Event, Observation, ToolCall, ToolResult, ToolSpec
from core.perception import PerceptMemory, Perceiver, SymbolicState

from .emulator import BUTTONS, Emulator, PyBoyEmulator
from .memory_map import read_state
from .reward import RewardTracker


class PokemonRedPlugin:
    """One live Pokémon Red session driven through button-press tool calls."""

    def __init__(
        self,
        rom_path: Optional[str] = None,
        emulator: Optional[Emulator] = None,
        out_dir: str = "runs/pokemon_red",
        headless: bool = True,
        init_state: Optional[str] = None,
        perceiver: Optional[Perceiver] = None,
    ) -> None:
        if emulator is None:
            if rom_path is None:
                raise ValueError("provide either rom_path or an emulator instance")
            emulator = PyBoyEmulator(rom_path, headless=headless)
        self.emu = emulator
        # Boot straight into real gameplay by loading a save state made past the
        # intro/name-entry (which a button-mashing brain can't reliably clear).
        if init_state is not None:
            self.emu.load_state(init_state)
        self.out_dir = out_dir
        os.makedirs(self.out_dir, exist_ok=True)

        self._events: list[Event] = []
        self._reward = RewardTracker()
        self._reward.reset_baseline(read_state(self.emu.read))
        self._obs_count = 0

        # Iteration 02: optional pixel-perception path. When set, Observation.data is a
        # SymbolicState (pixels-derived) and RAM is written to a separate oracle log for
        # SCORING ONLY — it never enters the agent's input. Default (None) = legacy RAM obs.
        self.perceiver = perceiver
        self._percept_memory = PerceptMemory() if perceiver is not None else None
        self._oracle_path = os.path.join(self.out_dir, "oracle.jsonl")
        self._last_action: Optional[str] = None  # fed to the perceiver for odometry

    # -- GamePlugin surface --------------------------------------------------

    def tools(self, agent_id: str) -> list[ToolSpec]:
        button_enum = {"type": "string", "enum": list(BUTTONS)}
        return [
            ToolSpec(
                name="press_button",
                description=(
                    "Press one Game Boy button (a, b, start, select, up, down, "
                    "left, right). Use A to confirm/interact, B to cancel, the "
                    "d-pad to walk. The press is held briefly then released."
                ),
                schema={
                    "type": "object",
                    "properties": {
                        "button": button_enum,
                        "hold_frames": {"type": "integer", "minimum": 1, "maximum": 120},
                    },
                    "required": ["button"],
                },
                cost=1,
                mutating=True,
            ),
            ToolSpec(
                name="press_sequence",
                description=(
                    "Press several buttons in order in one call — efficient for "
                    "walking a few tiles or stepping through a menu."
                ),
                schema={
                    "type": "object",
                    "properties": {
                        "buttons": {"type": "array", "items": button_enum, "maxItems": 16},
                    },
                    "required": ["buttons"],
                },
                cost=1,
                mutating=True,
            ),
            ToolSpec(
                name="wait",
                description=(
                    "Advance the game without input — let text scroll, an "
                    "animation finish, or an NPC move."
                ),
                schema={
                    "type": "object",
                    "properties": {
                        "frames": {"type": "integer", "minimum": 1, "maximum": 600},
                    },
                    "required": [],
                },
                cost=1,
                mutating=True,
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
        state = read_state(self.emu.read)
        self._obs_count += 1
        screen_path = os.path.join(self.out_dir, f"frame_{self._obs_count:06d}.png")
        try:
            self.emu.save_screen(screen_path)
        except Exception:
            screen_path = ""

        if self.perceiver is not None:
            # Pixel-perception path: the agent sees a SymbolicState; RAM goes to the oracle
            # log (scoring only) and NEVER enters Observation.data. (no-leak, structural)
            try:
                pixels = self.emu.screen_ndarray()
            except Exception:
                pixels = None
            context = {"frame_path": screen_path, "last_action": self._last_action}
            sym = self.perceiver.perceive(pixels, self._percept_memory, context)
            self._log_oracle(state, screen_path, sym)
            data = sym.to_dict()
            data["step"] = self._obs_count
            data["screen_path"] = sym.raw_ref  # alias so an image-capable brain still finds the frame
            return Observation(data=data, text=self._render_symbolic(sym),
                               agent_id=agent_id, t=time.time())

        # Legacy RAM-based observation (unchanged when no perceiver is injected).
        data = dict(state)
        data["screen_path"] = screen_path
        data["frame"] = self.emu.frame
        data["step"] = self._obs_count
        data["maps_seen"] = self._reward.maps_seen
        return Observation(
            data=data,
            text=self._render(state, screen_path),
            agent_id=agent_id,
            t=time.time(),
        )

    def _log_oracle(self, state: dict, screen_path: str,
                    sym: Optional[SymbolicState] = None) -> None:
        """Append a paired (truth ⟂ perceived) record for SCORING ONLY — never an agent input.
        RAM truth stays top-level; the perceiver's verdict goes under `perceived`. The scorer
        (eval/score_perception.py) compares the two to grade perception without leaking RAM."""
        rec = {
            "step": self._obs_count, "t": time.time(), "frame": self.emu.frame,
            "screen_path": screen_path,
            "map_id": state["map_id"], "x": state["x"], "y": state["y"],
            "in_battle": state["in_battle"], "badges": state["badges"],
            "maps_seen": self._reward.maps_seen,
        }
        if sym is not None:
            la = sym.last_action or {}
            rec["perceived"] = {
                "outcome": la.get("outcome"),          # moved | blocked | unknown
                "action": la.get("action"),
                "diff": la.get("diff"),                # frame-diff value (for threshold tuning)
                "pose": (sym.pose or {}).get("value"),
                "area": (sym.pose or {}).get("area"),
                "context": sym.context,
                "confidence": sym.confidence,
                "walls_here": (sym.spatial_memory or {}).get("walls_here"),
            }
        try:
            with open(self._oracle_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except OSError:
            pass

    def _render_symbolic(self, sym: SymbolicState) -> str:
        """Turn the SymbolicState into a navigation-useful prompt for the planner. The spatial
        memory (where I've been, what's a wall, where's unexplored) is what breaks the loop."""
        pose = sym.pose or {}
        sm = sym.spatial_memory or {}
        la = sym.last_action or {}
        lines = ["Overworld exploration. Perception is approximate; a screenshot is attached."]
        if pose.get("value") is not None:
            lines.append(f"Your position (dead-reckoned, approximate): {tuple(pose['value'])}.")
        action, outcome = la.get("action"), la.get("outcome")
        if action and outcome == "blocked":
            lines.append(f"Last move '{action}' -> BLOCKED: you did NOT move; that direction is a "
                         f"wall. Choose a DIFFERENT direction.")
        elif action and outcome == "moved":
            lines.append(f"Last move '{action}' -> moved.")
        if sm.get("walls_here"):
            lines.append(f"Known walls at this spot: {', '.join(sm['walls_here'])}.")
        if sym.affordances:
            lines.append(f"Unexplored/open directions from here (head toward these to make "
                         f"progress): {', '.join(sym.affordances)}.")
        lines.append(f"Tiles explored in this area so far: {sm.get('visited', 0)}.")
        return "\n".join(lines)

    def drain_events(self) -> list[Event]:
        out, self._events = self._events, []
        return out

    # -- internals -----------------------------------------------------------

    def _do_buttons(self, call: ToolCall, buttons: list, hold: int) -> ToolResult:
        for b in buttons:
            if not isinstance(b, str) or b.lower() not in BUTTONS:
                return self._reject(call, f"invalid button: {b!r}",
                                    extra={"valid_buttons": list(BUTTONS)})
        for b in buttons:
            self.emu.press(b.lower(), hold_frames=max(1, min(int(hold), 120)))
        return self._post_action(call, action="+".join(str(b) for b in buttons))

    def _post_action(self, call: ToolCall, action: str) -> ToolResult:
        self._last_action = action  # remembered so the next observe() can do odometry
        state = read_state(self.emu.read)
        reward, breakdown = self._reward.update(state)
        now = time.time()
        self._events.append(Event(type="tool_called", t=now, agent_id=call.agent_id,
                                  data={"action": action, "frame": self.emu.frame}))
        if reward != 0.0:
            self._events.append(Event(type="reward", t=now, agent_id=call.agent_id,
                                      data=breakdown, reward=reward))
        if "badges" in breakdown:
            self._events.append(Event(type="badge_earned", t=now, agent_id=call.agent_id,
                                      data={"badges": state["badges"]}))
        return ToolResult(
            call_id=call.call_id, ok=True,
            data={"action": action, "frame": self.emu.frame,
                  "in_battle": state["in_battle"], "reward": reward},
            cost_charged=1,
        )

    def _reject(self, call: ToolCall, reason: str, extra: Optional[dict] = None) -> ToolResult:
        data = {"valid_buttons": list(BUTTONS)}
        if extra:
            data.update(extra)
        return ToolResult(call_id=call.call_id, ok=False, data=data, error=reason, cost_charged=1)

    def _render(self, state: dict, screen_path: str) -> str:
        battle = {0: "no", 1: "wild battle", 2: "trainer battle"}.get(state["in_battle"], "?")
        lines = [
            f"Pokémon Red — step {self._obs_count} (frame {self.emu.frame})",
            f"Location: map {state['map_id']} at (x={state['x']}, y={state['y']})   In battle: {battle}",
            f"Badges: {state['badges']}   Money: ¥{state['money']}   Maps seen: {self._reward.maps_seen}",
            f"Party ({state['party_count']}):",
        ]
        for i, p in enumerate(state["party"], 1):
            lines.append(f"  {i}. species#{p['species_id']} Lv{p['level']}  HP {p['hp']}/{p['max_hp']}")
        if screen_path:
            lines.append(f"Screen image: {screen_path}")
        return "\n".join(lines)

    def save_state(self, path: str) -> None:
        """Write the live emulator state to disk (for resuming or seeding runs)."""
        self.emu.save_state(path)

    def close(self) -> None:
        self.emu.close()
