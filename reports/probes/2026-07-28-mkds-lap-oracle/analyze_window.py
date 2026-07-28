"""Analyze the pass-2 window trace: print the per-address transition list for every address in
the window that changed few times, grouped so the per-racer struct stride is visible."""
import sys, numpy as np

out = sys.argv[1]
base = int(sys.argv[2], 0)
W = np.load(out + "/window.npy")      # (n, w) uint8
F = np.load(out + "/frames.npy")

print("samples", W.shape, "frames", F[0], "..", F[-1])
for j in range(W.shape[1]):
    col = W[:, j]
    ch = np.nonzero(col[1:] != col[:-1])[0] + 1
    if not (1 <= len(ch) <= 6):
        continue
    span = int(col.max()) - int(col.min())
    if span > 8:
        continue
    trace = " ".join(f"{int(col[0])}" if k == 0 else f"->{int(col[i])}@f{F[i]}"
                     for k, i in enumerate([0] + ch.tolist()))
    print(f"{base+j:#010x} (+{j:#05x})  {trace}")
