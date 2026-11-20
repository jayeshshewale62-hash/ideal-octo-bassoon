// Particle presets as pure functions of the frame (seeded, analytic motion), drawn as soft point sprites.
//   sparks (fuse), debris (sawdust / dirt chunks), smoke (plume), explosion (flash + fireball + sparks + smoke),
//   firework (coloured shell burst), dust (impact ring puff) + rain streaks around the camera + ground shockwave ring.
// An emitter from story.js: { id, kind, f0, f1?, at: (g) => [x, y, z], seed?, scale?, rate?, dir?: [x, y, z], col? }
import * as THREE from "three";

const h1 = (k) => { const x = Math.sin(k * 12.9898 + 78.233) * 43758.5453; return x - Math.floor(x); };
const G = -9.8;
/** preset: life (s), rate (per s, continuous emitters), speed, spread, gravity scale, drag, size (m) start/end, colour ramp, blending */
export const PRESETS = {
  sparks: { life: [0.25, 0.6], rate: 140, speed: [1.5, 4], up: 0.6, grav: 0.6, drag: 1.2, size: [0.05, 0.01], col: [[1, 0.95, 0.7], [1, 0.45, 0.1]], add: true, glow: 3 },
  debris: { life: [0.7, 1.4], burst: 90, speed: [2, 6.5], up: 0.8, grav: 1, drag: 0.4, size: [0.07, 0.05], col: [[0.55, 0.42, 0.28], [0.4, 0.3, 0.2]], add: false, bounce: true },
  sawdust: { life: [0.8, 1.6], rate: 60, speed: [0.6, 1.8], up: 0.4, grav: 0.35, drag: 2.2, size: [0.03, 0.025], col: [[0.86, 0.72, 0.5], [0.8, 0.66, 0.46]], add: false },
  smoke: { life: [2.2, 3.6], rate: 22, speed: [0.4, 0.9], up: 1, grav: -0.12, drag: 0.6, size: [0.5, 2.6], col: [[0.55, 0.55, 0.57], [0.35, 0.35, 0.37]], add: false, alpha: 0.42, soft: true },
  explosion: { sphere: true, life: [0.5, 1.1], burst: 160, speed: [5, 16], up: 0.2, grav: 0.25, drag: 2.4, size: [0.9, 2.4], col: [[1, 0.93, 0.6], [0.9, 0.25, 0.05]], add: true, glow: 4, soft: true },
  firework: { life: [1.1, 1.9], burst: 220, speed: [9, 14], up: 0, grav: 0.35, drag: 1.1, size: [0.35, 0.12], col: [[1, 1, 1], [1, 0.3, 0.2]], add: true, glow: 6, sphere: true },
  dust: { life: [0.8, 1.5], burst: 70, speed: [3, 7], up: 0.08, grav: 0.05, drag: 2.5, size: [0.4, 1.6], col: [[0.72, 0.64, 0.52], [0.62, 0.56, 0.48]], add: false, alpha: 0.5, soft: true, ring: true },
};

const spriteTex = (() => {
  const c = document.createElement("canvas"); c.width = c.height = 64; const g = c.getContext("2d"), gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, "rgba(255,255,255,1)"); gr.addColorStop(0.35, "rgba(255,255,255,0.8)"); gr.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = gr; g.fillRect(0, 0, 64, 64); return new THREE.CanvasTexture(c);
})();
const pointsMat = (add) => new THREE.ShaderMaterial({
  transparent: true, depthWrite: false, blending: add ? THREE.AdditiveBlending : THREE.NormalBlending,
  uniforms: { tex: { value: spriteTex }, scaleH: { value: 1000 }, tint: { value: new THREE.Color(1, 1, 1) } },
  vertexShader: `attribute float size; attribute vec4 rgba; varying vec4 vC; uniform float scaleH;
    void main(){ vC = rgba; vec4 mv = modelViewMatrix * vec4(position, 1.0); gl_PointSize = clamp(size * scaleH / -mv.z, 1.0, 512.0); gl_Position = projectionMatrix * mv; }`,
  fragmentShader: `uniform sampler2D tex; uniform vec3 tint; varying vec4 vC;
    void main(){ vec4 t = texture2D(tex, gl_PointCoord); gl_FragColor = vec4(vC.rgb * tint, vC.a * t.a); }`,
});

/** particles of one emitter at frame f -> arrays (positions, colours, sizes) */
export const simulate = (e, f, groundAt) => {
  const P = { ...PRESETS[e.kind], ...(e.over || {}) }, sc = e.scale ?? 1, out = [];
  const seed = (e.seed ?? 1) * 1000, fps = 30, end = e.f1 ?? e.f0 + 1;
  const n = P.burst ? Math.round(P.burst * (e.count ?? 1)) : Math.max(0, Math.floor(((Math.min(f, end) - e.f0) / fps) * (e.rate ?? P.rate)));
  for (let i = 0; i < n; i++) {
    const birth = P.burst ? e.f0 + h1(seed + i * 7.1) * 1.5 : e.f0 + (i / (e.rate ?? P.rate)) * fps;
    const life = P.life[0] + (P.life[1] - P.life[0]) * h1(seed + i * 3.3), age = (f - birth) / fps;
    if (age < 0 || age > life) continue;
    const t = age / life, o = e.at(Math.floor(birth));
    // direction: sphere (fireworks / explosion) or cone around e.dir / up
    const u = h1(seed + i * 1.7) * 2 - 1, ph = h1(seed + i * 2.9) * Math.PI * 2, s = Math.sqrt(1 - u * u);
    let d = P.sphere ? [s * Math.cos(ph), u, s * Math.sin(ph)] : P.ring ? [Math.cos(ph), 0.05 + 0.1 * h1(i), Math.sin(ph)] : [s * Math.cos(ph) * (1 - P.up), Math.abs(u) * P.up + (1 - P.up) * u * 0.3, s * Math.sin(ph) * (1 - P.up)];
    if (e.dir) d = [d[0] * 0.5 + e.dir[0], d[1] * 0.5 + e.dir[1], d[2] * 0.5 + e.dir[2]];
    const v = (P.speed[0] + (P.speed[1] - P.speed[0]) * h1(seed + i * 5.3)) * sc, k = P.drag;
    const travel = k > 0 ? (1 - Math.exp(-k * age)) / k : age; // drag-integrated distance
    let x = o[0] + d[0] * v * travel, y = o[1] + d[1] * v * travel + 0.5 * G * P.grav * age * age, z = o[2] + d[2] * v * travel;
    if (P.bounce && groundAt) { const gy = groundAt(x, z) + 0.03; if (y < gy) y = gy + Math.abs(y - gy) * 0.15; }
    const c0 = e.col ? e.col[0] : P.col[0], c1 = e.col ? e.col[1] : P.col[1], a = (P.alpha ?? 1) * (P.soft ? Math.sin(Math.min(1, t * 4) * Math.PI / 2) * (1 - t) : 1 - t * t);
    const glow = P.glow ? 1 + P.glow * (1 - t) : 1;
    out.push([x, y, z, (c0[0] + (c1[0] - c0[0]) * t) * glow, (c0[1] + (c1[1] - c0[1]) * t) * glow, (c0[2] + (c1[2] - c0[2]) * t) * glow, a, (P.size[0] + (P.size[1] - P.size[0]) * t) * sc]);
  }
  return out;
};

export const makeVfx = (scene) => {
  const pools = new Map();
  const pool = (id, add) => {
    let p = pools.get(id);
    if (!p) {
      const geo = new THREE.BufferGeometry(), N = 4096;
      geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(N * 3), 3));
      geo.setAttribute("rgba", new THREE.BufferAttribute(new Float32Array(N * 4), 4));
      geo.setAttribute("size", new THREE.BufferAttribute(new Float32Array(N), 1));
      const pts = new THREE.Points(geo, pointsMat(add)); pts.frustumCulled = false; pts.renderOrder = 3; scene.add(pts);
      p = { pts, N }; pools.set(id, p);
    }
    return p;
  };
  // rain streaks: line segments in a box around the camera, falling + wind slant, wrapped (frame-pure)
  const RN = 7000, rainGeo = new THREE.BufferGeometry(), rainPos = new Float32Array(RN * 6);
  rainGeo.setAttribute("position", new THREE.BufferAttribute(rainPos, 3));
  const rain = new THREE.LineSegments(rainGeo, new THREE.LineBasicMaterial({ color: 0xc8d6ea, transparent: true, opacity: 0.35, depthWrite: false }));
  rain.frustumCulled = false; rain.renderOrder = 4; scene.add(rain);
  // shockwave ring
  const ringMat = new THREE.MeshBasicMaterial({ color: 0xe9dcc4, transparent: true, depthWrite: false, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -4 });
  const ring = new THREE.Mesh(new THREE.RingGeometry(0.85, 1, 64), ringMat); ring.rotation.x = -Math.PI / 2; ring.renderOrder = 2; scene.add(ring);

  const update = (f, S, camera, groundAt, H) => {
    const seen = new Set();
    for (const e of S.emitters || []) {
      const P = PRESETS[e.kind]; if (!P) continue;
      const p = pool(e.id, P.add), parts = simulate(e, f, groundAt).slice(0, p.N), a = p.pts.geometry.attributes;
      parts.forEach((q, i) => { a.position.setXYZ(i, q[0], q[1], q[2]); a.rgba.setXYZW(i, q[3], q[4], q[5], q[6]); a.size.setX(i, q[7]); });
      p.pts.geometry.setDrawRange(0, parts.length);
      a.position.needsUpdate = a.rgba.needsUpdate = a.size.needsUpdate = true;
      p.pts.material.uniforms.scaleH.value = H / (2 * Math.tan((camera.fov * Math.PI) / 360));
      p.pts.material.uniforms.tint.value.setRGB(...(P.add ? [1, 1, 1] : S.cardTint || [1, 1, 1]));
      p.pts.visible = parts.length > 0; seen.add(e.id);
    }
    for (const [id, p] of pools) if (!seen.has(id)) p.pts.visible = false;
    // rain
    const R = S.light.rain || 0;
    rain.visible = R > 0.01;
    if (rain.visible) {
      const c = camera.position, bx = 26, by = 22, bz = 26, sp = 9 + 4 * R, len = 0.45 + 0.25 * R, wx = 1.2 * R, t = f / 30, n = Math.floor(RN * Math.min(1, 0.45 + 0.4 * R));
      for (let i = 0; i < n; i++) {
        const x0 = h1(i * 1.3) * bx, z0 = h1(i * 2.7) * bz, y0 = h1(i * 4.1) * by;
        const x = c.x - bx / 2 + ((x0 + wx * t - c.x) % bx + bx) % bx, z = c.z - bz / 2 + ((z0 - c.z) % bz + bz) % bz, y = c.y - by / 2 + ((y0 - sp * t - c.y) % by + by) % by;
        rainPos.set([x, y, z, x - wx * len / sp * 3, y + len, z], i * 6);
      }
      rainGeo.setDrawRange(0, n * 2); rainGeo.attributes.position.needsUpdate = true;
      rain.material.opacity = 0.18 + 0.14 * R;
    }
    // shockwave ring
    const W = S.shock;
    ring.visible = !!W;
    if (W) { ring.position.set(W.pos[0], groundAt(W.pos[0], W.pos[2]) + 0.06, W.pos[2]); ring.scale.setScalar(W.radius); ringMat.opacity = 0.32 * W.alpha; ring.geometry.dispose(); ring.geometry = new THREE.RingGeometry(Math.max(0.05, 1 - W.width / Math.max(W.radius, 0.5)), 1, 64); ringMat.color.setRGB(...(S.cardTint || [1, 1, 1])).multiply(new THREE.Color(0xb8ab96)).multiplyScalar(S.light.practical ? 0.45 : 1); }
  };
  return { update };
};
