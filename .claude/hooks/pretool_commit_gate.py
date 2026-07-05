#!/usr/bin/env python
"""PreToolUse(Bash) gate — block Claude's `git commit` if the FAST invariant tests fail.

Fires before every Bash command but no-ops unless the command is a `git commit` (and not `--no-verify`).
Runs only the fast architectural/contract guards for immediate feedback; the FULL suite runs in the
pre-commit git hook + CI. On red it returns permissionDecision=deny so the commit is blocked. Fails OPEN —
a bug in this hook must never block a commit on its own.
"""
import json
import subprocess
import sys
from pathlib import Path

FAST = [
    "tests/test_import_boundaries.py",
    "tests/test_no_ram_leak.py",
    "tests/test_contract_frozen.py",
]


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return  # unparseable input -> allow (fail open)
    cmd = ((data.get("tool_input") or {}).get("command") or "")
    if "git commit" not in cmd or "--no-verify" in cmd:
        return  # not a guarded commit -> allow
    root = Path(__file__).resolve().parents[2]
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *FAST],
            cwd=str(root), capture_output=True, text=True, timeout=300,
        )
    except Exception:
        return  # our own tooling failed -> fail open, don't block the commit
    if r.returncode != 0:
        tail = (r.stdout or "")[-1200:]
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "Commit blocked: fast invariant tests FAILED (import-boundary / no-RAM-leak / "
                "frozen-contract). Fix the code — do NOT edit the tests to silence them.\n\n" + tail
            ),
        }}))
    # pass -> emit nothing (normal flow continues; other permission checks still apply)


if __name__ == "__main__":
    main()
