"""Eyes-on Kirby's Dream Land (GB) driver for the Stage-3 oracle hunt. $0, offline PyBoy, no LLM.

Why this exists instead of reusing nav_step.py: core.gb_emulator.PyBoyEmulator.press() drives ONE
button at a time (press+release over N frames), so it cannot hold `right` while tapping `a` --
exactly the input Kirby's float needs. The 2026-07-25 hunt stalled inside Castle Lololo with that
handicap. This talks to PyBoy directly so a step can hold any BUTTON COMBINATION, and returns a
labelled montage of the burst so one Read shows the whole thing.

Probe-only: nothing here is agent-visible, no core/ or world_mcp.py involvement.

  python kdrive.py --load at_s2.state --save r01 --script "90:right,25:right+a,40:right" --shots 12
"""
from __future__ import annotations

import argparse
import os

from PIL import Image, ImageDraw

PRIMARY = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red"
ROM = PRIMARY + "/roms/Kirby's Dream Land (USA, Europe).gb"
OUT = os.environ.get("KDRIVE_OUT", "C:/Users/Succe/AppData/Local/Temp/claude/"
                     "E--AI-Personas-10-pokemon-and-chess-and-office/"
                     "671b9313-5a35-40f5-a26e-315d9f7e8f28/scratchpad/kirby3")

BUTTONS = ("a", "b", "start", "select", "up", "down", "left", "right")
# The 8 lockstep survivors from reports/2026-07-25-oracle-kirby-gb-stage.md (0 in Stage 1, 1 in
# Stage 2). The whole point of this hunt is what they read in Stage 3.
CAND = (0xC057, 0xC073, 0xC07B, 0xD03B, 0xD19F, 0xD3A9, 0xD3BA, 0xD3CD)
HEALTH, LIVES = 0xD086, 0xD089
# Kirby's X within the current room, found by findpos.py (rises holding right, falls holding left,
# still when idle). Mirrored at 0xD3ED. NOTE: 0xD052 is NOT its high byte -- it oscillates 1..5 on
# its own, which is what made the 2026-07-25 hunt call it "volatile". Room changes are detected
# from the SCREEN (KDL blanks it between rooms), not from RAM.
X_ADDR = 0xD051


def read_score(mem) -> int:
    # Per PyBoy's own Kirby game wrapper: 4 digits at 0xD070..0xD073.
    return sum(mem[0xD070 + n] * 10 ** (4 - n) for n in range(4))


def snapshot(pb) -> dict:
    mem = pb.memory
    return {
        "score": read_score(mem),
        "hp": mem[HEALTH],
        "lives": mem[LIVES],
        "x": mem[X_ADDR],
        "cand": [mem[a] for a in CAND],
    }


def parse_script(text: str):
    """"90:right,25:right+a,30:" -> [(90, ['right']), (25, ['right','a']), (30, [])]"""
    steps = []
    for raw in text.split(","):
        raw = raw.strip()
        if not raw:
            continue
        frames, _, btns = raw.partition(":")
        held = [b.strip().lower() for b in btns.split("+") if b.strip()]
        for b in held:
            if b not in BUTTONS:
                raise SystemExit(f"unknown button {b!r} in step {raw!r}")
        steps.append((int(frames), held))
    return steps


def montage(shots, path, cols=2, scale=3):
    """shots: list of (label, PIL.Image). Grid with a label bar under each cell.

    Cells are deliberately large: a 160x144 GB frame is unreadable when a whole sheet gets
    downscaled for viewing, and misreading the room geometry costs more than an extra call.
    """
    if not shots:
        return
    w, h, bar = 160 * scale, 144 * scale, 16
    rows = (len(shots) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * (h + bar)), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for i, (label, img) in enumerate(shots):
        x, y = (i % cols) * w, (i // cols) * (h + bar)
        sheet.paste(img.convert("RGB").resize((w, h), Image.NEAREST), (x, y))
        draw.text((x + 4, y + h + 3), label, fill=(255, 255, 0))
    sheet.save(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--load", required=True, help="state file (path, or name under OUT)")
    ap.add_argument("--save", required=True, help="name under OUT for the resulting state/png")
    ap.add_argument("--script", required=True, help="comma-separated frames:buttons steps")
    ap.add_argument("--shots", type=int, default=4, help="frames sampled into the montage")
    ap.add_argument("--tiles", action="store_true", help="print the 20x16 game_area tile grid")
    ap.add_argument("--cols", type=int, default=2, help="montage columns")
    ap.add_argument("--scale", type=int, default=3, help="montage pixel scale")
    ap.add_argument("--stop-on-death", action="store_true",
                    help="halt as soon as hp hits 0 (keeps the pre-death state usable)")
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    load_path = args.load if os.path.exists(args.load) else os.path.join(OUT, args.load)
    if not os.path.exists(load_path):
        raise SystemExit(f"no such state: {load_path}")

    from pyboy import PyBoy
    pb = PyBoy(ROM, window="null", sound_emulated=False)
    pb.set_emulation_speed(0)
    with open(load_path, "rb") as f:
        pb.load_state(f)
    pb.tick(1, render=True)

    steps = parse_script(args.script)
    total = sum(f for f, _ in steps)
    every = max(1, total // max(1, args.shots))

    start = snapshot(pb)
    prev_cand, prev_lives, prev_hp = start["cand"], start["lives"], start["hp"]
    events, shots = [], []
    elapsed, next_shot, died = 0, 0, False
    rooms, was_blank = 0, False

    for frames, held in steps:
        for b in held:
            pb.button_press(b)
        left = frames
        while left > 0:
            chunk = min(4, left)
            render = True          # always render: the blank-screen room detector needs pixels
            pb.tick(chunk, render=render)
            elapsed += chunk
            left -= chunk

            # KDL blanks the whole screen while swapping rooms -- the one unambiguous transition
            # signal (every RAM byte tried for this turned out to oscillate on its own).
            px = pb.screen.ndarray[:, :, 0]
            blank = bool((px == px[0, 0]).mean() > 0.98)
            if blank and not was_blank:
                rooms += 1
                events.append(f"f{elapsed}: SCREEN BLANK -> room change #{rooms}")
            was_blank = blank

            cur = snapshot(pb)
            if cur["cand"] != prev_cand:
                events.append(f"f{elapsed}: CANDIDATES {prev_cand} -> {cur['cand']}")
                prev_cand = cur["cand"]
            if cur["lives"] != prev_lives:
                events.append(f"f{elapsed}: lives {prev_lives} -> {cur['lives']}")
                prev_lives = cur["lives"]
            if cur["hp"] == 0 and prev_hp != 0:
                events.append(f"f{elapsed}: hp hit 0")
                died = True
            prev_hp = cur["hp"]

            if elapsed >= next_shot:
                shots.append((f"f{elapsed} +{'+'.join(held) or 'idle'} x{cur['x']} "
                              f"sc{cur['score']} hp{cur['hp']} lv{cur['lives']}",
                              pb.screen.image.copy()))
                next_shot += every
            if died and args.stop_on_death:
                break
        for b in held:
            pb.button_release(b)
        if died and args.stop_on_death:
            break

    pb.tick(1, render=True)
    end = snapshot(pb)
    shots.append((f"FINAL f{elapsed} x{end['x']} sc{end['score']} hp{end['hp']} lv{end['lives']}",
                  pb.screen.image.copy()))

    png = os.path.join(OUT, f"{args.save}.png")
    state = os.path.join(OUT, f"{args.save}.state")
    pb.screen.image.save(png)
    with open(state, "wb") as f:
        pb.save_state(f)
    montage(shots, os.path.join(OUT, f"{args.save}_montage.png"),
            cols=args.cols, scale=args.scale)

    if args.tiles:
        try:
            grid = pb.game_wrapper.game_area()
            print("tiles (20 wide x 16 tall, scroll-following):")
            for row in grid:
                print("  " + " ".join(f"{int(v):3d}" for v in row))
        except Exception as e:
            print(f"tiles unavailable: {e}")
    pb.stop(save=False)

    names = " ".join(f"{a:04X}" for a in CAND)
    print(f"loaded  {load_path}")
    print(f"saved   {state}")
    print(f"montage {os.path.join(OUT, args.save + '_montage.png')}")
    print(f"frames  {elapsed}")
    print(f"start   x={start['x']} score={start['score']} hp={start['hp']} "
          f"lives={start['lives']} cand={start['cand']}")
    print(f"end     x={end['x']} score={end['score']} hp={end['hp']} "
          f"lives={end['lives']} cand={end['cand']}")
    print(f"rooms   {rooms} screen-blank room change(s) this burst")
    print(f"addrs   {names}")
    for e in events:
        print(f"EVENT   {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
