"""Pokémon Red plugin tests — run with NO ROM and NO PyBoy.

The emulator is dependency-injected, so a tiny in-memory FakeEmulator exercises
every code path: state parsing, error-as-observation, reward shaping, the
gateway's permission veto, and a full runner episode. (A real-ROM integration
test is intentionally omitted — it needs a copyrighted ROM the project never
ships.)
"""

from __future__ import annotations

import pytest

from core.brains import ScriptedBrain
from core.gateway import Gateway
from core.permissions import Allowlist
from core.runner import run_episode
from games.pokemon_red import POKEMON_SANDBOX, POKEMON_SYSTEM
from games.pokemon_red import memory_map as mm
from games.pokemon_red.plugin import PokemonRedPlugin


class FakeEmulator:
    """RAM-backed stand-in for PyBoy. Tests poke `mem` to simulate the game."""

    def __init__(self) -> None:
        self.mem: dict[int, int] = {}
        self._frame = 0
        self._screen = None  # set to an ndarray to drive the perception path
        self.settles = 0     # count of settle() calls (battle-pacing wiring assertion)
        self._faded = False  # set True to simulate a press that crossed a map-warp fade

    def press(self, button, hold_frames=8, settle_frames=16):
        self._frame += hold_frames + settle_frames

    def tick(self, frames):
        self._frame += frames

    def settle(self, max_frames=240):
        self.settles += 1
        return True

    def faded(self):
        return self._faded

    def read(self, addr):
        return self.mem.get(addr, 0)

    def save_screen(self, path):
        with open(path, "wb") as f:
            f.write(b"")  # empty PNG placeholder is enough for the path contract

    def screen_ndarray(self):
        import numpy as np
        return self._screen if self._screen is not None else np.zeros((144, 160, 4), dtype="uint8")

    def load_state(self, path):
        self.loaded = path

    def save_state(self, path):
        self.saved = path

    @property
    def frame(self):
        return self._frame

    def close(self):
        pass


def _seed_party_mon1(emu: FakeEmulator):
    emu.mem[mm.ADDR_PARTY_COUNT] = 1
    base = mm.ADDR_PARTY_MON1
    emu.mem[base + mm.OFF_SPECIES] = 153
    emu.mem[base + mm.OFF_CUR_HP] = 0x00
    emu.mem[base + mm.OFF_CUR_HP + 1] = 0x14  # 20
    emu.mem[base + mm.OFF_LEVEL] = 12
    emu.mem[base + mm.OFF_MAX_HP] = 0x00
    emu.mem[base + mm.OFF_MAX_HP + 1] = 0x18  # 24


# -- prompt: lesson channel (S3 beta — harness channel retired) ---------------

def test_pokemon_system_no_harness_lesson_channel_under_beta():
    # S3 beta: the harness no longer advertises a plain `LESSON:` line — aria owns within-run memory and
    # teaches its own <lesson> tag (stripped server-side, so THINK/MOVE parsing is untouched).
    assert "LESSON:" not in POKEMON_SYSTEM                  # harness plain-text channel retired
    assert "<lesson>" not in POKEMON_SYSTEM.lower()         # the harness prompt must NOT teach the tag either
    # The muzzle stays lifted (so aria can emit its tags around the reply); THINK/MOVE still required.
    assert "nothing else" not in POKEMON_SYSTEM
    assert "THINK:" in POKEMON_SYSTEM and "MOVE:" in POKEMON_SYSTEM and "GOTO:" in POKEMON_SYSTEM


def test_pokemon_system_has_battle_guidance():
    # Battle policy v2 (run-#6b fixes): the prompt must teach picking a DAMAGING move (not mashing A
    # into a non-damaging status move like GROWL) and reading the screen to name your Pokémon + the foe.
    low = POKEMON_SYSTEM.lower()
    assert "battle" in low
    assert "fight" in low                      # the action-menu option to attack with
    assert "damage" in low                     # pick a move that DEALS DAMAGE...
    assert "growl" in low                      # ...not a non-damaging status move (the run-#6b trap)
    assert "mash a" in low                     # explicit: do NOT just mash A


# -- battle pacing: settle a battle animation before observing -----------------

def _battle_frame():
    import numpy as np
    f = np.full((144, 160, 3), 60, dtype=np.uint8)
    f[:58, :] = 255      # white HP boxes (top)
    f[96:, :] = 255      # white action/text box (bottom)
    return f


def test_advance_until_static_settles_when_animation_stops():
    import numpy as np
    from games.pokemon_red.emulator import advance_until_static
    a = np.zeros((4, 4, 3), dtype=np.uint8)
    b = np.full((4, 4, 3), 200, dtype=np.uint8)
    seq = [a, b, a, b] + [a] * 30            # animating, then static
    it = iter(seq)
    settled, pulled = advance_until_static(lambda: next(it, seq[-1]),
                                           max_frames=200, window=10, eps=2.0)
    assert settled is True
    assert pulled < 200                       # stopped early once it went static


def test_advance_until_static_caps_when_never_static():
    import numpy as np
    from games.pokemon_red.emulator import advance_until_static
    flip = [np.zeros((4, 4, 3), np.uint8), np.full((4, 4, 3), 200, np.uint8)]
    n = {"i": 0}
    def nxt():
        n["i"] += 1
        return flip[n["i"] % 2]               # perpetual animation
    settled, pulled = advance_until_static(nxt, max_frames=50, window=10, eps=2.0)
    assert settled is False and pulled == 50


def test_advance_until_static_tolerates_cursor_blink():
    # A blinking cursor (one tiny tile toggling) must NOT reset the streak — the screen is still
    # "waiting for input". Simulate a sub-eps periodic flicker on an otherwise static screen.
    import numpy as np
    from games.pokemon_red.emulator import advance_until_static
    base = np.full((144, 160, 3), 100, dtype=np.uint8)
    blink = base.copy(); blink[112:120, 8:16] = 130   # one 8x8 tile, small delta
    seq = [base, blink, base, blink, base, base, base, base, base, base, base, base]
    it = iter(seq)
    settled, _ = advance_until_static(lambda: next(it, base), max_frames=100, window=8, eps=2.0)
    assert settled is True


def test_advance_until_static_eps_is_strict_not_inclusive():
    # A diff exactly == eps must NOT count as static (the code uses `< eps`). Guards against a future
    # `<=` typo that would read a constant eps-sized animation as "settled".
    import numpy as np
    from games.pokemon_red.emulator import advance_until_static
    a = np.zeros((4, 4, 3), dtype=np.uint8)
    b = np.full((4, 4, 3), 2, dtype=np.uint8)        # mean abs diff a<->b == 2.0 == eps
    it = iter([a, b] * 40)
    settled, pulled = advance_until_static(lambda: next(it, a), max_frames=40, window=8, eps=2.0)
    assert settled is False and pulled == 40          # never settles: each diff == eps, not < eps


def test_advance_until_static_none_frame_does_not_break_streak():
    # A None frame (emulator returned nothing this tick) skips that diff without resetting the streak
    # and without crashing — the static run resumes across the gap.
    import numpy as np
    from games.pokemon_red.emulator import advance_until_static
    s = np.full((4, 4, 3), 100, dtype=np.uint8)
    seq = [s, s, s, None, s, s, s, s, s, s]           # static, with one None hole partway
    it = iter(seq)
    settled, _ = advance_until_static(lambda: next(it, s), max_frames=50, window=6, eps=2.0)
    assert settled is True


def test_advance_until_static_requires_a_full_window():
    # Exactly `window` sub-eps diffs are needed; the first pulled frame has no predecessor to diff,
    # so settling happens on pull window+1. Pins the `>= window` threshold against an off-by-one.
    import numpy as np
    from games.pokemon_red.emulator import advance_until_static
    base = np.full((8, 8, 3), 70, dtype=np.uint8)
    it = iter([base] * 50)
    settled, pulled = advance_until_static(lambda: next(it, base), max_frames=50, window=5, eps=2.0)
    assert settled is True and pulled == 6            # 1 priming pull + 5 stable diffs


def test_battle_screen_settles_before_observe(tmp_path):
    # In battle, an action must trigger emulator.settle() so the agent observes a stable screen.
    p, emu = _plugin(tmp_path)
    emu._screen = _battle_frame()
    p.handle(_tc("press_button", {"button": "a"}))
    assert emu.settles == 1


def test_overworld_action_does_not_settle(tmp_path):
    # Outside battle, settling would needlessly slow the free autopilot — it must NOT fire.
    p, emu = _plugin(tmp_path)
    emu._screen = None                         # default zeros frame -> detect_mode == overworld
    p.handle(_tc("press_button", {"button": "down"}))
    assert emu.settles == 0


# -- memory map ---------------------------------------------------------------

def test_bcd_and_popcount():
    assert mm.bcd3_to_int(0x00, 0x30, 0x00) == 3000
    assert mm.bcd3_to_int(0x01, 0x23, 0x45) == 12345
    assert mm.popcount(0b00000011) == 2
    assert mm.popcount(0xFF) == 8


def test_read_state_parses_party_and_fields():
    emu = FakeEmulator()
    _seed_party_mon1(emu)
    emu.mem[mm.ADDR_MAP_ID] = 12
    emu.mem[mm.ADDR_X] = 4
    emu.mem[mm.ADDR_Y] = 7
    emu.mem[mm.ADDR_BADGES] = 0b00000001  # 1 badge
    emu.mem[mm.ADDR_MONEY] = 0x00
    emu.mem[mm.ADDR_MONEY + 1] = 0x30
    emu.mem[mm.ADDR_MONEY + 2] = 0x00

    s = mm.read_state(emu.read)
    assert s["map_id"] == 12 and s["x"] == 4 and s["y"] == 7
    assert s["badges"] == 1 and s["money"] == 3000
    assert s["party_count"] == 1
    assert s["party"][0] == {"species_id": 153, "level": 12, "hp": 20,
                             "max_hp": 24, "status": 0}
    assert s["party_level_sum"] == 12 and s["party_hp_sum"] == 20


# -- plugin: errors are observations -----------------------------------------

def _plugin(tmp_path):
    emu = FakeEmulator()
    p = PokemonRedPlugin(emulator=emu, out_dir=str(tmp_path))
    return p, emu


def test_invalid_button_is_observation_not_exception(tmp_path):
    p, _ = _plugin(tmp_path)
    res = p.handle(_tc("press_button", {"button": "z"}))
    assert res.ok is False
    assert "invalid button" in res.error
    assert set(res.data["valid_buttons"]) >= {"a", "b", "up", "down"}


def test_unknown_tool_is_observation(tmp_path):
    p, _ = _plugin(tmp_path)
    res = p.handle(_tc("teleport", {}))
    assert res.ok is False and "unknown tool" in res.error


def test_valid_press_returns_ok_and_emits_event(tmp_path):
    p, _ = _plugin(tmp_path)
    res = p.handle(_tc("press_button", {"button": "a"}))
    assert res.ok is True and res.data["action"] == "a"
    types = [e.type for e in p.drain_events()]
    assert "tool_called" in types


def test_init_state_is_loaded_before_baseline(tmp_path):
    emu = FakeEmulator()
    PokemonRedPlugin(emulator=emu, out_dir=str(tmp_path), init_state="start.state")
    assert emu.loaded == "start.state"


def test_save_state_delegates_to_emulator(tmp_path):
    p, emu = _plugin(tmp_path)
    p.save_state("final.state")
    assert emu.saved == "final.state"


def test_observe_writes_screen_path_and_text(tmp_path):
    p, emu = _plugin(tmp_path)
    _seed_party_mon1(emu)
    obs = p.observe("agent-x")
    assert obs.data["screen_path"].endswith(".png")
    assert "Pokémon Red" in obs.text
    assert obs.data["party"][0]["level"] == 12


# -- reward shaping -----------------------------------------------------------

def test_badge_gain_rewards_and_emits_badge_event(tmp_path):
    p, emu = _plugin(tmp_path)  # baseline: 0 badges
    emu.mem[mm.ADDR_BADGES] = 0b00000001  # earn one
    res = p.handle(_tc("press_button", {"button": "a"}))
    assert res.data["reward"] == pytest.approx(10.0)
    assert "badge_earned" in [e.type for e in p.drain_events()]


def test_new_map_gives_exploration_reward(tmp_path):
    p, emu = _plugin(tmp_path)  # baseline map 0
    emu.mem[mm.ADDR_MAP_ID] = 5
    res = p.handle(_tc("press_button", {"button": "up"}))
    assert res.data["reward"] == pytest.approx(1.0)


# -- gateway ------------------------------------------------------------------

def test_gateway_rejects_unknown_tool(tmp_path):
    p, _ = _plugin(tmp_path)
    gw = Gateway(p, POKEMON_SANDBOX)
    res = gw.execute(_tc("fly_away", {}))
    assert res.ok is False and "unknown tool" in res.error


def test_gateway_permission_denies_out_of_sandbox(tmp_path):
    p, _ = _plugin(tmp_path)
    gw = Gateway(p, Allowlist({"wait"}))  # press_button NOT allowed
    res = gw.execute(_tc("press_button", {"button": "a"}))
    assert res.ok is False and "denied" in res.error


def test_gateway_passes_allowed_call(tmp_path):
    p, _ = _plugin(tmp_path)
    gw = Gateway(p, POKEMON_SANDBOX)
    res = gw.execute(_tc("press_button", {"button": "a"}))
    assert res.ok is True and res.cost_charged == 1


# -- runner episode -----------------------------------------------------------

def test_full_episode_runs_with_scripted_brain(tmp_path):
    p, _ = _plugin(tmp_path)
    gw = Gateway(p, POKEMON_SANDBOX)
    brain = ScriptedBrain("agent-1", seed=42)
    summary = run_episode(gw, p, brain, "agent-1", max_steps=8)
    assert summary["steps"] == 8
    assert summary["event_counts"].get("tool_called") == 8


# -- helpers ------------------------------------------------------------------

def _tc(tool, args):
    from core.contracts import ToolCall
    return ToolCall(tool=tool, args=args, agent_id="agent-1", call_id="call-1")
