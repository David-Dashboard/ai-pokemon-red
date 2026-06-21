"""World-agnostic client for the local vision service (vision_service.py).

Lets the perceiver/brain use off-the-shelf perception (OCR / scene caption /
per-cell CLIP grid) over HTTP without the world-repo importing torch. All calls
DEGRADE GRACEFULLY: if the service is down/disabled or errors, they return an
empty result so the fast pixel-only perceiver keeps working. Pixels only — no
RAM ever crosses here (the non-leaking-oracle invariant holds).

This module is game-agnostic by design (ADR-001): it knows nothing about
Pokémon. Labels, cell sizes and textbox regions are supplied by the caller
(the world-specific perceiver in games/<world>/).
"""
from __future__ import annotations

from typing import List, Optional, Sequence

try:
    import requests
except Exception:  # requests is a hard dep, but stay import-safe
    requests = None


class VisionClient:
    def __init__(self, url: str = "http://127.0.0.1:4002", timeout: float = 60.0,
                 enabled: bool = True) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.enabled = enabled and requests is not None
        self.calls = 0

    # -- low-level ---------------------------------------------------------- #
    def _post(self, path: str, payload: dict) -> Optional[dict]:
        if not self.enabled:
            return None
        try:
            r = requests.post(f"{self.url}{path}", json=payload, timeout=self.timeout)
            r.raise_for_status()
            self.calls += 1
            return r.json()
        except Exception:
            return None

    def health(self) -> Optional[dict]:
        if not self.enabled:
            return None
        try:
            return requests.get(f"{self.url}/health", timeout=5).json()
        except Exception:
            return None

    # -- capabilities ------------------------------------------------------- #
    def ocr(self, image_path: str, region: Optional[Sequence[int]] = None,
            upscale: int = 1) -> str:
        """Read text from an image (optionally a cropped region, optionally upscaled)."""
        out = self._post("/ocr", {"image_path": image_path,
                                  "region": list(region) if region else None,
                                  "upscale": upscale})
        return (out or {}).get("text", "")

    def caption(self, image_path: str, with_ocr: bool = False) -> str:
        """Whole-image descriptive caption (the agent's 'pause & grasp the scene')."""
        out = self._post("/caption", {"image_path": image_path, "with_ocr": with_ocr})
        return (out or {}).get("caption", "")

    def grid(self, image_path: str, labels: Sequence[str], cell: int = 16,
             upscale: int = 8, background: Optional[Sequence[str]] = None) -> List[dict]:
        """Per-cell CLIP classification -> object cells [{x,y,label,score}, ...]
        (cells whose label is in `background` are dropped from `objects`)."""
        out = self._post("/grid", {"image_path": image_path, "labels": list(labels),
                                   "cell": cell, "upscale": upscale,
                                   "background": list(background or [])})
        return (out or {}).get("objects", [])
