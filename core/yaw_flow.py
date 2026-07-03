"""YawBandFlow (P1): ego-rotation primitive for 3D worlds -- "am I turning, which way, how fast".

Design: reports/2026-07-04-vizdoom-3d-floor-design.md S1.1 (7-slot North-Eye contract). Validated at
R0 by the free offline pre-check: runs/vizdoom_precheck/PRECHECK_REPORT.md PC-2 -- sign-agreement
0.964, None-rate 0.201 at floors ncc>=0.2 / prom>=0.02 (pooled over basic_mixed + a freshly-recaptured
dtc_mixed with a per-step action log; the 2026-07-02 dtc capture had a one-frame action<->frame
misalignment and is NOT used anywhere). Those floors are the pinned R0 defaults here -- ported, not
reinvented (runs/vizdoom_precheck/pc2_yawband.py, pc2_dtc_fresh.py are the reference implementation).

Replaces core.egomotion.best_shift for 3D worlds: best_shift searched a 2D +/-18px window and was
"silently wrong" on 190/200 tics of real rotation in defend_the_center (probe finding, design doc S0).
YawBandFlow fixes both failure modes: 1D search is cheap enough to go to +/-64px, and ambiguous input
returns None explicitly rather than a fabricated (0,0).

Three-valued honesty (design S1.1 slot 5): direction "none" = confidently stationary (dx==0 at a
clear peak); None = cannot tell (peak too flat / not prominent enough, e.g. a blank wall filling the
band). Conflating these two is exactly the best_shift failure this primitive exists to avoid -- never
collapse None into 0.0-meaning-idle.

R0: numpy + PIL only. Swappable to R1 (Farneback / Lucas-Kanade horizontal component) if a future
fixture bar fails this rung -- no such failure yet (PC-2 passed; see PRECHECK_REPORT.md).
"""
from __future__ import annotations

from typing import NamedTuple, Optional

import numpy as np

MAX_SHIFT = 64
BAND = (84, 156)  # rows 0.35H-0.65H of a 240-row frame; excludes weapon sprite / ceiling
NCC_FLOOR = 0.2
PROM_FLOOR = 0.02
NONADJ = 8  # shifts within this many px of the peak count as the same peak (not a competitor)


class YawReading(NamedTuple):
    """Output contract (design S1.1 slot 5). dx_px/direction/confidence are None together when the
    estimate is unusable; direction=="none" with dx_px==0 is a confident "not turning" reading."""
    dx_px: Optional[int]
    direction: Optional[str]        # "left" | "right" | "none" | None
    confidence: Optional[float]     # peak prominence, None when unusable


def band_profile(gray: np.ndarray, band: tuple[int, int] = BAND) -> np.ndarray:
    """Collapse a mid-screen horizontal band of a grayscale frame to a 1D column-mean profile.
    `gray` is a 2D array (H, W); band rows are absolute pixel indices (defaults assume H=240)."""
    r0, r1 = band
    return gray[r0:r1, :].mean(axis=0)


def _ncc(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    denom = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / denom) if denom > 1e-9 else 0.0


def _best_shift_1d(p_prev: np.ndarray, p_cur: np.ndarray, max_shift: int = MAX_SHIFT):
    """1D cross-correlation of two column-mean profiles over shifts in [-max_shift, max_shift].
    dx is the shift such that cur[x] ~ prev[x - dx] (matches runs/vizdoom_precheck/pc2_yawband.py).
    Returns (dx, ncc_best, prominence)."""
    W = len(p_cur)
    scores: dict[int, float] = {}
    for dx in range(-max_shift, max_shift + 1):
        if dx >= 0:
            c, p = p_cur[dx:], p_prev[: W - dx]
        else:
            c, p = p_cur[:dx], p_prev[-dx:]
        scores[dx] = _ncc(c, p)
    best = max(scores, key=scores.get)
    best_s = scores[best]
    nonadj = [v for k, v in scores.items() if abs(k - best) > NONADJ]
    prom = best_s - max(nonadj) if nonadj else best_s
    return best, best_s, prom


def yaw_band_flow(
    prev_gray: np.ndarray,
    cur_gray: np.ndarray,
    *,
    band: tuple[int, int] = BAND,
    max_shift: int = MAX_SHIFT,
    ncc_floor: float = NCC_FLOOR,
    prom_floor: float = PROM_FLOOR,
) -> YawReading:
    """R0 YawBandFlow. `prev_gray`/`cur_gray` are 2D grayscale arrays (H, W), same shape.

    Grounding (design S1.1 slot 2, empirically verified by PC-2): in ViZDoom, TURN_LEFT rotates the
    view left, so the world image streams RIGHT (+dx), and TURN_RIGHT gives -dx. `direction` reports
    the EGO's turn direction (matching that convention: +dx -> "left", -dx -> "right"), not the raw
    image-flow direction -- this is what a caller commanding turns and reading back agreement expects.
    """
    p_prev = band_profile(prev_gray, band)
    p_cur = band_profile(cur_gray, band)
    dx, ncc_best, prom = _best_shift_1d(p_prev, p_cur, max_shift=max_shift)

    if ncc_best < ncc_floor or prom < prom_floor:
        return YawReading(dx_px=None, direction=None, confidence=None)

    direction = "none" if dx == 0 else ("left" if dx > 0 else "right")
    return YawReading(dx_px=int(dx), direction=direction, confidence=round(float(prom), 4))


def calibrate(commanded_turns: list[tuple[float, int]]) -> Optional[float]:
    """Self-calibration hook (design S1.1 slot 2): regress px-per-degree from (deg, dx_px) pairs
    observed within THIS run, never hand-set (the fg_grid=58 sin) and never persisted across runs
    (learning-boundary law -- callers must not cache this between sessions).

    `commanded_turns`: list of (deg, dx_px) for turn steps where dx_px is a non-None reading and deg
    is the known commanded turn magnitude in degrees (sign-agreeing with dx_px is the caller's job --
    pass only steps that already agree, or this will report a poor/negative fit as a signal to widen
    the disagreement-drops-confidence path per the design). Returns deg_per_px, or None if there are
    fewer than 2 usable points or the turn magnitudes don't vary (can't fit a scale).

    PC-2 found deg-per-px is regime-dependent (slow-turn ramp ~2.8 px/deg vs fast-turn burst ~2.8-3.4
    px/deg) -- a single run-local regression over whatever commanded turns actually occurred, not a
    constant pinned here.
    """
    pts = [(deg, dx) for deg, dx in commanded_turns if deg != 0]
    if len(pts) < 2:
        return None
    degs = np.array([p[0] for p in pts], dtype=np.float64)
    dxs = np.array([abs(p[1]) for p in pts], dtype=np.float64)
    if np.ptp(degs) == 0:
        return None
    # least-squares fit of |dx| = k * deg, through the origin (turning 0 deg moves 0 px)
    k = float((degs * dxs).sum() / (degs * degs).sum())
    if k <= 0:
        return None
    return 1.0 / k
