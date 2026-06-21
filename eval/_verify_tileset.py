"""Independent leave-one-TILESET-out + wall-recall + overlap verification.
Reuses probe_tilemap.gather for the exact same labelled samples, then groups maps
into tilesets and holds out ALL maps of a group (no sibling in store). The crux:
does indoor confidently mispredict walls as walkable when NO indoor map is in store?"""
import sys
from collections import Counter, defaultdict
import numpy as np
from core.tilemap import TileFunctionMap
from eval.probe_tilemap import gather

RUNS = ["runs/kanto1","runs/race1","runs/race2","runs/race3","runs/fix1","runs/fix2",
        "runs/fix4","runs/fix5","runs/novelty_val","runs/novelty_val3"]

# tileset groups by map_id (from lore + checked below by overlap)
GROUPS = {
    "town":   {0, 1},
    "route":  {12, 13},
    "indoor": {37, 38, 39, 40, 41},
    "forest": {51},
}

def main():
    samples = gather(RUNS)
    print(f"total samples {len(samples)}")
    # ---- pairwise fingerprint overlap (exact + tol) between maps ----
    by_map_fps = defaultdict(set)
    for fp, lab, mp, wcell, gs in samples:
        by_map_fps[mp].add(fp)
    def overlap(a, b, tol=0):
        A, B = by_map_fps[a], by_map_fps[b]
        if not A: return 0.0
        if tol == 0:
            return len(A & B) / len(A)
        cnt = 0
        for x in A:
            if any(bin(x ^ y).count("1") <= tol for y in B):
                cnt += 1
        return cnt / len(A)
    maps = sorted(by_map_fps, key=lambda m: -len(by_map_fps[m]))
    print("\n-- per-map best sibling overlap (exact / tol6) --")
    for m in maps:
        if not by_map_fps[m]: continue
        best0 = max(((overlap(m,o,0), o) for o in maps if o!=m and by_map_fps[o]), default=(0,None))
        best6 = max(((overlap(m,o,6), o) for o in maps if o!=m and by_map_fps[o]), default=(0,None))
        print(f"  map {m:>3} ndistinct={len(by_map_fps[m]):>4}  best-exact {best0[0]:.2f}->m{best0[1]}  best-tol6 {best6[0]:.2f}->m{best6[1]}")

    # ---- leave-one-TILESET-out ----
    print("\n-- leave-one-TILESET-out (ALL maps of group held; NO sibling in store) --")
    print("  group     n   cov    acc   base   wall-recall  walls(miscalled/total)  meanconf-misc  exactmatch-misc")
    for gname, mids in GROUPS.items():
        test = [s for s in samples if s[2] in mids]
        store = [s for s in samples if s[2] not in mids]
        if len(test) < 20: 
            print(f"  {gname}: too few ({len(test)})"); continue
        tmap = TileFunctionMap()
        store_fp_set = set()
        # also track store exact walkable fps for the exact-match audit
        store_walkable_fps = set()
        for fp, lab, *_ in store:
            tmap.observe(fp, lab)
            store_fp_set.add(fp)
            if lab == "walkable":
                store_walkable_fps.add(fp)
        known=correct=0
        wall_total=wall_recovered=0
        miscalled_walls=[]  # confidence
        exact_misc=0
        for fp, lab, *_ in test:
            pred = tmap.predict(fp)
            if pred is not None:
                known += 1
                correct += (pred[0]==lab)
            if lab == "blocked":
                if pred is not None:
                    wall_total += 1
                    if pred[0] == "blocked":
                        wall_recovered += 1
                    else:  # miscalled walkable
                        miscalled_walls.append(pred[1])
                        if fp in store_walkable_fps:
                            exact_misc += 1
        cov = known/len(test)
        acc = correct/known if known else float("nan")
        labs = Counter(s[1] for s in test)
        base = max(labs.values())/len(test)
        wr = (wall_recovered/wall_total) if wall_total else float("nan")
        mc = np.mean(miscalled_walls) if miscalled_walls else float("nan")
        print(f"  {gname:<8} {len(test):>4} {cov:>5.1%} {acc:>6.1%} {base:>6.1%}  {wr:>10.1%}   {len(miscalled_walls)}/{wall_total:<6}        {mc:>6.2f}        {exact_misc}")

if __name__ == "__main__":
    main()
