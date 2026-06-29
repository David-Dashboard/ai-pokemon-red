"""Drive any Emulator-Protocol emulator from a cold boot into GAMEPLAY (System-1, no game facts).

Wraps the pure `core/autoplay.py:ModalAutoPolicy` (modality-driven escape ladder) with the actual
press/observe loop, so the SAME boot-to-gameplay capability the recorder uses is reusable by the bench,
the play harnesses, and the reasoning brain's warmup. World-agnostic: it only presses buttons and reads
`screen_ndarray()`, exactly like the perceiver.

`reached` is declared when the modality detector reads "gameplay" for `stable_k` consecutive steps (a
single-frame flicker isn't enough). Returns telemetry (steps-to-first-gameplay, steps-to-stable, the mode
trace) so a measurement harness can report WHERE the policy reaches vs gets stuck across the corpus.

NDS (dual-screen) and other multi-region consoles: pass `frame_fn` to extract the screen modality should
judge (e.g. the top screen), keeping this loop substrate-agnostic.
"""
from __future__ import annotations

import random
from typing import Callable, Optional

import numpy as np

from core.autoplay import ModalAutoPolicy


def _default_frame(emu) -> np.ndarray:
    return np.asarray(emu.screen_ndarray())


def reach_gameplay(
    emu,
    *,
    max_steps: int = 150,
    stable_k: int = 3,
    hold: int = 8,
    settle: int = 8,
    seed: int = 0,
    frame_fn: Optional[Callable[[object], np.ndarray]] = None,
    gameplay_action: Optional[Callable[[random.Random], list]] = None,
    keep_every: int = 0,
) -> dict:
    """Press through titles/menus until modality reads gameplay `stable_k` steps running, or give up.

    Returns: {reached, steps (to stable gameplay, or max_steps), first_gameplay (step of the first
    gameplay read, or None), stalls (non-gameplay steps), mode_trace, frames}. `frames` is a list of
    (step, frame) sampled every `keep_every` steps (empty when keep_every == 0) — for hand-label strips.
    """
    rng = random.Random(seed)
    frame_fn = frame_fn or _default_frame
    # During the gameplay streak we keep nudging movement so modality stays grounded in locomotion;
    # reach_gameplay stops once the streak is long enough, so this rarely runs more than stable_k times.
    gameplay_action = gameplay_action or (lambda r: ["right"])
    policy = ModalAutoPolicy(rng, gameplay_action)

    prev: Optional[np.ndarray] = None
    last_buttons: list = []
    streak = 0
    first_gameplay: Optional[int] = None
    trace: list = []
    frames: list = []

    def _result(reached, step):
        if keep_every and (not frames or frames[-1][0] != step):
            frames.append((step, np.asarray(curr).copy()))   # always include the stop frame
        return {"reached": reached, "steps": step, "first_gameplay": first_gameplay,
                "stalls": policy.stalls, "mode_trace": trace, "frames": frames}

    for step in range(max_steps):
        curr = frame_fn(emu)
        if keep_every and step % keep_every == 0:
            frames.append((step, np.asarray(curr).copy()))
        mode, buttons = policy.decide(prev, curr, last_buttons)
        trace.append(mode)
        if mode == "gameplay":
            if first_gameplay is None:
                first_gameplay = step
            streak += 1
            if streak >= stable_k:
                return _result(True, step)
        else:
            streak = 0
        for b in buttons:
            emu.press(b, hold_frames=hold, settle_frames=settle)
        prev, last_buttons = curr, buttons

    return _result(False, max_steps - 1)
