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


def _arcagi3_static_tools() -> list[dict]:
    """tools/list response for arcagi3 — identical regardless of which --arc-game is chosen."""
    return [_ARCAGI3_OBSERVE_TOOL, _REMEMBER_TOOL, *_ARCAGI3_ACTION_TOOLS]


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

    def _act(self, args: dict) -> list[dict]:
        name = str(args.get("action", "")).strip().upper()
        if not name:
            return [{"type": "text", "text": "act needs a string `action` (e.g. \"ACTION1\")."}]
        from core.arcagi3_world import ALL_ACTIONS, COORD_ACTION
        if name not in ALL_ACTIONS:
            return [{"type": "text", "text": f"act error: {name!r} is not a valid action; must be one "
                                             f"of {list(ALL_ACTIONS)}."}]
        # numeric id ARC uses in available_actions (e.g. [1,2,3,4]) vs our "ACTION{n}" name
        try:
            action_id = int(name.replace("ACTION", ""))
        except ValueError:
            return [{"type": "text", "text": f"act error: could not parse action id from {name!r}."}]
        if self._last_state in ("WIN", "GAME_OVER"):
            return [{"type": "text",
                     "text": f"act error: the game is over (state={self._last_state}) — only "
                             "reset_game is legal now. No action was sent."}]
        if action_id not in self._last_available_actions:
            return [{"type": "text",
                     "text": f"act error: {name} is not currently legal — available_actions is "
                             f"{self._last_available_actions}. No action was sent."}]
        x = y = None
        if name == COORD_ACTION:
            if "x" not in args or "y" not in args:
                return [{"type": "text", "text": "act error: ACTION6 requires integer x and y (0-63). "
                                                 "No action was sent."}]
            try:
                x, y = int(args["x"]), int(args["y"])
            except (TypeError, ValueError):
                return [{"type": "text", "text": "act error: x and y must be integers. No action was sent."}]
            if not (0 <= x <= 63 and 0 <= y <= 63):
                return [{"type": "text",
                         "text": f"act error: x,y must be in [0, 63]; got ({x}, {y}). No action was sent."}]
        try:
            fr = self.client.action(name, self._step_count + 1, x=x, y=y)
        except Exception as e:
            return [{"type": "text", "text": f"act error: {type(e).__name__}: {e}"}]
        self._apply_frame(fr)
        head = f"[act {name}" + (f" ({x},{y})" if x is not None else "") + " -> ok]"
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
