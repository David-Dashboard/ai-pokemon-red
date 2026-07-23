#!/usr/bin/env python
"""gate0_stub_mcp_server.py -- a minimal LOCAL stdio MCP server exposing ONE trivial tool (`ping`).

Built for tools/gate0_appserver_launch.py's `--mcp stub` path (PRIMARY path per 2026-07-23
orchestrator update: Docker Desktop is down on the launch host, so the Gate 0 `gb-mcp-world`
container is unavailable -- this stub is not a fallback, it is the thing script (a)/(b) in
reports/2026-07-23-gate0-appserver-launch-runbook.md actually point at).

Why this reproduces the mechanism under test just as well as the Docker world: the exec
MCP-cancel bug (openai/codex#15824 / #16685) fires for ANY non-`codex_apps` MCP server -- it is
codex-side and world-agnostic, triggered by codex's own app-tool approval flow, not by anything
`gb-mcp-world`-specific. A `ping` call through THIS server hits the identical
`item/tool/requestUserInput` "Approve app tool call?" prompt tools/gate0_appserver_client.py exists
to answer. Confirming the tool call completes here confirms the SAME mechanism the Docker world
would exercise, at zero image/mount/emulator complexity.

Protocol: newline-delimited JSON-RPC over stdio, the exact minimal subset `codex app-server`'s own
MCP-client-of-this-server needs (`initialize`, `tools/list`, `tools/call`) -- same hand-rolled
shape as world_mcp.py's own MCP server (see that file's module docstring: "Why stdlib (no `mcp`
dep): the frozen contract ... is shape-compatible with MCP via a thin adapter"). No new dependency.

Deliberately trivial: `ping` takes no required arguments and returns a fixed "pong" text result --
there is nothing here for an approval prompt to be interesting ABOUT; the whole point is a tool
call cheap enough to run for real without spending anything beyond one Codex turn.
"""
from __future__ import annotations

import json
import sys

# Same stdout/stdin discipline as world_mcp.py: stdout is the JSON-RPC channel, keep it pristine.
# This script prints nothing else, but reconfiguring stdin's encoding up front matches the
# project-wide convention (Windows stdin otherwise defaults to cp1252) and costs nothing to keep.
try:
    sys.stdin.reconfigure(encoding="utf-8")
except Exception:
    pass

_PROTOCOL = "2024-11-05"

_PING_TOOL = {
    "name": "ping",
    "description": "Trivial no-op tool: takes no required input, always returns the text 'pong'.",
    "inputSchema": {"type": "object", "properties": {}, "required": []},
}


def _send(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def main() -> int:
    for line in sys.stdin:  # newline-delimited JSON-RPC (MCP stdio transport)
        if line and ord(line[0]) == 0xFEFF:  # tolerate a leading BOM on the first message
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

        if mid is None:  # a notification (e.g. notifications/initialized) -- never reply
            continue
        if method == "initialize":
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": _PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "gate0-stub-mcp-server", "version": "0.1.0"}}})
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [_PING_TOOL]}})
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name", "")
            if name == "ping":
                _send({"jsonrpc": "2.0", "id": mid,
                       "result": {"content": [{"type": "text", "text": "pong"}]}})
            else:
                _send({"jsonrpc": "2.0", "id": mid,
                       "result": {"content": [{"type": "text", "text": f"error: unknown tool {name!r}"}],
                                  "isError": True}})
        else:
            _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
