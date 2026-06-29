"""BlobContingencyLocalizer -- action-contingency localizer at the blob level.

Pipeline:
  rolling-median background -> foreground mask -> connected-components (core.blob)
  -> track blobs across frames -> avatar = the blob whose centroid displacement most
     consistently projects onto the commanded direction over the last H steps.

Persistence: when multiple blobs are tied, prefer the one nearest to the last known position.
Below a foreground floor (not enough motion) -> HOLD or None.

Output contract: (col, row, confidence) or None — same as AvatarLocalizer.
bbox is available via .last_blob (may be None).
numpy only. R0 realizer.
"""
from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np

from core.blob import Blob, RollingBg, associate_blobs, segment_blobs
from core.grid import DELTA

# ── hyperparameters ────────────────────────────────────────────────────────────
_BG_WINDOW      = 6       # rolling background window (frames)
_HISTORY        = 8       # steps of direction-history to score blobs against
_THRESH         = 15.0    # foreground threshold (pixel units)
_MIN_AREA       = 16      # min blob size (pixels)
_FLOOR_AREA     = 30.0    # min total foreground area to fire an update (vs stationary)
_PROJ_THRESH    = 0.3     # min mean cosine-projection score to claim command-contingency
_MAX_DIST       = 40.0    # max centroid distance for cross-frame association (px)
_CONF_SAT       = 6.0     # history length at which confidence saturates (~ _HISTORY)


# Direction unit vectors (for projection scoring)
_DIR_VEC = {
    "up":    np.array([ 0., -1.]),
    "down":  np.array([ 0.,  1.]),
    "left":  np.array([-1.,  0.]),
    "right": np.array([ 1.,  0.]),
}


class _TrackedBlob:
    """A blob being tracked across frames, with its direction-projection history."""
    def __init__(self, blob: Blob, track_id: int):
        self.id = track_id
        self.blob = blob
        # ring of (dx, dy, commanded_dir) for scoring
        self._history: deque[tuple[float, float, str]] = deque(maxlen=_HISTORY)
        self._prev_cx = blob.cx
        self._prev_cy = blob.cy

    def push(self, blob: Blob, commanded_dir: Optional[str]):
        dx = blob.cx - self._prev_cx
        dy = blob.cy - self._prev_cy
        self._prev_cx = blob.cx
        self._prev_cy = blob.cy
        self.blob = blob
        if commanded_dir in _DIR_VEC:
            self._history.append((dx, dy, commanded_dir))

    @property
    def centroid(self):
        return (self.blob.cx, self.blob.cy)

    def contingency_score(self) -> float:
        """Mean cosine-projection of displacement onto commanded direction.
        Ranges [-1, 1]; high = blob moves in commanded direction."""
        if not self._history:
            return 0.0
        scores = []
        for dx, dy, d in self._history:
            vec = _DIR_VEC[d]
            norm = float(np.hypot(dx, dy))
            if norm < 0.5:
                scores.append(0.0)     # stationary step
                continue
            scores.append(float((dx * vec[0] + dy * vec[1]) / norm))
        return float(np.mean(scores))


class BlobContingencyLocalizer:
    """Avatar localizer using blob-level action-contingency scoring."""

    def __init__(self):
        self._bg = RollingBg(_BG_WINDOW)
        self._tracks: dict[int, _TrackedBlob] = {}   # track_id -> TrackedBlob
        self._next_id = 0
        self.pos: Optional[tuple] = None
        self._avatar_track_id: Optional[int] = None
        self.last_blob: Optional[Blob] = None

    def reset(self):
        self._bg = RollingBg(_BG_WINDOW)
        self._tracks = {}
        self._next_id = 0
        self.pos = None
        self._avatar_track_id = None
        self.last_blob = None

    def _spawn_track(self, blob: Blob) -> int:
        tid = self._next_id; self._next_id += 1
        self._tracks[tid] = _TrackedBlob(blob, tid)
        return tid

    def update(self, frame, commanded_dir: Optional[str] = None):
        """Returns (col, row, confidence) or None."""
        a = np.asarray(frame)
        gray = a[..., :3].mean(2).astype(np.float32) if a.ndim == 3 else a.astype(np.float32)

        fg_mag = self._bg.update(gray)
        if fg_mag is None:
            return None

        # Not enough foreground -> avatar stationary -> HOLD
        if fg_mag.sum() < _FLOOR_AREA and self.pos is not None:
            return (self.pos[0], self.pos[1], 0.3)

        blobs = segment_blobs(None, fg_mag=fg_mag, thresh=_THRESH, min_area=_MIN_AREA)

        # Associate blobs to existing tracks
        prev_blobs = [t.blob for t in self._tracks.values()]
        prev_ids   = list(self._tracks.keys())
        cur_ids: list[Optional[int]] = []  # track_id for each cur blob

        pairs = associate_blobs(prev_blobs, blobs, max_dist=_MAX_DIST)
        new_track_ids: dict[int, int] = {}  # blob_index -> track_id
        for pi, ci in pairs:
            blob = blobs[ci]
            if pi is not None:
                tid = prev_ids[pi]
                self._tracks[tid].push(blob, commanded_dir)
                new_track_ids[ci] = tid
            else:
                tid = self._spawn_track(blob)
                new_track_ids[ci] = tid

        # Drop tracks that have no matching blob this frame
        live_tids = set(new_track_ids.values())
        dead = [tid for tid in self._tracks if tid not in live_tids]
        for tid in dead:
            del self._tracks[tid]
        if self._avatar_track_id not in self._tracks:
            self._avatar_track_id = None

        if not self._tracks:
            return None

        # Score each track
        scores = {tid: t.contingency_score() for tid, t in self._tracks.items()}
        best_tid = max(scores, key=lambda tid: scores[tid])
        best_score = scores[best_tid]

        if best_score < _PROJ_THRESH:
            # No blob clearly action-contingent: HOLD if we have a pos
            if self.pos is not None:
                return (self.pos[0], self.pos[1], 0.2)
            # Fallback on first frame(s): largest blob
            best_tid = max(self._tracks, key=lambda tid: self._tracks[tid].blob.area)

        self._avatar_track_id = best_tid
        avatar = self._tracks[best_tid].blob
        self.pos = (float(avatar.cx), float(avatar.cy))
        self.last_blob = avatar

        # Confidence: blend score and history length
        n_hist = len(self._tracks[best_tid]._history)
        hist_conf = min(1.0, n_hist / _CONF_SAT)
        score_conf = max(0.0, min(1.0, (best_score - _PROJ_THRESH) / (1.0 - _PROJ_THRESH)))
        conf = 0.5 * hist_conf + 0.5 * score_conf

        return (self.pos[0], self.pos[1], conf)
