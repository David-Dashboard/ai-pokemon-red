"""Tests for the free smoke sweep (tools/smoke_sweep.py + tools/smoke_sweep_report.py).

CI-safe: only the stdlib-importable surfaces are exercised (ROM discovery + the report formatter,
with synthetic JSONL). Nothing here boots an emulator or needs a ROM — the emulator paths are
validated live via tools/run_smoke_sweep.sh (Docker / gba-spike), not in CI.
"""

import json

from tools.smoke_sweep import console_for, discover_roms
from tools.smoke_sweep_report import load_records, render_markdown, verdict


def _rec(**over):
    base = {"game": "g", "rom": "roms/g.gb", "console": "gb", "boot_ok": True,
            "frames_advanced": 1300, "n_observations": 15, "screen_variety": 12,
            "entities_seen_median": 2, "pose_present": True, "registered_game": None,
            "exception": None, "timeout": False, "duration_s": 9.0}
    base.update(over)
    return base


# -- discovery -------------------------------------------------------------

def test_discover_roms_skips_zips_and_non_roms(tmp_path):
    (tmp_path / "a.gb").write_bytes(b"x")
    (tmp_path / "b.gbc").write_bytes(b"x")
    (tmp_path / "c.zip").write_bytes(b"x")
    (tmp_path / "README.md").write_text("not a rom")
    (tmp_path / "gba").mkdir()
    (tmp_path / "gba" / "d.gba").write_bytes(b"x")
    (tmp_path / "gba" / "d.zip").write_bytes(b"x")
    (tmp_path / "nds").mkdir()
    (tmp_path / "nds" / "e.nds").write_bytes(b"x")

    found = discover_roms(str(tmp_path))
    names = sorted(p.replace("\\", "/").split("/")[-1] for p in found)
    assert names == ["a.gb", "b.gbc", "d.gba", "e.nds"]


def test_discover_roms_console_filter(tmp_path):
    (tmp_path / "a.gb").write_bytes(b"x")
    (tmp_path / "gba").mkdir()
    (tmp_path / "gba" / "d.gba").write_bytes(b"x")
    only_gba = discover_roms(str(tmp_path), consoles={"gba"})
    assert len(only_gba) == 1 and only_gba[0].endswith("d.gba")


def test_console_for():
    assert console_for("x/Foo.GB") == "gb"
    assert console_for("x/foo.gbc") == "gb"
    assert console_for("x/foo.gba") == "gba"
    assert console_for("x/foo.nds") == "nds"
    assert console_for("x/foo.zip") is None
    assert console_for("x/foo.funscript") is None


# -- verdicts --------------------------------------------------------------

def test_verdict_broken_on_exception_or_no_boot():
    assert verdict(_rec(exception={"type": "RuntimeError", "msg": "boom"})) == "broken"
    assert verdict(_rec(boot_ok=False, frames_advanced=0)) == "broken"


def test_verdict_degraded_on_frozen_screen_or_short_run():
    assert verdict(_rec(screen_variety=1)) == "degraded"        # black/frozen screen
    assert verdict(_rec(screen_variety=0)) == "degraded"
    assert verdict(_rec(frames_advanced=500)) == "degraded"     # stalled well under expected
    assert verdict(_rec(n_observations=0)) == "degraded"


def test_verdict_runnable():
    assert verdict(_rec()) == "runnable"


# -- markdown rendering ----------------------------------------------------

def test_render_markdown_table_shape_and_content(tmp_path):
    recs = [
        _rec(game="Zelda", console="gb"),
        _rec(game="Kirby NDS", console="nds", screen_variety=1),
        _rec(game="MK Advance", console="gba", boot_ok=False, frames_advanced=0,
             exception={"type": "ValueError", "msg": "bad rom header"}),
    ]
    p = tmp_path / "sweep.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in recs) + "\n\n", encoding="utf-8")

    loaded = load_records(str(p))                # tolerates the trailing blank line
    assert len(loaded) == 3

    md = render_markdown(loaded)
    lines = md.splitlines()
    assert lines[0].startswith("| game | console | boot |")
    assert set(lines[1].replace("|", "").strip()) <= {"-"}       # separator row
    assert len([ln for ln in lines if ln.startswith("| ")]) == 4  # header + 3 rows
    # rows are sorted by console: gb before gba before nds
    body = [ln for ln in lines[2:] if ln.startswith("| ")]
    assert [r.split(" | ")[0].lstrip("| ") for r in body] == ["Zelda", "MK Advance", "Kirby NDS"]
    assert "| runnable |" in body[0]
    assert "broken" in body[1] and "ValueError" in body[1]
    assert "degraded" in body[2] and "frozen/black screen" in body[2]
    assert "3 games: 1 runnable, 1 degraded, 1 broken" in md


def test_render_markdown_entities_dash_when_absent():
    md = render_markdown([_rec(entities_seen_median=None)])
    row = [ln for ln in md.splitlines() if ln.startswith("| g |")][0]
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[5] == "-"                       # entities column
