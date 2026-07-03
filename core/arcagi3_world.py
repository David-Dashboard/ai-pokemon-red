"""arcagi3_world.py -- a thin adapter over the ARC-AGI-3 public REST API, mirroring the shape of the
other per-world adapters (core/miniwob_world.py, core/vizdoom_world.py): reset/step/screen(grid),
nothing more. The REST client itself is ported near-verbatim from runs/arcagi3_probe/client.py (the
spec-built probe; see runs/arcagi3_probe/PROBE_REPORT.md for the full API map + citations).

Why this world is structurally different from every other one in the registry: the "screen" here is
ALREADY a discrete int[][] grid (0-15 color indices, <=64x64), not pixels. There is no perceiver, no
frame-diff-to-blobs step needed to reach symbolic state -- the grid IS the symbolic state (see
PROBE_REPORT.md's "Analysis prep" section). So this adapter hands the RAW grid back to its caller
(world_mcp.ArcAgi3Session), which renders it as compact text -- unlike the GB/GBA/NDS worlds, which
deliberately withhold raw pixels from the brain (ADR-001 anti-confabulation law).

No-leak law (per the task brief): `levels_completed`/`win_levels`/`state`("WIN"/"GAME_OVER") are
oracle-only -- this adapter returns them to the caller in FrameResult, which is responsible for
routing them to oracle.jsonl and NEVER forwarding them into a tool result (same separation as
VizdoomWorld/MiniWobWorld -- this module does not know about oracle.jsonl at all).

Rate limiting: docs cap at 600 req/min; this client adds an unconditional client-side throttle (min
_MIN_INTERVAL seconds between HTTP calls, sleeping if called sooner) ON TOP OF the probe's existing
429-backoff retry, per the task brief's "build in a polite client-side throttle" instruction -- we do
not want to lean on the server's own limit enforcement as our only guard against a shared free preview
service.

Lazy: `requests` is already a repo dependency (pyproject.toml, used by core/llm.py's Ollama HTTP
path) -- no new dependency needed, so importing this module directly is safe with no env guard, unlike
the vizdoom/selenium adapters, which lazy-import an optional heavy install.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

BASE_URL = os.environ.get("ARC_BASE_URL", "https://three.arcprize.org")
API_KEY_ENV = "ARC_API_KEY"

# --- action space (docs.arcprize.org/actions.md; see PROBE_REPORT.md "Action space") --------------
SIMPLE_ACTIONS = ("ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION7")
COORD_ACTION = "ACTION6"
ALL_ACTIONS = (*SIMPLE_ACTIONS[:5], COORD_ACTION, SIMPLE_ACTIONS[5])  # ACTION1..7 in numeric order
GRID_MAX = 63  # x,y in [0, 63] inclusive (docs' "0-based grid coordinates (0-63 inclusive)")

# Client-side throttle: minimum seconds between any two outbound HTTP calls (polite floor well under
# the documented 600 req/min == one call per 100ms; 250ms keeps us at <=240 req/min even in a tight
# loop, per the task brief's explicit "min 250ms between calls" instruction).
_MIN_INTERVAL = 0.25

# 16-color ARC-AGI palette used only for the debug PNG dump path (unused by the MCP text-grid seam,
# kept for parity with the probe's client.py in case a debugging script wants it later).
ARC_PALETTE = [
    (0, 0, 0), (0, 116, 217), (255, 65, 54), (46, 204, 64), (255, 220, 0),
    (170, 170, 170), (240, 18, 190), (255, 133, 27), (127, 219, 255), (135, 12, 37),
    (100, 100, 100), (110, 90, 60), (60, 130, 90), (150, 60, 150), (200, 200, 50),
    (230, 230, 230),
]


@dataclass
class FrameResult:
    """One (action, state, score) record -- mirrors FrameData's public fields minus nothing (the
    caller, not this module, decides what's oracle-only vs brain-visible)."""
    step: int
    action: str
    args: dict
    game_id: str
    guid: str
    state: str                 # NOT_FINISHED | WIN | GAME_OVER
    levels_completed: int
    win_levels: int
    available_actions: list
    grid: list = field(repr=False)       # the LAST grid in the frame list (see _to_frame_result)
    frame_count: int = 1                 # how many grids `frame` actually contained (usually 1)


class ArcAgi3Client:
    """Raw REST client for the ARC-AGI-3 public API. One instance per scorecard; open_scorecard()
    must be called before reset(), reset() before any action.

    Endpoint map (docs.arcprize.org/api-reference/*; see runs/arcagi3_probe/PROBE_REPORT.md):
        POST /api/scorecard/open            -> {"card_id": "..."}
        POST /api/cmd/RESET                 -> FrameData (starts or restarts a game instance)
        POST /api/cmd/ACTION{1-5,7}         -> FrameData (simple actions, no params)
        POST /api/cmd/ACTION6 {x,y}         -> FrameData (coordinate action, x,y in 0-63)
        POST /api/scorecard/close           -> final scorecard summary
        GET  /api/scorecard/{card_id}       -> scorecard summary (mid-run or after close)
        GET  /api/games                     -> [{"game_id", "title"}, ...] (title-sorted)
    Auth: header `X-API-Key: <ARC_API_KEY>` on every request.
    Session affinity: RESET/ACTION responses set AWSALB* cookies; a requests.Session persists these
    automatically across calls on the same client instance -- do NOT create a fresh Session per call.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: str = BASE_URL, timeout: float = 30.0):
        self.api_key = api_key or os.environ.get(API_KEY_ENV, "")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": self.api_key, "Accept": "application/json",
                                     "Content-Type": "application/json"})
        self.card_id: Optional[str] = None
        self.game_id: Optional[str] = None
        self.guid: str = ""
        self._last_call_ts: float = 0.0

    # -- polite client-side throttle: sleep so consecutive calls are >= _MIN_INTERVAL apart -----------

    def _throttle(self) -> None:
        now = time.monotonic()
        wait = self._last_call_ts + _MIN_INTERVAL - now
        if wait > 0:
            time.sleep(wait)
        self._last_call_ts = time.monotonic()

    # -- low-level request wrapper: throttle + one retry-on-429 per the documented rate limit ---------

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self.base_url}{path}"
        for attempt in range(3):
            self._throttle()
            r = self.session.post(url, json=body, timeout=self.timeout)
            if r.status_code == 429:   # RATE_LIMIT_EXCEEDED (docs: 600 rpm cap) -- exponential backoff
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
        return r.json()

    def _get(self, path: str) -> dict:
        self._throttle()
        r = self.session.get(f"{self.base_url}{path}", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # -- scorecard lifecycle ----------------------------------------------------------------------------

    def open_scorecard(self, tags: Optional[list[str]] = None, source_url: Optional[str] = None) -> str:
        body: dict[str, Any] = {}
        if tags:
            body["tags"] = tags
        if source_url:
            body["source_url"] = source_url
        resp = self._post("/api/scorecard/open", body)
        self.card_id = resp["card_id"]
        return self.card_id

    def close_scorecard(self) -> dict:
        if not self.card_id:
            raise RuntimeError("no open scorecard -- call open_scorecard() first")
        return self._post("/api/scorecard/close", {"card_id": self.card_id})

    def get_scorecard(self, card_id: Optional[str] = None) -> dict:
        cid = card_id or self.card_id
        if not cid:
            raise RuntimeError("no scorecard to retrieve")
        return self._get(f"/api/scorecard/{cid}")

    def list_games(self) -> list[dict]:
        return self._get("/api/games")

    # -- game lifecycle -----------------------------------------------------------------------------------

    def reset(self, game_id: str) -> FrameResult:
        if not self.card_id:
            raise RuntimeError("no open scorecard -- call open_scorecard() first")
        self.game_id = game_id
        resp = self._post("/api/cmd/RESET", {"game_id": game_id, "card_id": self.card_id, "guid": None})
        self.guid = resp["guid"]
        return self._to_frame_result(0, "RESET", {}, resp)

    def action(self, name: str, step: int, x: Optional[int] = None, y: Optional[int] = None,
               reasoning: Optional[dict] = None) -> FrameResult:
        if not self.guid:
            raise RuntimeError("no active game -- call reset() first")
        body: dict[str, Any] = {"game_id": self.game_id, "guid": self.guid}
        args: dict[str, Any] = {}
        if name == COORD_ACTION:
            if x is None or y is None:
                raise ValueError(f"{COORD_ACTION} requires x, y in [0, {GRID_MAX}]")
            x, y = int(x), int(y)
            if not (0 <= x <= GRID_MAX and 0 <= y <= GRID_MAX):
                raise ValueError(f"x,y must be in [0, {GRID_MAX}]; got ({x}, {y})")
            body["x"], body["y"] = x, y
            args = {"x": x, "y": y}
        if reasoning is not None:
            body["reasoning"] = reasoning
        resp = self._post(f"/api/cmd/{name}", body)
        self.guid = resp.get("guid", self.guid)   # guid can rotate across calls
        return self._to_frame_result(step, name, args, resp)

    @staticmethod
    def _to_frame_result(step: int, action: str, args: dict, resp: dict) -> FrameResult:
        # `frame` is a LIST of grids (docs say "1-N frames" per action; every worked example shows
        # len==1 -- PROBE_REPORT.md open question 2). Take the LAST grid (the settled post-action
        # state, if N>1 represents animation sub-steps) and record how many we saw, rather than
        # assuming len==1 and silently mis-indexing if the live API ever returns more.
        frames = resp.get("frame") or []
        grid = frames[-1] if frames else []
        return FrameResult(
            step=step, action=action, args=args,
            game_id=resp.get("game_id", ""), guid=resp.get("guid", ""),
            state=resp.get("state", "UNKNOWN"),
            levels_completed=resp.get("levels_completed", 0),
            win_levels=resp.get("win_levels", 0),
            available_actions=resp.get("available_actions", []),
            grid=grid,
            frame_count=len(frames),
        )


# --- text rendering: compact single-char-per-cell rows, <=64 chars/row (world_mcp's observe seam) ----
# 16-color palette -> single printable ASCII char per cell, so a 64x64 grid renders as 64 rows of
# <=64 chars each -- lossless (each of the 16 colors maps to a distinct char) and compact (a 64x64
# grid is 64 short text lines, versus a 4096-int JSON array).
_CELL_CHARS = "0123456789ABCDEF"  # index -> char; grid values are ints 0-15


def render_grid(grid: list) -> str:
    """Render an int[][] grid as compact text rows, one char per cell (hex-nibble style: 0-9, A-F),
    max 64 chars/row (the grid is capped at 64x64 by the API, so no row ever needs truncation).

    A cell value outside the documented 0-15 color range raises ValueError LOUDLY (PR #77 review
    finding 3) -- a silent modulo wrap would mask a spec violation / palette expansion from the live
    API, inconsistent with this repo's reject-loudly-never-clamp discipline."""
    if not grid:
        return "(empty grid)"
    lines = []
    for y, row in enumerate(grid):
        chars = []
        for x, v in enumerate(row):
            try:
                idx = int(v)
            except (TypeError, ValueError):
                raise ValueError(f"grid cell ({x},{y}) has non-numeric value {v!r} -- "
                                 "expected an int color index 0-15")
            if not (0 <= idx <= 15):
                raise ValueError(f"grid cell ({x},{y}) has color value {idx} outside the documented "
                                 "0-15 range -- the API spec may have changed; refusing to render")
            chars.append(_CELL_CHARS[idx])
        lines.append("".join(chars))
    return "\n".join(lines)


def diff_grids(prev: Optional[list], curr: list) -> dict:
    """Exact cell-level diff between two grids: returns {"changed": n, "by_color": {"A->B": count}}.
    `prev` is None on the very first frame (nothing to diff against). Grids of mismatched shape (a
    level transition can resize the grid) are reported as a shape-change, not cell-by-cell -- diffing
    cell (x,y) across two different-sized grids is meaningless."""
    if prev is None:
        return {"changed": 0, "by_color": {}, "note": "first frame -- nothing to diff"}
    if len(prev) != len(curr) or (prev and curr and len(prev[0]) != len(curr[0])):
        return {"changed": -1, "by_color": {},
                "note": f"grid shape changed ({len(prev)}x{len(prev[0]) if prev else 0} -> "
                        f"{len(curr)}x{len(curr[0]) if curr else 0})"}
    changed = 0
    by_color: dict[str, int] = {}
    for y in range(len(curr)):
        prow, crow = prev[y], curr[y]
        for x in range(len(crow)):
            pv, cv = int(prow[x]), int(crow[x])
            if pv != cv:
                changed += 1
                key = f"{pv}->{cv}"
                by_color[key] = by_color.get(key, 0) + 1
    return {"changed": changed, "by_color": by_color, "note": ""}
