#!/usr/bin/env python3
"""SFX stem (all original synthesis). NO BACKGROUND MUSIC: the soundtrack is the voiceover + this SFX stem only.
Template = the v2 demo "The Grocer's Rocket Cart" (62 s).
usage: python3 audio.py <voice> <outdir>   -> outdir/sfx.wav (48 kHz stereo, exact voice length)
Rewrite CUES / MUSIC_STOP for each story (event times in frames at 30 fps, taken from story.js / work/words.json); the
synths stay. Levels do not matter here: mix.py locks the stem to -6.0 dB under the voice.
No music, no musical stings (no melody, chords, drums or cymbals): emphasis comes from SFX alone.
SFX: whooshes on whip-glides, cart rattle, rain bed, thunder on lightning, splash on the slip / dive, van brakes,
fuse fizz, rocket launch, firework pops, final explosion, plus a quiet location ambience bed (day air / night
insects + wind / rain) so the gated level can lock at -6 dB without pushing the hits over the voice."""
import sys, subprocess
import numpy as np
from dsp import SR, ns, tt, rng, lp, hp, bp, colored, smooth_noise, fades, phase, pan, st, place, write_wav
from sfx_gen import rattle, whoosh, breeze, splash_big, clink, crickets, bird_chirps

FPS = 30.0
F = lambda f: f / FPS

# ---------------- cue table (frames) ----------------
LAST_WORD = 1832
AMBIENCE = [(0, 640, "day"), (640, 1185, "rain"), (1185, 1560, "night"), (1560, 1860, "rain")]   # (from, to, kind)
WHOOSH = [150, 450, 462, 572, 1010, 1062, 1640, 1700]
RAIN = (640, 1700)                 # rain bed (frames)
THUNDER = [990, 1101, 1585, 1668, 1745]
SPLASH = [711, 1076]
RATTLE = [(0, 700), (760, 1050)]    # cart wheels on the road
BRAKES = 1030
FIZZ = [(0, 120), (1290, 1530), (1648, 1718)]
LAUNCH = 1718
POPS = [1758, 1772, 1788, 1802]


def voice_len(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return len(raw) // 4


def thunder(r, dur=3.0):
    n = ns(dur); t = np.arange(n) / SR
    crack = bp(r.standard_normal(n), 300, 4000, 1) * np.exp(-t / 0.05)
    roll = lp(colored(n, r, 1.4), 160, 2) * (0.5 + 0.5 * smooth_noise(n, r, 3)) * np.exp(-t / 1.1)
    return fades(crack * 0.6 + roll * 2.2, 0.002, 0.3)


def boom(r, a=1.0, dur=3.2):
    n = ns(dur); t = np.arange(n) / SR
    sub = np.sin(phase(42 * (1 + 1.5 * np.exp(-t / 0.08)))) * np.exp(-t / 0.6)
    body = lp(colored(n, r, 1.0), 900, 2) * np.exp(-t / 0.45)
    crackle = bp(r.standard_normal(n), 2000, 9000, 1) * (smooth_noise(n, r, 40) > 0.75) * np.exp(-t / 0.9) * 0.5
    return fades((sub * 1.6 + body * 1.2 + crackle) * a, 0.0005, 0.4)


def fizz(dur, r):
    n = ns(dur)
    return fades(hp(colored(n, r, -0.3), 2500, 2) * (0.6 + 0.4 * smooth_noise(n, r, 18)) * 0.25, 0.02, 0.05)


def sfx(N):
    r = rng(2); out = np.zeros((2, N))
    for f in WHOOSH: place(out, st(whoosh(0.45, r)), F(f) - 0.2, 0.8)
    a, b = RAIN; place(out, breeze(F(b - a), r, 0.6, bright=2500), F(a), 0.5)
    for f in THUNDER: place(out, pan(thunder(r), r.uniform(-0.5, 0.5)), F(f), 1.0)
    for f in SPLASH: place(out, st(splash_big(r)), F(f), 0.9)
    for a, b in RATTLE: place(out, st(rattle(F(b - a), r, 24)), F(a), 0.25)
    n = ns(0.9); place(out, st(bp(colored(n, r, 0) , 1800, 5000, 2) * np.linspace(1, 0, n) * 0.5), F(BRAKES))
    for a, b in FIZZ: place(out, st(fizz(F(b - a), r)), F(a))
    place(out, st(lp(colored(ns(2.5), r, 0.6), 1200, 2) * np.exp(-np.arange(ns(2.5)) / SR / 0.8)), F(LAUNCH), 1.2)
    for f in POPS: place(out, pan(boom(r, 0.45, 1.6), r.uniform(-0.6, 0.6)), F(f)); place(out, st(clink(r)), F(f) + 0.05, 0.4)
    place(out, st(boom(r, 1.2)), F(LAST_WORD))
    for k in range(10): place(out, pan(boom(r, 0.25, 1.2), r.uniform(-0.8, 0.8)), F(LAST_WORD) + 0.5 + 0.18 * k + r.uniform(0, 0.1))  # debris pops
    for a, b, kind in AMBIENCE:  # location bed, low
        d = F(b - a)
        if kind == "day": place(out, breeze(d, r, 0.35, bright=1500), F(a), 0.35); place(out, st(bird_chirps(d, r, 0.25)), F(a), 0.25)
        elif kind == "night": place(out, st(crickets(d, r)), F(a), 0.3); place(out, breeze(d, r, 0.25, bright=700), F(a), 0.3)
        else: place(out, breeze(d, r, 0.5, bright=3000), F(a), 0.35)
    return out


if __name__ == "__main__":
    voice, outdir = sys.argv[1], sys.argv[2]
    N = voice_len(voice)
    s = sfx(N)
    write_wav(f"{outdir}/sfx.wav", s / max(1e-9, np.abs(s).max()) * 0.5)
    print("sfx stem written (no music)", round(N / SR, 2), "s")
