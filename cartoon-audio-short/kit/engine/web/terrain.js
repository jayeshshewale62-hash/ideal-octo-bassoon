// Generic layered-heightmap terrain (pure, Node-importable): a flat valley floor along the road, rolling hills that rise
// away from it, one story hill the road climbs. Used by world.js (mesh) and story.js (staging: feet on the ground).
import { ROAD, HILL } from "./layout.js";
export const sstep = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const hash = (i, j) => { const h = Math.sin(i * 127.1 + j * 311.7) * 43758.5453; return h - Math.floor(h); };
const vnoise = (x, y) => {
  const i = Math.floor(x), j = Math.floor(y), fx = x - i, fy = y - j, u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy);
  const a = hash(i, j), b = hash(i + 1, j), c = hash(i, j + 1), d = hash(i + 1, j + 1);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
};
export const fbm = (x, y, oct = 4) => { let s = 0, a = 0.5, f = 1, n = 0; for (let k = 0; k < oct; k++) { s += a * vnoise(x * f, y * f); n += a; f *= 2.03; a *= 0.5; } return s / n; };
/** distance from (x, z) to a polyline [[x, z], ...] and the arc length at the closest point */
export const polyDist = (pts, x, z) => {
  let best = 1e9, sAt = 0, acc = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, az] = pts[i], [bx, bz] = pts[i + 1], dx = bx - ax, dz = bz - az, L = Math.hypot(dx, dz) || 1;
    const t = Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / (L * L))), d = Math.hypot(x - ax - dx * t, z - az - dz * t);
    if (d < best) { best = d; sAt = acc + t * L; }
    acc += L;
  }
  return [best, sAt];
};
/** point + tangent at arc length s along a polyline */
export const polyAt = (pts, s) => {
  let acc = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, az] = pts[i], [bx, bz] = pts[i + 1], L = Math.hypot(bx - ax, bz - az);
    if (s <= acc + L || i === pts.length - 2) { const t = Math.max(0, Math.min(1, (s - acc) / L)); return { x: ax + (bx - ax) * t, z: az + (bz - az) * t, dx: (bx - ax) / L, dz: (bz - az) / L }; }
    acc += L;
  }
};
export const polyLen = (pts) => pts.slice(1).reduce((a, p, i) => a + Math.hypot(p[0] - pts[i][0], p[1] - pts[i][1]), 0);
const hillBump = (x, z) => HILL.h * Math.exp(-((x - HILL.x) ** 2 + (z - HILL.z) ** 2) / (2 * HILL.r * HILL.r));
/** terrain height in metres */
export const groundAt = (x, z) => {
  const [d] = polyDist(ROAD, x, z);
  const side = (6 + 48 * fbm(x * 0.006 + 4.1, z * 0.006 - 2.3, 5)) * sstep(14, 90, d) + 3.5 * (fbm(x * 0.03, z * 0.03, 3) - 0.5) * sstep(10, 40, d);
  const floor = 0.18 * (fbm(x * 0.08, z * 0.08, 2) - 0.5) * sstep(4.5, 9, d); // road bed stays flat
  return hillBump(x, z) + side + floor;
};
