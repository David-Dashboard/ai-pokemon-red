#!/usr/bin/env python
"""SessionStart hook — auto-orient each session.

Surfaces the canonical-goal + current-NEXT pointers from HANDOFF.md so a new session
starts grounded without relying on remembering to "read HANDOFF". Fails SILENT — a hook
must never break a session.
"""
import json
from pathlib import Path


def main():
    try:
        root = Path(__file__).resolve().parents[2]  # .claude/hooks/ -> project root
        handoff = root / "HANDOFF.md"
        current_next = ""
        if handoff.exists():
            # HANDOFF is append-at-top: ONLY the topmost "⇒ NEXT (priority order)" line is current.
            # (The old any-"NEXT"-substring scan surfaced stale lines from demoted blocks.)
            lines = handoff.read_text(encoding="utf-8", errors="replace").splitlines()
            for ln in lines[:160]:
                s = ln.strip().lstrip("*-# >").strip()
                if s.startswith("⇒ NEXT") or s.startswith("**⇒ NEXT"):
                    current_next = s[:300]
                    break
        ctx = (
            "PROJECT ORIENTATION — North Star (HANDOFF.md §1): ONE fixed brain + swappable perceiver, "
            "screen-only, across worlds, cheap, no per-world training; games are probes, not the goal. "
            "Cold session read order: .claude/skills/README.md (session-start -> safety-invariants -> "
            "your task's skill). Strategy: reports/2026-07-05-northstar-capability-map.md (every gate "
            "names which of the 6 capabilities it buys). Read HANDOFF.md topmost NEWEST block before "
            "substantive work; position wins over dates. Redesigns = a new ADR in ARCHITECTURE.md, not "
            "silent edits. Commit/push only when asked."
        )
        if current_next:
            ctx += " Current top NEXT line (verify in HANDOFF): " + current_next
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": ctx[:1400],
        }}))
    except Exception:
        pass  # never break a session


if __name__ == "__main__":
    main()
