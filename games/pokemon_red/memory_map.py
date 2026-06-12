"""Curated Pokémon Red (US/EN) WRAM map → structured agent state.

These addresses come from the `pokered` disassembly and are the same set
Peter Whidden's PokemonRedExperiments uses; they are battle-tested but
ROM-revision specific. A wrong address yields wrong *telemetry*, not a
crash — so if a field looks bogus, suspect the address before the reader.

Everything here is pure: it reads through a `read(addr) -> int` callable
and returns plain JSON-serializable Python. No PyBoy import lives in this
module, which is what lets the plugin's logic be unit-tested with a fake
memory and no ROM (see tests/test_pokemon_red.py).
"""

from __future__ import annotations

from typing import Callable

ReadFn = Callable[[int], int]

# --- Single-byte / coordinate state -----------------------------------------
ADDR_IS_IN_BATTLE = 0xD057   # 0 = overworld, 1 = wild battle, 2 = trainer battle
ADDR_MAP_ID = 0xD35E         # current map (route/town/building id)
ADDR_X = 0xD362              # player X tile within the current map
ADDR_Y = 0xD361              # player Y tile within the current map
ADDR_BADGES = 0xD356         # bitfield; popcount = number of badges earned
ADDR_MONEY = 0xD347          # 3 bytes, big-endian BCD (e.g. 0x01 0x23 0x45 = 12345)

# --- Party block ------------------------------------------------------------
ADDR_PARTY_COUNT = 0xD163    # number of Pokémon in the party (0..6)
ADDR_PARTY_MON1 = 0xD16B     # start of the first party-mon struct
PARTY_MON_STRIDE = 0x2C      # 44 bytes per mon
OFF_SPECIES = 0x00           # internal species index (NOT the Pokédex number)
OFF_CUR_HP = 0x01            # u16, big-endian
OFF_STATUS = 0x04            # status-condition bitfield
OFF_LEVEL = 0x21             # current level
OFF_MAX_HP = 0x22            # u16, big-endian
MAX_PARTY = 6


def read_u16_be(read: ReadFn, addr: int) -> int:
    """Two consecutive bytes, big-endian — the Game Boy CPU's word order here."""
    return (read(addr) << 8) | read(addr + 1)


def popcount(byte: int) -> int:
    return bin(byte & 0xFF).count("1")


def bcd3_to_int(b0: int, b1: int, b2: int) -> int:
    """Pokémon money is 3 binary-coded-decimal bytes (each nibble a digit)."""
    digits = 0
    for b in (b0, b1, b2):
        digits = digits * 100 + (((b >> 4) & 0xF) * 10) + (b & 0xF)
    return digits


def read_party(read: ReadFn) -> list[dict]:
    """Return one dict per party member with the fields a brain actually uses."""
    count = min(read(ADDR_PARTY_COUNT), MAX_PARTY)
    party = []
    for i in range(count):
        base = ADDR_PARTY_MON1 + i * PARTY_MON_STRIDE
        party.append(
            {
                "species_id": read(base + OFF_SPECIES),  # raw internal index
                "level": read(base + OFF_LEVEL),
                "hp": read_u16_be(read, base + OFF_CUR_HP),
                "max_hp": read_u16_be(read, base + OFF_MAX_HP),
                "status": read(base + OFF_STATUS),
            }
        )
    return party


def read_state(read: ReadFn) -> dict:
    """The canonical structured snapshot handed to brains as Observation.data.

    JSON-only (invariant 3): no tensors, no PyBoy handles. The screen image
    is added by the plugin as a *path*, not pixels.
    """
    party = read_party(read)
    return {
        "in_battle": read(ADDR_IS_IN_BATTLE),
        "map_id": read(ADDR_MAP_ID),
        "x": read(ADDR_X),
        "y": read(ADDR_Y),
        "badges": popcount(read(ADDR_BADGES)),
        "badge_flags": read(ADDR_BADGES) & 0xFF,
        "money": bcd3_to_int(read(ADDR_MONEY), read(ADDR_MONEY + 1), read(ADDR_MONEY + 2)),
        "party_count": len(party),
        "party": party,
        "party_level_sum": sum(p["level"] for p in party),
        "party_hp_sum": sum(p["hp"] for p in party),
    }
