"""3D GATE smoke test (cheap, ViZDoom): does our core idea — behaviour=truth + a CHEAP pixels-only
self-motion signal — survive 3D ego-motion? If a dumb frame-diff can tell "I walked forward down a
corridor" from "I walked into a wall" (ground-truthed by ViZDoom's position), then the dual-process /
appearance-advisory approach has 3D LEGS and It3 (real 3D) is worth a full iteration. If not, 3D needs
a heavier perceiver and should be its own clean-sheet build.

Records the RAW substrate (frame + action + ground-truth pos/angle) from `my_way_home` under a
forward-biased random policy (so we get many corridor-advances AND wall-bumps), then reports whether
frame-diff separates advanced-vs-blocked on pure-forward steps. Run:
  uv run --with vizdoom python -m eval.vizdoom_smoke
"""
from __future__ import annotations
import json, math, os
import numpy as np
from PIL import Image

OUT = "runs/vizdoom_mywayhome"
STEPS = 700
TICS = 4


def _gray(rgb):
    return rgb[..., :3].mean(axis=2)


def main():
    import random
    import vizdoom as vzd
    os.makedirs(OUT, exist_ok=True)
    g = vzd.DoomGame()
    g.load_config(os.path.join(vzd.scenarios_path, "my_way_home.cfg"))
    g.set_window_visible(False)
    g.set_screen_resolution(vzd.ScreenResolution.RES_160X120)
    g.set_screen_format(vzd.ScreenFormat.RGB24)
    g.set_available_game_variables([vzd.GameVariable.POSITION_X, vzd.GameVariable.POSITION_Y,
                                    vzd.GameVariable.ANGLE])
    g.init()
    BTN = [str(b).split(".")[-1] for b in g.get_available_buttons()]  # TURN_LEFT/RIGHT, MOVE_FORWARD,...
    iF, iL, iR = BTN.index("MOVE_FORWARD"), BTN.index("TURN_LEFT"), BTN.index("TURN_RIGHT")
    rng = random.Random(1)

    def policy():
        a = [0] * len(BTN)
        r = rng.random()
        if r < 0.60:
            a[iF] = 1                       # pure forward (corridor-advance OR wall-bump)
        elif r < 0.75:
            a[iL] = 1
        elif r < 0.90:
            a[iR] = 1
        else:
            a[iF] = 1; a[rng.choice([iL, iR])] = 1   # forward + turn
        return a

    jf = open(os.path.join(OUT, "buttons.jsonl"), "w", encoding="utf-8")
    rows = []                               # (action, gray, pos, angle)
    g.new_episode()
    for i in range(STEPS):
        if g.is_episode_finished():
            g.new_episode()
        st = g.get_state()
        rgb = st.screen_buffer
        gx, gy, ga = (float(v) for v in st.game_variables)
        act = policy()
        path = os.path.join(OUT, f"frame_{i:06d}.png")
        Image.fromarray(rgb).save(path)
        jf.write(json.dumps({"step": i, "screen_path": path.replace("\\", "/"),
                             "buttons": [BTN[k] for k, on in enumerate(act) if on],
                             "pos": [gx, gy], "angle": ga}) + "\n")
        rows.append((act, _gray(rgb), (gx, gy)))
        g.make_action(act, TICS)
    jf.close()
    g.close()

    # ---- gate analysis: among PURE-forward steps, does frame-diff separate advanced vs blocked? ----
    fwd = []   # (delta_pos, frame_diff)
    for i in range(1, len(rows)):
        act, gray, pos = rows[i]
        pact = rows[i - 1][0]
        # ACTION-FRAME ALIGNMENT (was off-by-one): pos/gray are logged BEFORE make_action, so the
        # i-1 -> i transition (both dpos and fdiff) is caused by the action at row i-1 (pact), NOT i.
        # Filtering on `act` mislabels steps and BLURS the signal (verified 2026-06-22: the bug
        # under-reported accuracy 96.9% -> 83.7% and collapsed turn-direction to chance).
        pure_fwd = pact[iF] and not pact[iL] and not pact[iR]
        if not pure_fwd:
            continue
        dpos = math.dist(pos, rows[i - 1][2])
        fdiff = float(np.abs(gray - rows[i - 1][1]).mean())
        fwd.append((dpos, fdiff))
    fwd = np.array(fwd)
    if len(fwd) < 20:
        print(f"too few pure-forward steps ({len(fwd)})"); return
    dpos, fdiff = fwd[:, 0], fwd[:, 1]
    # "blocked" = essentially no position change on a forward press; "advanced" = clearly moved
    thr = max(1.0, np.percentile(dpos, 60) * 0.2)     # small distance => wall-bump
    blocked, advanced = fdiff[dpos <= thr], fdiff[dpos > thr]
    print(f"=== ViZDoom my_way_home 3D gate ===  steps={len(rows)}  pure-forward={len(fwd)}")
    print(f"  pos-change threshold (blocked<= ): {thr:.2f}   blocked n={len(blocked)}  advanced n={len(advanced)}")
    if len(blocked) and len(advanced):
        print(f"  frame-diff | BLOCKED (walked into wall): mean {blocked.mean():.2f}")
        print(f"  frame-diff | ADVANCED (corridor):        mean {advanced.mean():.2f}")
        # cheap separability: best single-threshold accuracy of frame-diff predicting advanced
        alld = np.sort(np.unique(fdiff))
        best = 0.0
        y = (dpos > thr).astype(int)
        for t in alld:
            acc = ((fdiff > t).astype(int) == y).mean()
            best = max(best, acc, 1 - acc)
        corr = float(np.corrcoef(dpos, fdiff)[0, 1])
        print(f"  best frame-diff threshold accuracy (advanced vs blocked): {best:.1%}")
        print(f"  corr(pos-change, frame-diff): {corr:+.2f}")
        # NOTE: this is a BINARY advance-vs-stuck detector, NOT metric odometry (graded distance
        # carries ~no info: corr among only-moving steps ~= +0.02). And whole-frame frame-diff
        # CANNOT tell rotation from translation -- for the real perceiver use OPTICAL FLOW
        # (column-shift sign => turn direction; expansion flow => advance). See
        # eval/vizdoom_flow_ceiling.py + reports/2026-06-22-cross-game-phase-plan.md.
        print("\nVERDICT: high separation/corr => behaviour=truth + a cheap pixels-only advance/stuck"
              "\n         signal HAS 3D legs (greenlight It3, build optical-flow ego-motion);"
              "\n         near-chance => 3D needs a heavier perceiver (defer to a clean-sheet iteration).")


if __name__ == "__main__":
    main()
