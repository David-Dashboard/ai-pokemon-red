"""GridPerceiver — the shared occupancy-grid perceiver (pixels -> SymbolicState) for the lean worlds.

The pose backbone that transfers across camera classes: a coarse occupancy grid dead-reckoned ONE cell
per confirmed move, with persistent-wall confirmation (a follow camera's dead-zone or a fixed camera's
idle animation makes a single no-move ambiguous, so only seal a wall after N persistent attempts). The
ONLY per-world parts are injected as a `MoveSignal` strategy: (a) did the commanded action land, (b)
which cardinal to step, (c) what to surface as `ego_motion`. Everything else — the grid, frontiers,
affordances, the wall bookkeeping, the SymbolicState assembly — is shared. Pixels only; RAM never
touched (no-leak is structural). `context` comes from world-agnostic `core.modality.detect_modality`.

Lifted from games/gauntlet/perceiver.py + games/cave_noire/perceiver.py the second time the body was
needed; the two now differ ONLY in their move signal (camera-scroll vs foreground-residual) and step
source (ego token vs commanded button) — both expressed as a MoveSignal below.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol

import numpy as np
from PIL import Image

from core.egomotion import best_shift, direction
from core.entities import EntityDetector
from core.grid import BACK, DELTA, DIR2EGO, DIRS, EGO2DIR
from core.modality import detect_modality
from core.perception import JSON, PerceptMemory, SymbolicState
from core.tilemap import TileFunctionMap

WALL_CONFIRM = 3           # seal a wall only after N persistent no-move attempts (dead-zone/idle is transient)
_NW, _NH = 128, 112        # normalize frames for best_shift (same as eval/probe_camera_model)
_MAX_SHIFT, _STEP = 18, 2  # 2D translation search (px on the normalized frame)
_GRID = 8                  # per-cell change grid (eval/probe_spatial_move): a real move spikes ONE cell
# no-progress backstop: a per-step pixel signal can't fully separate a real move from a stuck flicker-loop
# (eval/probe_phantom_move: ~33% of corridor wall-bumps still spike a cell), so a sustained same-direction
# run that isn't VISUALLY progressing is a phantom runaway -> demote to no-move and let wall-confirm seal it.
# Gated on a long same-dir run so it never fires on normal exploration.
_RUN_GUARD, _PROG_W, _PROG_MIN = 4, 4, 4.0
_DELTA_INV = {v: k for k, v in DELTA.items()}    # unit (dx,dy) -> cardinal, for snapping cell deltas to a step
# Pose-drift / confidence tracking:
#   _CONF_BASE  — steady-state confidence when the map is reliable
#   _CONF_DRIFT — confidence floor when drift is detected (no-move-after-command or phantom-runaway)
#   _CONF_RECOV — how quickly confidence recovers per confirmed move (linear rise back to _CONF_BASE)
#   _DEAD_TRIES — a frontier is pruned after this many goto/explore "no-path / 0-step" attempts
_CONF_BASE, _CONF_DRIFT, _CONF_RECOV = 0.7, 0.2, 0.1
_DEAD_TRIES = 3

# Tilemap-based relocalization (loop closure for dead-reckoning drift).
# A "place signature" is a tuple of tile fingerprints sampled from fixed screen regions (avoiding the
# avatar at screen centre). On revisit, a distinctive, unique signature match → re-anchor the cursor.
# Only fires in fixed-camera worlds (ForegroundSignal) where the background is stable each frame.
#
# Crop grid: 12 positions across 3 rows × 4 columns. Each crop is _SIG_TILE × _SIG_TILE pixels.
# Columns are spaced to cover left/right thirds; rows avoid the screen centre strip (avatar zone).
# GB frame is 160×144 px. Avatar in fixed-camera worlds sits near pixel (80, 72) = centre.
# We sample: rows at y=8, y=56, y=112 (top, upper-mid below row 0, bottom) — skipping y=72 (avatar).
# Columns at x=8, x=52, x=104, x=144 (left, centre-left, centre-right, right edge).
_SIG_TILE = 16       # pixels per side for each sampled crop
_SIG_ROWS = [8, 56, 112]              # y offsets (top-left of crop); avoids centre strip 64-88
_SIG_COLS = [8, 52, 104, 144]        # x offsets
_SIG_POSITIONS = [(y, x) for y in _SIG_ROWS for x in _SIG_COLS]  # 12 crops

# A signature is considered flat/ambiguous if too many of its tiles are individually flat.
_SIG_MIN_DISTINCT = 6    # at least this many non-flat fingerprints required (out of 12)
# Relocalization fires only when the signature match is UNIQUE (exactly 1 stored cell) and the
# re-anchor distance is > 1 cell (a 1-cell difference is within dead-reckoning noise — not worth firing).
_RELOC_MIN_DIST = 2      # minimum L-inf distance (cells) to trigger a re-anchor
# A loop-closure means RETURNING to a place after travelling elsewhere — not a look-alike frame seen a step
# or two ago during normal travel (which is a false positive: same signature, genuinely different cell). Only
# re-anchor when the stored signature was last recorded at least this many gameplay frames ago.
_RELOC_RECENCY = 5


def grid_max_change(prev_norm, cur_norm) -> float:
    """Max per-cell mean-abs change (8x8 grid): localizes a sprite move the whole-frame mean washes out.
    AUC 0.99 vs 0.86 whole-frame for move-vs-stuck (eval/probe_spatial_move)."""
    if prev_norm is None or cur_norm is None:
        return 0.0
    d = np.abs(cur_norm - prev_norm)
    nh, nw = d.shape
    ch, cw = nh // _GRID, nw // _GRID
    return float(d[:ch * _GRID, :cw * _GRID].reshape(_GRID, ch, _GRID, cw).mean(axis=(1, 3)).max())


@dataclass(frozen=True)
class MoveResult:
    """A MoveSignal's verdict for one commanded step."""
    moved: bool                  # did the commanded action land?
    step_dir: Optional[str]      # cardinal to advance the cursor AND clear walls; None if not moved
    ego_motion: str              # value to surface in spatial_memory["ego_motion"] ("east".."north"/"none")


class MoveSignal(Protocol):
    """Decides move/step/ego from the (base-computed) ego-motion primitives. The only per-world part."""
    def __call__(self, *, commanded_dir: Optional[str], ego_token: str,
                 sdx: int, sdy: int, best_diff: float, grid_max: float) -> MoveResult: ...


class CameraScrollSignal:
    """Follow-camera worlds (Gauntlet): the camera scrolled => we moved; step by the ego (scrolled) axis."""

    def __init__(self, move_px: float = 2.0) -> None:
        self.move_px = move_px

    def __call__(self, *, commanded_dir, ego_token, sdx, sdy, best_diff, grid_max=0.0) -> MoveResult:
        # Step by the EGO axis (best_shift's dominant axis), not the last-pressed token: on an 8-way
        # diagonal press ego picks the axis that ACTUALLY scrolled (the 0.31->0.02 drift fix). Surface the
        # raw ego token regardless of whether it cleared the move threshold.
        if max(abs(sdx), abs(sdy)) >= self.move_px:
            return MoveResult(True, EGO2DIR.get(ego_token, commanded_dir), ego_token)
        return MoveResult(False, None, ego_token)

    def fixed_camera(self) -> bool:
        return False    # follow-camera: the world scrolls under a centered avatar


class ForegroundSignal:
    """Fixed-camera worlds (Cave Noire): the screen never scrolls, so the move signal is FOREGROUND motion.
    The per-step signal is GRID-MAX (max per-cell change) -- a real sprite move spikes one cell, where the
    whole-frame residual gets diluted by the static background (AUC 0.99 vs 0.86, eval/probe_spatial_move;
    a CNN/embedding was tested and is no better -- invariance machines forgive the small change we want).
    Direction is the commanded button (turn-based, command == move); camera-scroll is a rarely-firing
    fallback. The residual tail it can't separate is caught by the base's no-progress backstop."""

    def __init__(self, move_px: float = 2.0, fg_grid: float = 58.0) -> None:
        self.move_px = move_px
        self.fg_grid = fg_grid

    def __call__(self, *, commanded_dir, ego_token, sdx, sdy, best_diff, grid_max=0.0) -> MoveResult:
        scrolled = max(abs(sdx), abs(sdy)) >= self.move_px
        if scrolled or grid_max >= self.fg_grid:
            step = EGO2DIR.get(ego_token, commanded_dir) if scrolled else commanded_dir
            return MoveResult(True, step, DIR2EGO.get(step, "none"))
        return MoveResult(False, None, "none")

    def fixed_camera(self) -> bool:
        return True     # fixed/static screen: sprites move against a still background


def _dominant_dir(action: Optional[str]) -> Optional[str]:
    """Net commanded direction of an action like 'up+up' or 'right+b' -> 'up' / 'right' / None."""
    if not action:
        return None
    toks = [t for t in str(action).replace("+", " ").split() if t in DIRS]
    return toks[-1] if toks else None


def _grays(frame, nw: int, nh: int):
    """(full-res grayscale for detect_modality, normalized nw x nh for best_shift) from a raw frame."""
    if frame is None:
        return None, None
    a = np.asarray(frame)
    g = a[..., :3].mean(axis=2) if a.ndim == 3 else a.astype(np.float32)
    norm = np.asarray(Image.fromarray(g.astype(np.uint8)).resize((nw, nh), Image.BILINEAR), np.float32)
    return g.astype(np.float32), norm


def _place_sig(frame_arr: np.ndarray) -> Optional[tuple]:
    """Compute a place signature: a tuple of tile fingerprints from 12 fixed screen regions.

    Returns None if the frame is too small or the signature is too flat/ambiguous (too many
    near-uniform crops → not a distinctive enough place to risk re-anchoring on).

    The 12 positions avoid the screen centre (avatar zone). This is called on the raw uint8 frame."""
    h, w = frame_arr.shape[:2]
    fps = []
    flat_count = 0
    for (py, px) in _SIG_POSITIONS:
        y1, y2 = py, min(py + _SIG_TILE, h)
        x1, x2 = px, min(px + _SIG_TILE, w)
        if y2 <= y1 or x2 <= x1:
            return None          # frame too small
        crop = frame_arr[y1:y2, x1:x2]
        fp = TileFunctionMap.fingerprint(crop)
        fps.append(fp)
        if TileFunctionMap.is_flat(fp):
            flat_count += 1
    distinct = len(_SIG_POSITIONS) - flat_count
    if distinct < _SIG_MIN_DISTINCT:
        return None              # too many flat/ambiguous tiles → not a safe relocalization target
    return tuple(fps)


class GridPerceiver:
    """screen -> SymbolicState via dead-reckoned odometry + a coarse occupancy map. No RAM.

    `move_signal` is the only per-world part (see CameraScrollSignal / ForegroundSignal)."""

    def __init__(self, move_signal: MoveSignal, *, max_shift: int = _MAX_SHIFT, step: int = _STEP,
                 nw: int = _NW, nh: int = _NH, wall_confirm: int = WALL_CONFIRM,
                 entity_detector: Optional[EntityDetector] = None) -> None:
        self.move_signal = move_signal
        self.max_shift = max_shift
        self.step = step
        self.nw, self.nh = nw, nh
        self.wall_confirm = wall_confirm
        self._entity_detector = entity_detector or EntityDetector()

    def perceive(self, frame: Any, memory: PerceptMemory,
                 context: Optional[JSON] = None) -> SymbolicState:
        m = memory.data
        m.setdefault("cursor", (0, 0))
        cells = m.setdefault("cells", {})
        blocked = m.setdefault("blocked_attempts", {})   # (cell, dir) -> consecutive no-move attempts
        dead_frontiers = m.setdefault("dead_frontiers", {})  # (cx,cy) -> consecutive 0-step/no-path tries
        m.setdefault("pose_confidence", _CONF_BASE)
        ctx = context or {}
        action = ctx.get("last_action")
        commanded_dir = _dominant_dir(action)
        cur_full, cur_norm = _grays(frame, self.nw, self.nh)
        first = m.get("prev_norm") is None

        # context: world-agnostic gameplay/menu/static.
        if first or cur_full is None:
            label = "gameplay"
        else:
            toks = [t for t in str(action or "").replace("+", " ").split() if t]
            label, _ = detect_modality(m["prev_full"], cur_full, toks)
        if label != "gameplay":          # a menu/transition breaks a movement run (no-progress backstop state)
            m["run"] = (None, 0)

        # ego-motion primitives: best translation aligning prev->cur (camera) + the residual (foreground)
        # + the localized per-cell max change (the move signal that beats whole-frame on a fixed camera).
        best_diff, sdx, sdy, grid_max = 0.0, 0, 0, 0.0
        if not first and cur_norm is not None:
            _, best_diff, sdx, sdy = best_shift(m["prev_norm"], cur_norm,
                                                max_shift=self.max_shift, step=self.step, tie_break=1e-3)
            grid_max = grid_max_change(m["prev_norm"], cur_norm)
        ego_token = direction(sdx, sdy)

        # Optional absolute-pose hook (fixed-camera localization): if the move signal can read the avatar's
        # cell from pixels, SNAP the cursor to it -- pose is a function of the CURRENT frame, so there is no
        # dead-reckoning integral to accumulate error (the strand fix). None (unlocked / no frame) -> fall back
        # to the dead-reckon path below, so we are never worse than before. Walls are sealed/cleared only on a
        # clean unit step that AGREES with the command (the avatar moves only where commanded; a disagreeing
        # delta is localizer noise -> snap the position but leave the walls).
        abs_cell = None
        if not first and frame is not None and hasattr(self.move_signal, "absolute_cell"):
            abs_cell = self.move_signal.absolute_cell(frame, commanded_dir=commanded_dir)

        x, y = m["cursor"]
        cell = cells.setdefault((x, y), {"visited": True, "walls": set()})
        cell["visited"] = True
        outcome, ego_motion = "unknown", "none"
        if abs_cell is not None:
            nx, ny = abs_cell
            if not m.get("snapped"):                  # first lock: the pre-lock dead-reckon cells are in the
                cells.clear(); blocked.clear()         # wrong (relative) frame -> drop them, re-anchor on truth
            dx, dy = nx - x, ny - y
            ncell = cells.setdefault((nx, ny), {"visited": True, "walls": set()})
            ncell["visited"] = True
            m["cursor"] = (nx, ny)
            step = _DELTA_INV.get((dx, dy))
            if m.get("snapped") and step is not None and step == commanded_dir:   # confirmed unit step
                cell["walls"].discard(step)                          # left cell open the way we MOVED
                ncell["walls"].discard(BACK[step])                   # entered cell open back the way we came
                blocked.pop(((x, y), commanded_dir), None)
                ego_motion, outcome = DIR2EGO.get(step, "none"), "moved"
            elif m.get("snapped") and dx == 0 and dy == 0 and commanded_dir:       # commanded but pinned -> wall
                key = ((x, y), commanded_dir)
                blocked[key] = blocked.get(key, 0) + 1
                if blocked[key] >= self.wall_confirm:
                    cell["walls"].add(commanded_dir)
                    outcome = "blocked"
            elif dx or dy:                                           # first lock / >1 jump / off-axis noise
                outcome = "moved"
            m["snapped"] = True
            cell, x, y = ncell, nx, ny
        elif not first:
            res = self.move_signal(commanded_dir=commanded_dir, ego_token=ego_token,
                                   sdx=sdx, sdy=sdy, best_diff=best_diff, grid_max=grid_max)
            ego_motion = res.ego_motion
            moved, step_dir = res.moved, res.step_dir
            if moved and step_dir and commanded_dir:
                # no-progress backstop: track the consecutive same-direction run and whether the screen has
                # actually changed over the last _PROG_W steps. A long run that isn't progressing = a phantom
                # runaway (idle flicker faking grid-max moves at a wall) -> demote to no-move; wall-confirm seals it.
                run_dir, run_len = m.get("run", (None, 0))
                run_len = run_len + 1 if step_dir == run_dir else 1
                m["run"] = (step_dir, run_len)
                recent = m.get("recent_norms", [])
                prog = (float(np.abs(cur_norm - recent[-_PROG_W]).mean())
                        if cur_norm is not None and len(recent) >= _PROG_W else None)
                if run_len >= _RUN_GUARD and prog is not None and prog < _PROG_MIN:
                    moved, step_dir = False, None          # not actually getting anywhere -> treat as no-move
                    # phantom runaway detected: the move signal fired but we went nowhere; the occupancy map
                    # is likely drifting -> drop confidence so the brain knows the symbolic view is unreliable.
                    m["pose_confidence"] = _CONF_DRIFT
            elif not (moved and step_dir):
                m["run"] = (None, 0)
            if commanded_dir:
                if moved and step_dir:                      # the commanded move landed
                    blocked.pop(((x, y), commanded_dir), None)
                    step = step_dir
                    cell["walls"].discard(step)            # the cell we left is open the way we MOVED
                    dx, dy = DELTA[step]
                    x, y = x + dx, y + dy                   # one press = one cell (magnitude deferred)
                    cell = cells.setdefault((x, y), {"visited": True, "walls": set()})
                    cell["visited"] = True
                    cell["walls"].discard(BACK[step])       # the entered cell is open back the way we came
                    m["cursor"] = (x, y)
                    outcome = "moved"
                    # confirmed move: map is tracking; recover confidence toward the base.
                    m["pose_confidence"] = min(_CONF_BASE, m["pose_confidence"] + _CONF_RECOV)
                else:                                       # no move: a WALL or a transient dead-zone/idle
                    key = ((x, y), commanded_dir)
                    blocked[key] = blocked.get(key, 0) + 1
                    if blocked[key] >= self.wall_confirm:   # persistent -> a real wall, seal it
                        cell["walls"].add(commanded_dir)
                        outcome = "blocked"
                    elif blocked[key] == 1:
                        # first no-move-after-command (may be drift, not a wall yet): mild confidence drop.
                        # This is the highest-leverage signal: ok=True from the gateway but the avatar
                        # didn't move -> the dead-reckoned cursor may be wrong.
                        m["pose_confidence"] = max(_CONF_DRIFT, m["pose_confidence"] - 0.15)

        m["prev_full"], m["prev_norm"] = cur_full, cur_norm
        if cur_norm is not None:                 # rolling frame buffer for the no-progress backstop
            recent = m.setdefault("recent_norms", [])
            recent.append(cur_norm)
            del recent[:-(_PROG_W + 1)]

        # Tilemap-based relocalization (loop closure) for PURE dead-reckoning worlds: when the agent
        # re-enters mapped territory, re-anchor the drifted cursor to the remembered location. SKIPPED
        # when the move signal provides an `absolute_cell` localizer (it already gives a per-frame
        # ground-truth fix — there is no dead-reckoning drift to recover, and running both would make
        # two snap mechanisms fight over the cursor). Fixed-camera only — follow-camera worlds scroll
        # every step, so a fixed-screen signature is meaningless. Guard: the signature must be
        # distinctive (`_place_sig` rejects flat/ambiguous frames) and the re-anchor distance must
        # exceed dead-reckoning noise (_RELOC_MIN_DIST).
        # KNOWN LIMITATION (see reports/2026-06-29-relocalization-notes.md): exact 12-tile signatures
        # cannot distinguish a real loop-closure from two identically-templated rooms, so a wrong
        # re-anchor is possible in games with repeated room layouts. NOT yet bench-validated.
        fixed_cam = getattr(self.move_signal, "fixed_camera", lambda: False)()
        if (fixed_cam
                and not hasattr(self.move_signal, "absolute_cell")
                and label == "gameplay" and frame is not None):
            frame_arr = np.asarray(frame)
            if frame_arr.ndim >= 2:
                place_sigs: dict = m.setdefault("place_sigs", {})   # sig -> (cx, cy, step_last_seen)
                step_n = m["_reloc_step"] = m.get("_reloc_step", 0) + 1
                sig = _place_sig(frame_arr)
                if sig is not None:
                    # MATCH FIRST against the PRIOR recording, THEN record. Recording before the lookup
                    # (the original bug) just returned the position we wrote this frame, so the re-anchor
                    # guard was always false and relocalization never fired. Re-anchor only on a genuine
                    # loop-closure: a stored signature, far enough from the (drifted) cursor, AND last seen
                    # _RELOC_RECENCY+ frames ago (so a look-alike frame recurring during travel doesn't
                    # spuriously snap us back). Then overwrite with the new position + step.
                    prev = place_sigs.get(sig)
                    if (prev is not None
                            and (prev[0], prev[1]) != (x, y)
                            and max(abs(prev[0] - x), abs(prev[1] - y)) >= _RELOC_MIN_DIST
                            and step_n - prev[2] >= _RELOC_RECENCY):
                        mx, my = prev[0], prev[1]
                        m["cursor"] = (mx, my)
                        x, y = mx, my
                        cell = cells.setdefault((x, y), {"visited": True, "walls": set()})
                        cell["visited"] = True
                        m["pose_confidence"] = _CONF_BASE
                        outcome = "moved"   # treat as a successful repositioning
                    # Record AFTER matching (only past the origin so it isn't over-recorded). After a
                    # re-anchor (x, y) == prev cell, so this just refreshes its step stamp.
                    if len(cells) >= 2:
                        place_sigs[sig] = (x, y, step_n)

        # Dead-frontier detection: two signals increment a frontier's fail counter:
        # 1. External (world_mcp / bench): context["goto_fails"] = [(cx,cy), ...] — the caller
        #    observed 0 steps / no-path for these targets and tells us explicitly.
        # 2. Internal (purely perceiver-side): if the cursor has been at the SAME position for
        #    _DEAD_TRIES consecutive commanded moves that all returned no-move outcomes, then all
        #    current frontiers are inaccessible from here (the agent is jammed). Demote all of them.
        for fail_coord in ctx.get("goto_fails", []):
            key = tuple(fail_coord)
            dead_frontiers[key] = dead_frontiers.get(key, 0) + 1
        # Internal jam detection: if the agent keeps trying the SAME DIRECTION with no movement,
        # the cursor is drift-jammed (a phantom-runaway or a corrupt wall map). Distinguish this from
        # NORMAL wall discovery (trying different directions at a dead-end, which is expected exploration).
        # Only fire when the same commanded direction produces no-move _DEAD_TRIES times in a row from
        # the same cursor position — that's a repeated single-direction jam, not multi-direction probing.
        cursor_now = (x, y)
        m.setdefault("_jam_dir", None)
        m.setdefault("_jam_len", 0)
        if commanded_dir and outcome not in ("moved",):
            if m["_jam_dir"] == commanded_dir and m.get("_jam_pos") == cursor_now:
                m["_jam_len"] += 1
            else:
                m["_jam_dir"] = commanded_dir
                m["_jam_pos"] = cursor_now
                m["_jam_len"] = 1
        else:
            m["_jam_dir"] = None
            m["_jam_pos"] = cursor_now
            m["_jam_len"] = 0
        # Fire after _DEAD_TRIES same-direction no-moves, demoting only the SPECIFIC cells involved:
        # - the cursor's current cell (the frontier head that can't be left in this direction)
        # - the neighbor in the jammed direction (the dead target)
        # Targeted demotion avoids mass-pruning valid frontiers in other directions (Zelda regression
        # when ALL frontiers were demoted simultaneously at a multi-frontier dead-end).
        if m["_jam_len"] >= _DEAD_TRIES and commanded_dir:
            jammed_dx, jammed_dy = DELTA.get(commanded_dir, (0, 0))
            jam_target = (cursor_now[0] + jammed_dx, cursor_now[1] + jammed_dy)
            dead_frontiers[jam_target] = dead_frontiers.get(jam_target, 0) + 1
            dead_frontiers[cursor_now] = dead_frontiers.get(cursor_now, 0) + 1
        # Drop cells that have failed _DEAD_TRIES times from the dead-frontier set if they're now reachable
        # (a wall was later confirmed there) — keep the dict bounded.
        dead_frontiers_pruned = {k: v for k, v in dead_frontiers.items() if v < _DEAD_TRIES * 3}
        m["dead_frontiers"] = dead_frontiers_pruned

        # affordances: open (non-wall) directions, unexplored first.
        open_unexplored, open_all = [], []
        for d in DIRS:
            if d in cell["walls"]:
                continue
            open_all.append(d)
            ddx, ddy = DELTA[d]
            nbr = cells.get((x + ddx, y + ddy))
            if nbr is None or not nbr.get("visited"):
                open_unexplored.append(d)

        # full map + frontier cells (a frontier = visited cell with a non-wall edge into the unknown).
        # Dead frontiers (repeatedly unreachable) are demoted: kept in the map but omitted from the
        # active frontier list so the brain isn't lured into infinite retries toward them.
        visited_n = sum(1 for c in cells.values() if c.get("visited"))
        grid, frontiers = [], []
        for (cx, cy), c in cells.items():
            grid.append({"x": cx, "y": cy, "visited": bool(c.get("visited")),
                         "portal": None, "walls": sorted(c["walls"])})
            if not c.get("visited"):
                continue
            for d in DIRS:
                if d in c["walls"]:
                    continue
                ddx, ddy = DELTA[d]
                nbr = cells.get((cx + ddx, cy + ddy))
                if nbr is None or not nbr.get("visited"):
                    # omit frontier if it has failed _DEAD_TRIES times (dead / drift-isolated)
                    if dead_frontiers_pruned.get((cx, cy), 0) < _DEAD_TRIES:
                        frontiers.append([cx, cy])
                    break

        # Entity detection (S7) is DISPATCHED BY CAMERA CLASS (S3): the motion-based foreground detector is
        # valid only on a fixed/static screen, where sprites move against a still background. On a follow
        # camera the whole screen scrolls every frame, so the rolling-background reads the scroll as
        # foreground and floods spurious blobs — so we skip it (return empty) rather than feed the brain
        # garbage. The follow-camera detector (a camera-compensated residual) is a future per-cell algorithm;
        # see reports/perception-ontology.md (S7 routed by S3) + the killed relative-motion pipeline.
        entities: list[dict] = []
        if fixed_cam and frame is not None:
            frame_arr = np.asarray(frame)
            if frame_arr.ndim == 3 and frame_arr.shape[2] >= 3:
                entities = self._entity_detector.detect(frame_arr)

        raw_ref = ctx.get("frame_path", "") if frame is not None else ""
        pose_conf = m["pose_confidence"]
        return SymbolicState(
            # Pose-drift-aware confidence: starts at _CONF_BASE (0.7), drops toward _CONF_DRIFT (0.2) when
            # a no-move-after-command or phantom-runaway is detected, recovers by _CONF_RECOV per confirmed
            # move. Low confidence signals the brain that the dead-reckoned map may be wrong. (ADR-001 inv-6)
            confidence=round(pose_conf, 2),
            context=label,
            pose={"frame": "grid", "value": [x, y], "uncertain": pose_conf < _CONF_BASE, "area": 0,
                  "confidence": round(pose_conf, 2)},
            spatial_memory={"kind": "occupancy-grid", "area": 0, "visited": visited_n,
                            "walls_here": sorted(cell["walls"]),
                            "map": grid, "frontiers": frontiers, "rois": [],
                            "place_portals": [], "place_frontiers": [], "places_known": 1,
                            "ego_motion": ego_motion,
                            "entities": entities},
            affordances=open_unexplored or open_all,
            last_action={"action": action, "outcome": outcome, "diff": round(best_diff, 2)},
            screen_text="",
            raw_available=bool(raw_ref), raw_ref=raw_ref,
        )
