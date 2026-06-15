"""Evaluation & measurement harnesses (all $0 — no API, no ROM required to import).

  * score_perception.py — score a perception run against the RAM oracle (oracle.jsonl).
  * tune_threshold.py    — pick the move/area frame-diff thresholds from a logged run.
  * capture_modes.py     — script the gated opening to real battle/dialog frames and grade detect_mode().

Making this a regular package (rather than relying on an implicit namespace package) keeps
`python -m eval.<module>` and `from eval.<module> import ...` unambiguous.
"""
