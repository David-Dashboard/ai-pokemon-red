"""Sweep the 12 anchor dumps for a fixed-address 'where am I' byte.

OUT   = 6 states, ALL the same outdoor Littleroot Town map, 6 different standing positions
        reached through 4 different doors.
IN    = 5 different interior maps of the same town + the intro truck (different region).

A genuine CURRENT-MAP byte must be bit-identical across every OUT state and must take a
different value on each interior map.
A genuine REGION/MAPSEC byte must be bit-identical across OUT + all 5 Littleroot interiors.
"""
import sys, os

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dumps")
OUT = ["out_truck", "out_ownhouse", "out_north", "out_labdoor", "out_nw", "out_gap"]
INT = ["house1f", "bed2f", "may1f", "may2f", "lab"]
TRUCK = "truck"


def load(tag, region):
    with open(os.path.join(D, f"A_{tag}.{region}.bin"), "rb") as f:
        return f.read()


def sweep(region, base):
    out = [load(t, region) for t in OUT]
    ins = [load(t, region) for t in INT]
    truck = load(TRUCK, region)
    n = len(out[0])
    map_ids, region_ids = [], []
    for i in range(n):
        v = out[0][i]
        if any(o[i] != v for o in out[1:]):
            continue                       # not stable within the one outdoor map
        iv = [x[i] for x in ins]
        # current-map candidate: distinct on every interior AND different from outdoors
        if len(set(iv + [v])) == len(iv) + 1:
            map_ids.append((base + i, v, iv, truck[i]))
        # region candidate: same on outdoors + every Littleroot interior, different in the truck
        if all(x == v for x in iv) and truck[i] != v:
            region_ids.append((base + i, v, truck[i]))
    return map_ids, region_ids


for region, base in (("ewram", 0x02000000), ("iwram", 0x03000000)):
    m, r = sweep(region, base)
    print(f"=== {region} ===")
    print(f"CURRENT-MAP candidates (stable across 6 outdoor states, unique per interior): {len(m)}")
    for a, v, iv, t in m[:40]:
        print(f"   {hex(a)} out={v} interiors={iv} truck={t}")
    print(f"REGION candidates (same on outdoor+5 Littleroot interiors, differs in truck): {len(r)}")
    for a, v, t in r[:60]:
        print(f"   {hex(a)} littleroot={v} truck={t}")
