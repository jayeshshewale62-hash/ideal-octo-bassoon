# cartoon-audio-short kit (v2)
Engine + tools for the cartoon-audio-short skill: 58-65 s, 1080x1920, 30 fps vertical shorts with 2D ink characters in a
realistic PBR 3D world. Demo story: "The Grocer's Rocket Cart" (62 s, 9 shots, all 5 beats, 3 lighting presets, X-ray cutaway).
- `tools/setup.sh ~/shorts/<slug>`: copy the engine, install three.js r160, build `web/toon.js`, link Playwright, syntax-check.
- `engine/web/`: `main.js` (renderer, lit + shadowed cards with depth pull, lantern/headlight pools, sky IBL, grade, motion blur, DOF),
  `world.js` (PBR terrain, roads, houses, trees, instanced wind grass, props, mountains, sky), `pbr.js` (procedural albedo/normal/roughness
  painters), `terrain.js`, `layout.js`, `lighting.js` (crispDay, nightRain, stormyRoad, golden, memory), `vfx.js` (sparks, debris, sawdust,
  smoke, explosion, firework, dust, rain, shock ring), `motion.js` (whip-glides, tracking cam, breathing, damped shake, shockwave, shell fade,
  comic overlay timing), `story.js` (demo staging), `toonbase.js` + `cast.js` (Pen API, MIT, + poses and comic overlays), `castdefs.js`, `paint.js`.
- `engine/`: `render.mjs`, `audit.mjs` (retention audit + stills list), `pacing.py`, `timing.py`, `captions.py` (.ass pop words), `sheet.py`, `finish.sh`.
- `engine/audio/`: `audio.py` (cue table), `mix.py` (-6.0 dB lock), `finish_audio.py` (-14 LUFS, LRA 2.4-2.9, -1 dBTP), synth modules (MIT).
- `example/rocket_cart/script.txt` (demo narration), `example/mountain_man_v1/` (original toon engine + story, reference only).
