"""Shared helpers for eval scripts.

Keeps one canonical copy of small utilities that would otherwise be duplicated
across compare_localizers.py, probe_entities.py, play_generic.py, bench_generic.py.
"""
from __future__ import annotations

import os
import re


# Games that use a follow/scroll camera (spread < 15 from eval/score_localize).
FOLLOW_KEYS = ("gold", "kirby", "metroid", "spaceinv", "f1race", "ffa", "sml")

# Held-out games: never tune thresholds on these; report separately.
HELD_OUT = {"crystalis", "zelda", "sml", "f1race"}


def _slug(path: str) -> str:
    """Label-file path -> game slug, stripping any leading date prefix."""
    name = os.path.basename(path).replace(".json", "")
    return re.sub(r'^\d{4}-\d{2}-\d{2}_', '', name)


def is_follow_camera(slug: str) -> bool:
    """Return True when the game uses a follow/scroll camera."""
    return any(k in slug for k in FOLLOW_KEYS)


def _camera(slug: str) -> str:
    """Return 'follow' or 'fixed'."""
    return "follow" if is_follow_camera(slug) else "fixed"


def _is_held_out(slug: str) -> bool:
    return any(h in slug for h in HELD_OUT)


def _iou(b1, b2) -> float:
    """Intersection-over-union for float bbox [x0, y0, x1, y1] (exclusive convention)."""
    ix0, iy0 = max(b1[0], b2[0]), max(b1[1], b2[1])
    ix1, iy1 = min(b1[2], b2[2]), min(b1[3], b2[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    if inter == 0:
        return 0.0
    a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    return inter / (a1 + a2 - inter)
