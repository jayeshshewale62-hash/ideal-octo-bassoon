// PBR world builder for the v2 demo. Realistic materials (MeshStandardMaterial + procedural albedo/normal/roughness),
// layered heightmap terrain, instanced wind-swayed grass, layered trees, real-scale props, distant mountains in haze,
// physical / 3-stop sky, drifting clouds. Replace the LAYOUT-driven parts for each story; keep the builders.
// buildWorld(scene, THREE) -> { mats, walls, lanterns, cart, car, sky, clouds, update(f, S, camera) }
import * as THREE from "three";
import { Sky } from "three/addons/objects/Sky.js";
import * as PB from "./pbr.js";
import { cloudCanvas } from "./paint.js";
import { groundAt, polyDist, polyAt, polyLen, fbm } from "./terrain.js";
import { ROAD, ROAD_W, HOUSES, LANTERNS, TREES, PROPS } from "./layout.js";

export const buildWorld = (scene, Q = { grass: 1, trees: 1 }) => {
  const rnd = PB.rng(77);
  const mats = [];
  const M = (m) => { mats.push(m); return m; };
  const add = (o, cast = true, recv = true) => { o.traverse((c) => { if (c.isMesh) { c.castShadow = cast; c.receiveShadow = recv; } }); scene.add(o); return o; };

  // ---------------- materials (real-world tile sizes) ----------------
  const MAT = {
    grass: M(PB.pbrMat("grass", () => PB.grassGround(4, 1024, "#4a6130"), { macro: [0.025, 0.28], wettable: true })),
    dirt: M(PB.pbrMat("dirt", () => PB.dirtGround(3), { macro: [0.04, 0.2], wettable: true })),
    road: M(PB.pbrMat("road", () => PB.roadTex(2, { width: ROAD_W, lines: "both" }), { macro: [0.05, 0.12], wettable: true, normalStrength: 3 })),
    track: M(PB.pbrMat("track", () => PB.roadTex(12, { width: 4.5, dirt: true }), { wettable: true })),
    cobble: M(PB.pbrMat("cobble", () => PB.cobble(5), { wettable: true, normalStrength: 3 })),
    flag: M(PB.pbrMat("flag", () => PB.cobble(15, 1024, { cells: 5, flag: true, colr: "#8d877c" }), { wettable: true, normalStrength: 3 })),
    brick: M(PB.pbrMat("brick", () => PB.stoneBrick(6), { normalStrength: 3.2, wettable: true })),
    brick2: M(PB.pbrMat("brick2", () => PB.stoneBrick(16, 1024, { colr: "#b49c7e", mortar: "#cdc3b0" }), { normalStrength: 3.2, wettable: true })),
    plaster: M(PB.pbrMat("plaster", () => PB.dirtGround(21, 512, "#d8cdb8"), { normalScale: 0.4 })),
    wood: M(PB.pbrMat("wood", () => PB.woodPlanks(7), { normalStrength: 2.6, wettable: true })),
    woodDark: M(PB.pbrMat("woodDark", () => PB.woodPlanks(17, 1024, { colr: "#4a3322" }), { wettable: true })),
    terracotta: M(PB.pbrMat("terracotta", () => PB.roofTiles(9), { normalStrength: 3.5, wettable: true, side: THREE.DoubleSide })),
    slate: M(PB.pbrMat("slate", () => PB.roofTiles(19, 1024, { kind: "slate" }), { normalStrength: 3, wettable: true, side: THREE.DoubleSide })),
    bark: M(PB.pbrMat("bark", () => PB.bark(8), { normalStrength: 4 })),
    rock: M(PB.pbrMat("rock", () => PB.cobble(25, 512, { cells: 4, colr: "#7d776f" }), { macro: [0.01, 0.25] })),
    glass: M(PB.glassMat()),
    iron: M(PB.plainMat(0x2b2b2e, 0.45, 0.85)),
    brass: M(PB.plainMat(0xb08a3e, 0.35, 0.9)),
    canvasW: M(PB.pbrMat("fabric", () => PB.fabric(10), { normalScale: 0.2 })),
    leaf: M(PB.plainMat(0xffffff, 0.8, 0, { vertexColors: true })),
    pine: M(PB.plainMat(0xffffff, 0.88, 0, { vertexColors: true })),
    leaf2: M(PB.plainMat(0xe8ffe0, 0.82, 0, { vertexColors: true })),
    tire: M(PB.plainMat(0x161618, 0.85, 0)),
    chrome: M(PB.plainMat(0xd9dde2, 0.15, 1)),
    sign: M(PB.plainMat(0x1f6b3a, 0.4, 0.2)),
  };
  const leafCardTex = (() => { const t = new THREE.CanvasTexture(PB.leafCard(11)); t.colorSpace = THREE.SRGBColorSpace; return t; })();
  MAT.leafCard = M(new THREE.MeshStandardMaterial({ map: leafCardTex, alphaTest: 0.5, side: THREE.DoubleSide, roughness: 0.75 }));
  const tile = (geo, mat) => PB.boxUV(geo, mat.userData.tile || 1);

  // ---------------- terrain: layered heightmap (fine near the road, coarse far) ----------------
  {
    const N = 220, ext = 900, pos = [], uv = [], idx = [];
    const g = (i) => { const t = i / N * 2 - 1; return Math.sign(t) * Math.abs(t) ** 1.8 * ext; }; // denser in the middle
    for (let j = 0; j <= N; j++) for (let i = 0; i <= N; i++) { const x = g(i), z = g(j) - 40; pos.push(x, groundAt(x, z) - 0.05, z); uv.push(x / MAT.grass.userData.tile, z / MAT.grass.userData.tile); }
    for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) { const a = j * (N + 1) + i, b = a + 1, c = a + N + 1, d = c + 1; idx.push(a, c, b, b, c, d); }
    const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); geo.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2)); geo.setIndex(idx); geo.computeVertexNormals();
    add(new THREE.Mesh(geo, MAT.grass), false, true);
  }
  // ribbon along a polyline at terrain height (UV: u across 0..1, v = metres / tile)
  const ribbon = (pts, w, mat, lift = 0.04, vtile = null) => {
    const L = polyLen(pts), n = Math.max(8, Math.round(L / 1.0)), pos = [], uv = [], idx = [], vt = vtile ?? mat.userData.tile;
    for (let i = 0; i <= n; i++) {
      const s = (i / n) * L, p = polyAt(pts, s);
      for (const sd of [-1, 1]) { const x = p.x - p.dz * sd * w / 2, z = p.z + p.dx * sd * w / 2; pos.push(x, groundAt(p.x, p.z) + lift, z); uv.push(sd < 0 ? 0 : 1, s / vt); }
      if (i < n) { const a = i * 2; idx.push(a, a + 2, a + 1, a + 1, a + 2, a + 3); }
    }
    const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); geo.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2)); geo.setIndex(idx); geo.computeVertexNormals();
    if (geo.attributes.normal.getY(0) < 0) { for (let i = 0; i < idx.length; i += 3) [idx[i + 1], idx[i + 2]] = [idx[i + 2], idx[i + 1]]; geo.setIndex(idx); geo.computeVertexNormals(); }
    return add(new THREE.Mesh(geo, mat), false, true);
  };
  const roadEnd = polyLen(ROAD) - 70;
  const asphaltPts = [], trackPts = [];
  for (let s = 0; s <= polyLen(ROAD); s += 4) { const p = polyAt(ROAD, s); (s <= roadEnd ? asphaltPts : trackPts).push([p.x, p.z]); }
  trackPts.unshift(asphaltPts[asphaltPts.length - 1]);
  ribbon(asphaltPts, ROAD_W, MAT.road, 0.05, 14);
  ribbon(asphaltPts, ROAD_W + 3.2, MAT.dirt, 0.02);           // dirt shoulders
  ribbon(trackPts, 4.5, MAT.track, 0.05, 12);
  ribbon([[0, 100], [0.5, 24]], ROAD_W + 9, MAT.flag, 0.03);  // flagstone village square under the road edge
  ribbon([[0, 100], [0.5, 24]], ROAD_W, MAT.road, 0.055, 14);

  // ---------------- houses: stone-brick walls, mortar depth, wood door, reflective glass windows, tile roofs ----------------
  const walls = [];
  const gableRoof = (w, d, rise, over, mat) => {
    const hw = w / 2 + over, hd = d / 2 + over, g = new THREE.BufferGeometry(), sl = Math.hypot(hd, rise), t = mat.userData.tile;
    const v = [-hw, 0, hd, hw, 0, hd, hw, rise, 0, -hw, rise, 0, -hw, rise, 0, hw, rise, 0, hw, 0, -hd, -hw, 0, -hd];
    const uv = [0, 0, 2 * hw / t, 0, 2 * hw / t, sl / t, 0, sl / t, 0, sl / t, 2 * hw / t, sl / t, 2 * hw / t, 0, 0, 0];
    g.setAttribute("position", new THREE.Float32BufferAttribute(v, 3)); g.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
    g.setIndex([0, 1, 2, 0, 2, 3, 4, 5, 6, 4, 6, 7]); g.computeVertexNormals();
    const m = new THREE.Mesh(g, mat);
    const thick = new THREE.Mesh(tile(new THREE.BoxGeometry(2 * hw, 0.12, 0.18), MAT.woodDark), MAT.woodDark); thick.position.set(0, rise + 0.04, 0);
    const grp = new THREE.Group(); grp.add(m, thick); return grp;
  };
  const house = ([x, z, w, d, hgt, yaw, roofKind, storeys], i) => {
    const g = new THREE.Group(), y0 = groundAt(x, z), wallM = i % 3 === 2 ? MAT.brick2 : MAT.brick;
    const body = new THREE.Mesh(tile(new THREE.BoxGeometry(w, hgt, d), wallM), wallM); body.position.y = hgt / 2; g.add(body);
    const base = new THREE.Mesh(tile(new THREE.BoxGeometry(w + 0.25, 0.5, d + 0.25), MAT.rock), MAT.rock); base.position.y = 0.2; g.add(base);
    const rise = 1.6 + 0.18 * w, roof = gableRoof(w, d, rise, 0.5, roofKind ? MAT.slate : MAT.terracotta); roof.position.y = hgt; g.add(roof);
    // gable ends
    const gab = new THREE.Shape([new THREE.Vector2(-d / 2, 0), new THREE.Vector2(d / 2, 0), new THREE.Vector2(0, rise * (d / 2) / (d / 2 + 0.5))]);
    for (const s of [-1, 1]) { const ge = new THREE.Mesh(tile(new THREE.ShapeGeometry(gab), wallM), wallM); ge.rotation.y = s * Math.PI / 2; ge.position.set(s * w / 2, hgt, 0); g.add(ge); }
    // door + frame (front face = +z local)
    const door = new THREE.Mesh(tile(new THREE.BoxGeometry(1.1, 2.15, 0.1), MAT.woodDark), MAT.woodDark); door.position.set(-w * 0.18, 1.08 + 0.2, d / 2 + 0.03); g.add(door);
    const knob = new THREE.Mesh(new THREE.SphereGeometry(0.045, 10, 8), MAT.brass); knob.position.set(-w * 0.18 + 0.38, 1.25, d / 2 + 0.1); g.add(knob);
    // windows: wood frame + glass + sill, per storey
    for (let s = 0; s < storeys; s++) for (const wx of s === 0 ? [w * 0.22] : [-w * 0.22, w * 0.22]) {
      const wy = 1.7 + s * (hgt / storeys), fr = new THREE.Mesh(tile(new THREE.BoxGeometry(1.15, 1.35, 0.14), MAT.wood), MAT.wood); fr.position.set(wx, wy, d / 2 + 0.02); g.add(fr);
      const gl = new THREE.Mesh(new THREE.BoxGeometry(0.95, 1.15, 0.04), MAT.glass); gl.position.set(wx, wy, d / 2 + 0.08); g.add(gl);
      const mull = new THREE.Mesh(new THREE.BoxGeometry(0.06, 1.15, 0.06), MAT.wood); mull.position.set(wx, wy, d / 2 + 0.1); g.add(mull);
      const sill = new THREE.Mesh(tile(new THREE.BoxGeometry(1.35, 0.08, 0.3), MAT.rock), MAT.rock); sill.position.set(wx, wy - 0.72, d / 2 + 0.12); g.add(sill);
    }
    g.position.set(x, y0, z); g.rotation.y = yaw;
    add(g);
    // wall AABB (world) for card depth-pull near walls
    const c = Math.abs(Math.cos(yaw)), s = Math.abs(Math.sin(yaw)), hx = (w * c + d * s) / 2, hz = (w * s + d * c) / 2;
    walls.push([x - hx, z - hz, x + hx, z + hz]);
  };
  HOUSES.forEach(house);

  // ---------------- street lanterns (iron post, glass box with emissive core; PointLights come from the engine pool) ----------------
  const lanternGlow = M(new THREE.MeshStandardMaterial({ color: 0xffe2a8, emissive: 0xffb050, emissiveIntensity: 0, roughness: 0.3 }));
  const lanterns = LANTERNS.map(([x, z]) => {
    const g = new THREE.Group(), y0 = groundAt(x, z);
    const post = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.09, 3.2, 10), MAT.iron); post.position.y = 1.6; g.add(post);
    const arm = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.06, 0.5), MAT.iron); arm.position.set(0, 3.1, 0.22); g.add(arm);
    const box = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.46, 0.34), MAT.glass); box.position.set(0, 2.82, 0.45); g.add(box);
    const core = new THREE.Mesh(new THREE.SphereGeometry(0.1, 12, 10), lanternGlow); core.position.set(0, 2.8, 0.45); g.add(core);
    const cap = new THREE.Mesh(new THREE.ConeGeometry(0.28, 0.2, 4), MAT.iron); cap.position.set(0, 3.15, 0.45); cap.rotation.y = Math.PI / 4; g.add(cap);
    g.position.set(x, y0, z); g.rotation.y = x < 0 ? Math.PI / 2 : -Math.PI / 2;
    add(g, true, false);
    const lp = new THREE.Vector3(0, 2.8, 0.45).applyMatrix4(g.matrixWorld.compose(g.position, g.quaternion, g.scale));
    return [lp.x, lp.y, lp.z];
  });

  // ---------------- trees: tapered bark trunk + branches + clustered leaf spheres + alpha leaf cards ----------------
  const trees = [];
  const tree = ([x, z, s]) => {
    const g = new THREE.Group(), y0 = groundAt(x, z), h = (5 + rnd() * 3) * s;
    const trunk = new THREE.Mesh(tile(new THREE.CylinderGeometry(0.16 * s, 0.32 * s, h, 12, 4), MAT.bark), MAT.bark); trunk.position.y = h / 2; g.add(trunk);
    const crown = new THREE.Group(); crown.position.y = h * 0.82; g.add(crown);
    for (let i = 0; i < 4; i++) { const b = new THREE.Mesh(new THREE.CylinderGeometry(0.05 * s, 0.11 * s, 2.2 * s, 7), MAT.bark), a = i * 1.7 + rnd(); b.position.set(Math.cos(a) * 0.6 * s, -0.4 * s, Math.sin(a) * 0.6 * s); b.rotation.set(Math.sin(a) * 0.9, 0, -Math.cos(a) * 0.9); crown.add(b); }
    for (let i = 0; i < 9; i++) {
      const r = (1.0 + rnd() * 0.9) * s, geo = new THREE.IcosahedronGeometry(r, Q.trees >= 1 ? 4 : 3), p = geo.attributes.position, cols = [];
      for (let k = 0; k < p.count; k++) {
        const nx = p.getX(k) / r, ny = p.getY(k) / r, nz = p.getZ(k) / r;
        const lump = fbm(nx * 2.2 + i * 3.1, ny * 2.2 + nz * 1.7, 4), f = 1 + 0.32 * (lump - 0.5) + 0.06 * (fbm(nx * 9 + i, nz * 9 + ny, 2) - 0.5);
        p.setXYZ(k, p.getX(k) * f, p.getY(k) * f * 0.85, p.getZ(k) * f);
        // vertex colour: darker underneath and in the dips (fake canopy self-occlusion), yellow-green on top, per-leaf speckle
        const occl = 0.55 + 0.45 * (0.5 + 0.5 * ny) * (0.6 + 0.8 * (lump - 0.3)), sp = 0.85 + 0.3 * fbm(nx * 23 + i, ny * 23 + nz * 11, 1);
        cols.push(0.13 * occl * sp + 0.02 * Math.max(0, ny), 0.23 * occl * sp + 0.03 * Math.max(0, ny), 0.08 * occl * sp); // dark core: leaf cards carry the detail
      }
      geo.setAttribute("color", new THREE.Float32BufferAttribute(cols, 3));
      geo.computeVertexNormals();
      const m = new THREE.Mesh(geo, i % 3 ? MAT.leaf : MAT.leaf2), a = rnd() * 6.3, rr = (i ? 1.3 : 0) * s * rnd();
      m.position.set(Math.cos(a) * rr, (rnd() - 0.2) * 1.4 * s, Math.sin(a) * rr); crown.add(m);
    }
    for (let i = 0; i < Math.round(70 * Q.trees); i++) { const c = new THREE.Mesh(new THREE.PlaneGeometry(1.5 * s, 1.5 * s), MAT.leafCard), a = rnd() * 6.3, rr = (1.3 + 1.1 * rnd()) * s; c.position.set(Math.cos(a) * rr, (rnd() - 0.3) * 2 * s, Math.sin(a) * rr); c.rotation.set(rnd() * 3, rnd() * 3, 0); crown.add(c); }
    g.position.set(x, y0, z); g.rotation.y = rnd() * 6;
    add(g); trees.push({ crown, seed: rnd() * 10 });
  };
  TREES.forEach(tree);
  for (let i = 0; i < 160; i++) { // background forest on the hills (cheaper: no cards)
    const x = (rnd() - 0.5) * 700, z = -40 + (rnd() - 0.5) * 700, [d] = polyDist(ROAD, x, z);
    if (d < 30) continue;
    const s = 1 + rnd() * 0.8, y0 = groundAt(x, z), g = new THREE.Group(), h = 6 * s;
    const t = new THREE.Mesh(new THREE.CylinderGeometry(0.2 * s, 0.35 * s, h, 6), MAT.bark); t.position.y = h / 2; g.add(t);
    for (let k = 0; k < 4; k++) { // stacked, noise-displaced conifer tiers (no toy cones)
      const geo = new THREE.ConeGeometry((2.6 - 0.55 * k) * s, (3.6 - 0.4 * k) * s, 28, 6), p = geo.attributes.position, cols = [];
      for (let v = 0; v < p.count; v++) {
        const a = Math.atan2(p.getZ(v), p.getX(v)), droop = 0.5 + 0.5 * Math.cos(a * 9 + k), n = 1 + 0.22 * (fbm(p.getX(v) * 2 + i + k, p.getZ(v) * 2 + p.getY(v), 3) - 0.5) * 2 + 0.08 * droop;
        p.setXYZ(v, p.getX(v) * n, p.getY(v) - 0.12 * droop * s, p.getZ(v) * n);
        const t = (p.getY(v) / ((3.6 - 0.4 * k) * s)) + 0.5, sh = 0.55 + 0.45 * t;
        cols.push(0.06 * sh, 0.13 * sh, 0.07 * sh);
      }
      geo.setAttribute("color", new THREE.Float32BufferAttribute(cols, 3)); geo.computeVertexNormals();
      const c = new THREE.Mesh(geo, MAT.pine); c.position.y = h * 0.45 + k * 1.5 * s; c.rotation.y = k; g.add(c);
    }
    g.position.set(x, y0, z); add(g, true, false);
  }

  // ---------------- instanced grass blades with vertex wind sway: sin(time + worldPos.x) ----------------
  const wind = { time: { value: 0 }, amp: { value: 1 } };
  {
    const blade = new THREE.BufferGeometry();
    // 7-vertex curved blade (bends forward toward the tip), root dark -> tip light vertex colours
    blade.setAttribute("position", new THREE.Float32BufferAttribute([-0.035, 0, 0, 0.035, 0, 0, -0.026, 0.22, 0.015, 0.026, 0.22, 0.015, -0.014, 0.42, 0.05, 0.014, 0.42, 0.05, 0, 0.6, 0.11], 3));
    blade.setAttribute("normal", new THREE.Float32BufferAttribute([0, 0.6, 0.8, 0, 0.6, 0.8, 0, 0.75, 0.66, 0, 0.75, 0.66, 0, 0.88, 0.47, 0, 0.88, 0.47, 0, 1, 0.2], 3));
    blade.setAttribute("color", new THREE.Float32BufferAttribute([0.45, 0.45, 0.4, 0.45, 0.45, 0.4, 0.75, 0.78, 0.68, 0.75, 0.78, 0.68, 1, 1, 0.92, 1, 1, 0.92, 1.15, 1.12, 0.95], 3));
    blade.setIndex([0, 1, 2, 2, 1, 3, 2, 3, 4, 4, 3, 5, 4, 5, 6]);
    const mat = M(new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.78, side: THREE.DoubleSide, vertexColors: true }));
    mat.onBeforeCompile = (sh) => {
      sh.uniforms.uTime = wind.time; sh.uniforms.uWind = wind.amp;
      sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\nuniform float uTime; uniform float uWind;")
        .replace("#include <begin_vertex>", `#include <begin_vertex>
        { vec4 wp0 = modelMatrix * instanceMatrix * vec4(0.0, 0.0, 0.0, 1.0);
          float k = transformed.y * transformed.y * 2.6;
          float sw = sin(uTime * 1.9 + wp0.x * 0.45 + wp0.z * 0.17) * 0.09 + sin(uTime * 3.7 + wp0.x * 1.3) * 0.025;
          transformed.x += sw * k * uWind; transformed.z += sw * 0.45 * k * uWind; }`);
    };
    mat.customProgramCacheKey = () => "grasswind";
    const N = Math.round(42000 * (Q.grass ?? 1)), inst = new THREE.InstancedMesh(blade, mat, N), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler(), col = new THREE.Color();
    let n = 0;
    for (let tries = 0; n < N && tries < N * 4; tries++) {
      const s = rnd() * polyLen(ROAD), p = polyAt(ROAD, s), off = (rnd() < 0.5 ? -1 : 1) * (ROAD_W / 2 + 1.7 + Math.abs(rnd() - rnd()) * 26);
      const x = p.x - p.dz * off + (rnd() - 0.5) * 2, z = p.z + p.dx * off + (rnd() - 0.5) * 2;
      if (z > 24 && z < 100 && Math.abs(off) < 17) continue; // village square / houses
      e.set((rnd() - 0.5) * 0.5, rnd() * 6.3, (rnd() - 0.5) * 0.5); q.setFromEuler(e);
      const sc = 0.7 + rnd() * 0.9;
      m4.compose(new THREE.Vector3(x, groundAt(x, z) - 0.03, z), q, new THREE.Vector3(sc, sc * (0.8 + rnd() * 0.7), sc));
      inst.setMatrixAt(n, m4); inst.setColorAt(n, col.setHSL(0.21 + rnd() * 0.06, 0.45 + rnd() * 0.2, 0.2 + rnd() * 0.16)); n++;
    }
    inst.count = n; inst.castShadow = false; inst.receiveShadow = true; scene.add(inst);
  }

  // ---------------- props at real-world scale ----------------
  const cartGroup = (withShell = false) => { // ~2.2 m long hand cart, 0.9 m bed height, 1.3 m wheels
    const g = new THREE.Group(), shell = [], inner = new THREE.Group();
    const bed = new THREE.Mesh(tile(new THREE.BoxGeometry(1.25, 0.1, 2.0), MAT.wood), MAT.wood); bed.position.y = 0.75; g.add(bed);
    for (const s of [-1, 1]) {
      const side = new THREE.Mesh(tile(new THREE.BoxGeometry(0.06, 0.55, 2.0), MAT.wood), withShell ? MAT.wood.clone() : MAT.wood); side.position.set(s * 0.62, 1.05, 0); g.add(side); shell.push(side);
      const end = new THREE.Mesh(tile(new THREE.BoxGeometry(1.25, 0.55, 0.06), MAT.wood), withShell ? MAT.wood.clone() : MAT.wood); end.position.set(0, 1.05, s * 1.0); g.add(end); shell.push(end);
      const handle = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 1.2, 8), MAT.woodDark); handle.rotation.x = Math.PI / 2 - 0.25; handle.position.set(s * 0.45, 0.82, 1.5); g.add(handle);
    }
    const wheels = [];
    for (const s of [-1, 1]) {
      const w = new THREE.Group(); w.position.set(s * 0.72, 0.62, 0.15);
      const rim = new THREE.Mesh(new THREE.TorusGeometry(0.6, 0.05, 8, 28), MAT.woodDark); rim.rotation.y = Math.PI / 2; w.add(rim);
      const tyre = new THREE.Mesh(new THREE.TorusGeometry(0.6, 0.025, 6, 28), MAT.iron); tyre.rotation.y = Math.PI / 2; tyre.scale.setScalar(1.05); w.add(tyre);
      for (let k = 0; k < 8; k++) { const sp = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.022, 1.15, 6), MAT.woodDark); sp.rotation.x = (k / 8) * Math.PI; w.add(sp); }
      g.add(w); wheels.push(w);
    }
    if (withShell) { // tarp on top = part of the X-ray shell
      const tarp = new THREE.Mesh(new THREE.CylinderGeometry(0.66, 0.66, 2.02, 18, 1, true, 0, Math.PI), MAT.canvasW.clone()); tarp.rotation.set(Math.PI / 2, Math.PI / 2, 0); tarp.position.y = 1.3; tarp.material.side = THREE.DoubleSide; g.add(tarp); shell.push(tarp);
      // inner mechanism: 82 rockets in a rack, all tied to one fuse ring
      const rocketM = M(PB.plainMat(0xc8322b, 0.5, 0.1)), tipM = M(PB.plainMat(0xe8c34a, 0.4, 0.3));
      for (let k = 0; k < 82; k++) {
        const cx = -0.48 + (k % 9) * 0.12, cz = -0.85 + Math.floor(k / 9) * 0.19;
        const r = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 0.55, 8), rocketM); r.position.set(cx, 1.08, cz); inner.add(r);
        const t = new THREE.Mesh(new THREE.ConeGeometry(0.04, 0.12, 8), tipM); t.position.set(cx, 1.41, cz); inner.add(t);
      }
      const fuseM = M(new THREE.MeshStandardMaterial({ color: 0x3a3028, emissive: 0xff7a20, emissiveIntensity: 0, roughness: 0.9 }));
      const fuse = new THREE.Mesh(new THREE.TorusGeometry(0.5, 0.018, 6, 48), fuseM); fuse.rotation.x = Math.PI / 2; fuse.scale.set(1, 1.75, 1); fuse.position.y = 0.86; inner.add(fuse);
      g.add(inner);
      g.userData = { shell, inner, wheels, fuseM };
    } else g.userData = { shell: [], inner: null, wheels, fuseM: null };
    return g;
  };
  for (const [x, z, yaw] of PROPS.carts) { const c = cartGroup(); c.position.set(x, groundAt(x, z), z); c.rotation.y = yaw; add(c); }
  const barrel = new THREE.CylinderGeometry(0.3, 0.3, 0.88, 16); barrel.translate(0, 0.44, 0);
  for (const [x, z] of PROPS.barrels) { const b = new THREE.Mesh(tile(barrel.clone(), MAT.wood), MAT.wood); b.position.set(x, groundAt(x, z), z); add(b); for (const hy of [0.15, 0.73]) { const hoop = new THREE.Mesh(new THREE.TorusGeometry(0.305, 0.015, 6, 24), MAT.iron); hoop.rotation.x = Math.PI / 2; hoop.position.set(x, groundAt(x, z) + hy, z); add(hoop, false, false); } }
  for (const [x, z, yaw] of PROPS.crates) { const c = new THREE.Mesh(tile(new THREE.BoxGeometry(0.6, 0.6, 0.6), MAT.wood), MAT.wood); c.position.set(x, groundAt(x, z) + 0.3, z); c.rotation.y = yaw; add(c); }
  for (const [[ax, az], [bx, bz]] of PROPS.fences) {
    const L = Math.hypot(bx - ax, bz - az), n = Math.ceil(L / 2.2), yaw = Math.atan2(bx - ax, bz - az);
    for (let i = 0; i <= n; i++) { const x = ax + (bx - ax) * i / n, z = az + (bz - az) * i / n, p = new THREE.Mesh(tile(new THREE.BoxGeometry(0.12, 1.2, 0.12), MAT.woodDark), MAT.woodDark); p.position.set(x, groundAt(x, z) + 0.6, z); add(p); }
    for (let i = 0; i < n; i++) for (const ry of [0.45, 0.95]) {
      const x0 = ax + (bx - ax) * i / n, z0 = az + (bz - az) * i / n, x1 = ax + (bx - ax) * (i + 1) / n, z1 = az + (bz - az) * (i + 1) / n;
      const r = new THREE.Mesh(tile(new THREE.BoxGeometry(0.06, 0.12, L / n), MAT.wood), MAT.wood); r.position.set((x0 + x1) / 2, (groundAt(x0, z0) + groundAt(x1, z1)) / 2 + ry, (z0 + z1) / 2); r.rotation.y = yaw; add(r);
    }
  }
  for (const [x, z, yaw, text] of PROPS.signs) { // reads correctly from the road (canvas text on the +z face only)
    const g = new THREE.Group();
    const post = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 2.4, 8), MAT.chrome); post.position.y = 1.2; g.add(post);
    const c = document.createElement("canvas"); c.width = 512; c.height = 256; const x2 = c.getContext("2d");
    x2.fillStyle = "#1f6b3a"; x2.fillRect(0, 0, 512, 256); x2.strokeStyle = "#f2f2ea"; x2.lineWidth = 12; x2.strokeRect(14, 14, 484, 228);
    x2.fillStyle = "#f2f2ea"; x2.font = "bold 92px sans-serif"; x2.textAlign = "center"; x2.textBaseline = "middle"; x2.fillText(text, 256, 132);
    const tx = new THREE.CanvasTexture(c); tx.colorSpace = THREE.SRGBColorSpace;
    const face = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.65, 0.04), [MAT.sign, MAT.sign, MAT.sign, MAT.sign, M(new THREE.MeshStandardMaterial({ map: tx, roughness: 0.35, metalness: 0.1 })), MAT.sign]);
    face.position.y = 2.15; g.add(face);
    g.position.set(x, groundAt(x, z), z); g.rotation.y = yaw; add(g);
  }
  for (const [x, z, yaw, colr] of PROPS.tents) { // 3.2 m ridge tent
    const tm = M(PB.pbrMat("tent" + colr, () => PB.fabric(31, 512, colr), {})), g = new THREE.Group();
    const shape = new THREE.Shape([new THREE.Vector2(-1.6, 0), new THREE.Vector2(1.6, 0), new THREE.Vector2(0, 2.2)]);
    const body = new THREE.Mesh(tile(new THREE.ExtrudeGeometry(shape, { depth: 3.2, bevelEnabled: false }), tm), [tm, tm]); body.position.z = -1.6; g.add(body);
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 2.5, 6), MAT.woodDark); pole.position.set(0, 1.25, 1.65); g.add(pole);
    g.position.set(x, groundAt(x, z), z); g.rotation.y = yaw; add(g);
  }
  // vehicle: delivery van (~4.6 m) with SpotLight headlights from the engine pool
  const carGroup = (colr) => {
    const g = new THREE.Group(), paint = M(PB.paintMat(colr));
    const body = new THREE.Mesh(new THREE.BoxGeometry(1.8, 1.0, 4.6), paint); body.position.y = 0.85; g.add(body);
    const cab = new THREE.Mesh(new THREE.BoxGeometry(1.7, 0.9, 2.6), paint); cab.position.set(0, 1.75, -0.4); g.add(cab);
    const ws = new THREE.Mesh(new THREE.BoxGeometry(1.55, 0.7, 0.05), MAT.glass); ws.position.set(0, 1.78, 0.92); ws.rotation.x = -0.25; g.add(ws);
    for (const s of [-1, 1]) { const sw = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.55, 1.6), MAT.glass); sw.position.set(s * 0.86, 1.8, -0.3); g.add(sw); }
    for (const [wx, wz] of [[-0.85, 1.45], [0.85, 1.45], [-0.85, -1.5], [0.85, -1.5]]) { const w = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.38, 0.26, 20), MAT.tire); w.rotation.z = Math.PI / 2; w.position.set(wx, 0.38, wz); g.add(w); const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.2, 0.28, 12), MAT.chrome); hub.rotation.z = Math.PI / 2; hub.position.copy(w.position); g.add(hub); }
    const headM = M(new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xfff2cc, emissiveIntensity: 0, roughness: 0.1 }));
    for (const s of [-1, 1]) { const h = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.13, 0.06, 16), headM); h.rotation.x = Math.PI / 2; h.position.set(s * 0.6, 0.95, 2.31); g.add(h); }
    const bump = new THREE.Mesh(new THREE.BoxGeometry(1.85, 0.18, 0.14), MAT.chrome); bump.position.set(0, 0.5, 2.33); g.add(bump);
    g.userData = { headM, heads: [[-0.6, 0.95, 2.35], [0.6, 0.95, 2.35]] };
    return g;
  };
  const car = carGroup(PROPS.vehicles[0][3]);
  { const [x, z, yaw] = PROPS.vehicles[0]; car.position.set(x, groundAt(x, z), z); car.rotation.y = yaw; add(car); }
  const cart = add(cartGroup(true));

  // ---------------- distant mountain silhouettes (fade into fog / haze) ----------------
  {
    const mm = M(PB.plainMat(0xffffff, 0.95, 0, { vertexColors: true }));
    for (let i = 0; i < 22; i++) {
      const a = (i / 22) * Math.PI * 2 + rnd() * 0.2, r = 1500 + rnd() * 700, R = 240 + rnd() * 200, Hh = 160 + rnd() * 200;
      const geo = new THREE.ConeGeometry(R, Hh, 64, 24, true), p = geo.attributes.position, colA = [];
      for (let k = 0; k < p.count; k++) {
        const x = p.getX(k), y = p.getY(k), z = p.getZ(k), t = (y + Hh / 2) / Hh, n = fbm(x * 0.012 + i * 7, z * 0.012 + y * 0.01, 5);
        const f = 1 + (n - 0.5) * 0.7 * (1 - t * 0.5); p.setXYZ(k, x * f, y + (n - 0.5) * 40 * t, z * f);
        const snow = t > 0.72 + (n - 0.5) * 0.2 ? 1 : 0, c = snow ? [0.92, 0.94, 0.98] : [0.33 + 0.1 * n, 0.36 + 0.1 * n, 0.4 + 0.08 * n];
        colA.push(...c);
      }
      geo.setAttribute("color", new THREE.Float32BufferAttribute(colA, 3)); geo.computeVertexNormals();
      const m = new THREE.Mesh(geo, mm); m.position.set(Math.cos(a) * r, Hh / 2 - 30, Math.sin(a) * r - 40); add(m, false, false);
    }
  }

  // ---------------- sky: physical (Sky shader) or 3-stop atmospheric gradient; both blend to the fog colour at the horizon ----------------
  // procedural cloud layer (fbm on a sky plane, self-shadowed toward the sun, drifts with time) shared by both skies,
  // so reflections / IBL see the same clouds. cover 0..1, colours per preset (lighting.js cloud / cover).
  const CLOUD_GLSL = `
  uniform float cTime; uniform float cCover; uniform vec3 cLit; uniform vec3 cShade;
  float cH(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  float cN(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f); return mix(mix(cH(i), cH(i + vec2(1, 0)), f.x), mix(cH(i + vec2(0, 1)), cH(i + vec2(1, 1)), f.x), f.y); }
  float cF(vec2 p){ float s = 0.0, a = 0.5; for (int i = 0; i < 6; i++) { s += a * cN(p); p = p * 2.03 + vec2(1.7, 9.2); a *= 0.5; } return s; }
  vec3 clouds(vec3 col, vec3 dir, vec3 sd, vec3 sunC){
    if (dir.y <= 0.0 || cCover <= 0.0) return col;
    vec2 uv = dir.xz / (dir.y + 0.1) * 1.3 + vec2(cTime * 0.006, cTime * 0.002);
    float d = cF(uv), cov = smoothstep(1.0 - cCover, 1.0 - cCover + 0.3, d);
    float lt = cF(uv + normalize(sd.xz + 1e-4) * 0.06);
    float sh = clamp(0.62 + (d - lt) * 3.0, 0.2, 1.15);
    vec3 cc = mix(cShade, cLit, sh) + sunC * pow(max(dot(dir, sd), 0.0), 8.0) * 0.5 * (1.0 - cov * 0.5);
    return mix(col, cc, cov * smoothstep(0.0, 0.14, dir.y) * 0.96);
  }`;
  const cloudU = { cTime: { value: 0 }, cCover: { value: 0.4 }, cLit: { value: new THREE.Color(1, 1, 1) }, cShade: { value: new THREE.Color(0.6, 0.65, 0.75) } };
  const phys = new Sky(); phys.scale.setScalar(4500); phys.frustumCulled = false;
  const skyU = { fogCol: { value: new THREE.Color() }, skyK: { value: 1 } };
  phys.material.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, skyU, cloudU);
    sh.fragmentShader = sh.fragmentShader.replace("uniform vec3 up;", "uniform vec3 up; uniform vec3 fogCol; uniform float skyK;" + CLOUD_GLSL)
      .replace("gl_FragColor = vec4( retColor, 1.0 );", "retColor = min(pow(retColor, vec3(2.2)) * skyK, vec3(6.0)); retColor = clouds(retColor, direction, vSunDirection, vec3(1.0, 0.9, 0.75) * skyK * 0.25); retColor = mix(fogCol, retColor, smoothstep(-0.02, 0.2, direction.y)); gl_FragColor = vec4( retColor, 1.0 );");
  };
  phys.material.customProgramCacheKey = () => "physsky";
  const grad = new THREE.Mesh(new THREE.SphereGeometry(4000, 32, 16), new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, fog: false,
    uniforms: { top: { value: new THREE.Color() }, mid: { value: new THREE.Color() }, hor: { value: new THREE.Color() }, sunDir: { value: new THREE.Vector3() }, sunCol: { value: new THREE.Color() }, flash: { value: 0 }, discA: { value: 0.9993 }, discK: { value: 1.5 }, ...cloudU },
    vertexShader: "varying vec3 vD; void main(){ vD = normalize(position); vec4 p = projectionMatrix * modelViewMatrix * vec4(position,1.0); gl_Position = p.xyww; }",
    fragmentShader: `uniform vec3 top; uniform vec3 mid; uniform vec3 hor; uniform vec3 sunDir; uniform vec3 sunCol; uniform float flash; uniform float discA; uniform float discK; varying vec3 vD;` + CLOUD_GLSL + `
    void main(){ float h = clamp(vD.y, 0.0, 1.0); vec3 c = mix(mix(hor, mid, smoothstep(0.0, 0.22, h)), top, smoothstep(0.18, 0.85, h));
      float s = max(dot(normalize(vD), sunDir), 0.0); c += sunCol * (pow(s, 24.0) * 0.25 + pow(s, 400.0) * 0.4) + sunCol * smoothstep(discA, discA + (1.0 - discA) * 0.12, s) * discK; // sun / moon disc (blooms)
      c = clouds(c, normalize(vD), sunDir, sunCol);
      c += vec3(0.75, 0.8, 1.0) * flash * (0.4 + 0.6 * h); gl_FragColor = vec4(c, 1.0); }`,
  }));
  grad.frustumCulled = false;
  scene.add(phys, grad);
  const clouds = []; // painted billboard clouds replaced by the procedural layer above

  // ---------------- per-frame: wind, swaying trees, drifting clouds, cart pose + X-ray shell, van ----------------
  const update = (f, S, camera) => {
    const L = S.light, w = S.world || {};
    wind.time.value = f / 30; wind.amp.value = 1 + 1.6 * (L.rain || 0);
    for (const t of trees) { t.crown.rotation.z = 0.025 * wind.amp.value * Math.sin(f / 30 * 1.3 + t.seed); t.crown.rotation.x = 0.018 * wind.amp.value * Math.sin(f / 30 * 0.9 + t.seed * 2); }
    const cl = L.cloud || [1, 1, 1];
    cloudU.cTime.value = f / 30; cloudU.cCover.value = L.cover ?? 0.4;
    cloudU.cLit.value.setRGB(cl[0], cl[1], cl[2]).convertSRGBToLinear(); cloudU.cShade.value.copy(cloudU.cLit.value).multiplyScalar(0.5).lerp(new THREE.Color(L.mid).convertSRGBToLinear(), 0.35);
    lanternGlow.emissiveIntensity = (L.practical ? 14 : 0.2) * (1 + 0.06 * Math.sin(f * 1.7) + 0.04 * Math.sin(f * 4.3));
    // rocket cart
    const C = w.cart;
    cart.visible = !!C;
    if (C) {
      cart.position.set(...C.pos); cart.rotation.set(C.pitch || 0, C.yaw || 0, C.roll || 0, "YXZ");
      for (const wh of cart.userData.wheels) wh.rotation.x = C.wheel || 0;
      const op = C.shell ?? 1;
      for (const s of cart.userData.shell) { s.material.transparent = op < 1; s.material.opacity = op; s.material.depthWrite = op > 0.5; s.visible = op > 0.01; }
      cart.userData.inner.visible = op < 0.995 || !!C.showInner;
      cart.userData.fuseM.emissiveIntensity = (C.fuse || 0) * 6;
    }
    // van + headlights
    const V = w.van;
    if (V) { car.position.set(...V.pos); car.rotation.y = V.yaw; }
    car.userData.headM.emissiveIntensity = V && V.lights ? 30 * V.lights : 0;
  };
  const vanHeads = () => car.userData.heads.map((h) => new THREE.Vector3(...h).applyMatrix4(car.matrixWorld));
  const vanDir = () => new THREE.Vector3(0, -0.12, 1).applyQuaternion(car.quaternion).normalize();
  return { mats, walls, lanterns, cart, car, vanHeads, vanDir, sky: { phys, grad, skyU, cloudU }, update };
};
