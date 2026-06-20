"""Reset the aria (Red) memory to a clean SEED state before a fresh iteration.

David's standing requirement: every paid run starts with ZERO accumulated experience — the agent
must begin each episode with no carried-over learning, so iterations are a fair comparison. But the
agent's *constitution* (who Red is: goals / type chart / how-to-play lessons) is the defined starting
point, not "experience", so it's KEPT.

What this does to `<aria>/pokemon-red-data/`:
  * KEEP the seed constitution (git-tracked): goals.md, core_memory.md, lessons.md, README.md, .gitignore
    (and best-effort `git checkout` them, in case a run ever mutates them).
  * KEEP the embedding-model caches (embed_model_cache/, .hf/) — model weights, not memory; deleting
    them only forces a slow re-download.
  * DELETE everything else (the agent's run-generated experience): earlier_today.json, usage.jsonl,
    memstore.db, journal/, and any episodic/notes/core_history the agent writes.

Per the data dir's own README + .gitignore, "everything the running agent writes here stays
untracked" — so "remove all that isn't seed or a model cache" is exactly the experience wipe.

Safe by default: prints the plan and changes NOTHING unless you pass --yes.

    uv run python reset_aria_memory.py            # dry run: show what WOULD be wiped
    uv run python reset_aria_memory.py --yes       # actually wipe (run before each paid iteration)
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import zipfile

# The seed constitution (git-tracked) + the model-weight caches — everything NOT in here is
# run-generated experience and gets wiped for a clean slate.
SEED = {".gitignore", "goals.md", "core_memory.md", "lessons.md", "README.md"}
KEEP_CACHES = {"embed_model_cache", ".hf"}
SEED_TRACKED = ["goals.md", "core_memory.md", "lessons.md", "README.md", ".gitignore"]


def _default_data_dir() -> str:
    # ai-pokemon-red and ai-aria are sibling repos under .../Github/.
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "ai-aria", "pokemon-red-data"))


def _default_archive_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "aria_memory_archives")


def is_clean(data_dir: str | None = None) -> bool:
    """True if aria's data dir holds NO run-generated experience — only the seed + model caches remain
    (a reset has run and nothing has been written since). The paid drivers use this as a FAIL-LOUD
    precondition under the beta learning boundary (S3): aria now OWNS the within-run memory, so a run
    that starts on un-reset memory silently leaks the PRIOR run across the across-run boundary. A name
    check suffices in practice — every aria turn appends to `journal/`, so any un-reset state shows a
    non-seed entry here even though a git-reverted `lessons.md`/`core_memory.md` (both seed) read clean."""
    d = data_dir or _default_data_dir()
    if not os.path.isdir(d):
        return True   # nothing there -> nothing to leak
    return all(name in SEED or name in KEEP_CACHES for name in os.listdir(d))


def _archive(data_dir: str, archive_dir: str) -> tuple[str, int]:
    """Zip the agent's memory (seed + accumulated experience; NOT the bulky model-weight caches) to a
    dated, NUMBERED archive BEFORE wiping — David wants every iteration's data preserved. The number
    is the next free index in archive_dir. Returns (zip_path, iteration_index)."""
    os.makedirs(archive_dir, exist_ok=True)
    nums = [int(m.group(1)) for f in os.listdir(archive_dir)
            if (m := re.match(r"iter-(\d+)_", f))]
    idx = (max(nums) + 1) if nums else 1
    path = os.path.join(archive_dir, f"iter-{idx:03d}_{datetime.date.today().isoformat()}.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(data_dir):
            dirs[:] = [sub for sub in dirs if sub not in KEEP_CACHES]  # skip model-weight caches
            for f in files:
                fp = os.path.join(root, f)
                z.write(fp, os.path.relpath(fp, data_dir))
    return path, idx


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Wipe aria/Red run-generated experience; keep the seed.")
    ap.add_argument("--data-dir", default=_default_data_dir(),
                    help="path to aria's pokemon-red-data dir (default: the sibling ai-aria repo)")
    ap.add_argument("--yes", action="store_true",
                    help="actually archive + delete (default is a dry run that only prints the plan)")
    ap.add_argument("--archive-dir", default=_default_archive_dir(),
                    help="where to store the pre-wipe memory zips (default: ./aria_memory_archives)")
    ap.add_argument("--no-archive", action="store_true",
                    help="skip the pre-wipe archive (NOT recommended; each iteration's data is kept)")
    args = ap.parse_args(argv)

    d = args.data_dir
    if not os.path.isdir(d):
        print(f"error: data dir not found: {d}\n(point --data-dir at aria's pokemon-red-data)",
              file=sys.stderr)
        return 2

    keep, wipe = [], []
    for name in sorted(os.listdir(d)):
        (keep if name in SEED or name in KEEP_CACHES else wipe).append(name)

    print(f"aria memory reset  (data dir: {d})")
    print(f"  KEEP  ({len(keep)}): {', '.join(keep) or '(none)'}")
    print(f"  WIPE  ({len(wipe)}): {', '.join(wipe) or '(none)'}")
    if not args.no_archive:
        print(f"  ARCHIVE before wipe -> {os.path.join(args.archive_dir, 'iter-NNN_<date>.zip')} "
              f"(memory snapshot, minus model caches)")
    if not args.yes:
        print("\nDRY RUN - nothing archived or deleted. Re-run with --yes to archive + wipe.")
        return 0

    if not args.no_archive:
        zpath, idx = _archive(d, args.archive_dir)
        print(f"archived iteration {idx} -> {zpath}  ({os.path.getsize(zpath):,} bytes)")

    for name in wipe:
        p = os.path.join(d, name)
        if os.path.isdir(p) and not os.path.islink(p):
            shutil.rmtree(p)
        else:
            os.remove(p)
    # Restore the tracked seed in case a run mutated it. Under the beta learning boundary (S3) aria's
    # durable memory IS the authoritative within-run store, so this git-revert is LOAD-BEARING for the
    # no-across-run-leak invariant (a run's <lesson>/<core_update> writes to lessons.md/core_memory.md
    # must be reverted) — it now FAILS HARD rather than best-effort, and verifies the result.
    try:
        r = subprocess.run(["git", "-C", d, "checkout", "--", *SEED_TRACKED],
                           check=False, capture_output=True, text=True)
    except FileNotFoundError:
        print("ERROR: git not found, but the seed-revert is load-bearing under the beta learning "
              "boundary (a run may have mutated lessons.md/core_memory.md). Install git, or restore "
              "the seed by hand, then re-run.", file=sys.stderr)
        return 3
    if r.returncode != 0:
        print(f"ERROR: git checkout of the seed failed (rc={r.returncode}): {r.stderr.strip()}\n"
              f"The seed may be mutated; refusing to certify a clean start.", file=sys.stderr)
        return 3
    dirty = [f for f in SEED_TRACKED
             if subprocess.run(["git", "-C", d, "diff", "--quiet", "HEAD", "--", f],
                               capture_output=True).returncode != 0]
    if dirty:
        print(f"ERROR: after checkout these seed files still differ from HEAD: {', '.join(dirty)}. "
              f"Refusing to certify a clean start (the next run could leak prior-run learning).",
              file=sys.stderr)
        return 3

    print(f"\nDONE - wiped {len(wipe)} item(s); seed git-reverted + verified vs HEAD. Red starts clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
