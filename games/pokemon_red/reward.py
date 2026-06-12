"""Reward shaping for Pokémon Red.

There is no score in the cartridge, so we synthesize one from state deltas:
progress (badges), growth (party levels), and curiosity (newly seen maps).
This is exactly the signal an RL agent would optimize, and a readable
proxy for "is the LLM agent actually making progress" in the runner log.

Per invariant 12 the reward the plugin emits is a single scalar; the
breakdown rides along in Event.data for anyone who wants it.
"""

from __future__ import annotations

# Weights are deliberately blunt; tune per experiment.
W_BADGE = 10.0      # a gym badge is the densest real progress signal
W_LEVEL = 0.5       # each party level gained
W_NEW_MAP = 1.0     # first time we set foot on a map id (exploration)
W_FAINT = -0.5      # party HP collapsing to ~0 (blacked out / wiped)


class RewardTracker:
    """Stateful between steps: holds the baseline to diff the next state against."""

    def __init__(self) -> None:
        self._prev: dict | None = None
        self._seen_maps: set[int] = set()

    def reset_baseline(self, state: dict) -> None:
        self._prev = state
        self._seen_maps = {state.get("map_id", -1)}

    def update(self, state: dict) -> tuple[float, dict]:
        """Return (scalar_reward, breakdown) for the transition into `state`."""
        if self._prev is None:
            self.reset_baseline(state)
            return 0.0, {"reason": "baseline"}

        prev = self._prev
        breakdown: dict[str, float] = {}

        d_badges = state.get("badges", 0) - prev.get("badges", 0)
        if d_badges:
            breakdown["badges"] = W_BADGE * d_badges

        d_level = state.get("party_level_sum", 0) - prev.get("party_level_sum", 0)
        if d_level > 0:  # levels never legitimately drop
            breakdown["levels"] = W_LEVEL * d_level

        map_id = state.get("map_id", -1)
        if map_id not in self._seen_maps:
            self._seen_maps.add(map_id)
            breakdown["new_map"] = W_NEW_MAP

        # Wipe-out heuristic: had HP last step, ~none now.
        if prev.get("party_hp_sum", 0) > 0 and state.get("party_hp_sum", 0) == 0:
            breakdown["faint"] = W_FAINT

        self._prev = state
        total = float(sum(breakdown.values()))
        return total, breakdown

    @property
    def maps_seen(self) -> int:
        return len(self._seen_maps)
