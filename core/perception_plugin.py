"""PerceptionPlugin — a perception-only GamePlugin for the lean worlds (the constancy infra).

Lifted from games/gauntlet/plugin.py the second time it was needed (Gauntlet + Cave Noire): NO RAM in the
observation (a perceiver is required), no reward tracker, no Gen-1 battle settling. A lightweight fade
watch samples the screen while ticking actions and surfaces ctx["transition"] (+ ctx["frames_advanced"])
to the perceiver — pixels-only, ignored by perceivers that don't read those keys. The agent sees a `SymbolicState` (pixels-derived); RAM, if a `watch` map is supplied, goes ONLY
to oracle.jsonl for offline scoring and NEVER into Observation.data (the no-leak rule, structural). The
emulator is injected, so the class is exercisable with a FakeEmulator and no ROM. The only per-world bits
are flavor text (button descriptions + the render header) — injected, not subclassed.
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

import numpy as np

from core.contracts import Event, Observation, ToolCall, ToolResult, ToolSpec
from core.gb_emulator import BUTTONS, Emulator, PyBoyEmulator
from core.patience import Patience, classify
from core.perception import PerceptMemory, Perceiver

_DEFAULT_BUTTON_DESC = ("Press one Game Boy button (a, b, start, select, up, down, left, right). "
                        "The d-pad moves; A/B act; START advances menus/titles.")
_DEFAULT_SEQUENCE_DESC = ("Press several buttons in order in one call — efficient for walking a few "
                          "steps. Diagonals are two presses (e.g. up then left).")
_DEFAULT_RENDER_HEADER = "Top-down maze exploration. Perception is approximate; a screenshot is attached."

# A map-warp FADE frame is near-uniform (all-dark or all-bright): measured std 0.0 on real Gen-1 fades vs
# > 65 on real gameplay/UI frames (games/pokemon_red/perceiver.detect_mode uses the same 6.0 guard).
_FADE_STD = 6.0
# Sample the screen for a fade every this many ticks during `wait` (a fade holds for many frames, so a
# coarse stride still catches it; sampling is a read-only screen copy, no extra emulator ticks).
_FADE_SAMPLE_TICKS = 4


def _is_fade_frame(frame) -> bool:
    """True if the frame is a near-uniform dark/bright fade frame (pixels only)."""
    if frame is None:
        return False
    g = np.asarray(frame)
    if g.ndim == 3:
        g = g[..., :3].mean(axis=2)
    return float(g.std()) < _FADE_STD


# PATIENCE's control-grounding fallback (a candidate advance button produced no context/text change):
# a pixel-identical frame pair means the button was a true no-op (e.g. Emerald's naming screen: 'a'
# loops silently). Exact equality only — any real redraw (even a blinking cursor) must count as changed,
# so this stays a strict identity check, not a fuzzy diff.
def _is_frame_equal(a, b) -> bool:
    if a is None or b is None:
        return a is b
    a, b = np.asarray(a), np.asarray(b)
    return a.shape == b.shape and bool(np.array_equal(a, b))


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
        patience: Optional[Patience] = None,
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
        # Live fade watch (2026-07-02 review of PR #44): the perceiver's ctx["transition"] fade flag
        # existed but was NEVER wired on the lean path, so warp detection fell back to the best-shift
        # residual — which a cutscene can spike with no real warp. The plugin now samples intermediate
        # frames while it ticks the emulator (after each button press; every ~4 ticks during `wait`) and
        # flags a near-uniform fade frame. Game-agnostic and additive: perceivers that don't read the key
        # (core.grid_perceiver) ignore it.
        self._fade_seen = False
        self._frame_at_obs = self.emu.frame   # for ctx["frames_advanced"] (frozen-frame settle guard)
        self._button_desc = button_desc
        self._sequence_desc = sequence_desc
        self._render_header = render_header
        # PATIENCE (2026-07-02 design): auto-advance a plain gated-static screen (dialog/cutscene/title)
        # for free after an action, so the brain's next observe() never lands mid-textbox. On by default
        # (Patience() with its own budget) — harmless when a world never emits a gated-static context
        # (classify() falls back to "choice"/"free-control" and the loop never fires). Pass patience=None
        # explicitly only if a caller truly wants it off (kept possible for tests/back-compat).
        self.patience = patience if patience is not None else Patience()

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
                remaining = max(1, min(frames, 600))
                while remaining > 0:           # tick in short chunks so the fade watch can sample
                    step = min(_FADE_SAMPLE_TICKS, remaining)
                    self.emu.tick(step)
                    remaining -= step
                    self._sample_fade()
                return self._post_action(call, action=f"wait {frames}")
            return self._reject(call, f"unknown tool: {call.tool}",
                                extra={"available": ["press_button", "press_sequence", "wait"]})
        except Exception as e:  # defensive: never raise across the gateway boundary
            return self._reject(call, f"internal error: {e}")

    def observe(self, agent_id: str) -> Observation:
        self._obs_count += 1
        sym, screen_path = self._perceive_once()

        # PATIENCE: if the frame is gated-static (a plain textbox/cutscene/title waiting for an
        # advance input — never a choice), auto-advance it FOR FREE right here, before returning to the
        # brain, so the caller's next observe() lands on free-control or a real choice. Re-perceives
        # after each press (settle-to-stable IS the re-perceive: the perceiver only reports "gameplay"
        # ready once the screen has actually changed), so a slow-fading textbox is never skipped past.
        advanced = 0
        if classify(sym.context) == "gated-static":
            def _press_and_reperceive(button: str):
                nonlocal sym, screen_path
                prev_context, prev_text = sym.context, sym.screen_text
                try:
                    prev_pixels = self.emu.screen_ndarray()
                except Exception:
                    prev_pixels = None
                self.emu.press(button, hold_frames=8)
                self._sample_fade()
                self._last_action = button   # keep ctx["last_action"] honest for this internal press
                sym, screen_path = self._perceive_once()
                # "changed" needs more than the bare context label: two consecutive dialog LINES both
                # read as context=="dialog", so a no-op button (Emerald's 'a' on the naming screen) would
                # look identical to a working one if we only compared context. screen_text catches real
                # progress through a textbox (Red); a context change alone also counts (dialog ->
                # free-control). Fall back to a raw pixel diff for text-less gated-static screens (a
                # generic world's "static" — a title/naming screen with no decoded text at all): any
                # world can be control-grounded this way, not just ones with a text decoder.
                changed = (sym.context != prev_context) or (sym.screen_text != prev_text)
                if not changed and prev_pixels is not None:
                    try:
                        changed = not _is_frame_equal(prev_pixels, self.emu.screen_ndarray())
                    except Exception:
                        pass
                return sym.context, changed

            _, advanced = self.patience.advance(sym.context, _press_and_reperceive)
            # sym/screen_path were updated in-place by _press_and_reperceive on every press; the
            # returned final_context is the same as sym.context by now (kept for Patience's own API).

        self._log_oracle(screen_path, sym, advanced=advanced)
        data = sym.to_dict()
        data["step"] = self._obs_count
        data["screen_path"] = sym.raw_ref  # alias so an image-capable brain still finds the frame
        data["patience_advances"] = advanced   # PATIENCE traceability: free auto-advances this observe() ate
        return Observation(data=data, text=self._render_symbolic(sym), agent_id=agent_id, t=time.time())

    def _perceive_once(self):
        """Grab the current frame, build the perceiver context, and perceive() once. Shared by observe()
        and the PATIENCE auto-advance loop (which re-perceives after each free button press)."""
        screen_path = os.path.join(self.out_dir, f"frame_{self._obs_count:06d}.png")
        try:
            self.emu.save_screen(screen_path)
        except Exception:
            screen_path = ""
        try:
            pixels = self.emu.screen_ndarray()
        except Exception:
            pixels = None
        # transition: the live fade watch (a near-uniform frame seen while ticking the last action) —
        # positive evidence of a map-warp fade. frames_advanced: emulator frame-counter delta since the
        # last observe; 0 means the screen could not have changed (a frozen frame pair), which gates the
        # perceiver's settle/recovery path. Both are ignored by perceivers that don't read them.
        context = {"frame_path": screen_path, "last_action": self._last_action,
                   "transition": self._fade_seen,
                   "frames_advanced": self.emu.frame - self._frame_at_obs,
                   **self._extra_context}
        self._fade_seen = False                  # consumed — re-arm the watch for the next action
        self._frame_at_obs = self.emu.frame
        self._extra_context = {}   # consumed — clear so it doesn't leak to the next observe()
        sym = self.perceiver.perceive(pixels, self._percept_memory, context)
        return sym, screen_path

    def _log_oracle(self, screen_path: str, sym, advanced: int = 0) -> None:
        """Append a (truth ⟂ perceived) record for SCORING ONLY — never an agent input. The watched RAM
        (if any) is the truth; the perceiver's verdict goes under `perceived`. RAM never enters obs."""
        rec = {"step": self._obs_count, "t": time.time(), "frame": self.emu.frame,
               "screen_path": screen_path, "patience_advances": advanced}
        if self._watch:
            try:
                rec["watch"] = {nm: int(self.emu.read(ad)) for nm, ad in self._watch.items()}
            except Exception:
                pass
        la = sym.last_action or {}
        rec["perceived"] = {"outcome": la.get("outcome"), "action": la.get("action"),
                            "diff": la.get("diff"), "pose": (sym.pose or {}).get("value"),
                            "context": sym.context, "confidence": sym.confidence,
                            "ego_motion": (sym.spatial_memory or {}).get("ego_motion"),
                            "screen_text": sym.screen_text}
        try:
            with open(self._oracle_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except OSError:
            pass

    # Contexts that mean "free movement" across the two perceiver vocabularies in use: pokemon_red's
    # own perceiver emits "overworld"; the shared GridPerceiver (cave_noire, gauntlet, NDS) emits
    # "gameplay" for the exact same situation. Treating only "overworld" as free-movement made every
    # GridPerceiver-based world (including NDS) permanently render the degenerate branch below — the
    # spatial view (pose/walls/frontiers/entities/touch_targets) never surfaced, and gameplay itself got
    # mislabeled "NOT free movement". Everything else (static/menu/unknown/dialog/battle_text/...) is
    # correctly non-free-movement and unaffected by this change.
    _FREE_MOVEMENT_CONTEXTS = ("overworld", "gameplay")

    def _render_symbolic(self, sym) -> str:
        """Turn the SymbolicState into a navigation-useful prompt. Game-agnostic (reads only seam fields)."""
        pose = sym.pose or {}
        sm = sym.spatial_memory or {}
        la = sym.last_action or {}
        lines = [self._render_header]

        # Non-free-movement: the exploration render (pose/cells/frontiers) is degenerate/stale during a
        # dialog and previously confused the brain into thinking perception had frozen. Lead with the
        # decoded text instead and skip the spatial lines. touch_targets and the last-move outcome are
        # still surfaced here (unaffected by pose staleness) — a brain often needs to tap through exactly
        # these screens (title/menus) and was otherwise flying blind.
        if sym.context not in self._FREE_MOVEMENT_CONTEXTS:
            if sym.screen_text:
                lines.append(f"On-screen text (you are in a {sym.context}, NOT free movement): "
                             f"\"{sym.screen_text}\"")
                if sym.context in ("dialog", "battle_text"):
                    lines.append("Press A (or B) to advance the text.")
                elif sym.context == "menu":
                    lines.append("This is a menu choice to read and decide, not a place to walk.")
            else:
                lines.append(f"You are in a {sym.context}, NOT free movement.")
            action, outcome = la.get("action"), la.get("outcome")
            if action and outcome == "blocked":
                lines.append(f"Last move '{action}' -> BLOCKED: you did NOT move.")
            elif action and outcome == "moved":
                lines.append(f"Last move '{action}' -> moved.")
            touch_targets = sm.get("touch_targets") or []
            if touch_targets:
                tgts = ", ".join(
                    f"{i}:({t['cx']},{t['cy']})" for i, t in enumerate(touch_targets[:12])
                )
                lines.append(f"Touch targets detected (id:(cx,cy), area-sorted): {tgts}. "
                             f"Use touch_target(id) to tap one.")
            return "\n".join(lines)

        if pose.get("lost"):
            # A perceiver may flag pose as LOST after an unattributed scene change (a cutscene, a warp it
            # couldn't pin to a commanded step) instead of guessing — game-agnostic: only ever set by a
            # perceiver that tracks pose_confidence; absent otherwise, so other worlds are unaffected.
            lines.append("Position lost: the last screen change couldn't be explained by your move. "
                         "The map below is not yet trustworthy; keep moving one step at a time to "
                         "re-establish where you are.")
            return "\n".join(lines)
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
        if sym.screen_text:  # rare in overworld, but harmless to surface if present
            lines.append(f"On-screen text: \"{sym.screen_text}\"")
        touch_targets = sm.get("touch_targets") or []
        if touch_targets:
            tgts = ", ".join(
                f"{i}:({t['cx']},{t['cy']})" for i, t in enumerate(touch_targets[:12])
            )
            lines.append(f"Touch targets detected (id:(cx,cy), area-sorted): {tgts}. "
                         f"Use touch_target(id) to tap one.")
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
            self._sample_fade()   # a door-walk fade shows right after the press's hold+settle ticks
        return self._post_action(call, action="+".join(str(b) for b in buttons))

    def _sample_fade(self) -> None:
        """Peek at the current screen (read-only, no ticks) and latch whether a fade frame was seen.
        The latch holds until the next observe() consumes it into ctx["transition"]."""
        if self._fade_seen:
            return
        try:
            self._fade_seen = _is_fade_frame(self.emu.screen_ndarray())
        except Exception:
            pass

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
