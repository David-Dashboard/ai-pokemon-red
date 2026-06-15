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
import os
import shutil
import subprocess
import sys

# The seed constitution (git-tracked) + the model-weight caches — everything NOT in here is
# run-generated experience and gets wiped for a clean slate.
SEED = {".gitignore", "goals.md", "core_memory.md", "lessons.md", "README.md"}
KEEP_CACHES = {"embed_model_cache", ".hf"}
SEED_TRACKED = ["goals.md", "core_memory.md", "lessons.md", "README.md", ".gitignore"]


def _default_data_dir() -> str:
    # ai-pokemon-red and ai-aria are sibling repos under .../Github/.
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "ai-aria", "pokemon-red-data"))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Wipe aria/Red run-generated experience; keep the seed.")
    ap.add_argument("--data-dir", default=_default_data_dir(),
                    help="path to aria's pokemon-red-data dir (default: the sibling ai-aria repo)")
    ap.add_argument("--yes", action="store_true",
                    help="actually delete (default is a dry run that only prints the plan)")
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
    if not args.yes:
        print("\nDRY RUN - nothing deleted. Re-run with --yes to wipe and start the agent clean.")
        return 0

    for name in wipe:
        p = os.path.join(d, name)
        if os.path.isdir(p) and not os.path.islink(p):
            shutil.rmtree(p)
        else:
            os.remove(p)
    # Belt-and-suspenders: restore the tracked seed in case a run ever mutated it (best effort).
    try:
        subprocess.run(["git", "-C", d, "checkout", "--", *SEED_TRACKED],
                       check=False, capture_output=True)
    except FileNotFoundError:
        print("  (git not found — skipped restoring tracked seed; the seed files were kept as-is)")

    print(f"\nDONE - wiped {len(wipe)} item(s); seed + model caches kept. Red starts clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
