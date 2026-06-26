"""BayesAvatarLocalizer -- Bayes-filter replacement for the argmax in core.localize.

Reuses AvatarLocalizer's heatmap-accumulation machinery verbatim; replaces the argmax+outlier-gate
with a proper Bayes filter:
  - Motion model: truncated-Gaussian spread (avatar moves smoothly, ~1 cell/step max).
  - Observation model: treat the normalized heatmap as a likelihood over grid cells.
  - State: log-posterior over grid cells; MAP cell = estimate.

This gives principled outlier rejection (the posterior can't teleport even if the observation peaks
somewhere far) and less jitter (the motion-model prior pulls the estimate toward the previous location
when the observation is weak).

Output contract identical to AvatarLocalizer: (col, row, confidence) or None.
numpy only. R0 realizer.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from PIL import Image

from core.grid import DELTA
from core.localize import _gray, _shift, AvatarLocalizer, _CELL, _KSHIFTS, _DECAY, _PEAK, _CONF_SAT

# Bayes filter hyperparameters
_MOTION_SIGMA_CELLS = 1.2    # avatar moves ~1 cell/step; Gaussian spread in cell units
_OBS_SIGMA_CELLS    = 1.5    # observation noise (heatmap peak isn't pixel-perfect)
_MIN_LOG_PRIOR      = -50.0  # floor for log-posterior (prevent underflow)
_CONF_FLOOR         = 0.05   # confidence returned when posterior is uninformative


def _make_motion_kernel(sigma: float, shape: tuple[int, int]) -> np.ndarray:
    """Gaussian blur kernel truncated to shape (odd, odd)."""
    H, W = shape
    ky = int(3 * sigma) * 2 + 1
    kx = ky
    cy, cx = ky // 2, kx // 2
    ys, xs = np.mgrid[-cy:cy + 1, -cx:cx + 1]
    k = np.exp(-(xs ** 2 + ys ** 2) / (2 * sigma ** 2))
    k /= k.sum()
    return k


def _convolve2d_valid(arr: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """2D convolution via sliding window (pure numpy, small kernel)."""
    kh, kw = kernel.shape
    ph, pw = kh // 2, kw // 2
    H, W = arr.shape
    # pad with edge values
    padded = np.pad(arr, ((ph, ph), (pw, pw)), mode="edge")
    out = np.zeros_like(arr)
    for dy in range(kh):
        for dx in range(kw):
            out += padded[dy:dy + H, dx:dx + W] * kernel[dy, dx]
    return out


class BayesAvatarLocalizer:
    """Bayes-filter avatar localizer.

    Identical accumulation logic to AvatarLocalizer; replaces argmax+gate with MAP on a Bayesian
    posterior maintained over the heatmap grid.
    """
    def __init__(self):
        self._base = AvatarLocalizer()          # reuse heatmap accumulation
        self._log_post: Optional[np.ndarray] = None   # log-posterior over cells
        self._kernel: Optional[np.ndarray] = None     # cached motion kernel
        self.pos: Optional[tuple] = None

    def reset(self):
        self._base.reset()
        self._log_post = None
        self.pos = None

    def _ensure_kernel(self, shape):
        if self._kernel is None:
            self._kernel = _make_motion_kernel(_MOTION_SIGMA_CELLS, shape)

    def update(self, frame, commanded_dir: Optional[str] = None):
        """Returns (col, row, confidence) or None."""
        # 1. Accumulate heatmap (reuse base machinery)
        gray = _gray(frame)
        self._base._accumulate(gray, commanded_dir)
        self._base.prev = gray

        heat = self._base.heat
        CH, CW = heat.shape

        # 2. Initialise flat log-posterior on first call
        if self._log_post is None:
            self._log_post = np.zeros((CH, CW), np.float64)

        self._ensure_kernel(heat.shape)

        # 4. Observation model gate: check heatmap strength first.
        peak = float(heat.max())
        mean = float(heat.mean()) + 1e-6

        # No commanded motion -> heatmap unchanged -> HOLD (don't re-update posterior on idle frames)
        if commanded_dir not in DELTA:
            if self.pos is not None:
                return (self.pos[0], self.pos[1], _CONF_FLOOR)
            return None

        if peak / mean < _PEAK:
            # Commanded motion but heatmap still weak (warming up) -> HOLD
            if self.pos is not None:
                return (self.pos[0], self.pos[1], _CONF_FLOOR)
            return None

        # 3. Motion model: diffuse the probability distribution via Gaussian blur.
        # Must exponentiate first (blur probabilities, not log-probs) then re-log.
        prob = np.exp(self._log_post - self._log_post.max())  # numerically stable
        prob_blurred = _convolve2d_valid(prob, self._kernel)
        prob_blurred = np.maximum(prob_blurred, 1e-300)
        log_prior = np.log(prob_blurred)
        log_prior -= log_prior.max()

        # convert heatmap to a probability-like obs likelihood (Gaussian around peak)
        # obs_ll[i,j] = -||cell_ij - peak_cell||^2 / (2*obs_sigma^2)
        pr, pc = np.unravel_index(int(heat.argmax()), heat.shape)
        rs, cs = np.mgrid[0:CH, 0:CW]
        obs_ll = -((rs - pr) ** 2 + (cs - pc) ** 2) / (2 * _OBS_SIGMA_CELLS ** 2)

        # 5. Update posterior: log P(state|obs) ∝ log_prior + obs_ll
        log_post = log_prior + obs_ll
        # normalise to prevent drift to -inf
        log_post -= log_post.max()
        log_post = np.maximum(log_post, _MIN_LOG_PRIOR)
        self._log_post = log_post

        # 6. MAP estimate
        mr, mc = np.unravel_index(int(log_post.argmax()), log_post.shape)
        new_pos = ((mc + 0.5) * _CELL, (mr + 0.5) * _CELL)
        self.pos = new_pos

        # 7. Confidence: reuse heatmap peak/mean grading (same scale as baseline)
        conf = min(1.0, max(0.0, (peak / mean - _PEAK) / (_CONF_SAT - _PEAK)))
        return (self.pos[0], self.pos[1], conf)
