// Lighting presets (pure data, Node-importable). Three core looks + two story extras. Colours are linear RGB multipliers
// for lights, hex sRGB for the sky / fog. Units: sun intensity ~ multiples of PI (physically-correct lights in r160).
//   crispDay   : high sun, physical Sky shader, light haze, dry PBR ground
//   nightRain  : moon key + warm PointLight lanterns, wet ground (roughness ~0.22), rain streaks, dense blue fog
//   stormyRoad : low storm key, SpotLight headlights, lightning flashes, wet asphalt, heavy rain
//   golden / memory : sunset drama and a desaturated flashback
export const LP = {
  crispDay: {
    sky: "physical", az: 120, el: 48, sun: [1.25, 1.18, 1.05], sunK: 2.6, amb: [0.62, 0.72, 0.92], gnd: [0.36, 0.31, 0.25], hemiK: 0.9,
    top: "#3c7fd6", mid: "#8fb9e8", hor: "#cfe0ef", fogD: 0.0007, expo: 1.06, sat: 1.16, lift: [0.0, 0.004, 0.012], gain: [1, 1, 1], bloom: 0.35,
    wet: 0, rain: 0, turbidity: 3.2, rayleigh: 1.4, cloud: [1, 1, 1], cardK: 1.0, ink: 0,
  },
  nightRain: {
    sky: "gradient", az: 210, el: 38, sun: [0.42, 0.52, 0.85], sunK: 0.55, amb: [0.20, 0.26, 0.42], gnd: [0.05, 0.05, 0.08], hemiK: 0.55,
    top: "#070d1f", mid: "#14223f", hor: "#2b3d5e", fogD: 0.006, expo: 1.18, sat: 1.08, bloom: 0.95, lift: [0.006, 0.01, 0.03], gain: [0.98, 1, 1.06],
    wet: 0.22, rain: 1, cloud: [0.22, 0.27, 0.4], cardK: 1.0, ink: 0, practical: 1,
  },
  stormyRoad: {
    sky: "gradient", az: 250, el: 14, sun: [0.55, 0.62, 0.78], sunK: 0.9, amb: [0.28, 0.32, 0.4], gnd: [0.08, 0.08, 0.09], hemiK: 0.7,
    top: "#1a2230", mid: "#39434f", hor: "#5d6670", fogD: 0.0075, expo: 1.12, sat: 0.92, bloom: 0.8, lift: [0.01, 0.012, 0.02], gain: [0.97, 1, 1.04],
    wet: 0.2, rain: 1.6, cloud: [0.35, 0.38, 0.44], cardK: 1.0, ink: 0, practical: 1, lightning: 1,
  },
  golden: {
    sky: "physical", az: 165, el: 9, sun: [1.6, 1.0, 0.55], sunK: 2.2, amb: [0.48, 0.45, 0.62], gnd: [0.3, 0.22, 0.17], hemiK: 0.8,
    top: "#5c6fbf", mid: "#e6a98e", hor: "#ffcf8e", fogD: 0.0009, expo: 1.0, sat: 1.14, bloom: 0.5, lift: [0.01, 0.0, 0.02], gain: [1.04, 0.99, 0.93],
    wet: 0, rain: 0, turbidity: 6, rayleigh: 2.4, cloud: [1, 0.85, 0.72], cardK: 1.0, ink: 0,
  },
  memory: {
    sky: "gradient", az: 160, el: 13, sun: [1.0, 0.7, 0.62], sunK: 1.6, amb: [0.38, 0.38, 0.55], gnd: [0.16, 0.14, 0.2], hemiK: 0.8,
    top: "#2a3a72", mid: "#7c6f96", hor: "#d29a84", fogD: 0.0022, expo: 1.0, sat: 0.65, lift: [0.02, 0.02, 0.045], gain: [1, 0.97, 1.02],
    wet: 0, rain: 0, cloud: [0.72, 0.6, 0.7], cardK: 1.0, ink: 0,
  },
};
const lerp = (a, b, t) => a + (b - a) * t;
const hexMix = (a, b, t) => { const A = parseInt(a.slice(1), 16), B = parseInt(b.slice(1), 16); const ch = (s) => Math.round(((A >> s) & 255) * (1 - t) + ((B >> s) & 255) * t).toString(16).padStart(2, "0"); return `#${ch(16)}${ch(8)}${ch(0)}`; };
/** blend two presets (numbers, arrays, hex colours; the sky kind and discrete fields switch at t = 0.5) */
export const blendL = (a, b, t) => {
  const o = {};
  for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) {
    const x = a[k] ?? b[k], y = b[k] ?? a[k];
    o[k] = typeof x === "string" ? (x[0] === "#" ? hexMix(x, y, t) : t < 0.5 ? x : y) : Array.isArray(x) ? x.map((v, i) => lerp(v, y[i], t)) : typeof x === "number" ? lerp(x, y, t) : t < 0.5 ? x : y;
  }
  let d = b.az - a.az; if (d > 180) d -= 360; if (d < -180) d += 360; o.az = a.az + d * t;
  return o;
};
const sm = (t) => t * t * (3 - 2 * t);
/** piecewise light over frames: [[f, "preset" | object], ...] with smooth blends between neighbours */
export const lightSeq = (seq, f) => {
  const P = (v) => (typeof v === "string" ? LP[v] : v);
  if (f <= seq[0][0]) return P(seq[0][1]);
  for (let i = 0; i < seq.length - 1; i++) if (f <= seq[i + 1][0]) return blendL(P(seq[i][1]), P(seq[i + 1][1]), sm((f - seq[i][0]) / (seq[i + 1][0] - seq[i][0])));
  return P(seq[seq.length - 1][1]);
};
/** sun / moon direction (unit, world) from a preset */
export const sunDir = (L) => { const e = (L.el * Math.PI) / 180, a = (L.az * Math.PI) / 180; return [Math.cos(e) * Math.cos(a), Math.sin(e), Math.cos(e) * Math.sin(a)]; };
/** deterministic lightning: returns 0..1 flash strength for stormy presets (double-strike flickers) */
export const lightning = (f, strikes) => {
  let k = 0;
  for (const s of strikes) { const d = f - s; if (d >= 0 && d < 9) k = Math.max(k, [1, 0.25, 0.85, 0.5, 0.3, 0.18, 0.1, 0.05, 0.02][d]); }
  return k;
};
