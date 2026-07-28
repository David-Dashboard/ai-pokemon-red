"""Derive Emerald's map identity table straight out of the ROM — no network, no symbol file.

Anchoring argument (this is the part that makes the derivation evidence rather than recall):
  1. `gMapHeader` is a FIXED EWRAM global at 0x02037318 (BSS, not in a relocating save block).
     A live dump of it while standing in outdoor Littleroot Town gives four ROM pointers
     (mapLayout / events / mapScripts / connections).
  2. Those 16 bytes occur EXACTLY ONCE in the ROM -> that address is Littleroot's MapHeader.
  3. Exactly one u32 in the ROM points at that MapHeader -> that word is `gMapGroups[0][9]`,
     which pins the group-0 header-pointer table (and therefore Littleroot = map (0, 9)).
  4. From there the connection lists and the whole 34-group / 518-map table are walkable, and the
     regionMapSectionId of every map in the game can be read.

ASSUMED, NOT DERIVED (pokeemerald domain knowledge baked in below — stated so the derivation is not
mistaken for assumption-free): Littleroot is map number 9 of group 0; MapHeader field offsets
(mapsec +0x14, map_type +0x17); the 12-byte MapConnection stride; and the `0x08480000..0x08490000`
window used to find the end of the group table (so the map census is only as complete as that
bound). The two `assert len(...) == 1` checks and the mapsec-0 census matching the six
live-visited Littleroot maps are what corroborate these.

Run: python rom_maps.py "<path to Pokemon - Emerald Version (U).gba>"
"""
import struct
import sys

BASE = 0x08000000
DIRS = {1: "S", 2: "N", 3: "W", 4: "E", 5: "DIVE", 6: "EMERGE"}

# Live-dumped gMapHeader pointer quad for outdoor Littleroot Town (probe anchor `out_gap`,
# and identical in all six outdoor anchors) -- see reports/2026-07-28-emerald-oldale-oracle.md.
LITTLEROOT_LIVE_PTRS = (0x083EA284, 0x08527840, 0x081E7DCB, 0x0848660C)


def main(path):
    rom = open(path, "rb").read()
    u32 = lambda a: struct.unpack_from("<I", rom, a - BASE)[0]
    s32 = lambda a: struct.unpack_from("<i", rom, a - BASE)[0]

    sig = struct.pack("<IIII", *LITTLEROOT_LIVE_PTRS)
    hits = [BASE + i for i in range(0, len(rom) - 16, 4) if rom[i:i + 16] == sig]
    assert len(hits) == 1, f"expected a unique MapHeader match, got {hits}"
    hdr = hits[0]
    refs = [BASE + i for i in range(0, len(rom) - 4, 4)
            if struct.unpack_from("<I", rom, i)[0] == hdr]
    assert len(refs) == 1, f"expected a unique pointer-table entry, got {refs}"
    g0 = refs[0] - 9 * 4                       # Littleroot is map number 9 of group 0
    gmaps = [BASE + i for i in range(0, len(rom) - 4, 4)
             if struct.unpack_from("<I", rom, i)[0] == g0]
    assert len(gmaps) == 1
    gmaps = gmaps[0]

    def header(a):
        o = a - BASE
        lay, ev, scr, con = struct.unpack_from("<IIII", rom, o)
        music, layout_id = struct.unpack_from("<HH", rom, o + 0x10)
        return dict(conn=con, music=music, layout_id=layout_id, mapsec=rom[o + 0x14],
                    map_type=rom[o + 0x17])

    def connections(ptr):
        if not ptr:
            return []
        cnt, arr = s32(ptr), u32(ptr + 4)
        return [(DIRS.get(rom[arr - BASE + 12 * i], rom[arr - BASE + 12 * i]),
                 struct.unpack_from("<i", rom, arr - BASE + 12 * i + 4)[0],
                 rom[arr - BASE + 12 * i + 8], rom[arr - BASE + 12 * i + 9])
                for i in range(cnt)]

    groups = []
    a = gmaps
    while 0x08480000 <= u32(a) <= 0x08490000:
        groups.append(u32(a))
        a += 4

    print(f"gMapGroups @ {gmaps:#x}, {len(groups)} groups")
    print("\n-- walk from Littleroot along map connections --")
    for num in (9, 16, 10):
        h = header(u32(g0 + 4 * num))
        print(f"  map (0,{num:2}) layoutId={h['layout_id']:3} mapsec={h['mapsec']:3} "
              f"type={h['map_type']} conns={connections(h['conn'])}")

    by_sec = {}
    total = 0
    for gi, gstart in enumerate(groups):
        gend = groups[gi + 1] if gi + 1 < len(groups) else gmaps
        for num in range((gend - gstart) // 4):
            hp = u32(gstart + 4 * num)
            if not (BASE <= hp < 0x09000000):
                continue
            total += 1
            by_sec.setdefault(rom[hp - BASE + 0x14], []).append((gi, num))

    print(f"\n-- regionMapSectionId census over all {total} maps --")
    for sec, label in ((0, "LITTLEROOT_TOWN"), (1, "OLDALE_TOWN"), (16, "ROUTE_101")):
        maps = by_sec.get(sec, [])
        print(f"  mapsec {sec:3} ({label:15}): {len(maps)} maps -> {maps}")


if __name__ == "__main__":
    main(sys.argv[1])
