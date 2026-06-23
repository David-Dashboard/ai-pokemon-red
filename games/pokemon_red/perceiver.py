"""OverworldPerceiver (Iteration 02, Step 2): pixels -> SymbolicState via odometry + an
occupancy map. Near vision-free — it uses a frame-diff ("did my move change the screen?")
plus dead-reckoning to remember where it has been and which directions are walls or
unexplored. That memory is the cure for the Iteration-01 "loop in one room" failure.

RAM is never touched (it's the scoring oracle). Phase B upgraded the odometry/area model:
- **Translation-based move detection:** the best integer-tile shift that aligns consecutive frames
  (``_best_shift``) gives a robust moved-vs-blocked signal (a real scroll vs a turn into a wall). The
  cursor still advances ONE tile per action — the ExploreBrain controller treats ``[d,d]`` as a net
  one-tile step, and recording the true 1-or-2 tiles makes it overshoot/oscillate. (The full
  measured-distance odometry — the complete dead-reckoning drift fix — waits on a controller that
  understands variable step sizes; the shift magnitude is already computed for when it lands.)
- **Topological place-graph:** a map WARP is detected as a scene cut (no translation aligns the
  frames) OR a fade (the emulator's pixels-only flag, robust right after a menu). On a warp the
  perceiver crosses to another PLACE, reusing a KNOWN place (restoring its accumulated map) via a
  direction-independent door edge, else minting a new one — so a building round-trip returns to the
  same map instead of re-exploring it (the run-#4 lab-entrance fix). Stairs (which don't fade) are
  caught by the translation signal.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from core.egomotion import best_shift
from core.egomotion import direction as ego_direction
from core.perception import JSON, PerceptMemory, SymbolicState
from core.tilemap import TileFunctionMap

_DIRS = ("up", "down", "left", "right")
_DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
_BACK = {"up": "down", "down": "up", "left": "right", "right": "left"}
_MOVE_THRESHOLD = 4.0   # (legacy) mean abs pixel diff above which a move happened
_AREA_THRESHOLD = 30.0  # best-SHIFT residual above which NO translation aligns the frames => a warp.
                        # Measured (eval/inspect_translation): same-map best-shift diff p90~5; real
                        # warps 55-77 (incl. stairs); a frame right after a warp can spike, so we
                        # re-baseline one frame after every transition.
                        # NOTE (2026-06-21 diagnosis): walking up to Oak's table scores ~35 and mints a
                        # SPURIOUS in-lab place here. Raising this to 45 was REVERTED: free-validation
                        # found a real lab-area transition at residual ~37 (warp/same-map bands overlap
                        # more than 55-77), so 45 would miss warps. The proper guard is a 2-frame
                        # confirmation (require the high residual to persist), not a higher threshold —
                        # deferred; the phantom place is a low-impact co-symptom, not the trap.
_TILE_PX = 16           # overworld tile = 16x16 px; the camera scrolls in whole-tile steps
_SHIFT_RANGE = 64       # search +/- this many px (4 tiles) for the translation that aligns two frames
# A small selection box in the upper-right (a YES/NO or list OVER a bottom textbox) marks a CHOICE,
# not plain advanceable text. Measured near-white fraction in that region: plain dialog ~0.00, an empty
# opening box ~0.08, a YES/NO box ~0.33, the START menu ~0.94 — so 0.15 cleanly flags a choice.
_CHOICE_WHITE = 0.15
# The overworld is camera-centred: the player sits at this screen cell, so the FACED tile (the one we
# walk onto / bump) is the player cell + the move's delta, in the 10x9 metatile grid (160x144 / 16).
# This (4,4) assumption holds away from map borders (where the camera stops and the player goes
# off-centre) — a known MVP limit, flagged for the tile-fingerprint robustness follow-on (Q6).
_PLAYER_CELL = (4, 4)
_SCREEN_COLS, _SCREEN_ROWS = 10, 9


def _dominant_dir(action: Optional[str]) -> Optional[str]:
    """Net direction of an action like 'up+up+up' or 'right+a' -> 'up' / 'right' / None.
    Uses the LAST directional token — the net facing for repeated taps."""
    if not action:
        return None
    toks = [t for t in str(action).replace("+", " ").split() if t in _DIRS]
    return toks[-1] if toks else None


def _has_frontier(cells: dict) -> bool:
    """True if this place still has an exploration frontier: a visited, non-portal cell with a non-wall
    direction into an unvisited (unknown) cell. Lets a GLOBAL explorer tell which OTHER places are still
    worth visiting (the cross-place exploration signal)."""
    for (cx, cy), c in cells.items():
        if not c.get("visited") or c.get("portal") is not None:
            continue
        for d in _DIRS:
            if d in c["walls"]:
                continue
            ddx, ddy = _DELTA[d]
            nbr = cells.get((cx + ddx, cy + ddy))
            if nbr is None or not nbr.get("visited"):
                return True
    return False


def _frame_diff(a, b) -> float:
    if a is None or b is None:
        return 0.0
    a = np.asarray(a, dtype=np.int16)
    b = np.asarray(b, dtype=np.int16)
    if a.shape != b.shape:
        return 255.0  # totally different (resolution / area change)
    return float(np.abs(a - b).mean())


def _gray(frame):
    g = np.asarray(frame)
    return g[..., :3].mean(axis=2) if g.ndim == 3 else g


def _best_shift(a, b):
    """The integer-tile translation that best aligns frame `b` back onto `a`, as (best_diff, (dx, dy)).
    Within a map the camera scrolls under a centered player, so frame N+1 is frame N shifted by the move
    — SOME shift matches (low best_diff); across a warp the scene cuts and NO shift aligns it (high
    best_diff). The shift magnitude is the distance actually scrolled (|shift|/tile = tiles moved). The
    tie_break biases toward the smallest aligning shift so identical frames give (0,0) = "blocked", not
    a phantom corner jump. Thin wrapper over the world-agnostic core.egomotion.best_shift; the overworld
    camera scrolls in whole tiles, hence step=_TILE_PX over +/-_SHIFT_RANGE px. Pixels only — no RAM."""
    _, best_diff, dx, dy = best_shift(a, b, max_shift=_SHIFT_RANGE, step=_TILE_PX, tie_break=1e-3)
    return best_diff, (dx, dy)


def _tile_at(frame, sc: int, sr: int):
    """The 16x16 pixel tile at screen cell (sc, sr) of a 160x144 frame, or None if out of range."""
    a = np.asarray(frame)
    y0, x0 = sr * _TILE_PX, sc * _TILE_PX
    tile = a[y0:y0 + _TILE_PX, x0:x0 + _TILE_PX]
    return tile if tile.shape[0] == _TILE_PX and tile.shape[1] == _TILE_PX else None


def _observe_faced_tile(tmap: TileFunctionMap, prev, direction: str, label: str) -> None:
    """Record the FACED tile's APPEARANCE with its behaviourally-proven function — 'walkable' from a
    confirmed move, 'blocked' from a bump. Cropped from the PRE-move frame, where the faced cell is
    clean terrain (the player is still at the centre cell, not on it yet), mirroring
    eval/probe_walkability_learn.py. This is the online build of the tile->function world model."""
    if prev is None:
        return
    pcx, pcy = _PLAYER_CELL
    ddx, ddy = _DELTA[direction]
    tile = _tile_at(prev, pcx + ddx, pcy + ddy)
    if tile is not None:
        tmap.observe(TileFunctionMap.fingerprint(tile), label)


def _predict_visible(tmap: TileFunctionMap, frame, cursor, cells: dict):
    """ADVISORY appearance-based layer: for each visible cell NOT yet physically visited, predict its
    function from its appearance (recognised from a tile-type touched elsewhere) and flag cells whose
    appearance is novel (unseen -> an exploration target = the novelty gate). World coords.

    Behaviour stays truth: this never overrides a confirmed wall (it only fills UNKNOWN cells), so it
    is a prior the controller MAY use to skip re-bumping appearance-known walls (the 'don't walk every
    cell' speedup) — wired in a later increment. The player cell is skipped (occluded by the sprite)."""
    if frame is None:
        return [], []
    x, y = cursor
    pcx, pcy = _PLAYER_CELL
    preds, novel = [], []
    for sr in range(_SCREEN_ROWS):
        for sc in range(_SCREEN_COLS):
            if (sc, sr) == _PLAYER_CELL:
                continue
            wx, wy = x + (sc - pcx), y + (sr - pcy)
            c = cells.get((wx, wy))
            if c is not None and c.get("visited"):
                continue                       # ground truth already known here
            tile = _tile_at(frame, sc, sr)
            if tile is None:
                continue
            fp = TileFunctionMap.fingerprint(tile)
            fn, conf, is_novel = tmap.classify(fp)
            if is_novel:
                novel.append([wx, wy])
            else:
                # 5th field = is_flat: a near-uniform tile whose function can't be trusted from looks
                # (a flat dark tile may be a wall OR a doorway/stairs), so a consumer can choose not to
                # act on flat predictions (ExploreBrain skip_flat) — the closed-loop A/B showed naive
                # skipping of flat 'blocked' tiles strands the agent on look-alike critical paths.
                preds.append([wx, wy, fn, round(conf, 2), TileFunctionMap.is_flat(fp)])
    return preds, novel


def detect_mode(frame, white: int = 230, t: float = 0.15) -> str:
    """Mode from pixels (overworld | menu | dialog | battle). Gen-1 UI panels are PURE white and the
    game world almost never is, so the near-white fraction by region separates them. Measured: an
    overworld frame is ~0% near-white everywhere; the START menu's right panel ~66%. A bottom panel =
    a dialog textbox; bright panels both top AND bottom = a battle (HP boxes + action box). Cheap, CPU,
    no training. Battle/dialog thresholds are structural priors to firm up once we have those frames."""
    if frame is None:
        return "overworld"
    g = _gray(frame)
    # A near-uniform frame (std ~ 0) is a fade/flash TRANSITION, not a UI panel. Measured: white and
    # black fades have std 0.0, while real battle/menu/dialog frames have std > 65 (dark sprites/text
    # on the white). Without this, an all-white flash trips the bright-top-AND-bottom 'battle' rule
    # (a false positive seen during the starter cutscene). Treat it as overworld — it's a one-frame
    # blank the odometry/area-change path already tolerates, and the next frame resolves the state.
    if float(g.std()) < 6.0:
        return "overworld"
    H, W = g.shape
    w = g >= white
    right = float(w[:, int(W * 0.6):].mean())
    bottom = float(w[int(H * 0.66):, :].mean())
    top = float(w[:int(H * 0.4), :].mean())
    if max(right, bottom, top) < t:
        return "overworld"
    if bottom > 0.3 and top > 0.3:
        return "battle"          # HP boxes (top) + action/text box (bottom)
    if right > 0.35 and right >= bottom:
        return "menu"            # right-side panel (START menu / battle action menu)
    if bottom > 0.3:
        # A bottom textbox. If a small selection box ALSO sits in the upper-right ABOVE the textbox (a
        # YES/NO, list, etc.), this is a CHOICE, not plain text -> label it 'menu' so the planner is
        # woken to decide, never auto-advanced. Plain dialog is just the bottom box (midright ~0).
        # The region spans the upper-right down to just above the textbox (rows ~24..89; the box starts
        # ~row 96, so its white interior never bleeds in — plain dialog stays 0.0 across captured frames,
        # incl. bright Pallet scenes). It only needs to catch a choice box drawn OVER a textbox; a
        # full-screen/right-panel menu (START, shop, battle action box) is already caught by the
        # right>0.35 rule above, and a battle by the battle rule, so this stays the narrow safety net.
        midright = float(w[int(H * 0.167):int(H * 0.62), int(W * 0.7):].mean())
        return "menu" if midright > _CHOICE_WHITE else "dialog"   # choice-over-textbox vs plain dialog
    # No region is a CLEAR UI panel (battle/dialog need bottom>0.3; a menu needs right>0.35). A region
    # merely in the 0.15-0.3 band is a bright OUTDOOR scene (Pallet's white roofs/paths push the bottom
    # to ~0.16), not a menu — calling it 'menu' was the run-#4 false-positive that triggered a resync
    # and masked the next map warp. Default to overworld.
    return "overworld"


class OverworldPerceiver:
    """Frame-diff walkability + a dead-reckoned occupancy map. All state lives in PerceptMemory."""

    def __init__(self, move_threshold: float = _MOVE_THRESHOLD,
                 area_threshold: float = _AREA_THRESHOLD) -> None:
        self.move_threshold = move_threshold
        self.area_threshold = area_threshold
        self._font = None            # lazily-loaded Gen-1 glyph table (textbox decoder)
        self._font_loaded = False

    def _ensure_font(self):
        """Lazily load the Gen-1 glyph table (a static pixels-only asset). None if absent/unloadable."""
        if not self._font_loaded:
            self._font_loaded = True
            try:
                from .textbox import FontTable
                self._font = FontTable.load()
            except Exception:
                self._font = None
        return self._font

    def _battle_context(self, frame) -> str:
        """A SETTLED battle frame -> 'battle_text' (advanceable narration the harness auto-advances)
        or 'battle' (the action/move menu: a DECISION -> wake). Pixels-only; DEFAULTS TO 'battle'
        (wake) unless narration is positively identified, so a mis-read menu is never auto-advanced."""
        if frame is None or self._ensure_font() is None:
            return "battle"
        try:
            from .textbox import battle_subscreen
            return "battle_text" if battle_subscreen(frame, self._font) == "battle_text" else "battle"
        except Exception:
            return "battle"

    def _read_text(self, frame) -> str:
        """Decode the dialog textbox to text — PIXELS ONLY (no RAM/VRAM), via the static glyph asset.
        Returns '' if the asset is absent, decoding fails, or the region holds too little recognizable
        text (so a non-textbox screen, e.g. the START menu over the world, doesn't produce junk)."""
        if frame is None or self._ensure_font() is None:
            return ""
        try:
            from .textbox import decode, decode_move_menu
            text = decode(frame, self._font)
            menu = decode_move_menu(frame, self._font)   # in-battle FIGHT move list + cursor, if shown
        except Exception:
            return ""
        known = sum(c not in "? \n" for c in text)
        parts = []
        if known >= 3:                      # guard: ignore glyph-poor regions (not a real textbox)
            parts.append(text)
        if menu:                            # surfaced even when the textbox itself is blank (move-select)
            parts.append(menu)
        return "\n".join(parts)

    def perceive(self, frame, memory: PerceptMemory,
                 context: Optional[JSON] = None) -> SymbolicState:
        ctx = context or {}
        m = memory.data
        m.setdefault("cursor", (0, 0))
        m.setdefault("places", {0: {}})    # place_id -> occupancy map {(x,y): {"visited","walls",...}}
        m.setdefault("place", 0)           # the place (map/room) we're in now
        m.setdefault("edges", {})          # (place, exit_cell, dir) -> (dest_place, entry_cell): warps
        m.setdefault("next_place", 1)      # id to assign the next NEW place
        m.setdefault("prev_frame", None)
        m.setdefault("steps", 0)
        m.setdefault("resync", False)
        m.setdefault("tilemap", TileFunctionMap())   # online behaviour-labelled appearance->function map
        m["steps"] += 1
        cells = m["places"].setdefault(m["place"], {})   # the CURRENT place's map

        # Mode first: a menu/dialog/battle is NOT the overworld — hand it straight to the planner and
        # do NOT run odometry on it (a menu cursor move isn't walking). Re-baseline when we return.
        mode = detect_mode(frame)
        if mode != "overworld":
            # In a battle, split the SETTLED frame finer: narration ('battle_text', the harness
            # auto-advances it for free) vs the action/move menu ('battle', a decision -> wake). Other
            # modes pass through unchanged. detect_mode still returns 'battle', so _settle_if_battle
            # (which keys on detect_mode) keeps firing on narration frames.
            ctx_label = self._battle_context(frame) if mode == "battle" else mode
            m["prev_frame"] = np.asarray(frame).copy() if frame is not None else None
            m["resync"] = True
            return SymbolicState(
                confidence=0.5, context=ctx_label,
                pose={"frame": "grid", "value": list(m["cursor"]), "uncertain": True, "area": m["place"]},
                spatial_memory={"kind": "occupancy-grid", "area": m["place"]},
                affordances=[],
                last_action={"action": ctx.get("last_action"), "outcome": "n/a"},
                screen_text=self._read_text(frame),   # decode the dialog/menu textbox from pixels
                raw_available=True, raw_ref=ctx.get("frame_path", ""))

        action = ctx.get("last_action")
        direction = _dominant_dir(action)
        prev = m["prev_frame"]
        first = prev is None or m["resync"]   # re-baseline after a menu/battle/transition
        m["resync"] = False

        # Ego-motion vs scene-cut, from PIXELS: the best translation that aligns prev->frame. A low
        # residual means a shift aligns them (same map, the camera scrolled); a high residual means no
        # shift does (a warp). The shift's magnitude is the distance ACTUALLY scrolled -> true odometry.
        shift_diff, (sdx, sdy) = 255.0, (0, 0)
        if not first and prev is not None and frame is not None:
            shift_diff, (sdx, sdy) = _best_shift(_gray(prev), _gray(frame))

        # A WARP: a FADE (emulator flag — robust even right after a menu, run #4's dominant miss) OR no
        # translation aligns the frames (a scene cut — this also catches interior STAIRS, which don't
        # fade). Needs a direction (you walked into the warp).
        transitioned = direction is not None and (
            bool(ctx.get("transition")) or ((not first) and shift_diff > self.area_threshold))

        x, y = m["cursor"]
        cell = cells.setdefault((x, y), {"visited": True, "walls": set()})
        cell["visited"] = True

        outcome, tiles = "unknown", 0
        if transitioned:
            # Cross to another PLACE. Reuse the KNOWN destination (restoring its accumulated map) if
            # we've taken this door before, else mint a NEW place — so a building round-trip returns to
            # the same Pallet map (incl. the lab door we already found) instead of re-exploring it.
            self._transit(m, (x, y), direction)
            cells = m["places"][m["place"]]
            x, y = m["cursor"]
            cell = cells.setdefault((x, y), {"visited": True, "walls": set()})
            cell["visited"] = True
            # Re-baseline the next frame's TRANSLATION check (not the fade): the frame right after a warp
            # is the arrival, and a normal move from it can score a high best-shift residual -> a spurious
            # transition that, at the entry cell, hits the reverse edge and lumps the two maps. Suppress
            # just the translation path for one frame; a genuine door RETURN still fires via the fade
            # flag. (Both doors are sealed in _transit, so the autopilot won't choose to re-cross anyway.)
            m["resync"] = True
            outcome = "moved"
        elif not first and direction:
            # Did we actually move, and how far? The best-shift magnitude along the action axis is a
            # robust moved-vs-blocked signal (a real scroll vs a turn-into-a-wall) AND the true distance
            # scrolled. We advance the cursor by the MEASURED tile count and mark every cell stepped
            # THROUGH as visited. The autopilot now single-steps ([d] = one tile, ExploreBrain
            # single_step), so this is 1 for routine traversal; a multi-tile press (an LLM 'up+up') lands
            # the cursor at the true end instead of silently dropping tiles. The old cap-at-one was the
            # run-#15 interior DRIFT bug: [d,d] moved two tiles but recorded one, so the occupancy map
            # corrupted in the tight lab room. Clamp to the search range so a mis-measure can't fling it.
            axis_px = abs(sdy) if direction in ("up", "down") else abs(sdx)
            if axis_px < _TILE_PX / 2:         # negligible scroll -> we walked into a wall
                cell["walls"].add(direction)
                outcome = "blocked"
                _observe_faced_tile(m["tilemap"], prev, direction, "blocked")
            else:
                # Re-ground (2026-06-21 diagnosis): the occupancy was ADD-ONLY (walls never cleared), so a
                # wall written at a phantom cell during Oak's cutscene boxed the agent in forever. A
                # CONFIRMED scroll is fresh evidence the cell is passable, so clear the stale wall both
                # ways: `direction` is open from the cell we left, and `_BACK[direction]` is open from the
                # cell we entered. (Only fires on a real move — |scroll| >= half a tile — so a wall-jam
                # still records its wall above.)
                cell["walls"].discard(direction)
                tiles = max(1, min(_SHIFT_RANGE // _TILE_PX, int(round(axis_px / _TILE_PX))))
                dx, dy = _DELTA[direction]
                for _ in range(tiles):         # mark each tile traversed, not just the endpoint
                    x, y = x + dx, y + dy
                    cells.setdefault((x, y), {"visited": True, "walls": set()})["visited"] = True
                m["cursor"] = (x, y)
                cell = cells[(x, y)]
                cell["walls"].discard(_BACK[direction])
                outcome = "moved"
                _observe_faced_tile(m["tilemap"], prev, direction, "walkable")

        # Motion-saliency (free NPC/ROI prior): when the camera was STATIC this step — we didn't
        # scroll (a blocked move or an A-press, |best-shift| < half a tile) — two consecutive frames
        # are pixel-aligned, so any region that still CHANGES is a MOVING entity (an idle-animating
        # NPC). The occupancy map only knows walls, not what's ON them; this fills that gap. Record
        # each such entity's WORLD cell (player cell + the on-screen offset) with a motion tally, so
        # the controller/LLM can seek it. Pixels only; saliency.motion_rois cluster-filters animated
        # terrain (water/flowers) out. The entity sits on a non-walkable tile (it reads as a wall), so
        # the ROI cell stays unvisited and never becomes a phantom frontier.
        camera_static = (not first) and prev is not None and max(abs(sdx), abs(sdy)) < _TILE_PX / 2
        if camera_static:
            from .saliency import motion_rois, roi_offsets
            for dx, dy in roi_offsets(motion_rois(prev, frame)):
                rc = cells.setdefault((x + dx, y + dy), {"visited": False, "walls": set()})
                rc["motion"] = rc.get("motion", 0) + 1

        m["prev_frame"] = np.asarray(frame).copy() if frame is not None else None

        # Affordances: directions from HERE that aren't known walls. Prefer those leading to an
        # unvisited cell (frontiers); fall back to any open direction.
        open_unexplored, open_all = [], []
        for d in _DIRS:
            if d in cell["walls"]:
                continue
            open_all.append(d)
            dx, dy = _DELTA[d]
            nbr = cells.get((x + dx, y + dy))
            if nbr is None or not nbr.get("visited"):
                open_unexplored.append(d)

        visited_n = sum(1 for c in cells.values() if c.get("visited"))
        # Motion-detected entities (NPCs) as candidate interaction targets, most-seen first.
        rois = sorted(([cx, cy] for (cx, cy), c in cells.items() if c.get("motion")),
                      key=lambda rc: -cells[(rc[0], rc[1])]["motion"])
        # Place-graph for a GLOBAL (cross-place) explorer: every portal edge (door cell + crossing
        # direction + destination place) and which places still have a frontier. Lets the controller
        # leave an exhausted room and resume exploring elsewhere instead of getting stuck (the lab trap).
        place_portals = [[p, list(c), d, dest] for (p, c), (dest, _e, d) in m["edges"].items()]
        place_frontiers = [pid for pid, pcells in m["places"].items() if _has_frontier(pcells)]
        # Full map + frontier cells, so a LOCAL controller can pathfind without the LLM. A frontier
        # is a visited cell with a non-wall direction into an unvisited (unknown) cell.
        grid, frontiers = [], []
        for (cx, cy), c in cells.items():
            grid.append({"x": cx, "y": cy, "visited": bool(c.get("visited")),
                         "portal": c.get("portal"), "walls": sorted(c["walls"])})
            if not c.get("visited") or c.get("portal") is not None:
                continue  # unvisited, or a portal boundary back to a seen place (not a frontier)
            for d in _DIRS:
                if d in c["walls"]:
                    continue
                ddx, ddy = _DELTA[d]
                nbr = cells.get((cx + ddx, cy + ddy))
                if nbr is None or not nbr.get("visited"):
                    frontiers.append([cx, cy])
                    break

        # Advisory appearance layer: from the online tile->function map, predict the function of
        # visible cells we have NOT yet visited and flag cells whose appearance is NOVEL (unseen ->
        # an exploration target). Additive to the open spatial_memory dict (no contract change);
        # behavioural occupancy (walls) stays authoritative.
        tile_predictions, novel_tiles = _predict_visible(m["tilemap"], frame, (x, y), cells)
        return SymbolicState(
            confidence=0.4,  # Step 2: keep the image attached; text-only is earned later
            context="overworld",
            pose={"frame": "grid", "value": [x, y], "uncertain": True, "area": m["place"]},
            spatial_memory={"kind": "occupancy-grid", "area": m["place"], "visited": visited_n,
                            "walls_here": sorted(cell["walls"]),
                            "map": grid, "frontiers": frontiers, "rois": rois,
                            "place_portals": place_portals, "place_frontiers": place_frontiers,
                            "places_known": len(m["places"]),
                            "tile_predictions": tile_predictions, "novel_tiles": novel_tiles,
                            "tile_types_seen": len(m["tilemap"]),
                            # pixels-only camera self-motion as a DIRECTION token (cardinal/none); the
                            # raw shift magnitude is unreliable so it is deliberately NOT surfaced here.
                            "ego_motion": ego_direction(sdx, sdy)},
            affordances=open_unexplored or open_all,
            last_action={"action": action, "outcome": outcome,
                         "diff": round(shift_diff, 2), "tiles": tiles},
            raw_available=True,
            raw_ref=ctx.get("frame_path", ""),
        )

    @staticmethod
    def _transit(m: dict, exit_cell: tuple, direction: str) -> None:
        """Cross a warp from the current place via the door at `exit_cell`. If we've taken this door
        before, return to that KNOWN place at its recorded entry (restoring its accumulated map); else
        mint a NEW place. Doors are keyed by CELL, not direction (you enter a building walking one way
        but leave the doormat walking another), with a reverse edge so the round-trip is symmetric.

        To stop the autopilot ping-ponging the doorway, BOTH ends of the door are sealed as PORTALs
        (walkable, never an exploration frontier): the source cell we left from, AND the cell just
        BEHIND the arrival (the way back out) — while the arrival cell ITSELF stays explorable so the
        new place still has a frontier to explore forward (sealing the arrival would strand the
        frontier-only autopilot)."""
        src = m["place"]
        key = (src, exit_cell)
        if key in m["edges"]:
            dest, entry, _ = m["edges"][key]
        else:
            dest = m["next_place"]
            m["next_place"] += 1
            entry = (0, 0)
            # store the crossing DIRECTION on each edge so a global explorer can route OUT of an
            # exhausted room: from src you cross by pressing `direction` at exit_cell; from dest you
            # cross back by pressing the reverse at entry.
            m["edges"][key] = (dest, entry, direction)
            m["edges"][(dest, entry)] = (src, exit_cell, _BACK[direction])   # reverse edge (keyed by cell)
            m["places"].setdefault(dest, {})
        dcells = m["places"].setdefault(dest, {})
        dcells.setdefault(entry, {"visited": True, "walls": set()})["visited"] = True   # arrival: explorable
        m["places"].setdefault(src, {}).setdefault(           # seal the door on the source side
            exit_cell, {"visited": True, "walls": set()})["portal"] = dest
        bdx, bdy = _DELTA[_BACK[direction]]                   # the cell behind the arrival = the way back
        back = (entry[0] + bdx, entry[1] + bdy)
        dcells.setdefault(back, {"visited": True, "walls": set()})["portal"] = src
        m["place"] = dest
        m["cursor"] = entry
