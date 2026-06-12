"""The gateway — the single door (invariant 1).

Every agent action on every world passes through `execute()`. The gateway
owns POLICY: it resolves the tool spec, runs the permission check, deep-copies
wire values at the boundary (invariant 4 — frozen dataclasses are only
shallowly frozen), dispatches to the plugin, and normalizes failures into
ok=False ToolResults (invariant 2). Brains never touch a plugin directly.
"""

from __future__ import annotations

import copy

from core.contracts import GamePlugin, PermissionPolicy, ToolCall, ToolResult


class Gateway:
    def __init__(self, plugin: GamePlugin, policy: PermissionPolicy) -> None:
        self.plugin = plugin
        self.policy = policy

    def execute(self, call: ToolCall) -> ToolResult:
        # Deep-copy in: the brain must not retain a handle to mutate post-send.
        call = ToolCall(
            tool=call.tool,
            args=copy.deepcopy(call.args),
            agent_id=call.agent_id,
            call_id=call.call_id,
        )

        specs = {s.name: s for s in self.plugin.tools(call.agent_id)}
        spec = specs.get(call.tool)
        if spec is None:
            return ToolResult(
                call_id=call.call_id, ok=False,
                data={"available": sorted(specs)},
                error=f"unknown tool: {call.tool}", cost_charged=0,
            )

        ok, reason = self.policy.check(call, spec)
        if not ok:
            # Async approval rides the pending: convention (invariant 11).
            if reason.startswith("pending:"):
                approval_id = reason.split(":", 1)[1]
                return ToolResult(call_id=call.call_id, ok=False,
                                  data={"approval_id": approval_id},
                                  error=reason, cost_charged=0)
            return ToolResult(call_id=call.call_id, ok=False,
                              data={}, error=f"denied: {reason}", cost_charged=0)

        result = self.plugin.handle(call)

        # Deep-copy out + make sure a cost was charged for an executed call.
        return ToolResult(
            call_id=result.call_id,
            ok=result.ok,
            data=copy.deepcopy(result.data),
            error=result.error,
            cost_charged=result.cost_charged or spec.cost,
        )
