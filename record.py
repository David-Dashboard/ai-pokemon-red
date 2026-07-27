"""Generalized RAW recorder — the game-AGNOSTIC data substrate for cross-game perception work.

Runs on ANY Game Boy / GBC ROM and logs the minimal universal substrate so we can develop (and
re-develop) odometry/perception OFFLINE without re-collecting and without baking in any one game's
camera assumptions: per step it saves the FRAME + the EXACT buttons that were active + (optional) a
raw WRAM snapshot. NO dependency on the Pokémon perceiver / memory map — pixels + inputs only.

Two drive modes:
  --mode auto   headless, a game-agnostic randomized button policy (bulk breadth, unattended, fast).
  --mode human  a window you play; captures the buttons you actually hold each interval. TAB toggles
                the auto policy on/off mid-session, C saves a .state checkpoint, ESC quits.

Output under runs/<name>/:
  frame_NNNNNN.png        one per recorded step
  buttons.jsonl           {step, t, frame, screen_path, buttons:[...], mode}
  ram.bin                 (only with --ram) raw 8 KB WRAM per step, indexed by step
  meta.json               rom + recorder config

Examples:
  uv run python record.py --rom "roms/Kirby's Dream Land (USA, Europe).gb" --name kirby_auto --mode auto --steps 3000
  uv run python record.py --rom "roms/...Link's Awakening...gb" --name zelda_human --mode human --keys wasd
"""
from __future__ import annotations

import argparse
import ctypes
import datetime
import json
import os
import random
import re
import time

GB_BUTTONS = ("up", "down", "left", "right", "a", "b", "start", "select")


def ensure_sdl_dll_path() -> None:
    """Best-effort fix for PySDL2 DLL discovery (only needed for the visible window)."""
    if os.environ.get("PYSDL2_DLL_PATH"):
        return
    try:
        import sdl2dll
        for base in list(getattr(sdl2dll, "__path__", [])):
            dll = os.path.join(base, "dll")
            if os.path.exists(os.path.join(dll, "SDL2.dll")):
                os.environ["PYSDL2_DLL_PATH"] = dll
                return
    except Exception:
        pass


def remap_wasd() -> None:
    """Repoint PyBoy's SDL2 keymap to WASD movement + J/K for A/B (PyBoy hardcodes arrows + a/s).
    In-place update of the module-global dicts (the compiled pump resolves them from there)."""
    from pyboy.plugins import window_sdl2 as w
    import sdl2
    from pyboy.utils import WindowEvent as E
    w.KEY_DOWN.update({
        sdl2.SDLK_w: E.PRESS_ARROW_UP, sdl2.SDLK_s: E.PRESS_ARROW_DOWN,
        sdl2.SDLK_a: E.PRESS_ARROW_LEFT, sdl2.SDLK_d: E.PRESS_ARROW_RIGHT,
        sdl2.SDLK_j: E.PRESS_BUTTON_A, sdl2.SDLK_k: E.PRESS_BUTTON_B,
    })
    w.KEY_UP.update({
        sdl2.SDLK_w: E.RELEASE_ARROW_UP, sdl2.SDLK_s: E.RELEASE_ARROW_DOWN,
        sdl2.SDLK_a: E.RELEASE_ARROW_LEFT, sdl2.SDLK_d: E.RELEASE_ARROW_RIGHT,
        sdl2.SDLK_j: E.RELEASE_BUTTON_A, sdl2.SDLK_k: E.RELEASE_BUTTON_B,
    })


def auto_action(rng: random.Random) -> list:
    """A game-agnostic randomized button set for one step. Direction-heavy (movement/coverage), with
    move+A combos (platformer jump / attack / interact), bare A/B, and occasional idle (lets a forced-
    scroll world advance on its own). Different seeds diverge."""
    r = rng.random()
    d = rng.choice(["up", "down", "left", "right"])
    if r < 0.50:
        return [d]
    if r < 0.66:
        return [d, "a"]            # move + jump/attack/interact (platformers)
    if r < 0.80:
        return ["a"]
    if r < 0.88:
        return ["b"]
    if r < 0.93:
        return ["start"]           # punch through titles / menus from a cold boot
    return []


def make_explore_action(rng: random.Random, p_continue: float = 0.8, p_interact: float = 0.07):
    """A direction-PERSISTENT gameplay action for camera/odometry data: hold ONE direction across many
    steps so a follow/side camera actually SCROLLS. (auto_action re-rolls a fresh random direction every
    step, so the avatar wiggles in place and the camera never pans -- the locomotion-sparsity the
    camera-model probe diagnosed.) Re-rolls the direction ~(1-p_continue) of steps; occasionally taps A/B
    to interact / advance a bump. Pair with a longer --hold (>= one tile-step, ~16) so each step completes
    a tile move."""
    st = {"d": rng.choice(["up", "down", "left", "right"])}

    def act(r: random.Random) -> list:
        if r.random() < p_interact:
            return [r.choice(["a", "b"])]
        if r.random() > p_continue:
            st["d"] = r.choice(["up", "down", "left", "right"])
        return [st["d"]]
    return act


def _grab_ram(pb):
    try:
        return bytes(pb.memory[0xC000:0xE000])      # 8 KB WRAM (current bank); pixels-agnostic oracle
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", required=True)
    ap.add_argument("--name", required=True,
                    help="dataset dir under runs/ (auto-prefixed with today's date 'YYYY-MM-DD_' "
                         "unless --name already starts with a date)")
    ap.add_argument("--mode", choices=["auto", "human"], default="auto")
    ap.add_argument("--steps", type=int, default=3000, help="recorded steps (auto mode)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--load-state", default="")
    ap.add_argument("--smart-auto", action="store_true",
                    help="auto mode: use the world-agnostic modality detector + escape policy "
                         "(core/) to get through titles/menus into gameplay (default: pure random)")
    ap.add_argument("--explore", action="store_true",
                    help="auto mode: direction-PERSISTENT walk for sustained camera scrolls "
                         "(odometry/camera-model data); implies smart-auto menu escape. Pair with --hold 16.")
    ap.add_argument("--keys", choices=["wasd", "arrows"], default="wasd", help="human movement layout")
    ap.add_argument("--ram", action="store_true", help="also dump raw 8KB WRAM per step (ram.bin)")
    ap.add_argument("--watch", default="",
                    help="comma-list of name=HEXADDR WRAM bytes to log per step as a position oracle into a "
                         "SEPARATE oracle.jsonl (never buttons.jsonl), e.g. kirby 'scroll_x=0xD051' or metroid "
                         "'x_px=0xD027,x_scr=0xD028' (Data Crystal RAM maps). World-agnostic: reads pb.memory[addr].")
    ap.add_argument("--sound", action="store_true", help="human mode audio")
    ap.add_argument("--hold", type=int, default=8)
    ap.add_argument("--settle", type=int, default=16)
    ap.add_argument("--sample-every", type=int, default=12, help="human mode: frames per recorded step")
    args = ap.parse_args()
    watch = []
    for p in (e.strip() for e in args.watch.split(",") if e.strip()):
        if p.count("=") != 1 or not p.split("=", 1)[0].strip():
            raise SystemExit(f"--watch entries must be name=HEXADDR; bad entry: {p!r}")
        nm, ad = p.split("=", 1)
        watch.append((nm.strip(), int(ad, 16)))

    # Prefix the run dir with today's date so data artifacts are sortable + self-identifying (unless the
    # caller already supplied a YYYY-MM-DD prefix). Keeps runs/ chronologically ordered.
    name = args.name
    if not re.match(r"\d{4}-\d{2}-\d{2}[_-]", name):
        name = f"{datetime.date.today().isoformat()}_{name}"
    out = os.path.join("runs", name)
    os.makedirs(out, exist_ok=True)

    if args.mode == "human":
        ensure_sdl_dll_path()
    from pyboy import PyBoy
    pb = PyBoy(args.rom, window=("SDL2" if args.mode == "human" else "null"),
               sound_emulated=(args.sound and args.mode == "human"),
               sound_volume=(100 if (args.sound and args.mode == "human") else 0))
    if args.mode == "human" and args.keys == "wasd":
        remap_wasd()
        pb.set_emulation_speed(1)
    if args.load_state and os.path.exists(args.load_state):
        with open(args.load_state, "rb") as f:
            pb.load_state(f)
    pb.tick(4, render=True)

    jf = open(os.path.join(out, "buttons.jsonl"), "a", encoding="utf-8")
    rf = open(os.path.join(out, "ram.bin"), "ab") if args.ram else None
    # --watch's RAM oracle goes to a SEPARATE channel (oracle.jsonl), never into buttons.jsonl: buttons.jsonl +
    # frames are the pixels+actions substrate the offline pipeline reads, so RAM must stay out of it (ADR-001).
    of = open(os.path.join(out, "oracle.jsonl"), "a", encoding="utf-8") if watch else None
    n = {"i": 0}

    def record(buttons, mode):
        path = os.path.join(out, f"frame_{n['i']:06d}.png")
        pb.screen.image.save(path)
        jf.write(json.dumps({"step": n["i"], "t": time.time(), "frame": pb.frame_count,
                             "screen_path": path.replace("\\", "/"),
                             "buttons": list(buttons), "mode": mode}) + "\n")
        jf.flush()
        if of is not None:                            # position oracle -> separate channel, not the substrate
            of.write(json.dumps({"step": n["i"], "frame": pb.frame_count,
                                 "watch": {nm: int(pb.memory[ad]) for nm, ad in watch}}) + "\n")
        if rf is not None:
            rf.write(_grab_ram(pb) or bytes(8192))
        n["i"] += 1

    with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as mf:
        json.dump({"rom": os.path.basename(args.rom), "mode": args.mode, "keys": args.keys,
                   "ram": bool(args.ram), "hold": args.hold, "settle": args.settle,
                   "sample_every": args.sample_every, "seed": args.seed}, mf, indent=2)

    if args.mode == "auto":
        rng = random.Random(args.seed)
        policy = None
        if args.smart_auto or args.explore:
            from core.autoplay import ModalAutoPolicy   # world-agnostic; only imported when asked
            gameplay = make_explore_action(rng) if args.explore else auto_action
            policy = ModalAutoPolicy(rng, gameplay)
        prev_frame, last_buttons, mode = None, [], "auto"
        for i in range(args.steps):
            if policy is not None:
                curr_frame = pb.screen.ndarray.copy()   # the screen we're about to act on
                mode, act = policy.decide(prev_frame, curr_frame, last_buttons)
            else:
                act = auto_action(rng)
            for b in act:
                pb.button(b, delay=args.hold)
            pb.tick(args.hold + args.settle, render=True)
            record(act, "auto")
            if policy is not None:
                prev_frame, last_buttons = curr_frame, act
            if i % 500 == 0:
                tag = f"  mode={mode} stalls={policy.stalls}" if policy is not None else ""
                print(f"[{args.name}] auto step {i}/{args.steps}{tag}", flush=True)
    else:
        _run_human(pb, args, record, out)

    jf.close()
    if rf is not None:
        rf.close()
    if of is not None:
        of.close()
    print(f"\nsaved {n['i']} steps to {out}/  (mode={args.mode})", flush=True)
    pb.stop(save=False)
    return 0


def _run_human(pb, args, record, out):
    import sdl2
    nkeys = ctypes.c_int(0)
    if args.keys == "wasd":
        keymap = {sdl2.SDL_SCANCODE_W: "up", sdl2.SDL_SCANCODE_S: "down",
                  sdl2.SDL_SCANCODE_A: "left", sdl2.SDL_SCANCODE_D: "right",
                  sdl2.SDL_SCANCODE_J: "a", sdl2.SDL_SCANCODE_K: "b"}
    else:
        keymap = {sdl2.SDL_SCANCODE_UP: "up", sdl2.SDL_SCANCODE_DOWN: "down",
                  sdl2.SDL_SCANCODE_LEFT: "left", sdl2.SDL_SCANCODE_RIGHT: "right",
                  sdl2.SDL_SCANCODE_A: "a", sdl2.SDL_SCANCODE_S: "b"}
    keymap[sdl2.SDL_SCANCODE_RETURN] = "start"
    keymap[sdl2.SDL_SCANCODE_BACKSPACE] = "select"

    S = {"quit": False, "auto": False, "ckpt": 0}
    held = {"tab": False, "c": False, "esc": False}
    rng = random.Random(args.seed)

    def hotkeys(ks):
        def edge(name, sc):
            now = bool(ks[sc]); fired = now and not held[name]; held[name] = now; return fired
        if edge("tab", sdl2.SDL_SCANCODE_TAB):
            S["auto"] = not S["auto"]
            print(f"[auto {'ON' if S['auto'] else 'OFF'}]", flush=True)
        if edge("c", sdl2.SDL_SCANCODE_C):
            S["ckpt"] += 1
            # NOT os.path.join("runs", args.name): the run dir is date-prefixed (see main()), so
            # using the raw name wrote to a directory that does not exist and crashed the session.
            p = os.path.join(out, f"checkpoint_{S['ckpt']:02d}.state")
            with open(p, "wb") as f:
                pb.save_state(f)
            print(f"[checkpoint -> {p}]", flush=True)
        if edge("esc", sdl2.SDL_SCANCODE_ESCAPE):
            S["quit"] = True

    print(f"Controls ({args.keys}): "
          + ("WASD=move J=A K=B" if args.keys == "wasd" else "Arrows=move A=A S=B")
          + "  Enter=Start  Backspace=Select  TAB=auto  C=checkpoint  ESC=quit")
    while not S["quit"]:
        if S["auto"]:
            act = auto_action(rng)
            for b in act:
                pb.button(b, delay=args.hold)
            for _ in range(args.hold + args.settle):
                if not pb.tick(1, True):
                    S["quit"] = True
                hotkeys(sdl2.SDL_GetKeyboardState(ctypes.byref(nkeys)))
                if S["quit"]:
                    break
            record(act, "auto")
        else:
            active = set()
            for _ in range(args.sample_every):
                if not pb.tick(1, True):
                    S["quit"] = True
                ks = sdl2.SDL_GetKeyboardState(ctypes.byref(nkeys))
                for sc, name in keymap.items():
                    if ks[sc]:
                        active.add(name)
                hotkeys(ks)
                if S["quit"]:
                    break
            record(sorted(active), "human")


if __name__ == "__main__":
    raise SystemExit(main())
