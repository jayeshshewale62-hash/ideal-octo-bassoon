"""Audio: the user's voice (unedited, only shifted for silent cards), an original synthesized music bed,
SFX placed from shot events, a level-locked mix and loudness to -14 LUFS."""
import json, os, re, subprocess
import numpy as np, soundfile as sf
from scipy.signal import butter, lfilter, sosfilt

SR = 48000
rng = np.random.default_rng(5)


def lp(x, fc, o=2): b, a = butter(o, fc / (SR / 2), 'low'); return lfilter(b, a, x)
def hp(x, fc, o=2): b, a = butter(o, fc / (SR / 2), 'high'); return lfilter(b, a, x)
def bp(x, f1, f2): b, a = butter(2, [f1 / (SR / 2), f2 / (SR / 2)], 'band'); return lfilter(b, a, x)
def hz(n): return 440 * 2 ** ((n - 69) / 12)


def place(buf, x, t, gain=1.0, pan=0.0):
    i = int(t * SR)
    if i < 0: x = x[-i:]; i = 0
    if x.ndim == 1:
        l, r = np.cos((pan + 1) * np.pi / 4) * 1.414, np.sin((pan + 1) * np.pi / 4) * 1.414; x = np.stack([x * l, x * r], 1)
    j = min(i + len(x), len(buf))
    if i < len(buf): buf[i:j] += x[:j - i] * gain


# ---------------------------------------------------------------- instruments
def pluck(f, dur=0.34, amp=0.5, decay=10):
    n = int(dur * SR); t = np.arange(n) / SR; env = np.exp(-t * decay) * (1 - np.exp(-t * 500))
    return amp * env * (np.sin(2 * np.pi * f * t) + .5 * np.sin(4 * np.pi * f * t) + .22 * np.sin(6 * np.pi * f * t) + .1 * np.sin(8 * np.pi * f * t))
def bass(f, dur=0.42, amp=0.6):
    n = int(dur * SR); t = np.arange(n) / SR; env = np.exp(-t * 6) * (1 - np.exp(-t * 300))
    return amp * env * lp(np.sin(2 * np.pi * f * t) + .6 * np.sin(4 * np.pi * f * t) + .25 * np.sin(6 * np.pi * f * t), 900)
def vibes(f, dur=0.9, amp=0.2):
    n = int(dur * SR); t = np.arange(n) / SR; env = np.exp(-t * 4.5) * (1 - np.exp(-t * 900))
    return amp * env * (np.sin(2 * np.pi * f * t) + .3 * np.sin(2 * np.pi * 4 * f * t) * np.exp(-t * 14)) * (1 + .25 * np.sin(2 * np.pi * 5.5 * t))
def pad(freqs, dur, amp=0.05, lo=300, hi=3200, buzz=0.5):
    n = int(dur * SR); t = np.arange(n) / SR; out = np.zeros(n)
    for f in freqs:
        for d in (-1.8, 0, 2.1):
            ph = ((f + d) * t) % 1; out += (2 * ph - 1) + buzz * np.sign(np.sin(2 * np.pi * (f + d) * t))
    out = bp(out, lo, hi); env = np.minimum(1, t / .12) * np.minimum(1, (dur - t) / .2) * (1 + .12 * np.sin(2 * np.pi * 5 * t))
    return amp * out * env / len(freqs)
def brush(amp=0.06, dur=0.07):
    n = int(dur * SR); return amp * hp(rng.standard_normal(n), 5500) * np.exp(-np.arange(n) / SR * 55)
def kick(amp=0.4):
    n = int(.22 * SR); t = np.arange(n) / SR; return amp * np.sin(2 * np.pi * (48 + 70 * np.exp(-t * 34)) * t) * np.exp(-t * 15)
def snap(amp=.12):
    n = int(.12 * SR); t = np.arange(n) / SR; return amp * bp(rng.standard_normal(n), 1200, 6000) * np.exp(-t * 40)


# ---------------------------------------------------------------- moods (original progressions)
MOODS = {
    # bpm, chords [(root midi, [chord midi])], bass walk offsets, motifs, pad (lo, hi, buzz), drums
    "mystery": dict(bpm=104, prog=[(45, [57, 60, 64]), (41, [53, 57, 60]), (38, [50, 53, 57]), (40, [52, 56, 59])],
                    walk=[[0, 3, 7, 3], [0, 4, 7, 4], [0, 3, 7, 10], [0, 4, 7, 11]],
                    motifs=[[76, None, 75, 76, None, 72, None, None], [None, 69, None, 72, 71, None, 69, None], [77, None, 76, 74, None, 72, None, 74], [None, 71, 72, None, 76, None, 80, None]],
                    pad=(300, 3200, .5), drums="swing"),
    "upbeat": dict(bpm=112, prog=[(48, [60, 64, 67]), (43, [55, 59, 62]), (45, [57, 60, 64]), (41, [53, 57, 60])],
                   walk=[[0, 7, 12, 7], [0, 7, 12, 7], [0, 7, 12, 7], [0, 7, 12, 7]],
                   motifs=[[72, None, 76, None, 79, None, 76, None], [74, None, 79, None, 83, None, 79, 77], [76, None, 72, None, 69, None, 72, None], [77, 76, 74, None, 72, None, None, None]],
                   pad=(400, 4000, .2), drums="pop"),
    "dramatic": dict(bpm=84, prog=[(38, [50, 53, 57]), (46, [58, 62, 65]), (41, [53, 57, 60]), (45, [57, 61, 64])],
                     walk=[[0, 0, 12, 0], [0, 0, 12, 0], [0, 0, 12, 0], [0, 0, 12, 7]],
                     motifs=[[74, None, None, 72, None, None, 69, None], [None, None, 74, None, 77, None, None, None], [72, None, None, 69, None, None, 65, None], [None, None, 73, None, 76, None, 73, None]],
                     pad=(200, 2200, .2), drums="heavy"),
    "calm": dict(bpm=76, prog=[(41, [53, 57, 60, 64]), (43, [55, 59, 62, 65]), (45, [57, 60, 64, 67]), (38, [50, 53, 57, 60])],
                 walk=[[0, 7, 12, 7], [0, 7, 12, 7], [0, 7, 12, 7], [0, 7, 12, 7]],
                 motifs=[[72, None, 76, None, 79, None, 76, None], [74, None, 77, None, 81, None, 77, None], [76, None, 79, None, 83, None, 79, None], [72, None, 77, None, 81, None, 77, None]],
                 pad=(250, 2400, .1), drums="none"),
    "tense": dict(bpm=96, prog=[(40, [52, 55, 59]), (40, [52, 55, 60]), (41, [53, 56, 60]), (39, [51, 55, 58])],
                  walk=[[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
                  motifs=[[None, 76, None, None, 75, None, None, None], [None, None, 79, None, None, 78, None, None], [None, 77, None, None, 76, None, None, None], [None, None, 75, None, 74, None, 71, None]],
                  pad=(180, 1800, .3), drums="pulse"),
}


def music_bed(L, mood, mutes):
    M = MOODS.get(mood, MOODS["mystery"]); beat = 60 / M["bpm"]; e8 = beat / 2; bar = 4 * beat
    out = np.zeros((int((L + 3) * SR), 2)); t = 0.0; bi = 0
    while t < L:
        sec = (bi // 8) % 6  # arrangement: every 8 bars change texture
        root, ch = M["prog"][bi % 4]; muted = any(a - bar * .5 < t < b - .1 for a, b in mutes)
        if not muted:
            lo, hi, bz = M["pad"]
            place(out, pad([hz(n) for n in ch], bar * .98, 0.05 if sec != 3 else .035, lo, hi, bz), t, 1.0, -0.2)
            if sec != 3:
                for i, off in enumerate(M["walk"][bi % 4]): place(out, bass(hz(root + off), beat * .95, .55), t + i * beat)
            if M["drums"] != "none" and sec not in (0, 3):
                for i in (1, 3): place(out, sum(pluck(hz(n + 12), .2, .16) for n in ch[:3]), t + i * beat, 1.0, 0.25)
            if (bi % 2 == 0 and sec in (1, 2, 4)) or sec == 5:
                mot = M["motifs"][(bi + sec) % 4]
                for i, n in enumerate(mot):
                    if n: place(out, vibes(hz(n), .8, .14), t + i * e8, 1.0, -0.3 + .08 * i)
            d = M["drums"]
            if d != "none" and sec not in (0, 3):
                for i in range(8): place(out, brush(.06 if i % 2 == 0 else .035), t + i * e8 + (0.03 if (i % 2 and d == "swing") else 0), 1.0, 0.3)
                for i in ((0, 2) if d in ("swing", "pop") else (0,) if d == "heavy" else (0, 1, 2, 3)): place(out, kick(.32 if d != "pulse" else .2), t + i * beat)
                if d == "pop":
                    for i in (1, 3): place(out, snap(.1), t + i * beat, 1.0, .1)
        t += bar; bi += 1
    return out


# ---------------------------------------------------------------- SFX
def whoosh(dur=0.5):
    n = int(dur * SR); x = rng.standard_normal(n); out = np.zeros(n); seg = 600
    for i in range(0, n, seg):
        u = i / n; fc = 350 + 5200 * np.sin(np.pi * u) ** 1.3; y = bp(x[i:i + seg], max(fc * .55, 120), min(fc * 1.6, 16000)); out[i:i + len(y)] = y
    return out * np.sin(np.pi * np.arange(n) / n) ** 2 * 1.3
def popfx(f0=340): n = int(.13 * SR); t = np.arange(n) / SR; return np.sin(2 * np.pi * (f0 + 900 * np.exp(-t * 42)) * t) * np.exp(-t * 34) * .6
def thud(big=True):
    n = int(.7 * SR); t = np.arange(n) / SR
    out = np.sin(2 * np.pi * (42 + 95 * np.exp(-t * 26)) * t) * np.exp(-t * 8) + lp(rng.standard_normal(n), 2800) * np.exp(-t * 38) * .7
    if big: out += hp(rng.standard_normal(n), 3500) * np.exp(-t * 7) * .22
    return out * .9
def tick(): n = int(.016 * SR); return hp(rng.standard_normal(n), 2800) * np.exp(-np.arange(n) / SR * 280) * .5
def step(): n = int(.09 * SR); t = np.arange(n) / SR; return lp(rng.standard_normal(n), 1400) * np.exp(-t * 60) * .8 + np.sin(2 * np.pi * 150 * t) * np.exp(-t * 50) * .5
def shutter():
    out = np.zeros(int(.45 * SR)); a = tick() * 2.2; out[:len(a)] += a; k = int(.07 * SR); out[k:k + len(a)] += a
    t = np.arange(len(out)) / SR; out += hp(rng.standard_normal(len(out)), 6000) * np.exp(-t * 12) * .12; return out
def scribble(dur=.42): n = int(dur * SR); t = np.arange(n) / SR; return bp(rng.standard_normal(n), 1400, 5200) * (0.5 + 0.5 * np.sin(2 * np.pi * 13 * t)) * .26
def boom(): n = int(1.6 * SR); t = np.arange(n) / SR; return np.sin(2 * np.pi * 36 * t) * np.exp(-t * 2.4) * .8 + lp(rng.standard_normal(n), 180) * np.exp(-t * 3) * .4
def ding(): n = int(.9 * SR); t = np.arange(n) / SR; return (np.sin(2 * np.pi * 2637 * t) + .5 * np.sin(2 * np.pi * 3951 * t)) * np.exp(-t * 7) * .25
def paper(): n = int(.35 * SR); t = np.arange(n) / SR; return bp(rng.standard_normal(n), 900, 7000) * np.sin(np.pi * t / .35) ** 2 * .35
def sting():
    out = np.zeros(int(1.8 * SR))
    for n, g in ((45, .3), (57, .25), (64, .22), (68, .18), (72, .15)): out += np.pad(vibes(hz(n), 1.6, g) + pluck(hz(n), 1.6, .2, 4), (0, int(.2 * SR)))[:len(out)]
    return out
def clack(): n = int(.08 * SR); t = np.arange(n) / SR; return (bp(rng.standard_normal(n), 900, 4200) * np.exp(-t * 70) + np.sin(2 * np.pi * 520 * t) * np.exp(-t * 60) * .4) * .7
def rumble(dur=1.2):
    n = int(dur * SR); t = np.arange(n) / SR; env = np.minimum(1, t / .08) * np.clip((dur - t) / .4, 0, 1)
    return (lp(rng.standard_normal(n), 120, 2) * 3 + np.sin(2 * np.pi * 31 * t) * .4) * env * .8
def whoosh_soft(): return whoosh(1.1) * .35
SFX = dict(clack=clack, whoosh_soft=whoosh_soft, pop=lambda: popfx(rng.uniform(320, 440)), thud=thud, whoosh=lambda: whoosh(.45), tick=tick, shutter=shutter, scribble=scribble,
           boom=boom, ding=ding, paper=paper, step=step, sting=sting)


# ---------------------------------------------------------------- ambience beds (room tone under each place)
def _noise(n, lo=None, hi=None):
    x = rng.standard_normal(n)
    if lo and hi: return bp(x, lo, hi)
    if hi: return lp(x, hi)
    if lo: return hp(x, lo)
    return x
def amb_room(n):
    t = np.arange(n) / SR; return _noise(n, hi=260) * 1.6 + np.sin(2 * np.pi * 60 * t) * .015 + _noise(n, 2000, 6000) * .04
def amb_street(n):
    t = np.arange(n) / SR; base = _noise(n, hi=500) * 1.4; cars = np.zeros(n)
    k = 0
    while k < n:  # cars passing: slow swells every few seconds
        d = int(rng.uniform(2.5, 5.0) * SR); w = np.sin(np.pi * np.arange(min(d, n - k)) / d) ** 2; cars[k:k + len(w)] += w * rng.uniform(.5, 1); k += int(d * rng.uniform(.6, 1.4))
    return base * (.5 + .7 * cars) + _noise(n, 1500, 5000) * .05 * cars
def amb_night(n):
    t = np.arange(n) / SR; chirp = np.sin(2 * np.pi * 4300 * t) * (np.sin(2 * np.pi * 28 * t) > .2) * ((t % .9) < .22)
    return chirp * .05 + _noise(n, 150, 600) * .5
def amb_rain(n):
    x = _noise(n, 900, 9000) * .8; crack = (rng.random(n) < 0.0016) * rng.standard_normal(n) * 4; return x + hp(crack, 2500)
def amb_crowd(n):
    t = np.arange(n) / SR; out = np.zeros(n)
    for f0 in (320, 520, 760, 1100):
        out += _noise(n, f0 * .8, f0 * 1.3) * (0.6 + 0.4 * np.sin(2 * np.pi * rng.uniform(2.5, 5.5) * t + rng.uniform(0, 6)))
    return out * .9
def amb_wind(n):
    t = np.arange(n) / SR; return _noise(n, 180, 900) * (0.6 + 0.4 * np.sin(2 * np.pi * .13 * t) + .2 * np.sin(2 * np.pi * .31 * t))
def amb_clock(n):
    out = amb_room(n) * .7; tk = tick() * .5
    for k in range(0, n - len(tk), SR): out[k:k + len(tk)] += tk * (1.0 if (k // SR) % 2 == 0 else .7)
    return out
def amb_city(n): return amb_street(n) * .5 + _noise(n, hi=200) * .8
AMBIENCE = dict(room=amb_room, street=amb_street, night=amb_night, rain=amb_rain, crowd=amb_crowd, wind=amb_wind, clock=amb_clock, city=amb_city)
SET_AMBIENCE = dict(office="room", home="room", street="street", skyline="city")


def ambience_spans(tl):
    """[(name, t0, t1)] merged over consecutive shots. World shots get room tone from their set; "ambience" overrides;
    graphics shots inherit the previous place's tone (the viewer is still 'there'), silent title cards cut it."""
    from .render import DEFAULT_SET
    spans = []; cur = None
    for s in tl.shots:
        sp = s["spec"]; k = sp.get("kind", "wide")
        if "ambience" in sp: name = sp["ambience"]
        elif k in DEFAULT_SET: name = SET_AMBIENCE.get(sp.get("set", DEFAULT_SET[k]))
        elif k == "title": name = None
        else: name = cur
        if k in ("crowd",) and "ambience" not in sp: name = "crowd"
        if name in (None, "none"): name = None
        elif name not in AMBIENCE: raise SystemExit(f"shot {s['k']}: unknown ambience '{name}'. Ambience: {', '.join(AMBIENCE)}, none")
        if name and spans and spans[-1][0] == name and abs(spans[-1][2] - s["t0"]) < 1e-6: spans[-1][2] = s["t1"]
        elif name: spans.append([name, s["t0"], s["t1"]])
        cur = name
    return spans


def ambience_bed(tl, N, lead=1.0, tail=.6):
    """Each place's tone starts `lead` s before its cut (J-cut: we hear the next scene first) and lingers `tail` s (L-cut)."""
    out = np.zeros((N, 2))
    for name, a, b in ambience_spans(tl):
        a0 = max(0.0, a - lead); b1 = min(N / SR, b + tail); n = int((b1 - a0) * SR)
        if n <= 0: continue
        x = AMBIENCE[name](n); t = np.arange(n) / SR; env = np.minimum(1, t / max(lead, .05)) * np.clip((b1 - a0 - t) / max(tail, .05), 0, 1)
        x = x / (np.sqrt(np.mean(x ** 2)) + 1e-9) * env; st = np.stack([x, np.roll(x, int(.011 * SR))], 1)
        place(out, st, a0)
    return out


def build(P, mood=None, music_db=-17.0, sfx_db=-9.0, amb_db=-30.0):
    from .render import setup, _G, whip_flags
    from .shots import build as build_shot
    setup(P); tl = _G["tl"]; story = _G["story"]; mood = mood or story.get("mood", "mystery")
    from .render import voice_path
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", voice_path(P), "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    vx = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).astype(np.float64)
    L = tl.duration; N = int(L * SR) + SR; voice = np.zeros((N, 2))
    for (a, b, o) in tl.voice_segments(): place(voice, vx[int(a * SR):int(b * SR)], o)
    mutes = [(s["t0"], s["t1"]) for s in tl.shots if s["silent"] and s["spec"].get("kind") == "title"]
    music = music_bed(L, mood, mutes)[:N]; sfx = np.zeros((N, 2)); whips = whip_flags(tl)
    for (a, b) in mutes: place(sfx, boom(), a, .6)
    for i, s in enumerate(tl.shots):
        if whips[i]: place(sfx, whoosh(.45), s["t1"] - .3, .45, rng.uniform(-.3, .3))
        if s["spec"].get("kind") == "title" and not s["silent"]: place(sfx, boom(), s["t0"], .4)
        shot = build_shot(s, tl, _G["cast"], _G["env"]) if True else None
        for ev in shot.sfx_events():
            name, t = ev[0], ev[1]
            if name == "rumble": place(sfx, rumble(ev[2] if len(ev) > 2 else 1.2), t, .9); continue
            if name == "steps":
                walk_d = (s["t1"] - s["t0"]) if any(a.walk for a in shot.actors) else 1.1
                for k in range(int(walk_d / .285)): place(sfx, step(), t + .1 + k * .285, .35, -.4 + .03 * k)
            elif name == "tick":
                for k in range(18): place(sfx, tick(), t + .05 + k * .07, .35, .2)
            elif name in SFX: place(sfx, SFX[name](), t, .8 if name != "thud" else 1.0, rng.uniform(-.3, .3))
        if shot.pol: place(sfx, sting(), shot.pol["t"], .5)
    sfx += (lp(rng.standard_normal(N), 400) * 0.003)[:, None]
    # ---- level lock (gated RMS of the voice is the reference; the voice itself is untouched)
    vm = np.abs(voice).mean(1); env = lp(vm, 6, 1); gate = env > np.percentile(env[env > 0], 40) * .5 if (env > 0).any() else env > 0
    vref = np.sqrt(np.mean(voice[gate] ** 2)) if gate.any() else .1
    mref = np.sqrt(np.mean(music[np.abs(music).mean(1) > 1e-5] ** 2)) + 1e-9
    music *= vref * 10 ** (music_db / 20) / mref
    speech = np.clip(env / (np.percentile(env[gate], 50) + 1e-9), 0, 1) if gate.any() else np.zeros(N)
    duck = 1 - .45 * lp(speech, 3, 1).clip(0, 1); music *= duck[:, None]
    tt = np.arange(N) / SR; music *= np.minimum(1, tt / .4)[:, None] * np.clip((L - .2 - tt) / 1.2, 0, 1)[:, None]
    srms = np.sqrt(np.mean(sfx[np.abs(sfx).mean(1) > 1e-3] ** 2)) + 1e-9 if (np.abs(sfx).mean(1) > 1e-3).any() else 1.0
    sfx *= vref * 10 ** (sfx_db / 20) / srms; vpk = np.abs(voice).max() + 1e-9; spk = np.abs(sfx).max()
    if spk > .7 * vpk: sfx *= .7 * vpk / spk
    amb = ambience_bed(tl, N); arms = np.sqrt(np.mean(amb[np.abs(amb).mean(1) > 1e-6] ** 2)) + 1e-9 if (np.abs(amb).mean(1) > 1e-6).any() else 1.0
    amb *= vref * 10 ** (amb_db / 20) / arms; amb *= (1 - .3 * lp(speech, 3, 1).clip(0, 1))[:, None]
    mix = voice + music + sfx + amb
    os.makedirs(os.path.join(P, "work"), exist_ok=True); rawp = os.path.join(P, "work", "mix_raw.wav"); sf.write(rawp, mix[:int(L * SR)].astype(np.float32), SR)
    for nm, x in (("voice", voice), ("music", music), ("sfx", sfx), ("ambience", amb)): sf.write(os.path.join(P, "work", f"stem_{nm}.wav"), x[:int(L * SR)].astype(np.float32), SR)
    db = lambda x: 20 * np.log10(np.sqrt(np.mean(x[gate] ** 2)) + 1e-12)
    print(f"levels in speech: voice {db(voice):.1f} dBFS, music {db(music) - db(voice):+.1f} dB, sfx peak {20 * np.log10(np.abs(sfx).max() / vpk + 1e-9):+.1f} dB vs voice peak, ambience {db(amb) - db(voice):+.1f} dB")
    return rawp


def loudness(src, dst, target=-14.0):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-af", f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    m = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr)
    if not m: raise SystemExit("loudness measurement failed:\n" + r.stderr[-800:])
    js = json.loads(m[-1]); gain = target - float(js["input_i"])
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af", f"volume={gain:.2f}dB,alimiter=limit=0.84:level=false", "-ar", str(SR), dst], check=True)
    print(f"loudness: input {js['input_i']} LUFS -> gain {gain:+.1f} dB"); return dst


def mux(P, title="final"):
    v = os.path.join(P, "work", "video.mp4"); a = os.path.join(P, "work", "mix.wav")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_") or "final"; os.makedirs(os.path.join(P, "out"), exist_ok=True)
    if os.environ.get("RM_RES", "1080") != "1080": safe += f"_{os.environ['RM_RES']}p"
    out = os.path.join(P, "out", f"{safe}.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", v, "-i", a, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", out], check=True)
    print("final ->", out); return out
