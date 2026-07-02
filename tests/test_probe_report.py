"""Tests for tools/probe_report.py — the ledger+transcript -> Markdown formatter, over synthetic fixtures.
Stdlib only; no docker/ROM/network involved.
"""

import json
import os

from tools.probe_report import load_ledger, parse_probe_line, render_markdown


def _write_transcript(path, probe_line: str | None):
    content = []
    if probe_line is not None:
        content.append({"type": "text", "text": f"closing thoughts.\n{probe_line}\nbye."})
    msg = {"type": "assistant", "message": {"content": content}}
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(msg) + "\n")


def test_load_ledger_reads_jsonl(tmp_path):
    p = tmp_path / "ledger.jsonl"
    p.write_text(json.dumps({"slug": "a", "exit": 0, "duration": 1.0, "cost": 0.5}) + "\n",
                 encoding="utf-8")
    assert load_ledger(str(p)) == [{"slug": "a", "exit": 0, "duration": 1.0, "cost": 0.5}]


def test_parse_probe_line_missing_transcript():
    verdict, gaps = parse_probe_line("/no/such/file.jsonl")
    assert verdict is None and gaps is None


def test_parse_probe_line_extracts_verdict_and_gaps(tmp_path):
    p = tmp_path / "transcript.jsonl"
    _write_transcript(p, "PROBE verdict=free_movement gaps=no combat feedback, no minimap")
    verdict, gaps = parse_probe_line(str(p))
    assert verdict == "free_movement"
    assert gaps == "no combat feedback, no minimap"


def test_parse_probe_line_none_when_absent(tmp_path):
    p = tmp_path / "transcript.jsonl"
    _write_transcript(p, None)
    verdict, gaps = parse_probe_line(str(p))
    assert verdict is None and gaps is None


def test_render_markdown_table_shape_and_content(tmp_path):
    runs_root = tmp_path
    for slug, probe_line, cost in [
        ("gameA", "PROBE verdict=free_movement gaps=none", 1.11),
        ("gameB", "PROBE verdict=stuck_title gaps=couldn't tell if intro ended", None),
    ]:
        d = runs_root / f"probe_{slug}"
        d.mkdir()
        _write_transcript(d / "transcript.jsonl", probe_line)

    ledger = [
        {"slug": "gameA", "exit": 0, "duration": 42.0, "cost": 1.11},
        {"slug": "gameB", "exit": 0, "duration": 10.0, "cost": None},
    ]
    md = render_markdown(ledger, str(runs_root))
    lines = md.splitlines()
    assert lines[0].startswith("| game | verdict | cost_usd | gaps |")
    body = [ln for ln in lines[2:] if ln.startswith("| ")]
    assert len(body) == 2
    row_a = [c.strip() for c in body[0].strip("|").split("|")]
    assert row_a[0] == "gameA" and row_a[1] == "free_movement" and row_a[2] == "1.11"
    row_b = [c.strip() for c in body[1].strip("|").split("|")]
    assert row_b[0] == "gameB" and row_b[1] == "stuck_title" and row_b[2] == "-"
    assert "2 probe(s)." in md


def test_render_markdown_missing_transcript_shows_dashes(tmp_path):
    ledger = [{"slug": "ghost", "exit": 1, "duration": 5.0, "cost": None}]
    md = render_markdown(ledger, str(tmp_path))
    row = [ln for ln in md.splitlines() if ln.startswith("| ghost")][0]
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[1] == "-" and cells[3] == "-"
