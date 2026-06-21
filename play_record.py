"""Interactive PLAY + RECORD: you guide the game in a window; flip on the auto-explorer whenever you
want hands-free dense tile-sampling. Captures probe-compatible data (frames + oracle.jsonl) across as
many maps/tilesets as you can reach (Viridian, Route 1/2, the Forest, Pewter, Brock's gym, Mt Moon,
Cerulean, Misty...), which is the cross-tileset data we lack to test the tile-fingerprint vs CLIP /
overlap-window questions.

This is the only reliable way to get DEEP data: the auto random-walk can't beat gym trainers and the
LLM agent can't reach there either. So YOU drive the hard parts (battles, gyms, gates, menus) and hand
control to the free frontier autopilot (ExploreBrain) inside each area to bump walls + walk floors,
which densely labels walkable/blocked tiles by appearance.

RAM stays the non-leaking ORACLE (the side-log only); the perceiver sees pixels only — same posture as
a normal run. Data lands in runs/<name>/ as frame_NNNNNN.png + oracle.jsonl, exactly the format
eval/probe_tilemap.py, eval/probe_walkability_learn.py and eval/replay_tilemap.py consume.

Controls (the window must be focused):
  Move = Arrow keys      A = A key      B = S key      Start = Enter      Select = Backspace
  TAB  = toggle the auto-explorer on/off      C = save a checkpoint .state      ESC = quit & finalize
  (PyBoy extras: SPACE = fast-forward while held, Z/X = its own save/load)

Run:  uv run python play_record.py --rom roms/PokemonRed.gb --load-state start.state --name kanto1 [--sound]
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import random
import time

from core.brains import ExploreBrain
from core.contracts import Observation
from core.perception import PerceptMemory
from games.pokemon_red.emulator import ensure_sdl_dll_path
from games.pokemon_red.memory_map import read_state
from games.pokemon_red.perceiver import OverworldPerceiver

_DIR_OF = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


def infer_dir(prev, cur):
    """Direction of a within-map tile step (prev/cur = (map,x,y)); None across maps or no move."""
    if prev is None or cur is None or prev[0] != cur[0]:
        return None
    dx, dy = cur[1] - prev[1], cur[2] - prev[2]
    if abs(dx) >= abs(dy):
        return "right" if dx > 0 else "left" if dx < 0 else None
    return "down" if dy > 0 else "up"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default="roms/PokemonRed.gb")
    ap.add_argument("--load-state", default="start.state")
    ap.add_argument("--name", default="manual", help="dataset dir under runs/")
    ap.add_argument("--sound", action="store_true")
    args = ap.parse_args()

    out = os.path.join("runs", args.name)
    os.makedirs(out, exist_ok=True)
    oracle_path = os.path.join(out, "oracle.jsonl")

    ensure_sdl_dll_path()
    from pyboy import PyBoy
    pb = PyBoy(args.rom, window="SDL2", sound_emulated=args.sound,
               sound_volume=100 if args.sound else 0)
    pb.set_emulation_speed(1)             # PyBoy paces to real time; SPACE still fast-forwards
    if args.load_state and os.path.exists(args.load_state):
        with open(args.load_state, "rb") as f:
            pb.load_state(f)
    pb.tick(4, render=True)

    import sdl2                            # same SDL context PyBoy initialised; shares the keyboard state
    nkeys = ctypes.c_int(0)

    rd = lambda a: pb.memory[a]
    perceiver = OverworldPerceiver()
    mem = PerceptMemory()
    explore = ExploreBrain("rec", single_step=True, probe_interactables=True)

    S = {"auto": False, "quit": False, "checkpoint": 0}
    held = {"tab": False, "c": False, "esc": False}
    oracle = open(oracle_path, "a", encoding="utf-8")
    step = {"n": 0}

    def hotkeys():
        ks = sdl2.SDL_GetKeyboardState(ctypes.byref(nkeys))
        def edge(name, scancode):
            now = bool(ks[scancode])
            fired = now and not held[name]
            held[name] = now
            return fired
        if edge("tab", sdl2.SDL_SCANCODE_TAB):
            S["auto"] = not S["auto"]
            print(f"[auto-explore {'ON' if S['auto'] else 'OFF'}]  (map {rd(0xD35E)})")
        if edge("c", sdl2.SDL_SCANCODE_C):
            S["checkpoint"] += 1
            p = os.path.join(out, f"checkpoint_{S['checkpoint']:02d}.state")
            with open(p, "wb") as f:
                pb.save_state(f)
            print(f"[checkpoint -> {p}]")
        if edge("esc", sdl2.SDL_SCANCODE_ESCAPE):
            S["quit"] = True

    def pump(n):
        """Advance n frames (applying human input + pacing), polling hotkeys. False => stop."""
        for _ in range(n):
            if not pb.tick(1, True):
                S["quit"] = True
            hotkeys()
            if S["quit"]:
                return False
        return True

    def press(b, hold=8, settle=16):
        pb.button(b, delay=hold)
        return pump(hold + settle)

    def log(st, sym):
        path = os.path.join(out, f"frame_{step['n']:06d}.png")
        pb.screen.image.save(path)
        la = sym.last_action or {}
        sm = sym.spatial_memory or {}
        oracle.write(json.dumps({
            "step": step["n"], "t": time.time(), "frame": pb.frame_count,
            "screen_path": path.replace("\\", "/"), "mode": "auto" if S["auto"] else "manual",
            "map_id": st["map_id"], "x": st["x"], "y": st["y"],
            "in_battle": st["in_battle"], "badges": st["badges"],
            "perceived": {"outcome": la.get("outcome"), "action": la.get("action"),
                          "diff": la.get("diff"), "pose": (sym.pose or {}).get("value"),
                          "area": (sym.pose or {}).get("area"), "context": sym.context,
                          "confidence": sym.confidence, "walls_here": sm.get("walls_here"),
                          "screen_text": sym.screen_text, "tile_types_seen": sm.get("tile_types_seen")},
        }) + "\n")
        oracle.flush()
        step["n"] += 1

    print("Controls: Arrows=move  A=A  S=B  Enter=Start  Backspace=Select  "
          "SPACE=fast-forward (hold)")
    print(f"          TAB=toggle auto-explore   C=checkpoint .state   ESC=quit & finalize")
    print(f"recording -> {out}/\n")

    last_act = None
    last_pos = (rd(0xD35E), rd(0xD362), rd(0xD361))
    last_battle = rd(0xD057)

    while not S["quit"]:
        if S["auto"]:
            frame = pb.screen.ndarray
            st = read_state(rd)
            sym = perceiver.perceive(frame, mem, {"last_action": last_act})
            log(st, sym)
            call = explore.decide(Observation(data=sym.to_dict(), text="", agent_id="rec", t=time.time()), [], {})
            bs = (call.args.get("buttons") if call else None) or [random.choice(list(_DIR_OF))]
            for b in bs:
                if not press(b):
                    break
            last_act = "+".join(bs)
            last_pos = (st["map_id"], st["x"], st["y"])
            last_battle = st["in_battle"]
        else:
            if not pump(3):                       # let the human play a few frames
                break
            st = read_state(rd)
            pos = (st["map_id"], st["x"], st["y"])
            if pos != last_pos or st["in_battle"] != last_battle:
                pump(6)                           # brief settle after the step
                frame = pb.screen.ndarray
                st = read_state(rd)
                pos = (st["map_id"], st["x"], st["y"])
                sym = perceiver.perceive(frame, mem, {"last_action": infer_dir(last_pos, pos)})
                log(st, sym)
                last_pos, last_battle = pos, st["in_battle"]

    oracle.close()
    print(f"\nsaved {step['n']} rows + frames to {out}/   tile-types learned: {len(mem.data.get('tilemap', []))}")
    pb.stop(save=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
