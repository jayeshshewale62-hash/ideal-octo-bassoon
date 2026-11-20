// Motion helpers: easing, camera key interpolation, idle life, blinks, kicks. All pure functions of the frame.
export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lin = (a, b, x) => clamp((x - a) / (b - a));
export const smooth = (t) => t * t * (3 - 2 * t);
export const smoother = (t) => t * t * t * (t * (t * 6 - 15) + 10);
export const easeOut = (t) => 1 - (1 - t) ** 3;
export const easeIn = (t) => t * t * t;
export const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
export const back = (t, s = 1.70158) => { const u = t - 1; return 1 + u * u * ((s + 1) * u + s); };
export const spring = (t, k = 9, z = 0.32) => 1 - Math.exp(-z * k * t) * Math.cos(k * t);
export const lerp = (a, b, t) => a + (b - a) * t;
export const lerp3 = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
export const add3 = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
/** Catmull-Rom through pts at t in 0..1 (uniform) */
export const catmull = (pts, t) => {
  const n = pts.length - 1, x = clamp(t) * n, i = Math.min(n - 1, Math.floor(x)), u = x - i;
  const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(n, i + 2)];
  return p1.map((_, k) => 0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * u + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * u * u + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * u * u * u));
};
/** camera keys: [{f, pos, look, fov, roll, ease}] ; glides between consecutive keys with the key's ease */
export const camKeys = (keys, f) => {
  if (f <= keys[0].f) return keys[0];
  for (let i = 0; i < keys.length - 1; i++) {
    const a = keys[i], b = keys[i + 1];
    if (f <= b.f) {
      const e = (b.ease || smoother)(lin(a.f, b.f, f));
      return { pos: b.path ? catmull([a.pos, ...b.path, b.pos], e) : lerp3(a.pos, b.pos, e), look: lerp3(a.look, b.look, e), fov: lerp(a.fov, b.fov, e), roll: lerp(a.roll || 0, b.roll || 0, e) };
    }
  }
  return keys[keys.length - 1];
};
/** impact flip-shake: sign flips every frame, decays over n frames */
export const kick = (f, list, n = 7) => {
  let x = 0, y = 0;
  for (const k of list) { const d = f - k.f; if (d >= 0 && d < n) { const a = (k.a ?? 0.06) * (1 - d / n) * (d % 2 ? -1 : 1); x += a; y += a * 0.6; } }
  return [x, y];
};
const hash = (k) => { const x = Math.sin(k * 91.7 + 13.1) * 43758.5453; return x - Math.floor(x); };
/** blink 0..1 (4 frames) at seeded intervals of 15-70 frames */
export const blinkAt = (f, seed) => {
  let t = Math.floor(hash(seed) * 30);
  for (let i = 0; i < 200 && t <= f + 4; i++) {
    const d = f - t;
    if (d >= 0 && d < 4) return d === 0 || d === 3 ? 0.5 : 1;
    t += 15 + Math.floor(hash(seed * 7 + i) * 55);
  }
  return 0;
};
/** breathing / sway for a standing card */
export const idle = (f, seed) => ({ bob: 0.012 * Math.sin(f * 0.19 + seed), tilt: 1.4 * Math.sin(f * 0.071 + seed * 1.3), head: 1.8 * Math.sin(f * 0.053 + seed * 2.1) });
/** quantise for card keys */
export const q = (x, s = 0.02) => Math.round(x / s) * s;

// ======================= v2: continuous 3D camera choreography (30 fps) =======================
export const FPS = 30;
export const sec = (s) => Math.round(s * FPS);
export const easeInOutCubic = easeInOut;
export const dist3 = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
const hashN = (k) => { const x = Math.sin(k * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
/** smooth 1-D value noise (deterministic, frame-pure) */
export const vnoise1 = (x, seed = 0) => { const i = Math.floor(x), u = x - i, s = u * u * (3 - 2 * u); return lerp(hashN(i + seed * 57), hashN(i + 1 + seed * 57), s) * 2 - 1; };

/** whip-glide between two camera states over n frames (6-12) with easeInOutCubic, replacing a hard cut.
 *  The path bows sideways (arc, in metres) so it reads as one continuous move in 3D space; fov dips a little mid-whip
 *  and the glide carries a small roll (deg) for energy. Returns {pos, look, fov, roll, whip: 0..1 speed}. */
export const whipGlide = (A, B, f, f0, n = 9, { arc = 0.12, roll = 2.5, fovDip = 3 } = {}) => {
  n = clamp(n, 6, 12);
  const t = clamp((f - f0) / n), e = easeInOutCubic(t);
  const d = [B.pos[0] - A.pos[0], B.pos[1] - A.pos[1], B.pos[2] - A.pos[2]], L = Math.hypot(...d) || 1;
  const side = [-d[2] / L, 0, d[0] / L], bow = Math.sin(e * Math.PI) * arc * L;
  return {
    pos: [lerp(A.pos[0], B.pos[0], e) + side[0] * bow, lerp(A.pos[1], B.pos[1], e) + 0.25 * bow, lerp(A.pos[2], B.pos[2], e) + side[2] * bow],
    look: lerp3(A.look, B.look, e), fov: lerp(A.fov, B.fov, e) - fovDip * Math.sin(e * Math.PI),
    roll: lerp(A.roll || 0, B.roll || 0, e) + roll * Math.sin(e * Math.PI), whip: Math.sin(t * Math.PI),
  };
};

/** camera keys with whip-glides: like camKeys, but a key with {whip: n} (6-12) is reached by an n-frame whipGlide that
 *  starts at key.f - n; until then the previous key holds (wrap the result in alive() so the hold still creeps).
 *  Use whips for nearby shots in one location instead of hard cuts. Adds .whip (0..1 speed) for motion blur. */
export const camWhipKeys = (keys, f) => {
  if (f <= keys[0].f) return { ...keys[0], roll: keys[0].roll || 0, whip: 0 };
  for (let k = 1; k < keys.length; k++) {
    const a = keys[k - 1], b = keys[k];
    if (f > b.f) continue;
    if (!b.whip) return { ...camKeys([a, b], f), whip: 0 };
    const fs = b.f - clamp(b.whip, 6, 12);
    if (f < fs) return { pos: a.pos, look: a.look, fov: a.fov, roll: a.roll || 0, whip: 0 };
    return whipGlide(a, b, f, fs, b.f - fs, b.whipOpts || {});
  }
  const z = keys[keys.length - 1];
  return { pos: z.pos, look: z.look, fov: z.fov, roll: z.roll || 0, whip: 0 };
};

/** prop / vehicle tracking camera with lag (~0.08 per frame, exponential follow). targetAt(f) -> [x,y,z] of the prop.
 *  offset = camera offset from the prop (world), lookAhead = metres along the prop's velocity added to the aim point.
 *  Pure function of the frame: the follow filter is re-run from f0 (cheap). */
export const trackCam = (targetAt, f, f0, { offset = [3, 1.6, 5], lookUp = 0.8, lag = 0.08, lookAhead = 1.2, fov = 40 } = {}) => {
  let pos = [0, 0, 0], aim = [0, 0, 0];
  for (let g = f0; g <= f; g++) {
    const p = targetAt(g), v = sub3(targetAt(g + 1), p), sp = Math.hypot(...v) || 1;
    const wantPos = add3(p, offset), wantAim = [p[0] + (v[0] / sp) * lookAhead * Math.min(1, sp * 10), p[1] + lookUp, p[2] + (v[2] / sp) * lookAhead * Math.min(1, sp * 10)];
    if (g === f0) { pos = wantPos; aim = wantAim; continue; }
    pos = lerp3(pos, wantPos, lag); aim = lerp3(aim, wantAim, lag * 2.2);
  }
  const p = targetAt(f), speed = dist3(targetAt(f + 1), p) * FPS; // m/s for motion blur
  return { pos, look: aim, fov, roll: 0, speed };
};
const sub3 = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];

/** handheld breathing float (metres / degrees): slow, small, always on. amp 1 = ~1.5 cm drift + 0.25 deg roll */
export const breathe = (f, seed = 1, amp = 1) => ({
  pos: [0.015 * amp * vnoise1(f / 41, seed), 0.011 * amp * vnoise1(f / 53, seed + 3), 0.013 * amp * vnoise1(f / 47, seed + 7)],
  look: [0.012 * amp * vnoise1(f / 37, seed + 11), 0.009 * amp * vnoise1(f / 43, seed + 13), 0],
  roll: 0.25 * amp * vnoise1(f / 59, seed + 17),
});

/** 7-frame damped camera shake for heavy impacts: list [{f, a}] (a ~0.02-0.05 = fraction of distance) */
export const dampedShake = (f, list, n = 7) => {
  let x = 0, y = 0, r = 0;
  for (const k of list) {
    const d = f - k.f;
    if (d < 0 || d >= n) continue;
    const env = (k.a ?? 0.03) * Math.exp(-3.2 * d / n) * (1 - d / n);
    x += env * Math.cos(d * 2.6 + 0.4); y += env * 0.7 * Math.sin(d * 3.3 + 1.1); r += env * 60 * Math.sin(d * 2.1);
  }
  return [x, y, r];
};

/** expanding ground shockwave ring: returns null or {radius (m), alpha, width} for an impact at fi */
export const shockwave = (f, fi, { maxR = 9, dur = 16 } = {}) => {
  const d = f - fi;
  if (d < 0 || d >= dur) return null;
  const t = d / dur;
  return { radius: 0.3 + maxR * easeOut(t), alpha: (1 - t) ** 1.5, width: lerp(0.9, 0.25, t) };
};

/** cutaway / X-ray: outer shell opacity 1 -> 0 over n (=10) frames from f0, back up from f1 (optional) */
export const shellOpacity = (f, f0, n = 10, f1 = Infinity) => (f < f1 ? 1 - easeInOutCubic(clamp((f - f0) / n)) : easeInOutCubic(clamp((f - f1) / n)));

/** make any camera state alive: adds breathing float and a minimum creep (push-in) so no 4+ frame span is static.
 *  push = metres per second of slow dolly toward the look point. */
export const alive = (cam, f, { seed = 1, amp = 1, push = 0.06, from = 0 } = {}) => {
  const b = breathe(f, seed, amp), dir = sub3(cam.look, cam.pos), L = Math.hypot(...dir) || 1, k = Math.min(push * (f - from) / FPS, L * 0.3) / L;
  return { ...cam, pos: add3(add3(cam.pos, dir.map((v) => v * k)), b.pos), look: add3(cam.look, b.look), roll: (cam.roll || 0) + b.roll };
};

// ======================= comic overlays (drawn by cast.js comicFx) =======================
/** frame-triggered overlay helper: comicAt(f, [{k: "rage", f0, f1, ramp}...]) -> opts.comic (rage | sweat | whiteout | lines | steam) */
export const comicAt = (f, list) => {
  const out = {};
  for (const e of list) {
    if (f < e.f0 || f >= e.f1) continue;
    const r = e.ramp ?? 4, v = Math.min(1, (f - e.f0 + 1) / r, (e.f1 - f) / r);
    out[e.k] = e.k === "sweat" ? ((f - e.f0) / 18) % 1 : e.k === "steam" ? ((f - e.f0) / 14) % 1 : Math.max(out[e.k] || 0, Math.round(v * 8) / 8);
  }
  return Object.keys(out).length ? out : null;
};

