"""Smoke-test the vision service via the core client (run from the MAIN repo env:
  uv run python eval/_vision_smoke.py
proves the cross-env HTTP path: client (main env, requests-only) -> service (py3.12+torch)."""
import time
from core.vision_client import VisionClient

LABELS = ["a blank repeating tiled floor pattern", "a plain stone wall",
          "a small cartoon person or character", "a small round ball",
          "a glowing television or computer screen", "a leafy green potted plant",
          "a wooden box or cabinet", "a staircase"]

vc = VisionClient("http://127.0.0.1:4002")
h = None
for _ in range(40):
    h = vc.health()
    if h:
        break
    time.sleep(1)
print("health:", h)
assert h, "service not up"

print("\nOCR (title, 3x):", repr(vc.ocr("runs/haiku_eval/frame_000016.png", upscale=3)))
print("OCR (dialog region, 3x):",
      repr(vc.ocr("runs/modes/242_ui_candidate_dialog.png", region=[0, 96, 160, 144], upscale=3)))
print("\nCAPTION (bedroom):", repr(vc.caption("runs/perception_run/frame_000001.png")))
print("\nGRID objects (bedroom):")
for o in vc.grid("runs/perception_run/frame_000001.png", LABELS, background=["floor", "wall"]):
    print("  ", o)
print("\nclient calls:", vc.calls)
