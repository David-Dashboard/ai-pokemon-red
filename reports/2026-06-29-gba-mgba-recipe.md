# GBA via mgba — proven build recipe + why there's no container yet (2026-06-29)

`core/gba_emulator.py` (mgba flavour of the `Emulator` Protocol) is **validated**: 5/5 against real
Pokémon Emerald via the WSL spike build at `~/gba-spike` — non-blank framebuffer `(160,240,3)` max 255,
WRAM reads, savestate round-trip. The emulator works. **What does not exist is a container** — the
agent-generated `docker/gba.Dockerfile` was dropped because its install recipe was fiction. This note
records the *real* recipe so the container can be built when Docker is back up.

## The trap: there is NO `mgba` package on PyPI
Confirmed 2026-06-29: `pip download mgba` (any version, wheel or sdist) → "No matching distribution".
Neither `pip install mgba` nor `uv add mgba` can ever work. mgba's Python bindings only exist via a
**source build**. The dropped Dockerfile's `pip install mgba==0.10.2` fast-path was hallucinated.

## The proven recipe (reconstructed from `~/gba-spike` artifacts)
The spike source-built mgba 0.10.2 and **hand-patched a link-time gap** — there is no clean one-shot
cmake invocation. Steps, in order:

1. **Source.** `git clone --branch 0.10.2 https://github.com/mgba-emu/mgba.git`
2. **cmake** (flags actually used, from the spike's `CMakeCache.txt` — note **`ENABLE_EREADER` is NOT a
   real option**; the agent invented it):
   `BUILD_PYTHON=ON  BUILD_SHARED=ON  CMAKE_BUILD_TYPE=Release` with the `USE_*` family
   (`USE_PNG/USE_ZLIB/USE_LZMA/USE_MINIZIP/USE_EPOXY=ON`, `USE_FFMPEG/USE_SQLITE3/USE_LIBZIP/USE_ELF=OFF`).
3. **The EReader stub patch (the part the Dockerfile missed entirely).** The 0.10.2 build leaves the
   `EReaderAnchorList*` / `EReaderBlockList*` symbols **undefined**, so the python binding fails to link.
   The spike fixed this by compiling a tiny stub object exporting those symbols
   (`libmgba_ereader_stubs.so`), merging it into libmgba (`libmgba_with_stubs.so` →
   `libmgba_patched.so.0.10.2`), and symlinking it as `libmgba.so.0.10` so the abi3 binding loads the
   patched lib. **The exact stub-generation commands were done interactively and are not captured** —
   reconstructing them (enumerate undefined `EReader*` syms → emit empty bodies → compile → relink) is
   the one genuinely unknown step. This is why a clean-room Dockerfile cannot be written blind.
4. **Python deps** the binding needs at import time (3.8 venv): `cffi`, `cached-property`, plus `numpy`,
   `pillow`. (These were missing from the spike venv initially and had to be added.)

## Runtime env (how `core/gba_emulator.py` actually loaded it)
```
LD_LIBRARY_PATH=~/gba-spike                                    # finds the patched libmgba.so.0.10
PYTHONPATH=~/gba-spike/mgba-build/python/lib.linux-x86_64-3.8  # the abi3 mgba/ binding
```
mgba logs GBA BIOS/DMA chatter to **stdout** (not stderr) during boot — expect noise; it's normal.

## To containerize later (when Docker is up)
Base `python:3.11-slim` (abi3 binding loads fine on 3.11). Carry steps 1–4 above; the open work is
scripting step 3 reproducibly and then build-testing the image — neither is possible while Docker is
down. The container is **packaging only**: on WSL/Linux the emulator already runs without it, which is
the path for the GBA end-to-end bring-up.
