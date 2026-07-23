"""F4 scorer: oracle map_id (truth) vs coined place_id `area` (pixels-only). Tests whether a name
coined in-run stays a faithful, stable ADDRESS across transitions -> the A2 falsifier.
"""
import json, sys, math, collections

SETTLE = 3  # drop the first N frames of each visit-run (warp re-anchor lag)

def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")]

def visit_runs(rows):
    """Contiguous runs of constant map_id, in order. Returns list of dicts."""
    runs = []
    for r in rows:
        m = r["map_id"]
        if not runs or runs[-1]["map"] != m:
            runs.append({"map": m, "areas": [], "start": r["step"]})
        runs[-1]["areas"].append(r["area"])
    for k, run in enumerate(runs):
        run["tidx"] = k                      # transition index (0 = first arrival)
        settled = run["areas"][SETTLE:] or run["areas"]
        run["mode"] = collections.Counter(settled).most_common(1)[0][0]
        run["distinct"] = sorted(set(run["areas"]))
    return runs

def entropy(counter):
    n = sum(counter.values())
    return -sum((c/n)*math.log(c/n) for c in counter.values() if c)

def vmeasure(rows):
    C = collections.Counter(r["map_id"] for r in rows)      # truth
    K = collections.Counter(r["area"] for r in rows)        # coined
    joint = collections.Counter((r["map_id"], r["area"]) for r in rows)
    n = len(rows)
    # H(C|K) = sum_k p(k) H(C|k)
    hck = 0.0
    for k in K:
        sub = collections.Counter(c for (c, kk), v in joint.items() if kk == k for _ in range(v))
        hck += (K[k]/n) * entropy(sub)
    hkc = 0.0
    for c in C:
        sub = collections.Counter(kk for (cc, kk), v in joint.items() if cc == c for _ in range(v))
        hkc += (C[c]/n) * entropy(sub)
    HC, HK = entropy(C), entropy(K)
    h = 1 - hck/HC if HC else 1.0
    comp = 1 - hkc/HK if HK else 1.0
    v = 2*h*comp/(h+comp) if (h+comp) else 0.0
    return h, comp, v

def main():
    rows = load(sys.argv[1])
    maps = [r["map_id"] for r in rows]
    mseq = [m for i, m in enumerate(maps) if i == 0 or m != maps[i-1]]
    runs = visit_runs(rows)

    m2a = collections.defaultdict(set); a2m = collections.defaultdict(set)
    for r in rows:
        m2a[r["map_id"]].add(r["area"]); a2m[r["area"]].add(r["map_id"])
    split = {m: sorted(a) for m, a in m2a.items() if len(a) > 1}
    merge = {a: sorted(m) for a, m in a2m.items() if len(m) > 1}
    h, comp, v = vmeasure(rows)

    print(f"frames={len(rows)} transitions={len(mseq)-1} distinct_maps={sorted(set(maps))}")
    print(f"map_seq={mseq}")
    print(f"SPLIT (map->coined areas, >1 = re-mint): {split}")
    print(f"MERGE (coined area->maps, >1 = collision): {merge}")
    print(f"V-measure: homogeneity(no-merge)={h:.3f} completeness(no-split)={comp:.3f} V={v:.3f}")
    print()
    # coin a NAME at each map's FIRST visit = settled-mode area of run 0
    name = {}
    for run in runs:
        name.setdefault(run["map"], run["mode"])
    print("NAME bindings (map -> coined area at first visit):", name)
    # is each name unambiguous? (its area maps to exactly one true map, all-frames)
    ambiguous = {m: a for m, a in name.items() if len(a2m[a]) > 1}
    print("ambiguous names (coined area also = another map):", ambiguous)
    print()
    print("RESOLUTION TEST — for each RETURN visit-run: does settled area == the name coined at first visit?")
    hdr = f"{'map':>4} {'tidx':>4} {'coined':>6} {'ret_area':>8} {'result':>10}  areas_seen"
    print(hdr)
    total = ok = ge5 = ge5ok = 0
    for run in runs:
        m = run["map"]
        if run["tidx"] == 0:
            continue                          # first visit = the coin event, not a return
        total += 1
        coined = name[m]
        got = run["mode"]
        success = (got == coined) and (m not in ambiguous)
        # classify a failure: SPLIT (fresh/other area not previously a name) = fail-safe;
        # MERGE/mislabel (got == another map's coined name) = confident-wrong (dangerous)
        if success:
            res = "OK"
        elif got in name.values() and got != coined:
            res = "WRONG"                     # resolves to a DIFFERENT named place
        else:
            res = "SPLIT"                     # honest fresh/unknown -> fail-safe
        ok += success
        if run["tidx"] >= 5:
            ge5 += 1; ge5ok += success
        print(f"{m:>4} {run['tidx']:>4} {coined:>6} {got:>8} {res:>10}  {run['distinct']}")
    print()
    print(f"resolution accuracy: {ok}/{total} returns; after >=5 transitions: {ge5ok}/{ge5}")

if __name__ == "__main__":
    main()
