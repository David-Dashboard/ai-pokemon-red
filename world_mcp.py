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
import json
import uuid

# Run from the repo root so `import core` and relative rom/run paths resolve regardless of launch cwd.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from core.brains import ExploreBrain        # noqa: E402  (the free System-1 autopilot)
from core.contracts import ToolCall         # noqa: E402
from core.gateway import Gateway            # noqa: E402
from games.cave_noire import CAVE_NOIRE_SANDBOX, CaveNoirePlugin  # noqa: E402
from games.cave_noire.perceiver import CaveNoirePerceiver         # noqa: E402

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


def _send(msg: dict) -> None:
    _OUT.write(json.dumps(msg) + "\n")
    _OUT.flush()


class World:
    """One live perception-only Cave Noire session, driven through the existing Gateway + plugin."""

    def __init__(self, args) -> None:
        self.with_screenshot = bool(args.with_screenshot)
        header = ("Top-down dungeon exploration. Perception is approximate; a screenshot is attached."
                  if self.with_screenshot else
                  "Top-down dungeon exploration. You perceive only this symbolic view — reason from it.")
        self.plugin = CaveNoirePlugin(rom_path=args.rom, out_dir=args.out, headless=True,
                                      init_state=args.init_state, perceiver=CaveNoirePerceiver(),
                                      watch={"x": 0xC504, "y": 0xC503},  # RAM -> oracle.jsonl ONLY, never the wire
                                      render_header=header)
        self.gw = Gateway(self.plugin, CAVE_NOIRE_SANDBOX)
        self.explore = ExploreBrain(_AGENT, single_step=True)   # Cave Noire is turn-based: one press/move
        # within-run self-improvement state (discarded at process end — the learning-boundary law)
        self.lessons: list[str] = []
        self.decisions = 0       # your LLM wakes (press/goto/explore) — the cost the north star keeps LOW
        self.auto_tiles = 0      # tiles the free System-1 autopilot walked for you (free; NOT the cost metric)
        self.visited = 0         # cells explored so far (progress); improvement = more cells per decision (wake)

    def tools(self) -> list[dict]:
        action = [{"name": s.name, "description": s.description, "inputSchema": s.schema}
                  for s in self.plugin.tools(_AGENT)]
        return [_OBSERVE_TOOL, _EXPLORE_TOOL, _GOTO_TOOL, _REMEMBER_TOOL, *action]

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

    @staticmethod
    def _drop_frame(obs) -> None:
        p = (obs.data or {}).get("screen_path") or ""   # don't accumulate frame debris (oracle.jsonl keeps the record)
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

    def _content(self, obs) -> list[dict]:
        sm = (obs.data or {}).get("spatial_memory") or {}
        if isinstance(sm.get("visited"), int):
            self.visited = sm["visited"]        # track progress (cells explored) for the cost-per-progress signal
        content: list[dict] = [{"type": "text", "text": self._fix_text(obs.text)}]
        p = (obs.data or {}).get("screen_path") or ""
        if p and os.path.exists(p):
            if self.with_screenshot:
                with open(p, "rb") as f:
                    content.append({"type": "image", "data": base64.b64encode(f.read()).decode(),
                                    "mimeType": "image/png"})
            try:
                os.remove(p)
            except OSError:
                pass
        return content

    # -- the free System-1 autopilot (dual-process: wake the brain only at a decision) -----------------------

    def _run_autopilot(self, target, max_steps: int) -> tuple[int, str]:
        steps = 0
        for _ in range(max(1, min(int(max_steps), 200))):
            obs = self.plugin.observe(_AGENT)
            self._drop_frame(obs)
            if target is not None:
                pose = (obs.data.get("pose") or {}).get("value")
                if pose is not None and list(pose) == target:
                    return steps, "arrived at the target cell"
            call = self.explore.decide(obs, self.plugin.tools(_AGENT), {"goto": target})
            if call is None:
                return steps, ("blocked / no path to the target" if target is not None
                               else "out of reachable frontiers — your decision")
            self.gw.execute(call)
            steps += 1
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
        else:
            # a direct action (press_button / press_sequence / wait): route through the gateway (policy + plugin).
            if name in ("press_button", "press_sequence", "wait"):
                self.decisions += 1          # a real brain action is a wake; an unknown tool name is not counted
            res = self.gw.execute(ToolCall(tool=name, args=args, agent_id=_AGENT, call_id=str(uuid.uuid4())))
            head = {"type": "text", "text": f"[{name} -> ok={res.ok}" + ("" if res.ok else f", {res.error}") + "]"}
            body = [head, *self._content(self.plugin.observe(_AGENT))]

        pre = self._preamble()
        return ([{"type": "text", "text": pre}, *body] if pre else body)


def main() -> int:
    ap = argparse.ArgumentParser(description="MCP (stdio) server exposing Cave Noire as tools.")
    ap.add_argument("--rom", default="roms/Cave Noire (Japan) [T-En by Aeon Genesis v1.00].gb")
    ap.add_argument("--init-state", default="runs/cn_human.state")
    ap.add_argument("--out", default="runs/mcp_cave_noire")
    ap.add_argument("--with-screenshot", action="store_true",
                    help="DEBUG ONLY: also return the raw frame image. Off by default — the brain is meant to "
                         "reason from the symbolic view (the perception seam), not read pixels.")
    args = ap.parse_args()

    world = World(args)
    tools = world.tools()

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
            _send({"jsonrpc": "2.0", "id": mid, "result": {"tools": tools}})
        elif method == "tools/call":
            p = msg.get("params") or {}
            try:
                content = world.call(p.get("name", ""), p.get("arguments") or {})
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
