"""Uniqueness + value-trace analysis for the Emerald map-identity candidates.

Prints, for every anchor, the byte at each candidate address, and counts how many OTHER
addresses in EWRAM/IWRAM carry a bit-identical value vector across all 12 anchors
(the 'how many twins does this signal have' number).
"""
import os

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dumps")
ANCHORS = ["truck", "out_truck", "house1f", "bed2f", "out_ownhouse", "may1f", "may2f",
           "out_north", "out_labdoor", "out_nw", "out_gap", "lab"]
OUT = {"out_truck", "out_ownhouse", "out_north", "out_labdoor", "out_nw", "out_gap"}
LITTLEROOT_INT = ["house1f", "bed2f", "may1f", "may2f", "lab"]

dumps = {r: {t: open(os.path.join(D, f"A_{t}.{r}.bin"), "rb").read() for t in ANCHORS}
         for r in ("ewram", "iwram")}

CAND = [("gObjectEvents[0].localId?", 0x02037358), ("mapNum", 0x02037359),
        ("mapGroup", 0x0203735A), ("elevation", 0x0203735B),
        ("initialCoords.x (BANKED 'map_num')", 0x0203735C),
        ("initialCoords.y", 0x0203735E),
        ("BANKED 'map_group'", 0x02037340)]

print("anchor          " + " ".join(f"{t[:9]:>9}" for t in ANCHORS))
for name, addr in CAND:
    row = [dumps["ewram"][t][addr - 0x02000000] for t in ANCHORS]
    print(f"{hex(addr)} {name[:26]:26} " + " ".join(f"{v:>9}" for v in row))

print()
for name, addr in (("mapNum", 0x02037359), ("mapGroup", 0x0203735A)):
    target = [dumps["ewram"][t][addr - 0x02000000] for t in ANCHORS]
    for region, base, lo in (("ewram", 0x02000000, 0), ("iwram", 0x03000000, 0)):
        d = dumps[region]
        blobs = [d[t] for t in ANCHORS]
        n = len(blobs[0])
        twins_all, twins_hi = [], []
        for i in range(lo, n):
            if all(b[i] == v for b, v in zip(blobs, target)):
                twins_all.append(base + i)
                if base + i >= 0x02010000 or region == "iwram":
                    twins_hi.append(base + i)
        print(f"{name} twins in {region}: {len(twins_all)} total, "
              f"{len(twins_hi)} outside the low-EWRAM graphics band -> {[hex(a) for a in twins_hi[:12]]}")

# How many EWRAM bytes would ALSO pass a naive 'stable per map' test but be wrong?
ew = dumps["ewram"]
outs = [ew[t] for t in OUT]
stable_out = sum(1 for i in range(len(outs[0])) if all(o[i] == outs[0][i] for o in outs[1:]))
print(f"\nEWRAM bytes bit-stable across all 6 outdoor-Littleroot anchors: {stable_out} "
      f"/ {len(outs[0])}")
