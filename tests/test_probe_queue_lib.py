"""Tests for tools/probe_queue_lib.py — the pure ledger/skip/session-limit logic behind
tools/run_probe_queue.sh. Stdlib only; no docker/network/claude involved.
"""

import json
import time

from tools.probe_queue_lib import (
    ledger_row,
    ledger_slugs,
    parse_session_limit,
    parse_total_cost_usd,
    read_queue,
    should_run,
)


def test_read_queue_skips_blanks_and_comments(tmp_path):
    p = tmp_path / "queue.txt"
    p.write_text("game_a\n\n# a comment\ngame_b\n  \ngame_c\n", encoding="utf-8")
    assert read_queue(str(p)) == ["game_a", "game_b", "game_c"]


def test_ledger_slugs_missing_file_is_empty_set(tmp_path):
    assert ledger_slugs(str(tmp_path / "nope.jsonl")) == set()


def test_ledger_slugs_reads_rows(tmp_path):
    p = tmp_path / "ledger.jsonl"
    p.write_text(
        json.dumps({"slug": "a", "exit": 0}) + "\n" +
        json.dumps({"slug": "b", "exit": 1}) + "\n" +
        "not json\n",
        encoding="utf-8",
    )
    assert ledger_slugs(str(p)) == {"a", "b"}


def test_should_run_skips_done_unless_redo():
    done = {"a", "b"}
    assert should_run("a", done, redo=False) is False
    assert should_run("a", done, redo=True) is True
    assert should_run("c", done, redo=False) is True


def test_parse_session_limit_none_for_ordinary_error():
    assert parse_session_limit("Traceback: connection refused") is None
    assert parse_session_limit("") is None


def test_parse_session_limit_falls_back_without_a_time():
    assert parse_session_limit("Session limit reached, try later.") == 3600.0


def test_parse_session_limit_parses_resets_clock():
    # Pin "now" to a fixed time so the sleep duration is deterministic in the test.
    now = time.mktime((2026, 7, 3, 10, 0, 0, 0, 0, -1))   # 2026-07-03 10:00 local
    secs = parse_session_limit("5-hour limit reached, resets 2:00pm", now=now)
    assert secs == 4 * 3600.0


def test_parse_session_limit_resets_tomorrow_if_time_already_passed():
    now = time.mktime((2026, 7, 3, 15, 0, 0, 0, 0, -1))   # 2026-07-03 15:00 local
    secs = parse_session_limit("usage limit reached, resets 2:00pm", now=now)
    assert secs == 23 * 3600.0   # 2pm tomorrow, 23h away


def test_parse_total_cost_usd_missing_file():
    assert parse_total_cost_usd("/no/such/transcript.jsonl") is None


def test_parse_total_cost_usd_from_result_line(tmp_path):
    p = tmp_path / "transcript.jsonl"
    p.write_text(
        json.dumps({"type": "assistant", "message": {"content": []}}) + "\n" +
        json.dumps({"type": "result", "total_cost_usd": 1.23, "other": "stuff"}) + "\n",
        encoding="utf-8",
    )
    assert parse_total_cost_usd(str(p)) == 1.23


def test_parse_total_cost_usd_none_when_no_result_line(tmp_path):
    p = tmp_path / "transcript.jsonl"
    p.write_text(json.dumps({"type": "assistant"}) + "\n", encoding="utf-8")
    assert parse_total_cost_usd(str(p)) is None


def test_ledger_row_shape():
    row = ledger_row("game_a", 0, 12.345, 1.5)
    assert row == {"slug": "game_a", "exit": 0, "duration": 12.3, "cost": 1.5}
    row_no_cost = ledger_row("game_b", 1, 5.0, None)
    assert row_no_cost["cost"] is None
