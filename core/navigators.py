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
                 buttons: Sequence[str] = BUTTONS, upscale: int = 3):
        self.model, self.api_base, self.buttons, self.upscale = model, api_base, buttons, upscale

    def decide(self, frame, buttons: Optional[Sequence[str]] = None) -> str:
        bs = tuple(buttons or self.buttons)
        msg = [{"role": "user", "content": [
            {"type": "text", "text": _PROMPT},
            {"type": "image_url", "image_url": {"url": _img_data_url(frame, self.upscale)}},
        ]}]
        r = litellm.completion(model=self.model, api_base=self.api_base, api_key="local",
                               messages=msg, max_tokens=8, temperature=0)
        return _parse_button(r.choices[0].message.content, bs) or "a"


class MenuPerceiverNavigator:
    """Menu -> TEXT (RapidOCR lines + contrast cursor cue) -> small text LLM -> button.

    perceive() is the menu-perceiver built from our primitives: OCR the visible text rows and flag the
    row that stands out by local contrast (a selected/highlighted item is usually inverted or boxed).
    """

    def __init__(self, model: str = "openai/qwen2.5-text", api_base: str = "http://localhost:8081/v1",
                 buttons: Sequence[str] = BUTTONS):
        self.model, self.api_base, self.buttons = model, api_base, buttons
        self._ocr = None

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
        prompt = (_PROMPT + "\n\nThe perceiver read these on-screen text rows (top to bottom by y; OCR on a "
                  "pixel font is imperfect, infer intent). The row marked SELECTION POINTER has the menu "
                  "cursor next to it (blank if none detected):\n" + rows +
                  "\n\nMove the selection with up/down; choose the pointed option with 'a'.")
        r = litellm.completion(model=self.model, api_base=self.api_base, api_key="local",
                               messages=[{"role": "user", "content": prompt}], max_tokens=8, temperature=0)
        return _parse_button(r.choices[0].message.content, bs) or "a"


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
        a = np.asarray(frame)[..., :3].mean(2)
        return np.asarray(Image.fromarray(a.astype("uint8")).resize((40, 36)), np.float32)

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
        a = np.asarray(frame)[..., :3].mean(2)
        return np.asarray(Image.fromarray(a.astype("uint8")).resize((40, 36)), np.float32)

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
