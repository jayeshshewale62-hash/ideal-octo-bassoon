// Procedural PBR texture sets (albedo + roughness + normal from a height field) and MeshStandardMaterial factories.
// Everything is seeded and deterministic. Real-world scale: every set has `tile` = metres covered by one texture repeat,
// and uvWorld()/boxUV() rewrite geometry UVs in metres so texel density is constant across props.
import * as THREE from "three";

export const rng = (seed) => { let s = seed >>> 0 || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); };
const cv = (w, h = w) => { const c = document.createElement("canvas"); c.width = w; c.height = h; return c; };

// ---------- fast tileable value noise ----------
const PERM = (() => { const r = rng(1337), p = Array.from({ length: 256 }, (_, i) => i); for (let i = 255; i > 0; i--) { const j = (r() * (i + 1)) | 0; [p[i], p[j]] = [p[j], p[i]]; } return Uint8Array.from([...p, ...p]); })();
/** periodic value noise: period `per` cells so textures tile */
const vn = (x, y, per, seed = 0) => {
  const xi = Math.floor(x), yi = Math.floor(y), fx = x - xi, fy = y - yi, u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy);
  const h = (i, j) => PERM[(PERM[((i % per) + per) % per + seed & 255] + (((j % per) + per) % per)) & 511] / 255;
  const a = h(xi, yi), b = h(xi + 1, yi), c = h(xi, yi + 1), d = h(xi + 1, yi + 1);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
};
/** tileable fbm over a S x S texture: base cells per tile `cells`, returns 0..1 */
export const fbmT = (x, y, S, cells = 8, oct = 5, seed = 0) => {
  let s = 0, a = 0.5, n = 0, c = cells;
  for (let k = 0; k < oct; k++) { s += a * vn((x / S) * c, (y / S) * c, c, seed + k * 31); n += a; a *= 0.5; c *= 2; }
  return s / n;
};

/** a texture "set": albedo canvas, height Float32Array, roughness Float32Array, size S */
const makeSet = (S) => ({ S, col: cv(S), h: new Float32Array(S * S), r: new Float32Array(S * S).fill(0.8) });
/** height -> tangent-space normal canvas (Sobel, wraps) */
const normalCanvas = (h, S, strength = 2) => {
  const c = cv(S), g = c.getContext("2d"), im = g.createImageData(S, S), d = im.data;
  const H = (x, y) => h[((y + S) % S) * S + ((x + S) % S)];
  for (let y = 0; y < S; y++) for (let x = 0; x < S; x++) {
    const dx = (H(x + 1, y - 1) + 2 * H(x + 1, y) + H(x + 1, y + 1) - H(x - 1, y - 1) - 2 * H(x - 1, y) - H(x - 1, y + 1)) * strength;
    const dy = (H(x - 1, y + 1) + 2 * H(x, y + 1) + H(x + 1, y + 1) - H(x - 1, y - 1) - 2 * H(x, y - 1) - H(x + 1, y - 1)) * strength;
    const l = Math.hypot(dx, dy, 1), i = (y * S + x) * 4;
    d[i] = (-dx / l * 0.5 + 0.5) * 255; d[i + 1] = (dy / l * 0.5 + 0.5) * 255; d[i + 2] = (1 / l * 0.5 + 0.5) * 255; d[i + 3] = 255;
  }
  g.putImageData(im, 0, 0);
  return c;
};
const grayCanvas = (a, S) => {
  const c = cv(S), g = c.getContext("2d"), im = g.createImageData(S, S), d = im.data;
  for (let i = 0; i < S * S; i++) { const v = Math.max(0, Math.min(255, a[i] * 255)); d[i * 4] = d[i * 4 + 1] = d[i * 4 + 2] = v; d[i * 4 + 3] = 255; }
  g.putImageData(im, 0, 0);
  return c;
};
/** read the albedo canvas back to modulate per-pixel (noise grime) */
const pixelPass = (set, fn) => {
  const g = set.col.getContext("2d"), im = g.getImageData(0, 0, set.S, set.S), d = im.data, S = set.S;
  for (let y = 0; y < S; y++) for (let x = 0; x < S; x++) { const i = y * S + x; fn(d, i * 4, x, y, i); }
  g.putImageData(im, 0, 0);
};
const hex = (c) => { const n = parseInt(c.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
const wrap9 = (S, fn) => { for (const dx of [-S, 0, S]) for (const dy of [-S, 0, S]) fn(dx, dy); };

// ---------- surface painters ----------
/** cracked asphalt: aggregate speckle, tar patches, branching cracks (deep, rough), oil stains */
export const asphalt = (seed = 1, S = 1024) => {
  const T = makeSet(S), r = rng(seed);
  pixelPass(T, (d, i, x, y, k) => {
    const n = fbmT(x, y, S, 6, 5, seed), sp = PERM[(x * 7 + y * 13 + seed) & 511] / 255;
    const v = 52 + 38 * n + 26 * (sp - 0.5) + (sp > 0.93 ? 30 : 0);
    d[i] = v; d[i + 1] = v * 1.01; d[i + 2] = v * 1.04; d[i + 3] = 255;
    T.h[k] = 0.5 + 0.25 * (sp - 0.5) + 0.2 * n; T.r[k] = 0.72 + 0.1 * sp;
  });
  const g = T.col.getContext("2d");
  // tar seal patches (darker, smoother)
  for (let i = 0; i < 7; i++) { const x = r() * S, y = r() * S, w = 80 + r() * 220, h = 40 + r() * 160; wrap9(S, (dx, dy) => { g.fillStyle = "rgba(25,26,29,0.55)"; g.fillRect(x + dx, y + dy, w, h); }); }
  // cracks: random walks, branch
  const crack = (x, y, a, len, w) => {
    g.strokeStyle = "rgba(10,10,12,0.95)"; g.lineCap = "round"; g.lineJoin = "round";
    const pts = [[x, y]];
    for (let s = 0; s < len; s++) { a += (r() - 0.5) * 0.9; x += Math.cos(a) * 9; y += Math.sin(a) * 9; pts.push([x, y]); if (r() < 0.04 && w > 1.2) crack(x, y, a + (r() - 0.5) * 2.4, len * 0.4, w * 0.6); }
    wrap9(S, (dx, dy) => { g.beginPath(); pts.forEach(([px, py], j) => (j ? g.lineTo(px + dx, py + dy) : g.moveTo(px + dx, py + dy))); g.lineWidth = w; g.stroke(); });
    for (const [px, py] of pts) for (let o = -2; o <= 2; o++) { const xx = ((Math.round(px) + o) % S + S) % S, yy = ((Math.round(py)) % S + S) % S; T.h[yy * S + xx] = 0.05; T.r[yy * S + xx] = 0.95; }
  };
  for (let i = 0; i < 9; i++) crack(r() * S, r() * S, r() * 6.3, 30 + r() * 50, 2 + r() * 2.5);
  // oil stains
  for (let i = 0; i < 5; i++) { const x = r() * S, y = r() * S, rr = 30 + r() * 70; wrap9(S, (dx, dy) => { const gr = g.createRadialGradient(x + dx, y + dy, 0, x + dx, y + dy, rr); gr.addColorStop(0, "rgba(12,10,14,0.45)"); gr.addColorStop(1, "rgba(12,10,14,0)"); g.fillStyle = gr; g.fillRect(x + dx - rr, y + dy - rr, rr * 2, rr * 2); }); }
  return { ...T, tile: 4, rough: 0.75 };
};

/** road strip (U across the road 0..1, V along it, tile = metres per repeat along V): asphalt + painted lines + tyre tracks
 *  lines: "center-yellow" (double yellow dashed), "edge-white", "both", or "none"; dirt: true for a dirt track instead */
export const roadTex = (seed = 2, { width = 7, lines = "both", dirt = false, S = 1024 } = {}) => {
  const base = dirt ? dirtGround(seed, S, "#8b6d4c") : asphalt(seed, S);
  const g = base.col.getContext("2d"), px = S / width; // pixels per metre across
  const paint = (u0, u1, v0, v1, colr) => {
    g.fillStyle = colr; g.fillRect(u0 * S, v0 * S, (u1 - u0) * S, (v1 - v0) * S);
    for (let y = Math.floor(v0 * S); y < v1 * S; y++) for (let x = Math.floor(u0 * S); x < u1 * S; x++) { const k = y * S + x; base.h[k] = 0.62; base.r[k] = 0.5; }
  };
  // tyre tracks: two darker polished bands per lane
  for (const u of [0.22, 0.36, 0.64, 0.78]) {
    const gr = g.createLinearGradient((u - 0.05) * S, 0, (u + 0.05) * S, 0);
    gr.addColorStop(0, "rgba(0,0,0,0)"); gr.addColorStop(0.5, dirt ? "rgba(60,40,24,0.45)" : "rgba(14,14,16,0.32)"); gr.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = gr; g.fillRect((u - 0.05) * S, 0, 0.1 * S, S);
    for (let y = 0; y < S; y++) for (let x = Math.floor((u - 0.03) * S); x < (u + 0.03) * S; x++) { const k = y * S + x; base.r[k] *= 0.82; if (dirt) base.h[k] *= 0.7; }
  }
  if (!dirt && (lines === "center-yellow" || lines === "both")) {
    const lw = 0.12 * px / S, gap = 0.1 * px / S;
    for (const o of [-gap / 2 - lw, gap / 2]) for (let v = 0; v < 1; v += 0.5) paint(0.5 + o, 0.5 + o + lw, v, v + 0.3, "#d9a51f");
  }
  if (!dirt && (lines === "edge-white" || lines === "both")) { const lw = 0.15 * px / S; paint(0.04, 0.04 + lw, 0, 1, "#e9e6dc"); paint(0.96 - lw, 0.96, 0, 1, "#e9e6dc"); }
  // paint wear: grain over the lines
  pixelPass(base, (d, i, x, y) => { const n = fbmT(x, y, S, 24, 3, seed + 5); if (n < 0.38) { d[i] *= 0.82; d[i + 1] *= 0.82; d[i + 2] *= 0.82; } });
  return { ...base, tile: width, rough: dirt ? 0.9 : 0.75 };
};

/** dirt / packed earth with pebbles */
export const dirtGround = (seed = 3, S = 1024, colr = "#8f7253") => {
  const T = makeSet(S), [cr, cg, cb] = hex(colr);
  pixelPass(T, (d, i, x, y, k) => {
    const n = fbmT(x, y, S, 5, 6, seed), m = fbmT(x, y, S, 40, 2, seed + 9), sp = PERM[(x * 11 + y * 17 + seed) & 511] / 255;
    const peb = m > 0.72 ? (m - 0.72) * 3 : 0, v = 0.75 + 0.45 * n + 0.15 * (sp - 0.5) + peb * 0.6;
    d[i] = cr * v; d[i + 1] = cg * v; d[i + 2] = cb * v; d[i + 3] = 255;
    T.h[k] = 0.4 * n + peb + 0.05 * sp; T.r[k] = 0.92 - 0.15 * peb;
  });
  return { ...T, tile: 3, rough: 0.92 };
};

/** grass ground (seen from height): mixed greens, dry patches, clover clumps */
export const grassGround = (seed = 4, S = 1024, colr = "#5f7f3a") => {
  const T = makeSet(S), [cr, cg, cb] = hex(colr);
  pixelPass(T, (d, i, x, y, k) => {
    const n = fbmT(x, y, S, 4, 5, seed), b = fbmT(x, y, S, 64, 2, seed + 3), dry = Math.max(0, fbmT(x, y, S, 3, 3, seed + 7) - 0.58) * 3;
    const v = 0.65 + 0.55 * n + 0.35 * (b - 0.5);
    d[i] = (cr * (1 - dry) + 150 * dry) * v; d[i + 1] = (cg * (1 - dry) + 128 * dry) * v; d[i + 2] = (cb * (1 - dry) + 70 * dry) * v; d[i + 3] = 255;
    T.h[k] = 0.6 * b + 0.3 * n; T.r[k] = 0.9;
  });
  return { ...T, tile: 4, rough: 0.9 };
};

/** cobblestone / flagstone: jittered grid cells (Worley-ish), domed stones, sunk seams with dirt */
export const cobble = (seed = 5, S = 1024, { cells = 9, flag = false, colr = "#7f7a72" } = {}) => {
  const T = makeSet(S), r = rng(seed), [cr, cg, cb] = hex(colr), N = cells;
  const pts = []; for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) pts.push([(i + 0.15 + 0.7 * r()) / N * S, (j + 0.15 + 0.7 * r()) / N * S, 0.75 + 0.5 * r()]);
  pixelPass(T, (d, i, x, y, k) => {
    const ci = Math.floor((x / S) * N), cj = Math.floor((y / S) * N);
    let d1 = 1e9, d2 = 1e9, tone = 1;
    for (let b = -1; b <= 1; b++) for (let a = -1; a <= 1; a++) {
      const ii = (ci + a + N) % N, jj = (cj + b + N) % N, p = pts[jj * N + ii], px = p[0] + Math.floor((ci + a) / N) * S, py = p[1] + Math.floor((cj + b) / N) * S;
      const dd = flag ? Math.max(Math.abs(x - px), Math.abs(y - py)) : Math.hypot(x - px, y - py);
      if (dd < d1) { d2 = d1; d1 = dd; tone = p[2]; } else if (dd < d2) d2 = dd;
    }
    const edge = (d2 - d1) / (S / N), seam = edge < 0.08, n = fbmT(x, y, S, 16, 3, seed);
    const dome = Math.min(1, edge * 4), v = seam ? 0.45 : tone * (0.8 + 0.35 * n);
    d[i] = (seam ? 70 : cr) * v; d[i + 1] = (seam ? 58 : cg) * v; d[i + 2] = (seam ? 44 : cb) * v; d[i + 3] = 255;
    T.h[k] = seam ? 0 : 0.35 + 0.65 * Math.sqrt(dome) + 0.05 * n; T.r[k] = seam ? 0.98 : 0.68 + 0.15 * n;
  });
  return { ...T, tile: flag ? 3 : 1.6, rough: 0.75 };
};

/** weathered stone brick with recessed mortar, per-brick tone, rain streak stains */
export const stoneBrick = (seed = 6, S = 1024, { rows = 10, cols = 4, colr = "#9a8f80", mortar = "#b9b2a4" } = {}) => {
  const T = makeSet(S), r = rng(seed), [cr, cg, cb] = hex(colr), [mr, mg, mb] = hex(mortar);
  const bh = S / rows, bw = S / cols, jit = Array.from({ length: rows * cols * 2 }, () => 0.78 + 0.4 * r());
  pixelPass(T, (d, i, x, y, k) => {
    const row = Math.floor(y / bh), off = (row % 2) * bw * 0.5, xx = (x + off) % S, col = Math.floor(xx / bw);
    const ex = Math.min(xx - col * bw, (col + 1) * bw - xx), ey = Math.min(y - row * bh, (row + 1) * bh - y), e = Math.min(ex, ey);
    const mw = 5 + 2 * fbmT(x, y, S, 32, 2, seed), isM = e < mw, n = fbmT(x, y, S, 12, 4, seed + 1);
    const tone = jit[(row * cols + col) % jit.length], streak = Math.max(0, fbmT(x * 0.25, y * 0.02, S, 8, 2, seed + 2) - 0.55) * 1.5;
    const v = isM ? 0.9 + 0.2 * n : tone * (0.78 + 0.4 * n) - streak * 0.35;
    d[i] = (isM ? mr : cr) * v; d[i + 1] = (isM ? mg : cg) * v; d[i + 2] = (isM ? mb : cb) * v; d[i + 3] = 255;
    T.h[k] = isM ? 0.1 + 0.1 * Math.min(1, e / mw) : 0.55 + 0.35 * Math.min(1, (e - mw) / 10) * (0.7 + 0.3 * n); T.r[k] = isM ? 0.95 : 0.78 + 0.12 * n;
  });
  return { ...T, tile: 2.4, rough: 0.85 };
};

/** aged wood planks with grain lines, knots and gaps (planks run along V) */
export const woodPlanks = (seed = 7, S = 1024, { planks = 6, colr = "#7a5536" } = {}) => {
  const T = makeSet(S), r = rng(seed), [cr, cg, cb] = hex(colr), pw = S / planks, tones = Array.from({ length: planks }, () => 0.75 + 0.45 * r());
  const knots = Array.from({ length: 10 }, () => [r() * S, r() * S, 6 + r() * 14]);
  pixelPass(T, (d, i, x, y, k) => {
    const p = Math.floor(x / pw), ex = Math.min(x - p * pw, (p + 1) * pw - x), gap = ex < 2.5;
    let warp = 0; for (const [kx, ky, kr] of knots) { const dd = Math.hypot(x - kx, y - ky); if (dd < kr * 4) warp += (kr * 4 - dd) / (kr * 4) * 6 * Math.sign(x - kx); }
    const grain = 0.5 + 0.5 * Math.sin((x + warp + 9 * fbmT(x, y, S, 4, 3, seed + p)) * 0.55 + p * 3), n = fbmT(x, y, S, 8, 4, seed + 11);
    let knot = 0; for (const [kx, ky, kr] of knots) if (Math.hypot(x - kx, (y - ky) * 0.6) < kr) knot = 1;
    const v = gap ? 0.25 : tones[p] * (0.7 + 0.22 * grain + 0.25 * n) * (knot ? 0.55 : 1);
    d[i] = cr * v; d[i + 1] = cg * v; d[i + 2] = cb * v; d[i + 3] = 255;
    T.h[k] = gap ? 0 : 0.5 + 0.18 * grain + 0.1 * n - (knot ? 0.15 : 0); T.r[k] = gap ? 1 : 0.7 + 0.15 * grain;
  });
  return { ...T, tile: 2, rough: 0.8 };
};

/** tree bark: vertical furrows */
export const bark = (seed = 8, S = 512, colr = "#5b4636") => {
  const T = makeSet(S), [cr, cg, cb] = hex(colr);
  pixelPass(T, (d, i, x, y, k) => {
    const f = fbmT(x * 4, y * 0.5, S * 4, 6, 4, seed), furrow = Math.abs(Math.sin((x / S) * Math.PI * 14 + f * 6));
    const v = 0.55 + 0.6 * furrow * (0.7 + 0.3 * f);
    d[i] = cr * v; d[i + 1] = cg * v; d[i + 2] = cb * v; d[i + 3] = 255; T.h[k] = furrow; T.r[k] = 0.92;
  });
  return { ...T, tile: 1.2, rough: 0.92 };
};

/** roof tiles: "terracotta" barrel tiles or "slate" overlapping slabs; rows along V (down the roof) */
export const roofTiles = (seed = 9, S = 1024, { kind = "terracotta", rows = 8, cols = 8 } = {}) => {
  const T = makeSet(S), r = rng(seed), base = kind === "slate" ? [66, 70, 78] : [168, 82, 52];
  const tones = Array.from({ length: rows * cols }, () => 0.75 + 0.45 * r());
  const rh = S / rows, cw = S / cols;
  pixelPass(T, (d, i, x, y, k) => {
    const row = Math.floor(y / rh), off = (row % 2) * cw * 0.5, xx = (x + off) % S, col = Math.floor(xx / cw);
    const u = (xx - col * cw) / cw, v = (y - row * rh) / rh, n = fbmT(x, y, S, 16, 3, seed);
    const prof = kind === "slate" ? 0.3 + 0.7 * v : Math.sin(u * Math.PI) * (0.4 + 0.6 * v);
    const lip = v > 0.9 || (kind === "slate" && (u < 0.03 || u > 0.97));
    const moss = Math.max(0, fbmT(x, y, S, 6, 3, seed + 4) - 0.62) * 2.5;
    const t = tones[(row * cols + col) % tones.length] * (0.6 + 0.4 * prof + 0.2 * n) * (lip ? 0.45 : 1);
    d[i] = (base[0] * (1 - moss) + 80 * moss) * t; d[i + 1] = (base[1] * (1 - moss) + 96 * moss) * t; d[i + 2] = (base[2] * (1 - moss) + 50 * moss) * t; d[i + 3] = 255;
    T.h[k] = lip ? 0 : prof; T.r[k] = kind === "slate" ? 0.55 + 0.2 * n : 0.8;
  });
  return { ...T, tile: 2, rough: kind === "slate" ? 0.6 : 0.8 };
};

/** canvas / tent fabric: weave */
export const fabric = (seed = 10, S = 512, colr = "#c9b48a") => {
  const T = makeSet(S), [cr, cg, cb] = hex(colr);
  pixelPass(T, (d, i, x, y, k) => {
    const w = 0, n = fbmT(x, y, S, 6, 3, seed), v = 0.86 + 0.28 * (n - 0.5); // no fine weave: it aliased into moire on curved covers
    d[i] = cr * v; d[i + 1] = cg * v; d[i + 2] = cb * v; d[i + 3] = 255; T.h[k] = n * 0.3 + w; T.r[k] = 0.95;
  });
  return { ...T, tile: 1.6, rough: 0.95 };
};

/** leaf cluster albedo with alpha (for leaf cards) */
export const leafCard = (seed = 11, S = 512, colr = "#4f7a34") => {
  const c = cv(S), g = c.getContext("2d"), r = rng(seed), [cr, cg, cb] = hex(colr);
  // 700 overlapping leaves: darker inside the cluster, sunlit yellow-green tips, midrib + soft edge shading
  for (let i = 0; i < 700; i++) {
    const rr = Math.sqrt(r()) * 0.46, th = r() * 6.283, x = S / 2 + Math.cos(th) * rr * S, y = S / 2 + Math.sin(th) * rr * S * 0.92, a = th + (r() - 0.5) * 1.6, l = 12 + r() * 20;
    const k = (0.45 + 0.75 * rr * 2 * (0.6 + 0.4 * r())) * (y < S / 2 ? 1.12 : 0.9), warm = r() < 0.15 ? 1.18 : 1;
    g.save(); g.translate(x, y); g.rotate(a); g.beginPath(); g.moveTo(-l, 0); g.quadraticCurveTo(0, -l * 0.55, l, 0); g.quadraticCurveTo(0, l * 0.55, -l, 0);
    const gr = g.createLinearGradient(0, -l * 0.5, 0, l * 0.5); gr.addColorStop(0, `rgb(${Math.min(255, cr * k * warm * 1.15) | 0},${Math.min(255, cg * k * 1.15) | 0},${cb * k | 0})`); gr.addColorStop(1, `rgb(${cr * k * 0.7 | 0},${cg * k * 0.75 | 0},${cb * k * 0.7 | 0})`);
    g.fillStyle = gr; g.fill(); g.strokeStyle = "rgba(15,30,10,0.45)"; g.lineWidth = 1; g.beginPath(); g.moveTo(-l * 0.9, 0); g.lineTo(l * 0.9, 0); g.stroke(); g.restore();
  }
  return c;
};

// ---------- three.js material factories ----------
const texCache = new Map();
/** canvases -> THREE textures (sRGB albedo, linear normal / roughness), repeat wrap, mipmaps, anisotropy */
export const toTextures = (set, normalStrength = 2.2) => {
  const t = (c, srgb) => { const x = new THREE.CanvasTexture(c); x.wrapS = x.wrapT = THREE.RepeatWrapping; x.anisotropy = 16; if (srgb) x.colorSpace = THREE.SRGBColorSpace; return x; };
  return { map: t(set.col, true), normalMap: t(normalCanvas(set.h, set.S, normalStrength), false), roughnessMap: t(grayCanvas(set.r, set.S), false) };
};
/** world-space macro variation (breaks tiling on big surfaces) injected into a standard material */
export const addMacro = (m, scale = 0.03, amount = 0.22) => {
  const prev = m.onBeforeCompile;
  m.onBeforeCompile = (sh, r) => {
    prev && prev(sh, r);
    sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\nvarying vec3 vMacroP;").replace("#include <worldpos_vertex>", "#include <worldpos_vertex>\nvMacroP = (modelMatrix * vec4(transformed, 1.0)).xyz;");
    sh.fragmentShader = sh.fragmentShader.replace("#include <common>", `#include <common>
varying vec3 vMacroP;
float mHash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float mNoise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mHash(i), mHash(i + vec2(1, 0)), f.x), mix(mHash(i + vec2(0, 1)), mHash(i + vec2(1, 1)), f.x), f.y); }`)
      .replace("#include <map_fragment>", `#include <map_fragment>
{ float mn = mNoise(vMacroP.xz * ${scale.toFixed(4)}) * 0.6 + mNoise(vMacroP.xz * ${(scale * 3.7).toFixed(4)}) * 0.4;
  diffuseColor.rgb *= 1.0 - ${amount.toFixed(3)} + 2.0 * ${amount.toFixed(3)} * mn; }`);
  };
  m.customProgramCacheKey = () => "macro" + scale + amount + (m.userData.key || "");
  return m;
};
/** PBR material from a painter set. opts: color, metalness, normalScale, macro, wettable, envMapIntensity */
export const pbrMat = (key, makeSetFn, opts = {}) => {
  let tx = texCache.get(key);
  if (!tx) { const set = makeSetFn(); tx = { ...toTextures(set, opts.normalStrength ?? 2.2), tile: set.tile, rough: set.rough }; texCache.set(key, tx); }
  const m = new THREE.MeshStandardMaterial({
    map: tx.map, normalMap: tx.normalMap, roughnessMap: tx.roughnessMap, roughness: 1, metalness: opts.metalness ?? 0,
    color: opts.color ?? 0xffffff, normalScale: new THREE.Vector2(opts.normalScale ?? 1, opts.normalScale ?? 1), envMapIntensity: opts.envMapIntensity ?? 1,
    side: opts.side ?? THREE.FrontSide,
  });
  m.userData = { tile: tx.tile, baseRough: tx.rough, wettable: !!opts.wettable, key };
  if (opts.macro) addMacro(m, opts.macro[0], opts.macro[1]);
  return m;
};
/** plain PBR (no texture) */
export const plainMat = (color, roughness = 0.6, metalness = 0, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness, metalness, ...extra });
/** reflective window glass (needs scene.environment for reflections) */
export const glassMat = (tint = 0x9fb4c4) => new THREE.MeshPhysicalMaterial({ color: tint, roughness: 0.06, metalness: 0.0, reflectivity: 0.9, clearcoat: 1, clearcoatRoughness: 0.04, envMapIntensity: 1.6, transparent: true, opacity: 0.85 });
/** car paint */
export const paintMat = (color) => new THREE.MeshPhysicalMaterial({ color, roughness: 0.32, metalness: 0.45, clearcoat: 1, clearcoatRoughness: 0.08, envMapIntensity: 1.2 });

/** rewrite UVs of any geometry to world metres / tile (planar per dominant normal axis = box-mapping) */
export const boxUV = (geo, tile = 1) => {
  const p = geo.attributes.position, n = geo.attributes.normal, uv = new Float32Array(p.count * 2);
  for (let i = 0; i < p.count; i++) {
    const ax = Math.abs(n.getX(i)), ay = Math.abs(n.getY(i)), az = Math.abs(n.getZ(i));
    const [u, v] = ay >= ax && ay >= az ? [p.getX(i), p.getZ(i)] : ax >= az ? [p.getZ(i), p.getY(i)] : [p.getX(i), p.getY(i)];
    uv[i * 2] = u / tile; uv[i * 2 + 1] = v / tile;
  }
  geo.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
  return geo;
};
/** apply wetness to every wettable material: roughness multiplier toward `wetRough`, albedo darkens ~25 % */
export const applyWet = (mats, wet) => {
  for (const m of mats) {
    if (!m.userData.wettable) continue;
    const target = wet > 0 ? Math.min(1, wet / (m.userData.baseRough || 0.8)) : 1;
    m.roughness = target;
    if (m.userData.dryColor === undefined) m.userData.dryColor = m.color.getHex();
    m.color.setHex(m.userData.dryColor).multiplyScalar(wet > 0 ? 0.72 : 1);
  }
};
