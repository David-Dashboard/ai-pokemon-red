"""Blob-segmentation primitive: foreground mask -> discrete sprite blobs.

Foreground = |frame - rolling-median background| > thresh.
Connected-components via pure-numpy BFS union-find (scipy.ndimage not in the frozen env).
Returns per-blob centroid / bbox / area; drops blobs below min_area.

A minimal cross-frame tracker (associate_blobs) pairs blobs to previous blobs by nearest-centroid
with IoU tie-break -- used by BlobContingencyLocalizer for persistence.

numpy only. R0 realizer. No cv2, no scipy.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from PIL import Image

# ── connected-components (pure numpy, BFS) ────────────────────────────────────

def _label_bfs(mask: np.ndarray, connectivity: int = 4) -> tuple[np.ndarray, int]:
    """Label connected components of bool mask via BFS. Returns (labels, n_labels).
    Labels are 1-indexed (0 = background).
    connectivity=4: cardinal neighbours only (default).
    connectivity=8: cardinal + diagonal neighbours."""
    H, W = mask.shape
    labels = np.zeros((H, W), dtype=np.int32)
    n = 0
    flat = mask.ravel()
    label_flat = labels.ravel()
    idx = np.where(flat)[0]
    pending = set(idx.tolist())
    _neighbours4 = ((-1, 0), (1, 0), (0, -1), (0, 1))
    _neighbours8 = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))
    neighbours = _neighbours8 if connectivity == 8 else _neighbours4
    for seed in list(pending):
        if label_flat[seed] != 0 or not flat[seed]:
            continue
        n += 1
        queue = [seed]
        label_flat[seed] = n
        head = 0
        while head < len(queue):
            cur = queue[head]; head += 1
            cy, cx = divmod(cur, W)
            for dy, dx in neighbours:
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < H and 0 <= nx < W:
                    ni = ny * W + nx
                    if flat[ni] and label_flat[ni] == 0:
                        label_flat[ni] = n
                        queue.append(ni)
    return labels, n


# ── rolling-median background ─────────────────────────────────────────────────

class RollingBg:
    """Rolling median background model over the last `window` grayscale frames."""
    def __init__(self, window: int = 6):
        self.window = window
        self._buf: list[np.ndarray] = []

    def update(self, gray: np.ndarray) -> Optional[np.ndarray]:
        """Push a new frame; return the foreground magnitude (or None if not enough history)."""
        self._buf.append(gray)
        if len(self._buf) > self.window:
            self._buf.pop(0)
        if len(self._buf) < 3:
            return None
        bg = np.median(np.stack(self._buf), axis=0)
        return np.abs(gray.astype(np.float32) - bg)


# ── blob descriptor ───────────────────────────────────────────────────────────

class Blob:
    __slots__ = ("cx", "cy", "x0", "y0", "x1", "y1", "area")

    def __init__(self, cx: float, cy: float, x0: int, y0: int, x1: int, y1: int, area: int):
        self.cx = cx; self.cy = cy
        self.x0 = x0; self.y0 = y0; self.x1 = x1; self.y1 = y1
        self.area = area

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.x0, self.y0, self.x1, self.y1)

    def __repr__(self):
        return f"Blob(c=({self.cx:.0f},{self.cy:.0f}) bbox={self.bbox} area={self.area})"


def _gray(frame) -> np.ndarray:
    a = np.asarray(frame)
    if a.ndim == 3:
        g = a[..., :3].mean(2)
    else:
        g = a
    return g.astype(np.float32)


def segment_blobs(
    frame,
    fg_mag: Optional[np.ndarray] = None,
    *,
    bg: Optional["RollingBg"] = None,
    thresh: float = 15.0,
    min_area: int = 16,
    connectivity: int = 4,
) -> list[Blob]:
    """Segment foreground blobs from a frame.

    Args:
        frame: RGB array or PIL Image (160x144 or any shape).
        fg_mag: pre-computed foreground magnitude (|frame - bg|); if None, `bg` must be provided.
        bg: RollingBg instance; only used when fg_mag is None.
        thresh: foreground threshold (pixel units, 0-255 scale).
        min_area: drop blobs with fewer pixels than this.
        connectivity: 4 (cardinal, default) or 8 (cardinal+diagonal).

    Returns list of Blob (empty list if no foreground or not enough bg history).
    """
    if fg_mag is None:
        gray = _gray(frame)
        if bg is None:
            raise ValueError("provide either fg_mag or bg")
        fg_mag = bg.update(gray)
        if fg_mag is None:
            return []

    mask = fg_mag > thresh
    if not mask.any():
        return []

    labels, n = _label_bfs(mask, connectivity=connectivity)
    blobs = []
    for lbl in range(1, n + 1):
        ys, xs = np.where(labels == lbl)
        area = len(xs)
        if area < min_area:
            continue
        blobs.append(Blob(
            cx=float(xs.mean()), cy=float(ys.mean()),
            x0=int(xs.min()), y0=int(ys.min()),
            x1=int(xs.max()), y1=int(ys.max()),
            area=area,
        ))
    return blobs


# ── cross-frame tracker ───────────────────────────────────────────────────────

def _iou(a: Blob, b: Blob) -> float:
    ix0, iy0 = max(a.x0, b.x0), max(a.y0, b.y0)
    ix1, iy1 = min(a.x1, b.x1), min(a.y1, b.y1)
    inter = max(0, ix1 - ix0 + 1) * max(0, iy1 - iy0 + 1)
    if inter == 0:
        return 0.0
    ua = (a.x1 - a.x0 + 1) * (a.y1 - a.y0 + 1)
    ub = (b.x1 - b.x0 + 1) * (b.y1 - b.y0 + 1)
    return inter / (ua + ub - inter)


def associate_blobs(
    prev: list[Blob],
    cur: list[Blob],
    *,
    max_dist: float = 40.0,
) -> list[tuple[Optional[int], int]]:
    """Greedy nearest-centroid association. Returns list of (prev_idx or None, cur_idx)."""
    if not prev or not cur:
        return [(None, j) for j in range(len(cur))]
    # distance matrix
    pc = np.array([(b.cx, b.cy) for b in prev])
    cc = np.array([(b.cx, b.cy) for b in cur])
    # (n_prev, n_cur)
    diffs = pc[:, None, :] - cc[None, :, :]          # (P, C, 2)
    dists = np.hypot(diffs[..., 0], diffs[..., 1])   # (P, C)
    used_prev = set()
    used_cur = set()
    pairs: list[tuple[Optional[int], int]] = []
    # sort all (dist, pi, ci) and greedily match
    order = np.argsort(dists.ravel())
    for flat in order:
        pi, ci = divmod(int(flat), len(cur))
        if pi in used_prev or ci in used_cur:
            continue
        if dists[pi, ci] > max_dist:
            break
        pairs.append((pi, ci))
        used_prev.add(pi); used_cur.add(ci)
    # unmatched current blobs are new
    for ci in range(len(cur)):
        if ci not in used_cur:
            pairs.append((None, ci))
    return pairs
