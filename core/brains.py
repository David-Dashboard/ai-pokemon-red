"""Brains — everything that decides (the Brain protocol).

Two are provided:

  * ScriptedBrain — zero-dependency. A seeded "mash A and wander" policy that
    proves the whole pipeline (gateway → plugin → emulator) end to end without
    any model. This is your smoke test.

  * LLMButtonBrain — an LLM agent. Builds a prompt from the observation's text
    (and optionally the screenshot, for vision models) and asks a local Ollama
    model for the next button. Provider is pluggable via `complete_fn`; the
    default talks to Ollama over HTTP. Point it at Claude/any API by passing
    your own complete_fn.

Both obey invariant 13: one ToolCall per decide() call. Multi-step play is the
runner looping, not a fatter brain.
"""

from __future__ import annotations

import base64
import json
import random
import re
import uuid
from typing import Callable, Optional

from core.contracts import Observation, ToolCall, ToolSpec
from core.disconfirm import DisconfirmDetector
from core.novelty import NoveltyMemory
from core.outcome import OutcomeMemory, action_key, state_signature

BUTTONS = ("a", "b", "start", "select", "up", "down", "left", "right")

# How many of the most recent LLM-authored lessons to keep in the per-run buffer and re-inject. A
# small cap keeps the re-injection cheap (cost-conscious) and recent (the run's latest learning).
_LESSON_CAP = 8
# How many recent auto-advanced dialog text chunks to carry as the "missed since last decision"
# transcript. Capped so a long forced dialog can't bloat the next wake's prompt.
_TRANSCRIPT_CAP = 12
# A safety fuse: force one LLM wake after this many CONSECUTIVE free auto-advances, so a pathological
# never-terminating advance loop (a stuck textbox/battle that always reads as advanceable) can't run
# forever for free. Normal dialog/battle narration is a handful of frames between decisions, so this
# never trips in practice — it's a backstop, not a budget.
_ADVANCE_FUSE = 50
# Seen-states cycle gate: a dialog state VISITED this many times while auto-advancing means we're
# CYCLING a textbox the confirm button can't dismiss (e.g. Oak's "which POKEMON?" — in Red you must
# WALK to a Pokeball, A only re-opens the prompt). Stop mashing and wake System 2 with the bare fact.
# Unlike _ADVANCE_FUSE (consecutive frames, reset by the interleaved overworld frames the cycle emits,
# so it never tripped), this counts VISITS and is immune. From the longloop run the trap's settled
# frames recur 10x; 3 visits trips at step ~416 (the trap ran uncaught to 463), while the legit Oak
# intro (all-unique lines) and a held textbox (1 visit) never trip.
_CYCLE_REVISITS = 3
# General stuck-breaker (no-novelty): how many consecutive non-overworld DECISIONS with no NEW
# (signature, screen_text) state seen before we tell System 2 it appears stuck. Catches a HELD stuck
# screen the cycle gate misses — e.g. the name-entry keyboard (run 3: 44 identical frames, all 1
# "visit" under rising-edge) — and a stuck menu, WITHOUT false-firing in a real battle (whose
# narration keeps producing novel text, resetting the count). Conservative: between _CYCLE_REVISITS
# (3) and the driver wake-watchdog (~40), so it nudges a recovery well before the run is halted.
_STUCK_STALE = 12
# Repeated-no-move breaker: consecutive OVERWORLD decisions with NO pose change before we force a STEERED
# System-2 wake. From the 2026-06-21 odometry diagnosis: in the lab the autopilot jammed ONE blocked move
# 243x (pose frozen) and never woke, draining to the watchdog; the runs that GOT the starter escaped only
# when an LLM wake re-routed off the stale wall. Firing at 8 breaks the jam early; legit walking changes the
# pose every single_step, so it resets and never trips while the agent is actually moving.
_NO_MOVE_STALL = 8

# Circuit breaker: halt after this many CONSECUTIVE failed model calls (the driver checks
# brain.consec_api_errors). A persistent backend outage — e.g. aria/litellm returning the same
# 400 "credit balance is too low" every wake (runs #5/#6/#14) — otherwise burns the whole --max-llm-
# calls budget on no-op retries before halting; this fails fast and loud instead. A real reply resets it.
API_ERROR_CIRCUIT_BREAKER = 4

# Substrings that mark a reply as a backend/API error PASSED THROUGH as content (aria returns litellm
# errors as a 200 with the error text in the message, so they don't raise — runs #5/#6/#14). Specific
# enough that a normal THINK/MOVE reply never matches.
_API_ERROR_MARKERS = ("ModelHTTPError", "Something went wrong on my end", "BadRequestError",
                      "status_code: 4", "status_code: 5", "credit balance", "litellm.")


def _looks_like_api_error(raw: Optional[str]) -> bool:
    """True if a model reply is actually a backend error echoed back as content (not a real answer)."""
    return bool(raw) and any(m in raw for m in _API_ERROR_MARKERS)


# Default per-token prices for the spend ESTIMATE (USD/token) — Haiku-4.5 rates (2026-06): $1.00 / $5.00
# per MTok in/out, $1.25 cache-write, $0.10 cache-read. The brain is model-agnostic (ROADMAP), so pass a
# different `pricing` to bill another model. This is an estimate for a cost GUARD, not an invoice: it bills
# whatever usage fields the backend returns and treats input with no reported cache-split at the full
# input rate (a slight over-estimate, the safe direction for a "don't overspend" breaker).
HAIKU_45_PRICING = {"in": 1.00e-6, "out": 5.00e-6, "cache_read": 0.10e-6, "cache_write": 1.25e-6}
# Sonnet 4.6 pricing for the perception-escalation cost estimate, folded into the SAME run cost cap as
# the cheap agent (so escalation isn't a separate untracked budget). A guard estimate — over-billing is
# the safe direction; adjust if Anthropic's posted Sonnet rates differ.
SONNET_46_PRICING = {"in": 3.00e-6, "out": 15.00e-6, "cache_read": 0.30e-6, "cache_write": 3.75e-6}


def _estimate_cost(usage: Optional[dict], pricing: dict) -> float:
    """USD estimate for ONE model call from its OpenAI-shaped `usage`. litellm surfaces Anthropic prompt
    caching as prompt_tokens_details.cached_tokens and/or cache_read/creation_input_tokens; whichever are
    present are billed at the cache rates and the remainder of prompt_tokens at the input rate.

    NOTE (S1 / pre-S2): the live aria backend currently reports only prompt/completion/total tokens — NO
    cache split (`ai-aria/.../openai_compat.py`) — so today `cached`/`created` are 0 and the whole prompt
    bills at the input rate (an over-estimate, the safe direction for a spend guard). The cache branch is
    forward-looking: it becomes live once aria forwards cache tokens. It assumes those fields are a SUBSET
    already inside `prompt_tokens` (litellm's OpenAI normalization rolls cache reads into prompt_tokens);
    if aria ever forwards the RAW Anthropic `input_tokens` (the uncached remainder) plus a separate cache
    count, this subtraction would under-bill — re-verify the subset semantics when S2 turns caching on."""
    if not usage:
        return 0.0
    pt = usage.get("prompt_tokens") or 0
    ct = usage.get("completion_tokens") or 0
    details = usage.get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens") or usage.get("cache_read_input_tokens") or 0
    created = usage.get("cache_creation_input_tokens") or 0
    uncached = max(pt - cached - created, 0)
    return (uncached * pricing["in"] + cached * pricing["cache_read"]
            + created * pricing["cache_write"] + ct * pricing["out"])


def _call(tool: str, args: dict, agent_id: str) -> ToolCall:
    return ToolCall(tool=tool, args=args, agent_id=agent_id, call_id=f"call-{uuid.uuid4()}")


class ScriptedBrain:
    """Deterministic smoke-test policy: mostly advance dialog, sometimes walk."""

    def __init__(self, agent_id: str, seed: int = 0) -> None:
        self.agent_id = agent_id
        self.rng = random.Random(seed)

    def decide(self, obs: Observation, tools: list[ToolSpec], context: dict) -> Optional[ToolCall]:
        # 60% press A (advance text / confirm), 40% a random walk direction.
        if self.rng.random() < 0.6:
            button = "a"
        else:
            button = self.rng.choice(["up", "down", "left", "right"])
        return _call("press_button", {"button": button}, self.agent_id)


_DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


class ExploreBrain:
    """Local frontier-exploration autopilot — NO LLM, NO API. Reads the SymbolicState's occupancy
    map and BFS-paths to the nearest frontier. This is the cheap controller that does routine
    traversal, so an expensive brain is only needed at real decisions. Returns None when no frontier
    remains (exploration of the known area is exhausted).

    `single_step` selects the per-tile MOTION CONTRACT (a per-world property the driver injects):
      * False (agnostic default): press the direction TWICE ([d, d]) — "turn, then move", a net one
        tile under GateWorld semantics where a direction change costs a press.
      * True: press the direction ONCE ([d]). On the real Pokémon emulator the held press absorbs the
        turn, so a single press = exactly one tile (validated, eval/probe_step). [d, d] there moves
        TWO tiles, which the dead-reckoning cursor recorded as one -> the run-#15 interior DRIFT.
        Single-stepping keeps every move one tile so the cursor stays synced with the world."""

    def __init__(self, agent_id: str, single_step: bool = False,
                 probe_interactables: bool = False) -> None:
        self.agent_id = agent_id
        self.last_thought = ""
        self.single_step = single_step
        # When frontier exploration is exhausted, instead of immediately giving up (waking the LLM),
        # PROBE the surrounding walls for an interactable: an NPC / object / sign sits on a non-walkable
        # tile, so it reads as a wall and is never a frontier — the only way to find it from the screen
        # is to face it and press the confirm button. Off by default (agnostic worlds unchanged); the
        # Pokémon drivers turn it on. `_probed` remembers which wall directions were tried at each cell.
        self.probe_interactables = probe_interactables
        self._probed: dict = {}

    def decide(self, obs: Observation, tools: list[ToolSpec], context: dict) -> Optional[ToolCall]:
        sm = obs.data.get("spatial_memory") or {}
        pose = (obs.data.get("pose") or {}).get("value")
        cells = {(c["x"], c["y"]): c for c in sm.get("map", [])}
        if pose is None:
            self.last_thought = "bootstrap"
            return self._move("down")
        cur = (pose[0], pose[1])
        # goto(target): if the planner set a destination, pathfind to it (free); when it's reached
        # or unreachable from the known map, fall through to ordinary frontier exploration.
        goto = (context or {}).get("goto")
        if goto is not None and tuple(goto[:2]) != cur:
            d = self._bfs_first_step(cur, cells, {tuple(goto[:2])})
            if d:
                self.last_thought = f"goto {tuple(goto[:2])} via {d}"
                return self._move(d)
        d = self._unexplored_dir(cur, cells)
        if d:
            self.last_thought = f"frontier here -> {d}"
            return self._move(d)
        d = self._bfs_first_step(cur, cells, {tuple(f) for f in sm.get("frontiers", [])})
        if d:
            self.last_thought = f"to nearest frontier via {d}"
            return self._move(d)
        # This room is fully explored — but the GLOBAL map may not be. Before probing or giving up,
        # route back through a known portal to a place that still has a frontier (the cross-place
        # explorer): exhaust the lab -> pop back to Pallet -> walk its remaining frontiers. General; it
        # only activates when the observation carries a place-graph (other worlds are unaffected).
        area = (obs.data.get("pose") or {}).get("area")
        d = self._cross_place(cur, cells, area, sm.get("place_portals") or [],
                              set(sm.get("place_frontiers") or []))
        if d:
            self.last_thought = f"area explored — cross to a place with frontiers via {d}"
            return self._move(d)
        # Out of frontiers everywhere reachable — now probe the walls here for an interactable.
        if self.probe_interactables:
            d = self._next_probe(cur, cells, sm.get("rois") or [])
            if d:
                self.last_thought = f"probe interactable -> {d}"
                return self._probe(d)
        self.last_thought = "no reachable frontier — area explored"
        return None

    def _next_probe(self, cur, cells, rois) -> Optional[str]:
        """Pick the next WALL direction at `cur` to probe for an interactable (each tried once). A wall
        pointing at a motion-detected ROI is probed FIRST (guided search). None when every wall here is
        already probed — truly stuck, so the LLM is woken."""
        walls = set(cells.get(cur, {}).get("walls", []))
        done = self._probed.setdefault(cur, set())
        cand = [d for d in ("up", "down", "left", "right") if d in walls and d not in done]
        if not cand:
            return None
        roiset = {tuple(r[:2]) for r in rois}
        # neighbour-in-ROI -> False sorts before True, so an ROI-pointing direction goes first
        cand.sort(key=lambda d: (cur[0] + _DELTA[d][0], cur[1] + _DELTA[d][1]) not in roiset)
        d = cand[0]
        done.add(d)
        return d

    def _cross_place(self, cur, cells, area, portals, frontier_places) -> Optional[str]:
        """Route OUT of an exhausted room toward a place that still has a frontier. Two-level: a BFS over
        the PLACE graph (portals) finds the nearest frontier-bearing place and the first door to head for;
        then a BFS within THIS room walks to that door, and once on it we press the crossing direction.
        Returns a direction to move, or None (no other place has a frontier / it's unreachable)."""
        if area is None or not portals or not frontier_places or area in frontier_places:
            return None
        hop = self._route_first_portal(area, portals, frontier_places)
        if hop is None:
            return None
        door, cross_dir = hop
        if cur != door:
            return self._bfs_first_step(cur, cells, {door})   # walk to the door (None if unreachable)
        return cross_dir                                      # on the door -> step through the portal

    @staticmethod
    def _route_first_portal(area, portals, frontier_places):
        """BFS over the place graph (portals = [place, [x,y], dir, dest]) from `area` to the nearest place
        in `frontier_places`. Returns (door_cell, cross_dir) for the FIRST hop out of `area`, or None."""
        from collections import deque
        adj: dict = {}
        for place, cell, d, dest in portals:
            adj.setdefault(place, []).append((dest, (cell[0], cell[1]), d))
        prev = {area: None}            # place -> (from_place, door_cell, cross_dir) used to reach it
        q = deque([area])
        target = None
        while q:
            p = q.popleft()
            if p != area and p in frontier_places:
                target = p
                break
            for dest, cell, d in adj.get(p, []):
                if dest not in prev:
                    prev[dest] = (p, cell, d)
                    q.append(dest)
        if target is None:
            return None
        node = target                  # walk the chain back to the hop whose source is `area`
        while prev[node] is not None and prev[node][0] != area:
            node = prev[node][0]
        if prev.get(node) is None:
            return None
        _src, door, cross_dir = prev[node]
        return (door, cross_dir)

    def _probe(self, d: str) -> ToolCall:
        # Face the adjacent tile, then press the confirm button: facing turns IN PLACE (no scroll -> no
        # odometry drift), then A interacts. A dialog/menu/battle on the next observation = that "wall"
        # was an interactable; nothing = it really was a wall.
        return _call("press_sequence", {"buttons": [d, "a"]}, self.agent_id)

    @staticmethod
    def _unexplored_dir(cur, cells) -> Optional[str]:
        walls = set(cells.get(cur, {}).get("walls", []))
        for d in ("up", "down", "left", "right"):
            if d in walls:
                continue
            dx, dy = _DELTA[d]
            nbr = cells.get((cur[0] + dx, cur[1] + dy))
            if nbr is None or not nbr.get("visited"):
                return d
        return None

    @staticmethod
    def _bfs_first_step(cur, cells, frontiers) -> Optional[str]:
        from collections import deque
        prev = {cur: None}
        q = deque([cur])
        while q:
            node = q.popleft()
            if node != cur and node in frontiers:
                path = [node]
                while prev[path[-1]] is not None:
                    path.append(prev[path[-1]])
                step = path[-2]  # first cell after cur on the path back
                dx, dy = step[0] - cur[0], step[1] - cur[1]
                return next((k for k, v in _DELTA.items() if v == (dx, dy)), None)
            walls = set(cells.get(node, {}).get("walls", []))
            for d in ("up", "down", "left", "right"):
                if d in walls:
                    continue
                dx, dy = _DELTA[d]
                nb = (node[0] + dx, node[1] + dy)
                if nb in cells and cells[nb].get("visited") and nb not in prev:
                    prev[nb] = node
                    q.append(nb)
        return None

    def _move(self, d: str) -> ToolCall:
        buttons = [d] if self.single_step else [d, d]   # one tile: [d] (real emu) or [d,d] (agnostic)
        return _call("press_sequence", {"buttons": buttons}, self.agent_id)


class HybridBrain:
    """Event-driven router (the cost win): run a free local autopilot by default, and WAKE an
    expensive brain (the LLM) only at real decisions —
      * a non-overworld mode (battle / menu / dialog), when perception reports `context != overworld`, or
      * the autopilot is stuck (no frontier left to explore).
    Dozens of free moves between rare LLM calls. `wake_rate` reports how often the expensive brain
    was actually needed. The mode trigger is dormant until perception sets `context` (the CV sub-step)."""

    def __init__(self, autopilot, fallback, replan_after: int = 5,
                 advance_on_dialog: bool = False, escalator=None) -> None:
        self.autopilot = autopilot
        self.fallback = fallback
        self.last_thought = ""
        self.woke = 0
        self.advanced = 0          # free dialog auto-advances (press A), not LLM wakes
        self._consec_advance = 0   # consecutive free auto-advances; trips the _ADVANCE_FUSE safety wake
        self.transcript: list = []  # dialog text auto-advanced past since the last wake (the missed text)
        self.total = 0
        self.mode = "autopilot"
        # feature #4 (dialog auto-advance): mash the world's confirm button through a PLAIN textbox for
        # free, waking the LLM only at a real choice (a 'menu'/'battle' context). Off by default so the
        # agnostic worlds/tests are unchanged; the Pokémon drivers turn it on. Pressing the confirm
        # button on plain text only advances/fast-forwards it (safe); the perceiver labels a textbox
        # that carries a selection box 'menu', so a YES/NO is never auto-mashed.
        self.advance_on_dialog = advance_on_dialog
        self.agent_id = (getattr(autopilot, "agent_id", None)
                         or getattr(fallback, "agent_id", None) or "agent")
        self.outcome = OutcomeMemory()   # feature #1: learn which actions do nothing here
        self.novelty = NoveltyMemory()   # seen-states signal: detect a cycling dialog (auto-advance gate)
        # General stuck-breaker (the seen-states principle, generalized past the dialog cycle gate): a
        # seen-set of non-overworld (signature, screen_text) states + a count of decisions since the last
        # NEW one. When it persists (a held stuck screen, e.g. the name-entry keyboard) the count climbs
        # and we hand System 2 the bare fact; real progress (new battle narration, a new menu) resets it.
        self._seen_states: set = set()
        self._since_novel = 0
        self._stuck = False
        self._consec_no_move = 0       # consecutive overworld decisions with a frozen pose (a wall-jam)
        self._last_pose = None
        # Perception escalation (optional, off by default so agnostic worlds/tests are unchanged): on a
        # STUCK wake, a strong VLM grounds the screen for the cheap agent. Pixels only; cached per state
        # + per-run capped (a healthy run never calls it). The Pokémon drivers wire one in. core/ stays
        # world-agnostic — the model call is injected (see core/vision_escalation.py).
        self.escalator = escalator
        self._cur_state_key = None     # (sig, screen_text) of the current frame — the escalator cache key
        self._last_sig = None
        self._last_action = None
        # feature #3: the disconfirm/surprise detector — when the agent makes no observable progress
        # for `replan_after` decisions (autopilot out of frontier, OR the LLM flailing in a dialog),
        # hand it a SURPRISE note that asks for a LESSON, instead of waking it to flail in silence
        # (the run-#1/#2 failure). Harness-owned, fresh per run, discarded at run end.
        self.replan_after = replan_after
        self.disconfirm = DisconfirmDetector(after=replan_after)
        # feature #2 (goto hookup): a destination the woken planner named, persisted so the FREE
        # autopilot drives there over the next overworld steps without re-waking the LLM each tile.
        self.goto: Optional[list] = None

    def decide(self, obs: Observation, tools: list[ToolSpec], context: dict) -> Optional[ToolCall]:
        self.total += 1
        sig = state_signature(obs.data)
        progressed = self._last_sig is not None and sig != self._last_sig
        ctx_label = obs.data.get("context") or "overworld"
        # Seen-states / novelty signal: while auto-advancing, are we moving through NOVEL text or
        # cycling back to a dialog state we've already visited (a textbox the confirm button can't
        # dismiss — Oak's "which POKEMON?")? Count VISITS to (signature, screen_text); observe(None)
        # on non-advanceable/empty frames so a state seen before and after a gap counts twice. Only
        # gates when auto-advance is on (else a dialog already wakes the LLM). See core/novelty.py.
        txt = (obs.data.get("screen_text") or "").strip()
        adv_ctx = ctx_label in ("dialog", "battle_text")
        nkey = (sig, txt) if (adv_ctx and txt) else None
        visits = self.novelty.observe(nkey)   # ALWAYS once per decide; observe(None) breaks a held run
        cycling = self.advance_on_dialog and nkey is not None and visits >= _CYCLE_REVISITS
        # General stuck-breaker: count consecutive NON-overworld decisions with no NEW (sig, screen_text)
        # state. A held stuck screen (the name-entry keyboard) keeps the same key -> the count climbs; a
        # new battle line / new menu is novel -> resets to 0 (so a real fight never trips). Overworld
        # 'stuck' is the autopilot/frontier's job, so it resets there. Keys on novelty, not the mode
        # label, so it works even though the keyboard mis-reads as 'battle'.
        if ctx_label == "overworld":
            self._since_novel = 0
        elif (sig, txt) in self._seen_states:
            self._since_novel += 1
        else:
            self._seen_states.add((sig, txt))
            self._since_novel = 0
        self._stuck = self._since_novel >= _STUCK_STALE
        self._cur_state_key = (sig, txt)   # escalator cache key: same stuck screen -> one VLM call
        # In a BATTLE the pose-based signature is frozen (the menu cursor isn't the world map), so every
        # turn looks like "no progress" even while the fight advances. Tallying that would mark the
        # confirm button (A — the primary battle action: advance text, pick FIGHT, choose a move) as a
        # dead/"avoid" action AND fire a spurious SURPRISE every few turns. So, like an auto-advanced
        # dialog, treat battle progress as invisible to this signature: don't tally it, keep the
        # no-progress streak clear. (Battle screens read as 'battle' — the action/move menus — or
        # 'battle_text' — auto-advanced narration; both are covered here.)
        if ctx_label in ("battle", "battle_text"):
            self.disconfirm.reset()
        else:
            if self._last_action is not None:  # grade the PREVIOUS action: did the situation change?
                self.outcome.record(self._last_sig, self._last_action, effective=progressed)
            # feed the disconfirm detector the same did-anything-change signal + the perceiver's
            # last_action outcome ('blocked' etc.), so a persistent no-progress streak raises a SURPRISE.
            self.disconfirm.record(progressed, obs.data.get("last_action"))
        # tell whoever decides which actions have repeatedly done nothing here, so it doesn't repeat them
        context = {**(context or {}), "avoid": self.outcome.dead_actions(sig)}

        # goto(target): consume it on arrival, else hand the persistent target to the free autopilot.
        pose = (obs.data.get("pose") or {}).get("value")
        # Repeated-no-move tracking: count consecutive OVERWORLD decisions where the pose did NOT change
        # (the agent keeps issuing moves but isn't going anywhere — a stale-wall-map jam). Reset whenever
        # it actually moves or leaves the overworld (a frozen pose during dialogue is legitimate).
        if ctx_label == "overworld" and pose is not None and pose == self._last_pose:
            self._consec_no_move += 1
        else:
            self._consec_no_move = 0
        self._last_pose = pose
        if self.goto is not None and pose is not None and list(pose) == list(self.goto):
            self.goto = None                          # arrived — destination reached, stop steering there
        if self.goto is not None:
            context["goto"] = self.goto               # the autopilot BFS-pathfinds toward it (free), else explores

        if ctx_label != "overworld":
            # Auto-advanceable = a PLAIN textbox ('dialog') OR battle NARRATION ('battle_text'): mash
            # the confirm button for FREE, waking the LLM only at a real choice (a 'menu'/'battle'
            # decision). The action/move menus stay 'battle' -> wake, so a move pick is never mashed.
            advanceable = self.advance_on_dialog and ctx_label in ("dialog", "battle_text")
            if advanceable and not cycling and self._consec_advance < _ADVANCE_FUSE:
                # advance it for FREE (no LLM). Auto-advancing IS progress (the story moves on) even
                # though the signature can't see it, so clear the no-progress streak.
                self.mode = "advance"
                self.advanced += 1
                self._consec_advance += 1
                self.disconfirm.reset()
                # `txt` (the screen text we're skipping past) was captured at the top of decide().
                # consecutive-dedup is deliberate: advancing text never shows the SAME line twice in a
                # row, so only the immediately-previous line can repeat (a held frame between A-presses).
                if txt and (not self.transcript or self.transcript[-1] != txt):
                    self.transcript.append(txt)
                    del self.transcript[:-_TRANSCRIPT_CAP]
                self.last_thought = "[auto-advance]"
                call = _call("press_button", {"button": "a"}, self.agent_id)
            else:
                # a real menu/battle decision, the CYCLE gate (we're revisiting a dialog state the
                # confirm button can't dismiss), OR the fuse tripped (a periodic look so an endless
                # free-advance loop can't run forever).
                why = "cycle" if cycling else ("fuse" if advanceable else "mode")
                self._consec_advance = 0
                call = self._wake(obs, tools, context, why)
        else:
            self._consec_advance = 0
            if self._consec_no_move >= _NO_MOVE_STALL:
                # the autopilot keeps issuing moves but the agent isn't going anywhere (a repeated
                # wall-jam on a stale/corrupt map — robust1's 243x 'right'). Don't let it repeat the dead
                # move; wake System 2 with a steering note to RE-ROUTE (what the successful runs did).
                self._consec_no_move = 0
                call = self._wake(obs, tools, context, "nomove")
            else:
                call = self.autopilot.decide(obs, tools, context)
                if call is not None:
                    self.mode = "autopilot"
                    self.last_thought = getattr(self.autopilot, "last_thought", "")
                else:
                    call = self._wake(obs, tools, context, "stuck")  # autopilot exhausted -> LLM
        self._last_sig = sig
        self._last_action = action_key(call)
        return call

    def _wake(self, obs, tools, context, why: str) -> Optional[ToolCall]:
        self.mode = "llm"
        self.woke += 1
        note = self.disconfirm.note()   # a persistent no-progress streak -> SURPRISE + ask for a LESSON
        if note:
            context = {**context, "surprise_note": note}
        if why == "cycle":   # seen-states signal: we're revisiting a dialog state the confirm button
            # can't dismiss. Hand System 2 the bare FACT — no suggested response (aria owns the
            # decision; keeps thin steering out of core/).
            context = {**context, "cycle_note":
                       "You are repeating a state you have already seen — your last action made no progress."}
        elif self._stuck:    # general stuck-breaker: PERSISTING on one screen with no new result (the
            # held case the cycle gate misses, e.g. the name-entry keyboard). Same bare-FACT seam.
            context = {**context, "stuck_note":
                       "Your last several actions on this screen produced no new result — you appear to be stuck on it."}
        if why == "nomove":  # repeated wall-jam: tried to move but the position hasn't changed. Bare FACT
            # + the one actionable hint (the wall map may be wrong) — System 2 re-routes (the escape the
            # successful runs found on their own).
            context = {**context, "nomove_note":
                       "You keep trying to move but your position hasn't changed — your wall map may be "
                       "stale or wrong. Try a DIFFERENT direction, or move toward a different open tile."}
        # Perception escalation: when stuck (cycling OR persisting), a strong VLM grounds the screen the
        # cheap perceiver mislabeled/under-read (System-1 escalation tier). Cached per state + capped.
        if self.escalator is not None and (why == "cycle" or self._stuck):
            hint = self.escalator.ground(obs.data.get("screen_path"), self._cur_state_key)
            if hint:
                context = {**context, "vision_hint": hint}
        if self.transcript:   # hand over (and clear) the dialog text the LLM auto-advanced past
            context = {**context, "transcript": " / ".join(self.transcript)}
            self.transcript = []
        call = self.fallback.decide(obs, tools, context)
        # If the planner named a destination this turn, adopt it — the free autopilot pursues it on
        # the next overworld steps (no GOTO = keep any target already in flight).
        named = getattr(self.fallback, "goto", None)
        if named is not None:
            self.goto = named
        tail = f" goto={self.goto}" if self.goto else ""
        lesson = getattr(self.fallback, "lesson", None)  # one-line lesson the LLM authored this wake
        ltail = f' lesson="{lesson}"' if lesson else ""
        self.last_thought = (f"[wake:{why}] "
                             f"{getattr(self.fallback, 'last_thought', '')}{tail}{ltail}").strip()
        return call

    @property
    def wake_rate(self) -> float:
        return self.woke / self.total if self.total else 0.0

    @property
    def consec_api_errors(self) -> int:
        """Forward the wrapped LLM brain's consecutive-error count, so the run driver's circuit breaker
        can halt a persistent backend outage (only the fallback actually calls the model)."""
        return getattr(self.fallback, "consec_api_errors", 0)

    @property
    def last_api_error(self) -> str:
        return getattr(self.fallback, "last_api_error", "")

    # Forward the wrapped LLM brain's token/cost meters so the driver's cost guardrails (per-wake
    # prompt-token cap, estimated-spend breaker) read the same numbers whether the brain is bare or
    # hybrid-wrapped (only the fallback actually calls the model). Mirrors consec_api_errors above.
    @property
    def last_prompt_tokens(self) -> int:
        return getattr(self.fallback, "last_prompt_tokens", 0)

    @property
    def total_prompt_tokens(self) -> int:
        return getattr(self.fallback, "total_prompt_tokens", 0)

    @property
    def total_completion_tokens(self) -> int:
        return getattr(self.fallback, "total_completion_tokens", 0)

    @property
    def total_cached_tokens(self) -> int:
        return getattr(self.fallback, "total_cached_tokens", 0)

    @property
    def total_cost_usd(self) -> float:
        # the cheap agent's spend PLUS any perception-escalation (strong-VLM) spend, so a single
        # --max-cost-usd cap bounds BOTH — escalation is not a separate untracked budget.
        base = getattr(self.fallback, "total_cost_usd", 0.0)
        esc = getattr(self.escalator, "total_cost_usd", 0.0) if self.escalator is not None else 0.0
        return base + esc


def _ollama_complete(model: str, url: str) -> Callable[[str, Optional[str]], str]:
    """Return a complete_fn(prompt, image_path) -> text backed by Ollama."""
    import requests

    def complete(prompt: str, image_path: Optional[str]) -> str:
        payload: dict = {"model": model, "prompt": prompt, "stream": False}
        if image_path:
            try:
                with open(image_path, "rb") as f:
                    payload["images"] = [base64.b64encode(f.read()).decode()]
            except OSError:
                pass
        r = requests.post(f"{url}/api/generate", json=payload, timeout=120)
        r.raise_for_status()
        return r.json().get("response", "")

    return complete


def _openai_complete(
    model: str, url: str, api_key: Optional[str] = None, system: Optional[str] = None
) -> Callable[[str, Optional[str]], str]:
    """complete_fn for an OpenAI-compatible /v1/chat/completions endpoint —
    e.g. llama.cpp's `llama-server` (run it with `--mmproj` for vision), or the
    decoupled `ai-aria` companion (POST :8001, bearer-authed, vision via data
    URIs). Also works with any OpenAI-shaped server. Images ride as base64 data
    URIs. Pass api_key to send an `Authorization: Bearer <key>` header.

    Returns (text, usage): the reply plus the response's `usage` block (prompt/completion/cached token
    counts) so the brain can meter spend (S1). The Ollama path and test stubs return a bare string;
    LLMButtonBrain normalizes both, so token metering is opt-in per backend without a protocol change.

    `system` (S2 constitution-first): when set, it is sent as a SYSTEM-role message rather than stapled
    into the user turn — so a constitution-aware brain (aria) can cache it in its static prefix once,
    instead of re-embedding + replaying it every wake (the ~7x duplication + sub-cache-floor cost). For
    a plain OpenAI server the system role is honoured natively; either way it's the right layer."""
    import requests

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None

    def complete(prompt: str, image_path: Optional[str]) -> tuple[str, dict]:
        content: list = [{"type": "text", "text": prompt}]
        if image_path:
            try:
                with open(image_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                content.append({"type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{b64}"}})
            except OSError:
                pass
        messages: list = []
        if system:   # the constitution rides a system-role message (cached prefix), not the user turn
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": content})
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "max_tokens": 128,   # room for THINK + MOVE + an optional GOTO and one-line LESSON
            "temperature": 0,
        }
        r = requests.post(f"{url}/v1/chat/completions", json=payload,
                          headers=headers, timeout=120)
        r.raise_for_status()
        body = r.json()
        return body["choices"][0]["message"]["content"], (body.get("usage") or {})

    return complete


# World-agnostic default. core/ knows nothing about any specific game; a world that wants a
# tailored prompt (Pokémon's turn-then-move + GOTO advice, the gating probe's neutral framing)
# injects its own via LLMButtonBrain(system=...). Only the THINK/MOVE contract is fixed, because
# _parse depends on it.
_DEFAULT_SYSTEM = (
    "You are an agent acting in a world through button presses. Choose the next input(s) from the "
    "observation below.\n"
    "Reply in EXACTLY this format and nothing else:\n"
    "THINK: <one short sentence — what you see and what you'll do>\n"
    "MOVE: <1-4 buttons separated by spaces, from: up down left right a b>"
)


class LLMButtonBrain:
    """LLM agent that picks one button per turn from the observation."""

    def __init__(
        self,
        agent_id: str,
        model: str = "llama3.2-vision",
        url: str = "http://localhost:11434",
        use_vision: bool = True,
        complete_fn: Optional[Callable[[str, Optional[str]], str]] = None,
        backend: str = "ollama",
        api_key: Optional[str] = None,
        system: Optional[str] = None,
        pricing: Optional[dict] = None,
        owns_memory: bool = False,
    ) -> None:
        self.agent_id = agent_id
        self.use_vision = use_vision
        # The system prompt is injectable so the SAME brain serves any world: the gating probe passes a
        # neutral framing (the leak control). core/ ships only a world-agnostic default — no game text.
        # Three cases: a non-empty string = use it; `None` = no constitution given -> the world-agnostic
        # default; `""` (empty) = the BACKEND owns its constitution (e.g. aria reads it from its own
        # config, ADR-001) -> send NOTHING from the harness. So an explicit "" must STAY empty.
        self.system = _DEFAULT_SYSTEM if system is None else system
        self.last_thought = ""       # the model's latest reasoning, for display
        self.goto: Optional[list] = None  # destination cell the planner named this turn (or None)
        self.lesson: Optional[str] = None  # one-line lesson the LLM authored THIS turn (or None)
        # `owns_memory` (S3 / beta): does the BACKEND keep its own durable, per-wake-reinjected memory?
        # World-agnostic — it's a property of the backend, not the game. When True (the decoupled aria
        # brain, set by its driver), the brain OWNS the within-run lesson store (its native <lesson> ->
        # lessons.md, re-read each turn), so the harness must NOT also keep + re-inject a duplicate
        # buffer. When False (ollama / a plain OpenAI server / an injected complete_fn / the gating
        # probe — no durable backend memory), the harness buffer below is the ONLY within-run lesson
        # store. The across-run boundary is then preserved differently per regime: False -> the buffer
        # is fresh per process; True -> reset_aria_memory.py wipes aria's store before each run.
        self.owns_memory = owns_memory
        # HARNESS-owned, per-run lesson buffer (learning-boundary law) — the within-run lesson store for
        # a MEMORYLESS backend (owns_memory=False). Lessons the LLM records via a plain `LESSON:` line
        # are kept here, re-injected on later wakes within this run, and discarded when the object dies
        # at run end. NOT aria's persistent <lesson>/lessons.md. Dormant when owns_memory=True (aria's
        # native memory is the store instead) — kept allocated so the attribute shape stays stable.
        self.lessons: list[str] = []
        self._last_pos = None        # (x, y) at the previous decision
        self._last_buttons = None    # what we pressed last, for wall-bump feedback
        self.consec_api_errors = 0   # consecutive failed model calls (circuit breaker; reset on a real reply)
        self.last_api_error = ""     # the most recent backend error detail, for the halt message
        # Token/cost metering (S1 cost-breaker). The OpenAI/aria backend returns a usage block; we
        # accumulate it so the drivers can enforce a per-wake prompt-token cap and an estimated-spend
        # ceiling (the true cost guard `--max-llm-calls` only approximates). `pricing` keeps the brain
        # model-agnostic — default Haiku-4.5 rates, override for another model.
        self.pricing = pricing or HAIKU_45_PRICING
        self.last_usage: dict = {}     # the most recent call's usage block ({} if the backend reports none)
        self.last_prompt_tokens = 0    # prompt tokens of the most recent wake (per-wake cap reads this)
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cached_tokens = 0
        self.total_cost_usd = 0.0      # running ESTIMATE of spend this run (usage x pricing)
        # Count model-call wakes so the driver's wake-watchdog (`--stuck-wakes`) works for `--brain llm`
        # too, where the brain is a BARE LLMButtonBrain (no HybridBrain). When wrapped, HybridBrain has
        # its own `woke` (the count the driver actually reads via the wrapper); this one is then unused.
        self.woke = 0
        # S2 (constitution-first): the OpenAI-family backends deliver `self.system` as a SYSTEM-role
        # message (so a constitution-aware brain caches it once), so `decide` must NOT also prepend it to
        # the user prompt. Ollama (no chat system role here) and an INJECTED complete_fn keep the old
        # inline delivery — backward-compatible (the test stubs see the system in the prompt as before).
        self._delivers_system = False
        if complete_fn is not None:
            self.complete = complete_fn
        elif backend == "ollama":
            self.complete = _ollama_complete(model, url)
        # `aria` is the decoupled ai-aria companion: same OpenAI wire format as
        # llamacpp/openai, but bearer-authed. It runs as its own service — we only
        # speak HTTP to it, importing none of its code.
        elif backend in ("llamacpp", "openai", "aria"):
            # Deliver the system prompt as a system-role message ONLY when one was EXPLICITLY provided
            # (the constitution case — the drivers pass POKEMON_SYSTEM). With no explicit system, keep
            # the _DEFAULT_SYSTEM fallback INLINE in the user prompt, so a plain openai/llamacpp caller's
            # wire format is unchanged (don't silently relocate a default into a system message).
            if system is not None:
                self.complete = _openai_complete(model, url, api_key=api_key, system=self.system)
                self._delivers_system = True
            else:
                self.complete = _openai_complete(model, url, api_key=api_key)
        else:
            raise ValueError(
                f"unknown LLM backend: {backend!r} (use 'ollama', 'llamacpp', or 'aria')")

    def decide(self, obs: Observation, tools: list[ToolSpec], context: dict) -> Optional[ToolCall]:
        # Cleared each turn so a model-call failure (early return below) can't leave the PREVIOUS
        # turn's destination/lesson looking "current" to HybridBrain — only THIS reply may set them.
        self.goto = None
        self.lesson = None
        self.woke += 1   # every decide() is one model-call wake (drives the wake-watchdog for --brain llm)
        strategy = context.get("strategy", "")  # KB-injected strategy doc, if any
        feedback = self._movement_feedback(obs)
        if not self.use_vision:
            # Text-only: no image is sent, so tell the model NOT to expect/ask for a screenshot — else
            # it wastes the turn ("I cannot see the screenshot you've attached", run #9) instead of
            # acting on the decoded on-screen text + state below.
            feedback = ("TEXT-ONLY MODE: no screenshot is provided — there is no image to look at. "
                        "Decide entirely from the decoded on-screen text and the state below; never "
                        "ask for or wait on an image.\n" + feedback).strip()
        avoid = context.get("avoid") or []      # actions that did nothing here (outcome memory)
        if avoid:
            feedback = (feedback + f"\nNOTE: these did NOTHING here, do NOT repeat them: "
                        f"{', '.join(avoid)}. Try something different.").strip()
        surprise = context.get("surprise_note")  # disconfirm/surprise nudge (HybridBrain detector)
        if surprise:
            feedback = (feedback + "\n" + surprise).strip()
        cycle = context.get("cycle_note")        # seen-states signal: cycling a state (HybridBrain detector)
        if cycle:
            feedback = (feedback + "\n" + cycle).strip()
        stuck = context.get("stuck_note")        # general stuck-breaker: persisting on a screen (HybridBrain)
        if stuck:
            feedback = (feedback + "\n" + stuck).strip()
        nomove = context.get("nomove_note")      # repeated wall-jam: tried to move, position unchanged
        if nomove:
            feedback = (feedback + "\n" + nomove).strip()
        vhint = context.get("vision_hint")       # perception escalation: a strong VLM's screen grounding
        if vhint:
            feedback = (feedback + "\nA closer look at the screen: " + vhint).strip()
        transcript = context.get("transcript")   # dialog text the harness auto-advanced past for you
        if transcript:
            feedback = (feedback + "\nText shown since your last decision (auto-advanced): "
                        + transcript).strip()
        # Belief-update re-grounding (agnostic-feature #4): when the screen carries decoded text, tell
        # the agent to trust the CURRENT screen over anything it assumed earlier — the run-#3 confab
        # was narrating "Bulbasaur received" while the screen said Squirtle. A harness-side text-match
        # can't do this (the decoder mangles the uppercase names it would need to compare), but the
        # model's own vision reads them — so we nudge it to let the observation overturn a prior belief.
        if (obs.data.get("screen_text") or "").strip():
            src = "the image and on-screen text show" if self.use_vision else "the on-screen text shows"
            feedback = (feedback + "\nTRUST THE SCREEN — this overrides memory: BEFORE you decide, state "
                        f"plainly what {src} RIGHT NOW. If that differs from "
                        "what you assumed or said on an earlier turn, you misread it earlier — the screen "
                        "wins: correct your belief and plan from what's shown now, and do NOT keep "
                        "narrating the old version.").strip()
        if self.lessons and not self.owns_memory:  # re-inject the harness buffer ONLY for a memoryless
            # backend; when owns_memory=True the brain (aria) re-injects its own lessons.md each turn, so
            # a second harness copy would duplicate it (the S3 retirement).
            feedback = (feedback + "\nLESSONS you recorded earlier THIS run (apply them):\n- "
                        + "\n- ".join(self.lessons)).strip()
        # The per-turn (volatile) content. When the backend delivers the constitution as a system-role
        # message (S2: openai/llamacpp/aria), DON'T also prepend self.system here — that would re-embed
        # it in the user turn (the duplication S2 removes). Ollama / an injected complete_fn keep it
        # inline (no system role on those paths), preserving the prior behaviour.
        body = (f"{strategy}\n{feedback}\n\nCurrent state:\n{obs.text}\n\nYour reply:")
        # Prepend self.system inline ONLY when it's non-empty AND the backend isn't delivering it as a
        # system message. Empty self.system (the backend owns its constitution, e.g. aria) -> send just
        # the observation body.
        prompt = body if (self._delivers_system or not self.system) else f"{self.system}\n\n{body}"
        image = obs.data.get("screen_path") if self.use_vision else None
        try:
            raw, usage = self._invoke(prompt, image)
        except Exception as e:
            self._note_api_error(f"{type(e).__name__}: {e}")   # network/HTTP raise
            self.last_usage, self.last_prompt_tokens = {}, 0    # no usage this wake — don't leave a stale value
            print(f"[LLMButtonBrain] model call failed ({e}); defaulting to 'a'")
            return _call("press_button", {"button": "a"}, self.agent_id)
        self._account(usage)   # meter tokens/cost for the spend guards (an error-as-content reply may
                               # still report usage, so account before the api-error check below)
        if _looks_like_api_error(raw):
            # aria echoes a backend error (e.g. credit-balance 400) as a 200 with the error as content,
            # so it doesn't raise. Count it toward the circuit breaker and DON'T parse it as a move.
            self._note_api_error((raw.strip().splitlines() or [""])[0][:200])
            self.last_thought = "[api-error] " + raw.strip()[:140]
            return _call("press_button", {"button": "a"}, self.agent_id)
        self.consec_api_errors = 0          # a real reply — the backend is healthy again
        buttons, thought = self._parse(raw)
        self.goto = self._parse_goto(raw)   # optional destination for the free autopilot (feature #2)
        self.lesson = self._parse_lesson(raw)  # parsed for the wake-log tail; stored only if owns_memory=False
        if self.lesson and not self.owns_memory and self.lesson.lower() not in [s.lower() for s in self.lessons]:
            self.lessons.append(self.lesson)   # dedup is whole-buffer + case-insensitive (not just
            del self.lessons[:-_LESSON_CAP]     # the last entry); keep most recent, re-injection cheap
        self.last_thought = thought or raw.strip()[:160]
        self._last_pos = (obs.data.get("x"), obs.data.get("y"))
        self._last_buttons = buttons
        if len(buttons) == 1:
            return _call("press_button", {"button": buttons[0]}, self.agent_id)
        return _call("press_sequence", {"buttons": buttons}, self.agent_id)

    def _invoke(self, prompt: str, image: Optional[str]) -> tuple[str, dict]:
        """Call the backend and normalize the reply to (text, usage). A complete_fn may return a bare
        string (Ollama, gateworld, test stubs) or a (text, usage) tuple (the OpenAI/aria path), so token
        metering is opt-in per backend without changing the complete_fn contract every caller relies on."""
        out = self.complete(prompt, image)
        if isinstance(out, tuple):
            raw, usage = out
            return raw, (usage or {})
        return out, {}

    def _account(self, usage: dict) -> None:
        """Record one call's token usage + estimated cost for the spend guardrails, and echo a per-call
        line to the console so spend is visible LIVE (S1). No-op (silent) when the backend reports no
        usage, so string-returning stubs/tests stay quiet."""
        self.last_usage = usage or {}
        self.last_prompt_tokens = self.last_usage.get("prompt_tokens") or 0
        if not self.last_usage:
            return
        ct = self.last_usage.get("completion_tokens") or 0
        details = self.last_usage.get("prompt_tokens_details") or {}
        cached = details.get("cached_tokens") or self.last_usage.get("cache_read_input_tokens") or 0
        cost = _estimate_cost(self.last_usage, self.pricing)
        self.total_prompt_tokens += self.last_prompt_tokens
        self.total_completion_tokens += ct
        self.total_cached_tokens += cached
        self.total_cost_usd += cost
        print(f"[tokens] prompt={self.last_prompt_tokens} (cached={cached}) completion={ct} "
              f"~${cost:.4f}  |  run {self.total_prompt_tokens} in / {self.total_completion_tokens} out "
              f"~${self.total_cost_usd:.3f}", flush=True)

    def _note_api_error(self, detail: str) -> None:
        """Record a failed model call for the circuit breaker (the driver halts at the threshold)."""
        self.consec_api_errors += 1
        self.last_api_error = detail

    def _movement_feedback(self, obs: Observation) -> str:
        """Tell the model when its previous move hit a wall (position unchanged). Skipped in
        perception mode (no RAM x/y) — the wall signal comes from the symbolic text instead."""
        if obs.data.get("x") is None:
            return ""
        pos = (obs.data.get("x"), obs.data.get("y"))
        dirs = {"up", "down", "left", "right"}
        if (self._last_pos is not None and pos == self._last_pos
                and self._last_buttons and set(self._last_buttons) & dirs):
            return (f"NOTE: your last move ({' '.join(self._last_buttons)}) did NOT "
                    f"move you — you walked into a wall. Pick a DIFFERENT direction.")
        return ""

    @staticmethod
    def _parse(raw: str, max_buttons: int = 4) -> tuple[list[str], str]:
        """Return (buttons, thought). When the model uses the THINK/MOVE format,
        buttons are taken only from the MOVE line — so direction words in the
        reasoning ('head down to the stairs') aren't mistaken for inputs. With no
        MOVE line (free-text reply) scan the reply, skipping tagged prose lines."""
        text = raw.strip()
        thought, move_src = "", None
        for line in text.splitlines():
            low = line.strip().lower()
            if low.startswith("think:"):
                thought = line.split(":", 1)[1].strip()
            elif low.startswith(("move:", "buttons:", "action:")):
                move_src = line.split(":", 1)[1]
        if move_src is not None:
            # The model used a MOVE line: trust ONLY it. Truncate at a GOTO/LESSON directive that got
            # concatenated onto the same line, so that line's prose ('LESSON: go down...') can't add
            # spurious button presses. A garbled/empty MOVE falls through to the safe 'a' default
            # below — we deliberately do NOT scan the reply's prose for buttons in this case.
            low = move_src.lower()
            cuts = [low.find(k) for k in ("goto:", "lesson:", "think:") if low.find(k) >= 0]
            if cuts:
                move_src = move_src[:min(cuts)]
            picks = [t for t in move_src.lower().replace(",", " ").split() if t in BUTTONS]
        else:
            # Free-text reply (no MOVE line): scan it for buttons, but skip tagged prose lines so a
            # direction word inside a THINK/LESSON/GOTO line isn't misread as an input.
            prose = ("think:", "lesson:", "goto:")
            scan = "\n".join(ln for ln in text.splitlines()
                             if not ln.strip().lower().startswith(prose))
            picks = [t for t in scan.lower().replace(",", " ").split() if t in BUTTONS]
        return picks[:max_buttons] or ["a"], thought  # 'a' = safe default

    @staticmethod
    def _parse_goto(raw: str) -> Optional[list]:
        """Optional 'GOTO: x y' (or 'x,y') line -> [x, y]; None if absent/garbled. This is the
        planner naming a destination cell once; HybridBrain persists it and the local autopilot
        pathfinds there for free (no per-tile LLM calls). Only read from a dedicated GOTO line so
        coordinates mentioned in prose ('go to the door') aren't mistaken for a target."""
        for line in raw.splitlines():
            if line.strip().lower().startswith("goto:"):
                nums = re.findall(r"-?\d+", line.split(":", 1)[1])
                if len(nums) >= 2:
                    return [int(nums[0]), int(nums[1])]
        return None

    @staticmethod
    def _parse_lesson(raw: str) -> Optional[str]:
        """Optional 'LESSON: <text>' line -> the lesson text (None if absent/empty). A plain line
        the HARNESS captures into a per-run buffer it re-injects within the run and discards at run
        end — deliberately NOT aria's <lesson> tag, which would persist to lessons.md across runs and
        break the learning-boundary law. Only the first LESSON line is taken; the placeholder the
        prompt shows ('<one short lesson>') is ignored so an un-filled template doesn't get stored."""
        for line in raw.splitlines():
            if line.strip().lower().startswith("lesson:"):
                text = line.split(":", 1)[1].strip()
                if text and not (text.startswith("<") and text.endswith(">")):
                    return text
        return None
