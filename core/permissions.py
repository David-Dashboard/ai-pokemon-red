"""Permission policies — the gateway's veto (the PermissionPolicy protocol).

Two regimes matter here:

  * Simulated worlds (chess, ecology): `AllowAll`. Nothing real is at stake.
  * Real-world plugins: the contract's hard rule is that mutating tools must
    NOT default to allow-all — the AI never gets unsupervised write access to
    David's real systems (email, files, Notion).

The Pokémon emulator is a deliberate middle case: it is driven like a
real-world plugin (GamePlugin-only, wall-clock time) but it is a sandbox —
pressing B in a Game Boy has no consequence outside the toy. So we do NOT use
AllowAll; we use `Allowlist`, which permits exactly the in-game button tools
and would deny anything that reached outside the sandbox (a hypothetical
disk-write or shell tool). That honors the rule by construction while still
letting the agent play.
"""

from __future__ import annotations

from core.contracts import ToolCall, ToolSpec


class AllowAll:
    """For deterministic sims only. Never point this at a real-world plugin."""

    def check(self, call: ToolCall, spec: ToolSpec) -> tuple[bool, str]:
        return True, ""


class Allowlist:
    """Permit only named tools; deny everything else as an observation."""

    def __init__(self, allowed: set[str]) -> None:
        self.allowed = set(allowed)

    def check(self, call: ToolCall, spec: ToolSpec) -> tuple[bool, str]:
        if call.tool in self.allowed:
            return True, ""
        return False, f"tool '{call.tool}' is not in the sandbox allowlist"


# The default for the Pokémon demo: exactly the sandboxed in-game inputs.
POKEMON_SANDBOX = Allowlist({"press_button", "press_sequence", "wait"})
