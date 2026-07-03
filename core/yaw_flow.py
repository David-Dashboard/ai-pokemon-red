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

Multi-band voting (reports/2026-07-05-p1-clutter-redesign.md S2(a), PR-F): re-scoped by review to
mechanism 2 ONLY (late-episode clutter -- a genuine P1 degradation as movers corrupt a single band's
correlation). Mechanism 1 (turn-onset ramp mis-scoring, run_pos<=1) is NOT an estimator defect -- the
world genuinely rotates ~0px on onset tics and every band would agree on that correct near-zero
reading -- it is fixed entirely by the GATE-3D-A3 pinned SCORING rule (eval/score_a3_precheck.py), not
here. `yaw_band_flow`'s default (`bands=None`) is BYTE-IDENTICAL to the pre-redesign single-band
behavior -- no blast radius for any caller not opting in (S4/anti-drift table: "don't change the
multi-band default for OTHER callers").
"""
from __future__ import annotations

from typing import NamedTuple, Optional, Sequence

import numpy as np

MAX_SHIFT = 64
BAND = (84, 156)  # rows 0.35H-0.65H of a 240-row frame; excludes weapon sprite / ceiling
NCC_FLOOR = 0.2
PROM_FLOOR = 0.02
NONADJ = 8  # shifts within this many px of the peak count as the same peak (not a competitor)

# Multi-band voting (design S2(a)): 3 bands centered at 0.40H/0.50H/0.60H of a 240-row frame, each the
# current 0.30H-tall (72px) window -- the MIDDLE band is exactly today's BAND re-derived from the same
# center/height rule; top/bottom bands re-slice the SAME frames (no new capture): 60px is still below
# the ceiling range PC-2's fixtures were curated against, 180px is still above the weapon sprite.
# Pinned here, not re-derived per-caller; a caller opts in by passing `bands=DEFAULT_BANDS`.
DEFAULT_BANDS: tuple[tuple[int, int], ...] = ((60, 132), (84, 156), (108, 180))
MIN_BANDS_CLEARING = 2  # fewer bands clearing the floor than this -> fall back to single-band (never
                        # regress below today's behavior, design S2(a) verbatim)
MAX_OUTLIER_BANDS = 1   # more than this many clearing bands disagreeing in sign with the majority ->
                        # direction=None (outlier rejection, design S2(a) verbatim)


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


def _direction_of(dx: int) -> str:
    return "none" if dx == 0 else ("left" if dx > 0 else "right")


def _single_band_reading(
    prev_gray: np.ndarray,
    cur_gray: np.ndarray,
    band: tuple[int, int],
    max_shift: int,
    ncc_floor: float,
    prom_floor: float,
) -> YawReading:
    """The pre-redesign R0 estimator on exactly one band -- unchanged logic, factored out so both the
    single-band caller path and multi-band voting's per-band pass share one implementation."""
    p_prev = band_profile(prev_gray, band)
    p_cur = band_profile(cur_gray, band)
    dx, ncc_best, prom = _best_shift_1d(p_prev, p_cur, max_shift=max_shift)
    if ncc_best < ncc_floor or prom < prom_floor:
        return YawReading(dx_px=None, direction=None, confidence=None)
    return YawReading(dx_px=int(dx), direction=_direction_of(dx), confidence=round(float(prom), 4))


def _vote_bands(readings: list[YawReading]) -> YawReading:
    """Trimmed-median vote with outlier rejection over N>=2 per-band readings that already cleared the
    floor (design S2(a)): dx = median dx among clearing bands; direction=None (outlier rejection) if
    more than MAX_OUTLIER_BANDS of the clearing bands disagree in sign with the majority; confidence =
    the MINIMUM confidence among the surviving (non-None) bands used in the vote, so a vote is never
    reported more confident than its weakest supporting band."""
    dxs = sorted(r.dx_px for r in readings)
    n = len(dxs)
    median_dx = dxs[n // 2] if n % 2 == 1 else round((dxs[n // 2 - 1] + dxs[n // 2]) / 2)

    signs = [0 if r.dx_px == 0 else (1 if r.dx_px > 0 else -1) for r in readings]
    n_pos = sum(1 for s in signs if s > 0)
    n_neg = sum(1 for s in signs if s < 0)
    if n_pos > 0 and n_neg > 0:
        # Both turning signs present among clearing bands: real disagreement. Tolerate it only if the
        # SMALLER side is a minority of at most MAX_OUTLIER_BANDS bands AND strictly smaller than the
        # majority side (the median can absorb a lone dissenting band, not a tie or a majority flip);
        # anything else -- including an exact tie -- is "disagree in sign by more than one band" -> None.
        minority_turn = min(n_pos, n_neg)
        if minority_turn > MAX_OUTLIER_BANDS or minority_turn == max(n_pos, n_neg):
            return YawReading(dx_px=None, direction=None, confidence=None)

    confidence = min(r.confidence for r in readings)
    return YawReading(dx_px=int(median_dx), direction=_direction_of(median_dx),
                       confidence=round(float(confidence), 4))


def yaw_band_flow(
    prev_gray: np.ndarray,
    cur_gray: np.ndarray,
    *,
    band: tuple[int, int] = BAND,
    max_shift: int = MAX_SHIFT,
    ncc_floor: float = NCC_FLOOR,
    prom_floor: float = PROM_FLOOR,
    bands: Optional[Sequence[tuple[int, int]]] = None,
) -> YawReading:
    """R0 YawBandFlow. `prev_gray`/`cur_gray` are 2D grayscale arrays (H, W), same shape.

    Grounding (design S1.1 slot 2, empirically verified by PC-2): in ViZDoom, TURN_LEFT rotates the
    view left, so the world image streams RIGHT (+dx), and TURN_RIGHT gives -dx. `direction` reports
    the EGO's turn direction (matching that convention: +dx -> "left", -dx -> "right"), not the raw
    image-flow direction -- this is what a caller commanding turns and reading back agreement expects.

    `bands` (design S2(a), PR-F, opt-in only): a sequence of 3+ `(r0, r1)` band ranges (e.g.
    `DEFAULT_BANDS`). When given, each band is scored independently with the SAME `max_shift`/
    `ncc_floor`/`prom_floor`, and the result is a trimmed-median vote across the bands that clear the
    floor, with outlier rejection (`_vote_bands`). If fewer than `MIN_BANDS_CLEARING` bands clear the
    floor, this falls back to today's single-band result on `band` -- multi-band voting can only ever
    do as well as or better than the single-band estimator, never worse (S2(a): "never regress below
    current behavior"). `bands=None` (the default) is the ORIGINAL single-band code path, byte-for-byte
    -- no behavior change for any existing caller that does not pass `bands`.
    """
    if bands is None:
        return _single_band_reading(prev_gray, cur_gray, band, max_shift, ncc_floor, prom_floor)

    if len(bands) < 3:
        raise ValueError(f"multi-band voting needs >=3 bands, got {len(bands)}")

    per_band = [_single_band_reading(prev_gray, cur_gray, b, max_shift, ncc_floor, prom_floor)
                for b in bands]
    clearing = [r for r in per_band if r.direction is not None]

    if len(clearing) < MIN_BANDS_CLEARING:
        # Fall back to the plain single-band reading on the caller's nominal `band` (never regress).
        return _single_band_reading(prev_gray, cur_gray, band, max_shift, ncc_floor, prom_floor)

    return _vote_bands(clearing)


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
