"""Cardinal-grid primitives shared by the occupancy-grid perceivers (world-agnostic).

Tiny and pure: the four cardinal directions, their unit deltas, the opposite-direction map, and the
two translations between the ego cardinal tokens (`east`/`west`/`south`/`north`, from
`core.egomotion.direction`) and the grid direction names (`right`/`left`/`down`/`up`). Lifted out of
the per-game perceivers the second time they were needed (the toolkit-of-primitives discipline);
games import these instead of copying them.
"""
from __future__ import annotations

DIRS = ("up", "down", "left", "right")
DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
BACK = {"up": "down", "down": "up", "left": "right", "right": "left"}
EGO2DIR = {"east": "right", "west": "left", "south": "down", "north": "up"}  # ego token -> grid dir
DIR2EGO = {"right": "east", "left": "west", "down": "south", "up": "north"}  # grid dir -> ego token
