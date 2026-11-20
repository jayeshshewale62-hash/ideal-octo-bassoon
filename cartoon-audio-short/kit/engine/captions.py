#!/usr/bin/env python3
"""captions.py work/words.json out/captions.ass [--font "Inter ExtraBold"] [--max-words 2]
30 fps pop-word captions: bold white sans, ONE word per card (a short word like "a", "by", "it" pairs with its neighbour; the
reference shorts change cards every ~11 frames / 0.37 s), thick black outline + drop shadow, centred in the lower
third (y = 70 % of 1920 = 1344 px), each card pops 92 % -> 100 % scale over 40 ms. Timings come from the word timestamps
(timing.py or ASR) snapped to 30 fps frame boundaries; cards never overlap and hold until the next card (or 0.5 s max
over a pause). Grouping: a card is 1 word, or 2 short words (<= 14 chars together) with no punctuation break between.
Burn in with finish.sh (ffmpeg -vf ass=...)."""
import argparse, json, re

FPS = 30
ap = argparse.ArgumentParser()
ap.add_argument("words"); ap.add_argument("out")
ap.add_argument("--font", default="Inter ExtraBold")
ap.add_argument("--size", type=int, default=96)
ap.add_argument("--max-words", type=int, default=2, help="cap; a 2nd word is only added after a short word (a, by, it...)")
ap.add_argument("--y", type=float, default=0.70)
ap.add_argument("--upper", action="store_true", help="UPPERCASE cards")
a = ap.parse_args()

W = json.load(open(a.words))
snap = lambda t: round(t * FPS) / FPS
def ts(t):
    cs = int(round(t * 100)); h, cs = divmod(cs, 360000); m, cs = divmod(cs, 6000); s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

cards, i = [], 0
while i < len(W):
    grp = [W[i]]
    while (len(grp) < a.max_words and i + len(grp) < len(W) and not re.search(r"[.,!?;:—-]$", grp[-1]["word"])
           and (len(grp[-1]["word"].strip(".,!?")) <= 3 or len(W[i + len(grp)]["word"].strip(".,!?")) <= 2)
           and len(" ".join(g["word"] for g in grp) + W[i + len(grp)]["word"]) <= 11
           and W[i + len(grp)]["start"] - grp[-1]["end"] < 0.12):
        grp.append(W[i + len(grp)])
    text = " ".join(re.sub(r"[\"“”]", "", g["word"]) for g in grp).rstrip(",;:")
    cards.append([snap(grp[0]["start"]), snap(grp[-1]["end"]), text.upper() if a.upper else text])
    i += len(grp)
for k, c in enumerate(cards):  # hold to the next card, but never overlap, and drop off after 0.5 s of silence
    nxt = cards[k + 1][0] if k + 1 < len(cards) else c[1] + 0.5
    c[1] = max(c[0] + 2 / FPS, min(nxt, c[1] + 0.5))

y = round(1920 * a.y)
head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pop,{a.font},{a.size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,1,0,1,9,5,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
with open(a.out, "w") as fo:
    fo.write(head)
    for s, e, t in cards:
        t = t.replace("{", "(").replace("}", ")")
        fo.write(f"Dialogue: 0,{ts(s)},{ts(e)},Pop,,0,0,0,,{{\\an5\\pos(540,{y})\\fscx92\\fscy92\\t(0,40,\\fscx100\\fscy100)}}{t}\n")
print(f"wrote {a.out}: {len(cards)} cards from {len(W)} words, y={y}px, font '{a.font}'")
