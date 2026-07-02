#!/usr/bin/env python
"""world_mcp.py — expose a Game Boy world as an MCP (stdio) server so a Claude Code instance can BE the
System-2 brain. This realizes ADR-001's S4 seam: WORLD = MCP server (System 1 + perception), AGENT = MCP
client (a Claude Agent). It is a TEST harness for attended Claude-Code-+-MCP use — NOT an unattended service.

North-star alignment (both review findings addressed):
  * The brain consumes the SYMBOLIC STATE, not pixels — "the agent never sees pixels" (ADR-001 / INSIGHTS §1).
    The screenshot is an independent perception channel that would reopen the §4 confabulation failure, so it
    is OFF by default and only behind --with-screenshot (a debug aid, never the brain's primary input).
  * Cost-first / dual-process — System 1 drives, System 2 wakes at decisions (INSIGHTS §5). The `explore` and
    `goto` tools run the free ExploreBrain autopilot and hand control back only at a decision point.
  * No-leak — only the pixels-derived SymbolicState (+ the optional debug PNG) crosses the wire. The watched
    RAM goes to oracle.jsonl on disk (scoring only) and is NEVER returned by any tool.

Self-improvement (INSIGHTS §6, S5) — WITHIN-RUN ONLY, per the learning-boundary HARD LAW (blank every run):
  * `remember(lesson)` lets the brain author tool-use lessons; they are re-injected into every result so
    experience compounds across the session. Discarded when the process ends (= run end). No across-run store.
  * A delegation tally (decisions vs. tiles auto-walked by System 1) is surfaced each turn, so the brain can
    see its own cost and learn to push routine movement onto explore/goto. Falling wakes/tile = the signal.
  * Promoting a proven skill into durable code is a DELIBERATE later step (an It4-era ADR), never auto-persist.

Why stdlib (no `mcp` dep): the frozen contract (core/contracts.py) is "shape-compatible with MCP via a thin
adapter" — a ToolSpec already IS an MCP tool, a ToolResult already IS a JSON result.
"""
from __future__ import annotations

import os
import sys

# --- stdout is the JSON-RPC channel; keep it pristine. Redirect fd 1 -> stderr BEFORE importing the game
# stack (PyBoy prints a banner to stdout, which would corrupt the protocol). Protocol writes use _OUT. ---
_OUT = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
os.dup2(2, 1)
sys.stdout = sys.stderr
try:
    sys.stdin.reconfigure(encoding="utf-8")   # MCP/JSON-RPC is UTF-8; Windows stdin else defaults to cp1252
except Exception:
    pass

import argparse
import base64
import io
import json
import signal
import uuid

# Run from the repo root so `import core` and relative rom/run paths resolve regardless of launch cwd.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from core.brains import ExploreBrain        # noqa: E402  (the free System-1 autopilot)
from core.contracts import ToolCall         # noqa: E402
from core.gateway import Gateway            # noqa: E402
from core.gb_emulator import BUTTONS as _GB_BUTTONS   # noqa: E402  (cheap import — no PyBoy; for the static tool list)
import core.nds_emulator as _nds_emu_mod   # noqa: E402  (for NDS BUTTONS; lazy-guard: import succeeds even without py-desmume)
import core.gba_emulator as _gba_emu_mod   # noqa: E402  (for GBA BUTTONS; lazy-guard: import succeeds even without mgba)

import importlib                            # noqa: E402  (worlds loaded by --game from GAMES — game-agnostic)

# Per-world registry so this harness serves ANY world via `--game`, not just Cave Noire. Each entry is the
# import paths + the per-world bits (default ROM, the RAM `watch` for the SCORING oracle — never on the wire).
# Lean worlds share the structure (a PerceptionPlugin subclass + a GridPerceiver-based perceiver + a sandbox).
_NDS_WORLDS = frozenset({"nds"})   # game keys that are NDS worlds (get touch + NDS buttons)
_GBA_WORLDS = frozenset({"kirby_gba", "emerald_gba"})   # game keys that are GBA worlds (mgba, no touch)
# Worlds that get the foveated region tools (ADR-002 Phase D probe: read_region + whats_changed). Scoped
# to cave_noire (the gate world) + its A/B control + the other lean GB world (gauntlet) — NOT the NDS/GBA
# worlds (no proven need there yet) and NOT pokemon_red (its own perceiver/prompt already ships screen_text).
_REGION_TOOL_WORLDS = frozenset({"cave_noire", "cave_noire_baseline", "gauntlet"})

# Lazy import so world_mcp.py is importable without py-desmume installed.
def _nds_sandbox():
    from core.permissions import Allowlist
    return Allowlist({"press_button", "press_sequence", "wait", "touch", "touch_target"})


# Lazy import so world_mcp.py is importable without mgba installed (GB-only sessions pay no cost).
def _gba_sandbox():
    from core.permissions import Allowlist
    return Allowlist({"press_button", "press_sequence", "wait"})


# Locally-built sandbox for the generic GB/GBC lean world (gb_generic) — mirrors _gba_sandbox()/_nds_sandbox();
# no game package to pull a *_SANDBOX constant from since gb_generic has no game-specific plugin.
def _gb_generic_sandbox():
    from core.permissions import Allowlist
    return Allowlist({"press_button", "press_sequence", "wait"})

GAMES = {
    "cave_noire": {"pkg": "games.cave_noire", "plugin": "CaveNoirePlugin", "sandbox": "CAVE_NOIRE_SANDBOX",
                   "perceiver_mod": "games.cave_noire.perceiver", "perceiver": "CaveNoirePerceiver",
                   "rom": "roms/Cave Noire (Japan) [T-En by Aeon Genesis v1.00].gb",
                   "watch": {"x": 0xC504, "y": 0xC503, "hp": 0xC120}},   # hp = ADR-002 gate life oracle (BCD)
    "cave_noire_baseline": {"pkg": "games.cave_noire", "plugin": "CaveNoirePlugin", "sandbox": "CAVE_NOIRE_SANDBOX",
                   "perceiver_mod": "games.cave_noire.perceiver", "perceiver": "CaveNoireBaselinePerceiver",
                   "rom": "roms/Cave Noire (Japan) [T-En by Aeon Genesis v1.00].gb",
                   "watch": {"x": 0xC504, "y": 0xC503, "hp": 0xC120}},   # A/B CONTROL: dead-reckon, no localizer (BCD)
    "gauntlet": {"pkg": "games.gauntlet", "plugin": "GauntletPlugin", "sandbox": "GAUNTLET_SANDBOX",
                 "perceiver_mod": "games.gauntlet.perceiver", "perceiver": "GauntletPerceiver",
                 "rom": "roms/Gauntlet II (USA, Europe).gb",
                 "watch": {"x": 0xC286, "y": 0xC2C6}},
    # NDS world: uses NDSPerceptionPlugin (adds touch) + NDSPerceiver + NDS BUTTONS.
    "nds": {"pkg": "core.nds_perception_plugin", "plugin": "NDSPerceptionPlugin",
            "sandbox": "NDS_MCP_SANDBOX",
            "perceiver_mod": "core.nds_perceiver", "perceiver": "NDSPerceiver",
            "rom": "roms/nds/game.nds",   # override with --rom
            "watch": {}},
    "pokemon_red": {"pkg": "games.pokemon_red", "plugin": "PokemonRedPlugin", "sandbox": "POKEMON_SANDBOX",
                    "perceiver_mod": "games.pokemon_red.perceiver", "perceiver": "OverworldPerceiver",
                    "rom": "roms/PokemonRed.gb",
                    "watch": {"x": 0xD362, "y": 0xD361, "map": 0xD35E, "party": 0xD163, "badges": 0xD356}},
    # GBA worlds: use the shared PerceptionPlugin (as play_generic.py does) + FollowCameraPerceiver
    # (core.grid_perceiver) + a locally-built sandbox (_gba_sandbox — mirrors _nds_sandbox()).
    # mgba is not importable on Windows; the emulator is only constructed lazily on first tool CALL.
    "kirby_gba": {"pkg": "core.perception_plugin", "plugin": "PerceptionPlugin",
                  "sandbox": "GBA_MCP_SANDBOX",
                  "perceiver_mod": "core.grid_perceiver", "perceiver": "FollowCameraPerceiver",
                  "rom": "roms/gba/Kirby - Nightmare in Dreamland (U) [!].gba",
                  "watch": {}},
    "emerald_gba": {"pkg": "core.perception_plugin", "plugin": "PerceptionPlugin",
                    "sandbox": "GBA_MCP_SANDBOX",
                    "perceiver_mod": "core.grid_perceiver", "perceiver": "FollowCameraPerceiver",
                    "rom": "roms/gba/Pokemon - Emerald Version (U).gba",
                    "watch": {}},
    # Generic GB/GBC lean world: any .gb/.gbc ROM via --rom, no game-specific plugin/oracle (probe-only —
    # watch={}, no oracle entries for generic worlds). Mirrors kirby_gba/emerald_gba's shared-plugin pattern,
    # GB family instead of GBA: PerceptionPlugin (default PyBoy emulator, no injection needed) +
    # FollowCameraPerceiver + a locally-built sandbox (_gb_generic_sandbox — no game package to source one from).
    "gb_generic": {"pkg": "core.perception_plugin", "plugin": "PerceptionPlugin",
                   "sandbox": "GB_GENERIC_MCP_SANDBOX",
                   "perceiver_mod": "core.grid_perceiver", "perceiver": "FollowCameraPerceiver",
                   "rom": "roms/PLACEHOLDER.gb",   # always override with --rom; no default GB ROM makes sense here
                   "watch": {}},
}
_GB_GENERIC_WORLDS = frozenset({"gb_generic"})   # game keys that need the locally-built generic-GB sandbox

_AGENT = "mcp-brain"
_PROTOCOL = "2024-11-05"
_MAX_LESSONS = 12
_GOTO_ADVERT = "Add 'GOTO: x y' to have a free pathfinder walk you to one."   # reworded for the MCP tool surface

_OBSERVE_TOOL = {
    "name": "observe",
    "description": ("Look at the dungeon RIGHT NOW without acting. Returns a pixels-derived SYMBOLIC view — "
                    "your dead-reckoned position, known walls here, open/unexplored directions, frontier "
                    "cells (x y), and your last move's outcome. This is your perception; reason from it. "
                    "Call it first, and after any move. (No screenshot unless the server was started with "
                    "--with-screenshot; the symbolic view is the brain's intended input.)"),
    "inputSchema": {"type": "object", "properties": {}},
}
_EXPLORE_TOOL = {
    "name": "explore",
    "description": ("Hand control to the FREE auto-explorer (System 1): it walks toward unexplored frontiers "
                    "on its own and returns control to you at a DECISION POINT — when it runs out of reachable "
                    "frontiers (or hits the step cap). This is the cost-first loop: cover routine ground with "
                    "this (one decision walks many tiles for free), and step in with press/goto only when it "
                    "reports it is stuck."),
    "inputSchema": {"type": "object",
                    "properties": {"max_steps": {"type": "integer", "minimum": 1, "maximum": 200}}},
}
_GOTO_TOOL = {
    "name": "goto",
    "description": ("Send yourself to a KNOWN map cell (use an (x, y) from observe's frontier list). A free "
                    "pathfinder (System 1) walks you there over several tiles and returns when you ARRIVE or "
                    "get stuck. Prefer this over pressing each tile yourself."),
    "inputSchema": {"type": "object",
                    "properties": {"x": {"type": "integer"}, "y": {"type": "integer"},
                                   "max_steps": {"type": "integer", "minimum": 1, "maximum": 200}},
                    "required": ["x", "y"]},
}
_REMEMBER_TOOL = {
    "name": "remember",
    "description": ("Record a short LESSON about how to play / use these tools (e.g. \"explore covers ground "
                    "for free — use it before pressing\", \"a BLOCKED move means a wall; turn instead\"). Your "
                    "lessons are shown back to you on every result, so you get better with experience THIS run. "
                    "Within-run only: forgotten when the session ends (that's intentional)."),
    "inputSchema": {"type": "object", "properties": {"lesson": {"type": "string"}}, "required": ["lesson"]},
}
# --- ADR-002 Phase D: the two foveated-region primitives a brain needs to HYPOTHESIZE "region R = my
# life" and ground it, without ever seeing a full-frame screenshot (that stays forbidden). Both take a
# pixel box on the CURRENT (already-observed) frame — no new emulator ticks, no state change, so they are
# NOT gateway/sandbox actions on the plugin; they read the last frame the World already has in hand.
_REGION_MAX_SIDE = 96          # source-pixel cap per side (loudly enforced) — a small hypothesized region,
                               # not a full-frame screenshot (160x144 GB screen).
_REGION_UPSCALE = 3            # nearest-neighbor upscale so an 8px GB font is legible to a vision model.

_READ_REGION_TOOL = {
    "name": "read_region",
    "description": ("Crop the CURRENT frame to a small pixel region (x0,y0)-(x1,y1) and return it as an "
                    "IMAGE (upscaled 3x, nearest-neighbor, so small text is legible). Use this to look "
                    "closely at ONE hypothesized region (e.g. a HUD box you think might be your life) — "
                    f"NOT a full screenshot. Capped at {_REGION_MAX_SIDE}x{_REGION_MAX_SIDE} source pixels; "
                    "a bigger request is rejected loudly with the cap in the error. The result reports "
                    "`step=<N>` — the world step of the frame shown; if you log a reading of it, copy "
                    "that exact step."),
    "inputSchema": {"type": "object",
                    "properties": {"x0": {"type": "integer", "minimum": 0},
                                   "y0": {"type": "integer", "minimum": 0},
                                   "x1": {"type": "integer", "minimum": 0},
                                   "y1": {"type": "integer", "minimum": 0}},
                    "required": ["x0", "y0", "x1", "y1"]},
}
_WHATS_CHANGED_TOOL = {
    "name": "whats_changed",
    "description": ("Compare a pixel region between the LAST TWO frames you observed (mean absolute "
                    "pixel difference) and report changed/unchanged with the score — a symbolic (no "
                    "image) way to check whether a hypothesized region's value just moved, e.g. while "
                    "you fight, without spending a read_region look every step. The result reports "
                    "`step=<N>` for the current frame compared."),
    "inputSchema": {"type": "object",
                    "properties": {"x0": {"type": "integer", "minimum": 0},
                                   "y0": {"type": "integer", "minimum": 0},
                                   "x1": {"type": "integer", "minimum": 0},
                                   "y1": {"type": "integer", "minimum": 0}},
                    "required": ["x0", "y0", "x1", "y1"]},
}
# Static action-tool specs (mirror the live plugin's tools()) so `tools/list` can answer WITHOUT booting
# the emulator — the emulator is built lazily on the first tool CALL (see main()). This keeps the
# `initialize`/`tools/list` handshake instant so the MCP client doesn't time out waiting on a boot.
#
# IMPORTANT: the button set is game-dependent.
#   GB worlds  (cave_noire, gauntlet, …) → _GB_BUTTONS (8 buttons; NO touch)
#   NDS worlds (nds)                     → _nds_emu_mod.BUTTONS (12 buttons) + _TOUCH_TOOL
#   GBA worlds (kirby_gba, emerald_gba)  → _gba_emu_mod.BUTTONS (10 buttons incl. l/r; NO touch)
#
# _static_tools(game) returns the correct per-game list; the `tools/list` handler calls it.
# assert_action_tools_fresh() does an EXACT-EQUALITY check (not intersection) so static==live is always true.

def _make_press_tools(buttons: tuple) -> list[dict]:
    """Return [press_button, press_sequence, wait] spec dicts for the given button set."""
    button_enum = {"type": "string", "enum": list(buttons)}
    return [
        {
            "name": "press_button",
            "description": "Move one tile (up/down/left/right) or act with `a` (interact / pick up).",
            "inputSchema": {"type": "object",
                            "properties": {"button": button_enum,
                                           "hold_frames": {"type": "integer", "minimum": 1, "maximum": 120}},
                            "required": ["button"]},
        },
        {
            "name": "press_sequence",
            "description": "Press several buttons in order (4-directional, no diagonals), e.g. [\"up\",\"up\",\"left\"].",
            "inputSchema": {"type": "object",
                            "properties": {"buttons": {"type": "array", "items": button_enum, "maxItems": 16}},
                            "required": ["buttons"]},
        },
        {
            "name": "wait",
            "description": "Advance the game without input — let an animation finish.",
            "inputSchema": {"type": "object",
                            "properties": {"frames": {"type": "integer", "minimum": 1, "maximum": 600}},
                            "required": []},
        },
    ]

_TOUCH_TOOL = {
    "name": "touch",
    "description": ("Tap the NDS bottom (touch) screen at pixel coordinates (x, y). "
                    "x: 0–255 (left to right), y: 0–191 (top to bottom). "
                    "Prefer touch_target(id) when the target is in observe()'s touch_targets; use raw "
                    "coords only for targets the detector missed. "
                    "Issues a stylus-down at (x, y), holds for a few ticks, then releases."),
    "inputSchema": {"type": "object",
                    "properties": {"x": {"type": "integer", "minimum": 0, "maximum": 255},
                                   "y": {"type": "integer", "minimum": 0, "maximum": 191},
                                   "hold_frames": {"type": "integer", "minimum": 1, "maximum": 60}},
                    "required": ["x", "y"]},
}

_TOUCH_TARGET_TOOL = {
    "name": "touch_target",
    "description": ("Tap the id-th detected touch target from observe()'s touch_targets list "
                    "(0-based, area-sorted; 0 = largest). Preferred over touch(x,y) — no raw coordinates."),
    "inputSchema": {"type": "object",
                    "properties": {"id": {"type": "integer", "minimum": 0},
                                   "hold_frames": {"type": "integer", "minimum": 1, "maximum": 60}},
                    "required": ["id"]},
}

# Pre-built per-world action-tool lists (no touch on GB/GBA; touch/touch_target + NDS buttons on NDS).
_GB_ACTION_TOOLS = _make_press_tools(_GB_BUTTONS)
_NDS_ACTION_TOOLS = [*_make_press_tools(_nds_emu_mod.BUTTONS), _TOUCH_TOOL, _TOUCH_TARGET_TOOL]
_GBA_ACTION_TOOLS = _make_press_tools(_gba_emu_mod.BUTTONS)


def _static_tools(game: str) -> list[dict]:
    """Return the correct tools/list response for `game` WITHOUT booting the emulator."""
    nav = [_OBSERVE_TOOL, _EXPLORE_TOOL, _GOTO_TOOL, _REMEMBER_TOOL]
    if game in _REGION_TOOL_WORLDS:
        nav = [*nav, _READ_REGION_TOOL, _WHATS_CHANGED_TOOL]
    if game in _NDS_WORLDS:
        return [*nav, *_NDS_ACTION_TOOLS]
    if game in _GBA_WORLDS:
        return [*nav, *_GBA_ACTION_TOOLS]
    return [*nav, *_GB_ACTION_TOOLS]


def assert_action_tools_fresh(plugin, game: str) -> None:
    """Lazy-boot safety net: `tools/list` answers from _static_tools() *before* the plugin is booted,
    so the static action specs could silently drift from what the plugin actually accepts.

    Invariant (EXACT EQUALITY): the set of static action tools must equal the live plugin's tools
    exactly — same names, same schemas. Fail LOUD rather than silently mislead the brain."""
    if game in _NDS_WORLDS:
        action_tools = _NDS_ACTION_TOOLS
    elif game in _GBA_WORLDS:
        action_tools = _GBA_ACTION_TOOLS
    else:
        action_tools = _GB_ACTION_TOOLS
    static = {t["name"]: t["inputSchema"] for t in action_tools}
    live = {s.name: s.schema for s in plugin.tools(_AGENT)}
    # Exact equality: static action tools == live plugin tools (no extras allowed on either side).
    drift = {nm: (static[nm], live[nm]) for nm in static if nm in live and static[nm] != live[nm]}
    missing_from_live = set(static) - set(live)
    extra_in_live = set(live) - set(static)
    if drift or missing_from_live or extra_in_live:
        raise SystemExit(
            "world_mcp static action tools are STALE vs the live plugin — update to match.\n"
            f"  schema drift: {drift}\n"
            f"  in static but not live: {missing_from_live}\n"
            f"  in live but not static: {extra_in_live}"
        )


def _send(msg: dict) -> None:
    _OUT.write(json.dumps(msg) + "\n")
    _OUT.flush()


class World:
    """One live perception-only session for the chosen `--game`, driven through the Gateway + plugin."""

    def __init__(self, args) -> None:
        spec = GAMES[args.game]
        pkg = importlib.import_module(spec["pkg"])
        Plugin = getattr(pkg, spec["plugin"])
        # Resolve sandbox: NDS/GBA/generic-GB worlds use a locally-built Allowlist (no shared module);
        # per-game GB worlds get their sandbox from the game's own package (e.g. CAVE_NOIRE_SANDBOX).
        if args.game in _NDS_WORLDS:
            sandbox = _nds_sandbox()
        elif args.game in _GBA_WORLDS:
            sandbox = _gba_sandbox()
        elif args.game in _GB_GENERIC_WORLDS:
            sandbox = _gb_generic_sandbox()
        else:
            sandbox = getattr(pkg, spec["sandbox"])
        Perceiver = getattr(importlib.import_module(spec["perceiver_mod"]), spec["perceiver"])
        self.with_screenshot = bool(args.with_screenshot)
        self.keep_frames = bool(getattr(args, "keep_frames", False))   # --keep-frames: KEEP per-step PNGs as logs
        header = ("Top-down exploration. Perception is approximate; a screenshot is attached."
                  if self.with_screenshot else
                  "Top-down exploration. You perceive only this symbolic view — reason from it.")
        record_path = os.path.join(args.out, "session.mp4") if args.record else None
        os.makedirs(args.out, exist_ok=True)   # the recorder opens <out>/session.mp4 before the plugin makedirs
        rom_path = args.rom or spec["rom"]
        # --rom must match --game's family: the extension dispatch below and the game-keyed
        # sandbox/static-tools would otherwise disagree and die later with a misleading
        # "static tools are STALE" SystemExit from assert_action_tools_fresh.
        ext = "nds" if rom_path.lower().endswith(".nds") else ("gba" if rom_path.lower().endswith(".gba") else "gb")
        fam = "nds" if args.game in _NDS_WORLDS else ("gba" if args.game in _GBA_WORLDS else "gb")
        if ext != fam:
            raise SystemExit(f"--game {args.game} is a {fam.upper()} world but ROM {rom_path!r} "
                             f"looks {ext.upper()} — mismatched --rom/--game?")
        if args.record and ext != "gb":
            raise SystemExit("--record is not supported for GBA/NDS worlds yet: recording threads only "
                             "through the default PyBoy emulator path (core/perception_plugin.py); "
                             "injected GBA/NDS emulators have no recorder. Use --keep-frames instead "
                             "(per-step PNGs are plugin-side and work for any emulator).")
        # Emulator dispatch by ROM extension (mirrors play_generic.py:75-77). Imports are LAZY so a
        # GB-only session never pays the mgba/py-desmume import cost (mgba isn't importable on Windows;
        # py-desmume may be absent in some envs) — the base PyBoy path below is unchanged.
        emulator = None
        if rom_path.lower().endswith(".nds"):
            from core.nds_emulator import DeSmuMEEmulator
            emulator = DeSmuMEEmulator(rom_path, headless=True)
        elif rom_path.lower().endswith(".gba"):
            from core.gba_emulator import GBAEmulator
            emulator = GBAEmulator(rom_path)
        self.plugin = Plugin(rom_path=rom_path, emulator=emulator, out_dir=args.out, headless=True,
                             init_state=args.init_state, perceiver=Perceiver(),
                             watch=spec["watch"],   # RAM -> oracle.jsonl ONLY, never the wire (incl. the hp oracle)
                             render_header=header, record_path=record_path)
        # --keep-frames: PATIENCE's intermediate auto-advance frames then get unique PNG paths
        # (audit logs) instead of overwriting one temp path per observe.
        self.plugin.keep_frames = self.keep_frames
        self.gw = Gateway(self.plugin, sandbox)
        self.explore = ExploreBrain(_AGENT, single_step=True)   # turn-based / one press = one move
        # within-run self-improvement state (discarded at process end — the learning-boundary law)
        self.lessons: list[str] = []
        self.decisions = 0       # your LLM wakes (press/goto/explore) — the cost the north star keeps LOW
        self.auto_tiles = 0      # tiles the free System-1 autopilot walked for you (free; NOT the cost metric)
        self.visited = 0         # cells explored so far (progress); improvement = more cells per decision (wake)
        self.region_tools = args.game in _REGION_TOOL_WORLDS   # ADR-002 Phase D: read_region/whats_changed
        self._frame_hist: list = []   # last <=2 observed frames (numpy HxWxC), for whats_changed's frame-diff

    def tools(self) -> list[dict]:
        action = [{"name": s.name, "description": s.description, "inputSchema": s.schema}
                  for s in self.plugin.tools(_AGENT)]
        nav = [_OBSERVE_TOOL, _EXPLORE_TOOL, _GOTO_TOOL, _REMEMBER_TOOL]
        if self.region_tools:
            nav = [*nav, _READ_REGION_TOOL, _WHATS_CHANGED_TOOL]
        return [*nav, *action]

    # -- self-improvement preamble (re-injected every turn) --------------------

    def _preamble(self) -> str:
        lines: list[str] = []
        if self.decisions:
            eff = self.visited / self.decisions
            lines.append(f"Cost so far: {self.decisions} decision(s) — your LLM wakes, the thing to keep LOW. "
                         f"Progress: {self.visited} cells explored = {eff:.1f} per decision (System 1 "
                         f"auto-walked {self.auto_tiles} tiles free). Improve by covering more NEW ground per "
                         f"decision: delegate travel to explore/goto, and don't spend a wake that gets nothing.")
        if self.lessons:
            lines.append("Your notes this run (UNVERIFIED — your own guesses, re-shown each turn; the loop "
                         "can't check them, so a wrong one will be repeated back — fix it with a new `remember`):")
            lines.extend(f"  - {lsn}" for lsn in self.lessons)
        return "\n".join(lines)

    # -- observation rendering -------------------------------------------------

    @staticmethod
    def _fix_text(text: str) -> str:
        return text.replace(_GOTO_ADVERT,
                            "Call the `goto` tool with one of these (x, y), or `explore` to auto-explore.")

    def _drop_frame(self, obs) -> None:
        if self.keep_frames:                            # --keep-frames: log every per-step PNG (oracle pairs to it)
            return
        p = (obs.data or {}).get("screen_path") or ""   # else don't accumulate frame debris
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

    def _content(self, obs) -> list[dict]:
        sm = (obs.data or {}).get("spatial_memory") or {}
        if isinstance(sm.get("visited"), int):
            self.visited = sm["visited"]        # track progress (cells explored) for the cost-per-progress signal
        if self.region_tools:
            self._track_frame()
        content: list[dict] = [{"type": "text", "text": self._fix_text(obs.text)}]
        p = (obs.data or {}).get("screen_path") or ""
        if p and os.path.exists(p):
            if self.with_screenshot:
                with open(p, "rb") as f:
                    content.append({"type": "image", "data": base64.b64encode(f.read()).decode(),
                                    "mimeType": "image/png"})
            if not self.keep_frames:
                try:
                    os.remove(p)
                except OSError:
                    pass
        return content

    # -- ADR-002 Phase D: foveated region primitives (read_region / whats_changed) --------------------------
    # Both read the CURRENT frame already in the emulator (no new ticks, no state change) — they are NOT
    # gateway/sandbox actions; they piggyback on whatever frame the last observe/action already produced.

    def _track_frame(self) -> None:
        """Keep the last <=2 observed (step, frame) pairs so whats_changed can diff them and both region
        tools can report WHICH world step the frame belongs to. `step` is the plugin's _obs_count at
        capture time — observe() increments _obs_count and then _log_oracle writes that same value as the
        oracle.jsonl row's "step", and _track_frame runs right after that observe returns, so this step is
        EXACTLY the oracle row logged for the frame being read (the scorer aligns on it; no wall clocks)."""
        try:
            frame = self.plugin.emu.screen_ndarray()
        except Exception:
            return
        step = int(getattr(self.plugin, "_obs_count", 0))
        self._frame_hist.append((step, frame))
        del self._frame_hist[:-2]

    @staticmethod
    def _validate_region(x0: int, y0: int, x1: int, y1: int, frame) -> str | None:
        """Return an error string if the region is out of bounds or exceeds the size cap; else None."""
        h, w = frame.shape[0], frame.shape[1]
        if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
            return (f"region ({x0},{y0})-({x1},{y1}) out of bounds for a {w}x{h} frame "
                    "(need 0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height)")
        rw, rh = x1 - x0, y1 - y0
        if rw > _REGION_MAX_SIDE or rh > _REGION_MAX_SIDE:
            return (f"region {rw}x{rh} exceeds the {_REGION_MAX_SIDE}x{_REGION_MAX_SIDE} source-pixel cap "
                    "— hypothesize a SMALLER region, not a full-frame screenshot")
        return None

    def _read_region(self, args: dict) -> list[dict]:
        try:
            x0, y0, x1, y1 = (int(args["x0"]), int(args["y0"]), int(args["x1"]), int(args["y1"]))
        except (KeyError, TypeError, ValueError):
            return [{"type": "text", "text": "read_region needs integer x0, y0, x1, y1."}]
        if not self._frame_hist:
            self._track_frame()
        if not self._frame_hist:
            return [{"type": "text", "text": "read_region: no frame available yet — call observe first."}]
        step, frame = self._frame_hist[-1]
        err = self._validate_region(x0, y0, x1, y1, frame)
        if err:
            return [{"type": "text", "text": f"read_region error: {err}"}]
        crop = frame[y0:y1, x0:x1]
        from PIL import Image
        im = Image.fromarray(crop).convert("RGB")
        im = im.resize((im.width * _REGION_UPSCALE, im.height * _REGION_UPSCALE), Image.NEAREST)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        png_b64 = base64.b64encode(buf.getvalue()).decode()
        return [{"type": "text",
                 "text": f"[read_region step={step} ({x0},{y0})-({x1},{y1}), upscaled {_REGION_UPSCALE}x — "
                         f"when logging a reading of this image, use this exact step: "
                         f"HYP region=({x0},{y0},{x1},{y1}) step={step} reading=<value>]"},
                {"type": "image", "data": png_b64, "mimeType": "image/png"}]

    def _whats_changed(self, args: dict) -> list[dict]:
        try:
            x0, y0, x1, y1 = (int(args["x0"]), int(args["y0"]), int(args["x1"]), int(args["y1"]))
        except (KeyError, TypeError, ValueError):
            return [{"type": "text", "text": "whats_changed needs integer x0, y0, x1, y1."}]
        if len(self._frame_hist) < 2:
            return [{"type": "text",
                    "text": "whats_changed: need two observed frames yet (only have "
                            f"{len(self._frame_hist)}) — call observe/press again first."}]
        (prev_step, prev), (curr_step, curr) = self._frame_hist[-2], self._frame_hist[-1]
        err = self._validate_region(x0, y0, x1, y1, curr)
        if err:
            return [{"type": "text", "text": f"whats_changed error: {err}"}]
        import numpy as np
        a = prev[y0:y1, x0:x1].astype(np.float32)
        b = curr[y0:y1, x0:x1].astype(np.float32)
        mad = float(np.mean(np.abs(a - b)))
        changed = mad >= 2.0   # small dead-zone against emulator/encoding noise on a static region
        return [{"type": "text",
                "text": f"[whats_changed step={curr_step} (vs step={prev_step}) ({x0},{y0})-({x1},{y1}): "
                        f"{'changed' if changed else 'unchanged'} (mean-abs-diff={mad:.2f})]"}]

    # -- the free System-1 autopilot (dual-process: wake the brain only at a decision) -----------------------

    def _run_autopilot(self, target, max_steps: int) -> tuple[int, str]:
        self.plugin._extra_context = {}   # clear stale slot from a previous call
        steps = 0
        prev_pose = None
        same_pose_count = 0
        flagged: set = set()
        for _ in range(max(1, min(int(max_steps), 200))):
            obs = self.plugin.observe(_AGENT)
            self._drop_frame(obs)
            if target is not None:
                pose = (obs.data.get("pose") or {}).get("value")
                if pose is not None and list(pose) == target:
                    return steps, "arrived at the target cell"
            call = self.explore.decide(obs, self.plugin.tools(_AGENT), {"goto": target})
            if call is None:
                # No reachable frontier: if we have a target, mark it as a dead frontier
                # so the perceiver prunes it from the frontier list on the next observe.
                if target is not None:
                    t = tuple(target)
                    if t not in flagged:
                        flagged.add(t)
                        self.plugin._extra_context["goto_fails"] = [target]
                return steps, ("blocked / no path to the target" if target is not None
                               else "out of reachable frontiers — your decision")
            self.gw.execute(call)
            steps += 1
            # Detect pose-frozen runs (all steps but cursor never moves) → mark target as dead.
            pose = (obs.data.get("pose") or {}).get("value")
            if pose is not None and list(pose) == (prev_pose or []):
                same_pose_count += 1
            else:
                same_pose_count = 0
                prev_pose = list(pose) if pose is not None else prev_pose
            if target is not None and same_pose_count >= 4:
                t = tuple(target)
                if t not in flagged:
                    flagged.add(t)
                    self.plugin._extra_context["goto_fails"] = [target]
        return steps, "reached the step cap"

    # -- dispatch (single return; the self-improvement preamble is prepended to every result) ----------------

    def call(self, name: str, args: dict) -> list[dict]:
        args = args or {}
        if name == "observe":
            body = self._content(self.plugin.observe(_AGENT))
        elif name == "remember":
            lesson = str(args.get("lesson", "")).strip()
            if lesson and lesson not in self.lessons:
                self.lessons.append(lesson)
                del self.lessons[:-_MAX_LESSONS]
            body = [{"type": "text", "text": f"Noted ({len(self.lessons)} lesson(s) this run)."},
                    *self._content(self.plugin.observe(_AGENT))]
        elif name == "explore":
            self.decisions += 1
            steps, why = self._run_autopilot(None, args.get("max_steps", 40))
            self.auto_tiles += steps
            body = [{"type": "text", "text": f"[explore -> stopped after {steps} autopilot step(s): {why}]"},
                    *self._content(self.plugin.observe(_AGENT))]
        elif name == "goto":
            if "x" not in args or "y" not in args:
                return [{"type": "text", "text": "goto needs integer x and y (from observe's frontier list)."}]
            target = [int(args["x"]), int(args["y"])]
            self.decisions += 1
            steps, why = self._run_autopilot(target, args.get("max_steps", 60))
            self.auto_tiles += steps
            body = [{"type": "text", "text": f"[goto {tuple(target)} -> {why} after {steps} step(s)]"},
                    *self._content(self.plugin.observe(_AGENT))]
        elif name == "read_region" and self.region_tools:
            body = self._read_region(args)
        elif name == "whats_changed" and self.region_tools:
            body = self._whats_changed(args)
        else:
            # a direct action (press_button / press_sequence / wait / touch / touch_target): route through the gateway.
            if name in ("press_button", "press_sequence", "wait", "touch", "touch_target"):
                self.decisions += 1          # a real brain action is a wake; an unknown tool name is not counted
            res = self.gw.execute(ToolCall(tool=name, args=args, agent_id=_AGENT, call_id=str(uuid.uuid4())))
            head = {"type": "text", "text": f"[{name} -> ok={res.ok}" + ("" if res.ok else f", {res.error}") + "]"}
            body = [head, *self._content(self.plugin.observe(_AGENT))]

        pre = self._preamble()
        return ([{"type": "text", "text": pre}, *body] if pre else body)


def main() -> int:
    ap = argparse.ArgumentParser(description="MCP (stdio) server exposing a Game Boy world as tools.")
    ap.add_argument("--game", default="cave_noire", choices=sorted(GAMES),  # noqa: GAMES includes "nds"
                    help="which world to serve (registry in world_mcp.py)")
    ap.add_argument("--rom", default=None, help="ROM path; defaults to the chosen game's ROM")
    ap.add_argument("--init-state", default=None, help="gameplay save-state to boot from")
    ap.add_argument("--out", default="runs/mcp_world")
    ap.add_argument("--record", action="store_true",
                    help="record an MP4 of the session to <out>/session.mp4 (needs imageio + imageio-ffmpeg)")
    ap.add_argument("--with-screenshot", action="store_true",
                    help="DEBUG ONLY: also return the raw frame image. Off by default — the brain is meant to "
                         "reason from the symbolic view (the perception seam), not read pixels.")
    ap.add_argument("--keep-frames", action="store_true",
                    help="KEEP every per-step frame PNG on disk (default drops them as debris). Max logging: each "
                         "PNG pairs with its oracle.jsonl step (RAM truth) + the symbolic view the brain saw.")
    args = ap.parse_args()

    # LAZY: do NOT boot the emulator here. `initialize`/`tools/list` must answer instantly or the MCP client
    # times out the startup handshake and marks the server "not connected". The World (PyBoy) is built on the
    # first tool CALL, which the client waits on as a normal request (no startup timeout).
    _world: list = [None]
    def world():
        if _world[0] is None:
            w = World(args)
            assert_action_tools_fresh(w.plugin, args.game)   # catch static-tool drift on first boot (exact equality)
            _world[0] = w
        return _world[0]

    # The MCP client (claude) usually TERMINATES the server (SIGTERM) instead of closing stdin (EOF), which
    # would skip the finalize below and leave the --record MP4 unmuxed (a stray .video.mp4, audio lost).
    # Finalize on SIGTERM/SIGINT too so the recording is always closed + audio-muxed before exit.
    def _shutdown(*_):
        if _world[0] is not None:
            try:
                _world[0].plugin.close()
            except Exception:
                pass
        raise SystemExit(0)
    for _sig in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGINT", None)):
        if _sig is not None:
            try:
                signal.signal(_sig, _shutdown)
            except (ValueError, OSError):        # not in main thread / unsupported -> rely on stdin-EOF
                pass

    for line in sys.stdin:                       # newline-delimited JSON-RPC (the MCP stdio transport)
        if line and ord(line[0]) == 0xFEFF:      # tolerate a leading BOM on the first message
            line = line[1:]
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        mid, method = msg.get("id"), msg.get("method")

        if mid is None:                          # a notification (e.g. notifications/initialized) — never reply
            continue
        if method == "initialize":
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": _PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ai-pokemon-red-world", "version": "0.3.0"}}})
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": mid, "result": {"tools": _static_tools(args.game)}})
        elif method == "tools/call":
            p = msg.get("params") or {}
            try:
                content = world().call(p.get("name", ""), p.get("arguments") or {})
                _send({"jsonrpc": "2.0", "id": mid, "result": {"content": content}})
            except Exception as e:               # a tool error is an observation, not a crash (invariant 4)
                _send({"jsonrpc": "2.0", "id": mid,
                       "result": {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True}})
        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": mid, "result": {}})
        elif method is None:
            _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32600, "message": "Invalid Request: no method"}})
        else:
            _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}})

    # client disconnected (stdin EOF) -> stop the emulator and FINALIZE the --record MP4 (imageio needs close()).
    if _world[0] is not None:
        try:
            _world[0].plugin.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
