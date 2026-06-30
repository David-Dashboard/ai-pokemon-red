"""Menu-navigation navigators for the boot-to-gameplay bake-off (System-1 escalation).

Two ways to get through a menu the blind escape-ladder can't (naming grids, file/character select):
  - VLMNavigator         : send the screen pixels to a small local VLM, get a button back.
  - MenuPerceiverNavigator: turn the menu into TEXT with our perception primitives (RapidOCR + a
                            contrast-based cursor cue), send that text to a small local LLM.

Both call a local llama.cpp `llama-server` (OpenAI-compatible) THROUGH LiteLLM — no provider SDKs, no
cloud, free. Output is forced to a valid button: parse first, and (optional) GBNF grammar on the server
guarantees it. The point is a head-to-head: does reading pixels (VLM) or reading our symbols (LLM) get
more games into real gameplay?
"""
from __future__ import annotations

import base64
import io
import random
import re
from typing import Optional, Sequence

import numpy as np
from PIL import Image

import litellm

litellm.suppress_debug_info = True

# GB/GBA share these; NDS adds x/y (+touch, handled elsewhere).
BUTTONS = ("a", "b", "start", "select", "up", "down", "left", "right")

# NDS 12-button set (import-safe: py-desmume is guarded inside DeSmuMEEmulator.__init__).
from core.nds_emulator import BUTTONS as NDS_BUTTONS  # noqa: E402
# Touch-target detector for NDS bottom screen (numpy-only, no heavy deps).
from core.nds_perceiver import _detect_touch_targets  # noqa: E402

# Stylus hold and settle frame counts (mirrors NDSPerceptionPlugin._do_touch).
_TOUCH_HOLD = 6
_TOUCH_SETTLE = 4

_PROMPT = (
    "You are playing a video game and the screen is currently a TITLE SCREEN, MENU, or other non-gameplay "
    "UI. Your goal is to reach actual GAMEPLAY (a controllable character/scene). Pick the SINGLE best button "
    "to press next to advance toward gameplay: confirm/advance with 'a' or 'start', move a cursor with "
    "up/down/left/right, cancel with 'b'. Reply with ONLY the button word, nothing else.\n"
    "Valid buttons: a, b, start, select, up, down, left, right."
)

_PROMPT_PRIMED = (
    _PROMPT
    + " (1) On a name-entry letter grid, 'a' only ADDS a letter — to finish, press 'start' or move to an "
    "'End'/'OK' tile. (2) Moving the cursor is NOT progress; press 'a' to SELECT a highlighted option, or "
    "'start' to confirm/skip. On a title screen, prefer 'start'."
)

# Rotation order for primed-navigator fallback when the model returns nothing parseable.
_FALLBACK_CYCLE = ("a", "start", "right", "b", "down", "up", "left", "select")


def apply_action(emu, action, *, hold: int = _TOUCH_HOLD, settle: int = _TOUCH_SETTLE) -> None:
    """Dispatch one action to the emulator.

    touch tuple ("touch", x, y) → stylus tap with hold+settle ticks (safe fallback to "a" if
    coords are out of range or the emulator does not support touch). Any other value → emu.press().
    Never raises.
    """
    if isinstance(action, tuple) and len(action) == 3 and action[0] == "touch":
        try:
            x, y = int(action[1]), int(action[2])
        except (TypeError, ValueError):
            emu.press("a")
            return
        if (0 <= x <= 255 and 0 <= y <= 191
                and hasattr(emu, "touch") and hasattr(emu, "touch_release")):
            emu.touch(x, y)
            emu.tick(hold)
            emu.touch_release()
            emu.tick(settle)
        else:
            emu.press("a")
    else:
        emu.press(str(action))


def _parse_nds_action(text: str, targets: list, buttons: Sequence[str]) -> "str | tuple | None":
    """Parse a model reply into a button string or touch tuple.

    Accepts (case-insensitive, tolerant of surrounding fluff):
      TOUCH <i>       — index into area-sorted targets list → ("touch", cx, cy)
      TOUCH <x> <y>  — raw coords, range-checked → ("touch", x, y)
      else            — delegate to _parse_button for a standard button word.
    Returns None if nothing matches.
    """
    if not text:
        return None
    t = text.strip()
    # Raw coords: TOUCH <x> <y>
    m = re.search(r"\btouch\s+(\d+)\s+(\d+)", t, re.IGNORECASE)
    if m:
        x, y = int(m.group(1)), int(m.group(2))
        if 0 <= x <= 255 and 0 <= y <= 191:
            return ("touch", x, y)
        # Out of range — fall through to button parse.
        return None
    # Index: TOUCH <i>
    m = re.search(r"\btouch\s+(\d+)", t, re.IGNORECASE)
    if m:
        i = int(m.group(1))
        if 0 <= i < len(targets):
            tgt = targets[i]
            return ("touch", tgt["cx"], tgt["cy"])
        # Out of range — fall through.
        return None
    return _parse_button(text, buttons)


class NDSTouchNavigator:
    """NDS navigator that can issue both button presses and stylus taps.

    mode='vlm' shows the top screen image to a local VLM; mode='ocr' sends text only.
    Detects touch targets on the bottom screen and offers them to the model as numbered
    options so touch-menu UIs can be cleared without knowing coordinates in advance.
    """

    def __init__(self, mode: str = "vlm", model: Optional[str] = None,
                 api_base: Optional[str] = None,
                 buttons: Sequence[str] = NDS_BUTTONS, upscale: int = 3):
        self.mode = mode
        self.buttons = buttons
        self.upscale = upscale
        self.model = model or ("openai/qwen2.5-vl" if mode == "vlm" else "openai/qwen2.5-text")
        self.api_base = api_base or ("http://localhost:8080/v1" if mode == "vlm" else "http://localhost:8081/v1")

    def decide(self, frame, buttons: Optional[Sequence[str]] = None) -> "str | tuple":
        bs = tuple(buttons or self.buttons)
        a = np.asarray(frame)
        if a.shape[0] == 384:
            top = a[:192]
            bot = a[192:]
        else:
            # Defensive: single screen passed — treat as top, no touch targets.
            top = a
            bot = None
        targets = _detect_touch_targets(bot) if bot is not None else []

        btn_list = ", ".join(bs)
        if targets:
            tgt_lines = "\n".join(
                f"  TOUCH {i} -> ({t['cx']},{t['cy']})" for i, t in enumerate(targets)
            )
        else:
            tgt_lines = "  (none detected)"

        prompt = (
            "You are playing a Nintendo DS game and the screen shows a TITLE SCREEN, MENU, or other "
            "non-gameplay UI. Your goal is to reach actual GAMEPLAY (a controllable character or scene).\n"
            f"NDS buttons: {btn_list}.\n"
            "Touch targets detected on the bottom (touch) screen (numbered, largest area first):\n"
            + tgt_lines + "\n"
            "Reply with EXACTLY ONE of:\n"
            "  - A button word (e.g. a, start, up)\n"
            "  - TOUCH <index>  (tap a numbered target above)\n"
            "  - TOUCH <x> <y>  (raw bottom-screen pixel, x 0-255 y 0-191)\n"
            "Reply with ONLY that — no other text."
        )

        if self.mode == "vlm":
            content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": _img_data_url(top, self.upscale)}},
            ]
        else:
            content = [{"type": "text", "text": prompt}]

        r = litellm.completion(
            model=self.model, api_base=self.api_base, api_key="local",
            messages=[{"role": "user", "content": content}],
            max_tokens=16, temperature=0,
        )
        raw = r.choices[0].message.content
        return _parse_nds_action(raw, targets, bs) or "a"


def _img_data_url(frame, upscale: int = 3) -> str:
    a = np.asarray(frame)[..., :3].astype("uint8")
    im = Image.fromarray(a, "RGB")
    if upscale > 1:
        im = im.resize((im.width * upscale, im.height * upscale), Image.NEAREST)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _small_gray(frame) -> np.ndarray:
    """Downscale a frame to a 36×40 float32 grayscale thumbnail (cheap screen fingerprint base)."""
    a = np.asarray(frame)[..., :3].mean(2)
    return np.asarray(Image.fromarray(a.astype("uint8")).resize((40, 36)), np.float32)


def _coarse_fingerprint(small: np.ndarray) -> tuple:
    """8×8 / 16-level coarse-gray fingerprint of a `_small_gray` thumbnail.

    Same screen (or the same menu re-rendered) collapses to one key; a genuinely new
    screen is distinct. Shared by every navigator that needs novelty/stall detection so
    the quantization stays in ONE place (the repo's anti-primitive-duplication rule)."""
    h, w = small.shape
    bh, bw = h // 8, w // 8
    grid = small[:bh * 8, :bw * 8].reshape(8, bh, 8, bw).mean(axis=(1, 3))
    return tuple(int(v / 16) for v in grid.flatten())


def _parse_button(text: str, buttons: Sequence[str]) -> Optional[str]:
    if not text:
        return None
    t = text.strip().lower()
    # exact first, then word-boundary search (model may add fluff despite instructions)
    if t in buttons:
        return t
    for b in buttons:
        if re.search(rf"\b{re.escape(b)}\b", t):
            return b
    return None


def _parse_action(text: str, buttons: Sequence[str]) -> Optional[str]:
    """Prefer an explicit 'ACTION: <button>' line; else the last button-word mentioned."""
    if not text:
        return None
    m = re.search(r"action\s*:\s*([a-z]+)", text, re.IGNORECASE)
    if m and m.group(1).lower() in buttons:
        return m.group(1).lower()
    # else: last button-word in the text (the conclusion usually comes last)
    found = [b for b in re.findall(r"[a-z]+", text.lower()) if b in buttons]
    return found[-1] if found else None


class VLMNavigator:
    """Screen pixels -> small VLM -> button."""

    def __init__(self, model: str = "openai/qwen2.5-vl", api_base: str = "http://localhost:8080/v1",
                 buttons: Sequence[str] = BUTTONS, upscale: int = 3, primed: bool = False):
        self.model, self.api_base, self.buttons, self.upscale = model, api_base, buttons, upscale
        self._prompt = _PROMPT_PRIMED if primed else _PROMPT
        self._fb_idx = 0   # fallback cycle index (used only when primed=True)
        self._primed = primed

    def _next_fallback(self) -> str:
        btn = _FALLBACK_CYCLE[self._fb_idx % len(_FALLBACK_CYCLE)]
        self._fb_idx += 1
        return btn

    def decide(self, frame, buttons: Optional[Sequence[str]] = None) -> str:
        bs = tuple(buttons or self.buttons)
        msg = [{"role": "user", "content": [
            {"type": "text", "text": self._prompt},
            {"type": "image_url", "image_url": {"url": _img_data_url(frame, self.upscale)}},
        ]}]
        r = litellm.completion(model=self.model, api_base=self.api_base, api_key="local",
                               messages=msg, max_tokens=8, temperature=0)
        parsed = _parse_button(r.choices[0].message.content, bs)
        return parsed if parsed is not None else (self._next_fallback() if self._primed else "a")


class MenuPerceiverNavigator:
    """Menu -> TEXT (RapidOCR lines + contrast cursor cue) -> small text LLM -> button.

    perceive() is the menu-perceiver built from our primitives: OCR the visible text rows and flag the
    row that stands out by local contrast (a selected/highlighted item is usually inverted or boxed).
    """

    def __init__(self, model: str = "openai/qwen2.5-text", api_base: str = "http://localhost:8081/v1",
                 buttons: Sequence[str] = BUTTONS, primed: bool = False):
        self.model, self.api_base, self.buttons = model, api_base, buttons
        self._ocr = None
        self._base_prompt = _PROMPT_PRIMED if primed else _PROMPT
        self._fb_idx = 0
        self._primed = primed

    def _next_fallback(self) -> str:
        btn = _FALLBACK_CYCLE[self._fb_idx % len(_FALLBACK_CYCLE)]
        self._fb_idx += 1
        return btn

    def _engine(self):
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR()
        return self._ocr

    def perceive(self, frame) -> dict:
        """Return {'lines': [{'text','box','y','gutter_ink'}...], 'cursor_hint': idx|None}.

        Cursor: the selection pointer (hand/arrow/dot) sits in the LEFT margin of the selected row.
        So for each OCR'd text row we measure 'ink' (deviation from the menu background) in the gutter
        just left of it; the row whose gutter clearly stands out is the selection. Robust to titles
        (a title has no left pointer), unlike the contrast heuristic which flagged the boldest text."""
        a = np.asarray(frame)[..., :3].astype("uint8")
        up = 4
        big = Image.fromarray(a, "RGB").resize((a.shape[1] * up, a.shape[0] * up), Image.NEAREST)
        res, _ = self._engine()(np.array(big)[:, :, ::-1])  # RGB->BGR
        gray = a.mean(2)
        bg = float(np.median(gray))                 # menu background level (most screens are flat-filled)
        lines = []
        for box, text, score in (res or []):
            xs = [p[0] / up for p in box]; ys = [p[1] / up for p in box]
            x0, y0, x1, y1 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
            x0, y0 = max(0, x0), max(0, y0)
            gx0 = max(0, x0 - 14)
            gutter = gray[y0:y1 + 1, gx0:x0]
            ink = float(np.abs(gutter - bg).mean()) if gutter.size else 0.0
            lines.append({"text": text, "box": [x0, y0, x1, y1], "y": y0, "gutter_ink": round(ink, 1)})
        cursor = None
        if lines:
            inks = sorted((l["gutter_ink"] for l in lines), reverse=True)
            top = inks[0]
            second = inks[1] if len(inks) > 1 else 0.0
            if top >= 6.0 and top > 1.5 * second:     # a clear marker, not just noise
                cursor = max(range(len(lines)), key=lambda i: lines[i]["gutter_ink"])
        return {"lines": lines, "cursor_hint": cursor}

    def decide(self, frame, buttons: Optional[Sequence[str]] = None) -> str:
        bs = tuple(buttons or self.buttons)
        menu = self.perceive(frame)
        rows = "\n".join(
            f"  y={l['y']:>3} \"{l['text']}\"{'   <-- SELECTION POINTER here' if i == menu['cursor_hint'] else ''}"
            for i, l in enumerate(menu["lines"])) or "  (no text detected)"
        prompt = (self._base_prompt + "\n\nThe perceiver read these on-screen text rows (top to bottom by y; OCR on a "
                  "pixel font is imperfect, infer intent). The row marked SELECTION POINTER has the menu "
                  "cursor next to it (blank if none detected):\n" + rows +
                  "\n\nMove the selection with up/down; choose the pointed option with 'a'.")
        r = litellm.completion(model=self.model, api_base=self.api_base, api_key="local",
                               messages=[{"role": "user", "content": prompt}], max_tokens=8, temperature=0)
        parsed = _parse_button(r.choices[0].message.content, bs)
        return parsed if parsed is not None else (self._next_fallback() if self._primed else "a")


_HARNESS_PROMPT = (
    "You are pressing buttons to get a video game from its TITLE/MENUS into actual GAMEPLAY (a controllable "
    "character or scene). Buttons: a, b, start, select, up, down, left, right.\n"
    "How menus work: to choose a menu option (e.g. 'New Game', 'Start', 'Yes'), move the cursor onto it with "
    "up/down/left/right, then press 'a' to SELECT it — selecting is what advances you. Don't just move the "
    "cursor back and forth; once the right option is highlighted, press 'a'. On a NAME-ENTRY letter grid, 'a' "
    "only ADDS a letter — to finish the name, move to an 'End'/'OK' tile or press 'start'. 'start' often "
    "confirms or skips."
)


class HarnessNavigator:
    """LLM navigator with a tiny agent harness: short action-history memory + brief reasoning.

    mode='vlm' shows the model the screen pixels; mode='ocr' shows it the menu-perceiver's text rows. Both
    record whether each press actually changed the screen and warn on repetition, so the model can notice a
    loop (e.g. pressing 'a' on a naming grid just appends letters) and switch strategy — the thing the
    stateless one-shot navigator couldn't do.
    """

    def __init__(self, mode: str = "vlm", model: Optional[str] = None,
                 api_base: Optional[str] = None, buttons: Sequence[str] = BUTTONS, hist: int = 5):
        self.mode = mode
        self.buttons = buttons
        self.hist = hist
        self.model = model or ("openai/qwen2.5-vl" if mode == "vlm" else "openai/qwen2.5-text")
        self.api_base = api_base or ("http://localhost:8080/v1" if mode == "vlm" else "http://localhost:8081/v1")
        self._history: list = []          # (button, changed|None)
        self._prev = None
        self._recent: list = []           # small grayscale frames, for same-screen stall detection
        self._perceiver = MenuPerceiverNavigator() if mode == "ocr" else None

    def _small(self, frame) -> np.ndarray:
        return _small_gray(frame)

    def _stalled(self, frame) -> bool:
        """True if we've been on essentially the same screen for ~6 presses (stuck in a menu)."""
        g = self._small(frame)
        stuck = len(self._recent) >= 6 and float(np.abs(g - self._recent[-6]).mean()) < 4.0
        self._recent.append(g)
        return stuck

    def _changed(self, frame) -> Optional[bool]:
        if self._prev is None:
            return None
        a = np.asarray(frame)[..., :3].mean(2)
        b = np.asarray(self._prev)[..., :3].mean(2)
        if a.shape != b.shape:
            return True
        return float(np.abs(a - b).mean()) > 1.5

    def _content(self, frame) -> list:
        if self.mode == "vlm":
            return [{"type": "image_url", "image_url": {"url": _img_data_url(frame, 4)}}]
        menu = self._perceiver.perceive(frame)
        rows = "\n".join(
            f"  y={l['y']:>3} \"{l['text']}\"{'  <-- SELECTION POINTER' if i == menu['cursor_hint'] else ''}"
            for i, l in enumerate(menu["lines"])) or "  (no text detected)"
        return [{"type": "text", "text": "On-screen text rows (top to bottom; OCR on a pixel font is "
                 "imperfect):\n" + rows}]

    def decide(self, frame, buttons: Optional[Sequence[str]] = None) -> str:
        bs = tuple(buttons or self.buttons)
        ch = self._changed(frame)
        if self._history and ch is not None:          # annotate the previous action's outcome
            self._history[-1] = (self._history[-1][0], ch)
        recent = [b for b, _ in self._history[-3:]]
        looping = len(recent) == 3 and len(set(recent)) == 1
        hist_txt = "\n".join(
            f"  {b} -> {'changed' if c else 'no change' if c is not None else '?'}"
            for b, c in self._history[-self.hist:]) or "  (none yet)"
        warn = ""
        if self._stalled(frame):
            tried = sorted({b for b, _ in self._history[-6:]})
            warn = (f"\nWARNING: the screen has barely changed for ~6 presses (tried: {tried}) — you are STUCK. "
                    "If this is a name-entry grid, the name is already entered; press 'start' to confirm/finish. "
                    "Otherwise try a button you have NOT been pressing.")
        elif looping:
            last = recent[-1]
            if last in ("up", "down", "left", "right"):
                warn = (f"\nWARNING: you've pressed '{last}' 3 times — you're just moving the cursor, not "
                        "advancing. Press 'a' now to SELECT the highlighted option.")
            elif last == "a":
                warn = ("\nWARNING: you've pressed 'a' 3 times with no real progress (e.g. only adding letters "
                        "on a name grid). Press 'start' to confirm/finish, or move to an 'End'/'OK' option.")
            else:
                warn = f"\nWARNING: you've pressed '{last}' 3 times with no progress — try a different button."
        prompt = (_HARNESS_PROMPT + "\n\nYour recent presses and whether the screen changed:\n" + hist_txt +
                  warn + "\n\nThink in ONE short sentence, then end with a final line: ACTION: <button>")
        content = [{"type": "text", "text": prompt}] + self._content(frame)
        r = litellm.completion(model=self.model, api_base=self.api_base, api_key="local",
                               messages=[{"role": "user", "content": content}], max_tokens=160, temperature=0)
        raw = r.choices[0].message.content
        self.last_prompt, self.last_raw = prompt, raw   # for debugging/inspection
        btn = _parse_action(raw, bs) or "a"
        self._history.append((btn, None))
        self._prev = np.asarray(frame).copy()
        return btn


_REACT_SYSTEM = (
    "You are an agent pressing Game Boy buttons to get a game from its TITLE/MENUS into actual GAMEPLAY "
    "(a controllable character or scene). Buttons: a, b, start, select, up, down, left, right.\n"
    "Menu rules: to choose an option, move the cursor onto it with up/down/left/right, then press 'a' to "
    "select it. On a name-entry LETTER GRID, 'a' only ADDS a letter — to FINISH the name, press 'start' (or "
    "move the cursor to an 'End'/'OK' tile). 'start' often confirms a menu or skips a screen.\n"
    "Each turn I give you an Observation: what your last press did, plus the current screen image. "
    "Reply in EXACTLY this format and nothing else:\n"
    "Thought: <1-2 sentences: what is on screen, are you making progress, what will advance toward gameplay>\n"
    "Action: <exactly one of: a, b, start, select, up, down, left, right>"
)


class ReActNavigator:
    """A real ReAct loop: one maintained conversation of Thought/Action/Observation turns.

    Unlike HarnessNavigator (a fresh single-shot each step), the model SEES its own prior Thoughts and the
    Observations they produced, so reasoning accumulates. Only the latest screen image is kept in context
    (older turns keep their text but drop the image) to bound a small model's context window.
    """

    def __init__(self, mode: str = "vlm", model: Optional[str] = None,
                 api_base: Optional[str] = None, buttons: Sequence[str] = BUTTONS, keep_turns: int = 8):
        self.mode = mode
        self.buttons = buttons
        self.keep_turns = keep_turns
        self.model = model or ("openai/qwen2.5-vl" if mode == "vlm" else "openai/qwen2.5-text")
        self.api_base = api_base or ("http://localhost:8080/v1" if mode == "vlm" else "http://localhost:8081/v1")
        self.messages: list = [{"role": "system", "content": _REACT_SYSTEM}]
        self._prev = None
        self._recent: list = []
        self._last_btn: Optional[str] = None
        self._btns: list = []             # recent buttons pressed, for naming the repeat in a stall warning
        self._perceiver = MenuPerceiverNavigator() if mode == "ocr" else None
        self.last_raw = ""

    def _small(self, frame) -> np.ndarray:
        return _small_gray(frame)

    def _changed(self, frame) -> Optional[bool]:
        if self._prev is None:
            return None
        a, b = self._small(frame), self._small(self._prev)
        return float(np.abs(a - b).mean()) > 1.5

    def _stalled(self, frame) -> bool:
        g = self._small(frame)
        stuck = len(self._recent) >= 6 and float(np.abs(g - self._recent[-6]).mean()) < 4.0
        self._recent.append(g)
        return stuck

    def _stall_peek(self, frame) -> bool:
        """Non-mutating stall check: same result as `_stalled` WITHOUT appending to `_recent`.

        Lets a subclass (MemNavigator) ask "are we stalled?" before delegating to
        `super().decide()` — which calls `_stalled` itself. Without this, MemNavigator
        and ReActNavigator both append per step, so `_recent` grows twice as fast and the
        ~6-frame stall window fires at ~3."""
        if len(self._recent) < 6:
            return False
        g = self._small(frame)
        return float(np.abs(g - self._recent[-6]).mean()) < 4.0

    def _screen_content(self, frame) -> list:
        if self.mode == "vlm":
            return [{"type": "image_url", "image_url": {"url": _img_data_url(frame, 4)}}]
        menu = self._perceiver.perceive(frame)
        rows = "\n".join(
            f"  y={l['y']:>3} \"{l['text']}\"{'  <-- POINTER' if i == menu['cursor_hint'] else ''}"
            for i, l in enumerate(menu["lines"])) or "  (no text detected)"
        return [{"type": "text", "text": "Screen text rows (OCR, imperfect):\n" + rows}]

    def _strip_old_images(self):
        for m in self.messages:
            if m["role"] == "user" and isinstance(m["content"], list):
                kept = [c for c in m["content"] if c.get("type") != "image_url"]
                if len(kept) != len(m["content"]):
                    kept.append({"type": "text", "text": "[earlier screen — not shown]"})
                m["content"] = kept

    def _trim(self):
        # keep system + the last keep_turns*2 messages (user/assistant pairs)
        if len(self.messages) > 1 + self.keep_turns * 2:
            tail = self.messages[-self.keep_turns * 2:]
            while tail and tail[0]["role"] != "user":   # don't start the convo mid-pair (on an assistant turn)
                tail = tail[1:]
            self.messages = [self.messages[0]] + tail

    def decide(self, frame, buttons: Optional[Sequence[str]] = None) -> str:
        bs = tuple(buttons or self.buttons)
        ch = self._changed(frame)
        stalled = self._stalled(frame)
        obs = []
        if self._last_btn is not None:
            obs.append(f"You pressed '{self._last_btn}'. The screen "
                       f"{'changed.' if ch else 'did NOT change.' if ch is not None else 'updated.'}")
        if stalled:
            repeated = sorted({b for b in self._btns[-6:]})
            obs.append(
                f"You have been on essentially the same screen for ~6 turns — you are STUCK. You already "
                f"tried {repeated} on THIS screen and NOTHING happened, so do NOT press any of "
                f"{repeated} again this turn. The screen image is misleading — pressing the same button "
                "will not advance you. Pick a DIFFERENT button: if this is a New Game/Continue menu, press "
                "'a' to SELECT the highlighted option; if this is a name-entry letter grid, press 'start' "
                "to FINISH the name.")
        obs.append("Current screen:")
        self._strip_old_images()
        self.messages.append({"role": "user", "content": [{"type": "text", "text": " ".join(obs)}]
                              + self._screen_content(frame)})
        self._trim()
        temp = 0.7 if stalled else 0.0   # break temp-0 determinism only when stuck
        r = litellm.completion(model=self.model, api_base=self.api_base, api_key="local",
                               messages=self.messages, max_tokens=200, temperature=temp)
        raw = r.choices[0].message.content
        self.messages.append({"role": "assistant", "content": raw})
        btn = _parse_action(raw, bs) or "a"
        self.last_raw = raw
        self._prev = np.asarray(frame).copy()
        self._last_btn = btn
        self._btns.append(btn)
        return btn


# ---------------------------------------------------------------------------
# Variant 1: LadderLLMNavigator
# Runs the blind escape ladder by default; wakes the VLM only on a novelty stall.
# A "novelty stall" fires when the set of seen screen fingerprints has cycled —
# i.e. no genuinely new fingerprint in the last N steps.  This catches name-grid
# loops where _changed() flickers (a keeps adding letters) but the screen-set
# repeats, a case the frame-diff alone cannot detect.
# ---------------------------------------------------------------------------

_NOVELTY_WINDOW = 6   # steps without a new fingerprint → stall


class LadderLLMNavigator:
    """Blind escape ladder + on-stall VLM wake.  Cost metric: self.wakes."""

    def __init__(self, mode: str = "vlm", model: Optional[str] = None,
                 api_base: Optional[str] = None, buttons: Sequence[str] = BUTTONS):
        self.buttons = buttons
        self.mode = mode
        self.model = model or "openai/qwen2.5-vl"
        self.api_base = api_base or "http://localhost:8080/v1"
        from core.autoplay import ModalAutoPolicy
        self._policy = ModalAutoPolicy(random.Random(0), lambda r: ["right"])
        self._prev = None
        self._last: list = []
        self.wakes: int = 0
        # Ring of fingerprints (hashable tuples) seen in the last N steps.
        self._fp_ring: list = []   # recent fingerprints (may have repeats)
        self._fp_seen: set = set() # unique fingerprints ever seen

    def _fingerprint(self, frame) -> tuple:
        """Coarse 8×8 quantized gray — same screen set collapses; genuinely new screen is distinct."""
        return _coarse_fingerprint(_small_gray(frame))

    def _stalled(self, frame) -> bool:
        fp = self._fingerprint(frame)
        self._fp_ring.append(fp)
        if len(self._fp_ring) > _NOVELTY_WINDOW:
            self._fp_ring.pop(0)
        # Stall = none of the last N fingerprints are new (all were seen before).
        new_in_window = any(f not in self._fp_seen for f in self._fp_ring)
        self._fp_seen.add(fp)
        return len(self._fp_ring) >= _NOVELTY_WINDOW and not new_in_window

    def decide(self, frame, buttons: Optional[Sequence[str]] = None) -> str:
        bs = tuple(buttons or self.buttons)
        if not self._stalled(frame):
            mode_buttons = self._policy.decide(self._prev, frame, self._last)[1]
            btn = mode_buttons[0] if mode_buttons else "right"
            self._prev = np.asarray(frame).copy()
            self._last = [btn]
            return btn
        # Novelty stall — wake LLM once for a corrective button.
        self.wakes += 1
        content: list = [{"type": "text", "text": _HARNESS_PROMPT + "\nThink briefly, then: ACTION: <button>"}]
        if self.mode == "vlm":
            content.append({"type": "image_url", "image_url": {"url": _img_data_url(frame, 3)}})
        r = litellm.completion(model=self.model, api_base=self.api_base, api_key="local",
                               messages=[{"role": "user", "content": content}],
                               max_tokens=64, temperature=0.7)
        btn = _parse_action(r.choices[0].message.content, bs) or "a"
        # The wake changes the screen out from under the ladder; reset its rotation so it
        # resumes from the advance-biased top instead of a stale mid-ladder move (which
        # otherwise derails a screen the fresh ladder would have cleared).
        self._policy.reset()
        self._prev = np.asarray(frame).copy()
        self._last = [btn]
        return btn


# ---------------------------------------------------------------------------
# Variant 2: MemNavigator
# ReActNavigator + dead-button ledger (OutcomeMemory) + durable lesson scratchpad.
# ---------------------------------------------------------------------------

_PREF_ORDER = ("start", "right", "down", "a", "b", "up", "left", "select")


class MemNavigator(ReActNavigator):
    """ReAct conversation extended with durable dead-button memory and lesson scratchpad."""

    def __init__(self, mode: str = "vlm", model: Optional[str] = None,
                 api_base: Optional[str] = None, buttons: Sequence[str] = BUTTONS,
                 keep_turns: int = 8):
        super().__init__(mode=mode, model=model, api_base=api_base,
                         buttons=buttons, keep_turns=keep_turns)
        from core.outcome import OutcomeMemory
        self._mem = OutcomeMemory(dead_after=2)
        self._lessons: list = []   # deduped, capped at 5, ≤120 chars each

    def _screen_key(self, frame) -> tuple:
        """8×8 / 16-level coarse fingerprint — same menu collapses; distinct menus differ."""
        return _coarse_fingerprint(self._small(frame))

    def _lesson_header(self) -> str:
        if not self._lessons:
            return ""
        return "Lessons learned THIS run (still apply):\n" + "\n".join(f"- {l}" for l in self._lessons)

    def _parse_lesson(self, raw: str) -> Optional[str]:
        m = re.search(r"lesson\s*:\s*(.+)", raw, re.IGNORECASE)
        if not m:
            return None
        text = m.group(1).strip()[:120]
        return text if text else None

    def decide(self, frame, buttons: Optional[Sequence[str]] = None) -> str:
        bs = tuple(buttons or self.buttons)
        # Record previous press outcome before updating self._prev.
        if self._last_btn is not None and self._prev is not None:
            key = self._screen_key(self._prev)
            effective = bool(self._changed(frame))
            self._mem.record(key, self._last_btn, effective)

        # Determine dead buttons for the current screen.
        curr_key = self._screen_key(frame)
        dead = set(self._mem.dead_actions(curr_key))

        # Inject dead-button warning + lessons into the system message for this turn.
        # We temporarily swap the system message, then restore after the call to keep
        # _trim() from ever seeing the injected text as a trimmed user/assistant turn.
        orig_system = self.messages[0]["content"]
        injected = orig_system
        if dead:
            injected = injected + f"\nOn THIS screen these buttons did nothing — do NOT press: {sorted(dead)}"
        lesson_hdr = self._lesson_header()
        if lesson_hdr:
            injected = injected + "\n" + lesson_hdr

        # Peek (non-mutating): super().decide() below calls _stalled() itself, which appends
        # to _recent. Calling _stalled() here too would double the append and halve the window.
        stalled = self._stall_peek(frame)
        if stalled and not injected.endswith("...and write a one-line Lesson so you don't repeat this"):
            injected = injected + "\n...and write a one-line Lesson so you don't repeat this"

        self.messages[0] = {"role": "system", "content": injected}
        btn = super().decide(frame, buttons)
        self.messages[0] = {"role": "system", "content": orig_system}

        # Override with a non-dead button if model chose a dead one.
        if btn in dead:
            for candidate in _PREF_ORDER:
                if candidate not in dead and candidate in bs:
                    btn = candidate
                    break

        # Parse and store lesson from this turn's raw output.
        lesson = self._parse_lesson(self.last_raw)
        if lesson and lesson not in self._lessons:
            self._lessons.append(lesson)
            if len(self._lessons) > 5:
                self._lessons.pop(0)

        # Fix _last_btn to what we actually returned (super().decide set it to something else).
        self._last_btn = btn
        if self._btns:
            self._btns[-1] = btn
        return btn


# ---------------------------------------------------------------------------
# UITARSNavigator
# GUI-grounding via UI-TARS-2B: given a screen + target description, outputs
# a click coordinate.  NDS → touch (primary); GB/GBA → derived dpad (experimental).
# ---------------------------------------------------------------------------

def _parse_uitars_coords(text: str) -> "tuple[int, int] | None":
    """Extract the first two integers from a UI-TARS reply (tolerant of wrapping text).

    Handles v1 "(499,637)" / "click(start_box='<|box_start|>(x,y)<|box_end|>')",
    doubao "<point>x y</point>", and any reply with at least two digit sequences.
    Returns (x, y) as raw integers (0-1000 scale) or None on failure.
    """
    if not text:
        return None
    # v1: explicit (x,y) pair (comma-separated).
    m = re.search(r"\((\d+)\s*,\s*(\d+)\)", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    # doubao: <point>x y</point> (space-separated).
    m = re.search(r"<point>\s*(\d+)\s+(\d+)\s*</point>", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Fallback: first two digit runs anywhere in the string.
    nums = re.findall(r"\d+", text)
    if len(nums) >= 2:
        return int(nums[0]), int(nums[1])
    return None


_UITARS_SYSTEM = (
    "You are a GUI agent. You are given a task and a screenshot. "
    "You need to perform the next action to complete the task.\n\n"
    "## Output Format\n"
    "Action: ...\n\n"
    "## Action Space\n"
    "click(start_box='<|box_start|>(x1,y1)<|box_end|>')\n\n"
    "## User Instruction\n"
    "{instruction}"
)

_UITARS_PROMPT_TOUCH = "Tap the on-screen button or menu option that advances toward starting or continuing the game."
_UITARS_PROMPT_TARGET = "Click the menu option that starts or advances the game (e.g. New Game / Start / Yes)."
_UITARS_PROMPT_CURSOR = "Click the option currently highlighted by the cursor or selection pointer."

# Threshold (fraction of frame height) within which target and cursor are
# considered "aligned" → press "a".
_UITARS_ALIGN_THRESH = 0.08


class UITARSNavigator:
    """GUI-grounding navigator backed by UI-TARS-2B.

    NDS (console="nds"): sends only the bottom screen to UI-TARS, parses a
    normalized (0-1000) coordinate, scales to bottom-screen pixels, and returns
    a ("touch", x, y) tuple.  On parse failure returns "a".

    GB/GBA (console in {"gb","gba"}): EXPERIMENTAL — uses two sequential
    UI-TARS queries (target option + cursor position) on the full frame to
    derive a dpad direction.  Falls back to "start" / rotating cycle on failure.
    """

    def __init__(self, console: str = "nds", model: str = "openai/uitars",
                 api_base: str = "http://localhost:8080/v1", upscale: int = 3):
        self.console = console
        self.model = model
        self.api_base = api_base
        self.upscale = upscale
        self._fb_idx = _FALLBACK_CYCLE.index("start")   # GB/GBA fallback rotation (start-first)

    def _next_fallback(self) -> str:
        btn = _FALLBACK_CYCLE[self._fb_idx % len(_FALLBACK_CYCLE)]
        self._fb_idx += 1
        return btn

    def _query(self, frame, prompt: str) -> "tuple[int, int] | None":
        """Send frame + task to UI-TARS; return parsed (x, y) in 0-1000 space or None."""
        try:
            msg = [
                {"role": "system", "content": _UITARS_SYSTEM.format(instruction=prompt)},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": _img_data_url(frame, self.upscale)}},
                ]},
            ]
            r = litellm.completion(
                model=self.model, api_base=self.api_base, api_key="local",
                messages=msg, max_tokens=64, temperature=0,
            )
            return _parse_uitars_coords(r.choices[0].message.content)
        except Exception:
            return None

    def _decide_nds(self, frame) -> "str | tuple":
        """NDS priority path: touch the bottom screen."""
        a = np.asarray(frame)
        if a.shape[0] == 384:
            bot = a[192:]   # bottom screen: 192 rows × 256 cols
        else:
            bot = a         # defensive: single screen passed
        H, W = bot.shape[:2]   # 192, 256

        coords = self._query(bot, _UITARS_PROMPT_TOUCH)
        if coords is None:
            return "a"
        nx, ny = coords
        px = min(max(round(nx / 1000 * W), 0), W - 1)
        py = min(max(round(ny / 1000 * H), 0), H - 1)
        return ("touch", px, py)

    def _decide_gb(self, frame) -> str:
        """GB/GBA experimental path: derive dpad from two grounding queries.

        Two queries on the full frame:
          1. target: where is the option to select?
          2. cursor: where is the currently highlighted item?
        If both succeed and are vertically close → "a" (already aligned);
        else navigate toward the target.  Falls back to "start" then cycle.
        """
        a = np.asarray(frame)
        H, W = a.shape[:2]

        target = self._query(a, _UITARS_PROMPT_TARGET)
        cursor = self._query(a, _UITARS_PROMPT_CURSOR)

        if target is None or cursor is None:
            # One query failed — rotate through the fallback cycle (starts at "start").
            return self._next_fallback()

        # Scale to pixel space for comparison.
        ty = round(target[1] / 1000 * H)
        cy = round(cursor[1] / 1000 * H)
        tx = round(target[0] / 1000 * W)
        cx = round(cursor[0] / 1000 * W)

        thresh_px = round(_UITARS_ALIGN_THRESH * H)
        if abs(ty - cy) <= thresh_px:
            return "a"   # cursor is on the target row → select it
        if ty < cy:
            return "up"
        if ty > cy:
            return "down"
        # Same row but different column (shouldn't happen often on GB menus).
        return "left" if tx < cx else "right"

    def decide(self, frame) -> "str | tuple":
        """Return a button str or ("touch", x, y) tuple.  Never raises."""
        try:
            if self.console == "nds":
                return self._decide_nds(frame)
            else:
                # GB / GBA (experimental grounding bridge).
                return self._decide_gb(frame)
        except Exception:
            return "a"


# ---------------------------------------------------------------------------
# HybridNavigator
# The escape ladder reaches the menu; UI-TARS navigates it once you're there.
# ---------------------------------------------------------------------------

class HybridNavigator:
    """Blind escape-ladder front-half, then hand off to UI-TARS grounding.

    Diagnosis (reports/2026-06-30 Exp 5): a pure-touch UI-TARS navigator gets STUCK on boot
    splashes / loading screens — there is nothing to ground or tap, and it cannot press
    start/wait to get *past* them (Phoenix Wright: Capcom splash → black loading → taps the
    center ×24 forever). The blind escape ladder is exactly the System-1 floor that advances
    through splash/title/loading; UI-TARS is the specialist that clears the menu once we are
    there. This composes the two: run the ladder until we have ARRIVED at a real menu, then
    latch into UI-TARS grounding for the rest of the run.

    Handoff trigger (per console):
      - NDS  : the bottom screen has >= `min_targets` detectable touch targets — a real touch
               menu is up. Flat splash / black loading screens have no edges → no targets → we
               keep laddering past them.
      - GB/GBA: a novelty-stall — the ladder has pressed for `_NOVELTY_WINDOW` steps without
               reaching a genuinely new screen fingerprint, i.e. it has hit a menu it cannot
               clear on its own (name grid / file-select). Hand to the UI-TARS grounding bridge.

    Telemetry: `handed_off` (have we switched yet) and `wakes` (UI-TARS grounding steps = the
    cost signal, mirroring LadderLLMNavigator.wakes). The navigator is constructed fresh per
    ROM, so no reset is needed between runs.
    """

    def __init__(self, console: str = "nds", model: str = "openai/uitars",
                 api_base: str = "http://localhost:8080/v1", upscale: int = 3,
                 min_targets: int = 1, buttons: Sequence[str] = BUTTONS):
        self.console = console
        self.buttons = buttons
        self.min_targets = min_targets
        self._uitars = UITARSNavigator(console=console, model=model,
                                       api_base=api_base, upscale=upscale)
        from core.autoplay import ModalAutoPolicy
        self._policy = ModalAutoPolicy(random.Random(0), lambda r: ["right"])
        self._prev = None
        self._last: list = []
        self.handed_off: bool = False
        self.wakes: int = 0
        # Novelty-stall fingerprint state (GB/GBA handoff trigger).
        self._fp_ring: list = []
        self._fp_seen: set = set()

    @staticmethod
    def _bottom(frame) -> np.ndarray:
        a = np.asarray(frame)
        return a[192:] if a.shape[0] == 384 else a

    def _stalled(self, frame) -> bool:
        """True once the ladder has gone `_NOVELTY_WINDOW` steps with no genuinely new screen."""
        fp = _coarse_fingerprint(_small_gray(frame))
        self._fp_ring.append(fp)
        if len(self._fp_ring) > _NOVELTY_WINDOW:
            self._fp_ring.pop(0)
        new_in_window = any(f not in self._fp_seen for f in self._fp_ring)
        self._fp_seen.add(fp)
        return len(self._fp_ring) >= _NOVELTY_WINDOW and not new_in_window

    def _at_menu(self, frame) -> bool:
        """Have we reached a menu UI-TARS should take over? (console-specific trigger)."""
        if self.console == "nds":
            return len(_detect_touch_targets(self._bottom(frame))) >= self.min_targets
        # GB / GBA: the ladder stalling on a screen it can't clear is the handoff cue.
        return self._stalled(frame)

    def decide(self, frame, buttons: Optional[Sequence[str]] = None) -> "str | tuple":
        if not self.handed_off and self._at_menu(frame):
            self.handed_off = True
        if self.handed_off:
            self.wakes += 1
            return self._uitars.decide(frame)
        # Still in the splash/title/loading run — step the blind escape ladder.
        mode_buttons = self._policy.decide(self._prev, frame, self._last)[1]
        btn = mode_buttons[0] if mode_buttons else "right"
        self._prev = np.asarray(frame).copy()
        self._last = [btn]
        return btn
