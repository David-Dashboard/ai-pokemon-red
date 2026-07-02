"""tools/probe_queue_lib.py — pure decision logic for tools/run_probe_queue.sh (the WSL queue-runner).

Kept out of bash (skip/lock/session-limit parsing are easy to get subtly wrong in shell) and out of any
module that needs an emulator/ROM, so it's unit-testable in CI: stdlib only, no docker/network/claude.

The queue-runner's flow, in terms of these functions:
  1. read_queue(queue_path)              -> ordered list of slugs to (maybe) run
  2. ledger_slugs(ledger_path)            -> slugs that already have a ledger row (skip unless --redo)
  3. parse_session_limit(run_err_text)    -> seconds to sleep before retrying, or None if not a limit hit
  4. parse_total_cost_usd(transcript_path) -> the run's total_cost_usd (None if absent/unparseable)
  5. ledger_row(slug, exit_code, duration_s, cost_usd) -> the dict appended to probe_ledger.jsonl
"""
from __future__ import annotations

import json
import re
import time

# "resets 2:30pm" / "resets at 14:30 UTC" / "resets in 45 minutes" — Claude Code's usage-limit message
# names when the limit clears; we only need a rough wait, so parse a wall-clock time-of-day if present.
_RESETS_CLOCK = re.compile(r"resets?\s+(?:at\s+)?(\d{1,2}):(\d{2})\s*([ap]m)?", re.IGNORECASE)
_SESSION_LIMIT_MARKERS = (
    "session limit reached",
    "usage limit reached",
    "5-hour limit reached",
)
_FALLBACK_SLEEP_S = 3600


def read_queue(queue_path: str) -> list[str]:
    """One slug per line; blank lines and '#'-comments ignored."""
    out = []
    with open(queue_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(line)
    return out


def ledger_slugs(ledger_path: str) -> set[str]:
    """Slugs that already have a row in probe_ledger.jsonl (missing file = empty set, not an error —
    the ledger is created by the first run)."""
    slugs: set[str] = set()
    try:
        with open(ledger_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                slug = rec.get("slug")
                if slug:
                    slugs.add(slug)
    except FileNotFoundError:
        pass
    return slugs


def should_run(slug: str, done: set[str], redo: bool) -> bool:
    """Idempotent skip: a slug with an existing ledger row is skipped unless --redo."""
    return redo or slug not in done


def _parse_clock_to_seconds_from_now(hh: int, mm: int, ampm: str | None, now: float | None = None) -> int:
    """Seconds from `now` (default: current time) until the next occurrence of hh:mm[am/pm], today or
    tomorrow if that time has already passed today. Local time, second-granularity is not needed here."""
    now = time.time() if now is None else now
    now_t = time.localtime(now)
    hour = hh % 12
    if ampm and ampm.lower() == "pm":
        hour += 12
    elif ampm is None and hh > 12:
        hour = hh  # already 24h form (e.g. "14:30")
    target = time.mktime((now_t.tm_year, now_t.tm_mon, now_t.tm_mday, hour, mm, 0,
                          0, 0, -1))
    if target <= now:
        target += 86400
    return max(1, int(target - now))


def parse_session_limit(err_text: str, now: float | None = None) -> float | None:
    """Seconds to sleep before retrying, if `err_text` (run.err / transcript tail) shows a session-limit
    message; else None (not a limit hit — some other failure, don't retry-sleep for it).

    Tries to parse a "resets <time>" clock; falls back to _FALLBACK_SLEEP_S (1 hour) if the message is
    recognized but no time could be parsed."""
    low = err_text.lower()
    if not any(marker in low for marker in _SESSION_LIMIT_MARKERS):
        return None
    m = _RESETS_CLOCK.search(err_text)
    if m:
        hh, mm, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
        return float(_parse_clock_to_seconds_from_now(hh, mm, ampm, now=now))
    return float(_FALLBACK_SLEEP_S)


def parse_total_cost_usd(transcript_path: str) -> float | None:
    """The run's total_cost_usd from the stream-json transcript's {"type": "result", ...} line, or None
    if the file is missing, empty, or has no result line (e.g. the run crashed before finishing)."""
    try:
        with open(transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return None
    for line in reversed(lines):        # the result line is normally last; scan from the end
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("type") == "result":
            cost = rec.get("total_cost_usd")
            return float(cost) if cost is not None else None
    return None


# Hard cap on session-limit retries per slug (review finding on PR #65: the retry loop was unbounded —
# a wording drift in the limit message could re-bill a stuck slug once an hour forever). On exhaustion
# the queue-runner records exit="limit_retries_exhausted" for the slug and MOVES ON to the next one.
MAX_LIMIT_RETRIES = 6
LIMIT_RETRIES_EXHAUSTED = "limit_retries_exhausted"


def ledger_row(slug: str, exit_code: int | str, duration_s: float, cost_usd: float | None,
               limit_retries: int = 0) -> dict:
    """One probe attempt's ledger record. `exit_code` is run.sh's exit int, or the string
    LIMIT_RETRIES_EXHAUSTED when the session-limit retry cap ran out for this slug."""
    return {"slug": slug, "exit": exit_code, "duration": round(duration_s, 1), "cost": cost_usd,
            "limit_retries": limit_retries}
