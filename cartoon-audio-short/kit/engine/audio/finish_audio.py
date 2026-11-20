#!/usr/bin/env python3
"""finish_audio.py mix.wav out.wav  -> master: -14.0 LUFS integrated, LRA 2.4-2.9 LU, -1.0 dBFS (true) peak ceiling.
1. LRA fit: if the mix's loudness range is outside 2.4-2.9 LU, a slow whole-mix leveller (3 s short-term loudness,
   gain = -k * (S - I), clamped +/-4 dB, 1.5 s smoothing) is solved for k so LRA lands on 2.65 LU. It acts on the summed
   mix, so music and SFX stay locked at -6.0 dB vs the voice; it only rides slow level, never timbre or timing.
   Pass --no-lra to skip it (then only one linear gain is applied).
2. One linear gain to -14.0 LUFS, then a lookahead peak limiter; the ceiling is lowered until the 4x-oversampled true
   peak is <= -1.0 dBTP."""
import sys
import numpy as np
from dsp import SR, read_wav, write_wav, integrated, true_peak, lra, short_term
from mix import peak_cap

LRA_LO, LRA_HI, LRA_T = 2.4, 2.9, 2.65


def level_curve(x, k):
    hop = 0.1
    S = short_term(x, hop)
    I = integrated(x)
    S = np.where(np.isfinite(S) & (S > I - 20), S, I)
    g_db = np.clip(-k * (S - I), -4, 4)
    w = int(1.5 / hop); ker = np.hanning(2 * w + 1); ker /= ker.sum()
    g_db = np.convolve(np.pad(g_db, w, mode="edge"), ker, mode="valid")
    t = (np.arange(len(g_db)) * hop + 1.5) * SR
    return 10 ** (np.interp(np.arange(x.shape[1]), t, g_db) / 20)


def fit_lra(x):
    L0 = lra(x)
    if LRA_LO <= L0 <= LRA_HI:
        return x, 0.0, L0
    lo, hi = (0.0, 0.95) if L0 > LRA_HI else (-1.5, 0.0)
    best = (x, 0.0, L0)
    for _ in range(14):  # LRA falls monotonically as k grows
        k = (lo + hi) / 2
        y = x * level_curve(x, k)[None, :]
        Ly = lra(y)
        best = min(best, (y, k, Ly), key=lambda b: abs(b[2] - LRA_T))
        if Ly > LRA_T:
            lo = k
        else:
            hi = k
    return best


if __name__ == "__main__":
    x, sr = read_wav(sys.argv[1])
    L0, R0 = integrated(x), lra(x)
    k = 0.0
    if "--no-lra" not in sys.argv:
        x, k, _ = fit_lra(x)
    y = x * 10 ** ((-14.0 - integrated(x)) / 20)
    ceil = -1.0
    for _ in range(8):
        z = peak_cap(y, 10 ** (ceil / 20), look=0.002, rel=0.05)
        tp = true_peak(z)
        if tp <= -1.0:
            break
        ceil -= (tp + 1.0) + 0.05
    write_wav(sys.argv[2], z)
    I, R = integrated(z), lra(z)
    print(f"in {L0:.2f} LUFS, LRA {R0:.2f} LU -> out {I:.2f} LUFS, LRA {R:.2f} LU (leveller k={k:+.2f}), true peak {tp:.2f} dBTP")
    ok = abs(I + 14.0) <= 0.3 and LRA_LO - 0.05 <= R <= LRA_HI + 0.05 and tp <= -0.95
    if not ok:
        print("WARNING: master outside spec (-14.0 LUFS, LRA 2.4-2.9 LU, <= -1.0 dBTP)")
        sys.exit(2)
