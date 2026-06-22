"""Ceiling probe for CHEAP 3D odometry on the saved ViZDoom my_way_home substrate.

Compares the dumb whole-frame frame-diff baseline against a slightly-smarter optical-flow proxy
(block-matching + phase correlation) computed purely on the saved grayscale frames. Reports:
  (a) advanced-vs-blocked accuracy on PURE-forward steps vs the 83.7% frame-diff baseline.
  (b) TURN_LEFT vs TURN_RIGHT vs forward classification (labels = recorded actions + gt angle delta).

No vizdoom needed; reads runs/vizdoom_mywayhome/{buttons.jsonl, frame_*.png}.
"""
from __future__ import annotations
import json, math
import numpy as np
from PIL import Image

RUN = "runs/vizdoom_mywayhome"


def load():
    rows = [json.loads(l) for l in open(f"{RUN}/buttons.jsonl", encoding="utf-8")]
    grays = []
    for r in rows:
        im = Image.open(r["screen_path"]).convert("L")
        grays.append(np.asarray(im, dtype=np.float32))
    return rows, grays


def angdiff(a, b):
    """signed smallest difference a-b in degrees, in (-180,180]."""
    d = (a - b + 180.0) % 360.0 - 180.0
    return d


# ---------- cheap optical-flow proxies (grayscale only) ----------

def phase_shift_x(prev, cur):
    """Global horizontal shift via 1-D phase correlation on column-summed profiles.
    Returns estimated horizontal pixel shift (cur relative to prev). +ve = scene moved right
    (=> camera turned left), -ve = scene moved left (=> camera turned right)."""
    pp = prev.mean(axis=0)
    cc = cur.mean(axis=0)
    pp = pp - pp.mean(); cc = cc - cc.mean()
    n = len(pp)
    F = np.fft.rfft(pp); G = np.fft.rfft(cc)
    R = F * np.conj(G)
    denom = np.abs(R); denom[denom == 0] = 1e-9
    R = R / denom
    corr = np.fft.irfft(R, n=n)
    peak = int(np.argmax(corr))
    if peak > n // 2:
        peak -= n
    return float(peak)


def xcorr_shift_x(prev, cur, max_shift=40):
    """Brute-force best horizontal integer shift of column-profile (robust on tiny frames).
    Returns shift s minimizing SAD where cur shifted by s matches prev. +ve => scene moved right."""
    pp = prev.mean(axis=0); cc = cur.mean(axis=0)
    pp = pp - pp.mean(); cc = cc - cc.mean()
    n = len(pp)
    best_s, best_e = 0, 1e18
    for s in range(-max_shift, max_shift + 1):
        # shift cc by s, compare overlap to pp
        if s >= 0:
            a = pp[s:]; b = cc[:n - s]
        else:
            a = pp[:n + s]; b = cc[-s:]
        if len(a) < n // 2:
            continue
        e = float(np.mean((a - b) ** 2))
        if e < best_e:
            best_e, best_s = e, s
    return float(best_s)


def expansion_flow(prev, cur):
    """Radial expansion signal for forward motion: when advancing down a corridor, the scene
    expands outward (center pixels flow toward edges). Proxy = compare how much the magnified
    (zoomed-in) previous frame matches the current frame vs identity. Returns an 'advance score':
    how much better a forward-zoom warp of prev predicts cur than prev itself.
    Higher => more forward expansion."""
    h, w = prev.shape
    # crop center of prev and upscale to full -> simulates forward zoom
    z = 0.85  # keep central 85%
    ch, cw = int(h * z), int(w * z)
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    center = prev[y0:y0 + ch, x0:x0 + cw]
    zoomed = np.asarray(Image.fromarray(center).resize((w, h), Image.BILINEAR), dtype=np.float32)
    err_identity = np.mean(np.abs(prev - cur))
    err_zoom = np.mean(np.abs(zoomed - cur))
    return float(err_identity - err_zoom)  # +ve => zoom explains cur better => forward advance


def center_edge_ratio(prev, cur):
    """Forward advance tends to change edges more than center is too crude; instead measure that
    a forward-zoom warp reduces residual. Use abs frame-diff in an annulus (edges) which sees the
    most expansion-driven change. Returns mean abs diff over outer ring."""
    h, w = prev.shape
    m = max(2, h // 6)
    ring = np.abs(prev - cur).copy()
    inner = ring[m:-m, m:-m]
    ring_sum = ring.sum() - inner.sum()
    ring_n = ring.size - inner.size
    return float(ring_sum / ring_n)


def best_threshold_acc(score, y):
    """Best single-threshold accuracy (allowing polarity flip)."""
    score = np.asarray(score); y = np.asarray(y).astype(int)
    ts = np.unique(score)
    best = 0.0
    for t in ts:
        acc = ((score > t).astype(int) == y).mean()
        best = max(best, acc, 1 - acc)
    return best


def main():
    rows, grays = load()
    n = len(rows)
    iF = lambda b: "MOVE_FORWARD" in b
    iL = lambda b: "TURN_LEFT" in b
    iR = lambda b: "TURN_RIGHT" in b

    # TIMING: angle/pos are logged BEFORE make_action, so the frame transition (i-1 -> i) AND the
    # gt pos/angle change (i-1 -> i) are both CAUSED by the action recorded at row i-1.
    # Guard against episode resets: drop transitions with an implausibly large position jump.
    def is_reset(i):
        return math.dist(rows[i]["pos"], rows[i - 1]["pos"]) > 60.0

    # ===== (a) advanced vs blocked on PURE-forward steps =====
    dpos, fdiff, exp_sc, ring_sc, absflowx = [], [], [], [], []
    for i in range(1, n):
        b = rows[i - 1]["buttons"]  # action that caused transition (i-1 -> i)
        if not (iF(b) and not iL(b) and not iR(b)):
            continue
        if is_reset(i):
            continue
        p0 = rows[i - 1]["pos"]; p1 = rows[i]["pos"]
        dp = math.dist(p1, p0)
        dpos.append(dp)
        fdiff.append(float(np.abs(grays[i] - grays[i - 1]).mean()))
        exp_sc.append(expansion_flow(grays[i - 1], grays[i]))
        ring_sc.append(center_edge_ratio(grays[i - 1], grays[i]))
        absflowx.append(abs(xcorr_shift_x(grays[i - 1], grays[i])))
    dpos = np.array(dpos); fdiff = np.array(fdiff)
    exp_sc = np.array(exp_sc); ring_sc = np.array(ring_sc); absflowx = np.array(absflowx)

    thr = max(1.0, np.percentile(dpos, 60) * 0.2)
    y = (dpos > thr).astype(int)  # 1 = advanced
    print(f"=== (a) ADVANCED vs BLOCKED  (pure-forward n={len(dpos)}) ===")
    print(f"  threshold blocked<= {thr:.2f}  blocked n={int((y==0).sum())} advanced n={int(y.sum())}")
    print(f"  majority baseline: {max(y.mean(),1-y.mean()):.1%}")
    print(f"  frame-diff      acc={best_threshold_acc(fdiff,y):.1%}  corr={np.corrcoef(dpos,fdiff)[0,1]:+.2f}")
    print(f"  expansion-flow  acc={best_threshold_acc(exp_sc,y):.1%}  corr={np.corrcoef(dpos,exp_sc)[0,1]:+.2f}")
    print(f"  ring-diff       acc={best_threshold_acc(ring_sc,y):.1%}  corr={np.corrcoef(dpos,ring_sc)[0,1]:+.2f}")
    print(f"  |flow_x| (low=adv) acc={best_threshold_acc(absflowx,y):.1%}  corr={np.corrcoef(dpos,absflowx)[0,1]:+.2f}")

    # combine frame-diff + expansion via simple logistic-free 2-feature grid? Just report a cheap
    # AND/OR: use the better of the two per-step is cheating; instead a 2-feature linear separator
    # found by brute force over a small grid.
    def two_feat_acc(f1, f2, y):
        f1 = (f1 - f1.mean()) / (f1.std() + 1e-9)
        f2 = (f2 - f2.mean()) / (f2.std() + 1e-9)
        best = 0.0
        for w1 in np.linspace(-1, 1, 11):
            w2 = math.copysign(math.sqrt(max(0, 1 - w1 * w1)), 1)
            s = w1 * f1 + w2 * f2
            best = max(best, best_threshold_acc(s, y))
        return best
    print(f"  frame-diff + expansion (2-feat) acc={two_feat_acc(fdiff,exp_sc,y):.1%}")

    # ===== (b) TURN_LEFT vs TURN_RIGHT vs FORWARD =====
    # labels from recorded action (pure turns + pure forward). Verify with gt angle delta.
    cats = {"LEFT": [], "RIGHT": [], "FWD": []}
    for i in range(1, n):
        b = rows[i - 1]["buttons"]  # action causing transition (i-1 -> i)
        if is_reset(i):
            continue
        da = angdiff(rows[i]["angle"], rows[i - 1]["angle"])
        sx_phase = phase_shift_x(grays[i - 1], grays[i])
        sx_xcorr = xcorr_shift_x(grays[i - 1], grays[i])
        rec = (da, sx_phase, sx_xcorr)
        if iL(b) and not iR(b) and not iF(b):
            cats["LEFT"].append(rec)
        elif iR(b) and not iL(b) and not iF(b):
            cats["RIGHT"].append(rec)
        elif iF(b) and not iL(b) and not iR(b):
            cats["FWD"].append(rec)
    print(f"\n=== (b) TURN classification (pure actions) ===")
    for k in ("LEFT", "RIGHT", "FWD"):
        arr = np.array(cats[k])
        print(f"  {k:5s} n={len(arr):3d}  gt_dAngle mean={arr[:,0].mean():+7.2f}  "
              f"phase_shift_x mean={arr[:,1].mean():+6.2f}  xcorr_shift_x mean={arr[:,2].mean():+6.2f}")

    # 3-way classify using xcorr_shift_x: large +shift=>left, large -shift=>right, small=>fwd
    X, Y = [], []
    lab = {"LEFT": 0, "RIGHT": 1, "FWD": 2}
    for k in cats:
        for da, sp, sx in cats[k]:
            X.append(sx); Y.append(lab[k])
    X = np.array(X); Y = np.array(Y)
    # grid search two thresholds (tlo<0<thi): sx>thi -> LEFT, sx<tlo -> RIGHT, else FWD
    best_acc, best_t = 0.0, None
    grid = np.linspace(-30, 30, 121)
    for thi in grid:
        for tlo in grid:
            if tlo >= thi:
                continue
            pred = np.where(X > thi, 0, np.where(X < tlo, 1, 2))
            acc = (pred == Y).mean()
            if acc > best_acc:
                best_acc, best_t = acc, (tlo, thi)
    print(f"  3-way (LEFT/RIGHT/FWD) best xcorr_shift_x thresholds {best_t} acc={best_acc:.1%}  "
          f"(chance={1/3:.1%}, majority={max(np.bincount(Y))/len(Y):.1%})")

    # turn-only L vs R (forward excluded): sign of shift
    mask = Y != 2
    Xt, Yt = X[mask], Y[mask]
    pred_lr = (Xt < 0).astype(int)  # shift<0 => RIGHT(1); shift>0 => LEFT(0)
    acc_lr = (pred_lr == Yt).mean()
    print(f"  L-vs-R (sign of xcorr_shift_x) acc={max(acc_lr,1-acc_lr):.1%}  (n={len(Yt)})")

    # also using gt angle delta sign as a sanity check that LEFT/RIGHT labels are consistent
    A = np.array([r[0] for k in ("LEFT","RIGHT") for r in cats[k]])
    AY = np.array([lab[k] for k in ("LEFT","RIGHT") for r in cats[k]])
    print(f"  sanity: gt dAngle sign vs LEFT/RIGHT label acc="
          f"{max(((A>0).astype(int)==AY).mean(), 1-((A>0).astype(int)==AY).mean()):.1%}")


if __name__ == "__main__":
    main()
