# NDS emulation plan — extending the world interface to Nintendo DS

_Parallel-fork plan. Bases the design on the existing **GB/GBC** (PyBoy) and **GBA** (mgba/pyboy-advance)
emulator work. Goal: bring NDS games into the same screen-only agent harness, reusing the decoupling seam
that already carried us GB → GBA._

---

## 0. The principle that makes this tractable (proven on GB → GBA)

The whole world interface hides behind one tiny seam — the **`Emulator` Protocol** (`core/gb_emulator.py`):

```
press(button, hold, settle) · tick(frames) · read(addr) · screen_ndarray() -> (H,W,C) uint8
save_screen(path) · save_state(path) · load_state(path) · frame · close()
```

The perceiver consumes `screen_ndarray()` and is **source-agnostic** — it has no idea whether PyBoy, mgba, or
desmume produced the frame. Adding a console = **implement those ~9 methods**; perception is untouched. This
is the same move that took us from GB (PyBoy) to GBA (mgba). NDS is the next rung — *with three genuine deltas
the Protocol doesn't yet cover* (§3).

## ✅ Spike results (2026-06-29) — py-desmume VERIFIED 4/4 on Windows

The de-risking spike is **done and passed** — `py-desmume==0.0.9` installs on **Windows / Python 3.12** (no
Linux container required, unlike GBA's mgba) and delivers **all four capabilities** against New Super Mario
Bros:

| Capability | Result | py-desmume call (verified) |
|---|---|---|
| Framebuffer | ✅ `(384,256,3)` — **both screens stacked** (top 0:192, bottom 192:384) | `np.frombuffer(emu.display_buffer_as_rgbx())[:256*384*4].reshape(384,256,4)[:,:,:3]` |
| RAM read (oracle) | ✅ full 4 MB main RAM, live values | `emu.memory.unsigned[addr]` / `.signed` / `.read(s,e,size)` |
| Savestate | ✅ roundtrip reverts | `emu.savestate.save_file(p)` / `load_file(p)` |
| Input | ✅ buttons + **touch** | `emu.input.keypad_add_key(keymask(Keys.KEY_*))` / `keypad_rm_key`; `touch_set_pos(x,y)` / `touch_release()` |
| Tick / close | ✅ | `for _ in range(n): emu.cycle()`; `emu.destroy()`; `emu.reset()` |

**Gotcha found:** **DSi-enhanced ROMs (Pokémon White) render blank** without DSi firmware — boot a **plain-DS**
ROM (NSMB, Mario Kart DS) or supply the DSi BIOS. **Verdict: py-desmume is the binding; NDS is *more*
Windows-friendly than GBA was.** This retires the "Linux-container-only" worry — a container is still nice for
reproducibility but is no longer required for parity. The §2 table below is now settled in py-desmume's favour.

## 1. What already exists (the prior art this plan reuses)

- **GB/GBC — `core/gb_emulator.py` (`PyBoyEmulator`):** the reference implementation of the Protocol;
  8-button input; headless ("null" window, no SDL/display); RAM `read()` for the scoring oracle; savestates.
- **The container pattern — `Dockerfile`:** `python:3.11-slim` + `pip install` the emulator, `COPY core/ games/
  world_mcp.py`, ROMs **mounted read-only** (copyrighted, never in the image), `runs/` mounted writable. This is
  the project's stated **"containerize"** preference — reproducible across Win/Linux/Pi.
- **GBA — the lesson learned (session 2026-06-28):**
  - **Windows native bindings are flaky.** `mgba` has no Windows wheel; `pyboy-advance` installs on Windows but
    **lacks `read()` (RAM) and savestates** — fine for pixels+buttons, useless for the oracle or branching.
  - **Linux is the reliable, full-parity path.** A WSL `mgba` spike passed **4/4** — framebuffer + RAM read +
    savestate roundtrip + input — and the verdict was **containerize it** (a Dockerfile mirroring the GB one).
  - **Spike-first.** Before any build, a throwaway spike proved the binding gave all four capabilities against a
    real ROM. That de-risking step is mandatory here too.

**⇒ NDS inherits this exact strategy: pick a Linux-viable Python binding, spike it for full parity, then
containerize behind the same Protocol.**

## 2. Emulator + binding choice (the GBA decision, applied to NDS)

| Option | Python binding | RAM read | Savestates | Platform | Verdict |
|---|---|---|---|---|---|
| **DeSmuME** | **`py-desmume`** (mature; used by SkyTemple) | ✅ memory API | ✅ | Win + Linux | **primary candidate** — full API, proven in Python |
| melonDS | none official (libretro only) | via libretro | via libretro | — | more accurate but weak Python surface |
| libretro core (desmume/melonds) | a libretro Python wrapper / ctypes shim | ✅ `get_memory_data` | ✅ `serialize` | any | fallback (same shape as the GBA libretro idea) |

**Recommendation: `py-desmume` first** — it's the maturest Python NDS API (full framebuffer, input, memory,
savestates), and unlike GBA's `mgba` it plausibly works on **both** Windows and Linux. Mirror the GBA lesson
anyway: **prefer the Linux container** for reproducibility, and **spike before committing**. If `py-desmume`
disappoints, the **libretro-core ctypes shim** is the robust fallback (the libretro memory + serialize API is
guaranteed, exactly as reasoned for GBA).

## 3. The three genuine deltas vs GB/GBA (where NDS is *not* a drop-in)

These are real and the Protocol/perception must grow to cover them.

**Δ1 · Dual screen (256×192 × 2).** GB/GBA return one frame; NDS has two. Decision for `screen_ndarray()`:
return **both screens stacked** → `(384, 256, 3)` by default (perception can crop), with an optional
"which screen" selector. `py-desmume` exposes both buffers. The perceiver picks the gameplay screen (often the
top; the bottom is frequently a map/touch UI) — a small per-game or heuristic choice, *not* a Protocol change.

**Δ2 · Touch (the new action).** NDS adds a stylus → an action the button-only `press()` can't express.
**Extend the Protocol with an optional `touch(x, y)` (and `touch_release`)**, and add `l`,`r` to the button set
(NDS has shoulders, like GBA). This ripples beyond the emulator: the **gateway action space** and the **brain's
tool surface** must learn a touch action. Button-only NDS games (Mario Kart DS, New Super Mario Bros) work
without it; touch-driven games (Phoenix Wright, Professor Layton, Spirit Tracks) *need* it. **Start button-only;
add touch as a second increment.**

**Δ3 · 3D rendering (the perception cell shift).** Many NDS games are 3D-rendered → the tile-based primitives
(`tilemap` recurrence, `best_shift` ego-motion, `blob` segmentation) assume flat 2D pixel art and **degrade or
break**. This is the perception ontology's *substrate = 3D / natural-image* cell — a genuinely harder problem.
**Start with 2D NDS games** (Pokémon Black/White overworld, NSMB 2.5D, Phoenix Wright) where the existing
primitives transfer with only a **resolution recalibration** (256×192 vs 160×144 → `best_shift.max_shift`, tile
grid, blob `min_area`). Treat 3D-robust perception as a later, measured climb — not a launch requirement.

## 4. Build order (the Realizer Ladder — cheapest first, mirrors the GBA path)

1. **Spike (de-risk, no commitment). ✅ DONE 2026-06-29 — passed 4/4 on Windows** (see "Spike results" above).
   `py-desmume==0.0.9` gave framebuffer (both screens) + RAM read + savestate + input/touch against NSMB. The
   libretro-shim fallback is unneeded. (Use a **plain-DS** ROM, not DSi-enhanced.)
2. **`core/nds_emulator.py`.** Implement the Protocol mirroring `PyBoyEmulator`: dual-screen `screen_ndarray()`
   (stacked), `BUTTONS` = GB's 8 + `l`,`r`, `read()`/savestates from the binding, lazy/guarded import. **No touch
   yet.**
3. **Containerize.** A `Dockerfile.nds` mirroring the GB one (`python:3.11-slim` + `py-desmume` + system deps;
   ROMs mounted read-only). Reproducible across machines — the project preference.
4. **Wire ONE 2D game + measure.** Point `PerceptionPlugin` + the shared `GridPerceiver` at it (recalibrated
   constants), run the generic bench, and **instrument where perception holds vs breaks** (dual-screen choice,
   2D-vs-3D, resolution). The bench is the prioritization signal — same discipline as GB/GBA.
5. **Increment 2 — touch.** Add `touch(x,y)` to the Protocol + gateway + brain tool surface; wire a touch game
   (Phoenix Wright). 
6. **Climb to 3D-robust perception only on measured failure** (a 3D game where the 2D primitives demonstrably
   fail) — not speculatively.

## 5. Open decisions to settle before/at the spike

- **Which screen(s) to perceive** by default — both stacked, or a gameplay-screen heuristic. (Lean: stacked,
  let the perceiver crop.)
- **py-desmume on Windows vs Linux-container only** — the spike answers this; mirror GBA and prefer the container.
- **Touch action shape** — `touch(x,y)` absolute pixel, vs a higher-level "tap region." (Lean: absolute pixel,
  let the brain reason; matches "human-grade controls.")
- **ROM set** — `roms/nds/` already holds Pokémon White, Mario Kart DS, NSMB, Spirit Tracks, Phoenix Wright,
  Layton, etc. Start: **Pokémon White** (2D overworld, has a RAM map → oracle) or **NSMB** (2.5D, button-only).

## 6. What stays unchanged (the reuse win)

The **brain, the `SymbolicState` seam, `core/contracts.py`, `PerceptionPlugin`, `GridPerceiver`, the bench
harness, the oracle/no-leak discipline** — all reused unchanged. NDS adds: one new `Emulator` implementation,
one Dockerfile, a touch action (increment 2), and resolution recalibration. That's the constancy claim in
action — a new console swaps the emulator, not the agent.
