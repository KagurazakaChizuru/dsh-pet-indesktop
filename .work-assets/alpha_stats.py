import sys

w, h = 640, 360
data = open(sys.argv[1], 'rb').read()
fs = w * h * 4
n = len(data) // fs
print("raw_bytes=%d frames=%d" % (len(data), n))
if n == 0:
    raise SystemExit("NO_FRAMES")
picks = sorted(set([0, n // 4, n // 2, (3 * n) // 4, n - 1]))
for i in picks:
    fr = data[i * fs:(i + 1) * fs]
    a = fr[3::4]
    zero = a.count(0)
    full = a.count(255)
    mid = len(a) - zero - full
    print("frame=%-4d alpha0=%-7d alpha255=%-7d mid=%d" % (i, zero, full, mid))
