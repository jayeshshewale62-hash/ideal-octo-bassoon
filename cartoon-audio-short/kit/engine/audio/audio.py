#!/usr/bin/env python3
"""Music + SFX stems (all original synthesis). Template = the v2 demo "The Grocer's Rocket Cart" (62 s).
usage: python3 audio.py <voice> <outdir> [story_frames.json]   -> outdir/music.wav, outdir/sfx.wav (48 kHz stereo, voice length)
Rewrite CUES / MUSIC_STOP for each story (event times in frames at 30 fps, taken from story.js / work/words.json); the
synths stay. Levels do not matter here: mix.py locks both stems to -6.0 dB under the voice.
Music: plucked-bass + brass-pad march loop in D, snare on 2/4; it stops before the cutaway question (the mystery beat
runs on a low drone + timpani roll), returns for the payoff and ends on a cymbal + low hit with the last word.
SFX: whooshes on whip-glides, cart rattle, rain bed, thunder on lightning, splash on the slip / dive, van brakes,
fuse fizz, rocket launch, firework pops, final explosion. Continuous beds stay low so the hits carry."""
import sys, subprocess
import numpy as np
from dsp import SR, ns, tt, rng, lp, hp, bp, colored, smooth_noise, fades, phase, pan, st, place, write_wav
from instruments import m2f, pluck, pad, snare, cymbal, timpani, glock
from sfx_gen import rattle, whoosh, breeze, splash_big, clink

FPS = 30.0
F = lambda f: f / FPS

# ---------------- cue table (frames) ----------------
MUSIC_STOP, DRONE_TO, MUSIC_BACK, LAST_WORD = 1150, 1555, 1700, 1832
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


def music(N):
    r = rng(1); out = np.zeros((2, N)); bpm = 112; beat = 60 / bpm
    prog = [[50, 57, 62], [55, 59, 62], [57, 61, 64], [50, 57, 62]]  # D G A D
    t, bar = 0.0, 0
    while t < F(LAST_WORD) + 0.2:
        on = t < F(MUSIC_STOP) or t >= F(MUSIC_BACK)
        if on:
            ch = prog[bar % 4]
            place(out, pad([m2f(n) for n in ch], beat * 4, 0.35, r), t)
            for b in range(4):
                place(out, pan(pluck(m2f(ch[0] - 12 + (7 if b % 2 else 0)), 0.8, r, beat), -0.1), t + b * beat)
                if b in (1, 3): place(out, pan(snare(0.5, r), 0.15), t + b * beat)
        t += beat * 4; bar += 1
    # mystery drone + timpani roll into the payoff
    dd = F(DRONE_TO) - F(MUSIC_STOP)
    place(out, pad([m2f(38), m2f(45)], dd, 0.5, r, att=1.2, rel=1.5, warm=500), F(MUSIC_STOP))
    for k in range(24): place(out, timpani(m2f(38), 0.2 + 0.6 * k / 24, r), F(DRONE_TO) - 1.6 + k * 0.066)
    # last-word sting
    place(out, cymbal(1.0, r, 3.0), F(LAST_WORD)); place(out, timpani(m2f(31), 1.0, r, 3.0), F(LAST_WORD))
    out[:, ns(F(LAST_WORD) + 3.0):] = 0
    return out


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
    for k in range(6): place(out, pan(glock(m2f(84 + 2 * k), 0.25, r), 0.3 - k * 0.1), F(LAST_WORD) + 0.4 + 0.12 * k)
    return out


if __name__ == "__main__":
    voice, outdir = sys.argv[1], sys.argv[2]
    N = voice_len(voice)
    m, s = music(N), sfx(N)
    write_wav(f"{outdir}/music.wav", m / max(1e-9, np.abs(m).max()) * 0.5)
    write_wav(f"{outdir}/sfx.wav", s / max(1e-9, np.abs(s).max()) * 0.5)
    print("stems written", round(N / SR, 2), "s")
