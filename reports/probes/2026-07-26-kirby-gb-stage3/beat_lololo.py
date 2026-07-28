"""Beat Lololo by hill-climbing on the boss health meter. $0, offline PyBoy, no LLM.

One-shot trials do not win (948 of them landed zero damage). What works is (a) matching Kirby's
HEIGHT to the ledge the block is travelling on before inhaling -- he was previously inhaling into
empty air one ledge below -- and (b) treating each landed hit as progress: when the meter drops,
that savestate becomes the new base and the search continues from there.

Boss meter: dark pixels in x 44-80, y 128-136. 72 px = 3 boxes = full; each hit removes ~24.

  python beat_lololo.py --start warp_left.state --rounds 6 --trials 60
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
        (kirby if t <= 60 else block if t == 230 else lololo if t >= 200 else []).append((s.x, s.y))
    mean = lambda p: (sum(x for x, _ in p) / len(p), sum(y for _, y in p) / len(p)) if p else None
    return mean(kirby), mean(block), mean(lololo)


def meter(pb):
    return int((pb.screen.ndarray[128:136, 44:80, 0] < 128).sum())


def attempt(start, seed, max_frames=6000, save_as=None):
    from pyboy import PyBoy
    rng = random.Random(seed)
    pb = PyBoy(ROM, window="null", sound_emulated=False)
    pb.set_emulation_speed(0)
    with open(os.path.join(OUT, start), "rb") as f:
        pb.load_state(f)
    pb.tick(1, render=True)

    held = set()

    def press(bs):
        nonlocal held
        for b in held - set(bs):
            pb.button_release(b)
        for b in set(bs) - held:
            pb.button_press(b)
        held = set(bs)

    full = meter(pb)
    best, best_state = full, None
    rooms, was_blank, elapsed = 0, False, 0
    ytol = rng.choice((10, 14, 18))
    reach = rng.choice((40, 56, 72))
    pulse = rng.choice((2, 3, 4))
    spit_gap = rng.choice((8, 12, 20))
    inhaling, spit_timer = False, 0

    while elapsed < max_frames and pb.memory[0xD086] > 0 and not rooms:
        pb.tick(4, render=True)
        elapsed += 4
        px = pb.screen.ndarray[:, :, 0]
        blank = bool((px == px[0, 0]).mean() > 0.98)
        if blank and not was_blank:
            rooms += 1
        was_blank = blank

        m = meter(pb)
        if m < best:                       # a hit landed -- keep this exact state
            best = m
            import io
            buf = io.BytesIO()
            pb.save_state(buf)
            best_state = buf.getvalue()

        k, blk, lol = read(pb)
        if k is None:
            press([])
            continue

        # Holding `b` only INHALES. Once the block is in Kirby's mouth it must be released and
        # pressed again to SPIT -- without this the fight lands at most an accidental hit.
        if spit_timer > 0:
            spit_timer -= 4
            press([] if spit_timer > spit_gap else ["b"])
            continue
        if inhaling and blk is None:
            inhaling = False
            spit_timer = spit_gap + 12     # let go, then tap b
            continue

        target = blk or lol
        if target is None:
            press([])
            inhaling = False
            continue
        dy, dx = target[1] - k[1], target[0] - k[0]
        if dy < -ytol:                     # block is on a higher ledge: float up to it
            press(["a"] if (elapsed // 4) % pulse == 0 else [])
            inhaling = False
        elif dy > ytol:
            press(["down"])
            inhaling = False
        elif dx > reach:
            press(["right"])               # close the gap along the ledge
            inhaling = False
        elif dx > 0:
            press(["right", "b"])          # same ledge, block approaching -> face it and inhale
            inhaling = True
        else:
            press(["left"])                # it went past; get back ahead of it
            inhaling = False

    if rooms:
        for _ in range(70):
            pb.tick(4, render=True)
    res = {"rooms": rooms, "full": full, "best": best, "hp": pb.memory[0xD086],
           "lives": pb.memory[0xD089], "frames": elapsed, "state": best_state,
           "cand": [pb.memory[a] for a in CAND],
           "score": sum(pb.memory[0xD070 + i] * 10 ** (4 - i) for i in range(4))}
    if save_as:
        pb.screen.image.save(os.path.join(OUT, f"{save_as}.png"))
        with open(os.path.join(OUT, f"{save_as}.state"), "wb") as f:
            pb.save_state(f)
    pb.stop(save=False)
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="warp_left.state")
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--seed", type=int, default=200000)
    args = ap.parse_args()

    base, seed = args.start, args.seed
    for rnd in range(args.rounds):
        base_meter, improved = None, False
        for i in range(args.trials):
            r = attempt(base, seed)
            seed += 1
            if base_meter is None:
                base_meter = r["full"]
                print(f"round {rnd}: base meter {base_meter} (start {base})")
            if r["rooms"]:
                w = attempt(base, seed - 1, save_as=f"LOLOLO_WIN")
                print(f"*** WIN: boss cleared. score={w['score']} hp={w['hp']} "
                      f"lives={w['lives']} candidates5={w['cand']} -> LOLOLO_WIN.state")
                return 0
            if r["best"] < base_meter and r["state"]:
                nxt = f"boss_prog_{rnd}.state"
                with open(os.path.join(OUT, nxt), "wb") as f:
                    f.write(r["state"])
                print(f"round {rnd}: meter {base_meter} -> {r['best']} after {r['frames']}f "
                      f"(hp={r['hp']}) -> {nxt}")
                base, improved = nxt, True
                break
        if not improved:
            print(f"round {rnd}: no further damage in {args.trials} trials (meter {base_meter})")
            return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
