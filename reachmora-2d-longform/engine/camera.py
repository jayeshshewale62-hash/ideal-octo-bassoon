"""Virtual 2D camera: shot sizes, angles, presets, timed moves, handheld float and 2.5D parallax.

Every shot has one camera. Per frame it returns a CamState: zoom, focus (world point at frame centre),
rotation, screen offset and a vertical stretch used to fake low/high angles. Everything stays inside the
overscan bleed (sets are drawn PADX/PADY larger than the frame), so zooms, pans and shakes never show an edge.

story.json, per shot:
  "size":   ews | ws | ms | mcu | cu | ecu      frames the subject (who / first character) on a third
  "angle":  eye | low | high | dutch            power and emotion (dutch: use sparingly)
  "cam":    {"preset": creep|push|punch|reveal|glide|tilt_up|tilt_down|hold, "at": cue, "dur": s,
             "dir": "left"|"right", "zoom": [z0, z1], "focus": [[x, y], [x, y]], "float": true/false}
  "moves":  [{"type": punch|push|pull|thud|rumble|dutch|snap, "at": cue, ...}]   timed camera events
"""
import math
from .kit import W, H, FPS, ease, ease_out, lerp, K, HEAD_CY

PADX, PADY = 420, 260  # overscan bleed of every cached background (22 % / 24 % of the frame)

# shot size -> (visible height in character units at s=1, eye line on the upper third)
SIZES = {"ews": None, "ws": None, "ms": 700, "mcu": 520, "cu": 380, "ecu": 170}
SIZE_RANK = {"ews": 0, "ws": 1, "ms": 2, "mcu": 3, "cu": 4, "ecu": 5}
ANGLES = ("eye", "low", "high", "dutch")
PRESETS = ("creep", "push", "punch", "reveal", "glide", "tilt_up", "tilt_down", "hold")
MOVES = ("punch", "push", "pull", "thud", "rumble", "dutch", "snap")


class CamState:
    __slots__ = ("z", "fx", "fy", "rot", "dx", "dy", "sy")

    def __init__(self, z=1.0, fx=W / 2, fy=H / 2, rot=0.0, dx=0.0, dy=0.0, sy=1.0):
        self.z, self.fx, self.fy, self.rot, self.dx, self.dy, self.sy = z, fx, fy, rot, dx, dy, sy

    def tuple(self): return (self.z, self.fx, self.fy, self.rot, self.dx, self.dy, self.sy)


def apply(c, cs, OS):
    """Push the camera transform onto canvas c (design space -> output pixels). Pair with c.restore()."""
    c.save(); c.scale(OS, OS); c.translate(W / 2 + cs.dx, H / 2 + cs.dy); c.rotate(cs.rot); c.scale(cs.z, cs.z * cs.sy); c.translate(-cs.fx, -cs.fy)


def layer(c, cs, cs0, depth, pivot):
    """Inside apply(): re-transform for a layer at another depth (2.5D parallax).
    depth 1 = the character plane; <1 = background (moves slower), >1 = foreground (moves faster).
    pivot (x, y) stays locked to the character plane (the floor under the feet), so feet never slide on a zoom."""
    if depth == 1.0: return False
    r = (cs.z ** depth) / cs.z; sx = (1 - depth) * (cs.fx - cs0.fx); sy = (1 - depth) * (cs.fy - cs0.fy) if depth > 1 else 0.0
    c.save(); c.translate(pivot[0] + sx, pivot[1] + sy); c.scale(r, r); c.translate(-pivot[0], -pivot[1]); return True


def clamp(cs, margin=24):
    """Keep the view inside the overscan bleed (with room for a shake)."""
    z = max(cs.z, 1.0); hw = W / (2 * z) + margin / z; hh = H / (2 * z * cs.sy) + margin / z
    cs.fx = min(max(cs.fx, -PADX + hw), W + PADX - hw); cs.fy = min(max(cs.fy, -PADY + hh), H + PADY - hh)
    return cs


def jitter(t, seed=0.0):
    """Smooth pseudo-random wave in -1..1 (sum of incommensurate sines)."""
    return (math.sin(t * 1.13 + seed) * .5 + math.sin(t * 2.71 + seed * 1.7) * .3 + math.sin(t * 4.37 + seed * 2.3) * .2)


class Camera:
    def __init__(self, shot):
        self.sh = shot; sp = shot.spec; self.cam = dict(sp.get("cam") or {})
        self.size = sp.get("size"); self.angle = sp.get("angle", "eye")
        if self.size and self.size not in SIZES: raise SystemExit(f"shot {shot.sh['k']}: unknown size '{self.size}'. Sizes: {', '.join(SIZES)}")
        if self.angle not in ANGLES: raise SystemExit(f"shot {shot.sh['k']}: unknown angle '{self.angle}'. Angles: {', '.join(ANGLES)}")
        self.preset = self.cam.get("preset")
        if self.preset and self.preset not in PRESETS: raise SystemExit(f"shot {shot.sh['k']}: unknown cam preset '{self.preset}'. Presets: {', '.join(PRESETS)}")
        self.ph = (shot.sh["k"] * 1.618) % 6.28
        self.moves = []
        for m in list(sp.get("moves", [])) + shot.auto_moves:
            if m.get("type") not in MOVES: raise SystemExit(f"shot {shot.sh['k']}: unknown move '{m.get('type')}'. Moves: {', '.join(MOVES)}")
            self.moves.append(dict(m, t=shot.cue(m.get("at"), .5)))
            if m["type"] in ("thud",): shot.events.append(("thud", self.moves[-1]["t"]))
            if m["type"] == "punch": shot.events.append(("pop", self.moves[-1]["t"]))
            if m["type"] == "rumble": shot.events.append(("rumble", self.moves[-1]["t"], float(m.get("dur", 1.2))))
            if m["type"] in ("push", "pull"): shot.events.append(("whoosh_soft", self.moves[-1]["t"]))
        if self.preset in ("push", "punch"):
            self.pt = shot.cue(self.cam.get("at"), .35 if self.preset == "push" else .5)
            if self.preset == "punch": shot.events.append(("pop", self.pt))
        self.cs0 = None

    # framing on the subject ---------------------------------------------------------------
    def subject(self):
        a = self.sh.actor(self.sh.spec.get("who")) if self.sh.actors else None
        if a is None: return None
        return a.x, a.y, a.s

    def framing(self):
        """Base zoom + focus from size/angle (static for the shot)."""
        z, fx, fy = 1.0, W / 2, H / 2 + 5; sub = self.subject()
        if self.size in ("ms", "mcu", "cu", "ecu") and sub:
            x, y, s = sub; vis = SIZES[self.size] * s; z = max(1.0, H / vis)
            eye = y + (HEAD_CY - 6) * s
            third = -1 if x < W / 2 else 1  # subject on the left or right third, the open two-thirds for graphics
            if self.sh.kind == "closeup": third = 0 if self.size == "ecu" else third * .5
            fx = x - third * (W / 6) / z; fy = eye + (H / 2 - H / 3) / z
            if self.size == "ecu": fy = eye + 10 * s / z
        elif self.size == "ews":
            z = 1.0; fy = H / 2 - 20
        sy = 1.0; rot = 0.0
        if self.angle == "low":  # camera near the floor looking up: subject looms, horizon drops
            sy = 1.08; fy += 70 / z; z *= 1.06
        elif self.angle == "high":  # looking down: subject small and exposed, more floor around them
            sy = .93; fy -= 50 / z
        elif self.angle == "dutch":
            rot = float(self.cam.get("deg", 9))
        return z, fx, fy, rot, sy

    def default_zoom(self): return self.sh.default_zoom()

    # per frame ------------------------------------------------------------------------------
    def at(self, t):
        sh = self.sh; t0, t1 = sh.t0, sh.t1; d = max(t1 - t0, 1e-3); u = K(t, t0, d)
        z0, fx, fy, rot, sy = self.framing(); cam = self.cam; p = self.preset; zm = 1.0; dx = dy = 0.0
        if "zoom" in cam or "focus" in cam:  # explicit keyframes (eased)
            z_ = cam.get("zoom", [1.0, self.default_zoom()]); f = cam.get("focus", [[fx, fy], [fx, fy]])
            if isinstance(f[0], (int, float)): f = [f, f]
            e = ease(u); zm = lerp(z_[0], z_[1], e); fx = lerp(f[0][0], f[1][0], e); fy = lerp(f[0][1], f[1][1], e)
            rot += cam.get("rot", 0) * (e - .5)
        elif p == "creep" or p is None:  # Ken Burns: linear, no easing (exposition, calm narration)
            zm = lerp(1.0, cam.get("to", self.default_zoom()), u if p == "creep" else ease(u))
        elif p == "hold":
            zm = lerp(1.0, 1.025, u)
        elif p == "push":  # dramatic push-in: ease in/out to ~135 % over 1.5-2.5 s, settles on the subject
            dur = float(cam.get("dur", 2.0)); k = ease(K(t, self.pt, dur)); to = cam.get("to", 1.35)
            zm = lerp(1.0, 1.03, K(t, t0, max(self.pt - t0, .01))) * lerp(1.0, to / 1.03, k)
            sub = self.subject()
            if sub and not self.size:
                x, y, s = sub; fx = lerp(fx, x, k * .8); fy = lerp(fy, y + (HEAD_CY + 40) * s + 130, k * .8)
        elif p == "punch":  # snap zoom 3 frames, held: punchlines, shock, one absurd word
            k = ease_out(K(t, self.pt, 3 / FPS)); zm = lerp(1.0, 1.02, u) * lerp(1.0, cam.get("to", 1.25), k)
            sub = self.subject()
            if sub and not self.size and k > 0: x, y, s = sub; fx = lerp(fx, x, k * .6); fy = lerp(fy, y + (HEAD_CY + 40) * s + 100, k * .6)
        elif p == "reveal":  # start tight on a detail, strong ease-out pull back to the full scene
            dur = float(cam.get("dur", 3.5)); k = ease_out(K(t, t0, dur)) ** .8; z_from = cam.get("from", 1.5)
            zm = lerp(z_from, 1.0, k) * lerp(1.0, 1.02, u)
            sub = self.subject(); gx, gy = (sub[0], sub[1] + (HEAD_CY + 40) * sub[2] + 60) if sub else cam.get("start", (W / 2, H / 2))
            fx = lerp(gx, fx, k); fy = lerp(gy, fy, k)
        elif p == "glide":  # parallax glide: steady horizontal travel, foreground faster than background
            dist = float(cam.get("dist", 260)); s_ = -1 if cam.get("dir", "right") == "left" else 1
            zm = cam.get("to", 1.12); fx += s_ * lerp(-dist, dist, ease(u) * .25 + u * .75)
        elif p in ("tilt_up", "tilt_down"):  # vertical sweep: up = scale/power, down = hidden consequence
            dur = min(float(cam.get("dur", 4.0)), d * .9); k = ease(K(t, t0 + .15, dur)); zm = cam.get("to", 1.22)
            ya, yb = (H / 2 + 300, H / 2 - 230) if p == "tilt_up" else (H / 2 - 230, H / 2 + 300)
            fy = lerp(ya, yb, k)
        z = z0 * zm
        # timed moves --------------------------------------------------------------------------
        for m in self.moves:
            tm = m["t"]
            if t < tm: continue
            ty = m["type"]
            if ty == "punch":
                h = float(m.get("hold", 1e9)); k = ease_out(K(t, tm, 3 / FPS)) * (1 - ease(K(t, tm + h, .3)))
                z *= lerp(1.0, m.get("to", 1.22), k)
            elif ty in ("push", "pull"):
                k = ease(K(t, tm, float(m.get("dur", 2.0)))); to = m.get("to", 1.3 if ty == "push" else 1 / 1.25)
                z *= lerp(1.0, to, k)
                if ty == "push" and m.get("who") is not None:
                    a = self.sh.actor(m["who"])
                    if a: fx = lerp(fx, a.x, k * .7); fy = lerp(fy, a.y + (HEAD_CY + 40) * a.s + 120, k * .7)
            elif ty == "thud":  # sharp downward jolt with a decaying bounce, 8-12 frames
                e = (t - tm) * FPS
                if e < 12: dy += float(m.get("px", 22)) * math.exp(-e / 3.2) * math.cos(e * 1.15)
            elif ty == "rumble":  # high-frequency, low-amplitude jitter for the duration
                dur = float(m.get("dur", 1.2)); amp = float(m.get("px", 9))
                if t < tm + dur:
                    f = int(t * FPS / 2); dx += amp * math.sin(f * 12.9898 + 1.3) * (1 - .3 * K(t, tm, dur)); dy += amp * math.sin(f * 78.233 + 4.1) * (1 - .3 * K(t, tm, dur))
            elif ty == "dutch":  # tilt the horizon as tension peaks
                rot += float(m.get("deg", 9)) * ease(K(t, tm, .5))
            elif ty == "snap":  # snap straight again on the realisation
                rot *= 1 - ease_out(K(t, tm, 4 / FPS))
        # handheld breathing float (dialogue, standoffs). Never stacked on a glide, whip or rumble.
        fl = cam.get("float", self.sh.float_default())
        if fl and p != "glide":
            amp = 3.0 if fl is True else float(fl); dx += amp * jitter(t * .9, self.ph); dy += amp * .7 * jitter(t * .9, self.ph + 2.1)
        if self.angle == "dutch" and "snap_at" in cam:  # snap the horizon straight on the realisation
            rot *= 1 - ease_out(K(t, self.sh.cue(cam["snap_at"]), 4 / FPS))
        cs = clamp(CamState(z, fx, fy, rot, dx, dy, sy))
        return cs

    def start(self):
        if self.cs0 is None: self.cs0 = self.at(self.sh.t0)
        return self.cs0
