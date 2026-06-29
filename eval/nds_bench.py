"""NDS bench harness — subprocess fan-out, ontology classification, markdown report.

Extracted from play_nds.py (was inlined in the driver; F6 cleanup splits it here).

Usage:
    python eval/nds_bench.py --roms-dir roms/nds --steps 150
    python eval/nds_bench.py --roms-dir roms/nds --steps 150 --report reports/nds-bench.md
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from typing import Optional

# ---------------------------------------------------------------------------
# Bench candidates
# (ROM filename substring, label, expected_gameplay_screen, skip_reason_or_None)
# ---------------------------------------------------------------------------
BENCH_ROMS = [
    # Plain-DS button/spatial — expected to render well
    ("New Super Mario Bros. (USA).nds",        "NSMB",     "top",    None),
    ("Kirby Super Star Ultra (USA).nds",        "Kirby",    "top",    None),
    # 3D — include to measure where 2D primitives break
    ("Mario Kart DS (USA",                     "MK-DS",    "top",    None),
    ("Resident Evil - Deadly Silence (USA).nds","RE-DS",    "top",    None),
    ("Harry Potter and the Order",             "HP-OotP",  "top",    None),
    ("FIFA Street 3 (USA",                     "FIFA-S3",  "top",    None),
    # Skip list (documented, not run)
    ("Pokemon - White Version",                 "Poke-W",   None,    "DSi-enhanced — skipped (no firmware)"),
    ("Phoenix Wright",                          "PW-T&T",   None,    "touch-primary — skipped"),
    ("Professor Layton",                        "Layton",   None,    "touch-primary — skipped"),
    ("Legend of Zelda, The - Spirit Tracks",    "ZeldaST",  None,    "touch-primary — skipped"),
]

_WARMUP_STEPS = 60
_EXPLORE_STEPS = 90


def _find_rom(roms_dir: str, substring: str) -> Optional[str]:
    sub = substring.lower()
    try:
        for f in os.listdir(roms_dir):
            if sub in f.lower() and f.lower().endswith(".nds"):
                return os.path.join(roms_dir, f)
    except OSError:
        pass
    return None


def classify_ontology(label: str, r: dict) -> dict:
    """Map perception findings to ontology stage failure (S1–S7)."""
    disc = r.get("discovery", {})
    spat = r.get("spatial", {})
    is_3d = label in ("MK-DS", "RE-DS", "HP-OotP", "FIFA-S3")
    conf = disc.get("avg_confidence", 0.0)
    screen_ok = disc.get("screen_correct")
    max_cells = spat.get("max_cells_visited", 0)
    ego_nz = spat.get("ego_motion_non_zero", 0)

    if not r.get("renders"):
        return {"stage": "S1-substrate", "note": "ROM frozen/blank — py-desmume substrate issue"}
    if is_3d:
        if max_cells == 0:
            return {"stage": "S1-substrate+S3-viewpoint",
                    "note": "3D game — tile primitives inapplicable; no cells discovered",
                    "primary": "S3-viewpoint"}
        return {"stage": "S3-viewpoint",
                "note": f"3D game — {max_cells} cells (partial, 2D primitives degraded)",
                "primary": "S3-viewpoint"}
    if conf < 0.4:
        return {"stage": "S1-substrate",
                "note": f"screen-role low confidence ({conf:.2f}) — dual-screen routing unreliable"}
    if screen_ok is False:
        return {"stage": "S1-substrate",
                "note": f"screen-role picked wrong screen (expected {disc.get('expected_screen')}, "
                        f"got {disc.get('dominant_screen')})"}
    if max_cells == 0 and ego_nz == 0:
        return {"stage": "S3-viewpoint",
                "note": "spatial pipeline ran but found 0 cells and no ego-motion — camera class mismatch"}
    if max_cells < 5:
        return {"stage": "S6-pose",
                "note": f"few cells ({max_cells}) — dead-reckoning unreliable; pose signal weak"}
    return {"stage": "OK",
            "note": f"pipeline ran — {max_cells} cells, {ego_nz} non-zero ego-motion steps"}


def run_bench(roms_dir: str, steps: int, out_dir: str, verbose: bool = True) -> list[dict]:
    """Run each game in a SUBPROCESS to avoid py-desmume DLL state corruption.

    py-desmume loads a single-instance DLL that tears down global state on destroy().
    Any subsequent DeSmuME() in the SAME process hits corrupted pointers. Each ROM
    gets its own process (fresh DLL image). We call play_nds.py in play mode and
    collect the JSON stdout.
    """
    # play_nds.py lives at repo root; resolve relative to this file's parent.
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "play_nds.py")
    py_exe = sys.executable
    results = []

    for rom_sub, label, expected_screen, skip_reason in BENCH_ROMS:
        print(f"\n--- [{label}] ---")
        if skip_reason:
            print(f"  SKIP: {skip_reason}")
            results.append({
                "label": label, "rom": rom_sub, "renders": None,
                "error": f"skipped: {skip_reason}", "discovery": {}, "spatial": {}, "per_screen": {},
                "ontology": {"stage": "SKIP", "note": skip_reason}, "_expected_screen": expected_screen,
            })
            continue

        rom_path = _find_rom(roms_dir, rom_sub)
        if rom_path is None:
            print(f"  ROM NOT FOUND: {rom_sub}")
            results.append({
                "label": label, "rom": rom_sub, "renders": False,
                "error": "ROM file not found", "discovery": {}, "spatial": {}, "per_screen": {},
                "ontology": {"stage": "S1-substrate", "note": "ROM missing"}, "_expected_screen": expected_screen,
            })
            continue

        rom_out = os.path.join(out_dir, label.replace(" ", "_").lower())
        cmd = [py_exe, script, "play", "--rom", rom_path, "--steps", str(steps),
               "--out", rom_out, "--label", label,
               "--expected-screen", str(expected_screen or "")]
        if not verbose:
            cmd.append("--quiet")

        print(f"  running: {label}  ({steps} steps)")
        t0 = time.time()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                  env={**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "")})
            elapsed = time.time() - t0
            stdout = proc.stdout
            # Find the JSON blob: first '{' at line-start through last '}'.
            json_start = -1
            for i, ch in enumerate(stdout):
                if ch == "{" and (i == 0 or stdout[i - 1] == "\n"):
                    json_start = i
                    break
            json_end = stdout.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                r = json.loads(stdout[json_start:json_end])
            else:
                r = {"label": label, "rom": os.path.basename(rom_path), "renders": False,
                     "error": f"no JSON in subprocess output (rc={proc.returncode})",
                     "discovery": {}, "spatial": {}, "per_screen": {},
                     "ontology": {"stage": "S1-substrate", "note": "subprocess produced no JSON"}}
            r["_elapsed_s"] = round(elapsed, 1)
            r["_expected_screen"] = expected_screen
            if "discovery" in r:
                r["discovery"]["expected_screen"] = expected_screen
                screen_chosen = r["discovery"].get("dominant_screen") or r["discovery"].get("final_gameplay")
                r["discovery"]["screen_correct"] = (screen_chosen == expected_screen) if expected_screen else None
            if verbose:
                non_json = stdout[:json_start].strip() if json_start >= 0 else stdout.strip()
                if non_json:
                    for line in non_json.splitlines()[-20:]:
                        print(f"    {line}")
        except subprocess.TimeoutExpired:
            r = {"label": label, "rom": os.path.basename(rom_path), "renders": False,
                 "error": "subprocess timed out (600s)", "discovery": {}, "spatial": {}, "per_screen": {},
                 "ontology": {"stage": "S1-substrate", "note": "timeout"}, "_expected_screen": expected_screen}
        except Exception as e:
            r = {"label": label, "rom": os.path.basename(rom_path), "renders": False,
                 "error": f"subprocess error: {e}", "discovery": {}, "spatial": {}, "per_screen": {},
                 "ontology": {"stage": "S1-substrate", "note": str(e)}, "_expected_screen": expected_screen}

        results.append(r)

    return results


def write_report(results: list[dict], report_path: str) -> None:
    lines = [
        "# NDS Bench Report", "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}", "",
        "## Per-game table", "",
        "| Game | Renders | Discovered screen (conf) | Correct? | Cells (max) | Ego-motion | Ontology stage | Notes |",
        "|------|---------|--------------------------|----------|-------------|------------|----------------|-------|",
    ]
    for r in results:
        label = r["label"]
        renders = r.get("renders")
        err = r.get("error") or ""
        disc = r.get("discovery", {})
        spat = r.get("spatial", {})
        onto = r.get("ontology", {})
        renders_str = "yes" if renders else ("skipped" if renders is None else "NO")
        if renders is None:
            lines.append(f"| {label} | {renders_str} | — | — | — | — | {onto.get('stage','?')} | {onto.get('note',err)[:80]} |")
            continue
        screen = disc.get("dominant_screen") or disc.get("final_gameplay") or "—"
        conf = disc.get("avg_confidence", 0.0)
        correct = disc.get("screen_correct")
        correct_str = "yes" if correct is True else ("no" if correct is False else "—")
        cells = spat.get("max_cells_visited", 0)
        ego = spat.get("ego_motion_non_zero", 0)
        stage = onto.get("stage", "?")
        note = onto.get("note", err)[:80]
        lines.append(f"| {label} | {renders_str} | {screen} ({conf:.2f}) | {correct_str} | {cells} | {ego} | {stage} | {note} |")

    lines += ["", "## Ranked NDS perception gaps", ""]
    for i, g in enumerate(_rank_gaps(results), 1):
        lines.append(f"{i}. {g}")
    lines += ["", "## Verdict", "", _verdict(results), "", "## Per-game detail", ""]
    for r in results:
        label = r["label"]
        lines.append(f"### {label}")
        lines.append(f"- ROM: `{r.get('rom','?')}`")
        lines.append(f"- Renders: {r.get('renders')}")
        err = r.get("error")
        if err:
            lines.append(f"- Error: {err}")
        disc = r.get("discovery", {})
        if disc:
            lines.append(f"- Screen role: gameplay={disc.get('final_gameplay')} dominant={disc.get('dominant_screen')} "
                         f"conf={disc.get('avg_confidence', 0):.3f} commit_step={disc.get('commit_step')} "
                         f"votes={disc.get('votes')}")
        spat = r.get("spatial", {})
        if spat:
            lines.append(f"- Spatial: max_cells={spat.get('max_cells_visited')} unique_poses={spat.get('unique_poses')} "
                         f"ego_nz={spat.get('ego_motion_non_zero')}")
        per = r.get("per_screen", {})
        if per:
            lines.append(f"- Per-screen diffs: top={per.get('top_diff')} bottom={per.get('bot_diff')} "
                         f"render_mean={per.get('render_diff_mean')}")
        onto = r.get("ontology", {})
        lines.append(f"- Ontology: {onto.get('stage','?')} — {onto.get('note','')}")
        lines.append("")

    os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nReport written -> {report_path}")


def _rank_gaps(results: list[dict]) -> list[str]:
    counts: dict[str, int] = {}
    for r in results:
        stage = (r.get("ontology") or {}).get("stage", "?")
        if stage in ("SKIP", "OK"):
            continue
        for s in stage.split("+"):
            counts[s] = counts.get(s, 0) + 1
    ranked = sorted(counts, key=lambda k: -counts[k])
    gap_map = {
        "S1-substrate": "S1-substrate: dual-screen routing unreliable / emulator boot fragility",
        "S3-viewpoint": "S3-viewpoint: 2D tile primitives break on 3D games and side-scrollers",
        "S6-pose": "S6-pose: dead-reckoning accumulates drift on 256×192 NDS frames",
        "S2-mode": "S2-mode: menu/gameplay mode confusion during title sequences",
        "S4-embodiment": "S4-embodiment: avatar not localized",
        "S7-entities": "S7-entities: no entity detection",
    }
    gaps = [gap_map.get(s, f"{s}: unknown gap ({counts.get(s, 0)} games affected)") for s in ranked]
    if "S1-substrate" not in ranked:
        gaps.append(gap_map["S1-substrate"] + " (not triggered this run)")
    if "S3-viewpoint" not in ranked:
        gaps.append(gap_map["S3-viewpoint"] + " (not triggered this run)")
    return gaps or ["No failures detected — all tested games passed the spatial pipeline."]


def _verdict(results: list[dict]) -> str:
    renders_ok = [r for r in results if r.get("renders") is True]
    renders_no = [r for r in results if r.get("renders") is False]
    skipped = [r for r in results if r.get("renders") is None]
    ok_spatial = [r for r in renders_ok if (r.get("ontology") or {}).get("stage") == "OK"]
    broken_3d = [r for r in renders_ok if "S3-viewpoint" in (r.get("ontology") or {}).get("stage", "")]
    low_conf = [r for r in renders_ok if (r.get("discovery") or {}).get("avg_confidence", 1.0) < 0.4]
    n_ok, n_skip, n_no = len(renders_ok), len(skipped), len(renders_no)
    n_spat, n_3d, n_lc = len(ok_spatial), len(broken_3d), len(low_conf)
    return (
        f"Of the {len(results)} bench candidates, {n_skip} were skipped by policy, "
        f"{n_no} failed to render, and {n_ok} rendered successfully.  \n"
        f"Screen-role discovery held up on {n_ok - n_lc} of {n_ok} rendering games (confidence >= 0.40).  \n"
        f"The 2D spatial pipeline produced usable cell maps on {n_spat} game(s); "
        f"{n_3d} 3D game(s) broke the tile primitives as expected."
    )


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="NDS bench harness — runs all NDS ROMs and emits a markdown report.")
    ap.add_argument("--roms-dir", default="roms/nds", help="Directory containing .nds ROMs")
    ap.add_argument("--steps", type=int, default=150, help="Steps per game")
    ap.add_argument("--out", default="runs/nds_bench", help="Output directory")
    ap.add_argument("--report", default="reports/nds-bench.md", help="Path for markdown report")
    ap.add_argument("--quiet", action="store_true", help="Suppress per-step prints")
    args = ap.parse_args()

    verbose = not args.quiet
    results = run_bench(roms_dir=args.roms_dir, steps=args.steps, out_dir=args.out, verbose=verbose)
    write_report(results, args.report)
    ok = sum(1 for r in results if r.get("renders") is True)
    print(f"\nBench complete. {ok} ROMs rendered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
