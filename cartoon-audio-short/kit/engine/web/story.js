// Staging for the v2 demo "The Grocer's Rocket Cart" (62.0 s, 1860 frames @ 30 fps). Every value is a pure function of
// the frame number, and the file is Node-importable (audit.mjs reads it). Replace SHOTS for each new story; keep the
// helpers and the frameState contract:
//   frameState(f) -> { shot, beat, cam{pos,look,fov,roll,whip?,speed?}, light, actors[], fx[], emitters[], shock?, boom?,
//                      world{cart?, van?}, flash, vign, dof{focus,cInf}, shadow{c,r}, lightning, mb, events[] }
import { clamp, lin, smooth, smoother, easeOut, easeIn, back, lerp, lerp3, add3, camKeys, camWhipKeys, trackCam, alive, dampedShake, shockwave,
  shellOpacity, blinkAt, idle, q, comicAt, microMoves, FPS } from "./motion.js";
import { LP, lightSeq, sunDir, lightning } from "./lighting.js";
import { groundAt, polyAt } from "./terrain.js";
import { ROAD } from "./layout.js";
import { GROCER, MAYOR, TOWN_1, TOWN_2, TOWN_KID } from "./castdefs.js";

export { FPS };
export const TOTAL = 1860;
/** the 5-beat structure (seconds) checked by audit.mjs */
export const BEATS = [
  { id: "hook", a: 0, b: 4 }, { id: "reveal", a: 4, b: 15 }, { id: "escalation", a: 15, b: 38 }, { id: "mechanism", a: 38, b: 52 }, { id: "payoff", a: 52, b: 62 },
];
/** spoken-word anchors (frames) from work/words.json; the demo uses a planned read at ~3.2 words/s */
export const WORDS = { eighty: 12, festival: 140, mayor: 470, moustache: 598, rain: 652, slipped: 700, rolled: 760, van: 985, puddle: 1075, whatsInThere: 1168, fuse: 1290, bothWays: 1390, hill: 1565, match: 1648, lit: 1760, last: 1832 };

// ---------------- helpers ----------------
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const norm = (a) => { const l = Math.hypot(...a) || 1; return a.map((v) => v / l); };
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const dist = (a, b) => Math.hypot(...sub(a, b));
const camRight = (c) => norm(cross(sub(c.look, c.pos), [0, 1, 0]));
const camUp = (c) => norm(cross(camRight(c), sub(c.look, c.pos)));
/** canvas angle the key light comes FROM for a card seen by camera c (mirror flips x) */
const lightAng = (c, L, mirror = 1) => {
  const d = sunDir(L), r = camRight(c), u = camUp(c);
  const sx = (d[0] * r[0] + d[1] * r[1] + d[2] * r[2]) * mirror, sy = d[0] * u[0] + d[1] * u[1] + d[2] * u[2];
  return q(Math.atan2(-Math.max(0.25, sy), sx), 0.35);
};
const mirrorOf = (c, dir) => { const r = camRight(c); return dir[0] * r[0] + dir[1] * r[2] < 0 ? -1 : 1; };
const gp = (x, z, dy = 0) => [x, groundAt(x, z) + dy, z];
const road = (s, off = 0) => { const p = polyAt(ROAD, s); return { x: p.x - p.dz * off, z: p.z + p.dx * off, dx: p.dx, dz: p.dz }; };
/** cart pose on the road at arc length s (moving north = s increasing): local -z is its front */
const cartAt = (s, off = 0, extra = {}) => {
  const r = road(s, off), y = groundAt(r.x, r.z), y2 = groundAt(r.x + r.dx, r.z + r.dz);
  return { pos: [r.x, y, r.z], yaw: Math.atan2(-r.dx, -r.dz), pitch: -Math.atan2(y2 - y, 1) * 0.0 + Math.atan2(y2 - y, 1), wheel: -s / 0.62, shell: 1, fuse: 0, ...extra };
};
const walkPhase = (d) => q(d / 1.25, 1 / 24);
const sWalk = (s0, v, f0, f) => s0 + v * Math.max(0, f - f0) / FPS;
let CAM = null; // current camera (for light angles)
const side = (id, outfit, x, z, dir, opts, extra = {}) => ({ id, kind: "side", outfit, pos: [x, z], dir, opts: { seed: 3, light: CAM && extra.L ? lightAng(CAM, extra.L, mirrorOf(CAM, dir)) : -2.2, ...opts }, ...extra, L: undefined });
const front = (id, outfit, x, z, opts, extra = {}) => ({ id, kind: "front", outfit, pos: [x, z], opts: { seed: 7, light: -2.2, ...opts }, ...extra });

// ---------------- shots ----------------
const SHOTS = [];
const shot = (id, beat, a, b, fn) => SHOTS.push({ id, beat, a, b, fn });

// cart route for the first two beats (day): s grows at ~1.25 m/s
const S0 = 60, V0 = 1.25;
const dayCart = (f) => cartAt(sWalk(S0, V0, 0, f));
const dayCartPt = (g) => { const c = dayCart(g); return [c.pos[0], c.pos[1] + 0.9, c.pos[2]]; };

// 1 HOOK (0-4 s): mid-action, frame 0 = grocer shoving a cart of 82 rockets, test fuse fizzing. Prop tracking cam (lag 0.08).
shot("hook", "hook", 0, 120, (f) => {
  const L = LP.brightDay;
  const cam = trackCam(dayCartPt, f, -40, { offset: [6.8, 1.6, 1.6], lookUp: 0.75, lag: 0.08, lookAhead: -1.7, fov: 46 });
  CAM = cam;
  const C = dayCart(f), sG = sWalk(S0, V0, 0, f) - 1.95, g = road(sG);
  const actors = [side("grocer", GROCER, g.x, g.z, [g.dx, g.dz], { mode: "walk", phase: walkPhase(sG), push: true, lean0: 9, expr: f < 60 ? "stubborn" : "strain", blink: blinkAt(f, 3), comic: comicAt(f, [{ k: "sweat", f0: 30, f1: 120 }]) }, { L })];
  const fusePt = (gg) => { const c = dayCart(gg); return [c.pos[0] - 0.3 * Math.sin(c.yaw), c.pos[1] + 1.62, c.pos[2] - 0.9 * Math.cos(c.yaw)]; };
  return { cam, L, actors, micro: 0.6, world: { cart: C }, emitters: [{ id: "testfuse", kind: "sparks", f0: -20, f1: 120, at: fusePt, seed: 2, scale: 0.8 }],
    dof: { focus: dist(cam.pos, C.pos) + 0.4, cInf: 11 }, shadow: { c: C.pos, r: 10 }, events: [{ f: 12, kind: "word" }] };
});

// 2 REVEAL (4-15 s): one continuous crane: from the cart up and back over the village to the valley, festival hill and
// mountains in haze; the light warms toward golden (lighting shift = pattern interrupt).
shot("reveal", "reveal", 120, 450, (f) => {
  const track = trackCam(dayCartPt, 120, -40, { offset: [6.8, 1.6, 1.6], lookUp: 0.75, lag: 0.08, lookAhead: -1.7, fov: 46 });
  const C = dayCart(f);
  const base = camKeys([
    { f: 120, pos: track.pos, look: track.look, fov: 42 },
    { f: 150, pos: add3(C.pos, [3.6, 1.4, -4.6]), look: add3(dayCart(150).pos, [0, 1.1, 0]), fov: 42, ease: smooth },
    { f: 300, pos: [34, 46, 176], look: [14, 4, -100], fov: 46, ease: smoother, path: [[14, 9, 132], [26, 28, 168]] },
    { f: 380, pos: [30, 40, 150], look: [20, 8, -150], fov: 40, ease: smooth },
    { f: 410, pos: [28, 37, 138], look: [24, 10, -190], fov: 30, ease: smooth },
    { f: 450, pos: [27, 33, 126], look: [24, 10, -190], fov: 26, ease: smooth },
  ], f);
  const cam = alive(base, f, { seed: 2, amp: 1.4, push: 0 }); CAM = cam;
  const L = lightSeq([[120, "brightDay"], [330, "brightDay"], [450, "golden"]], f);
  const sG = sWalk(S0, V0, 0, f) - 1.95, g = road(sG);
  const actors = [side("grocer", GROCER, g.x, g.z, [g.dx, g.dz], { mode: "walk", phase: walkPhase(sG), push: true, lean0: 9, expr: "stubborn", blink: blinkAt(f, 3) }, { L })];
  const fx = [];
  for (let i = 0; i < 4; i++) { const t = (f - 120) / 330; fx.push({ id: "bird" + i, kind: "bird", pos: [-30 + t * 70 + i * 5, 26 + i * 3 + Math.sin(t * 6 + i) * 1.5, 40 - i * 6], size: 1.8, t: q((f * 0.09 + i * 0.3) % 1, 0.125) }); }
  const wide = smooth(lin(150, 300, f));
  return { cam, L, actors, fx, world: { cart: C }, dof: { focus: dist(cam.pos, C.pos), cInf: 9 * (1 - wide) }, shadow: { c: lerp3(C.pos, [10, 0, 40], wide), r: lerp(10, 120, wide) }, mb: 1.2 };
});

// 3 MOCKERY (15-21.3 s): village square; the mayor laughs, the town bets, a kid peeks over the barrels; rage eyes on "moustache"
const SQ = [2.9, 66.5];
shot("mock", "escalation", 450, 640, (f) => {
  const L = LP.golden;
  const two = { pos: [6.2, 1.75, 52.0], look: [-1.4, 1.35, 61.8], fov: 40 };
  const mcu = { pos: [5.0, 1.65, 58.4], look: [1.3, 1.55, 64.1], fov: 34 };
  const base = camWhipKeys([
    { f: 450, pos: [24, 22, 96], look: [2, 2, 60], fov: 44 },
    { f: 462, ...two, whip: 12, whipOpts: { arc: 0.08 } },
    { f: 560, pos: add3(two.pos, [-0.7, -0.05, 0.9]), look: two.look, fov: 36 },
    { f: 572, ...mcu, whip: 9 },
  ], f);
  const cam = alive(base, f, { seed: 3, push: 0.12, from: 462 }); CAM = cam;
  const C = cartAt(0, 0, { pos: gp(SQ[0], SQ[1]), yaw: 0, wheel: 0 });
  const laugh = f >= 478, bounce = (s) => (laugh ? q(4 * Math.sin((f - 478) * 1.05 + s), 1) : q(idle(f, s).tilt, 0.5));
  const bob = (s) => (laugh ? q(Math.abs(Math.sin((f - 478) * 0.52 + s)) * -6, 1) : 0);
  const actors = [
    front("mayor", MAYOR, -2.4, 60.2, { expr: f < 478 ? "smug" : f < 590 ? "laugh" : "mock", armL: "belly", armR: f >= 520 && f < 590 ? "point" : "belly", tilt: bounce(1), bob: bob(1), blink: blinkAt(f, 7), seed: 7, look: 0.5 }),
    side("grocer", GROCER, 1.3, 64.1, [0, -1], { mode: "stand", expr: f >= 590 ? "rage" : "stern", blink: blinkAt(f, 3), comic: comicAt(f, [{ k: "rage", f0: 590, f1: 640, ramp: 3 }, { k: "steam", f0: 600, f1: 640 }]) }, { L }),
    front("bet1", TOWN_1, -5.6, 57.4, { expr: laugh ? "grin" : "smile", armR: f > 500 ? "wave" : "hang", armL: "hip", tilt: bounce(2), bob: bob(2), blink: blinkAt(f, 9), seed: 9, look: -0.4 }),
    front("bet2", TOWN_2, -6.4, 66.2, { expr: laugh ? "laugh" : "smile", armR: "belly", tilt: bounce(3), bob: bob(3), blink: blinkAt(f, 11), seed: 11 }),
    front("kid", TOWN_KID, -8.2, 52.8, { expr: f > 540 ? "grin" : "shock", armL: "up", armR: "up", blink: blinkAt(f, 13), seed: 13 }, { lift: lerp(-0.55, -0.25, smooth(lin(520, 545, f))) }),
  ];
  const fx = f >= 600 && f < 612 ? [{ id: "rbur", kind: "burst", pos: [1.6, 2.4, 64.0], size: 0.9, t: q((f - 599) / 12, 0.09), col: "#ff4a2a" }] : [];
  return { cam, L, actors, fx, world: { cart: C }, dof: { focus: dist(cam.pos, f < 566 ? [-0.6, 1.4, 61.4] : [1.3, 1.7, 64.1]), cInf: 10 }, shadow: { c: [0, 0, 61], r: 12 } };
});

// 4 RAIN + SLIP (21.3-25.3 s): time jump to night rain (hard cut + 6-frame flash). He pushes past the lanterns and slips.
const RS = 92; // arc length of the slip
shot("slip", "escalation", 640, 760, (f) => {
  const L = lightSeq([[640, "nightRain"]], f);
  const sC = RS + 2 + 1.6 * clamp((f - 640) / FPS, 0, 2) + (f > 700 ? 0.9 * (f - 700) / FPS * ((f - 700) / 60) : 0);
  const C = cartAt(sC, 0.4);
  const sG = Math.min(sC - 1.95, RS + 2 + 1.6 * 2 - 1.95 + 0.3), g = road(sG, 0.4);
  const cam0 = { pos: add3(gp(g.x, g.z), [-5.6, 1.35, 2.6]), look: add3(gp(g.x, g.z), [0.2, 1.0, -0.9]), fov: 40 };
  const cam = alive(cam0, f, { seed: 4, push: 0.2, from: 640 }); CAM = cam;
  const fall = easeIn(lin(700, 711, f));
  const actors = [side("grocer", GROCER, g.x, g.z, [g.dx, g.dz], { mode: f < 700 ? "walk" : "stand", phase: walkPhase(sG), push: f < 700, lean0: 8, expr: f < 700 ? "stubborn" : "whiteout", blink: blinkAt(f, 3),
    comic: comicAt(f, [{ k: "whiteout", f0: 700, f1: 760, ramp: 2 }, { k: "lines", f0: 700, f1: 722, ramp: 2 }]) }, { L, roll: -82 * fall * mirrorOf(cam, [g.dx, g.dz]), lift: 0.14 * fall + (f >= 711 ? 0.06 * Math.exp(-(f - 711) / 3) * Math.sin((f - 711) * 1.8) : 0) })];
  const flash = f < 646 ? [0.6, 0.4, 0.22, 0.1, 0.04, 0.01][f - 640] : 0;
  const emitters = f >= 711 ? [{ id: "splash1", kind: "debris", f0: 711, at: () => gp(g.x, g.z, 0.1), seed: 5, scale: 0.6, col: [[0.75, 0.82, 0.9], [0.5, 0.58, 0.68]] }] : [];
  return { cam, L, actors, world: { cart: C }, emitters, flash, cut: f === 640, kicks: [{ f: 711, a: 0.022 }], shockAt: { f: 711, pos: gp(g.x, g.z), maxR: 2.2, dur: 12 },
    dof: { focus: dist(cam.pos, gp(g.x, g.z, 1)), cInf: 9 }, shadow: { c: gp(g.x, g.z), r: 10 } };
});

// 5 RUNAWAY (25.3-32 s): the cart rolls off down Main Street; vehicle-tracking camera (lag 0.08) + motion blur; he chases.
const rollS = (f) => { const t = Math.max(0, (f - 700) / FPS); return RS + 2 + 3.2 + 0.9 * t * t / 2 * 1.6 + Math.max(0, t - 2.5) * 2.2; };
shot("runaway", "escalation", 760, 960, (f) => {
  const L = LP.nightRain;
  const C = cartAt(rollS(f), 0.4 + 0.8 * Math.sin((f - 760) / 40));
  C.yaw += 0.12 * Math.sin((f - 760) / 13);
  const pt = (g) => { const c = cartAt(rollS(g), 0.4 + 0.8 * Math.sin((g - 760) / 40)); return [c.pos[0], c.pos[1] + 0.9, c.pos[2]]; };
  const tc = trackCam(pt, f, 720, { offset: [-3.6, 1.4, 4.2], lookUp: 0.3, lag: 0.08, lookAhead: 2.5, fov: 44 });
  const cam = alive(tc, f, { seed: 5, amp: 2.2, push: 0 }); CAM = cam;
  const sG = rollS(f) - lerp(4, 9, smooth(lin(760, 960, f))), g = road(sG, -0.6);
  const actors = [side("grocer", GROCER, g.x, g.z, [g.dx, g.dz], { mode: "walk", phase: walkPhase(sG * 0.8), stride: 1.3, armsUp: true, lean0: 12, expr: f >= 878 && f < 900 ? "whiteout" : "shock", blink: blinkAt(f, 3), comic: comicAt(f, [{ k: "sweat", f0: 760, f1: 878 }, { k: "lines", f0: 878, f1: 900 }, { k: "sweat", f0: 900, f1: 960 }]) }, { L })];
  const emitters = f >= 878 ? [{ id: "pothole", kind: "debris", f0: 878, at: () => [C.pos[0], C.pos[1] + 0.2, C.pos[2]], seed: 6, scale: 0.7, col: [[0.7, 0.76, 0.85], [0.4, 0.45, 0.55]] }] : [];
  if (f >= 878 && f < 884) C.pitch = 0.12 * Math.sin((f - 878) * 1.2);
  return { cam, L, actors, world: { cart: C }, emitters, micro: 0, kicks: [{ f: 878, a: 0.02 }], dof: { focus: dist(cam.pos, C.pos), cInf: 6 }, shadow: { c: C.pos, r: 14 }, mb: 1.4 };
});

// 6 VAN (32-38 s): stormy road, a van's headlights, brakes; the cart swerves into the fence; he dives into a puddle.
const STOP = [7.6, -22];
shot("van", "escalation", 960, 1140, (f) => {
  const L = LP.stormyRoad;
  const vz = lerp(-78, -31, easeOut(lin(960, 1046, f))), vx = lerp(9.5, 5.4, lin(960, 1046, f));
  const van = { pos: gp(vx, vz), yaw: Math.atan2(5.4 - 9.5, 47) - (f > 1030 && f < 1052 ? 0.05 * Math.sin((f - 1030) * 0.9) : 0), lights: 1 };
  const cs = rollS(Math.min(f, 1000)), c0 = cartAt(cs, 0.6), k = smoother(lin(1000, 1050, f));
  const C = { ...c0, pos: lerp3(c0.pos, gp(STOP[0], STOP[1]), k), yaw: c0.yaw + 0.9 * k, wheel: c0.wheel - k * 9 };
  const base = camWhipKeys([
    { f: 960, pos: add3(C.pos, [-3.4, 1.5, 5]), look: add3(C.pos, [1, 0.9, -6]), fov: 44 },
    { f: 1010, pos: [-1.5, 1.9, -6], look: [6.5, 1.0, -30], fov: 40, whip: 10 },
    { f: 1062, pos: [-0.8, 1.6, -11], look: [6.6, 0.8, -24], fov: 36, whip: 8 },
  ], f);
  const cam = alive(base, f, { seed: 6, amp: 1.8, push: 0.15, from: 1062 }); CAM = cam;
  const dive = smoother(lin(1060, 1076, f)), gx = lerp(3.4, 5.8, dive), gz = lerp(-9 - 6 * lin(960, 1060, f), -21, dive);
  const actors = [side("grocer", GROCER, gx, gz, [0.15, -1], { mode: f < 1060 ? "walk" : "stand", phase: walkPhase(-gz), armsUp: true, stride: 1.2, lean0: 10, expr: f < 1076 ? "shock" : "whiteout", blink: blinkAt(f, 3),
    comic: comicAt(f, [{ k: "lines", f0: 1076, f1: 1096 }, { k: "whiteout", f0: 1076, f1: 1140 }]) }, { L, roll: -75 * dive * mirrorOf(cam, [0.15, -1]), lift: 0.6 * Math.sin(dive * Math.PI) + 0.14 * dive })];
  const emitters = f >= 1076 ? [{ id: "puddle", kind: "debris", f0: 1076, at: () => gp(5.8, -21, 0.1), seed: 8, scale: 0.9, col: [[0.8, 0.86, 0.94], [0.45, 0.52, 0.62]] }] : [];
  return { cam, L, actors, world: { cart: C, van }, emitters, kicks: [{ f: 1046, a: 0.02 }, { f: 1076, a: 0.025 }], shockAt: { f: 1076, pos: gp(5.8, -21), maxR: 3.5, dur: 14 }, strikes: [990, 1101],
    dof: { focus: dist(cam.pos, C.pos), cInf: 7 }, shadow: { c: [6, 0, -24], r: 18 }, mb: 1.2 };
});

// 7 MECHANISM (38-52 s): "So what's in there?" push in, the cart's outer shell fades 1 -> 0 over 10 frames (X-ray), orbit;
// 82 rockets on one ring fuse; the flame runs both ways, so every rocket leaves at once. Shell returns at the end.
shot("xray", "mechanism", 1140, 1560, (f) => {
  const L = lightSeq([[1140, "nightRain"], [1185, "moonCamp"]], f); // the rain breaks: clear moonlit night for the X-ray
  const C0 = cartAt(0, 0, { pos: gp(STOP[0], STOP[1]), yaw: cartAt(rollS(1000), 0.6).yaw + 0.9, wheel: 0 });
  const ctr = add3(C0.pos, [0, 1.05, 0]);
  const orb = (f - 1190) / 330 * 1.7 * Math.PI;
  const R = [[1140, 5.6], [1200, 4.0], [1262, 4.0], [1290, 3.0], [1330, 3.0], [1360, 4.4], [1420, 4.4], [1450, 3.0], [1480, 3.0], [1510, 4.3]].reduce((v, [g, r], i, A) => (i && f > A[i - 1][0] ? (f >= g ? r : lerp(A[i - 1][1], r, smooth(lin(A[i - 1][0], g, f)))) : v), 5.6);
  const ang = 0.6 + (f > 1190 ? orb : 0);
  const base = { pos: add3(ctr, [Math.cos(ang) * R, lerp(1.4, 2.1, smooth(lin(1140, 1200, f))), Math.sin(ang) * R]), look: ctr, fov: lerp(40, 36, smooth(lin(1140, 1200, f))) };
  const cam = alive(base, f, { seed: 7, push: 0 }); CAM = cam;
  const shell = shellOpacity(f, 1185, 10, 1530);
  const fuseT = clamp((f - WORDS.fuse) / 100), C = { ...C0, shell, fuse: f >= WORDS.fuse ? 0.4 + 0.6 * Math.abs(Math.sin(f * 0.4)) * 0.5 : 0, showInner: shell < 1 };
  // two sparks running around the ring fuse in opposite directions from the lit point
  const ring = (a) => { const cy = Math.cos(C.yaw), sy = Math.sin(C.yaw), lx = 0.5 * Math.cos(a), lz = 0.875 * Math.sin(a); return [C.pos[0] + lx * cy + lz * sy, C.pos[1] + 0.88, C.pos[2] - lx * sy + lz * cy]; };
  const emitters = f >= WORDS.fuse && f < 1530 ? [
    { id: "fuseA", kind: "sparks", f0: WORDS.fuse, f1: 1530, at: (g) => ring(Math.PI / 2 + Math.PI * clamp((g - WORDS.fuse) / 100)), seed: 3, scale: 0.6, rate: 90 },
    { id: "fuseB", kind: "sparks", f0: WORDS.fuse, f1: 1530, at: (g) => ring(Math.PI / 2 - Math.PI * clamp((g - WORDS.fuse) / 100)), seed: 4, scale: 0.6, rate: 90 },
  ] : [];
  void fuseT;
  const gx = STOP[0] - 2.1, gz = STOP[1] + 0.6;
  const actors = [side("grocer", GROCER, gx, gz, [1, 0], { mode: "stand", expr: f < 1300 ? "worried" : "grin", blink: blinkAt(f, 3), comic: comicAt(f, [{ k: "sweat", f0: 1140, f1: 1290 }, { k: "lines", f0: 1390, f1: 1410 }, { k: "sweat", f0: 1470, f1: 1560 }]) }, { L })];
  return { cam, L, actors, world: { cart: C }, emitters, dof: { focus: dist(cam.pos, ctr), cInf: 10 }, shadow: { c: C.pos, r: 8 }, mb: 0.8,
    events: [{ f: 1185, kind: "cutaway" }, { f: WORDS.fuse, kind: "prop" }, { f: 1390, kind: "prop" }] };
});

// 8 HILL (52-56.7 s): storm on the festival hill; the mayor laughs under the lightning; one match.
const TOP = [29.4, -211.5];
shot("hill", "payoff", 1560, 1700, (f) => {
  const L = LP.stormyRoad;
  const C = cartAt(0, 0, { pos: gp(TOP[0], TOP[1]), yaw: 0.4, wheel: 0, fuse: f > WORDS.match + 6 ? 1 : 0 });
  const wide = { pos: gp(TOP[0] - 6.8, TOP[1] + 7.5, 2.6), look: gp(TOP[0] + 1, TOP[1] - 1, 1.2), fov: 40 };
  const mcu = { pos: gp(TOP[0] - 4.6, TOP[1] + 4.2, 1.9), look: gp(TOP[0] - 0.6, TOP[1] + 0.4, 1.3), fov: 34 };
  const base = camWhipKeys([{ f: 1560, ...wide }, { f: 1610, pos: add3(wide.pos, [1.4, -0.3, -1.6]), look: wide.look, fov: 38 }, { f: 1640, ...mcu, whip: 8 }], f);
  const cam = alive(base, f, { seed: 8, amp: 1.6, push: 0.1, from: 1640 }); CAM = cam;
  const gx = TOP[0] - 1.2, gz = TOP[1] + 1.0;
  const actors = [
    side("grocer", GROCER, gx, gz, [0.7, -0.7], { mode: "stand", expr: f < WORDS.match ? "stubborn" : "grin", blink: blinkAt(f, 3) }, { L }),
    front("mayor", MAYOR, TOP[0] + 3.2, TOP[1] + 2.4, { expr: "laugh", armL: "belly", armR: "belly", tilt: q(4 * Math.sin(f * 1.05), 1), bob: q(Math.abs(Math.sin(f * 0.52)) * -6, 1), blink: blinkAt(f, 7), seed: 7 }),
    front("bet1", TOWN_1, TOP[0] + 6.5, TOP[1] - 3.5, { expr: "grin", armR: "wave", blink: blinkAt(f, 9), seed: 9 }),
  ];
  const emitters = f >= WORDS.match ? [{ id: "match", kind: "sparks", f0: WORDS.match, f1: WORDS.match + 14, at: () => gp(gx + 0.55, gz - 0.4, 1.25), seed: 9, scale: 0.7 }] : [];
  return { cam, L, actors, world: { cart: C }, emitters, strikes: [1585, 1668], dof: { focus: dist(cam.pos, gp(gx, gz, 1.4)), cInf: f > 1636 ? 12 : 6 }, shadow: { c: gp(TOP[0], TOP[1]), r: 12 } };
});

// 9 PAYOFF (56.7-62 s): 82 rockets leave at once; crane up to the whole valley; the biggest burst lands on the last word
shot("payoff", "payoff", 1700, 1860, (f) => {
  const L = lightSeq([[1700, "stormyRoad"], [1760, { ...LP.stormyRoad, expo: 1.15 }]], f);
  const C = cartAt(0, 0, { pos: gp(TOP[0], TOP[1]), yaw: 0.4, wheel: 0, fuse: 1, shell: 1 });
  const base = camKeys([
    { f: 1700, pos: gp(TOP[0] - 3.2, TOP[1] + 8.4, 1.6), look: add3(gp(TOP[0], TOP[1]), [0.6, 2.2, -2]), fov: 46 },
    { f: 1722, pos: gp(TOP[0] - 3.3, TOP[1] + 8.6, 1.6), look: add3(gp(TOP[0], TOP[1]), [0.4, 6, -8]), fov: 50, ease: smooth },
    { f: 1760, pos: gp(TOP[0] - 3.5, TOP[1] + 9, 1.7), look: add3(gp(TOP[0], TOP[1]), [0, 24, -60]), fov: 58, ease: smoother },
    { f: 1860, pos: gp(TOP[0] - 4.5, TOP[1] + 11.5, 1.8), look: add3(gp(TOP[0], TOP[1]), [0, 27, -64]), fov: 60, ease: (t) => smooth(t) },
  ], f);
  const cam = alive(base, f, { seed: 9, amp: 1.5, push: 0 }); CAM = cam;
  const L0 = 1718, emitters = [];
  // rocket trails: 8 visible streams (sparks emitters rising with the rockets)
  for (let i = 0; i < 8; i++) {
    const a = i * 0.8, rise = (g) => { const t = Math.max(0, (g - L0 - i) / FPS); return add3(C.pos, [Math.cos(a) * (0.4 + 4 * t), 1.4 + 38 * t - 2 * t * t, Math.sin(a) * (0.4 + 3 * t)]); };
    if (f >= L0 + i) emitters.push({ id: "trail" + i, kind: "sparks", f0: L0 + i, f1: L0 + i + 40, at: rise, seed: 20 + i, scale: 1.2, rate: 120, dir: [0, -0.6, 0] });
  }
  const bursts = [[1758, [-22, 34, -70], [[1, 0.9, 0.5], [1, 0.3, 0.2]]], [1772, [20, 40, -82], [[0.6, 0.9, 1], [0.2, 0.4, 1]]], [1788, [-6, 46, -95], [[1, 0.6, 1], [0.8, 0.2, 0.9]]], [1802, [26, 30, -66], [[0.8, 1, 0.6], [0.3, 0.9, 0.2]]]];
  for (const [fb, o, col] of bursts) if (f >= fb) emitters.push({ id: "fw" + fb, kind: "firework", f0: fb, at: () => add3(C.pos, o), seed: fb, scale: 2.6, col });
  if (f >= WORDS.last) emitters.push({ id: "big", kind: "explosion", f0: WORDS.last, at: () => add3(C.pos, [0, 40, -80]), seed: 99, scale: 3, count: 1.2 }, { id: "bigfw", kind: "firework", f0: WORDS.last + 2, at: () => add3(C.pos, [0, 40, -80]), seed: 98, scale: 4, count: 1.5, col: [[1, 1, 0.85], [1, 0.55, 0.15]] });
  if (f >= L0) emitters.push({ id: "launchsmoke", kind: "smoke", f0: L0, f1: 1860, at: () => add3(C.pos, [0, 0.8, 0]), seed: 31, scale: 1.0, rate: 10 });
  const boomK = f >= WORDS.last ? Math.exp(-(f - WORDS.last) / 9) : f >= 1758 ? 0.25 * Math.exp(-((f - 1758) % 14) / 5) : 0;
  const mayorGone = f >= WORDS.last + 2;
  const actors = [
    front("mayor", { ...MAYOR, moustache: mayorGone ? null : MAYOR.moustache }, TOP[0] + 3.2, TOP[1] + 2.4, { expr: f < L0 ? "laugh" : "whiteout", armL: f < L0 ? "belly" : "up", armR: f < L0 ? "belly" : "up", blink: blinkAt(f, 7), seed: 7,
      comic: comicAt(f, [{ k: "whiteout", f0: L0, f1: 1860, ramp: 2 }, { k: "lines", f0: WORDS.last, f1: 1860, ramp: 2 }, { k: "steam", f0: WORDS.last + 2, f1: 1860 }]) }, { outfitKey: mayorGone ? "bald" : "" }),
    side("grocer", GROCER, TOP[0] - 1.2, TOP[1] + 1.0, [0.7, -0.7], { mode: "stand", armsUp: f >= 1730, expr: f >= 1730 ? "relief_open" : "shock", blink: blinkAt(f, 3) }, { L }),
  ];
  return { cam, L, actors, micro: 0, world: { cart: { ...C, fuse: f < L0 ? 1 : 0 } }, emitters, boom: boomK > 0.01 ? { pos: add3(C.pos, [0, 36, -70]), k: boomK } : null,
    flash: f >= WORDS.last && f < WORDS.last + 4 ? [0.45, 0.25, 0.1, 0.03][f - WORDS.last] : 0,
    kicks: [{ f: L0, a: 0.025 }, { f: WORDS.last, a: 0.03 }], shockAt: { f: L0, pos: C.pos, maxR: 9, dur: 16 }, strikes: [1745],
    dof: { focus: 40, cInf: 0 }, shadow: { c: C.pos, r: 30 }, mb: 0.7, events: [{ f: WORDS.last, kind: "climax" }] };
});

export const SHOTLIST = SHOTS.map((s) => ({ id: s.id, beat: s.beat, a: s.a, b: s.b }));
export const shotAt = (f) => SHOTS.find((s) => f >= s.a && f < s.b) || SHOTS[SHOTS.length - 1];

export const frameState = (f) => {
  const s = shotAt(f), r = s.fn(f);
  // reference grammar: a 6-8 frame camera accent (dolly / orbit / crane) every ~21 frames on top of every shot's move
  // (r.micro = 0 to switch off, e.g. on tracking shots; pass r.beats = word frames to land accents on words)
  const mc = microMoves(r.cam, f, { f0: s.a, amp: r.micro ?? 1, seed: SHOTS.indexOf(s) + 1, beats: r.beats || null });
  const cam = { ...mc, pos: [...mc.pos], look: [...mc.look], roll: mc.roll || 0 };
  // 7-frame damped shake on heavy impacts (offsets the aim point; roll jolt)
  const [kx, ky, kr] = dampedShake(f, r.kicks || []);
  if (kx || ky) {
    const d = dist(cam.pos, cam.look), R = camRight(cam), U = camUp(cam);
    cam.look = add3(cam.look, [R[0] * kx * d + U[0] * ky * d, R[1] * kx * d + U[1] * ky * d, R[2] * kx * d + U[2] * ky * d]);
    cam.roll += kr;
  }
  // camera never under the terrain
  cam.pos[1] = Math.max(cam.pos[1], groundAt(cam.pos[0], cam.pos[2]) + 0.6);
  const sh = r.shockAt ? shockwave(f, r.shockAt.f, r.shockAt) : null;
  const L = r.L;
  return {
    shot: s.id, beat: s.beat, cam, light: L, actors: (r.actors || []).map((a) => { const { L: _, ...rest } = a; return rest; }), fx: r.fx || [], emitters: r.emitters || [],
    shock: sh ? { ...sh, pos: r.shockAt.pos } : null, boom: r.boom || null, world: { cart: null, van: null, ...(r.world || {}) },
    flash: Math.max(r.flash || 0, 0.35 * lightning(f, r.strikes || [])), lightning: L.lightning ? lightning(f, r.strikes || []) : 0,
    vign: r.vign ?? 0.2, dof: r.dof, shadow: r.shadow, mb: r.mb ?? 1, cut: !!r.cut, kicks: r.kicks || [], events: r.events || [],
  };
};
