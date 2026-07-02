#!/usr/bin/env python
"""tools/smoke_sweep.py — FREE (no-LLM) smoke sweep over the ROM library.

For each ROM (.gb/.gbc via PyBoy, .gba via GBAEmulator, .nds via DeSmuME): boot headless, mash
START/A through the title screens (~first 300 frames), then run ~900 frames with the perceiver
attached — the registered game's own plugin when the ROM matches a world_mcp.GAMES entry, else the
zero-config generic path (PerceptionPlugin + FollowCameraPerceiver; NDS gets the NDS pair) — sampling
an observe every ~60 frames. Emits one JSON line per game: boot_ok, frames_advanced, n_observations,
screen_variety (distinct frame hashes — detects black/frozen screens), entities_seen_median,
pose_present, exception. Saves 3 PNG frames (early/mid/late) per game.

Infrastructure/reporting only — no gates, no oracle (watch={}), no paid probes. Crash-isolated per
game: one broken ROM records its exception and never kills the sweep.

Run environments (mgba/py-desmume are not everywhere): GB+NDS inside the gb-mcp-world Docker image,
GBA via the WSL ~/gba-spike env — see tools/run_smoke_sweep.sh.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
import traceback

# Repo root on sys.path so `python tools/smoke_sweep.py` works from anywhere (imports core/, games/).
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

# All emulator / world imports are LAZY (inside functions): this module must import with stdlib only,
# so the discovery/median helpers are unit-testable in CI (no pyboy/mgba/py-desmume there).

ROM_EXTS = {".gb": "gb", ".gbc": "gb", ".gba": "gba", ".nds": "nds"}
MASH_FRAMES = 300      # title-screen mash budget (frames)
RUN_FRAMES = 900       # main observed phase (frames)
SAMPLE_EVERY = 60      # observe/hash sample stride (frames)
_AGENT = "smoke"


def console_for(path: str) -> str | None:
    """Console family for a file path, or None for non-ROM files (zips, saves, misc)."""
    return ROM_EXTS.get(os.path.splitext(path)[1].lower())


def discover_roms(root: str, consoles: set[str] | None = None) -> list[str]:
    """All ROM files under root (recursive), skipping zips/non-ROMs; optionally filtered by console."""
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            c = console_for(f)
            if c and (consoles is None or c in consoles):
                out.append(os.path.join(dirpath, f))
    return sorted(out)


def _slug(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)[:80]


def _registry():
    """world_mcp.GAMES, imported with its module-level side effects undone (it dups fd1->stderr and
    chdirs to the repo root to keep its JSON-RPC channel clean — protocol hygiene we don't want here)."""
    saved_fd, saved_stdout = os.dup(1), sys.stdout
    try:
        saved_cwd = os.getcwd()
    except OSError:          # launched from a deleted dir (e.g. an ephemeral WSL docker bind-mount)
        saved_cwd = None
    try:
        import world_mcp
        return world_mcp.GAMES
    finally:
        os.dup2(saved_fd, 1)
        os.close(saved_fd)
        sys.stdout = saved_stdout
        if saved_cwd is not None:
            os.chdir(saved_cwd)


def _build_plugin(rom_path: str, out_dir: str):
    """(plugin, registered_game_key_or_None) for a ROM — mirrors world_mcp.World's construction,
    minus gateway/sandbox/oracle (watch={}: a free sweep reads no RAM)."""
    import importlib

    ext = os.path.splitext(rom_path)[1].lower()
    emulator = None
    if ext == ".nds":
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")   # headless: DeSmuME init needs it (PR #45)
        from core.nds_emulator import DeSmuMEEmulator
        emulator = DeSmuMEEmulator(rom_path, headless=True)
    elif ext == ".gba":
        from core.gba_emulator import GBAEmulator
        emulator = GBAEmulator(rom_path)

    base = os.path.basename(rom_path).lower()
    for key, spec in _registry().items():
        # cave_noire_baseline is an A/B control on the same ROM; "nds"'s rom is a placeholder.
        if key in ("cave_noire_baseline", "nds"):
            continue
        if os.path.basename(spec["rom"]).lower() == base:
            Plugin = getattr(importlib.import_module(spec["pkg"]), spec["plugin"])
            Perceiver = getattr(importlib.import_module(spec["perceiver_mod"]), spec["perceiver"])
            return Plugin(rom_path=rom_path, emulator=emulator, out_dir=out_dir, headless=True,
                          perceiver=Perceiver(), watch={}), key

    if ext == ".nds":   # generic NDS path = the registry's own "nds" pair, keyed by extension
        from core.nds_perceiver import NDSPerceiver
        from core.nds_perception_plugin import NDSPerceptionPlugin
        return NDSPerceptionPlugin(rom_path=rom_path, emulator=emulator, out_dir=out_dir,
                                   headless=True, perceiver=NDSPerceiver(), watch={}), None
    from core.grid_perceiver import FollowCameraPerceiver
    from core.perception_plugin import PerceptionPlugin
    return PerceptionPlugin(rom_path=rom_path, emulator=emulator, out_dir=out_dir,
                            headless=True, perceiver=FollowCameraPerceiver(), watch={}), None


def sweep_one(rom_path: str, out_root: str, mash_frames: int = MASH_FRAMES,
              run_frames: int = RUN_FRAMES, sample_every: int = SAMPLE_EVERY,
              max_seconds: float = 600.0) -> dict:
    """Boot + mash + observe one ROM; ALWAYS returns a record (exceptions recorded, never raised)."""
    name = os.path.splitext(os.path.basename(rom_path))[0]
    rec: dict = {"game": name, "rom": rom_path, "console": console_for(rom_path),
                 "boot_ok": False, "frames_advanced": 0, "n_observations": 0,
                 "screen_variety": 0, "entities_seen_median": None, "pose_present": False,
                 "registered_game": None, "exception": None, "timeout": False, "duration_s": 0.0}
    t0 = time.time()
    plugin = None
    frames_dir = os.path.join(out_root, "frames", _slug(name))
    try:
        plugin, key = _build_plugin(rom_path, os.path.join(out_root, "games", _slug(name)))
        rec["registered_game"] = key
        emu = plugin.emu
        emu.tick(1)                     # prove the core actually advances before claiming boot_ok
        rec["boot_ok"] = True

        i = 0                           # title mash: alternate START / A (~press+ticks ≈ 48 frames each)
        while emu.frame < mash_frames:
            if time.time() - t0 > max_seconds:
                raise TimeoutError(f"mash phase exceeded {max_seconds}s")
            emu.press("start" if i % 2 == 0 else "a", hold_frames=8)
            emu.tick(24)
            i += 1

        hashes: list[str] = []
        ent_counts: list[int] = []
        n_samples = max(1, run_frames // sample_every)
        save_at = {0, n_samples // 2, n_samples - 1}        # early / mid / late PNGs
        target = emu.frame
        for s in range(n_samples):
            if time.time() - t0 > max_seconds:
                rec["timeout"] = True
                break
            target += sample_every
            while emu.frame < target:
                emu.tick(min(8, target - emu.frame))
            hashes.append(hashlib.md5(emu.screen_ndarray().tobytes()).hexdigest())
            obs = plugin.observe(_AGENT)
            rec["n_observations"] += 1
            data = obs.data or {}
            if (data.get("pose") or {}).get("value") is not None:
                rec["pose_present"] = True
            ents = (data.get("spatial_memory") or {}).get("entities")
            if isinstance(ents, list):
                ent_counts.append(len(ents))
            if s in save_at:
                os.makedirs(frames_dir, exist_ok=True)
                emu.save_screen(os.path.join(frames_dir, f"sample_{s:02d}_frame_{emu.frame}.png"))
        rec["screen_variety"] = len(set(hashes))
        if ent_counts:
            rec["entities_seen_median"] = statistics.median(ent_counts)
        rec["frames_advanced"] = int(emu.frame)
    except Exception as e:              # crash isolation: record, never re-raise
        rec["exception"] = {"type": type(e).__name__, "msg": str(e)[:500],
                            "trace_tail": traceback.format_exc().strip().splitlines()[-3:]}
    finally:
        if plugin is not None:
            try:
                plugin.close()
            except Exception:
                pass
        rec["duration_s"] = round(time.time() - t0, 1)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description="Free smoke sweep over the ROM library (no LLM).")
    ap.add_argument("--rom", action="append", default=[], help="one ROM path (repeatable)")
    ap.add_argument("--all-dir", default=None, help="sweep every ROM under this directory (recursive)")
    ap.add_argument("--consoles", default=None, help="comma filter: gb,gba,nds (with --all-dir)")
    ap.add_argument("--out", required=True, help="JSONL report path (appended per game)")
    ap.add_argument("--limit", type=int, default=None, help="only the first N discovered ROMs")
    ap.add_argument("--mash-frames", type=int, default=MASH_FRAMES)
    ap.add_argument("--run-frames", type=int, default=RUN_FRAMES)
    ap.add_argument("--sample-every", type=int, default=SAMPLE_EVERY)
    ap.add_argument("--max-seconds", type=float, default=600.0, help="per-game wall-clock cap")
    args = ap.parse_args()

    roms = list(args.rom)
    if args.all_dir:
        consoles = set(args.consoles.split(",")) if args.consoles else None
        roms += discover_roms(args.all_dir, consoles)
    if args.limit:
        roms = roms[:args.limit]
    if not roms:
        print("no ROMs to sweep (need --rom or --all-dir)", file=sys.stderr)
        return 2

    out_root = os.path.dirname(os.path.abspath(args.out)) or "."
    os.makedirs(out_root, exist_ok=True)
    for n, rom in enumerate(roms, 1):
        print(f"[{n}/{len(roms)}] {os.path.basename(rom)} ...", file=sys.stderr, flush=True)
        rec = sweep_one(rom, out_root, args.mash_frames, args.run_frames,
                        args.sample_every, args.max_seconds)
        with open(args.out, "a", encoding="utf-8") as f:     # append per game: partial runs keep results
            f.write(json.dumps(rec) + "\n")
        status = "OK" if rec["boot_ok"] and not rec["exception"] else \
            (rec["exception"] or {}).get("type", "FAIL")
        print(f"    -> {status} frames={rec['frames_advanced']} variety={rec['screen_variety']} "
              f"obs={rec['n_observations']} ({rec['duration_s']}s)", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
