#!/usr/bin/env python3
"""camscan.py ref.mp4 [outdir]  -> 30 fps camera / world / colour analysis of a reference short (learn the grammar, never copy shots)

Per frame (30 fps, 180x320 analysis size, caption band masked):
  camera  dense optical flow (Farneback) fitted to a similarity model: pan (x), tilt (y), zoom (divergence), roll (curl);
          the residual after the fit = 3D parallax (dolly / truck / orbit / crane through the set, not a pure rotation).
          Classes: static, creep (alive drift), pan, tilt, push, pull, roll, orbit/truck (lateral + parallax), dolly
          (zoom + parallax), whip (very fast), shake (sign-flipping jolts), cut.
  framing white character heads (pure-white round blobs with ink rims) -> head height as % of frame -> shot size
          (ECU / CU / MCU / MS / FS / WS) and head position (eye-line third); horizon row from the sky/ground edge ->
          camera pitch proxy (horizon high = looking down / crane, low = low-angle hero cam).
  colour  sky (top band) and ground (bottom band) mean colours, 5-colour palette (k-means), luminance p5/p50/p95,
          saturation, warm/cool balance (R-B), haze (contrast of the top half vs the bottom half).
Writes outdir/camscan.json (per frame + per shot), outdir/report.md (human summary) and outdir/timeline.png."""
import json, os, subprocess, sys
import numpy as np
import cv2

src = sys.argv[1]; out = sys.argv[2] if len(sys.argv) > 2 else "work/camscan"
os.makedirs(out, exist_ok=True)
W, H = 180, 320
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps=30,scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
F = np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3)
N = len(F)
CAP0, CAP1 = int(0.62 * H), int(0.78 * H)          # caption band (excluded from flow and colour)
mask = np.ones((H, W), bool); mask[CAP0:CAP1] = False
ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
cx, cy = (W - 1) / 2, (H - 1) / 2
X, Y = (xs - cx)[mask], (ys - cy)[mask]
A = np.zeros((2 * X.size, 4), np.float32)          # similarity model: u = tx + a x - b y ; v = ty + b x + a y
A[0::2, 0] = 1; A[0::2, 2] = X; A[0::2, 3] = -Y
A[1::2, 1] = 1; A[1::2, 2] = Y; A[1::2, 3] = X
Apinv = np.linalg.pinv(A)
gray = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) for f in F]
hsv_all = [cv2.cvtColor(f, cv2.COLOR_RGB2HSV) for f in F]

cam, cuts = [dict(tx=0, ty=0, zoom=0, roll=0, par=0, mag=0, cls="start")], []
for i in range(1, N):
    d = np.abs(gray[i].astype(np.int16) - gray[i - 1]).mean()
    hist_a = cv2.calcHist([hsv_all[i - 1]], [0, 1], None, [16, 8], [0, 180, 0, 256]); hist_b = cv2.calcHist([hsv_all[i]], [0, 1], None, [16, 8], [0, 180, 0, 256])
    hcorr = cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CORREL)
    if d > 28 and hcorr < 0.55:
        cuts.append(i); cam.append(dict(tx=0, ty=0, zoom=0, roll=0, par=0, mag=0, cls="cut")); continue
    fl = cv2.calcOpticalFlowFarneback(gray[i - 1], gray[i], None, 0.5, 3, 15, 3, 5, 1.2, 0)
    u, v = fl[..., 0][mask], fl[..., 1][mask]
    b = np.empty(2 * u.size, np.float32); b[0::2] = u; b[1::2] = v
    p = Apinv @ b
    res = b - A @ p
    tx, ty, a, rot = [float(x) for x in p]
    par = float(np.sqrt((res ** 2).reshape(-1, 2).sum(1)).mean())
    zoom = a * H / 2                                 # px of radial motion at the frame edge
    roll = np.degrees(rot)
    mag = float(np.hypot(u, v).mean())
    cam.append(dict(tx=tx, ty=ty, zoom=zoom, roll=roll, par=par, mag=mag))
# classify (thresholds in px/frame at 180x320; 1 px = 0.56 % of the frame width)
for i, c in enumerate(cam):
    if c.get("cls") in ("cut", "start"): continue
    prev = cam[i - 1]
    flip = prev.get("tx", 0) * c["tx"] < -0.25 and abs(c["tx"]) > 0.6 and abs(prev.get("tx", 0)) > 0.6
    if c["mag"] > 9: k = "whip"
    elif flip: k = "shake"
    elif c["mag"] < 0.12: k = "static"
    elif c["mag"] < 0.45 and c["par"] < 0.35: k = "creep"
    elif abs(c["roll"]) > 0.35 and abs(c["roll"]) * 2 > abs(c["tx"]): k = "roll"
    elif abs(c["zoom"]) > max(abs(c["tx"]), abs(c["ty"])) * 0.8: k = ("dolly-in" if c["zoom"] > 0 else "dolly-out") if c["par"] > 0.4 else ("push" if c["zoom"] > 0 else "pull")
    elif abs(c["tx"]) >= abs(c["ty"]): k = "orbit/truck" if c["par"] > 0.45 else "pan"
    else: k = "crane" if c["par"] > 0.45 else "tilt"
    c["cls"] = k

# ---------- framing: white character heads + horizon ----------
def heads(f, hsv):
    s, v = hsv[..., 1], hsv[..., 2]
    vt = max(150, min(228, np.percentile(v, 97)))   # adaptive: lamp-lit heads at night are cream, not pure white
    wm = ((s < 60) & (v > vt)).astype(np.uint8)
    wm = cv2.morphologyEx(wm, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    wm[CAP0 - 4:CAP1 + 4] = 0
    n, lab, st, cen = cv2.connectedComponentsWithStats(wm, 8)
    out = []
    for j in range(1, n):
        x, y, w, h, area = st[j]
        if area < 30 or h < 7 or w < 7: continue
        fill = area / (w * h)
        if 0.5 < fill < 0.93 and 0.6 < w / h < 1.7 and h < 0.45 * H:
            ring = f[max(0, y - 2):y + h + 2, max(0, x - 2):x + w + 2].mean(2)
            if (ring < 70).mean() > 0.04: out.append((y / H, h / H, (x + w / 2) / W))
    return out
def horizon(g):
    col = g[:CAP0].astype(np.float32).mean(1)
    gr = np.abs(np.diff(cv2.GaussianBlur(col.reshape(-1, 1), (1, 9), 3).ravel()))
    r = int(np.argmax(gr[10:CAP0 - 10])) + 10
    return r / H if gr[r] > 1.0 else None
SIZES = [(0.30, "ECU"), (0.17, "CU"), (0.10, "MCU"), (0.06, "MS"), (0.035, "FS"), (0, "WS")]
frm = []
for i in range(N):
    hs = heads(F[i], hsv_all[i])
    big = max(hs, key=lambda q: q[1]) if hs else None
    size = next(n for t, n in SIZES if big and big[1] >= t) if big else "none"
    frm.append(dict(heads=len(hs), head_h=round(big[1], 3) if big else 0, head_y=round(big[0], 3) if big else None, head_x=round(big[2], 3) if big else None, size=size, horizon=horizon(gray[i])))

# ---------- colour ----------
def colour(f, hsv):
    top, bot = f[: int(0.22 * H)].reshape(-1, 3), np.concatenate([f[int(0.5 * H):CAP0], f[CAP1:]]).reshape(-1, 3)
    lum = (0.2126 * f[..., 0] + 0.7152 * f[..., 1] + 0.0722 * f[..., 2])[mask]
    px = f[mask].reshape(-1, 3).astype(np.float32)
    _, lab, ctr = cv2.kmeans(px[::7], 5, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0), 2, cv2.KMEANS_PP_CENTERS)
    cnt = np.bincount(lab.ravel(), minlength=5); order = np.argsort(-cnt)
    up, lo = f[: CAP0 // 2].mean(2), f[CAP0 // 2:CAP0].mean(2)
    return dict(sky="#%02x%02x%02x" % tuple(top.mean(0).astype(int)), ground="#%02x%02x%02x" % tuple(bot.mean(0).astype(int)),
                palette=["#%02x%02x%02x" % tuple(ctr[j].astype(int)) for j in order], share=[round(cnt[j] / cnt.sum(), 2) for j in order],
                l5=float(np.percentile(lum, 5)), l50=float(np.percentile(lum, 50)), l95=float(np.percentile(lum, 95)),
                sat=float(hsv[..., 1][mask].mean()), warm=float((px[:, 0] - px[:, 2]).mean()), haze=float(up.std() / (lo.std() + 1e-6)))
col = [colour(F[i], hsv_all[i]) for i in range(0, N, 15)]

# ---------- per-shot summary ----------
bounds = [0] + cuts + [N]
shots = []
for a, b in zip(bounds[:-1], bounds[1:]):
    seg = [c for c in cam[a + 1:b] if c["cls"] not in ("cut", "start")]
    cls = {}
    for c in seg: cls[c["cls"]] = cls.get(c["cls"], 0) + 1
    sz = {}
    for q in frm[a:b]: sz[q["size"]] = sz.get(q["size"], 0) + 1
    runs, cur, n0 = [], None, 0          # move segments (merged runs of the same class)
    for j, c in enumerate(cam[a + 1:b], a + 1):
        if c["cls"] != cur:
            if cur is not None: runs.append((cur, n0, j - n0))
            cur, n0 = c["cls"], j
    if cur is not None: runs.append((cur, n0, b - n0))
    shots.append(dict(a=a, b=b, sec=round((b - a) / 30, 2), moves={k: round(v / max(1, len(seg)), 2) for k, v in sorted(cls.items(), key=lambda kv: -kv[1])},
                      sizes={k: round(v / (b - a), 2) for k, v in sorted(sz.items(), key=lambda kv: -kv[1])},
                      speed=round(float(np.mean([c["mag"] for c in seg])) if seg else 0, 2), parallax=round(float(np.mean([c["par"] for c in seg])) if seg else 0, 2),
                      segments=[r for r in runs if r[2] >= 6]))
json.dump(dict(src=os.path.basename(src), frames=N, cuts=cuts, cam=cam, framing=frm, colour=col, shots=shots), open(f"{out}/camscan.json", "w"))

# ---------- report ----------
allc = {}
for c in cam:
    allc[c["cls"]] = allc.get(c["cls"], 0) + 1
segs = []; cur, n0 = None, 0
for j, c in enumerate(cam):
    if c["cls"] != cur:
        if cur is not None: segs.append((cur, n0, j - n0))
        cur, n0 = c["cls"], j
segs.append((cur, n0, N - n0))
moves = [s for s in segs if s[0] not in ("static", "creep", "cut", "start") and s[2] >= 4]
szs = {}
for q in frm: szs[q["size"]] = szs.get(q["size"], 0) + 1
hy = [q["head_y"] for q in frm if q["head_y"] is not None]; hx = [q["head_x"] for q in frm if q["head_x"] is not None]
hz = [q["horizon"] for q in frm if q["horizon"] is not None]
L = [f"# camscan: {os.path.basename(src)}  ({N} frames @ 30 fps, {N / 30:.1f} s)", "",
     f"**Cuts:** {len(cuts)} at {', '.join(f'{c / 30:.1f}s' for c in cuts) or '-'} -> average shot {N / 30 / (len(cuts) + 1):.1f} s", "",
     "**Camera move mix (share of frames):** " + ", ".join(f"{k} {100 * v / N:.0f}%" for k, v in sorted(allc.items(), key=lambda kv: -kv[1])), "",
     f"**Move segments >= 4 f:** {len(moves)} (one every {N / max(1, len(moves)):.0f} frames); median length {int(np.median([m[2] for m in moves])) if moves else 0} f; "
     f"mean speed {np.mean([c['mag'] for c in cam]) / W * 100:.2f} % of frame width per frame; mean parallax {np.mean([c['par'] for c in cam]):.2f} px/f", "",
     "**Shot sizes (share of frames, by the biggest white head):** " + ", ".join(f"{k} {100 * v / N:.0f}%" for k, v in sorted(szs.items(), key=lambda kv: -kv[1])), "",
     f"**Head placement:** top of head at {np.median(hy) * 100:.0f}% of frame height (p25-p75 {np.percentile(hy, 25) * 100:.0f}-{np.percentile(hy, 75) * 100:.0f}%), x centre {np.median(hx) * 100:.0f}% (p25-p75 {np.percentile(hx, 25) * 100:.0f}-{np.percentile(hx, 75) * 100:.0f}%)" if hy else "**Head placement:** no heads detected", "",
     f"**Horizon row:** median {np.median(hz) * 100:.0f}% of frame height (p25-p75 {np.percentile(hz, 25) * 100:.0f}-{np.percentile(hz, 75) * 100:.0f}%)" if hz else "", "",
     "**Colour (every 0.5 s):** luminance p5/p50/p95 = " + f"{np.mean([c['l5'] for c in col]):.0f} / {np.mean([c['l50'] for c in col]):.0f} / {np.mean([c['l95'] for c in col]):.0f}; "
     f"saturation {np.mean([c['sat'] for c in col]):.0f}/255; warm-cool (R-B) {np.mean([c['warm'] for c in col]):+.0f}; haze ratio {np.mean([c['haze'] for c in col]):.2f}", "",
     "## Shots", "| # | time | s | moves | sizes | speed px/f | parallax | main segments |", "|---|---|---|---|---|---|---|---|"]
for k, s in enumerate(shots):
    L.append(f"| {k + 1} | {s['a'] / 30:.1f}-{s['b'] / 30:.1f} | {s['sec']} | " + ", ".join(f"{m} {int(100 * v)}%" for m, v in list(s["moves"].items())[:4]) +
             " | " + ", ".join(f"{m} {int(100 * v)}%" for m, v in list(s["sizes"].items())[:3]) + f" | {s['speed']} | {s['parallax']} | " +
             "; ".join(f"{m}@{a / 30:.1f}s/{n}f" for m, a, n in s["segments"] if m not in ('creep', 'static'))[:300] + " |")
L += ["", "## Colour samples (every 2 s)", "| t | sky | ground | palette (share) | p50 | sat | warm | haze |", "|---|---|---|---|---|---|---|---|"]
for j, c in enumerate(col[::4]):
    L.append(f"| {j * 2:.0f}s | {c['sky']} | {c['ground']} | " + " ".join(f"{p}({s})" for p, s in zip(c["palette"], c["share"])) + f" | {c['l50']:.0f} | {c['sat']:.0f} | {c['warm']:+.0f} | {c['haze']:.2f} |")
open(f"{out}/report.md", "w").write("\n".join(L))
# timeline image: one column per frame, colour by move class, row 2 = shot size, row 3 = mean frame colour
CC = {"static": (40, 40, 40), "creep": (90, 90, 90), "pan": (60, 140, 255), "tilt": (60, 220, 255), "push": (60, 220, 90), "pull": (40, 140, 60), "dolly-in": (150, 255, 90),
      "dolly-out": (90, 180, 40), "roll": (255, 200, 40), "orbit/truck": (255, 120, 40), "crane": (220, 80, 255), "whip": (255, 40, 40), "shake": (255, 255, 255), "cut": (255, 0, 255), "start": (0, 0, 0)}
SC = {"ECU": 250, "CU": 200, "MCU": 160, "MS": 120, "FS": 80, "WS": 45, "none": 10}
img = np.zeros((90, N, 3), np.uint8)
for i in range(N):
    img[:30, i] = CC.get(cam[i]["cls"], (0, 0, 0)); img[30:60, i] = SC[frm[i]["size"]]; img[60:, i] = F[i][:CAP0].reshape(-1, 3).mean(0)
cv2.imwrite(f"{out}/timeline.png", cv2.cvtColor(cv2.resize(img, (min(N, 1800), 90), interpolation=cv2.INTER_NEAREST), cv2.COLOR_RGB2BGR))
print("\n".join(L[:16]))
print(f"\nwrote {out}/report.md, camscan.json, timeline.png")
