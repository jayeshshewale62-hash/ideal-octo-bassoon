#!/usr/bin/env python3
"""refscan.py ref.mp4 [outdir]  -> 30 fps style analysis of a reference short (for learning pacing and look, never to copy shots)
Prints: resolution / fps / duration; hard cuts (scene > 0.32) and the average shot length; camera activity (mean
frame-to-frame motion above the caption band, % static frames, longest static run, runs >= 4 frames); motion per second;
caption cadence (changes in the caption band -> frames per card); colour (mean saturation / value); loudness (I, LRA,
true peak). Writes outdir/sheet_1fps.jpg (every second) and outdir/cuts.txt. Compare with the spec in SKILL.md."""
import json, os, subprocess, sys, glob, tempfile
import numpy as np
from PIL import Image

src = sys.argv[1]; out = sys.argv[2] if len(sys.argv) > 2 else "work/refscan"
os.makedirs(out, exist_ok=True)
pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate,nb_frames:format=duration", "-of", "json", src], capture_output=True, text=True).stdout)
s, dur = pr["streams"][0], float(pr["format"]["duration"])
print(f"{os.path.basename(src)}: {s['width']}x{s['height']} @ {s['r_frame_rate']}, {dur:.2f} s, {s.get('nb_frames')} frames")
tmp = tempfile.mkdtemp()
subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vf", "fps=30,scale=180:320", "-q:v", "4", f"{tmp}/f%05d.jpg"], check=True)
subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vf", "fps=1,scale=270:480", f"{out}/s%03d.jpg"], check=True)
A = [np.asarray(Image.open(f).convert("RGB"), dtype=np.float32) for f in sorted(glob.glob(f"{tmp}/*.jpg"))]
n = len(A)
mot = np.array([np.abs(A[i][:200] - A[i - 1][:200]).mean() for i in range(1, n)])
cap = np.array([np.abs(A[i][212:242, 20:160] - A[i - 1][212:242, 20:160]).mean() for i in range(1, n)])
cuts = [float(t) for t in subprocess.run(["bash", "-c", f"ffmpeg -v info -i '{src}' -vf \"select='gt(scene,0.32)',showinfo\" -an -f null - 2>&1 | grep -o 'pts_time:[0-9.]*' | cut -d: -f2"], capture_output=True, text=True).stdout.split()]
open(f"{out}/cuts.txt", "w").write("\n".join(f"{c:.2f}" for c in cuts))
static = mot < 0.6; runs, r = [], 0
for v in static:
    if v: r += 1
    elif r: runs.append(r); r = 0
capev = int(((cap[1:] > 12) & (cap[:-1] <= 12)).sum())
hsv = [np.asarray(Image.fromarray(a.astype(np.uint8)).convert("HSV"), dtype=np.float32) for a in A[::30]]
print(f"hard cuts: {len(cuts)} -> average shot {dur / (len(cuts) + 1):.1f} s   at: {', '.join(f'{c:.1f}' for c in cuts)}")
print(f"camera: mean motion {mot.mean():.2f}, static frames {100 * static.mean():.1f} %, longest static run {max(runs or [0])} f, runs >= 4 f: {sum(x >= 4 for x in runs)}")
print("motion per second:", " ".join(f"{mot[i:i + 30].mean():.0f}" for i in range(0, len(mot), 30)))
print(f"captions: ~{capev} card changes -> one card every {n / max(1, capev):.1f} frames ({n / max(1, capev) / 30:.2f} s)")
print(f"colour: mean saturation {np.mean([h[..., 1].mean() for h in hsv]):.0f}/255, value {np.mean([h[..., 2].mean() for h in hsv]):.0f}/255")
ld = subprocess.run(["bash", "-c", f"ffmpeg -nostats -i '{src}' -filter_complex ebur128=peak=true -f null - 2>&1 | grep -A14 Summary | grep -E 'I:|LRA:|Peak:'"], capture_output=True, text=True).stdout.split("\n")
print("loudness:", " | ".join(x.strip() for x in ld if x.strip()))
here = os.path.dirname(os.path.abspath(__file__))
subprocess.run([sys.executable, os.path.join(here, "sheet.py"), out, f"{out}/sheet_1fps.jpg", "10"], check=False)
