#!/usr/bin/env python
"""PreCompact hook — enforce 'notes-before-compact'.

Reminds (user + model) to persist orientation before context is summarized away, matching
the project's working style. Fails SILENT.
"""
import json


def main():
    try:
        print(json.dumps({"systemMessage": (
            "notes-before-compact: update HANDOFF.md §2 (LATEST + NEXT) and the current-status memory, "
            "and add any non-obvious learning to reports/LEARNINGS.md, so the next window stays oriented."
        )}))
    except Exception:
        pass


if __name__ == "__main__":
    main()
