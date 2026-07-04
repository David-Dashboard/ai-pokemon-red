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
from typing import Optional

import numpy as np

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
# MiniWoB++ computer-use worlds: a task-per-entry registry (mirrors the rest of GAMES — one key per
# concrete playable task, e.g. "kirby_gba" is one ROM) rather than a generic "--game miniwob --task foo"
# passthrough. Reasons: (1) --game's argparse `choices=` validation stays uniform and fails loud on typos
# instead of accepting an arbitrary --task string; (2) tools/list can answer per-task without booting a
# browser, same as every other world here; (3) a MiniWoB task IS the "ROM" for this family — one task,
# one fixed action surface, matches the existing one-entry-per-playable-thing shape exactly.
_MINIWOB_WORLDS = frozenset({"miniwob_click_button", "miniwob_click_checkboxes", "miniwob_focus_text"})
_MINIWOB_TASK_NAMES = {"miniwob_click_button": "click-button",
                       "miniwob_click_checkboxes": "click-checkboxes",
                       "miniwob_focus_text": "focus-text"}
# ViZDoom GATE-3D world: a standalone session class (DoomDtcSession below), same shape as
# MiniWobSession — NOT core.gateway.Gateway/GamePlugin (no tile grid, no press_button vocabulary; a
# 3D FPS's action surface is turn/attack). One entry, one scenario (dtc_gate.cfg per AMENDMENT A1.3) —
# mirrors the miniwob family's one-task-per-key registry shape rather than a generic --scenario flag.
_VIZDOOM_WORLDS = frozenset({"doom_dtc_gate"})
# ARC-AGI-3 world: a standalone session class (ArcAgi3Session below), same shape as MiniWobSession/
# DoomDtcSession — NOT core.gateway.Gateway/GamePlugin (no ROM/emulator concept at all; the "screen"
# is a native int[][] grid over a REST API). --game arcagi3 --arc-game <game_id> selects the actual
# ARC game_id at launch (unlike the miniwob/doom families, which pin one task/scenario per registry
# key) because ARC-AGI-3's game catalog is queried live from GET /api/games, not a fixed local list —
# see runs/arcagi3_probe/PROBE_REPORT.md.
_ARCAGI3_WORLDS = frozenset({"arcagi3"})
# Worlds that get the foveated region tools (ADR-002 Phase D probe: read_region + whats_changed). Scoped
# to cave_noire (the gate world) + its A/B control + the other lean GB world (gauntlet), plus
# kirby_dreamland (the entity-gate v2 port target — needs foveation for ENT boxes + NEAR corroboration,
# same as cave_noire) — NOT the NDS/GBA worlds (no proven need there yet) and NOT pokemon_red (its own
# perceiver/prompt already ships screen_text).
_REGION_TOOL_WORLDS = frozenset({"cave_noire", "cave_noire_baseline", "gauntlet", "kirby_dreamland"})

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
    # MiniWoB++ computer-use worlds: no pkg/plugin/rom/perceiver (no PyBoy/DeSmuME/mgba emulator, no
    # GamePlugin/Gateway — MiniWobSession below is a standalone dispatch path, not core.gateway.Gateway).
    # "watch" stays {} structurally (mirrors the GBA worlds' no-oracle shape) — MiniWob's real oracle is
    # the env's reward + dom_elements, which MiniWobSession logs straight to oracle.jsonl itself and NEVER
    # exposes as a `watch` dict (the RAM-address shape doesn't apply to a browser task).
    "miniwob_click_button": {"task": _MINIWOB_TASK_NAMES["miniwob_click_button"], "watch": {}},
    "miniwob_click_checkboxes": {"task": _MINIWOB_TASK_NAMES["miniwob_click_checkboxes"], "watch": {}},
    "miniwob_focus_text": {"task": _MINIWOB_TASK_NAMES["miniwob_focus_text"], "watch": {}},
    # Generic GB/GBC lean world: any .gb/.gbc ROM via --rom, no game-specific plugin/oracle (probe-only —
    # watch={}, no oracle entries for generic worlds). Mirrors kirby_gba/emerald_gba's shared-plugin pattern,
    # GB family instead of GBA: PerceptionPlugin (default PyBoy emulator, no injection needed) +
    # FollowCameraPerceiver + a locally-built sandbox (_gb_generic_sandbox — the _GB_GENERIC_WORLDS branch in
    # World.__init__ short-circuits the "sandbox" key lookup, so this entry deliberately has none).
    "gb_generic": {"pkg": "core.perception_plugin", "plugin": "PerceptionPlugin",
                   "perceiver_mod": "core.grid_perceiver", "perceiver": "FollowCameraPerceiver",
                   "rom": "roms/PLACEHOLDER.gb",   # always override with --rom; no default GB ROM makes sense here
                   "watch": {}},
    # Kirby's Dream Land: entity-grounding gate v2 port target (Cave Noire -> Kirby, per
    # runs/entity_world_port_findings.md). Same shared-plugin pattern as gb_generic (no game-specific
    # package exists for Kirby) — PerceptionPlugin + FollowCameraPerceiver + the generic-GB sandbox.
    # hp @ 0xD086 is a PLAIN integer 0-5 (1 unit per HUD pip), NOT BCD — verified by a free offline probe
    # (5/5 -> 4/5 -> 3/5 matched the HUD exactly across two contact-damage hits, continuous process, no
    # save/load in between). score_entity_gate_v2.py's _bcd() decode ((b>>4)*10 + (b&0xF)) is the IDENTITY
    # function for any raw byte in 0-9 (high nibble 0 at this range), so the v2 scorer works UNCHANGED on
    # this plain-int oracle — do not touch the scorer, this is a documentation note only.
    "kirby_dreamland": {"pkg": "core.perception_plugin", "plugin": "PerceptionPlugin",
                        "perceiver_mod": "core.grid_perceiver", "perceiver": "FollowCameraPerceiver",
                        "rom": "roms/Kirby's Dream Land (USA, Europe).gb",
                        "watch": {"hp": 0xD086}},
    # GATE-3D-A1 (reports/2026-07-04-vizdoom-3d-floor-design.md + AMENDMENT A1): ViZDoom
    # defend_the_center, symbolic-only seam (P1 yaw + P2 movers + episode status; no screenshot, no
    # game variables on the wire). No pkg/plugin/rom entry — DoomDtcSession below is a standalone
    # dispatch path (mirrors MiniWobSession), not core.gateway.Gateway. "watch" stays {} structurally
    # (mirrors the miniwob/GBA no-oracle shape); the REAL oracle (HEALTH/AMMO2/KILLCOUNT) is
    # DoomDtcSession's own oracle.jsonl writer, never a `watch` RAM-address dict (no RAM here at all).
    "doom_dtc_gate": {"cfg": "scenarios/dtc_gate.cfg", "watch": {}},
    # ARC-AGI-3 (docs.arcprize.org): a standalone session class (ArcAgi3Session below), no pkg/plugin/
    # rom/perceiver — the "watch" dict stays {} structurally (mirrors miniwob/doom's no-RAM-oracle
    # shape); the real oracle (levels_completed/win_levels/state) is ArcAgi3Session's own
    # oracle.jsonl writer, never a `watch` RAM-address dict (there is no RAM here, only a REST API).
    # The actual ARC game_id is a launch-time flag (--arc-game), not baked into this registry entry,
    # since ARC-AGI-3's game catalog is queried live (GET /api/games), unlike the miniwob/doom
    # families' one-task-per-key registry shape.
    "arcagi3": {"watch": {}},
}
_GB_GENERIC_WORLDS = frozenset({"gb_generic", "kirby_dreamland"})   # game keys needing the generic-GB sandbox

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

# --- MiniWoB++ computer-use tool specs. Same observe/read_region/whats_changed NAMES and meaning as the
# GB region-tool worlds (a symbolic, no-DOM view + a foveated crop) — there is no tile grid in a browser
# task. click/type_text/press_key/reset_episode replace press_button et al: a browser task's action
# vocabulary is mouse+keyboard, not a fixed game-button set. NOTE (PR #64 review): observe deliberately
# ships NO entity list — core/blob.py's RollingBg segmentation is motion-based (frame-vs-background diff)
# and returns zero foreground on a static UI, so a blob list here was structurally dead code. Static-UI
# segmentation is a NAMING-layer problem (what counts as a widget on a still frame), not a motion one —
# deferred; until then the brain sees the page by tiling read_region crops (live-validated workable).
_MINIWOB_OBSERVE_TOOL = {
    "name": "observe",
    "description": ("Look at the task page RIGHT NOW without acting. Returns the task instruction "
                    "(utterance), the screen size, and the episode status (in progress / over). To SEE "
                    "the page, tile read_region crops over it and read the upscaled images — there is "
                    "no entity list and no DOM. Call observe first, and after any click/type/key."),
    "inputSchema": {"type": "object", "properties": {}},
}
_MINIWOB_CLICK_TOOL = {
    "name": "click",
    "description": ("Click at pixel (x, y) on the task page. (x, y) must be inside the real clickable "
                    "viewport (x 0-159, y 0-176): the page is 210px tall but the headless browser can "
                    "only click down to y=176, so a click outside that band is REJECTED with an error "
                    "(never silently moved) — anything rendered below y=176 is unreachable."),
    "inputSchema": {"type": "object",
                    "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                    "required": ["x", "y"]},
}
_MINIWOB_TYPE_TOOL = {
    "name": "type_text",
    "description": "Type text into whatever element currently has focus (click it first to focus it).",
    "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
}
_MINIWOB_KEY_TOOL = {
    "name": "press_key",
    "description": "Press a single keyboard key (e.g. \"Enter\", \"Tab\", \"ArrowDown\") on the task page.",
    "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
}
_MINIWOB_RESET_TOOL = {
    "name": "reset_episode",
    "description": "Start a fresh episode of this task (new random instance of the same task template).",
    "inputSchema": {"type": "object", "properties": {}},
}
_MINIWOB_READ_REGION_TOOL = {
    "name": "read_region",
    "description": ("Crop the CURRENT screenshot to a small pixel region (x0,y0)-(x1,y1) and return it "
                    f"as an IMAGE (upscaled {_REGION_UPSCALE}x, nearest-neighbor). Use this to look "
                    "closely at one hypothesized region, NOT a full screenshot. Capped at "
                    f"{_REGION_MAX_SIDE}x{_REGION_MAX_SIDE} source pixels."),
    "inputSchema": {"type": "object",
                    "properties": {"x0": {"type": "integer", "minimum": 0},
                                   "y0": {"type": "integer", "minimum": 0},
                                   "x1": {"type": "integer", "minimum": 0},
                                   "y1": {"type": "integer", "minimum": 0}},
                    "required": ["x0", "y0", "x1", "y1"]},
}
_MINIWOB_WHATS_CHANGED_TOOL = {
    "name": "whats_changed",
    "description": ("Compare a pixel region between the LAST TWO screenshots you observed (mean absolute "
                    "pixel difference) and report changed/unchanged with the score."),
    "inputSchema": {"type": "object",
                    "properties": {"x0": {"type": "integer", "minimum": 0},
                                   "y0": {"type": "integer", "minimum": 0},
                                   "x1": {"type": "integer", "minimum": 0},
                                   "y1": {"type": "integer", "minimum": 0}},
                    "required": ["x0", "y0", "x1", "y1"]},
}
_MINIWOB_ACTION_TOOLS = [_MINIWOB_CLICK_TOOL, _MINIWOB_TYPE_TOOL, _MINIWOB_KEY_TOOL, _MINIWOB_RESET_TOOL]

# --- ViZDoom GATE-3D-A1 tool specs (design doc S3.2 + AMENDMENT A1.3). Symbolic-only observe (P1 yaw +
# P2 movers + episode status; NO screenshot, NO game variables — the no-leak law). turn_left/turn_right/
# attack take NO tics parameter (every action-step is tics=4 FIXED, the gate's action-grain equivalence
# pin) but DO take `repeat: 1..10` (a System-1 grain so the brain's decision budget isn't consumed by
# mechanical repetition, A1.3) — each of the up-to-10 sub-steps still individually computes+logs P1
# world-side (the PR #73 review finding this doc cites: the brain cannot influence when P1 runs).
_DOOM_OBSERVE_TOOL = {
    "name": "observe",
    "description": ("Look at the arena RIGHT NOW without acting. Returns your ego-rotation reading "
                    "(turning left/right/none, or null if it can't tell), a list of moving-thing "
                    "azimuths (null if you're not confidently stationary — turning closes this "
                    "channel; [] means confidently nothing is moving), and episode status. No "
                    "screenshot, no game stats — reason from this symbolic view only."),
    "inputSchema": {"type": "object", "properties": {}},
}


def _doom_action_tool(name: str, verb: str) -> dict:
    return {
        "name": name,
        "description": (f"{verb} — executes with a fixed action grain (no `tics` parameter here); "
                        "optionally `repeat` the SAME action several times in one call (System-1 "
                        "steps, does not cost you an extra decision) before returning your next "
                        "observation."),
        "inputSchema": {"type": "object",
                        "properties": {"repeat": {"type": "integer", "minimum": 1, "maximum": 10}},
                        "required": []},
    }


_DOOM_TURN_LEFT_TOOL = _doom_action_tool("turn_left", "Turn left")
_DOOM_TURN_RIGHT_TOOL = _doom_action_tool("turn_right", "Turn right")
_DOOM_ATTACK_TOOL = _doom_action_tool("attack", "Fire your weapon")
_DOOM_NEW_EPISODE_TOOL = {
    "name": "new_episode",
    "description": ("Advance to the NEXT pinned seed's episode. Calling this before the current "
                    "episode ends ABANDONS it — that seed's attempt is recorded as over right now "
                    "(one attempt per seed; no re-rolling a bad start)."),
    "inputSchema": {"type": "object", "properties": {}},
}
_DOOM_ACTION_TOOLS = [_DOOM_TURN_LEFT_TOOL, _DOOM_TURN_RIGHT_TOOL, _DOOM_ATTACK_TOOL, _DOOM_NEW_EPISODE_TOOL]


def _vizdoom_static_tools() -> list[dict]:
    """tools/list response for doom_dtc_gate — identical across (there's only one scenario)."""
    return [_DOOM_OBSERVE_TOOL, _REMEMBER_TOOL, *_DOOM_ACTION_TOOLS]


# --- ARC-AGI-3 tool specs (runs/arcagi3_probe/PROBE_REPORT.md "Seam sketch"). observe returns the
# CURRENT grid rendered as compact text (one char/cell) + a diff-summary vs the previous grid +
# available_actions + step count — the grid IS the screen here (discrete cells), so full-grid observe
# is seam-legitimate (unlike GB/GBA/NDS pixel screens, which stay withheld from the brain). A single
# generic `act` tool (not 7 per-action tools) validates against the CURRENT frame's available_actions,
# matching the docs' "available_actions changes per frame" behavior and MiniWobSession's "reject
# loudly, never silently clamp" discipline for ACTION6's x,y.
_ARCAGI3_OBSERVE_TOOL = {
    "name": "observe",
    "description": ("Look at the CURRENT grid right now without acting. Returns the grid as compact "
                    "text (one character per cell, 0-9 then A-F for the 16 ARC colors), a diff-summary "
                    "of cells changed since your last action (by color transition), the currently "
                    "legal actions, and the step count. The grid IS the whole observable screen here — "
                    "there is no hidden state to withhold. Call this first, and after any act."),
    "inputSchema": {"type": "object", "properties": {}},
}
_ARCAGI3_ACT_TOOL = {
    "name": "act",
    "description": ("Perform one action. `action` must be one of the CURRENTLY legal actions from "
                    "observe's available_actions (e.g. \"ACTION1\".. \"ACTION5\", \"ACTION7\" for "
                    "simple actions, or \"ACTION6\" for a coordinate click). ACTION6 REQUIRES x and y "
                    "(both 0-63); other actions take no coordinates. An action outside the currently "
                    "legal set is REJECTED with an error — nothing is sent to the game."),
    "inputSchema": {"type": "object",
                    "properties": {"action": {"type": "string",
                                              "enum": ["ACTION1", "ACTION2", "ACTION3", "ACTION4",
                                                       "ACTION5", "ACTION6", "ACTION7"]},
                                   "x": {"type": "integer", "minimum": 0, "maximum": 63},
                                   "y": {"type": "integer", "minimum": 0, "maximum": 63}},
                    "required": ["action"]},
}
_ARCAGI3_RESET_TOOL = {
    "name": "reset_game",
    "description": "Reset (restart) the current game instance to its initial state.",
    "inputSchema": {"type": "object", "properties": {}},
}
_ARCAGI3_ACTION_TOOLS = [_ARCAGI3_ACT_TOOL, _ARCAGI3_RESET_TOOL]


# --- Skill compilation rung 1 (reports/2026-07-03-skill-compilation-design.md, ArcAgi3Session port
# ONLY — no other world touched). `define_skill` composes a named macro out of EXISTING primitive
# actions (each step = one `act`-shaped payload, e.g. {"action": "ACTION1"}) plus the single bounded
# loop construct `repeat_until`. `run_skill` executes it against the live world, one LLM decision
# buying up to _SKILL_MAX_WORLD_STEPS world steps. Blank-agent law: skills live only in
# ArcAgi3Session.skills (a plain dict) — never persisted, gone when the session ends (same lifetime as
# `lessons`/`remember`).
_SKILL_MAX_ITERS = 8            # repeat_until's max_iters is schema-capped here (doc §3, pinned)
_SKILL_STEPS_ELAPSED_MAX = 50   # steps_elapsed(n): n <= 50 (doc §3, pinned)
_SKILL_UNCHANGED_FOR_MAX = 8    # grid_unchanged_for(k): k <= 8 (doc §3, pinned)
_SKILL_MAX_WORLD_STEPS = 50     # absolute ceiling per run_skill call, enforced world-side regardless
                                 # of what steps/max_iters would otherwise allow (doc §3, pinned)

_ARCAGI3_DEFINE_SKILL_TOOL = {
    "name": "define_skill",
    "description": ("Compile a named macro out of EXISTING primitive actions you already have. "
                    "`steps` is a list where each entry is either a plain action step "
                    "{\"action\": \"ACTION1\"} (ACTION6 needs x,y too), or a single bounded loop "
                    "{\"repeat_until\": {\"steps\": [...], \"stop_when\": \"<predicate>\", "
                    "\"max_iters\": <=8}} — re-run its inner steps until stop_when fires or max_iters "
                    "iterations complete (no nesting: a repeat_until's inner steps may not contain "
                    "another repeat_until). stop_when is checked after EVERY world step and is one "
                    "of: grid_changed_in_region(x0,y0,x1,y1) with 0<=x0<=x1<=63, 0<=y0<=y1<=63 (any "
                    "cell in that box differs between the two most recent grids), "
                    "grid_unchanged_for(k) with k<=8 (the whole grid identical for k consecutive "
                    "world steps — a stuck/blocked detector), or steps_elapsed(n) with n<=50 (n WORLD "
                    "steps executed inside the loop — every primitive action counts, so a 2-action "
                    "step list reaches steps_elapsed(4) after 2 passes). Re-using a name replaces "
                    "your prior definition. The definition is logged verbatim and forgotten when this "
                    "session ends — it does not persist across runs. Call run_skill(name) to execute "
                    "it."),
    "inputSchema": {"type": "object",
                    "properties": {"name": {"type": "string"}, "steps": {"type": "array"}},
                    "required": ["name", "steps"]},
}
_ARCAGI3_RUN_SKILL_TOOL = {
    "name": "run_skill",
    "description": ("Execute a skill you previously defined with define_skill. Advances world state "
                    "exactly as if each of its steps had been called individually (same validation, "
                    "same logging, same oracle write as a plain act), checking any repeat_until's "
                    "stop_when after each world step and stopping early (with the reason) if it "
                    "fires. An absolute ceiling of 50 world steps applies per call regardless of the "
                    "skill's own definition. Returns ONE result: the observation after the skill ran, "
                    "plus a log of which steps actually executed and why it stopped — one decision, "
                    "many world steps."),
    "inputSchema": {"type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"]},
}
_ARCAGI3_SKILL_TOOLS = [_ARCAGI3_DEFINE_SKILL_TOOL, _ARCAGI3_RUN_SKILL_TOOL]


def _arc_skills_enabled() -> bool:
    """A/B arm isolation (reports/2026-07-03-skill-compilation-design.md §4.1): Arm A must have ONLY
    the existing primitive tools, Arm B additionally gets define_skill/run_skill. Opt-in, default OFF —
    unset or anything other than exactly "1" leaves the brain unable to even see the skill tools."""
    return os.environ.get("ARC_SKILLS") == "1"


def _arcagi3_static_tools() -> list[dict]:
    """tools/list response for arcagi3 — identical regardless of which --arc-game is chosen. Skill
    tools (define_skill/run_skill) are gated behind ARC_SKILLS=1 (A/B arm isolation, see
    _arc_skills_enabled) — default arm (A) never sees them in the tool list at all."""
    base = [_ARCAGI3_OBSERVE_TOOL, _REMEMBER_TOOL, *_ARCAGI3_ACTION_TOOLS]
    if _arc_skills_enabled():
        return [*base, *_ARCAGI3_SKILL_TOOLS]
    return base


# --- Kirby GB port (reports/2026-07-03-kirby-skill-port-entity-v3.md §2/§3, "the second port named
# by the rung-1 A/B verdict's NEXT-implications section"). `define_skill`/`run_skill` are added to
# `World`'s tool surface and `World.call` dispatch — NOT a new session class — because kirby_dreamland
# runs through the generic `World`/Gateway/GamePlugin path (world_mcp.py:626), unlike ArcAgi3Session's
# standalone dispatch class. Build scope: kirby_dreamland ONLY (doc §2). Gated behind KIRBY_SKILLS=1,
# a SEPARATE flag from ARC_SKILLS (doc §2's "one flag per world, not a shared SKILLS_WORLDS" decision
# of record) so a --game kirby_dreamland session with ARC_SKILLS=1 (but no KIRBY_SKILLS) still sees no
# skill tools, and vice versa for an arcagi3 session with KIRBY_SKILLS=1 set.
#
# Steps are press_button-shaped ({"button": "right", "hold_frames": 30}), matching this world's own
# primitive action surface, not ARC's act-payloads. stop_when is Kirby's own closed enum (doc §3):
# steps_elapsed(n<=50), move_blocked, move_succeeded, region_changed(x0,y0,x1,y1) — NOT
# grid_changed_in_region/grid_unchanged_for (ARC's enum) and NOT entity_count_changed (doc §3: demoted
# to candidate, zero firings in all four archived Kirby transcripts) or any oracle/RAM field (hp
# included — doc §3 "hp_dropped is explicitly rejected").
_KIRBY_SKILL_MAX_ITERS = 8            # repeat_until's max_iters cap — identical to rung 1 (doc §3)
_KIRBY_STEPS_ELAPSED_MAX = 50         # steps_elapsed(n): n <= 50 (doc §3, pinned)
_KIRBY_SKILL_MAX_WORLD_STEPS = 50     # absolute per-run_skill-call ceiling, world-side (doc §3, pinned)

_KIRBY_DEFINE_SKILL_TOOL = {
    "name": "define_skill",
    "description": ("Compile a named macro out of EXISTING primitive actions you already have. "
                    "`steps` is a list where each entry is either a plain press step "
                    "{\"button\": \"right\", \"hold_frames\": 30} (hold_frames optional, matches "
                    "press_button's own default), or a single bounded loop "
                    "{\"repeat_until\": {\"steps\": [...], \"stop_when\": \"<predicate>\", "
                    "\"max_iters\": <=8}} — re-run its inner steps until stop_when fires or max_iters "
                    "iterations complete (no nesting: a repeat_until's inner steps may not contain "
                    "another repeat_until). stop_when is checked after EVERY press and is one of: "
                    "steps_elapsed(n) with n<=50 (n presses executed inside the loop), move_blocked "
                    "(your last press's outcome was BLOCKED — fires on the 3rd consecutive blocked "
                    "press against the same wall, not the first), move_succeeded (your last press "
                    "actually moved you), or region_changed(x0,y0,x1,y1) with a box no bigger than "
                    f"{_REGION_MAX_SIDE}x{_REGION_MAX_SIDE} source pixels (the pixels in that box "
                    "changed between your last two observations — same mean-abs-diff>=2.0 test as "
                    "whats_changed). Re-using a name replaces your prior definition. The definition is "
                    "logged verbatim and forgotten when this session ends — it does not persist across "
                    "runs. Call run_skill(name) to execute it."),
    "inputSchema": {"type": "object",
                    "properties": {"name": {"type": "string"}, "steps": {"type": "array"}},
                    "required": ["name", "steps"]},
}
_KIRBY_RUN_SKILL_TOOL = {
    "name": "run_skill",
    "description": ("Execute a skill you previously defined with define_skill. Advances world state "
                    "exactly as if each of its steps had been pressed individually (same validation, "
                    "same logging as a plain press_button), checking any repeat_until's stop_when "
                    "after EACH press and stopping early (with the reason) if it fires. An absolute "
                    f"ceiling of {_KIRBY_SKILL_MAX_WORLD_STEPS} presses applies per call regardless of "
                    "the skill's own definition. Returns ONE result: the observation after the skill "
                    "ran, plus a log of which steps actually executed and why it stopped — one "
                    "decision, many presses."),
    "inputSchema": {"type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"]},
}
_KIRBY_SKILL_TOOLS = [_KIRBY_DEFINE_SKILL_TOOL, _KIRBY_RUN_SKILL_TOOL]

# kirby_dreamland ONLY (doc §2 build scope) — a future third port pins its own flag, never a shared one
# (doc §2's stricter-only rule: "if a future third port wants skill tools, it gets its own flag too").
_KIRBY_SKILLS_WORLDS = frozenset({"kirby_dreamland"})


def _kirby_skills_enabled() -> bool:
    """Arm isolation (doc §2): KIRBY_SKILLS, a SEPARATE env var from ARC_SKILLS — one flag per world,
    not a shared SKILLS_WORLDS CSV var (doc §2's decision of record, justification 1-3). Opt-in,
    default OFF — unset or anything other than exactly "1" leaves the brain unable to even see the
    skill tools. Read once here; callers (tools/list wiring, World.__init__) call this at their own
    fixed point, matching _arc_skills_enabled's shape exactly."""
    return os.environ.get("KIRBY_SKILLS") == "1"


# --- NDS continuous-time skill port (reports/2026-07-04-mkds-continuous-time-build-plan.md, the build
# PR for reports/2026-07-04-continuous-time-stopwhen-design.md, PR #98). `define_skill`/`run_skill` are
# added to `World`'s tool surface + dispatch (nds runs through the SAME generic World/Gateway/GamePlugin
# path as kirby_dreamland, world_mcp.py:705) — NOT a new session class. Gated behind NDS_SKILLS=1, a
# SEPARATE flag from KIRBY_SKILLS/ARC_SKILLS (one flag per world, the same decision of record the Kirby
# port made) so a --game nds session with KIRBY_SKILLS=1 (but no NDS_SKILLS) still sees no skill tools,
# and vice versa for a kirby_dreamland session with NDS_SKILLS=1 set.
#
# The enum here is DIFFERENT from Kirby's (design §3): NDS is continuous-time (the world advances every
# frame regardless of player input, design §0), so the discrete "one press = one world step" assumption
# behind Kirby's steps_elapsed/move_blocked/move_succeeded/region_changed does not hold. This rung ships
# ONLY the two perception-free, frame-counted predicates (design §3): elapsed_frames(n) and
# idle_settled(threshold, k). Foveated region_* is explicitly deferred to the 3D-perception climb (design
# §3) — it is NOT in this enum.
_NDS_SKILL_MAX_ITERS = 8              # repeat_until's max_iters cap — same decision budget as Kirby (plan §3)
_NDS_SKILL_MAX_WORLD_FRAMES = 300     # F: absolute per-run_skill-call frame ceiling (plan §3, ~5s @ 59.83fps)

# Sample stride `s` and idle threshold, calibrated against the REAL probe trace
# (runs/nds3d_probe/idle_measurement.md), not the build plan's own (broken) arithmetic. The plan's
# tentative s=24 was wrong: it derives from k*s<=F alone, ignoring the ACTUAL count-in hold lengths the
# probe measured — 37 consecutive quiet frames (global frames 6-42) and 22 consecutive quiet frames
# (frames 50-71), both under threshold ~0.17-0.9%. At s=24, sampling every 24 frames inside the SHORTER
# 22-frame hold yields at most floor(22/24)+1 = 1 sample below threshold — idle_settled could never
# accumulate k>=2 consecutive sub-threshold samples, let alone the plan's suggested k=10. It would never
# fire on the real data.
#
# Pin s=4 instead: inside the shorter 22-frame hold this gives floor(22/4)=5 samples of margin; inside
# the longer 37-frame hold, floor(37/4)=9. A default/typical k=4 (4*4=16 quiet frames needed) comfortably
# fits inside BOTH holds with room to spare — the dwell requirement is satisfied well before either hold
# ends, not at its edge. k is a per-skill arg the brain supplies, bounded only by the reachability rule
# k*s <= F (not a separate hardcoded max) — at s=4 that allows k up to 75, but a skill author aiming at
# the count-in transition should use something in the k~=3-5 range per this data (floor(22/4)=5 is the
# shorter hold's own margin ceiling — k=6 would not fit inside it).
_NDS_SKILL_SAMPLE_STRIDE = 4          # s: frames between idle_settled samples (see reasoning above)
# Design §7's "threshold gaming" guard: the probe's clean band is ~[0.5%, 6%] — above the count-in
# hold's own noise floor (~0.3%) and below the ~6.77% active-play floor (both figures transcribed into
# the tracked reports/2026-07-04-mkds-continuous-time-build-plan.md §4, since the raw probe file
# runs/nds3d_probe/idle_measurement.md is gitignored and absent from a fresh checkout). A threshold
# outside this band is either unreachable (below count-in noise -> never fires) or trivially satisfied
# by active play (above 6% -> defeats the whole PASSIVE-vs-ACTIVE distinction design §6/§7 relies on).
# Recommended/typical value per the plan is 0.01 (1.0%).
_NDS_IDLE_THRESHOLD_FLOOR = 0.005     # 0.5% — above count-in hold noise
_NDS_IDLE_THRESHOLD_CEIL = 0.06       # 6% — below the ~6.77% active-play floor

_NDS_DEFINE_SKILL_TOOL = {
    "name": "define_skill",
    "description": ("Compile a named macro out of EXISTING primitive actions you already have. "
                    "`steps` is a list where each entry is either a plain press step "
                    "{\"button\": \"a\", \"hold_frames\": 8} (hold_frames optional, matches "
                    "press_button's own default), or a single bounded loop "
                    "{\"repeat_until\": {\"steps\": [...], \"stop_when\": \"<predicate>\", "
                    "\"max_iters\": <=8}} — re-run its inner steps until stop_when fires or max_iters "
                    "iterations complete (no nesting: a repeat_until's inner steps may not contain "
                    "another repeat_until). This world runs in CONTINUOUS TIME: the game advances every "
                    "frame whether or not you act, so stop_when is frame-counted, not press-counted. It "
                    "is one of: elapsed_frames(n) with 0<n<=300 (fires once n emulator frames have "
                    "elapsed since the loop started — the tool for an ACTIVE body, e.g. \"hold accelerate "
                    "for about n frames\"), or idle_settled(threshold, k) with "
                    "0.005<threshold<0.06 (~0.01 typical) and k>=1 (and k*s<=F) "
                    "(fires when the whole-frame pixel-change fraction stays below threshold for k "
                    "consecutive sampled frames — a TRANSITION detector for a PASSIVE body, e.g. \"hold "
                    "through a count-in until the world resumes\"; it will not fire during active play, "
                    "by design). Re-using a name replaces your prior definition. The definition is "
                    "logged verbatim and forgotten when this session ends — it does not persist across "
                    "runs. Call run_skill(name) to execute it."),
    "inputSchema": {"type": "object",
                    "properties": {"name": {"type": "string"}, "steps": {"type": "array"}},
                    "required": ["name", "steps"]},
}
_NDS_RUN_SKILL_TOOL = {
    "name": "run_skill",
    "description": ("Execute a skill you previously defined with define_skill. Advances world state "
                    "exactly as if each of its steps had been pressed individually (same validation, "
                    "same logging as a plain press_button), checking any repeat_until's stop_when "
                    "against sampled frames and stopping early (with the reason) if it fires. An "
                    f"absolute ceiling of {_NDS_SKILL_MAX_WORLD_FRAMES} emulator frames applies per call "
                    "regardless of the skill's own definition, on top of the max_iters decision cap. "
                    "Returns ONE result: the observation after the skill ran, plus a log of which steps "
                    "actually executed and why it stopped — one decision, many frames."),
    "inputSchema": {"type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"]},
}
_NDS_SKILL_TOOLS = [_NDS_DEFINE_SKILL_TOOL, _NDS_RUN_SKILL_TOOL]

# nds ONLY (mirrors Kirby's one-world-per-flag scoping) — a future third continuous-time world pins its
# own flag too, never a shared SKILLS_WORLDS var.
_NDS_SKILLS_WORLDS = frozenset({"nds"})


def _nds_skills_enabled() -> bool:
    """Arm isolation, identical shape to _kirby_skills_enabled/_arc_skills_enabled: NDS_SKILLS is its OWN
    env var, checked independently of KIRBY_SKILLS/ARC_SKILLS. Opt-in, default OFF — unset or anything
    other than exactly "1" leaves the brain unable to even see the skill tools."""
    return os.environ.get("NDS_SKILLS") == "1"


def _miniwob_static_tools() -> list[dict]:
    """tools/list response for any miniwob_* world — identical across tasks (same fixed action surface)."""
    return [_MINIWOB_OBSERVE_TOOL, _MINIWOB_READ_REGION_TOOL, _MINIWOB_WHATS_CHANGED_TOOL,
            *_MINIWOB_ACTION_TOOLS]


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
    if game in _MINIWOB_WORLDS:
        return _miniwob_static_tools()
    if game in _VIZDOOM_WORLDS:
        return _vizdoom_static_tools()
    if game in _ARCAGI3_WORLDS:
        return _arcagi3_static_tools()
    nav = [_OBSERVE_TOOL, _EXPLORE_TOOL, _GOTO_TOOL, _REMEMBER_TOOL]
    if game in _REGION_TOOL_WORLDS:
        nav = [*nav, _READ_REGION_TOOL, _WHATS_CHANGED_TOOL]
    # kirby_dreamland ONLY (doc §2 build scope), gated behind KIRBY_SKILLS=1 — pre-boot tools/list must
    # agree with the live World.tools() gating below so a stale client can't see skill tools that
    # World.call would then refuse (§6 gate 4: "an MCP client's tools/list response is inspectable
    # BEFORE any brain session starts"). Other GB games (incl. gb_generic, cave_noire, gauntlet) never
    # see these tools even if KIRBY_SKILLS happens to be set — the flag is world-scoped, not global.
    if game in _KIRBY_SKILLS_WORLDS and _kirby_skills_enabled():
        nav = [*nav, *_KIRBY_SKILL_TOOLS]
    # nds ONLY, gated behind NDS_SKILLS=1 — same arm-isolation discipline as Kirby: a --game nds session
    # with only KIRBY_SKILLS/ARC_SKILLS set (no NDS_SKILLS) must NOT see these tools, and vice versa (a
    # kirby_dreamland session with NDS_SKILLS=1 must not see them either — the world in-check above is
    # what enforces that direction).
    if game in _NDS_SKILLS_WORLDS and _nds_skills_enabled():
        nav = [*nav, *_NDS_SKILL_TOOLS]
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

        # Kirby GB skill port (reports/2026-07-03-kirby-skill-port-entity-v3.md §2, build scope
        # kirby_dreamland ONLY). Read KIRBY_SKILLS ONCE at init, not per call — the env can't flip
        # mid-session and change which arm this session is (same discipline as ArcAgi3Session's
        # _skills_enabled). tools/list already hides define_skill/run_skill when off or off-world;
        # this is defense-in-depth so a client that calls them anyway (stale tool list, hand-rolled
        # request) still gets a clear refusal, not silent execution.
        self.kirby_skills_world = args.game in _KIRBY_SKILLS_WORLDS
        self._kirby_skills_enabled = self.kirby_skills_world and _kirby_skills_enabled()
        self.skills: dict[str, dict] = {}   # within-run only, blank-agent law (same lifetime as lessons)
        self._skill_log_path = os.path.join(args.out, "skills.jsonl")

        # NDS continuous-time skill port (plan §1, mirrors the Kirby block immediately above). Same
        # per-flag/per-init discipline: NDS_SKILLS is read ONCE at construction, not per call, so the env
        # can't flip mid-session and change which arm this session is. tools/list already hides
        # define_skill/run_skill when off or off-world; this is defense-in-depth against a stale client
        # or hand-rolled request calling them anyway. `self.skills`/`self._skill_log_path` above are
        # reused unchanged — a World instance only ever serves ONE --game, so Kirby and NDS never
        # simultaneously populate the same skills dict.
        self.nds_skills_world = args.game in _NDS_SKILLS_WORLDS
        self._nds_skills_enabled = self.nds_skills_world and _nds_skills_enabled()

    def tools(self) -> list[dict]:
        action = [{"name": s.name, "description": s.description, "inputSchema": s.schema}
                  for s in self.plugin.tools(_AGENT)]
        nav = [_OBSERVE_TOOL, _EXPLORE_TOOL, _GOTO_TOOL, _REMEMBER_TOOL]
        if self.region_tools:
            nav = [*nav, _READ_REGION_TOOL, _WHATS_CHANGED_TOOL]
        if self._kirby_skills_enabled:
            nav = [*nav, *_KIRBY_SKILL_TOOLS]
        if self._nds_skills_enabled:
            nav = [*nav, *_NDS_SKILL_TOOLS]
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

    # -- Kirby GB skill compilation (doc §2/§3, kirby_dreamland ONLY, gated by KIRBY_SKILLS) -----------------
    # `steps` is a list of press_button-shaped steps and/or ONE bounded loop construct `repeat_until`
    # (no nesting, max_iters<=8 — identical caps to rung 1). Every stop_when predicate is computed
    # WORLD-SIDE from data already on this world's wire (sym.last_action["outcome"], or a pixel-region
    # MAD diff identical to whats_changed's own test, or a step counter) — never an oracle/RAM/score
    # field (doc §3: hp stays out of stop_when, out of the wire, always).

    def _log_skill(self, rec: dict) -> None:
        """world/ sibling of oracle.jsonl, same append-only jsonl shape as ArcAgi3Session._log_skill —
        every define_skill logs the full definition verbatim; every run_skill logs executed steps,
        iteration counts, which stop_when fired, executed-step count, and world_steps_used (doc §5.4/
        §5.6 need these fields byte-identical in shape to the ARC port's schema)."""
        try:
            with open(self._skill_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except OSError:
            pass

    @staticmethod
    def _parse_kirby_stop_when(expr: str):
        """Parse one of Kirby's four pinned predicates (doc §3) into (kind, params). Raises ValueError
        (caught by the caller, turned into a tool-result error, never a crash) on anything outside the
        closed enum — stop_when predicates are a fixed closed set, never learned/invented (doc §6 of
        the rung-1 design, carried unchanged)."""
        import re
        expr = (expr or "").strip()
        if expr == "move_blocked":
            return ("move_blocked", {})
        if expr == "move_succeeded":
            return ("move_succeeded", {})
        m = re.fullmatch(r"steps_elapsed\(\s*(\d+)\s*\)", expr)
        if m:
            n = int(m.group(1))
            if not (1 <= n <= _KIRBY_STEPS_ELAPSED_MAX):
                raise ValueError(f"steps_elapsed(n): n must be in [1, {_KIRBY_STEPS_ELAPSED_MAX}]; got {n}")
            return ("steps_elapsed", {"n": n})
        m = re.fullmatch(r"region_changed\(\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\)", expr)
        if m:
            x0, y0, x1, y1 = (int(g) for g in m.groups())
            # Reject loudly at define time (mirrors ARC's grid_changed_in_region PR #89 review finding
            # 1): a negative/inverted/oversize box would silently produce a scan that can never fire.
            if not (0 <= x0 < x1 and 0 <= y0 < y1):
                raise ValueError("region_changed(x0,y0,x1,y1): need 0 <= x0 < x1 and 0 <= y0 < y1; "
                                 f"got ({x0},{y0},{x1},{y1})")
            if (x1 - x0) > _REGION_MAX_SIDE or (y1 - y0) > _REGION_MAX_SIDE:
                raise ValueError(f"region_changed box {x1-x0}x{y1-y0} exceeds the "
                                 f"{_REGION_MAX_SIDE}x{_REGION_MAX_SIDE} source-pixel cap.")
            return ("region_changed", {"x0": x0, "y0": y0, "x1": x1, "y1": y1})
        raise ValueError(f"stop_when {expr!r} is not one of the pinned Kirby predicates: "
                         "steps_elapsed(n<=50), move_blocked, move_succeeded, "
                         "region_changed(x0,y0,x1,y1).")

    def _validate_kirby_step_list(self, steps, *, inside_loop: bool) -> Optional[str]:
        """Structural validation at define_skill time (fail loud before storing a broken skill, never
        at run_skill time). Enforces no-nesting and max_iters<=8, identical caps to rung 1 (doc §3)."""
        if not isinstance(steps, list) or not steps:
            return "define_skill error: `steps` must be a non-empty list."
        valid_buttons = set(self.plugin._buttons()) if hasattr(self.plugin, "_buttons") else set(_GB_BUTTONS)
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                return f"define_skill error: step {i} must be an object; got {type(step).__name__}."
            if "repeat_until" in step:
                if inside_loop:
                    return (f"define_skill error: step {i} is a repeat_until nested inside another "
                            "repeat_until — nesting is not allowed (doc §3, pinned).")
                loop = step["repeat_until"]
                if not isinstance(loop, dict):
                    return f"define_skill error: step {i}'s repeat_until must be an object."
                inner = loop.get("steps")
                stop_when = loop.get("stop_when")
                max_iters = loop.get("max_iters")
                if not isinstance(max_iters, int) or not (1 <= max_iters <= _KIRBY_SKILL_MAX_ITERS):
                    return (f"define_skill error: step {i}'s repeat_until.max_iters must be an int in "
                            f"[1, {_KIRBY_SKILL_MAX_ITERS}]; got {max_iters!r}.")
                try:
                    self._parse_kirby_stop_when(stop_when)
                except ValueError as e:
                    return f"define_skill error: step {i}'s repeat_until.stop_when invalid: {e}"
                err = self._validate_kirby_step_list(inner, inside_loop=True)
                if err:
                    return err
            elif "button" in step:
                b = str(step.get("button", "")).strip().lower()
                if b not in valid_buttons:
                    return (f"define_skill error: step {i}'s button {step.get('button')!r} is not "
                            f"valid; must be one of {sorted(valid_buttons)}.")
                hold = step.get("hold_frames", 8)
                if not isinstance(hold, int) or not (1 <= hold <= 120):
                    return (f"define_skill error: step {i}'s hold_frames must be an int in [1, 120]; "
                            f"got {hold!r}.")
            else:
                return f"define_skill error: step {i} must have either \"button\" or \"repeat_until\"."
        return None

    def _define_skill(self, args: dict) -> list[dict]:
        skill_name = str(args.get("name", "")).strip()
        if not skill_name:
            return [{"type": "text", "text": "define_skill error: `name` must be a non-empty string."}]
        if "stop_when" in args:
            # Mirrors ARC's PR #89 review finding: a top-level stop_when has NO effect (it belongs
            # inside a repeat_until step) — silently ignoring it would let the brain believe a
            # condition was armed when it wasn't. Reject loudly; nothing is defined.
            return [{"type": "text",
                     "text": "define_skill error: `stop_when` belongs INSIDE a repeat_until step "
                             "({\"repeat_until\": {\"steps\": [...], \"stop_when\": \"...\", "
                             "\"max_iters\": N}}), not at the top level — it would have no effect "
                             "there. Skill NOT defined."}]
        steps = args.get("steps")
        err = self._validate_kirby_step_list(steps, inside_loop=False)
        if err:
            return [{"type": "text", "text": err}]
        definition = {"name": skill_name, "steps": steps}
        prior = self.skills.get(skill_name)
        self.skills[skill_name] = definition
        # Auditability (doc §3, carried from rung 1): the full definition is logged verbatim. A
        # redefinition is a DISTINCT event carrying both the old and new definitions (same shape as
        # ArcAgi3Session._define_skill's redefine_skill event).
        step_count = int(getattr(self.plugin, "_obs_count", 0))
        if prior is not None:
            self._log_skill({"event": "redefine_skill", "step": step_count,
                             "prior_definition": prior, "definition": definition})
            return [{"type": "text",
                     "text": f"[define_skill {skill_name!r} -> ok, REPLACED your prior definition of "
                             f"the same name; {len(steps)} top-level step(s)] "
                             f"Call run_skill({{\"name\": {skill_name!r}}}) to execute it."}]
        self._log_skill({"event": "define_skill", "step": step_count, "definition": definition})
        return [{"type": "text",
                 "text": f"[define_skill {skill_name!r} -> ok, {len(steps)} top-level step(s)] "
                         f"Call run_skill({{\"name\": {skill_name!r}}}) to execute it."}]

    def _kirby_press_and_observe(self, button: str, hold_frames: int) -> tuple[bool, Optional[str], Optional[str]]:
        """Execute ONE primitive press via the gateway (same validation/logging/oracle-write path as a
        plain press_button call — doc §2 'honest accounting': no step can do anything a primitive
        call couldn't), THEN re-observe so stop_when predicates evaluate against FRESH state
        (doc §2's pinned executor mechanism — the `World._run_autopilot` per-step pattern:
        `plugin.observe(_AGENT)` after each step, world_mcp.py:834-851 — mirrored here per press).
        Returns (ok, error, outcome). Exactly ONE `plugin.observe()` call per press (doc §2's "one
        oracle row per press, the same step granularity as manual play" pin) — the outcome is
        returned so `_check_kirby_stop_when` never has to observe a second time for the same press.
        On success also updates `_frame_hist` via `_track_frame()` so region_changed can diff the two
        most recent presses' frames, identical to whats_changed."""
        res = self.gw.execute(ToolCall(tool="press_button", args={"button": button, "hold_frames": hold_frames},
                                       agent_id=_AGENT, call_id=str(uuid.uuid4())))
        if not res.ok:
            return False, res.error or "press_button rejected", None
        obs = self.plugin.observe(_AGENT)   # per-press re-observation: one oracle row per press (doc §2)
        self._drop_frame(obs)
        self._track_frame()                 # frame-pair update so region_changed's MAD diff is fresh
        outcome = ((obs.data or {}).get("last_action") or {}).get("outcome")
        return True, None, outcome

    def _check_kirby_stop_when(self, kind: str, params: dict, *, loop_steps: int,
                               last_outcome: Optional[str]) -> bool:
        """Evaluate one pinned predicate against the FRESH per-press state already captured by
        `_kirby_press_and_observe` (doc §3) — never a second observe() for the same press. move_blocked/
        move_succeeded read sym.last_action["outcome"] (passed in as `last_outcome`), the same field
        core/perception_plugin.py's renderer reads (the BLOCKED/moved text lines) — no new channel.
        region_changed reuses whats_changed's own MAD>=2.0 dead-zone over the two most recently tracked
        frames. Never an oracle/RAM field (hp stays out of stop_when — doc §3)."""
        if kind == "steps_elapsed":
            return loop_steps >= params["n"]
        if kind == "move_blocked":
            return last_outcome == "blocked"
        if kind == "move_succeeded":
            return last_outcome == "moved"
        if kind == "region_changed":
            if len(self._frame_hist) < 2:
                return False
            (_, prev), (_, curr) = self._frame_hist[-2], self._frame_hist[-1]
            x0, y0, x1, y1 = params["x0"], params["y0"], params["x1"], params["y1"]
            h, w = curr.shape[0], curr.shape[1]
            if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
                return False   # region no longer valid against the current frame size — never fire
            a = prev[y0:y1, x0:x1].astype(np.float32)
            b = curr[y0:y1, x0:x1].astype(np.float32)
            return float(np.mean(np.abs(a - b))) >= 2.0
        return False   # unreachable: _parse_kirby_stop_when already rejected anything else

    def _exec_kirby_primitive(self, step: dict, executed: list,
                              world_step_budget: list) -> tuple[Optional[str], Optional[str]]:
        """Execute ONE primitive press step. The budget is decremented ONLY on success (mirrors ARC's
        _exec_primitive: a rejected step sent nothing to the world, so world_steps_used must mean
        actual world activity, never attempts). Returns (error, outcome) — outcome is None on error."""
        if world_step_budget[0] <= 0:
            return f"stopped: absolute {_KIRBY_SKILL_MAX_WORLD_STEPS}-press ceiling hit", None
        button = str(step.get("button", "")).strip().lower()
        hold_frames = int(step.get("hold_frames", 8))
        ok, err, outcome = self._kirby_press_and_observe(button, hold_frames)
        if not ok:
            executed.append({"button": button, "hold_frames": hold_frames, "ok": False, "error": err})
            return err, None
        world_step_budget[0] -= 1
        executed.append({"button": button, "hold_frames": hold_frames, "ok": True})
        return None, outcome

    def _run_kirby_steps_once(self, steps, executed: list, world_step_budget: list) -> Optional[str]:
        """Execute the top-level step list: plain press steps and/or repeat_until blocks (whose inner
        lists are guaranteed flat — no nesting, enforced at define time). stop_when is checked after
        EVERY press (doc §2's per-press executor decision), so it can fire mid-iteration of a
        multi-press inner list."""
        for step in steps:
            if "repeat_until" in step:
                loop = step["repeat_until"]
                inner = loop["steps"]
                kind, params = self._parse_kirby_stop_when(loop["stop_when"])
                max_iters = loop["max_iters"]
                iters_done = 0
                loop_steps = 0   # presses executed inside THIS loop (steps_elapsed's unit)
                stop_reason = None
                while iters_done < max_iters and stop_reason is None:
                    for inner_step in inner:
                        err, outcome = self._exec_kirby_primitive(inner_step, executed, world_step_budget)
                        if err:
                            return err
                        loop_steps += 1
                        if self._check_kirby_stop_when(kind, params, loop_steps=loop_steps,
                                                       last_outcome=outcome):
                            stop_reason = (f"stop_when {loop['stop_when']!r} fired after "
                                           f"{loop_steps} press(es) ({iters_done + 1} iteration(s))")
                            break
                    iters_done += 1
                if stop_reason is None:
                    stop_reason = f"repeat_until reached max_iters={max_iters} without stop_when firing"
                executed.append({"repeat_until_summary": stop_reason, "iterations": iters_done,
                                 "world_steps": loop_steps})
            else:
                err, _outcome = self._exec_kirby_primitive(step, executed, world_step_budget)
                if err:
                    return err
        return None

    def _run_skill(self, args: dict) -> list[dict]:
        skill_name = str(args.get("name", "")).strip()
        definition = self.skills.get(skill_name)
        if definition is None:
            return [{"type": "text",
                     "text": f"run_skill error: no skill named {skill_name!r} — call define_skill "
                             "first (skills are within-run only, not persisted)."}]
        executed: list = []
        world_step_budget = [_KIRBY_SKILL_MAX_WORLD_STEPS]   # absolute ceiling, world-side (doc §3)
        error = self._run_kirby_steps_once(definition["steps"], executed, world_step_budget)
        executed_primitive_count = sum(1 for e in executed if e.get("ok") is True)
        if error is not None:
            stop_reason = error
        elif executed and "repeat_until_summary" in executed[-1]:
            stop_reason = executed[-1]["repeat_until_summary"]
        else:
            stop_reason = "all top-level steps executed"
        world_steps_used = _KIRBY_SKILL_MAX_WORLD_STEPS - world_step_budget[0]
        # RESIDUAL #1 (PR #92 verification comment, mandatory): log BEFORE any trailing observe, so the
        # span boundary S0 (`r.step - r.world_steps_used`) stays claimable per doc §5.6. `plugin._obs_count`
        # right now is EXACTLY the post-macro step (the last inner press's own re-observation already
        # advanced it, per-press, one oracle row per press) — logging here, before the trailing render
        # below calls `self.plugin.observe()` again (which would bump _obs_count one further), keeps
        # `step` in this record equal to the true macro-end boundary the scorer's exclusion formula needs.
        #
        # COUNTER-FAMILY NOTE (PR #93 executor review, finding 3 — documented so a refactor can't
        # silently break it): this `step` is the plugin's OBSERVE-CALL counter (`_obs_count`, one
        # increment + one oracle row per plugin.observe() call), NOT the ARC port's per-ACTION counter
        # (`ArcAgi3Session._step_count`, advanced by `_apply_frame` once per world action). The two
        # families coincide here ONLY because doc §2's pinned executor performs exactly one observe()
        # per inner press (`_kirby_press_and_observe` is the sole observe site inside the loop) and
        # ordinary manual play also observes once per decision. Anything that observes more or less
        # than once per press inside this loop (a second predicate observe, a PATIENCE opt-in for this
        # world that auto-presses inside observe(), a batched observe) breaks the step<->press
        # alignment that §5.6's exclusion formula and the oracle-row-per-press pin both depend on —
        # tests/test_kirby_skill_port.py pins the invariant through the real oracle.jsonl (one row per
        # press + one trailing render row, and patience_advances == 0 on every row).
        log_step = int(getattr(self.plugin, "_obs_count", 0))
        log_rec = {"event": "run_skill", "step": log_step, "name": skill_name,
                   "executed": executed, "executed_step_count": executed_primitive_count,
                   "stop_reason": stop_reason, "world_steps_used": world_steps_used}
        self._log_skill(log_rec)
        head = (f"[run_skill {skill_name!r} -> {executed_primitive_count} step(s) executed; "
                f"stopped because: {stop_reason}]")
        # Trailing render: a fresh observe (this DOES advance plugin._obs_count by one more, same as
        # every other World.call branch's trailing self._content(self.plugin.observe(_AGENT)) —
        # logged already, above, so this extra step is never mistaken for part of the macro's span.
        return [{"type": "text", "text": head}, *self._content(self.plugin.observe(_AGENT))]

    # -- NDS continuous-time skill compilation (plan §2-§5, nds ONLY, gated by NDS_SKILLS) ---------------------
    # `steps` is a list of press-shaped steps ({"button": "a"|"none", "hold_frames": N}) and/or ONE
    # bounded loop construct `repeat_until` (no nesting, max_iters<=8 — identical caps to Kirby/rung 1).
    # Unlike Kirby, this world is CONTINUOUS TIME (design §0): the world advances every frame regardless
    # of player input, so the budget is split (design §2) into a DECISION budget (max_iters, unchanged)
    # and a FRAME budget (_NDS_SKILL_MAX_WORLD_FRAMES, an absolute per-run_skill-call ceiling counted via
    # emu.frame deltas, never a press count). stop_when predicates are frame-counted
    # (elapsed_frames/idle_settled), never an oracle/RAM/score field — same no-leak law as Kirby.

    @staticmethod
    def _parse_nds_stop_when(expr: str):
        """Parse one of NDS's two pinned predicates (plan §2/design §3) into (kind, params). Raises
        ValueError (caught by the caller, turned into a tool-result error, never a crash) on anything
        outside the closed enum — mirrors _parse_kirby_stop_when exactly, different enum. Reachability
        (design §5's "reject an unsatisfiable skill at define, don't discover it at runtime") is checked
        HERE, at parse time, using the fixed frame ceiling F — not deferred to run_skill."""
        import re
        expr = (expr or "").strip()
        m = re.fullmatch(r"elapsed_frames\(\s*(\d+)\s*\)", expr)
        if m:
            n = int(m.group(1))
            if not (0 < n <= _NDS_SKILL_MAX_WORLD_FRAMES):
                raise ValueError(f"elapsed_frames(n): n must satisfy 0 < n <= "
                                 f"{_NDS_SKILL_MAX_WORLD_FRAMES}; got {n}")
            return ("elapsed_frames", {"n": n})
        m = re.fullmatch(r"idle_settled\(\s*([0-9]*\.?[0-9]+)\s*,\s*(\d+)\s*\)", expr)
        if m:
            threshold = float(m.group(1))
            k = int(m.group(2))
            if not (_NDS_IDLE_THRESHOLD_FLOOR < threshold < _NDS_IDLE_THRESHOLD_CEIL):
                raise ValueError(
                    f"idle_settled(threshold, k): threshold must satisfy "
                    f"{_NDS_IDLE_THRESHOLD_FLOOR} < threshold < {_NDS_IDLE_THRESHOLD_CEIL} "
                    "(the threshold-gaming guard — must sit strictly between the measured count-in "
                    f"idle noise and the active-play floor); got {threshold}")
            if k < 1:
                raise ValueError(f"idle_settled(threshold, k): k must be >= 1; got {k}")
            if k * _NDS_SKILL_SAMPLE_STRIDE > _NDS_SKILL_MAX_WORLD_FRAMES:
                raise ValueError(
                    f"idle_settled(threshold, k): k*s <= F required (s={_NDS_SKILL_SAMPLE_STRIDE}, "
                    f"F={_NDS_SKILL_MAX_WORLD_FRAMES}) so the dwell can ever be reached within budget; "
                    f"got k={k} (k*s={k * _NDS_SKILL_SAMPLE_STRIDE})")
            return ("idle_settled", {"threshold": threshold, "k": k})
        raise ValueError(f"stop_when {expr!r} is not one of the pinned NDS predicates: "
                         f"elapsed_frames(n) with 0<n<={_NDS_SKILL_MAX_WORLD_FRAMES}, "
                         f"idle_settled(threshold, k) with {_NDS_IDLE_THRESHOLD_FLOOR}<threshold"
                         f"<{_NDS_IDLE_THRESHOLD_CEIL} and k>=1 (and k*s<=F).")

    def _validate_nds_step_list(self, steps, *, inside_loop: bool) -> Optional[str]:
        """Structural validation at define_skill time (fail loud before storing a broken skill, never at
        run_skill time) — mirrors _validate_kirby_step_list. "none" is a valid pseudo-button meaning "no
        input this step" (tick frames with nothing held) — the PASSIVE body idle_settled needs (design
        §6: a button-issuing body keeps resetting idle_settled's streak, so a hold-through-transition
        loop's body must be able to issue nothing)."""
        if not isinstance(steps, list) or not steps:
            return "define_skill error: `steps` must be a non-empty list."
        valid_buttons = set(self.plugin._buttons()) if hasattr(self.plugin, "_buttons") else set(_nds_emu_mod.BUTTONS)
        valid_buttons = valid_buttons | {"none"}
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                return f"define_skill error: step {i} must be an object; got {type(step).__name__}."
            if "repeat_until" in step:
                if inside_loop:
                    return (f"define_skill error: step {i} is a repeat_until nested inside another "
                            "repeat_until — nesting is not allowed (plan §5, pinned).")
                loop = step["repeat_until"]
                if not isinstance(loop, dict):
                    return f"define_skill error: step {i}'s repeat_until must be an object."
                inner = loop.get("steps")
                stop_when = loop.get("stop_when")
                max_iters = loop.get("max_iters")
                if not isinstance(max_iters, int) or not (1 <= max_iters <= _NDS_SKILL_MAX_ITERS):
                    return (f"define_skill error: step {i}'s repeat_until.max_iters must be an int in "
                            f"[1, {_NDS_SKILL_MAX_ITERS}]; got {max_iters!r}.")
                try:
                    self._parse_nds_stop_when(stop_when)
                except ValueError as e:
                    return f"define_skill error: step {i}'s repeat_until.stop_when invalid: {e}"
                err = self._validate_nds_step_list(inner, inside_loop=True)
                if err:
                    return err
            elif "button" in step:
                b = str(step.get("button", "")).strip().lower()
                if b not in valid_buttons:
                    return (f"define_skill error: step {i}'s button {step.get('button')!r} is not "
                            f"valid; must be one of {sorted(valid_buttons)}.")
                hold = step.get("hold_frames", 8)
                if not isinstance(hold, int) or not (1 <= hold <= 120):
                    return (f"define_skill error: step {i}'s hold_frames must be an int in [1, 120]; "
                            f"got {hold!r}.")
            else:
                return f"define_skill error: step {i} must have either \"button\" or \"repeat_until\"."
        return None

    def _define_nds_skill(self, args: dict) -> list[dict]:
        skill_name = str(args.get("name", "")).strip()
        if not skill_name:
            return [{"type": "text", "text": "define_skill error: `name` must be a non-empty string."}]
        if "stop_when" in args:
            # Mirrors Kirby/ARC's finding: a top-level stop_when has NO effect (it belongs inside a
            # repeat_until step) — silently ignoring it would let the brain believe a condition was
            # armed when it wasn't. Reject loudly; nothing is defined.
            return [{"type": "text",
                     "text": "define_skill error: `stop_when` belongs INSIDE a repeat_until step "
                             "({\"repeat_until\": {\"steps\": [...], \"stop_when\": \"...\", "
                             "\"max_iters\": N}}), not at the top level — it would have no effect "
                             "there. Skill NOT defined."}]
        steps = args.get("steps")
        err = self._validate_nds_step_list(steps, inside_loop=False)
        if err:
            return [{"type": "text", "text": err}]
        definition = {"name": skill_name, "steps": steps}
        prior = self.skills.get(skill_name)
        self.skills[skill_name] = definition
        step_count = int(getattr(self.plugin, "_obs_count", 0))
        if prior is not None:
            self._log_skill({"event": "redefine_skill", "step": step_count,
                             "prior_definition": prior, "definition": definition})
            return [{"type": "text",
                     "text": f"[define_skill {skill_name!r} -> ok, REPLACED your prior definition of "
                             f"the same name; {len(steps)} top-level step(s)] "
                             f"Call run_skill({{\"name\": {skill_name!r}}}) to execute it."}]
        self._log_skill({"event": "define_skill", "step": step_count, "definition": definition})
        return [{"type": "text",
                 "text": f"[define_skill {skill_name!r} -> ok, {len(steps)} top-level step(s)] "
                         f"Call run_skill({{\"name\": {skill_name!r}}}) to execute it."}]

    @staticmethod
    def _nds_pct_changed(prev: np.ndarray, curr: np.ndarray) -> float:
        """Whole-frame mean-abs pixel-change fraction — the SAME metric
        runs/nds3d_probe/idle_measurement.md and the design doc pin (mean |delta| / 255 across the
        entire frame), so a threshold pinned from that probe transfers directly to this code."""
        return float(np.mean(np.abs(curr.astype(np.int32) - prev.astype(np.int32)))) / 255.0

    def _nds_step_and_sample(self, button: str, hold_frames: int,
                             world_frame_budget: list) -> tuple[Optional[str], list]:
        """Execute ONE inner step and return (error, samples) where `samples` is a list of pct_changed
        readings taken during the step (design §5's "sample every s frames"). Two shapes, by body kind:

        - PASSIVE step (button == "none"): advance in `_NDS_SKILL_SAMPLE_STRIDE`-frame ticks so
          idle_settled gets real intra-step samples (plan's "use tick(s) in a loop" instruction) — this
          is the only body kind idle_settled is meant to fire against (design §6/§7: an ACTING body
          keeps resetting the whole-frame change, making idle_settled self-defeating there).
        - ACTIVE step (a real button): executed as ONE emulator press() (hold+settle, ~24 frames) —
          press() is atomic (no public sub-tick hook without duplicating its key-hold logic), so the
          sample point is once per full press. This is fine because elapsed_frames, not idle_settled, is
          the predicate design §6 pins for an acting body — no intra-press stride is needed for it. A
          press is refused (ceiling hit) rather than issued if the REMAINING budget can't cover its full
          hold+settle — F is an absolute cap (plan §5), so a step must never be allowed to overshoot it,
          only to stop short of it (mirrors the "none" branch's own remaining=min(...) clamp below).

        The frame budget is decremented by the ACTUAL frames advanced (mirrors Kirby's press-budget
        decrement: only real world activity counts, never an attempted-but-rejected step)."""
        emu = self.plugin.emu
        if world_frame_budget[0] <= 0:
            return f"stopped: absolute {_NDS_SKILL_MAX_WORLD_FRAMES}-frame ceiling hit", []
        samples: list = []
        start_frame = emu.frame
        if button == "none":
            prev = emu.screen_ndarray("both")
            remaining = min(hold_frames, world_frame_budget[0])
            advanced = 0
            while advanced < remaining:
                step_frames = min(_NDS_SKILL_SAMPLE_STRIDE, remaining - advanced)
                emu.tick(step_frames)
                advanced += step_frames
                curr = emu.screen_ndarray("both")
                samples.append(self._nds_pct_changed(prev, curr))
                prev = curr
        else:
            if button not in set(self.plugin._buttons()):
                return f"invalid button: {button!r}", []
            # press()'s actual frame cost is hold_frames + its settle_frames default (16) — estimate
            # conservatively so a press that WOULD overshoot F is refused up front, never issued and
            # then overshot (DeSmuMEEmulator.press's own default settle; NDSPerceptionPlugin callers
            # never override it here, so this estimate matches the real cost byte-for-byte).
            estimated_cost = hold_frames + 16
            if estimated_cost > world_frame_budget[0]:
                return f"stopped: absolute {_NDS_SKILL_MAX_WORLD_FRAMES}-frame ceiling hit", []
            prev = emu.screen_ndarray("both")
            emu.press(button, hold_frames=hold_frames)
            curr = emu.screen_ndarray("both")
            samples.append(self._nds_pct_changed(prev, curr))
        frames_used = emu.frame - start_frame
        world_frame_budget[0] -= frames_used
        self._track_frame()   # keep _frame_hist fresh (read_region/whats_changed parity, if ever mixed)
        return None, samples

    def _check_nds_stop_when(self, kind: str, params: dict, *, elapsed_in_loop: int,
                             idle_streak: list) -> bool:
        """Evaluate one pinned predicate. `elapsed_in_loop` is the emulator-frame count since the
        CURRENT repeat_until loop started (elapsed_frames' unit — world time, not press count, per
        design §2's rethink of steps_elapsed). `idle_streak` is a 1-element mutable counter of
        CONSECUTIVE sub-threshold samples seen so far in this loop; the caller updates it per sample
        (across possibly-multiple samples per step) BEFORE calling this, mirroring how Kirby's
        move_blocked/move_succeeded read the freshly-captured outcome rather than re-observing."""
        if kind == "elapsed_frames":
            return elapsed_in_loop >= params["n"]
        if kind == "idle_settled":
            return idle_streak[0] >= params["k"]
        return False   # unreachable: _parse_nds_stop_when already rejected anything else

    def _run_nds_steps_once(self, steps, executed: list, world_frame_budget: list) -> Optional[str]:
        """Execute the top-level step list: plain steps and/or repeat_until blocks (inner lists
        guaranteed flat — no nesting, enforced at define time). stop_when is checked after EVERY
        sampled frame (design §5's per-sample executor decision — finer-grained than Kirby's per-press
        check, because a single step here can itself span several samples for a passive body)."""
        for step in steps:
            if "repeat_until" in step:
                loop = step["repeat_until"]
                inner = loop["steps"]
                kind, params = self._parse_nds_stop_when(loop["stop_when"])
                max_iters = loop["max_iters"]
                iters_done = 0
                loop_frame_start = self.plugin.emu.frame
                idle_streak = [0]   # consecutive sub-threshold samples, RESET when a sample is >= threshold
                stop_reason = None
                while iters_done < max_iters and stop_reason is None:
                    for inner_step in inner:
                        button = str(inner_step.get("button", "")).strip().lower()
                        hold_frames = int(inner_step.get("hold_frames", 8))
                        err, samples = self._nds_step_and_sample(button, hold_frames, world_frame_budget)
                        if err:
                            executed.append({"button": button, "hold_frames": hold_frames, "ok": False,
                                             "error": err})
                            return err
                        executed.append({"button": button, "hold_frames": hold_frames, "ok": True})
                        for pct in samples:
                            if kind == "idle_settled":
                                if pct < params["threshold"]:
                                    idle_streak[0] += 1
                                else:
                                    idle_streak[0] = 0
                            elapsed = self.plugin.emu.frame - loop_frame_start
                            if self._check_nds_stop_when(kind, params, elapsed_in_loop=elapsed,
                                                         idle_streak=idle_streak):
                                stop_reason = (f"stop_when {loop['stop_when']!r} fired after "
                                               f"{elapsed} frame(s) ({iters_done + 1} iteration(s))")
                                break
                        if stop_reason or world_frame_budget[0] <= 0:
                            break
                    iters_done += 1
                    if world_frame_budget[0] <= 0 and stop_reason is None:
                        stop_reason = f"stopped: absolute {_NDS_SKILL_MAX_WORLD_FRAMES}-frame ceiling hit"
                if stop_reason is None:
                    stop_reason = f"repeat_until reached max_iters={max_iters} without stop_when firing"
                loop_frames = self.plugin.emu.frame - loop_frame_start
                executed.append({"repeat_until_summary": stop_reason, "iterations": iters_done,
                                 "world_frames": loop_frames})
            else:
                button = str(step.get("button", "")).strip().lower()
                hold_frames = int(step.get("hold_frames", 8))
                err, _samples = self._nds_step_and_sample(button, hold_frames, world_frame_budget)
                if err:
                    executed.append({"button": button, "hold_frames": hold_frames, "ok": False, "error": err})
                    return err
                executed.append({"button": button, "hold_frames": hold_frames, "ok": True})
        return None

    def _run_nds_skill(self, args: dict) -> list[dict]:
        skill_name = str(args.get("name", "")).strip()
        definition = self.skills.get(skill_name)
        if definition is None:
            return [{"type": "text",
                     "text": f"run_skill error: no skill named {skill_name!r} — call define_skill "
                             "first (skills are within-run only, not persisted)."}]
        executed: list = []
        world_frame_budget = [_NDS_SKILL_MAX_WORLD_FRAMES]   # absolute ceiling, world-side (plan §3)
        start_frame = self.plugin.emu.frame
        error = self._run_nds_steps_once(definition["steps"], executed, world_frame_budget)
        executed_step_count = sum(1 for e in executed if e.get("ok") is True)
        if error is not None:
            stop_reason = error
        elif executed and "repeat_until_summary" in executed[-1]:
            stop_reason = executed[-1]["repeat_until_summary"]
        else:
            stop_reason = "all top-level steps executed"
        world_frames_used = self.plugin.emu.frame - start_frame
        # A run_skill call "qualifies" (design §7's conditional-half gate) only if stop_when actually
        # fired before the frame ceiling/max_iters — a real predicate branch, not a timeout. Log this
        # explicitly so the eventual A/B scorer can compute the gate without re-deriving it from prose.
        # Scan ALL executed top-level entries, not just the last one: a skill with multiple sequential
        # repeat_until blocks (design §6's launch+wait_out_banner shape) where an EARLY loop's stop_when
        # fires but a LATER one times out must still log True — checking only executed[-1] would
        # wrongly discard qualifying evidence the gate needs.
        stop_when_fired = any(isinstance(e, dict) and "fired after" in e.get("repeat_until_summary", "")
                              for e in executed)
        log_step = int(getattr(self.plugin, "_obs_count", 0))
        log_rec = {"event": "run_skill", "step": log_step, "name": skill_name,
                   "executed": executed, "executed_step_count": executed_step_count,
                   "stop_reason": stop_reason, "world_frames_used": world_frames_used,
                   "stop_when_fired": stop_when_fired}
        self._log_skill(log_rec)
        head = (f"[run_skill {skill_name!r} -> {executed_step_count} step(s) executed, "
                f"{world_frames_used} frame(s); stopped because: {stop_reason}]")
        # Trailing render: a fresh observe (advances plugin._obs_count by one more, logged already above
        # — mirrors Kirby's own trailing-observe-after-log ordering, RESIDUAL #1's discipline).
        return [{"type": "text", "text": head}, *self._content(self.plugin.observe(_AGENT))]

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
        elif name == "define_skill" and self.nds_skills_world:
            if not self._nds_skills_enabled:
                body = [{"type": "text",
                         "text": "define_skill error: skill tools are disabled for this session "
                                 "(set NDS_SKILLS=1 in the environment to enable, on nds only — see "
                                 "reports/2026-07-04-mkds-continuous-time-build-plan.md §1)."}]
            else:
                body = self._define_nds_skill(args)
        elif name == "run_skill" and self.nds_skills_world:
            if not self._nds_skills_enabled:
                body = [{"type": "text",
                         "text": "run_skill error: skill tools are disabled for this session (set "
                                 "NDS_SKILLS=1 in the environment to enable, on nds only — see "
                                 "reports/2026-07-04-mkds-continuous-time-build-plan.md §1)."}]
            else:
                self.decisions += 1   # one LLM decision buys up to _NDS_SKILL_MAX_WORLD_FRAMES frames
                body = self._run_nds_skill(args)
        elif name == "define_skill":
            if not self._kirby_skills_enabled:
                body = [{"type": "text",
                         "text": "define_skill error: skill tools are disabled for this session "
                                 "(set KIRBY_SKILLS=1 in the environment to enable, on kirby_dreamland "
                                 "only — see reports/2026-07-03-kirby-skill-port-entity-v3.md §2)."}]
            else:
                body = self._define_skill(args)
        elif name == "run_skill":
            if not self._kirby_skills_enabled:
                body = [{"type": "text",
                         "text": "run_skill error: skill tools are disabled for this session (set "
                                 "KIRBY_SKILLS=1 in the environment to enable, on kirby_dreamland only "
                                 "— see reports/2026-07-03-kirby-skill-port-entity-v3.md §2)."}]
            else:
                self.decisions += 1   # one LLM decision buys up to _KIRBY_SKILL_MAX_WORLD_STEPS presses
                body = self._run_skill(args)
        else:
            # a direct action (press_button / press_sequence / wait / touch / touch_target): route through the gateway.
            if name in ("press_button", "press_sequence", "wait", "touch", "touch_target"):
                self.decisions += 1          # a real brain action is a wake; an unknown tool name is not counted
            res = self.gw.execute(ToolCall(tool=name, args=args, agent_id=_AGENT, call_id=str(uuid.uuid4())))
            head = {"type": "text", "text": f"[{name} -> ok={res.ok}" + ("" if res.ok else f", {res.error}") + "]"}
            body = [head, *self._content(self.plugin.observe(_AGENT))]

        pre = self._preamble()
        return ([{"type": "text", "text": pre}, *body] if pre else body)


class MiniWobSession:
    """One live MiniWoB++ episode, served as an MCP tool surface. Standalone (not core.gateway.Gateway
    or a GamePlugin) — MiniWoB's action vocabulary (click/type/key) and observation shape (utterance +
    screenshot, no tile grid) don't fit the emulator-plugin abstraction the `World` class above wraps, so
    this is a parallel, equally-thin dispatch path. Same no-leak law as `World`: reward/dom_elements are
    the oracle here, logged to <out>/oracle.jsonl by _log_oracle, NEVER placed in a tool result."""

    def __init__(self, args) -> None:
        # NOTE: the --record rejection for this family lives in main()'s argument validation, NOT here —
        # this session is built lazily on the first tool CALL, so a SystemExit from __init__ would kill
        # the server mid-protocol instead of at launch (PR #64 re-validation nit).
        from core.miniwob_world import MiniWobWorld, VIEWPORT_HEIGHT, VIEWPORT_WIDTH
        self._viewport_h = VIEWPORT_HEIGHT
        self._viewport_w = VIEWPORT_WIDTH
        task = GAMES[args.game]["task"]
        os.makedirs(args.out, exist_ok=True)
        self._oracle_path = os.path.join(args.out, "oracle.jsonl")
        self._step_count = 0
        self._task = task
        self._episode_over = False   # env terminated/truncated flag; surfaced ONLY as observe's
                                     # episode-status line, never in an action result (PR #64 fix)
        self.mw = MiniWobWorld(task)
        self.mw.reset()
        self._frame_hist: list = []   # last <=2 (step, frame) pairs, for whats_changed (mirrors World)
        self._log_oracle(done=False)
        self._track_frame()

    # -- oracle logging (scoring only; never in a tool result) -----------------------------------------

    def _log_oracle(self, done: bool) -> None:
        info = self.mw.last_info or {}
        rec = {"step": self._step_count, "task": self._task,
              "reward": float(info.get("reward", 0.0)), "done": bool(done)}
        try:
            with open(self._oracle_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except OSError:
            pass

    # -- frame tracking for read_region/whats_changed (same shape as World._track_frame) ----------------

    def _track_frame(self) -> None:
        self._frame_hist.append((self._step_count, self.mw.screenshot))
        del self._frame_hist[:-2]

    # -- observe: utterance + screen size + episode status — no DOM, no reward, no entity list ----------
    # (PR #64 review, finding 2: the previous blob entity list was structurally dead code — core/blob.py's
    # RollingBg segmentation is motion-based, and the median background of N identical frames IS the
    # frame, so a static UI always yielded zero foreground. Static-UI segmentation is a NAMING-layer
    # problem — deciding what counts as a widget on a still frame — not a motion one; deferred. The brain
    # sees the page by tiling read_region crops, which the live validation proved sufficient.)

    def _observe_content(self) -> list[dict]:
        frame = self.mw.screenshot
        h, w = frame.shape[0], frame.shape[1]
        status = ("Episode over — call reset_episode to start a fresh one."
                  if self._episode_over else "Episode in progress.")
        lines = [f"Task: \"{self.mw.utterance}\"", f"Screen size: {w}x{h}.", status,
                 f"To see the page, tile read_region crops (max {_REGION_MAX_SIDE}x{_REGION_MAX_SIDE} "
                 "source pixels each) over the screen and read the upscaled images."]
        return [{"type": "text", "text": "\n".join(lines)}]

    # -- read_region / whats_changed: same crop/upscale-PNG + mean-abs-diff helpers as World -------------

    def _read_region(self, args: dict) -> list[dict]:
        try:
            x0, y0, x1, y1 = (int(args["x0"]), int(args["y0"]), int(args["x1"]), int(args["y1"]))
        except (KeyError, TypeError, ValueError):
            return [{"type": "text", "text": "read_region needs integer x0, y0, x1, y1."}]
        step, frame = self._frame_hist[-1] if self._frame_hist else (self._step_count, self.mw.screenshot)
        err = World._validate_region(x0, y0, x1, y1, frame)
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
                 "text": f"[read_region step={step} ({x0},{y0})-({x1},{y1}), upscaled {_REGION_UPSCALE}x]"},
                {"type": "image", "data": png_b64, "mimeType": "image/png"}]

    def _whats_changed(self, args: dict) -> list[dict]:
        try:
            x0, y0, x1, y1 = (int(args["x0"]), int(args["y0"]), int(args["x1"]), int(args["y1"]))
        except (KeyError, TypeError, ValueError):
            return [{"type": "text", "text": "whats_changed needs integer x0, y0, x1, y1."}]
        if len(self._frame_hist) < 2:
            return [{"type": "text",
                    "text": "whats_changed: need two observed frames yet (only have "
                            f"{len(self._frame_hist)}) — call observe/click/etc. again first."}]
        (prev_step, prev), (curr_step, curr) = self._frame_hist[-2], self._frame_hist[-1]
        err = World._validate_region(x0, y0, x1, y1, curr)
        if err:
            return [{"type": "text", "text": f"whats_changed error: {err}"}]
        import numpy as np
        a = prev[y0:y1, x0:x1].astype(np.float32)
        b = curr[y0:y1, x0:x1].astype(np.float32)
        mad = float(np.mean(np.abs(a - b)))
        changed = mad >= 2.0
        return [{"type": "text",
                "text": f"[whats_changed step={curr_step} (vs step={prev_step}) ({x0},{y0})-({x1},{y1}): "
                        f"{'changed' if changed else 'unchanged'} (mean-abs-diff={mad:.2f})]"}]

    # -- dispatch ----------------------------------------------------------------------------------------

    @staticmethod
    def _sanitize_exc(e: BaseException) -> str:
        """Exception class + the FIRST line of its message only (truncated). Selenium exceptions can
        embed multi-line page/element/session dumps in str(e) — DOM-adjacent detail the brain must not
        see (PR #64 finding 4); the first line is the human-readable summary."""
        first = (str(e).splitlines() or [""])[0]
        return f"{type(e).__name__}: {first[:200]}"

    def call(self, name: str, args: dict) -> list[dict]:
        args = args or {}
        if name == "observe":
            return self._observe_content()
        if name == "read_region":
            return self._read_region(args)
        if name == "whats_changed":
            return self._whats_changed(args)
        if name == "reset_episode":
            try:
                self.mw.reset()
            except Exception as e:
                return [{"type": "text", "text": f"reset_episode error: {self._sanitize_exc(e)}"}]
            self._episode_over = False
            self._step_count += 1
            self._log_oracle(done=False)
            self._track_frame()
            return [{"type": "text", "text": "[reset_episode -> new episode started]"},
                    *self._observe_content()]
        # Action results deliberately do NOT include the env's terminated flag — that is the oracle's
        # verdict (PR #64 finding 3). The flag only updates observe's episode-status line + oracle.jsonl.
        if name == "click":
            if "x" not in args or "y" not in args:
                return [{"type": "text", "text": "click needs integer x and y."}]
            x_in, y_in = int(args["x"]), int(args["y"])
            # REJECT out-of-viewport clicks loudly instead of silently clamping: a silent clamp turns
            # "I clicked the thing at (50,190)" into an unrelated click at (50,176) — corrupted feedback
            # the brain can't detect (PR #64 finding 5). The band below y=176 is genuinely unreachable.
            if not (0 <= x_in < self._viewport_w and 0 <= y_in < self._viewport_h):
                return [{"type": "text",
                         "text": f"click error: ({x_in},{y_in}) is outside the clickable viewport "
                                 f"(x 0-{self._viewport_w - 1}, y 0-{self._viewport_h - 1}). The page "
                                 f"is taller than the viewport; anything below y={self._viewport_h - 1} "
                                 "is unreachable in this headless browser. No click was performed."}]
            try:
                _, ep_over = self.mw.click(x_in, y_in)
            except Exception as e:
                return [{"type": "text", "text": f"click error: {self._sanitize_exc(e)}"}]
            head = f"[click ({x_in},{y_in}) -> ok]"
        elif name == "type_text":
            if "text" not in args:
                return [{"type": "text", "text": "type_text needs a string `text`."}]
            try:
                _, ep_over = self.mw.type_text(str(args["text"]))
            except Exception as e:
                return [{"type": "text", "text": f"type_text error: {self._sanitize_exc(e)}"}]
            head = "[type_text -> ok]"
        elif name == "press_key":
            if "key" not in args:
                return [{"type": "text", "text": "press_key needs a string `key`."}]
            try:
                _, ep_over = self.mw.press_key(str(args["key"]))
            except Exception as e:
                return [{"type": "text", "text": f"press_key error: {self._sanitize_exc(e)}"}]
            head = f"[press_key {args['key']} -> ok]"
        else:
            return [{"type": "text", "text": f"unknown tool: {name}"}]
        self._episode_over = ep_over
        self._step_count += 1
        self._log_oracle(done=ep_over)
        self._track_frame()
        return [{"type": "text", "text": head}, *self._observe_content()]

    def close(self) -> None:
        self.mw.close()


class DoomDtcSession:
    """One live GATE-3D-A1 session over `scenarios/dtc_gate.cfg` (defend_the_center), served as an MCP
    tool surface. Standalone (not core.gateway.Gateway/GamePlugin) — mirrors MiniWobSession's shape: a
    thin dispatch class owning the world adapter directly.

    Design: reports/2026-07-04-vizdoom-3d-floor-design.md S3 + AMENDMENT A1.3/A1.4.

    Load-bearing invariant (PR #73 review finding, cited by the brief): P1 (core.yaw_flow.yaw_band_flow)
    is computed and LOGGED on EVERY action sub-step, inside turn_left/turn_right/attack themselves —
    NOT lazily inside observe(). The brain calls observe() whenever it wants a symbolic view, but it
    cannot suppress or delay when P1 actually runs; ARM (b) (grounding-honesty) is scored from THESE
    per-action-step log rows, not from however many times the brain happened to call observe. Each of
    `repeat`'s up-to-10 sub-steps gets its own P1 computation and its own oracle.jsonl row (frame-diffed
    against the frame immediately before it, never a frame several sub-steps back).

    Oracle law (unchanged): HEALTH/AMMO2/KILLCOUNT never appear in a tool result — logged to
    oracle.jsonl only, `{episode, step, tic, health, ammo2, killcount}` (design S3.3). P1/P2 readings
    are NOT oracle — they're the brain's own perception and are also logged (a separate, non-oracle
    grounding log) purely so ARM (b) can be scored after the fact from the run's own logs (design
    S2.2: "commanded actions are the truth; no oracle involved").

    One-attempt-per-seed enforcement (design A1.4 degenerate guard) lives HERE: `new_episode` called
    before the current episode's `is_episode_finished()` is True counts the CURRENT seed's episode as
    abandoned (KILLCOUNT logged at abandonment, no re-roll) and advances to the next pinned seed.
    """

    def __init__(self, args) -> None:
        from core.stationary_movers import stationary_movers
        from core.vizdoom_world import VizdoomWorld
        from core.yaw_flow import yaw_band_flow

        self._yaw_band_flow = yaw_band_flow
        self._stationary_movers = stationary_movers

        # --rom is not used for this world (there is one pinned scenario, GAMES["doom_dtc_gate"]["cfg"];
        # no .wad/.cfg override knob — the gate is pre-registered, not a --rom-swappable free parameter).
        self.world = VizdoomWorld(GAMES["doom_dtc_gate"]["cfg"])

        self._seeds = _load_doom_seeds(args)
        if not self._seeds:
            raise SystemExit("doom_dtc_gate needs at least one pinned seed: --seeds-file or --seed")
        self._seed_idx = 0

        os.makedirs(args.out, exist_ok=True)
        self._oracle_path = os.path.join(args.out, "oracle.jsonl")
        self._grounding_path = os.path.join(args.out, "grounding.jsonl")

        self._episode_step = 0        # step count WITHIN the current episode (oracle/grounding alignment)
        self.lessons: list[str] = []  # within-run self-improvement notes (learning-boundary law: discarded at exit)

        self._prev_gray: Optional[np.ndarray] = None   # frame immediately before the NEXT action sub-step
        self._last_p1_reading = None
        self._last_screen = None
        # The (before, after) pair the LAST action sub-step actually ran on — distinct from
        # _prev_gray/_last_screen (which roll forward to feed the *next* substep's P1 computation).
        # observe()'s P2 call must diff THIS pair, or it would diff the current frame against itself
        # (both rolled to the same post-action frame) and always report [] regardless of what moved.
        self._last_pair_gray: Optional[tuple[np.ndarray, np.ndarray]] = None

        self._start_episode(self._seeds[self._seed_idx])

    # -- episode lifecycle ------------------------------------------------------------------------

    def _start_episode(self, seed: int) -> None:
        result = self.world.reset(seed=seed)
        self._episode_step = 0
        self._prev_gray = _to_gray(result.screen) if result.screen is not None else None
        self._last_p1_reading = None
        self._last_screen = result.screen
        self._last_pair_gray = None   # no action has run yet this episode -- no pair to diff
        self._log_oracle(finished=False)

    def _advance_seed(self, *, abandoned: bool) -> bool:
        """Move to the next pinned seed. If `abandoned`, log the CURRENT (unfinished) episode's oracle
        row first (one-attempt-per-seed: an early new_episode counts this seed as over right now).
        Returns False if there is no next seed (caller should report exhaustion, not crash)."""
        if abandoned and not self.world.episode_finished:
            self._log_oracle(finished=True, abandoned=True)
        self._seed_idx += 1
        if self._seed_idx >= len(self._seeds):
            return False
        self._start_episode(self._seeds[self._seed_idx])
        return True

    # -- oracle / grounding logging (scoring only; never in a tool result) ------------------------

    def _log_oracle(self, *, finished: bool, abandoned: bool = False) -> None:
        gv = self.world.game_variables() or {}
        rec = {
            "episode": self._seed_idx, "seed": self._seeds[self._seed_idx],
            "step": self._episode_step, "tic": self.world.tic,
            "health": gv.get("HEALTH"), "ammo2": gv.get("AMMO2"), "killcount": gv.get("KILLCOUNT"),
            "finished": bool(finished), "abandoned": bool(abandoned),
        }
        try:
            with open(self._oracle_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except OSError:
            pass

    def _log_grounding(self, commanded: Optional[str], reading) -> None:
        """Per-action-step P1 log row (design S2.2 ARM (b) input) — commanded turn direction ("left"/
        "right"/None for attack) vs P1's OWN reading, by episode+step (never wall-clock, PR #55 lesson).
        `reading` may be None (attack sub-steps don't compute P1 at all — see turn/attack dispatch)."""
        rec = {"episode": self._seed_idx, "seed": self._seeds[self._seed_idx],
              "step": self._episode_step, "tic": self.world.tic, "commanded": commanded,
              "direction": None if reading is None else reading.direction,
              "dx_px": None if reading is None else reading.dx_px,
              "confidence": None if reading is None else reading.confidence}
        try:
            with open(self._grounding_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except OSError:
            pass

    # -- observe: P1 + P2 + episode status only — no screenshot, no game variables -----------------

    def _observe_content(self) -> list[dict]:
        finished = self.world.episode_finished
        if finished:
            lines = [f"Episode {self._seed_idx} (seed {self._seeds[self._seed_idx]}) finished at tic "
                    f"{self.world.tic}.",
                    ("Call new_episode to advance to the next pinned seed."
                     if self._seed_idx + 1 < len(self._seeds) else
                     "This was the last pinned seed — no more episodes.")]
            return [{"type": "text", "text": "\n".join(lines)}]

        reading = self._last_p1_reading
        if reading is None:
            ego = {"turning": None, "dx_px": None, "confidence": None}
        else:
            ego = {"turning": reading.direction, "dx_px": reading.dx_px, "confidence": reading.confidence}

        movers_out: Optional[list] = None
        if reading is not None and self._last_pair_gray is not None:
            before, after = self._last_pair_gray
            movers_out = self._stationary_movers(before, after, reading)

        lines = [
            f"ego: turning={ego['turning']!r} dx_px={ego['dx_px']!r} confidence={ego['confidence']!r}",
            f"movers: {_movers_repr(movers_out)}",
            f"episode: finished=False tic={self.world.tic} episode_index={self._seed_idx}",
        ]
        return [{"type": "text", "text": "\n".join(lines)}]

    # -- actions: turn_left / turn_right / attack — fixed tics=4, System-1 `repeat`, P1 EVERY sub-step

    def _do_action(self, button_name: str, commanded_dir: Optional[str], repeat: int) -> list[dict]:
        repeat = max(1, min(int(repeat), 10))
        for _ in range(repeat):
            if self.world.episode_finished:
                break
            prev_gray = self._prev_gray
            result = self.world.step(button_name, repeat=1)
            self._episode_step += 1
            cur_gray = _to_gray(result.screen) if result.screen is not None else None
            reading = None
            if prev_gray is not None and cur_gray is not None:
                # P1 computed HERE — every sub-step, unconditionally, before the brain ever asks for
                # an observation (the PR #73 review finding this class exists to satisfy).
                reading = self._yaw_band_flow(prev_gray, cur_gray)
            self._log_grounding(commanded_dir, reading)
            self._last_p1_reading = reading
            if prev_gray is not None and cur_gray is not None:
                self._last_pair_gray = (prev_gray, cur_gray)   # exactly what THIS sub-step ran on
            self._prev_gray = cur_gray
            self._last_screen = result.screen
            if result.episode_finished:
                self._log_oracle(finished=True)
                break
            else:
                self._log_oracle(finished=False)
        head = f"[{button_name.lower()} x{repeat} -> ok]"
        return [{"type": "text", "text": head}, *self._observe_content()]

    # -- dispatch --------------------------------------------------------------------------------

    def call(self, name: str, args: dict) -> list[dict]:
        args = args or {}
        if name == "observe":
            return self._observe_content()
        if name == "remember":
            lesson = str(args.get("lesson", "")).strip()
            if lesson and lesson not in self.lessons:
                self.lessons.append(lesson)
                del self.lessons[:-_MAX_LESSONS]
            return [{"type": "text", "text": f"Noted ({len(self.lessons)} lesson(s) this run)."},
                    *self._observe_content()]
        if name == "turn_left":
            return self._do_action("TURN_LEFT", "left", args.get("repeat", 1))
        if name == "turn_right":
            return self._do_action("TURN_RIGHT", "right", args.get("repeat", 1))
        if name == "attack":
            return self._do_action("ATTACK", None, args.get("repeat", 1))
        if name == "new_episode":
            had_more = self._advance_seed(abandoned=True)
            if not had_more:
                return [{"type": "text", "text": "[new_episode -> no more pinned seeds]"}]
            return [{"type": "text", "text": "[new_episode -> started]"}, *self._observe_content()]
        return [{"type": "text", "text": f"unknown tool: {name}"}]

    def close(self) -> None:
        self.world.close()


class ArcAgi3Session:
    """One live ARC-AGI-3 game session over the public REST API, served as an MCP tool surface.
    Standalone (not core.gateway.Gateway/GamePlugin) — mirrors MiniWobSession/DoomDtcSession's shape:
    a thin dispatch class owning the world adapter (core/arcagi3_world.ArcAgi3Client) directly.

    Design: runs/arcagi3_probe/PROBE_REPORT.md "Seam sketch" section.

    No-leak law: `levels_completed`/`win_levels`/`state` are the oracle here — logged to
    <out>/oracle.jsonl by _log_oracle, NEVER placed in a tool result (same separation as
    MiniWobSession's reward/dom_elements, DoomDtcSession's HEALTH/AMMO2/KILLCOUNT). This differs from
    the probe report's open question 7 recommendation (brain-visible levels_completed) — the task
    brief is explicit that levels_completed/win-state must stay oracle-only, so that's what's built;
    revisit only with an explicit sign-off, per the probe report's own flag.

    Grid vs oracle: the GRID itself is fully brain-visible (it's the whole observable screen, not a
    hidden RAM value) — only the score/win-state bookkeeping is withheld.
    """

    def __init__(self, args) -> None:
        from core.arcagi3_world import ArcAgi3Client, diff_grids, render_grid

        self._diff_grids = diff_grids
        self._render_grid = render_grid

        game_id = getattr(args, "arc_game", None)
        if not game_id:
            raise SystemExit("arcagi3 needs --arc-game <game_id> (e.g. ls20)")
        self._game_id = game_id

        os.makedirs(args.out, exist_ok=True)
        self._oracle_path = os.path.join(args.out, "oracle.jsonl")

        self.client = ArcAgi3Client()
        self.lessons: list[str] = []   # within-run self-improvement notes (learning-boundary law: discarded at exit)
        self._step_count = 0
        self._prev_grid: Optional[list] = None
        self._last_grid: list = []
        self._last_available_actions: list = []
        self._last_state = "NOT_FINISHED"
        self._last_diff: dict = {"changed": 0, "by_color": {}, "note": "first frame -- nothing to diff"}
        self._unchanged_run = 0   # consecutive world steps with an all-cells-identical diff (grid_unchanged_for)

        # Skill compilation rung 1 (reports/2026-07-03-skill-compilation-design.md): within-run only,
        # blank-agent law — this dict lives exactly as long as `self` does, never written to disk,
        # never read back across a session boundary (same lifetime/shape as `self.lessons`).
        self.skills: dict[str, dict] = {}
        self._skill_log_path = os.path.join(args.out, "skills.jsonl")
        # A/B arm isolation (doc §4.1): read ARC_SKILLS ONCE at session init, not per call — the env
        # can't flip mid-session and change which arm this session is. tools/list already hides
        # define_skill/run_skill when off; this is defense-in-depth so a client that calls them anyway
        # (stale tool list, hand-rolled request) still gets a clear refusal, not silent execution.
        self._skills_enabled = _arc_skills_enabled()

        self.client.open_scorecard(tags=["ai-pokemon-red", "arcagi3_world"],
                                   source_url="ai-pokemon-red/world_mcp.py")
        self._apply_frame(self.client.reset(game_id))

    # -- oracle logging (scoring only; never in a tool result) -----------------------------------------

    def _log_oracle(self, fr) -> None:
        rec = {"step": self._step_count, "game_id": self._game_id, "action": fr.action, "args": fr.args,
              "state": fr.state, "levels_completed": fr.levels_completed, "win_levels": fr.win_levels,
              "frame_count": fr.frame_count}
        try:
            with open(self._oracle_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except OSError:
            pass

    # -- skill auditability logging (world/ sibling of oracle.jsonl, same append-only jsonl shape) -----
    # Doc §3 "auditability": every define_skill logs the full definition verbatim; every run_skill logs
    # executed steps, iteration counts, which stop_when fired, and the executed-step count (the
    # >=3-executed-steps gate rule from the doc's §4 gate needs this to be scoreable offline).

    def _log_skill(self, rec: dict) -> None:
        try:
            with open(self._skill_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except OSError:
            pass

    # -- frame bookkeeping: track prev/current grid for the diff-summary, update legal actions/state ---

    def _apply_frame(self, fr) -> None:
        # Prior-grid gate (PR #77 review finding 2): a RESET frame starts a fresh instance, so it has
        # no prior to diff against; EVERY other frame diffs against the grid we last held — never gate
        # on _step_count (client.reset() hardcodes step=0, so a step-count gate wrongly reported
        # "first frame" on the first post-action observe of every episode).
        prior = None if fr.action == "RESET" else self._last_grid
        self._prev_grid = prior
        self._last_diff = self._diff_grids(prior, fr.grid)
        self._last_grid = fr.grid
        self._last_available_actions = list(fr.available_actions)
        self._last_state = fr.state
        self._step_count = fr.step
        self._log_oracle(fr)
        # grid_unchanged_for(k): a RESET has no prior (never counts as "unchanged"); any other frame
        # extends the run only if EVERY cell matched the prior grid (changed == 0, not a shape-change,
        # which diff_grids reports as changed == -1 and must not count as "unchanged" either).
        if fr.action == "RESET":
            self._unchanged_run = 0
        elif self._last_diff.get("changed", -1) == 0:
            self._unchanged_run += 1
        else:
            self._unchanged_run = 0

    # -- observe: grid + diff-summary + available_actions + step — no levels_completed/win_levels ------

    def _observe_content(self) -> list[dict]:
        grid_text = self._render_grid(self._last_grid)
        diff = self._last_diff
        if diff.get("changed", 0) < 0:
            diff_line = f"grid changed shape: {diff.get('note', '')}"
        elif diff.get("changed", 0) == 0 and diff.get("note"):
            diff_line = diff["note"]
        else:
            by_color = ", ".join(f"{k}x{v}" for k, v in sorted(diff.get("by_color", {}).items()))
            diff_line = f"{diff.get('changed', 0)} cell(s) changed" + (f" ({by_color})" if by_color else "")
        status = ("GAME OVER — call reset_game to try again." if self._last_state == "GAME_OVER" else
                  "YOU WIN — call reset_game to play again." if self._last_state == "WIN" else
                  "in progress")
        lines = [
            f"grid ({len(self._last_grid)}x{len(self._last_grid[0]) if self._last_grid else 0}):",
            grid_text,
            f"diff since last action: {diff_line}",
            f"available_actions: {self._last_available_actions}",
            f"step: {self._step_count}",
            f"status: {status}",
        ]
        return [{"type": "text", "text": "\n".join(lines)}]

    # -- act: validate against CURRENT available_actions; ACTION6 needs x,y — reject loudly, no clamp --

    def _act_raw(self, name: str, args: dict) -> Optional[str]:
        """Validate + execute one primitive action step; on success calls _apply_frame and returns
        None; on failure returns an error string and touches nothing (no action was sent). Shared by
        the `act` tool and `run_skill`'s step dispatcher (doc §3 "honest accounting": every skill step
        resolves to an existing primitive's EXACT execution path — same validation, same logging, same
        oracle write — so no step can do anything a primitive call couldn't)."""
        name = str(name).strip().upper()
        if not name:
            return "act needs a string `action` (e.g. \"ACTION1\")."
        from core.arcagi3_world import ALL_ACTIONS, COORD_ACTION
        if name not in ALL_ACTIONS:
            return f"act error: {name!r} is not a valid action; must be one of {list(ALL_ACTIONS)}."
        # numeric id ARC uses in available_actions (e.g. [1,2,3,4]) vs our "ACTION{n}" name
        try:
            action_id = int(name.replace("ACTION", ""))
        except ValueError:
            return f"act error: could not parse action id from {name!r}."
        if self._last_state in ("WIN", "GAME_OVER"):
            return (f"act error: the game is over (state={self._last_state}) — only "
                    "reset_game is legal now. No action was sent.")
        if action_id not in self._last_available_actions:
            return (f"act error: {name} is not currently legal — available_actions is "
                    f"{self._last_available_actions}. No action was sent.")
        x = y = None
        if name == COORD_ACTION:
            if "x" not in args or "y" not in args:
                return "act error: ACTION6 requires integer x and y (0-63). No action was sent."
            try:
                x, y = int(args["x"]), int(args["y"])
            except (TypeError, ValueError):
                return "act error: x and y must be integers. No action was sent."
            if not (0 <= x <= 63 and 0 <= y <= 63):
                return f"act error: x,y must be in [0, 63]; got ({x}, {y}). No action was sent."
        try:
            fr = self.client.action(name, self._step_count + 1, x=x, y=y)
        except Exception as e:
            return f"act error: {type(e).__name__}: {e}"
        self._apply_frame(fr)
        return None

    def _act(self, args: dict) -> list[dict]:
        name = str(args.get("action", "")).strip().upper()
        err = self._act_raw(name, args)
        if err is not None:
            return [{"type": "text", "text": err}]
        x, y = args.get("x"), args.get("y")
        from core.arcagi3_world import COORD_ACTION
        head = f"[act {name}" + (f" ({x},{y})" if name == COORD_ACTION else "") + " -> ok]"
        return [{"type": "text", "text": head}, *self._observe_content()]

    # -- skill compilation rung 1: define_skill/run_skill (ARC port only) --------------------------------
    # Formalism per reports/2026-07-03-skill-compilation-design.md §3: `steps` is a list of plain action
    # steps and/or ONE bounded loop construct `repeat_until` (no nesting). Every stop_when predicate is
    # computed WORLD-SIDE from data already on this world's wire (diffs of consecutive grids `observe`
    # already returns, or a step counter) — never an oracle/RAM/score field.

    @staticmethod
    def _parse_stop_when(expr: str):
        """Parse one of the three pinned ARC predicates into (kind, params). Raises ValueError (caught
        by the caller, turned into a tool-result error, never a crash) on anything outside the closed
        enum — `stop_when` predicates are a fixed closed set, never learned/invented (doc §6)."""
        import re
        expr = (expr or "").strip()
        m = re.fullmatch(r"grid_changed_in_region\(\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\)", expr)
        if m:
            x0, y0, x1, y1 = (int(g) for g in m.groups())
            # Reject loudly at define time (PR #89 review finding 1: a negative/out-of-range/inverted
            # box would silently produce an empty scan range — the predicate could never fire and the
            # brain would read "region never changed" instead of "your region was malformed"). Same
            # 64x64 bound as ACTION6's x,y validation, same reject-loudly-never-clamp discipline.
            if not (0 <= x0 <= x1 <= 63 and 0 <= y0 <= y1 <= 63):
                raise ValueError("grid_changed_in_region(x0,y0,x1,y1): need 0 <= x0 <= x1 <= 63 and "
                                 f"0 <= y0 <= y1 <= 63; got ({x0},{y0},{x1},{y1})")
            return ("grid_changed_in_region", {"x0": x0, "y0": y0, "x1": x1, "y1": y1})
        m = re.fullmatch(r"grid_unchanged_for\(\s*(\d+)\s*\)", expr)
        if m:
            k = int(m.group(1))
            if not (1 <= k <= _SKILL_UNCHANGED_FOR_MAX):
                raise ValueError(f"grid_unchanged_for(k): k must be in [1, {_SKILL_UNCHANGED_FOR_MAX}]; got {k}")
            return ("grid_unchanged_for", {"k": k})
        m = re.fullmatch(r"steps_elapsed\(\s*(\d+)\s*\)", expr)
        if m:
            n = int(m.group(1))
            if not (1 <= n <= _SKILL_STEPS_ELAPSED_MAX):
                raise ValueError(f"steps_elapsed(n): n must be in [1, {_SKILL_STEPS_ELAPSED_MAX}]; got {n}")
            return ("steps_elapsed", {"n": n})
        raise ValueError(f"stop_when {expr!r} is not one of the pinned ARC predicates: "
                         "grid_changed_in_region(x0,y0,x1,y1), grid_unchanged_for(k<=8), steps_elapsed(n<=50).")

    def _validate_step_list(self, steps, *, inside_loop: bool) -> Optional[str]:
        """Structural validation at define_skill time (fail loud before storing a broken skill, never
        at run_skill time). Returns an error string, or None if `steps` is well-formed. Enforces
        no-nesting (doc §3: "repeat_until may not contain another repeat_until") and max_iters<=8."""
        if not isinstance(steps, list) or not steps:
            return "define_skill error: `steps` must be a non-empty list."
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                return f"define_skill error: step {i} must be an object; got {type(step).__name__}."
            if "repeat_until" in step:
                if inside_loop:
                    return (f"define_skill error: step {i} is a repeat_until nested inside another "
                            "repeat_until — nesting is not allowed (doc §3, pinned).")
                loop = step["repeat_until"]
                if not isinstance(loop, dict):
                    return f"define_skill error: step {i}'s repeat_until must be an object."
                inner = loop.get("steps")
                stop_when = loop.get("stop_when")
                max_iters = loop.get("max_iters")
                if not isinstance(max_iters, int) or not (1 <= max_iters <= _SKILL_MAX_ITERS):
                    return (f"define_skill error: step {i}'s repeat_until.max_iters must be an int in "
                            f"[1, {_SKILL_MAX_ITERS}]; got {max_iters!r}.")
                try:
                    self._parse_stop_when(stop_when)
                except ValueError as e:
                    return f"define_skill error: step {i}'s repeat_until.stop_when invalid: {e}"
                err = self._validate_step_list(inner, inside_loop=True)
                if err:
                    return err
            elif "action" in step:
                name = str(step.get("action", "")).strip().upper()
                from core.arcagi3_world import ALL_ACTIONS
                if name not in ALL_ACTIONS:
                    return f"define_skill error: step {i}'s action {name!r} is not a valid ARC action."
            else:
                return f"define_skill error: step {i} must have either \"action\" or \"repeat_until\"."
        return None

    def _define_skill(self, args: dict) -> list[dict]:
        skill_name = str(args.get("name", "")).strip()
        if not skill_name:
            return [{"type": "text", "text": "define_skill error: `name` must be a non-empty string."}]
        if "stop_when" in args:
            # PR #89 review finding: a top-level stop_when has NO effect (it belongs inside a
            # repeat_until step) — silently ignoring it would let the brain believe a condition was
            # armed when it wasn't. Reject loudly; nothing is defined.
            return [{"type": "text",
                     "text": "define_skill error: `stop_when` belongs INSIDE a repeat_until step "
                             "({\"repeat_until\": {\"steps\": [...], \"stop_when\": \"...\", "
                             "\"max_iters\": N}}), not at the top level — it would have no effect "
                             "there. Skill NOT defined."}]
        steps = args.get("steps")
        err = self._validate_step_list(steps, inside_loop=False)
        if err:
            return [{"type": "text", "text": err}]
        definition = {"name": skill_name, "steps": steps}
        prior = self.skills.get(skill_name)
        self.skills[skill_name] = definition
        # Auditability (doc §3): the full definition is logged verbatim, so a reviewer can see exactly
        # what macro was compiled and when. A redefinition is a DISTINCT event carrying both the old
        # and new definitions (PR #89 review finding 3: a silent overwrite would leave two same-name
        # define rows with no signal which one was live at a given transcript position).
        if prior is not None:
            self._log_skill({"event": "redefine_skill", "step": self._step_count,
                             "prior_definition": prior, "definition": definition})
            return [{"type": "text",
                     "text": f"[define_skill {skill_name!r} -> ok, REPLACED your prior definition of "
                             f"the same name; {len(steps)} top-level step(s)] "
                             f"Call run_skill({{\"name\": {skill_name!r}}}) to execute it."}]
        self._log_skill({"event": "define_skill", "step": self._step_count, "definition": definition})
        return [{"type": "text",
                 "text": f"[define_skill {skill_name!r} -> ok, {len(steps)} top-level step(s)] "
                         f"Call run_skill({{\"name\": {skill_name!r}}}) to execute it."}]

    def _check_stop_when(self, kind: str, params: dict, *, loop_world_steps: int) -> bool:
        """Evaluate one pinned predicate after a world step. `grid_changed_in_region` diffs the two
        CONSECUTIVE post-action grids (doc §3's exact definition — the same prev/last pair the
        diff-summary already reports); `grid_unchanged_for` reads the running identical-grid counter;
        `steps_elapsed` compares WORLD steps executed inside the current repeat_until (PR #89 review:
        world steps, never loop iterations — a 2-action inner list reaches steps_elapsed(4) after 2
        passes)."""
        if kind == "grid_changed_in_region":
            x0, y0, x1, y1 = params["x0"], params["y0"], params["x1"], params["y1"]
            prev, curr = self._prev_grid, self._last_grid
            if prev is None or not curr:
                return False
            for y in range(y0, min(len(curr), y1 + 1)):
                row_prev = prev[y] if y < len(prev) else []
                row_curr = curr[y]
                for x in range(x0, min(len(row_curr), x1 + 1)):
                    prev_v = row_prev[x] if x < len(row_prev) else None
                    if prev_v != row_curr[x]:
                        return True
            return False
        if kind == "grid_unchanged_for":
            return self._unchanged_run >= params["k"]
        if kind == "steps_elapsed":
            return loop_world_steps >= params["n"]
        return False   # unreachable: _parse_stop_when already rejected anything else

    def _exec_primitive(self, step: dict, executed: list, world_step_budget: list) -> Optional[str]:
        """Execute ONE primitive action step via _act_raw. The budget is decremented ONLY on success
        (PR #89 review finding: a rejected step sent nothing to the world — _act_raw's own contract —
        so world_steps_used must mean actual world activity, never attempts). Returns an error string
        (ceiling hit / step rejected / API failure) or None."""
        if world_step_budget[0] <= 0:
            return f"stopped: absolute {_SKILL_MAX_WORLD_STEPS}-world-step ceiling hit"
        name = str(step.get("action", "")).strip().upper()
        err = self._act_raw(name, step)
        step_args = {k: v for k, v in step.items() if k != "action"}
        if err is not None:
            executed.append({"action": name, "args": step_args, "ok": False, "error": err})
            return err
        world_step_budget[0] -= 1
        executed.append({"action": name, "args": step_args, "ok": True})
        return None

    def _run_steps_once(self, steps, executed: list, world_step_budget: list) -> Optional[str]:
        """Execute the top-level step list: plain action steps and/or repeat_until blocks (whose inner
        lists are guaranteed flat — no nesting, enforced at define time). Inside a repeat_until,
        stop_when is checked after EVERY world step (doc §3: "checking stop_when after each step"), so
        it can fire mid-iteration of a multi-action inner list — the iteration count in the summary
        then includes the partial iteration. Returns an error string and stops immediately if a step
        fails or the absolute world-step ceiling is hit; None on a clean pass."""
        for step in steps:
            if "repeat_until" in step:
                loop = step["repeat_until"]
                inner = loop["steps"]
                kind, params = self._parse_stop_when(loop["stop_when"])
                max_iters = loop["max_iters"]
                iters_done = 0
                loop_world_steps = 0   # WORLD steps executed inside THIS loop (steps_elapsed's unit)
                stop_reason = None
                while iters_done < max_iters and stop_reason is None:
                    for inner_step in inner:
                        err = self._exec_primitive(inner_step, executed, world_step_budget)
                        if err:
                            return err
                        loop_world_steps += 1
                        if self._check_stop_when(kind, params, loop_world_steps=loop_world_steps):
                            stop_reason = (f"stop_when {loop['stop_when']!r} fired after "
                                           f"{loop_world_steps} world step(s) "
                                           f"({iters_done + 1} iteration(s))")
                            break
                    iters_done += 1
                if stop_reason is None:
                    stop_reason = f"repeat_until reached max_iters={max_iters} without stop_when firing"
                executed.append({"repeat_until_summary": stop_reason, "iterations": iters_done,
                                 "world_steps": loop_world_steps})
            else:
                err = self._exec_primitive(step, executed, world_step_budget)
                if err:
                    return err
        return None

    def _run_skill(self, args: dict) -> list[dict]:
        skill_name = str(args.get("name", "")).strip()
        definition = self.skills.get(skill_name)
        if definition is None:
            return [{"type": "text",
                     "text": f"run_skill error: no skill named {skill_name!r} — call define_skill "
                             "first (skills are within-run only, not persisted)."}]
        executed: list = []
        world_step_budget = [_SKILL_MAX_WORLD_STEPS]   # absolute ceiling, enforced world-side (doc §3)
        error = self._run_steps_once(definition["steps"], executed, world_step_budget)
        # "executed" (the doc's >=3-executed-steps qualifying-call gate) means SUCCEEDED, not merely
        # attempted -- a rejected/illegal step (ok: False) advanced no world state, so it must not count.
        executed_primitive_count = sum(1 for e in executed if e.get("ok") is True)
        if error is not None:
            stop_reason = error
        elif executed and "repeat_until_summary" in executed[-1]:
            # A clean pass whose LAST top-level step was a loop: surface that loop's own fired-reason
            # (grid_changed_in_region/grid_unchanged_for/steps_elapsed, or "reached max_iters") rather
            # than a generic "completed" message — this is the load-bearing signal per doc §3.
            stop_reason = executed[-1]["repeat_until_summary"]
        else:
            stop_reason = "all top-level steps executed"
        log_rec = {"event": "run_skill", "step": self._step_count, "name": skill_name,
                   "executed": executed, "executed_step_count": executed_primitive_count,
                   "stop_reason": stop_reason,
                   "world_steps_used": _SKILL_MAX_WORLD_STEPS - world_step_budget[0]}
        self._log_skill(log_rec)
        head = (f"[run_skill {skill_name!r} -> {executed_primitive_count} step(s) executed; "
                f"stopped because: {stop_reason}]")
        return [{"type": "text", "text": head}, *self._observe_content()]

    # -- dispatch ----------------------------------------------------------------------------------------

    def call(self, name: str, args: dict) -> list[dict]:
        args = args or {}
        if name == "observe":
            return self._observe_content()
        if name == "remember":
            lesson = str(args.get("lesson", "")).strip()
            if lesson and lesson not in self.lessons:
                self.lessons.append(lesson)
                del self.lessons[:-_MAX_LESSONS]
            return [{"type": "text", "text": f"Noted ({len(self.lessons)} lesson(s) this run)."},
                    *self._observe_content()]
        if name == "act":
            return self._act(args)
        if name == "define_skill":
            if not self._skills_enabled:
                return [{"type": "text",
                         "text": "define_skill error: skill tools are disabled for this session "
                                 "(set ARC_SKILLS=1 in the environment to enable — see "
                                 "reports/2026-07-03-skill-compilation-design.md §4.1, Arm A must not "
                                 "have this tool at all)."}]
            return self._define_skill(args)
        if name == "run_skill":
            if not self._skills_enabled:
                return [{"type": "text",
                         "text": "run_skill error: skill tools are disabled for this session (set "
                                 "ARC_SKILLS=1 in the environment to enable — see "
                                 "reports/2026-07-03-skill-compilation-design.md §4.1, Arm A must not "
                                 "have this tool at all)."}]
            return self._run_skill(args)
        if name == "reset_game":
            try:
                fr = self.client.reset(self._game_id)
            except Exception as e:
                return [{"type": "text", "text": f"reset_game error: {type(e).__name__}: {e}"}]
            self._apply_frame(fr)
            return [{"type": "text", "text": "[reset_game -> new instance started]"},
                    *self._observe_content()]
        return [{"type": "text", "text": f"unknown tool: {name}"}]

    def close(self) -> None:
        try:
            self.client.close_scorecard()
        except Exception:
            pass


def _to_gray(screen: np.ndarray) -> np.ndarray:
    return np.asarray(screen)[..., :3].mean(axis=2).astype(np.float32)


def _movers_repr(movers) -> str:
    if movers is None:
        return "null (not ego-stationary)"
    if not movers:
        return "[] (confidently nothing moving)"
    return "[" + ", ".join(
        f"{{azimuth_px={m.azimuth_px:.0f}, azimuth_deg={m.azimuth_deg}, area={m.area}, "
        f"bbox={m.bbox}, confidence={m.confidence:.2f}}}" for m in movers
    ) + "]"


def _load_doom_seeds(args) -> list[int]:
    """Pinned-seed source: --seeds-file (one int per line, OR a JSON array — e.g. the committed
    eval/fixtures/gate3d_seeds.json) takes priority; else --seed (repeatable). Never invents a seed —
    an empty result is a launch-time error (see DoomDtcSession.__init__)."""
    seeds_file = getattr(args, "seeds_file", None)
    if seeds_file:
        with open(seeds_file, encoding="utf-8") as f:
            text = f.read()
        stripped = text.strip()
        if stripped.startswith("["):
            return [int(s) for s in json.loads(stripped)]
        return [int(line.strip()) for line in text.splitlines() if line.strip()]
    return [int(s) for s in (getattr(args, "seed", None) or [])]


def main() -> int:
    ap = argparse.ArgumentParser(description="MCP (stdio) server exposing a Game Boy (or MiniWoB++ "
                                              "computer-use) world as tools.")
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
    ap.add_argument("--seeds-file", default=None,
                    help="doom_dtc_gate only: path to a file of pinned seeds, one int per line "
                         "(GATE-3D-A1 §2.2/A1.4: distinct pinned seeds, one attempt each).")
    ap.add_argument("--seed", action="append", type=int, default=None,
                    help="doom_dtc_gate only: a pinned seed (repeatable, e.g. --seed 1 --seed 2 ...); "
                         "ignored if --seeds-file is given.")
    ap.add_argument("--arc-game", default=None,
                    help="arcagi3 only: the ARC-AGI-3 game_id to play (e.g. ls20). Requires "
                         "ARC_API_KEY in the environment (never passed as a CLI flag or logged).")
    args = ap.parse_args()

    # Argument validation that must fail AT LAUNCH, not on the lazily-deferred first tool call (a
    # SystemExit escaping mid-protocol kills the server after the handshake — worse than refusing to
    # start). --record only threads through the default PyBoy recorder path; miniwob has no frame
    # pipeline (house rule: fail loud rather than silently write no MP4, same as the GBA/NDS guard).
    if args.record and args.game in _MINIWOB_WORLDS:
        raise SystemExit("--record is not supported for miniwob worlds: recording threads only "
                         "through the default PyBoy emulator path. There is no per-step frame log "
                         "for this family yet either — drop --record.")
    if args.record and args.game in _VIZDOOM_WORLDS:
        raise SystemExit("--record is not supported for doom_dtc_gate: recording threads only "
                         "through the default PyBoy emulator path. Drop --record.")
    # Same reasoning: a missing pinned seed must fail AT LAUNCH — DoomDtcSession is built lazily on the
    # first tool call, and a SystemExit escaping from there would kill the server mid-protocol instead
    # of refusing to start (the PR #64 re-validation nit this mirrors).
    if args.game in _VIZDOOM_WORLDS and not _load_doom_seeds(args):
        raise SystemExit("doom_dtc_gate needs at least one pinned seed: --seeds-file or --seed")
    if args.game in _ARCAGI3_WORLDS and not args.arc_game:
        raise SystemExit("arcagi3 needs --arc-game <game_id> (e.g. ls20)")
    # A missing/empty ARC_API_KEY must fail AT LAUNCH too (PR #77 review finding 1): ArcAgi3Session
    # is built lazily on the first tool call, and an empty key there dies with a generic 401
    # mid-protocol instead of a clear refusal to start — the exact failure mode the seed/--record
    # guards around this exist to avoid. Only the key's ABSENCE is reported, never its value.
    if args.game in _ARCAGI3_WORLDS and not os.environ.get("ARC_API_KEY"):
        raise SystemExit("arcagi3 needs ARC_API_KEY in the environment (launchers must pass it "
                         "through, e.g. docker -e ARC_API_KEY or the WSL env — never a CLI flag).")
    if args.record and args.game in _ARCAGI3_WORLDS:
        raise SystemExit("--record is not supported for arcagi3: there is no pixel frame pipeline for "
                         "this world at all (the grid is text, not a rendered frame). Drop --record.")

    # LAZY: do NOT boot the emulator/browser here. `initialize`/`tools/list` must answer instantly or the
    # MCP client times out the startup handshake and marks the server "not connected". The World (PyBoy)
    # or MiniWobSession (Selenium) / DoomDtcSession (ViZDoom) is built on the first tool CALL, which the
    # client waits on as a normal request (no startup timeout).
    _is_miniwob = args.game in _MINIWOB_WORLDS
    _is_vizdoom = args.game in _VIZDOOM_WORLDS
    _is_arcagi3 = args.game in _ARCAGI3_WORLDS
    _world: list = [None]
    def _close_world(w) -> None:
        # World's emulator lives at w.plugin; MiniWobSession/DoomDtcSession/ArcAgi3Session close
        # themselves directly — same lazy-boot slot, different shapes, so shutdown/EOF-close needs to
        # know which.
        (w.close() if (_is_miniwob or _is_vizdoom or _is_arcagi3) else w.plugin.close())

    def world():
        if _world[0] is None:
            if _is_miniwob:
                _world[0] = MiniWobSession(args)
            elif _is_vizdoom:
                _world[0] = DoomDtcSession(args)
            elif _is_arcagi3:
                _world[0] = ArcAgi3Session(args)
            else:
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
                _close_world(_world[0])
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
                # MiniWob family: a raw Selenium exception message can embed page/element/session dumps
                # (DOM-adjacent detail) — forward only class + first line (PR #64 finding 4). MiniWob
                # in-session action errors are already sanitized inside MiniWobSession.call; this covers
                # construction-time failures (browser boot, first reset) that surface here.
                text = f"error: {MiniWobSession._sanitize_exc(e)}" if _is_miniwob else f"error: {e}"
                _send({"jsonrpc": "2.0", "id": mid,
                       "result": {"content": [{"type": "text", "text": text}], "isError": True}})
        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": mid, "result": {}})
        elif method is None:
            _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32600, "message": "Invalid Request: no method"}})
        else:
            _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}})

    # client disconnected (stdin EOF) -> stop the emulator/browser and FINALIZE the --record MP4 (imageio
    # needs close()).
    if _world[0] is not None:
        try:
            _close_world(_world[0])
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
