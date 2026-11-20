#!/usr/bin/env python3
"""pacing.py script.txt [--voice voice.mp3] [--wps 3.3] [--slow-wps 2.6]
Word-count + pacing guard and hook / structure lint for a 58-65 s vertical short (1750-1950 frames @ 30 fps).
- words: target 180-210 at ~3.2-3.5 words/s; WARN over ~210 words, or if a slower narrator voice (deep / "soothing"
  ElevenLabs voices read ~2.6 words/s with pauses) would push the video past 65 s.
- hook: a concrete number (digits or number words) or a paradox in the first 8 words; bans slow openers.
- midpoint pivot: a curiosity question ("So what's in there?", "How does this keep happening?") should exist.
- ending: no call-to-action / outro on the last line.
- with --voice: measures the real duration and checks 58-65 s (and that frames = round(duration x 30)).
Exit code 1 on any WARN (so it can gate the pipeline)."""
import argparse, re, subprocess, sys

NUMW = r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fifteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|half|double|twice|triple)\b"
PARADOX = r"\b(never|nobody|no one|without|but|backwards|impossible|accidentally|twice|only)\b"
SLOW = [r"^have you ever", r"^in ancient times", r"^long ago", r"^once upon", r"^did you know", r"^imagine", r"^today we", r"^in this video", r"^hey guys", r"^welcome"]
CTA = r"(subscribe|follow for more|like and|comment below|let me know|see you|thanks for watching|part two)"

ap = argparse.ArgumentParser(); ap.add_argument("script"); ap.add_argument("--voice"); ap.add_argument("--wps", type=float, default=3.3); ap.add_argument("--slow-wps", type=float, default=2.6)
a = ap.parse_args()
text = open(a.script).read().strip()
words = re.findall(r"[A-Za-z0-9'\-]+", text)
n, warn = len(words), []
est, slow = n / a.wps, n / a.slow_wps
print(f"words: {n}  -> ~{est:.1f} s at {a.wps} w/s ({round(est*30)} frames); ~{slow:.1f} s with a slow narrator ({a.slow_wps} w/s)")
if n > 210: warn.append(f"script is {n} words (> ~210 for a 60 s target): cut {n-200}+ words")
if n < 170: warn.append(f"script is {n} words: likely under 58 s at {a.wps} w/s")
if slow > 65: warn.append(f"a slow narrator voice would run ~{slow:.0f} s (> 65 s): use speed ~1.1 or trim to ~{int(65*a.slow_wps)} words")
first8 = " ".join(words[:8]).lower()
if not (re.search(r"\d", first8) or re.search(NUMW, first8) or re.search(PARADOX, first8)):
    warn.append(f"hook: no concrete number or paradox in the first 8 words: \"{first8}\"")
if any(re.search(p, text.lower()) for p in SLOW): warn.append("hook: slow setup opener (e.g. 'Have you ever wondered', 'In ancient times'): open mid-action")
if not re.search(r"(what'?s (in|inside|under) |how (does|did|do|could)|why (does|did|would)|so what|but how)[^?]*\?", text, re.I):
    warn.append("midpoint: no curiosity question before the cutaway (e.g. \"So what's in there?\")")
last = re.split(r"(?<=[.!?])\s+", text)[-1]
if re.search(CTA, last, re.I): warn.append(f"ending: call-to-action / outro in the last line: \"{last}\"")
if a.voice:
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.voice], capture_output=True, text=True).stdout.strip())
    print(f"voice: {d:.2f} s = {round(d*30)} frames @ 30 fps; real pace {n/d:.2f} words/s")
    if not 58 <= d <= 65: warn.append(f"voice runs {d:.1f} s: target 58-65 s (1750-1950 frames)")
for w in warn: print("WARN", w)
print("OK" if not warn else f"{len(warn)} warning(s)")
sys.exit(1 if warn else 0)
