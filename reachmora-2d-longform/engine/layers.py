"""2.5D depth layers: out-of-focus foreground silhouettes (drawn once per shot into a cached image) and
cheap per-frame particles. Both move at a different speed from the character plane (see camera.layer)."""
import math, random
import skia
from .kit import *

FG_INK = '#0C0E1C'


def _leaf(c, x, y, ang, L, w, v):
    c.save(); c.translate(x, y); c.rotate(ang); p = skia.Path(); p.moveTo(0, 0); p.quadTo(w, -L * .5, 0, -L); p.quadTo(-w, -L * .5, 0, 0); p.close()
    c.drawPath(p, fp(v)); c.restore()


def fg_plants(c, o):
    v = o.get("fg_color", FG_INK)
    for (bx, flip) in ((-120, 1), (W + 120, -1)):
        for i in range(9):
            _leaf(c, bx + flip * (i * 22), H + 60, flip * (8 + i * 9), 420 + (i % 3) * 90, 70, v)


def fg_lamp(c, o):
    v = o.get("fg_color", FG_INK); x = o.get("fg_x", 260)
    c.drawRect(skia.Rect(x - 6, -400, x + 6, 120), fp(v))
    sh = skia.Path(); sh.moveTo(x - 150, 300); sh.lineTo(x - 60, 110); sh.lineTo(x + 60, 110); sh.lineTo(x + 150, 300); sh.close(); c.drawPath(sh, fp(v))
    c.drawOval(skia.Rect(x - 150, 280, x + 150, 320), fp('#FFD98A', 120))


def fg_frame(c, o):  # door / window frame edges: "we're watching from the next room"
    v = o.get("fg_color", FG_INK)
    c.drawRect(skia.Rect(-500, -300, 230, H + 300), fp(v)); c.drawRect(skia.Rect(W - 190, -300, W + 500, H + 300), fp(v))
    c.drawRect(skia.Rect(-500, -300, W + 500, 40), fp(v))


def fg_desk(c, o):
    v = o.get("fg_color", FG_INK)
    c.drawRect(skia.Rect(-500, H - 120, W + 500, H + 300), fp(v))
    c.drawRRect(skia.RRect.MakeRectXY(skia.Rect(1500, H - 300, 1640, H - 110), 18, 18), fp(v)); c.drawCircle(1680, H - 220, 46, fp(v))
    c.drawCircle(1680, H - 220, 26, fp('#1E2238'))


def fg_heads(c, o):  # audience / crowd backs of heads
    v = o.get("fg_color", FG_INK); r = random.Random(4)
    for i in range(9):
        x = -80 + i * 260 + r.uniform(-40, 40); y = H + 40 + r.uniform(-30, 30); s = r.uniform(1.0, 1.3)
        c.drawCircle(x, y - 210 * s, 120 * s, fp(v)); c.drawRRect(skia.RRect.MakeRectXY(skia.Rect(x - 190 * s, y - 120 * s, x + 190 * s, y + 300), 90, 90), fp(v))


def fg_posts(c, o):  # street posts / railing passing the lens on a glide
    v = o.get("fg_color", FG_INK)
    for x in (-200, 560, 1320, 2080):
        c.drawRect(skia.Rect(x, 200, x + 70, H + 300), fp(v)); c.drawRect(skia.Rect(x - 20, 180, x + 90, 220), fp(v))
    c.drawRect(skia.Rect(-500, H - 140, W + 500, H - 110), fp(v))


FG = dict(plants=fg_plants, lamp=fg_lamp, frame=fg_frame, desk=fg_desk, heads=fg_heads, posts=fg_posts)


# ------------------------------------------------------------------ particles
class Particles:
    """Slow ambient motion that keeps a held frame alive: dust motes, snow, rain, embers, sparkles, bokeh."""
    KINDS = ("dust", "snow", "rain", "embers", "sparkle", "bokeh")

    def __init__(self, kind, seed=1, night=True, density=1.0):
        if kind not in self.KINDS: raise SystemExit(f"unknown particles '{kind}'. Particles: {', '.join(self.KINDS)}")
        self.kind = kind; r = random.Random(seed); n = int({"dust": 34, "snow": 70, "rain": 90, "embers": 30, "sparkle": 26, "bokeh": 12}[kind] * density)
        self.p = [(r.uniform(-300, W + 300), r.uniform(-200, H + 200), r.uniform(.5, 1.0), r.uniform(0, 6.28)) for _ in range(n)]
        self.night = night

    def draw(self, c, t):
        k = self.kind
        for (x, y, z, ph) in self.p:
            if k == "dust":  # drifting motes catching the light
                px = x + 18 * math.sin(t * .35 * z + ph) + t * 6 * z; py = y + 14 * math.sin(t * .27 + ph * 1.3) - t * 4 * z
                px = (px + 300) % (W + 600) - 300; py = (py + 200) % (H + 400) - 200
                a = (70 + 60 * math.sin(t * 1.3 + ph)) * (1 if self.night else .55); c.drawCircle(px, py, 2.2 + 2.6 * z, fp('#FFF1C8', a))
            elif k == "snow":
                px = x + 30 * math.sin(t * .8 + ph); py = (y + t * 90 * z + 200) % (H + 400) - 200
                c.drawCircle(px, py, 3 + 4 * z, fp('#FFFFFF', 200 * z))
            elif k == "rain":
                px = (x - t * 160 * z + 300) % (W + 600) - 300; py = (y + t * 1500 * z + 200) % (H + 400) - 200
                c.drawLine(px, py, px - 8, py + 46 * z, ink(2.2, '#B8C8F0', 110 * z))
            elif k == "embers":
                px = x + 26 * math.sin(t * 1.1 + ph); py = (y - t * 70 * z + 200) % (H + 400) - 200
                a = 160 + 90 * math.sin(t * 6 + ph); c.drawCircle(px, py, 2.5 + 3 * z, fp('#FFB347', a)); c.drawCircle(px, py, 9 * z, fp('#FF7A2A', 40))
            elif k == "sparkle":
                s = max(0.0, math.sin(t * 2.2 * z + ph)) ** 3 * 16 * z
                if s > 1:
                    st = skia.Path()
                    for i in range(8):
                        rr = s if i % 2 == 0 else s * .25; a = i * math.pi / 4; (st.moveTo if i == 0 else st.lineTo)(x + rr * math.cos(a), y + rr * math.sin(a))
                    st.close(); c.drawPath(st, fp('#FFF6DC', 230))
            elif k == "bokeh":
                px = x + 40 * math.sin(t * .2 + ph); py = y + 30 * math.sin(t * .17 + ph); r = 40 + 50 * z
                for rr, a in ((r, 22), (r * .8, 18), (r * .55, 16)): c.drawCircle(px, py, rr, fp('#FFE3A0', a))
