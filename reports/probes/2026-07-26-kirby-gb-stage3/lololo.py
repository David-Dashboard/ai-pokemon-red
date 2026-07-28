"""Reactive controller for the Lololo fight (Castle Lololo boss). $0, offline PyBoy, no LLM.

Blind search does not win this: 560 randomised/structured trials landed zero boss damage (the boss
meter -- a skull icon plus 3 boxes that replaces the score row -- never moved). The fight needs
Kirby to inhale one of the BLOCKS Lololo pushes along a ledge and spit it back at him, which needs
knowing where the block and Lololo actually are.

Sprite identification, calibrated by watching which sprites respond to input:
  Kirby        tiles <= 60   (walk pairs 0/16, 2/18, 4/20, 6/22, 8/24; inhale 36/38/52/54)
  effects      90, 100, 116, 130   (suction puff, stars) -- ignored
  block        a pair of tile-230 sprites
  Lololo       the animated pairs 248/250, 236/240, 234/242

Reward: dark-pixel count of the boss meter strip (x 44-80, y 128-136). 72 px = 3 boxes = full.
"""
from __future__ import annotations

import argparse
import os
import random

PRIMARY = "E:/AI_Personas/10_pokemon_and_chess_and_office/ai-pokemon-red"
ROM = PRIMARY + "/roms/Kirby's Dream Land (USA, Europe).gb"
OUT = ("C:/Users/Succe/AppData/Local/Temp/claude/"
       "E--AI-Personas-10-pokemon-and-chess-and-office/"
       "671b9313-5a35-40f5-a26e-315d9f7e8f28/scratchpad/kirby3")
START = os.environ.get("BOSS_START", "boss_ready.state")
CAND = (0xD03B, 0xD19F, 0xD3A9, 0xD3BA, 0xD3CD)
EFFECTS = {90, 100, 116, 130}


def read(pb):
    kirby, block, lololo = [], [], []
    for i in range(40):
        s = pb.get_sprite(i)
        if not s.on_screen or not (8 <= s.y <= 126):
            continue
        t = s.tile_identifier
        if t in EFFECTS:
            continue
        if t <= 60:
            kirby.append((s.x, s.y))
        elif t == 230:
            block.append((s.x, s.y))
        elif t >= 200:
            lololo.append((s.x, s.y))
    mean = lambda p: (sum(x for x, _ in p) / len(p), sum(y for _, y in p) / len(p)) if p else None
    return mean(kirby), mean(block), mean(lololo)


def boss_meter(pb):
    return int((pb.screen.ndarray[128:136, 44:80, 0] < 128).sum())


def fight(seed, max_frames=6000, save_as=None, verbose=False):
    from pyboy import PyBoy
    rng = random.Random(seed)
    pb = PyBoy(ROM, window="null", sound_emulated=False)
    pb.set_emulation_speed(0)
    with open(os.path.join(OUT, START), "rb") as f:
        pb.load_state(f)
    pb.tick(1, render=True)

    held, rooms, was_blank, elapsed = set(), 0, False, 0
    full = boss_meter(pb)
    best = full
    phase, timer = "camp", 0
    # Strategy (from tracing the fight): Lololo enters from the RIGHT pushing a block LEFTWARD,
    # so he is between Kirby and the block if Kirby waits on the right. Camp at the LEFT end of the
    # ledge facing right instead: the block arrives first, gets inhaled, and the spit travels right
    # into Lololo behind it.
    camp_x = rng.choice((16, 24, 32, 40))
    inhale_range = rng.choice((32, 44, 56))
    spit_delay = rng.choice((6, 10, 16))

    def press(btns):
        nonlocal held
        for b in held - set(btns):
            pb.button_release(b)
        for b in set(btns) - held:
            pb.button_press(b)
        held = set(btns)

    while elapsed < max_frames and pb.memory[0xD086] > 0 and not rooms:
        pb.tick(4, render=True)
        elapsed += 4
        px = pb.screen.ndarray[:, :, 0]
        blank = bool((px == px[0, 0]).mean() > 0.98)
        if blank and not was_blank:
            rooms += 1
        was_blank = blank
        m = boss_meter(pb)
        best = min(best, m)

        k, blk, lol = read(pb)
        if k is None:
            press([])
            continue
        timer += 4

        if phase == "camp":
            # walk to the left end of the ledge and hold there facing right
            if k[0] > camp_x + 6:
                press(["left"])
            else:
                press(["right"])          # face right, ready for the incoming block
                if timer >= 10:
                    phase, timer = "wait", 0
        elif phase == "wait":
            press([])
            if blk and abs(blk[1] - k[1]) <= 10 and 0 < blk[0] - k[0] <= inhale_range:
                phase, timer = "inhale", 0
            elif k[0] > camp_x + 20:      # drifted; re-camp
                phase, timer = "camp", 0
        elif phase == "inhale":
            press(["b"])
            # the block is gone once it stops being reported -> it is in Kirby's mouth
            if blk is None or timer >= 120:
                phase, timer = "aim", 0
        elif phase == "aim":
            press(["right"])              # Lololo follows the block, so he is to the right
            if timer >= spit_delay:
                phase, timer = "spit", 0
        elif phase == "spit":
            press(["b"])
            if timer >= 12:
                press([])
                phase, timer = "camp", 0

    if rooms:
        for _ in range(70):
            pb.tick(4, render=True)
    res = {"rooms": rooms, "meter_full": full, "meter_best": best,
           "hp": pb.memory[0xD086], "lives": pb.memory[0xD089],
           "score": sum(pb.memory[0xD070 + i] * 10 ** (4 - i) for i in range(4)),
           "cand": [pb.memory[a] for a in CAND], "frames": elapsed}
    if save_as:
        pb.screen.image.save(os.path.join(OUT, f"{save_as}.png"))
        with open(os.path.join(OUT, f"{save_as}.state"), "wb") as f:
            pb.save_state(f)
    pb.stop(save=False)
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    best_meter = None
    for i in range(args.trials):
        s = args.seed + i
        r = fight(s)
        if best_meter is None:
            best_meter = r["meter_full"]
            print(f"boss meter at full health = {best_meter} dark px")
        if r["rooms"]:
            r = fight(s, save_as=f"BOSSWIN_{s}")
            print(f"*** seed {s}: ROOM CHANGE after {r['frames']}f  score={r['score']} "
                  f"hp={r['hp']} lives={r['lives']} candidates5={r['cand']} -> BOSSWIN_{s}")
            return 0
        if r["meter_best"] < best_meter:
            best_meter = r["meter_best"]
            print(f"seed {s}: BOSS DAMAGED -- meter {r['meter_full']} -> {r['meter_best']} "
                  f"(hp={r['hp']}, {r['frames']}f)")
    print(f"no win in {args.trials} trials; best boss meter reached {best_meter}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
