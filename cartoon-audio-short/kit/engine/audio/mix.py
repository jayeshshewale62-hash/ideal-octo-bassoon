#!/usr/bin/env python3
"""mix.py voice music.wav sfx.wav [out.wav]
The voice is never touched (no gain, EQ, edit or retime). The music bed and the SFX stem are each locked to exactly
-6.0 dB (50 % gated RMS, BS.1770 integrated) below the voice. SFX peaks are capped below the voice peak
(0.7 x voice peak by default): the cap and the -6.0 dB gain are iterated together until both hold, so the SFX stem
lands at -6.0 dB, not lower. No ducking, no compression on the voice or music: one gain per stem + the SFX peak cap.
Prints the measured levels; exit code 2 if a stem misses -6.0 +/- 0.1 dB or an SFX peak pokes over the cap."""
import sys, subprocess
import numpy as np
from dsp import SR, integrated, read_wav, write_wav, st

TARGET = -6.0      # dB relative to the voice (gated)
SFX_PEAK = 0.7     # SFX peaks capped at this fraction of the voice peak (always below the voice)


def load_voice(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64).reshape(-1, 2).T


def _sliding_min(a, L):
    """minimum over a centred window of 2L+1 samples (pure numpy, O(n log L))"""
    out = a.copy(); w = 1
    while w <= L:
        sh = np.minimum(np.r_[out[w:], np.full(w, out[-1])], np.r_[np.full(w, out[0]), out[:-w]])
        out = np.minimum(out, sh); w *= 2
    return out


def peak_cap(x, ceiling, look=0.003, rel=0.08):
    """lookahead peak limiter on one stem: gain < 1 only where |x| would exceed the ceiling"""
    a = np.abs(x).max(0)
    need = np.minimum(1.0, ceiling / np.maximum(a, 1e-12))
    g = _sliding_min(need, int(look * SR))
    k = np.exp(-1.0 / (rel * SR))
    out = np.empty_like(g); cur = 1.0
    for i in range(len(g)):  # one-pole release
        cur = g[i] if g[i] < cur else cur * k + g[i] * (1 - k)
        out[i] = cur
    return x * np.minimum(out, need)[None, :]


def lock(stem, Lv, ceiling=None, iters=8):
    """gain the stem to Lv + TARGET; with a ceiling, alternate gain + peak cap until both hold"""
    y = stem.copy()
    for _ in range(iters):
        Ls = integrated(y)
        if not np.isfinite(Ls):
            return y
        y *= 10 ** ((Lv + TARGET - Ls) / 20)
        if ceiling is None:
            return y
        y = peak_cap(y, ceiling)
        if abs(integrated(y) - (Lv + TARGET)) < 0.05:
            break
    return y


if __name__ == "__main__":
    v = load_voice(sys.argv[1]); m, _ = read_wav(sys.argv[2]); s, _ = read_wav(sys.argv[3])
    out = sys.argv[4] if len(sys.argv) > 4 else "mix.wav"
    n = v.shape[1]; m = st(m)[:, :n]; s = st(s)[:, :n]
    m = np.pad(m, ((0, 0), (0, n - m.shape[1]))); s = np.pad(s, ((0, 0), (0, n - s.shape[1])))
    Lv, vpk = integrated(v), np.abs(v).max()
    m = lock(m, Lv)
    s = lock(s, Lv, ceiling=SFX_PEAK * vpk)
    mix = v + m + s
    write_wav(out, mix)
    dm, ds, spk = integrated(m) - Lv, integrated(s) - Lv, np.abs(s).max() / vpk
    print(f"voice {Lv:.2f} LUFS  peak {20*np.log10(vpk):.2f} dBFS  (untouched)")
    print(f"music {dm:+.2f} dB vs voice (gated)   peak {20*np.log10(np.abs(m).max()):.2f} dBFS")
    print(f"sfx   {ds:+.2f} dB vs voice (gated)   peak {spk:.2f} x voice peak (cap {SFX_PEAK})")
    print(f"mix   {integrated(mix):.2f} LUFS  peak {20*np.log10(np.abs(mix).max()):.2f} dBFS  -> {out}")
    bad = abs(dm - TARGET) > 0.1 or abs(ds - TARGET) > 0.1 or spk > SFX_PEAK + 0.01
    if bad:
        print("WARNING: level lock missed (music/SFX must read -6.0 dB, SFX peaks below the voice). If the SFX stem is "
              "all sharp hits, add a quiet bed (wind / room tone) so its gated level can reach -6 dB under the cap.")
        sys.exit(2)
