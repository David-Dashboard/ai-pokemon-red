"""One-off check: do the checkpoint bytes survive a save_state -> load_state round-trip in
the SAME emulator instance? (Same one-instance-per-process constraint as everything else here
-- this never creates a second DeSmuME().)

Usage: <venv>/python.exe verify_reload.py --assets <primary-checkout> --state <path>
"""
from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--repo", default=None)
    ap.add_argument("--state", required=True)
    args = ap.parse_args()

    assets = os.path.abspath(args.assets)
    repo = os.path.abspath(args.repo) if args.repo else assets
    sys.path.insert(0, repo)
    from core.nds_emulator import DeSmuMEEmulator  # noqa: E402

    rom = os.path.join(assets, "roms/nds/Mario Kart DS (USA) (En,Fr,De,Es,It).nds")
    emu = DeSmuMEEmulator(rom, headless=True)
    emu.load_state(args.state)
    before90, before94 = emu.read(0x022C8090), emu.read(0x022C8094)
    tmp = args.state + ".reload_test"
    emu.save_state(tmp)
    emu.load_state(tmp)
    after90, after94 = emu.read(0x022C8090), emu.read(0x022C8094)
    emu.close()
    os.remove(tmp)

    print(f"before: ckpt90={before90} ckpt94={before94}")
    print(f"after save+reload: ckpt90={after90} ckpt94={after94}")
    print(f"survives_reload: {before90 == after90 and before94 == after94}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
