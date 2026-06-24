"""Foreground-motion probe (measure-first). best_shift gives CAMERA (background) motion; it goes blind in
the camera-STATIC regime (a follow-camera dead-zone, or a fixed/flip camera) where the player moves but the
screen doesn't scroll -- that blind spot is what sealed phantom walls on Gauntlet (24% of moves) and makes
Cave Noire (99% static, fixed camera) unmappable by the camera recipe.

The complement is FOREGROUND motion: after removing the camera shift, residual on-screen change = the player
sprite. On a camera-static step best_shift's chosen shift is (0,0), so the camera-compensated residual is just
the whole-frame diff (fd). QUESTION: in the camera-static regime, does that residual separate a REAL move (RAM
position changed) from a WALL-BUMP (RAM unchanged)? If yes, "did I move" is recoverable without the camera ->
fixes the dead-zone false-walls AND unlocks the fixed-camera class. Idle animation (torches/enemies) is the
risk -- it raises fd while stuck; the AUC below measures whether real moves still separate.

RAM is the oracle, never an input. Gauntlet: --watch x/y. Cave Noire: x=0xC504,y=0xC503 from ram.bin (finder).
  uv run python -m eval.probe_foreground_motion
"""
from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image

from eval.probe_camera_model import NH, NW, best_shift

_DIRS = ("up", "down", "left", "right")


def _gray(p):
    return np.asarray(Image.open(p).convert("L").resize((NW, NH), Image.BILINEAR), dtype=np.float32)


def _wrapb(d):
    return ((d + 128) % 256) - 128


def _dir(buttons):
    toks = [b for b in (buttons or []) if b in _DIRS]
    return toks[-1] if toks else None


def _auc(moved, stuck):
    """P(a random moved-step's residual > a random stuck-step's) -- 1.0 = perfect separation, 0.5 = none."""
    if not moved or not stuck:
        return None
    m = np.array(moved); s = np.array(stuck)
    wins = (m[:, None] > s[None, :]).sum()
    ties = (m[:, None] == s[None, :]).sum()
    return (wins + 0.5 * ties) / (len(m) * len(s))


def _score(name, pos, buttons, frame_of):
    """pos[i]=(x,y), buttons[i]=list, frame_of(i)=path. Transition i->i+1 caused by buttons[i+1]."""
    moved_fd, stuck_fd = [], []
    cam_static_moves = total_moves = 0
    for i in range(len(pos) - 1):
        d = _dir(buttons[i + 1])
        if d is None:
            continue
        dx = _wrapb(pos[i + 1][0] - pos[i][0]); dy = _wrapb(pos[i + 1][1] - pos[i][1])
        dpos = abs(dx) + abs(dy)
        if dpos > 40:                      # wrap-ghost / scene cut
            continue
        fa, fb = frame_of(i), frame_of(i + 1)
        if not (os.path.exists(fa) and os.path.exists(fb)):
            continue
        fd, best, sdx, sdy = best_shift(_gray(fa), _gray(fb))
        if max(abs(sdx), abs(sdy)) >= 2:   # camera scrolled -> best_shift already handles it; skip
            if 1 <= dpos:
                total_moves += 1
            continue
        # camera-static: best_shift is blind. residual == fd here.
        if 1 <= dpos:
            moved_fd.append(fd); cam_static_moves += 1; total_moves += 1
        elif dpos == 0:
            stuck_fd.append(fd)
    auc = _auc(moved_fd, stuck_fd)
    mm = np.median(moved_fd) if moved_fd else float("nan")
    ms = np.median(stuck_fd) if stuck_fd else float("nan")
    static_frac = cam_static_moves / total_moves if total_moves else 0
    print(f"  {name:10s} cam-static moves={len(moved_fd):4d} ({static_frac:.0%} of moves)  wall-bumps={len(stuck_fd):4d}")
    print(f"             residual median: MOVED={mm:5.1f}  STUCK={ms:5.1f}   separation AUC={auc if auc is None else round(auc,2)}")
    return auc


def gauntlet():
    run = "runs/2026-06-23_gauntlet_ramplay"
    btn = [json.loads(l) for l in open(os.path.join(run, "buttons.jsonl"), encoding="utf-8")]
    ora = {r["step"]: r["watch"] for r in
           (json.loads(l) for l in open(os.path.join(run, "oracle.jsonl"), encoding="utf-8"))}
    steps = [b["step"] for b in btn if b["step"] in ora]
    pos = [(ora[s]["x"], ora[s]["y"]) for s in steps]
    buttons = [btn[s].get("buttons", []) for s in steps]
    return pos, buttons, lambda i: os.path.join(run, f"frame_{steps[i]:06d}.png")


def cavenoire():
    run = "runs/2026-06-23_cavenoire_explore"
    ram = np.fromfile(os.path.join(run, "ram.bin"), dtype=np.uint8)
    n = ram.size // 8192; ram = ram[:n * 8192].reshape(n, 8192)
    btn = [json.loads(l) for l in open(os.path.join(run, "buttons.jsonl"), encoding="utf-8")][:n]
    pos = [(int(ram[i, 0x504]), int(ram[i, 0x503])) for i in range(len(btn))]
    buttons = [b.get("buttons", []) for b in btn]
    return pos, buttons, lambda i: os.path.join(run, f"frame_{i:06d}.png")


def main():
    print("=== FOREGROUND-MOTION PROBE - residual separates MOVE from WALL-BUMP in the camera-static regime? ===")
    print("(AUC 1.0 = residual perfectly tells a real move from a wall-bump with the camera blind; 0.5 = useless)")
    for name, loader in (("gauntlet", gauntlet), ("cavenoire", cavenoire)):
        try:
            pos, buttons, frame_of = loader()
        except FileNotFoundError as e:
            print(f"  {name}: missing ({e})"); continue
        _score(name, pos, buttons, frame_of)
    print("\nHigh AUC => a cheap camera-compensated 'did I move' signal recovers the camera-static moves")
    print("(fixes Gauntlet's dead-zone false-walls + unlocks the fixed-camera class). Low => idle animation")
    print("pollutes fd and we need a button-direction-consistent foreground signal, not raw residual.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
