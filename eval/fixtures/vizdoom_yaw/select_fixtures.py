# Builds eval/fixtures/vizdoom_yaw/ from the precheck captures. Committed so the sampling is
# auditable: the main 28-pair set samples pairs where R0 ALREADY agrees with the commanded action
# (plus idle and turn->None pairs) -- it is a curated regression floor, NOT an unbiased draw from
# the pool. The pool's failing pairs are NOT discarded: every wrong-sign turn pair and every
# false-motion idle pair in the full pool is committed under known_limits/ with its own test
# (tests/test_yaw_flow.py) documenting the failure modes. Pool-honest numbers live in
# runs/vizdoom_precheck/PRECHECK_REPORT.md (PC-2), not here.
#
# Run from the repo root; requires the gitignored runs/vizdoom_precheck/{basic_mixed,dtc_mixed}/
# captures (regenerate via capture_basic_mixed.py / capture_dtc_mixed.py in that directory).
# Deterministic: RandomState(0), sequential sampling -- re-running reproduces the committed set.
import json
import os
import shutil
import sys
from collections import Counter

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from core.yaw_flow import yaw_band_flow  # noqa: E402

SRC = os.path.join("runs", "vizdoom_precheck")
DST = os.path.join("eval", "fixtures", "vizdoom_yaw")
EXP = {"TURN_LEFT": "left", "TURN_RIGHT": "right"}


def load_gray(path):
    return np.asarray(Image.open(path).convert("L"), dtype=np.float32)


def build_pairs(dirname):
    with open(os.path.join(SRC, dirname, "actions.jsonl")) as f:
        recs = [json.loads(l) for l in f]
    pairs = []
    for i in range(len(recs) - 1):
        if recs[i]["episode"] == recs[i + 1]["episode"]:
            pairs.append((dirname, recs[i]["frame"], recs[i + 1]["frame"],
                          recs[i]["action"], recs[i]["episode"]))
    return pairs


def main():
    all_pairs = build_pairs("basic_mixed") + build_pairs("dtc_mixed")
    cache = {}

    def gray(src, frame):
        key = (src, frame)
        if key not in cache:
            cache[key] = load_gray(os.path.join(SRC, src, frame))
        return cache[key]

    scored = []
    for src, fa, fb, act, ep in all_pairs:
        r = yaw_band_flow(gray(src, fa), gray(src, fb))
        scored.append({"src": src, "fa": fa, "fb": fb, "act": act, "ep": ep, "reading": r})

    # -- main-set buckets (agreeing turns / idle / turn->None) --------------------------------
    turn_left = [s for s in scored if s["act"] == "TURN_LEFT" and s["reading"].direction == "left"]
    turn_right = [s for s in scored if s["act"] == "TURN_RIGHT" and s["reading"].direction == "right"]
    idle = [s for s in scored if s["act"] == "IDLE"]
    uncertain = [s for s in scored
                 if s["act"] in ("TURN_LEFT", "TURN_RIGHT") and s["reading"].confidence is None]

    # -- known-limits pool: EVERY failing pair, exhaustive (no sampling, nothing excluded) -----
    wrong_sign = [s for s in scored
                  if s["act"] in EXP and s["reading"].direction is not None
                  and s["reading"].direction != EXP[s["act"]]]
    false_motion = [s for s in scored
                    if s["act"] == "IDLE"
                    and (s["reading"].direction not in (None, "none")
                         or s["reading"].dx_px not in (None, 0))]

    print("pool sizes: turn_left(agree)=%d turn_right(agree)=%d idle=%d uncertain(turn->None)=%d"
          % (len(turn_left), len(turn_right), len(idle), len(uncertain)))
    print("known-limits pool: wrong_sign=%d false_motion_idle=%d" % (len(wrong_sign), len(false_motion)))

    rng = np.random.RandomState(0)

    def sample(bucket, n):
        by_src = {}
        for s in bucket:
            by_src.setdefault(s["src"], []).append(s)
        picked = []
        srcs = list(by_src.keys())
        i = 0
        while len(picked) < n and any(by_src.values()):
            src = srcs[i % len(srcs)]
            if by_src[src]:
                idx = rng.randint(len(by_src[src]))
                picked.append(by_src[src].pop(idx))
            i += 1
        return picked

    picked = sample(turn_left, 8) + sample(turn_right, 8) + sample(idle, 6) + sample(uncertain, 6)

    seen = set()
    final = []
    for p in picked:
        key = (p["src"], p["fa"], p["fb"])
        if key not in seen:
            seen.add(key)
            final.append(p)
    print("main set:", len(final))

    def emit(items, out_dir, prefix):
        os.makedirs(out_dir, exist_ok=True)
        manifest = []
        for k, p in enumerate(items):
            fa_name = f"{prefix}{k:02d}_a.png"
            fb_name = f"{prefix}{k:02d}_b.png"
            shutil.copy(os.path.join(SRC, p["src"], p["fa"]), os.path.join(out_dir, fa_name))
            shutil.copy(os.path.join(SRC, p["src"], p["fb"]), os.path.join(out_dir, fb_name))
            manifest.append({
                "pair": k,
                "frame_a": fa_name,
                "frame_b": fb_name,
                "action": p["act"],
                "source": f"{p['src']}/ep{p['ep']}",
                "r0_dx_px": p["reading"].dx_px,
                "r0_direction": p["reading"].direction,
                "r0_confidence": p["reading"].confidence,
            })
        with open(os.path.join(out_dir, "actions.json"), "w") as f:
            json.dump(manifest, f, indent=2)
        return manifest

    main_manifest = emit(final, DST, "pair")
    limits_manifest = emit(wrong_sign + false_motion, os.path.join(DST, "known_limits"), "limit")

    print("main action mix:", Counter(m["action"] for m in main_manifest))
    print("main None count:", sum(1 for m in main_manifest if m["r0_direction"] is None))
    print("known_limits:", Counter(m["action"] for m in limits_manifest))


if __name__ == "__main__":
    main()
