"""Architectural fitness functions — IMPORT BOUNDARIES (the 'decoupled, no monolith' principle, executable).

These tests make ADR-001's decoupling un-violatable-silently. A red here means the seam is being crossed in
*code* — fix the offending import; do NOT edit this test to make it pass.

Enforced:
  1. `core/` is WORLD-AGNOSTIC — nothing in core/ may import `games/`.
  2. The BRAIN is DECOUPLED — nothing in this repo may import `aria` / `ai_aria` (it's an HTTP service).
  3. GAMES are ISOLATED — a game package may not import a sibling game package.
  4. NO OSSIFICATION — a lean game package may not carry its own emulator/plugin (shared world-interface
     infra lives in core/; a per-world copy is the duplication the toolkit-of-primitives thesis forbids).
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _abs_imports(py: Path):
    """Yield the absolute module paths a file imports (skips relative/`from . import` — those stay in-package)."""
    try:
        tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:  # absolute import only
                yield node.module


def _py_files(*rel_dirs: str):
    for rel in rel_dirs:
        d = ROOT / rel
        if d.is_dir():
            for p in d.rglob("*.py"):
                if "__pycache__" not in p.parts:
                    yield p


def _top(mod: str) -> str:
    return mod.split(".", 1)[0]


def test_core_is_world_agnostic():
    bad = [
        f"{py.relative_to(ROOT)} imports {mod}"
        for py in _py_files("core")
        for mod in _abs_imports(py)
        if _top(mod) == "games"
    ]
    assert not bad, "core/ must not import games/ (keep core world-agnostic):\n" + "\n".join(bad)


def test_brain_is_decoupled_no_aria_import():
    bad = [
        f"{py.relative_to(ROOT)} imports {mod}"
        for py in _py_files("core", "games", "eval")
        for mod in _abs_imports(py)
        if _top(mod) in {"aria", "ai_aria"}
    ]
    assert not bad, "this repo must not import aria (the brain is a decoupled HTTP service):\n" + "\n".join(bad)


def test_games_are_isolated_from_each_other():
    bad = []
    for py in _py_files("games"):
        parts = py.relative_to(ROOT).parts  # ('games', '<world>', ...)
        if len(parts) < 3:
            continue
        own = parts[1]
        for mod in _abs_imports(py):
            segs = mod.split(".")
            if segs[0] == "games" and len(segs) >= 2 and segs[1] != own:
                bad.append(f"{py.relative_to(ROOT)} imports {mod} (sibling game)")
    assert not bad, "a game package must not import a sibling game package:\n" + "\n".join(bad)


# Lean worlds (everything but Pokémon, the rich outlier) reuse the shared emulator/plugin from core/.
# A per-world emulator.py/plugin.py is the "specifics ossify in the perceiver" drift (INSIGHTS §2):
# the signal to LIFT the shared part to core/, not to copy a sibling. The tripwire for that.
_INFRA_OK = {"pokemon_red"}          # keeps its own emulator (fade layer) + plugin (reward/battle)


def _lean_game_dirs():
    games_dir = ROOT / "games"
    for pkg in games_dir.iterdir():
        if pkg.is_dir() and pkg.name not in _INFRA_OK and pkg.name != "__pycache__":
            yield pkg


def test_lean_games_do_not_carry_their_own_infra():
    bad = [f"games/{pkg.name}/{infra}"
           for pkg in _lean_game_dirs()
           for infra in ("emulator.py", "plugin.py") if (pkg / infra).exists()]
    assert not bad, ("lean game packages must reuse core/ infra, not copy it (lift to core/, don't "
                     "duplicate — INSIGHTS §2):\n" + "\n".join(bad))


# The filename check above only proves the two files just removed are gone. The PRINCIPLE is broader:
# a lean perceiver must be THIN CONFIG over the shared core base, not an inlined copy of the body. A
# duplicated GridPerceiver/best_shift/occupancy-grid body would be hundreds of lines; a config is tens.
# Budget guards the principle without prescribing a specific base (a future camera class gets its own).
_LEAN_PERCEIVER_MAX_LINES = 80


def test_lean_perceivers_are_thin_config_not_an_inlined_body():
    fat = []
    for pkg in _lean_game_dirs():
        perc = pkg / "perceiver.py"
        if not perc.exists():
            continue
        n = sum(1 for _ in perc.read_text(encoding="utf-8", errors="replace").splitlines())
        if n > _LEAN_PERCEIVER_MAX_LINES:
            fat.append(f"games/{pkg.name}/perceiver.py is {n} lines (> {_LEAN_PERCEIVER_MAX_LINES})")
    assert not fat, ("a lean perceiver must be thin config over a core/ base, not an inlined body "
                     "(lift the shared part — INSIGHTS §2):\n" + "\n".join(fat))
