"""Lay out the candidate per-racer array as a table: for slot bases base0 + k*0x8C,
print the value trace of fields +0x00 / +0x0C / +0x18."""
import sys, numpy as np

out, wbase = sys.argv[1], int(sys.argv[2], 0)
W = np.load(out + "/window.npy"); F = np.load(out + "/frames.npy")
first = int(sys.argv[3], 0)   # first slot base to print
n = int(sys.argv[4])
STRIDE = 0x8C

for k in range(n):
    sb = first + k * STRIDE
    print(f"--- slot {k}  base {sb:#010x}")
    for off in (0x00, 0x0C, 0x18):
        a = sb + off
        j = a - wbase
        if not (0 <= j < W.shape[1]):
            print(f"   +{off:#04x} {a:#010x}  <outside window>"); continue
        col = W[:, j]
        ch = np.nonzero(col[1:] != col[:-1])[0] + 1
        tr = f"{int(col[0])}" + "".join(f" ->{int(col[i])}@f{F[i]}" for i in ch[:8])
        print(f"   +{off:#04x} {a:#010x}  {tr}" + ("" if len(ch) <= 8 else f"  (+{len(ch)-8} more)"))
