// Engine v2: realistic PBR 3D world + cleanly integrated 2D ink cards. Exposes window.renderFrame(f) for render.mjs.
// Passes: colour (PBR, PCF soft shadows, IBL from the sky) -> normal+depth -> grade (+ optional world ink) ->
//         camera motion blur (depth reprojection) -> lens DOF -> screen. 1080 x 1920, 30 fps, every value a pure
//         function of the frame (story.js frameState).
import * as THREE from "three";
import * as T from "./toon.js";
import { buildWorld } from "./world.js";
import { makeVfx } from "./vfx.js";
import { applyWet } from "./pbr.js";
import { groundAt } from "./terrain.js";
import { sunDir } from "./lighting.js";
import { frameState, TOTAL } from "./story.js";

const W = 1080, H = 1920, PX = W / 1080;
const canvas = document.createElement("canvas");
canvas.width = W; canvas.height = H;
document.body.appendChild(canvas);
const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, preserveDrawingBuffer: true, powerPreference: "high-performance" });
renderer.setPixelRatio(1);
renderer.setSize(W, H, false);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.LinearSRGBColorSpace;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, W / H, 0.1, 8000);
scene.fog = new THREE.FogExp2(0xcfe0ef, 0.001);

// ---------- world ----------
const WORLD = buildWorld(scene);
const noND = (o) => { o.traverse((c) => { c.userData.noND = true; }); return o; };
noND(WORLD.sky.phys); noND(WORLD.sky.grad);
scene.traverse((o) => { if (o.isMesh && o.material && o.material.map && o.material.transparent && !o.material.alphaTest) o.userData.noND = true; }); // clouds
for (const m of WORLD.mats) m.userData.envBase = m.envMapIntensity ?? 1;

// ---------- lights: sun/moon key (2048 PCF soft shadows), hemisphere bounce, practical pools ----------
const hemi = new THREE.HemisphereLight(0xffffff, 0xffffff, 1); scene.add(hemi);
const sun = new THREE.DirectionalLight(0xffffff, 1);
sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048); sun.shadow.bias = -0.0005; sun.shadow.normalBias = 0.035; sun.shadow.radius = 3;
scene.add(sun, sun.target);
const LANTERN_POOL = 6; // constant light count (no shader recompiles); nearest lanterns to the action get them
const lampPool = Array.from({ length: LANTERN_POOL }, () => { const l = new THREE.PointLight(0xffb45c, 0, 38, 2); scene.add(l); return l; });
const heads = [0, 1].map(() => { const s = new THREE.SpotLight(0xfff1d6, 0, 90, 0.42, 0.55, 1.6); scene.add(s, s.target); return s; });
const beamMat = new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, uniforms: { k: { value: 0 } },
  vertexShader: "varying float vY; void main(){ vY = uv.y; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
  fragmentShader: "uniform float k; varying float vY; void main(){ gl_FragColor = vec4(vec3(1.0, 0.95, 0.85) * k * pow(vY, 2.2), 1.0); }" });
const beams = [0, 1].map(() => { const g = new THREE.ConeGeometry(4.2, 26, 24, 1, true); g.translate(0, -13, 0); g.rotateX(-Math.PI / 2); const m = new THREE.Mesh(g, beamMat); m.userData.noND = true; scene.add(m); return m; });
const boomLight = new THREE.PointLight(0xffa040, 0, 160, 1.6); scene.add(boomLight);

// ---------- environment (IBL) from the sky, cached per quantised sky state ----------
const pmrem = new THREE.PMREMGenerator(renderer);
const envScene = new THREE.Scene();
const envPhys = new THREE.Mesh(WORLD.sky.phys.geometry, WORLD.sky.phys.material); envPhys.scale.setScalar(4500);
const envGrad = new THREE.Mesh(WORLD.sky.grad.geometry, WORLD.sky.grad.material);
envScene.add(envPhys, envGrad);
const envCache = new Map();
const envFor = (key) => {
  let e = envCache.get(key);
  if (!e) { if (envCache.size > 24) { for (const v of envCache.values()) v.dispose(); envCache.clear(); } e = pmrem.fromScene(envScene, 0, 0.1, 5000).texture; envCache.set(key, e); }
  return e;
};

// ---------- 2D character cards: lit (wrapped Lambert), shadow-casting + receiving, view-space depth pull ----------
const SC = 0.00225; // metres per design unit (600 x 1000 design canvas = 1.35 x 2.25 m)
const CARD_RES = 2.4; // canvas pixels per design unit (high-res ink)
const cards = new Map();
const drawFn = { front: (p, a) => T.bodyFrontX(p, a.outfit, a.opts), side: (p, a) => T.bodySideX(p, a.outfit, a.opts) };
const ctex = (c) => { const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t; };
const blobTex = (() => { const c = document.createElement("canvas"); c.width = c.height = 128; const g = c.getContext("2d"), gr = g.createRadialGradient(64, 64, 0, 64, 64, 64); gr.addColorStop(0, "rgba(40,36,44,0.75)"); gr.addColorStop(0.55, "rgba(40,36,44,0.35)"); gr.addColorStop(1, "rgba(40,36,44,0)"); g.fillStyle = gr; g.fillRect(0, 0, 128, 128); return ctex(c); })();
const ndCardMat = (map, pullU) => new THREE.ShaderMaterial({
  uniforms: { map: { value: map }, uPull: pullU }, side: THREE.DoubleSide,
  vertexShader: "uniform float uPull; varying vec2 vUv; varying float vZ; void main(){ vUv = uv; vec4 mv = modelViewMatrix * vec4(position,1.0); float d = length(mv.xyz); mv.xyz *= max(0.15, (d - uPull) / d); vZ = -mv.z; gl_Position = projectionMatrix * mv; }",
  fragmentShader: "uniform sampler2D map; varying vec2 vUv; varying float vZ; void main(){ if (texture2D(map, vUv).a < 0.5) discard; gl_FragColor = vec4(0.0, 0.0, 0.0, vZ); }",
});
const WRAP_LAMBERT = THREE.ShaderChunk.lights_lambert_pars_fragment.replace(
  "float dotNL = saturate( dot( geometryNormal, directLight.direction ) );",
  "float dotNL = saturate( 0.78 + 0.22 * dot( geometryNormal, directLight.direction ) ); // wrapped: flat cards never go black");
const getCard = (id, DW, DH) => {
  let c = cards.get(id);
  if (c && c.DW === DW && c.DH === DH) return c;
  if (c) { scene.remove(c.mesh); scene.remove(c.blob); }
  const sc = CARD_RES * (DW > 600 ? 0.8 : 1);
  const cv = document.createElement("canvas"); cv.width = Math.round(DW * sc); cv.height = Math.round(DH * sc);
  const tex = ctex(cv); tex.anisotropy = 4;
  const geo = new THREE.PlaneGeometry(DW * SC, DH * SC); geo.translate(0, (DH * SC) / 2 - 25 * SC, 0);
  const pullU = { value: 0.3 }, gainU = { value: 1 };
  const mat = new THREE.MeshLambertMaterial({ map: tex, alphaTest: 0.5, side: THREE.DoubleSide });
  mat.customProgramCacheKey = () => "card2";
  mat.onBeforeCompile = (sh) => {
    sh.uniforms.uPull = pullU; sh.uniforms.uGain = gainU;
    sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\nuniform float uPull;")
      .replace("#include <project_vertex>", "#include <project_vertex>\n{ float d = length(mvPosition.xyz); mvPosition.xyz *= max(0.15, (d - uPull) / d); gl_Position = projectionMatrix * mvPosition; }");
    sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\nuniform float uGain;")
      .replace("#include <lights_lambert_pars_fragment>", WRAP_LAMBERT)
      .replace("#include <opaque_fragment>", "outgoingLight *= uGain;\n#include <opaque_fragment>");
  };
  const mesh = new THREE.Mesh(geo, mat);
  mesh.rotation.order = "YXZ"; mesh.castShadow = true; mesh.receiveShadow = true;
  mesh.customDepthMaterial = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking, map: tex, alphaTest: 0.5, side: THREE.DoubleSide });
  mesh.userData.nd = ndCardMat(tex, pullU);
  const bg = new THREE.PlaneGeometry(1.15, 0.6); bg.rotateX(-Math.PI / 2);
  const blob = new THREE.Mesh(bg, new THREE.MeshBasicMaterial({ map: blobTex, transparent: true, depthWrite: false, fog: false, polygonOffset: true, polygonOffsetFactor: -2 }));
  blob.userData.noND = true;
  scene.add(mesh, blob);
  c = { id, DW, DH, sc, cv, g: cv.getContext("2d"), tex, mesh, blob, key: "", pullU, gainU };
  cards.set(id, c);
  return c;
};
/** default depth pull: 0.3 m in the open, 0.8 m when the card stands within 1.5 m of a wall (prevents slicing into it) */
const pullFor = (a) => {
  if (a.pull != null) return a.pull;
  for (const [x0, z0, x1, z1] of WORLD.walls) { const dx = Math.max(x0 - a.pos[0], 0, a.pos[0] - x1), dz = Math.max(z0 - a.pos[1], 0, a.pos[1] - z1); if (Math.hypot(dx, dz) < 1.5) return 0.8; }
  return 0.3;
};
// 2D canvas effect cards (bursts, puffs, chips, comic stars...) from toon.js
const fxCards = new Map();
const fxDraw = {
  burst: (p, s) => T.fxBurst(p, s.t, s.col || "#fff3b0"), puff: (p, s) => T.fxPuff(p, s.t), chips: (p, s) => T.fxChips(p, s.t, s.seed || 1),
  stars: (p, s) => T.fxStars(p, s.t), creak: (p, s) => T.fxCreak(p, s.t), glow: (p) => T.fxGlow(p), smoke: (p, s) => T.fxSmoke(p, s.t), bird: (p, s) => T.fxBird(p, s.t),
};
const FXSIZE = { burst: [500, 500], puff: [300, 300], chips: [400, 400], stars: [420, 210], creak: [300, 300], glow: [256, 256], smoke: [300, 600], bird: [200, 100] };
const getFx = (id, kind) => {
  let c = fxCards.get(id);
  if (c && c.kind === kind) return c;
  const [w, h] = FXSIZE[kind];
  const cv = document.createElement("canvas"); cv.width = w; cv.height = h;
  const tex = ctex(cv);
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, h / w), new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false, side: THREE.DoubleSide, fog: kind !== "glow", blending: kind === "glow" ? THREE.AdditiveBlending : THREE.NormalBlending }));
  mesh.userData.noND = true; scene.add(mesh);
  c = { id, kind, cv, g: cv.getContext("2d"), tex, mesh, key: "" };
  fxCards.set(id, c);
  return c;
};
const VFX = makeVfx(scene);

// ---------- post ----------
const rtColor = new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4 });
const rtND = new THREE.WebGLRenderTarget(W, H, { type: THREE.FloatType, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter });
const rtPost = new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType });
const rtMB = new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType });
const ndWorld = new THREE.ShaderMaterial({
  side: THREE.DoubleSide,
  vertexShader: "varying vec3 vN; varying float vZ; void main(){ vN = normalize(normalMatrix * normal); vec4 mv = modelViewMatrix * vec4(position,1.0); vZ = -mv.z; gl_Position = projectionMatrix * mv; }",
  fragmentShader: "varying vec3 vN; varying float vZ; void main(){ vec3 n = normalize(vN) * (gl_FrontFacing ? 1.0 : -1.0); gl_FragColor = vec4(n, vZ); }",
});
const ndAlphaCache = new Map();
const ndAlpha = (map) => { let m = ndAlphaCache.get(map); if (!m) { m = new THREE.ShaderMaterial({ side: THREE.DoubleSide, uniforms: { map: { value: map } },
  vertexShader: "varying vec3 vN; varying float vZ; varying vec2 vUv; void main(){ vUv = uv; vN = normalize(normalMatrix * normal); vec4 mv = modelViewMatrix * vec4(position,1.0); vZ = -mv.z; gl_Position = projectionMatrix * mv; }",
  fragmentShader: "uniform sampler2D map; varying vec3 vN; varying float vZ; varying vec2 vUv; void main(){ if (texture2D(map, vUv).a < 0.5) discard; gl_FragColor = vec4(normalize(vN), vZ); }" }); ndAlphaCache.set(map, m); } return m; };
const FSV = "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }";
const fsScene = new THREE.Scene(), fsCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
const fsQuad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2)); fsQuad.frustumCulled = false; fsScene.add(fsQuad);
// grade: exposure, optional world ink (inkK, 0 for realistic worlds), saturation, lift/gain, filmic shoulder, vignette, flash
const gradeMat = new THREE.ShaderMaterial({
  uniforms: {
    tColor: { value: rtColor.texture }, tND: { value: rtND.texture }, texel: { value: new THREE.Vector2(1 / W, 1 / H) }, px: { value: PX },
    inkCol: { value: new THREE.Color(0x0b0a0c) }, fogCol: { value: new THREE.Color() }, sat: { value: 1.05 }, expo: { value: 1 },
    lift: { value: new THREE.Vector3() }, gain: { value: new THREE.Vector3(1, 1, 1) }, vign: { value: 0.18 }, flash: { value: 0 }, inkK: { value: 0 },
  },
  vertexShader: FSV,
  fragmentShader: `uniform sampler2D tColor; uniform sampler2D tND; uniform vec2 texel; uniform float px; uniform vec3 inkCol; uniform vec3 fogCol;
  uniform float sat; uniform float expo; uniform vec3 lift; uniform vec3 gain; uniform float vign; uniform float flash; uniform float inkK; varying vec2 vUv;
  vec3 shoulder(vec3 x){ return mix(x, 0.8 + 0.32 * (1.0 - exp(-(x - 0.8) / 0.32)), step(0.8, x)); }
  void main(){
    vec3 c = texture2D(tColor, vUv).rgb * expo;
    if (inkK > 0.0) {
      vec4 nd = texture2D(tND, vUv); float zc = nd.a > 0.0 ? nd.a : 1e5; float ink = 0.0;
      if (dot(nd.xyz, nd.xyz) > 0.25 && zc < 4000.0) {
        float w = mix(4.0, 2.4, smoothstep(1.8, 4.5, log(zc))) * px, bD = 99.0;
        for (int d = 0; d < 4; d++) {
          vec2 st = d == 0 ? vec2(1.0, 0.0) : d == 1 ? vec2(0.0, 1.0) : d == 2 ? vec2(0.7071, 0.7071) : vec2(0.7071, -0.7071);
          for (int s = 1; s <= 5; s++) { float fs = float(s), fl = fs * (d > 1 ? 1.4142 : 1.0); if (fl > w + 1.0) break;
            vec4 a = texture2D(tND, vUv + st * texel * fs), b = texture2D(tND, vUv - st * texel * fs);
            if (a.a <= 0.0) a.a = 1e5; if (b.a <= 0.0) b.a = 1e5;
            if (2.0 - zc / a.a - zc / b.a > 0.02) bD = min(bD, fl); }
        }
        ink = (1.0 - smoothstep(w - 0.6, w + 0.4, bD)) * (1.0 - smoothstep(120.0, 400.0, zc)) * inkK;
      }
      c = mix(c, inkCol, ink);
    }
    float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
    c = mix(vec3(l), c, sat);
    c = c * gain + lift * (1.0 - clamp(c, 0.0, 1.0));
    c = shoulder(max(c, 0.0));
    vec2 q = (vUv - 0.5) * vec2(0.75, 1.0);
    c *= 1.0 - vign * smoothstep(0.25, 0.75, length(q));
    c = mix(c, vec3(1.0), flash);
    gl_FragColor = vec4(c, 1.0);
  }`,
});
// camera motion blur: reconstruct world position from view depth, reproject with last frame's camera
const mbMat = new THREE.ShaderMaterial({
  uniforms: { tColor: { value: rtPost.texture }, tND: { value: rtND.texture }, texel: { value: new THREE.Vector2(1 / W, 1 / H) }, projInv: { value: new THREE.Matrix4() }, camWorld: { value: new THREE.Matrix4() }, prevVP: { value: new THREE.Matrix4() }, amt: { value: 0 } },
  vertexShader: FSV,
  fragmentShader: `uniform sampler2D tColor; uniform sampler2D tND; uniform vec2 texel; uniform mat4 projInv; uniform mat4 camWorld; uniform mat4 prevVP; uniform float amt; varying vec2 vUv;
  void main(){
    vec3 c0 = texture2D(tColor, vUv).rgb;
    if (amt <= 0.001) { gl_FragColor = vec4(c0, 1.0); return; }
    float z = texture2D(tND, vUv).a; z = z > 0.0 ? z : 3000.0;
    vec4 v = projInv * vec4(vUv * 2.0 - 1.0, 1.0, 1.0); v.xyz /= v.w;
    vec3 vp = v.xyz / -v.z * z;
    vec4 pc = prevVP * (camWorld * vec4(vp, 1.0));
    vec2 vel = (vUv - (pc.xy / pc.w * 0.5 + 0.5)) * amt;
    float lp = length(vel / texel); if (lp > 48.0) vel *= 48.0 / lp;
    if (lp < 0.7) { gl_FragColor = vec4(c0, 1.0); return; }
    vec3 acc = vec3(0.0);
    for (int i = 0; i < 14; i++) { float t = float(i) / 13.0 - 0.5; acc += texture2D(tColor, vUv - vel * t).rgb; }
    gl_FragColor = vec4(acc / 14.0, 1.0);
  }`,
});
const dofMat = new THREE.ShaderMaterial({
  uniforms: { tColor: { value: rtMB.texture }, tND: { value: rtND.texture }, texel: { value: new THREE.Vector2(1 / W, 1 / H) }, focus: { value: 10 }, cInf: { value: 0 }, cMax: { value: 18 } },
  vertexShader: FSV,
  fragmentShader: `uniform sampler2D tColor; uniform sampler2D tND; uniform vec2 texel; uniform float focus; uniform float cInf; uniform float cMax; varying vec2 vUv;
  float coc(float z){ z = z > 0.0 ? z : 1e5; return min(cMax, cInf * abs(1.0 - focus / max(z, 0.05))); }
  vec3 enc(vec3 c){ c = clamp(c, 0.0, 1.0); return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c)); }
  void main(){
    vec3 c0 = texture2D(tColor, vUv).rgb;
    float cc = coc(texture2D(tND, vUv).a);
    if (cInf < 0.3 || cc < 0.6) { gl_FragColor = vec4(enc(c0), 1.0); return; }
    vec3 acc = c0; float ws = 1.0;
    for (int i = 0; i < 48; i++) {
      float fi = float(i) + 0.5, r = sqrt(fi / 48.0) * cc, a = fi * 2.39996;
      vec2 uv = vUv + vec2(cos(a), sin(a)) * r * texel;
      float w = clamp(coc(texture2D(tND, uv).a) - r + 1.0, 0.0, 1.0);
      vec3 s = texture2D(tColor, uv).rgb; w *= 1.0 + 2.0 * smoothstep(0.85, 1.4, dot(s, vec3(0.333))); // bright bokeh
      acc += s * w; ws += w;
    }
    gl_FragColor = vec4(enc(acc / ws), 1.0);
  }`,
});

// ---------- per-frame ----------
const v3 = (a) => new THREE.Vector3(a[0], a[1], a[2]);
const lin = (hex) => new THREE.Color(hex).convertSRGBToLinear();
const lum = (c) => 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
const setCam = (cam, target) => {
  target.position.set(...cam.pos); target.up.set(0, 1, 0); target.lookAt(...cam.look);
  target.fov = cam.fov; target.updateProjectionMatrix();
  if (cam.roll) target.rotateZ((cam.roll * Math.PI) / 180);
  target.updateMatrixWorld();
};
const prevCam = new THREE.PerspectiveCamera(40, W / H, 0.1, 8000);
const q4 = (x, s) => Math.round(x / s) * s;
const applyLight = (L, S) => {
  const d = v3(sunDir(L)), flashK = S.lightning || 0;
  sun.color.setRGB(...L.sun); sun.intensity = Math.PI * L.sunK * (1 + 4 * flashK);
  hemi.color.setRGB(...L.amb); hemi.groundColor.setRGB(...L.gnd); hemi.intensity = Math.PI * L.hemiK * (1 + 2 * flashK);
  const c = v3(S.shadow.c), r = S.shadow.r;
  sun.position.copy(c).addScaledVector(d, 300); sun.target.position.copy(c);
  const sc = sun.shadow.camera; sc.left = -r; sc.right = r; sc.top = r; sc.bottom = -r; sc.near = 1; sc.far = 700; sc.updateProjectionMatrix();
  // sky
  const phys = L.sky === "physical";
  WORLD.sky.phys.visible = envPhys.visible = phys; WORLD.sky.grad.visible = envGrad.visible = !phys;
  const fogC = lin(L.hor);
  scene.fog.color.copy(fogC); scene.fog.density = L.fogD;
  WORLD.sky.skyU.fogCol.value.copy(fogC); WORLD.sky.skyU.skyK.value = L.skyK ?? 1.6;
  const pu = WORLD.sky.phys.material.uniforms;
  pu.sunPosition.value.copy(d); pu.turbidity.value = L.turbidity ?? 3; pu.rayleigh.value = L.rayleigh ?? 1.5; pu.mieCoefficient.value = 0.004; pu.mieDirectionalG.value = 0.8;
  const gu = WORLD.sky.grad.material.uniforms;
  gu.top.value.copy(lin(L.top)); gu.mid.value.copy(lin(L.mid)); gu.hor.value.copy(fogC); gu.sunDir.value.copy(d); gu.sunCol.value.setRGB(L.sun[0] * 0.5, L.sun[1] * 0.5, L.sun[2] * 0.5); gu.flash.value = flashK;
  // IBL
  const key = [L.sky, L.top, L.mid, L.hor, q4(L.az, 15), q4(L.el, 6), q4(L.turbidity || 0, 2), flashK > 0.3 ? 1 : 0].join("|");
  scene.environment = envFor(key);
  for (const m of WORLD.mats) m.envMapIntensity = (m.userData.envBase ?? 1) * (L.envK ?? 0.6);
  applyWet(WORLD.mats, L.wet || 0);
  // grade
  gradeMat.uniforms.sat.value = L.sat; gradeMat.uniforms.expo.value = L.expo ?? 1; gradeMat.uniforms.inkK.value = S.ink ?? L.ink ?? 0;
  gradeMat.uniforms.lift.value.set(...L.lift); gradeMat.uniforms.gain.value.set(...L.gain);
  // practical lights: lanterns nearest the action
  const P = L.practical || 0, focus = v3(S.cam.look);
  const near = WORLD.lanterns.map((p) => [p, focus.distanceTo(v3(p))]).sort((a, b) => a[1] - b[1]).slice(0, LANTERN_POOL);
  lampPool.forEach((l, i) => { const p = near[i]; if (!p) { l.intensity = 0; return; } l.position.set(...p[0]); l.intensity = P * 55 * (1 + 0.07 * Math.sin(S.f * 1.9 + i * 2.1) + 0.05 * Math.sin(S.f * 5.3 + i)); });
  // card brightness normaliser: a neutral card reads at its painted colour under this preset (+ local practicals add on top)
  const E = lum(L.sun) * L.sunK * 0.8 + 0.5 * (lum(L.amb) + lum(L.gnd)) * L.hemiK;
  S.cardGain = (L.cardK ?? 1) / Math.max(0.25, E) * (L.practical ? 1.25 : 1);
  S.cardTint = [Math.min(1.2, (L.sun[0] * L.sunK * 0.5 + L.amb[0] * L.hemiK) / Math.max(0.25, E) * 0.8), Math.min(1.2, (L.sun[1] * L.sunK * 0.5 + L.amb[1] * L.hemiK) / Math.max(0.25, E) * 0.8), Math.min(1.2, (L.sun[2] * L.sunK * 0.5 + L.amb[2] * L.hemiK) / Math.max(0.25, E) * 0.8)];
};

window.renderFrame = (f) => {
  const S = frameState(f); S.f = f;
  setCam(S.cam, camera);
  setCam(frameState(Math.max(0, f - 1)).cam, prevCam);
  applyLight(S.light, S);
  WORLD.update(f, S, camera);
  WORLD.sky.phys.position.copy(camera.position); WORLD.sky.grad.position.copy(camera.position);
  // headlights (SpotLights + faint volumetric cones in rain)
  const V = S.world && S.world.van, hp = WORLD.vanHeads(), hd = WORLD.vanDir();
  heads.forEach((s, i) => {
    s.intensity = V && V.lights ? 420 * V.lights : 0; s.position.copy(hp[i]); s.target.position.copy(hp[i]).addScaledVector(hd, 20);
    beams[i].visible = !!(V && V.lights); beams[i].position.copy(hp[i]); beams[i].lookAt(s.target.position);
  });
  beamMat.uniforms.k.value = V && V.lights ? 0.05 * V.lights * (0.6 + 0.6 * (S.light.rain || 0)) : 0;
  // explosion light
  boomLight.intensity = S.boom ? S.boom.k * 9000 : 0; if (S.boom) boomLight.position.set(...S.boom.pos);
  // cards
  const seen = new Set();
  for (const a of S.actors) {
    const DW = a.wide ? 1000 : 600, DH = a.wide ? 1150 : 1000;
    const c = getCard(a.id, DW, DH); seen.add(a.id);
    const key = a.kind + JSON.stringify(a.opts) + (a.outfitKey || "");
    if (key !== c.key) {
      c.key = key;
      c.g.setTransform(1, 0, 0, 1, 0, 0); c.g.clearRect(0, 0, c.cv.width, c.cv.height);
      c.g.setTransform(c.sc, 0, 0, c.sc, 0, 0); c.g.translate((DW - 600) / 2, DH - 1000);
      drawFn[a.kind](new T.Pen(c.g), a);
      c.tex.needsUpdate = true;
    }
    const gy = groundAt(a.pos[0], a.pos[1]), y = a.y ?? gy, s = a.scale || 1;
    c.mesh.position.set(a.pos[0], y + (a.lift || 0), a.pos[1]);
    let mirror = 1;
    if (a.kind === "side" && a.dir) { const r = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0); mirror = a.dir[0] * r.x + a.dir[1] * r.z < 0 ? -1 : 1; }
    c.mesh.scale.set(s * mirror, s, s);
    c.mesh.rotation.set(0, Math.atan2(camera.position.x - a.pos[0], camera.position.z - a.pos[1]), ((a.roll || 0) * Math.PI) / 180);
    c.pullU.value = pullFor(a); c.gainU.value = S.cardGain * (a.bright ?? 1);
    c.mesh.visible = a.visible !== false;
    c.blob.visible = a.visible !== false && a.blob !== false && !(a.lift > 0.3);
    c.blob.position.set(a.pos[0], gy + 0.03, a.pos[1]); c.blob.scale.setScalar(s * (1 - Math.min(0.6, Math.max(0, a.lift || 0) * 0.4)));
    c.blob.rotation.y = c.mesh.rotation.y; c.blob.material.opacity = Math.min(1, 0.55 + 0.45 * (S.light.hemiK || 1));
  }
  for (const [id, c] of cards) if (!seen.has(id)) { c.mesh.visible = false; c.blob.visible = false; }
  // 2D fx cards
  const seenFx = new Set();
  for (const e of S.fx) {
    const c = getFx(e.id, e.kind); seenFx.add(e.id);
    const key = JSON.stringify([e.t, e.seed, e.col]);
    if (key !== c.key) { c.key = key; c.g.setTransform(1, 0, 0, 1, 0, 0); c.g.clearRect(0, 0, c.cv.width, c.cv.height); fxDraw[e.kind](new T.Pen(c.g), e); c.tex.needsUpdate = true; }
    c.mesh.position.set(...e.pos);
    if (e.flat) c.mesh.rotation.set(-Math.PI / 2, 0, e.rot || 0); else { c.mesh.quaternion.copy(camera.quaternion); if (e.rot) c.mesh.rotateZ(e.rot); }
    c.mesh.scale.set(e.size * (e.mirror ? -1 : 1), e.size, e.size);
    c.mesh.material.opacity = e.alpha ?? 1;
    c.mesh.material.color.setRGB(...(e.kind === "glow" ? [1, 1, 1] : S.cardTint));
    c.mesh.visible = true;
  }
  for (const [id, c] of fxCards) if (!seenFx.has(id)) c.mesh.visible = false;
  VFX.update(f, S, camera, groundAt, H);

  // pass 1: colour
  renderer.shadowMap.enabled = true; renderer.shadowMap.needsUpdate = true;
  renderer.setRenderTarget(rtColor); renderer.setClearColor(0x000000, 1); renderer.clear();
  renderer.render(scene, camera);
  // pass 2: normal + depth (world -> normals/depth, cards -> alpha-tested depth, everything else hidden)
  const hidden = [], swapped = [];
  scene.traverse((o) => {
    if (!o.visible) return;
    if (o.isPoints || o.isLine || o.isSprite || o.isLight) { if (!o.isLight) { hidden.push(o); o.visible = false; } return; }
    if (!o.isMesh) return;
    if (o.userData.nd) { swapped.push([o, o.material]); o.material = o.userData.nd; }
    else if (o.userData.noND || o.isInstancedMesh || (o.material.transparent && o.material.opacity < 0.5)) { hidden.push(o); o.visible = false; }
    else { swapped.push([o, o.material]); const m = Array.isArray(o.material) ? o.material[0] : o.material; o.material = m.alphaTest > 0 && m.map ? ndAlpha(m.map) : ndWorld; }
  });
  const fog = scene.fog, env = scene.environment; scene.fog = null; renderer.shadowMap.enabled = false;
  renderer.setRenderTarget(rtND); renderer.setClearColor(0x000000, 0); renderer.clear();
  renderer.render(scene, camera);
  scene.fog = fog; scene.environment = env;
  for (const [o, m] of swapped) o.material = m;
  for (const o of hidden) o.visible = true;
  // pass 3: grade
  gradeMat.uniforms.flash.value = Math.min(0.9, S.flash || 0); gradeMat.uniforms.vign.value = S.vign ?? 0.18;
  fsQuad.material = gradeMat; renderer.setRenderTarget(rtPost); renderer.render(fsScene, fsCam);
  // pass 4: motion blur (180-degree shutter by default; off across cuts)
  const jump = camera.position.distanceTo(prevCam.position) > 3.5 || S.cut;
  mbMat.uniforms.projInv.value.copy(camera.projectionMatrixInverse); mbMat.uniforms.camWorld.value.copy(camera.matrixWorld);
  mbMat.uniforms.prevVP.value.multiplyMatrices(prevCam.projectionMatrix, prevCam.matrixWorldInverse);
  mbMat.uniforms.amt.value = window.NOMB || jump ? 0 : 0.5 * (S.mb ?? 1);
  fsQuad.material = mbMat; renderer.setRenderTarget(rtMB); renderer.render(fsScene, fsCam);
  // pass 5: lens DOF -> screen
  dofMat.uniforms.focus.value = S.dof.focus; dofMat.uniforms.cInf.value = window.NODOF ? 0 : S.dof.cInf * PX;
  fsQuad.material = dofMat; renderer.setRenderTarget(null); renderer.render(fsScene, fsCam);
  return canvas.toDataURL("image/jpeg", 0.95);
};
window.TOTAL = TOTAL;
window.ready = true;
