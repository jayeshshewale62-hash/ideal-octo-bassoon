// Pre-render retention audit (runs story.js in Node, no browser):  node audit.mjs [web/story.js] [--stills] [--strict]
// Checks the 30 fps vertical-short spec before any frame is rendered:
//  - runtime 1750-1950 frames (58-65 s); 5-beat structure (hook from frame 0, reveal, escalation, mechanism with a
//    cutaway/X-ray or POV inside 38-52 s, payoff with the climax on the last word)
//  - no camera static for 4+ frames (position, aim and fov all frozen)
//  - pattern interrupt every 60-90 frames: camera scale change (>= 12 % framing), whip-glide, lighting shift, comic
//    overlay onset, impact (kick / shockwave / flash), new particle emitter, or a shot change
//  - retention: any 90-frame (3 s) stretch inside a shot with no camera move, prop interaction or expression change
//  - --stills prints the frames to render for the contact sheet (shot middles, transitions, impacts, overlays)
import path from "node:path";
import { pathToFileURL } from "node:url";

const args = process.argv.slice(2);
const storyPath = path.resolve(args.find((a) => !a.startsWith("--")) || "web/story.js");
const S = await import(pathToFileURL(storyPath).href);
const N = S.TOTAL, FPS = 30, issues = [], warns = [];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]], len = (a) => Math.hypot(...a);
const st = Array.from({ length: N }, (_, f) => S.frameState(f));

// runtime
if (N < 1750 || N > 1950) issues.push(`runtime ${N} frames = ${(N / FPS).toFixed(2)} s (spec 1750-1950 frames / 58-65 s)`);
// beats
const beatsSeen = {};
st.forEach((s, f) => { (beatsSeen[s.beat] ||= [f, f])[1] = f; });
for (const b of ["hook", "reveal", "escalation", "mechanism", "payoff"]) if (!beatsSeen[b]) issues.push(`beat missing: ${b}`);
if (beatsSeen.hook && beatsSeen.hook[0] !== 0) issues.push("hook must start at frame 0 (mid-action)");
const winOK = (b, a0, a1) => { const r = beatsSeen[b]; if (r && (Math.abs(r[0] / FPS - a0) > 1.5 || Math.abs((r[1] + 1) / FPS - a1) > 2)) warns.push(`beat ${b} spans ${(r[0] / FPS).toFixed(1)}-${((r[1] + 1) / FPS).toFixed(1)} s (spec ${a0}-${a1} s)`); };
winOK("hook", 0, 4); winOK("reveal", 4, 15); winOK("escalation", 15, 38); winOK("mechanism", 38, 52);
const cutaway = st.findIndex((s) => (s.events || []).some((e) => e.kind === "cutaway") || Object.values(s.world || {}).some((w) => w && w.shell != null && w.shell < 0.99) || s.pov);
if (cutaway < 0) issues.push("no cutaway / X-ray (shell opacity < 1) or POV in the mechanism beat");
else if (cutaway / FPS < 37 || cutaway / FPS > 52) warns.push(`cutaway starts at ${(cutaway / FPS).toFixed(1)} s (spec 38-52 s)`);
else {
  const f0 = st.findIndex((s) => Object.values(s.world || {}).some((w) => w && w.shell != null && w.shell < 0.99));
  if (f0 >= 0) { const f1 = st.findIndex((s, f) => f > f0 && Object.values(s.world || {}).some((w) => w && w.shell != null && w.shell <= 0.01)); if (f1 > 0 && Math.abs(f1 - f0 - 9) > 3) warns.push(`shell fade takes ${f1 - f0 + 1} frames (spec 10)`); }
}
const climax = st.flatMap((s) => (s.events || []).filter((e) => e.kind === "climax").map((e) => e.f));
const lastWord = S.WORDS ? Math.max(...Object.values(S.WORDS)) : null;
if (!climax.length) warns.push("no climax event marked in the payoff (events: [{f, kind: 'climax'}])");
else if (lastWord != null && Math.abs(Math.max(...climax) - lastWord) > 3) warns.push(`climax f${Math.max(...climax)} is not on the last word (f${lastWord})`);
if (N - Math.max(...climax, 0) > 45) warns.push(`${N - Math.max(...climax, 0)} frames after the climax: no slow outro`);

// static camera
let run = 0, runStart = 0;
for (let f = 1; f < N; f++) {
  const a = st[f - 1].cam, b = st[f].cam, d = len(sub(a.pos, b.pos)) + len(sub(a.look, b.look)) * 0.25 + Math.abs(a.fov - b.fov) * 0.01 + Math.abs((a.roll || 0) - (b.roll || 0)) * 0.01;
  if (d < 1e-4 && st[f].shot === st[f - 1].shot) { if (!run) runStart = f - 1; run++; } else { if (run >= 3) issues.push(`camera static f${runStart}-f${runStart + run} (${run + 1} frames): add push-in / orbit / alive()`); run = 0; }
}
if (run >= 3) issues.push(`camera static f${runStart}-end`);

// pattern interrupts
const frameSize = (c) => len(sub(c.pos, c.look)) * Math.tan((c.fov * Math.PI) / 360);
const ev = [];
let refSize = frameSize(st[0].cam), lightKey = "", lightStable = 0;
const prevComic = new Map(), emitSeen = new Set();
st.forEach((s, f) => {
  const why = [];
  if (f && s.shot !== st[f - 1].shot) why.push("shot");
  const z = frameSize(s.cam); if (Math.abs(Math.log(z / refSize)) > 0.12) { why.push("scale"); refSize = z; }
  if ((s.cam.whip || 0) > 0.5 && !((st[f - 1] || s).cam.whip > 0.5)) why.push("whip");
  const lk = [s.light.top, s.light.hor, (s.light.sunK || 0).toFixed(2), s.light.rain || 0].join();
  if (lk !== lightKey) { if (lightStable >= 10 && f) why.push("light"); lightStable = 0; lightKey = lk; } else lightStable++;
  for (const a of s.actors) { const c = !!a.opts.comic; if (c && !prevComic.get(a.id)) why.push("overlay:" + a.id); prevComic.set(a.id, c); }
  if ((s.kicks || []).some((k) => k.f === f) || (s.shock && s.shock.radius < 1.5) || (s.flash > 0.2 && !(st[f - 1] && st[f - 1].flash > 0.2))) why.push("impact");
  for (const e of s.emitters) if (!emitSeen.has(e.id)) { emitSeen.add(e.id); why.push("fx:" + e.id); }
  for (const e of s.events || []) if (e.f === f) why.push(e.kind);
  if (why.length) ev.push([f, why]);
});
for (let i = 0; i <= ev.length; i++) {
  const a = i ? ev[i - 1][0] : 0, b = i < ev.length ? ev[i][0] : N;
  if (b - a > 90) issues.push(`no pattern interrupt for ${b - a} frames (f${a}-f${b}, ${((b - a) / FPS).toFixed(1)} s): add a scale change, whip, light shift or overlay every 60-90 frames`);
}
// 3-second retention audit inside shots
for (const sh of S.SHOTLIST) for (let f0 = sh.a; f0 + 90 <= sh.b; f0 += 15) {
  const A = st[f0], B = st[f0 + 90];
  const camMove = len(sub(A.cam.pos, B.cam.pos)) > 0.25 || Math.abs(A.cam.fov - B.cam.fov) > 2 || len(sub(A.cam.look, B.cam.look)) > 0.4;
  let expr = false, prop = false;
  for (let f = f0 + 1; f <= f0 + 90; f++) {
    const p = st[f - 1], s = st[f];
    if (s.actors.some((a) => { const q = p.actors.find((x) => x.id === a.id); return q && (q.opts.expr !== a.opts.expr || JSON.stringify(q.opts.comic) !== JSON.stringify(a.opts.comic) || q.opts.armR !== a.opts.armR); })) expr = true;
    if (s.emitters.length || s.fx.length || JSON.stringify(s.world) !== JSON.stringify(p.world)) prop = true;
  }
  if (!camMove && !expr && !prop) { issues.push(`shot ${sh.id} f${f0}-f${f0 + 90}: 3 s with no camera move, prop interaction or expression change`); break; }
}
// camera accent cadence (reference: a new 6-8 f move accent every ~21 frames; whole-set travel, not pan-in-place)
const camSpd = st.map((s, f) => (f ? len(sub(s.cam.pos, st[f - 1].cam.pos)) + 0.2 * len(sub(s.cam.look, st[f - 1].cam.look)) : 0));
const sm = camSpd.map((_, f) => camSpd.slice(Math.max(0, f - 2), f + 3).reduce((x, y) => x + y, 0) / 5);
const acc = []; for (let f = 2; f < N - 2; f++) if (sm[f] > sm[f - 1] && sm[f] >= sm[f + 1] && sm[f] > 1.3 * Math.min(...sm.slice(Math.max(0, f - 10), f))) acc.push(f);
const accGap = acc.length > 1 ? acc.slice(1).map((x, i) => x - acc[i]).sort((x, y) => x - y)[Math.floor((acc.length - 1) / 2)] : N;
if (accGap > 45) warns.push(`camera accents every ${accGap} frames (reference ~21): add microMoves / beat accents`);
// micro-gags (info)
const gagShots = S.SHOTLIST.filter((sh) => ["escalation", "payoff"].includes(sh.beat) && st[Math.floor((sh.a + sh.b) / 2)].actors.length >= 3).map((sh) => sh.id);

console.log(`story: ${path.relative(process.cwd(), storyPath)}  ${N} frames = ${(N / FPS).toFixed(2)} s @ 30 fps, ${S.SHOTLIST.length} shots`);
console.log("beats:", Object.entries(beatsSeen).map(([b, r]) => `${b} ${(r[0] / FPS).toFixed(1)}-${((r[1] + 1) / FPS).toFixed(1)}s`).join(" | "));
console.log(`camera accents: ${acc.length} (median gap ${accGap} f, reference ~21 f)`);
console.log(`pattern interrupts: ${ev.length} (median gap ${ev.length > 1 ? ev.slice(1).map((e, i) => e[0] - ev[i][0]).sort((a, b) => a - b)[Math.floor((ev.length - 1) / 2)] : "-"} frames); background-gag shots: ${gagShots.join(", ") || "none"}`);
for (const w of warns) console.log("WARN ", w);
for (const e of issues) console.log("FLAG ", e);
if (args.includes("--stills")) {
  const fr = new Set();
  for (const sh of S.SHOTLIST) { fr.add(sh.a + 3); fr.add(Math.floor((sh.a + sh.b) / 2)); }
  for (const [f, why] of ev) if (why.some((w) => /impact|whip|overlay|cutaway|climax/.test(w))) fr.add(Math.min(N - 1, f + 2));
  console.log("STILLS " + [...fr].filter((f) => f < N).sort((a, b) => a - b).join(","));
}
console.log(issues.length ? `${issues.length} flag(s)` : "audit OK");
process.exit(args.includes("--strict") && issues.length ? 1 : 0);
