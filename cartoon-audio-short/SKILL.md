---
name: "cartoon-audio-short"
description: "Make a 58-65 s vertical (1080x1920, 30 fps) animated short: 2D ink-outlined bean characters in a realistic PBR 3D world with continuous camera moves, a 5-beat hook-to-payoff story with a 3D cutaway, pop-word captions, and a voiceover + SFX soundtrack (no background music) with SFX locked at -6 dB under the user's voice. Offers 10 idea cards, writes the script, then turns the voiceover into a finished MP4. Use for any cartoon short or animated story video request."
---

# Vertical cartoon short v2: idea → script → voiceover → finished MP4

**The look:** flat 2D characters in the reference style: white round heads, bean torsos in patterned fabric, thin solid-black stick limbs, bold black ink outlines and bold hats, drawn on high-res canvas cards, standing in a **realistic PBR 3D world** (MeshStandardMaterial with procedural albedo + normal + roughness maps, physical sky, fog to the horizon, soft shadows, IBL reflections). The camera never stops moving and never hard-cuts inside a location. Comic overlays (rage eyes, sweat, white-out eyes, impact lines) land on frame-exact beats.

**Output and mastering spec (non-negotiable):**
- 1080x1920 (9:16), strictly 30.00 fps CFR, 58-65 s (1,750-1,950 frames). Script ~180-210 words at ~3.2-3.5 words/s.
- The voiceover is never edited, re-timed, EQ'd or compressed.
- **No background music.** The soundtrack is the voiceover + SFX only (no music bed, no musical stings, no melodic or drum elements).
- SFX locked at **-6.0 dB (50 % gated RMS) vs the voice**; SFX peaks capped below the voice peak (0.7x). Always use `mix.py voice sfx.wav mix.wav`.
- Master: **-14.0 LUFS integrated, LRA 2.4-2.9 LU, -1.0 dBFS true-peak ceiling** (`finish_audio.py`, run by `finish.sh`).
- Pop-word captions are on by default (see 4.8). Turn them off only if the user asks.
- **Characters are never blurred.** DOF, motion blur and bloom act on the world only; character pixels stay tack-sharp and are never smeared into a blurred background (enforced in `main.js`).

## Rules
- Stories, characters and shots are always original. Never recreate another creator's video shot for shot; offer an original take instead.
- No real, named living people as characters, and no brand mascots or logos. Diegetic text (signs) must read correctly (not mirrored).
- The picture is timed to the voice; every visual reaction lands 0-3 frames before its word.
- Keep the user informed with a task list. **Always send a stills contact sheet and the audit result before the long render.**
- Validate before rendering: `node --check` every `web/*.js`, `python3 -m py_compile` every script, `node audit.mjs` clean.

## Reference style (analysed at 30 fps)
Measured from the user's reference shorts with `refscan.py` (pacing and look only: never copy their stories, shots, characters or text):
| Metric | Reference | Our rule |
|---|---|---|
| Format | 30/1 fps, 59.1-59.5 s, vertical 9:16 | 1080x1920, 30.00 fps CFR, 58-65 s |
| Hard cuts | 2 and 6 per minute (avg shot 8.5-20 s) | continuous camera; whip-glides inside a location, cuts only for place/time jumps |
| Static camera | 1.9 % of frames, longest hold 9-13 f | never static 4+ frames (`alive()`), audit flags it |
| Motion | always moving; spikes on whips and impacts | slow push / orbit / tracking + bursts on beats |
| Captions | ~1 word per card, a new card every ~11 f (0.37 s), centre, ~70 % height | `captions.py`: one word per card (short words pair up), y = 70 % |
| Colour | vivid: night = moonlit blue + warm practicals, day = saturated green / blue | presets with sat 1.08-1.16, bloom on practicals |
| Loudness | -14.0 LUFS, LRA 2.4-2.5 LU, peak ≈ -2 dBFS | -14.0 LUFS, LRA 2.4-2.9 LU, ≤ -1.0 dBTP |

**Character design (match this):** pure white round head (slightly flattened circle) with a thick black outline; minimal face (dot / half-lid eyes, thin arched brows, small mouth, bold black moustache when needed); black hair cap, topknot or a bold hat (wide brim, cap, flat conical kasa); a tall bean torso in **patterned** cloth (stripes, ikat diamonds, check, dots); thin **solid-black** stick arms and legs with tiny black hands and oval feet. Characters are large in frame (MCUs: head in the upper third, torso filling the middle) and always readable: flat-ish lighting with a floor of 62 % of the painted colour, never clipped to white, never bloomed, never blurred. They hold or touch real 3D props (bombs, trays, signs, steering wheels).

**World + camera (match this):** game-engine-realistic sets (camps, tents with rugs and lanterns, highways, farms, offices, car interiors), soft shadows under every character, practical lights that glow (bloom), cinematic dusk/night grading. The mechanism beat uses an exploded / X-ray view of the object or a driver POV from inside a vehicle; the payoff is a huge explosion or crash.

To analyse new references: `python3 refscan.py ref.mp4 work/ref1` (cuts, static runs, motion per second, caption cadence, colour, loudness + a 1 fps contact sheet) and `python3 camscan.py ref.mp4 work/cam1` (per-frame camera move classes, shot sizes, head placement, horizon, palettes → `report.md`, `timeline.png`), then look at both.

### Camera grammar (camscan.py, 30 fps, both references)
| Measure | Reference | Engine rule |
|---|---|---|
| Move mix (share of frames) | creep 22-26 %, dolly-in 14-23 %, dolly-out 11-12 %, orbit/truck 13-19 %, crane 6-14 %, static 6-12 %, pan 2 %, tilt 2-3 %, roll 2-3 %, whip 0-3 % | the camera travels through the set (dolly / orbit / crane, real parallax); pure pan/tilt in place is rare |
| Accent cadence | a new 6-8 f move accent every ~21-22 frames (median segment 6-8 f) | `microMoves()` is applied to every shot in `frameState` (accent every ~21 f; `micro: 0` on tracking shots; pass `beats` = word frames to land them on words); `audit.mjs` warns if the cadence is > 45 f |
| Big accents | smoothed speed peaks every 51-111 f | pattern interrupt every 60-90 f (whip, scale change, impact, light shift) |
| Direction | push-ins outnumber pull-outs (19-31 % vs 15-17 % of frames) | net dolly-in bias; pull-outs reveal |
| Speed | median ~0.35 % of frame width per frame, p90 1.2-2.3 %, p99 3-6 % | creep + accents; whips only for transitions |
| Shot length | 7-20 s between hard cuts | one continuous camera per location |
| Framing | heads centred (x ≈ 52 %, p25-p75 35-64 %), head top at 36-46 % of frame height; head height median 10 % (camp, MCU/MS) and 5 % (road, FS/WS) | `heroCam(target, {size, yawDeg})` and `distFor(size, fov)`: MCU 12 %, MS 8 %, FS 4.5 %, WS 2.5 % of frame height |
| Camera height | horizon at 43-44 % of frame height (p25-p75 35-54 %): eye-level / slightly high camera looking a little down | camera ~1.3-1.6 m (character chest/eye height), aim at head height |

### World + colour palette (camscan.py)
| Look | Sky | Ground | Accents | Luminance p50 / sat | Preset |
|---|---|---|---|---|---|
| Moonlit camp / night | #1e263d-#363f58 (navy) | #5b3e31-#76482b (firelit earth) | cream heads #f0e0d0, fire #a5612d-#d99654, big blooming moon | 40-66 / 90-120 | `moonCamp` (+ lanterns / fires as practicals) |
| Tent interior | warm mauve #796465-#927469 | rug red #7b302b | warm R-B +27..+35 | 80-97 / 90-100 | warm practicals, `golden`-like key |
| Bright day / road | #7bb1e3-#9cb1d0 over #c9cdd6 haze | grass #3d582b / #5d8728 / #a0ad36, asphalt #9f9fa3 | red / yellow props, white cumulus | 110-160 / 70-90 | `brightDay` |
| Storm / car night | #2c3035-#444f5d | #292a2f | headlight cream, red tail-lights | 45-78 / 45-60 | `stormyRoad` |
| Payoff explosion | warm grey #8c8c99 | sunlit #8a7a68 | fireball #ecbd7a | 146 / 56 | explosion + flash + bloom |
Every world shot has a warm/cool split: cool sky / ambience against warm practical light on the ground and the props. Midtones stay dark at night (characters still read: card floor 62 %).

## Stage 1: Intake (always first)
If an audio file is already attached, skip to Stage 4 (use a script if given). Otherwise ask one AskUserQuestion: **"Where are you starting from?"**
- **Voiceover ready**: ask for the upload plus the script text (it makes timing exact). Go to Stage 4.
- **I have a script, need the voiceover**: run the Stage 3 rules and `pacing.py` on it, return it tightened with recording tips, ask for the upload.
- **Need video ideas and a script**: Stage 2.
The length is fixed at 58-65 s; say so if the user asks for something else and confirm.

## Stage 2: 10 idea cards (3-part arcs)
Give exactly 10 ideas in one reply, numbered; ask for a number (or "more"). Each card shows the **whole arc** so the user can judge it before picking:
- **Title** (5-8 words, curiosity-driven).
- **1 Hook line** (0-4 s): the first spoken sentence. Mid-action, with a concrete number or paradox in the first 8 words ("He drilled 82 holes in a ship he was trying to save.").
- **2 Midpoint cutaway** (38-52 s): the curiosity question + what the 3D cutaway / X-ray / POV shows ("So what's in the barrel? X-ray: 300 kg of cheese wheels as ballast.").
- **3 Final payoff** (last words): the large physical climax or ironic twist that lands on the final word.
- **Why it animates**: 2-3 big visual moments; which lighting presets (Crisp Daylight / Night Rain + lanterns / Stormy Road + headlights).
- **True or legend**: documented, disputed or folklore. Verify anything presented as true with a web search; frame viral legends as "legend says".
Good ideas: one surprising story with physical cause and effect, an everyman hero, a skeptic who mocks or makes it worse, a mechanism you can X-ray, a setting buildable from real-world props (roads, villages, harbours, camps, workshops). Mix eras and themes. Nothing graphic, political, or mocking real living people.

## Stage 3: Script (high-retention rules)
Narration only, ~180-210 words. Then run `python3 <kit>/engine/pacing.py script.txt` and fix every WARN.
1. **0-second hook (0-4 s):** open mid-action; a concrete number or paradox in the first 8 words. Banned: "Have you ever wondered...", "In ancient times...", "Did you know...", "Imagine...".
2. **World reveal (4-15 s):** when/where/who + the stakes, one concrete detail.
3. **Escalating doubt (15-38 s):** a skeptic mocks the hero or makes the problem worse (a commander's "grating cheese" joke; a town's flashing arrow that doubles the crashes). At least one physical-comedy beat. One exaggeration joke.
4. **Midpoint curiosity pivot (38-52 s):** ask "So what's in there?" / "How does this keep happening?" right before the cutaway, then explain the mechanism with an everyday analogy.
5. **Last-word climax (52-65 s):** the biggest explosion, crash or ironic twist lands on the final spoken words. No outro, no call to action.
- **Narrate intent, not visuals:** never describe what the viewer already sees. The voice carries stakes, irony and internal logic; the 2D characters carry the physical comedy.
- Plain spoken English, contractions, 8-15-word sentences, numbers as words.
- **Pacing guard:** `pacing.py` warns over ~210 words, under ~170, and when a slow narrator (deep/"soothing" ElevenLabs voices ≈ 2.6 words/s) would push past 65 s; then suggest speed 1.1 or trim.

Reply with: the script in a copyable block (word count, estimated length at 3.3 w/s and at 2.6 w/s), a one-paragraph 5-beat visual plan (including the cutaway), recording tips (one steady warm narrator; ElevenLabs speed ~1.05-1.1, stability ~45-55 %; mp3/wav, no music; natural pauses at sentence ends), and the ask: **"Upload the voiceover when it's ready and I'll make the full video."** Keep the final script text: it drives timing and captions.

## Stage 4: Build the video (after the voiceover arrives)
Do everything from here without stopping; ask only if timing cannot be resolved.

### 4.0 Kit + setup
The kit ships inside this skill folder at `kit/` (find it with `find / -name SKILL.md -path "*cartoon-audio-short*" 2>/dev/null`; treat it as read-only). Run `bash <skill>/kit/tools/setup.sh ~/shorts/<slug>`: copies the engine, installs three.js r160 (only network step, plus scipy if missing), builds `web/toon.js`, links Playwright, syntax-checks everything.
- Requirements: Node 22+, Python 3 + numpy + scipy + Pillow, ffmpeg with libass, Playwright Chromium. Chromium runs with `--use-angle=swiftshader` (CPU WebGL): **~7-10 s per 1080x1920 frame** with PBR + shadows + post, so a 62 s short is ~3.5-5 h of rendering. Plan for it.
- If `kit/` is missing (a synced copy can carry only this file), tell the user in one line and rebuild from the Architecture section; keep every Engine gotcha.

### 4.1 Timing + pacing
`python3 pacing.py script.txt --voice voice.mp3` (duration must be 58-65 s), then `python3 timing.py voice.mp3 script.txt --out work` (whisper word timestamps if installed, else script-to-silence DP alignment). Total frames = round(duration x 30). Check `work/phrases.json`: pauses fall at sentence ends. Put the key word frames into `WORDS` in `story.js`.

### 4.2 Shot plan (`work/PLAN.md` before code) on the 5-beat grid
| Beat | Time | Frames | Must contain |
|---|---|---|---|
| Hook | 0-4 s | 0-120 | Frame 0 is mid-action (no fade-in, no establishing shot). |
| World reveal | 4-15 s | 120-450 | One continuous pull-back / crane revealing the 3D environment and the stakes. |
| Escalation | 15-38 s | 450-1140 | Skeptic mockery, doubt, ≥1 physical-comedy beat (slip, dive, crash), background micro-gags. |
| Mechanism | 38-52 s | 1140-1560 | Curiosity question, then a 3D cutaway/X-ray (outer shell opacity 1→0 over 10 frames, `shellOpacity`) or driver/character POV that shows how it works. |
| Payoff | 52-65 s | 1560-end | Large-scale physical climax on the final word (explosion / crash / reveal), shake + shockwave. |
One row per shot: frames, words, set, lighting preset, camera move, cast + poses + expressions + comic overlays, VFX, SFX cue.
- **Pattern interrupt every 60-90 frames:** a camera scale change, whip-glide, lighting shift or comic overlay / impact.
- **Background micro-gags:** secondary characters keep reacting (peeking over barrels, betting, diving for cover) so re-watches pay off.
- Sad beats are never played for laughs. Dress and sets stay true to the story's place and period (add outfits to `castdefs.js`).

### 4.3 World: realistic PBR (`web/layout.js` + `web/world.js`, materials in `web/pbr.js`)
Never use MeshToonMaterial or flat colours on world geometry. Build with `PB.pbrMat(key, painter, opts)` (MeshStandardMaterial with albedo, roughness and Sobel normal maps from a height field) and `PB.boxUV(geo, tile)` so texel density is in real metres. Painters:
- Roads & ground: `asphalt` (cracks, tar patches, oil; roughness 0.75 dry, **0.20-0.22 wet**), `roadTex` (yellow centre / white edge lines, dirt tyre tracks, `dirt: true` for tracks), `dirtGround`, `grassGround`, `cobble` (cobblestone, or `flag: true` flagstones) with sunk seams.
- Architecture: `stoneBrick` (recessed mortar, per-brick tone, rain streaks), `woodPlanks` (grain, knots, gaps), `roofTiles` (terracotta barrel or slate), `glassMat()` reflective windows, `paintMat()` car paint, `bark`, `fabric`, `leafCard`.
- Big surfaces get `macro: [scale, amount]` world-space variation (no visible tiling). Wet presets call `applyWet` automatically (roughness → 0.22, albedo darkens).
- Terrain (`terrain.js`): layered fbm heightmap, flat valley floor along the road, hills rising away from it, one story hill. Distant mountain silhouettes (noise-displaced cones with snow caps) at 1.5-2.2 km dissolve into haze.
- Living world: ~40k instanced grass blades with vertex wind sway `sin(time + worldPos.x)`; layered trees (bark trunk, branches, clustered displaced leaf spheres + alpha leaf cards) that sway; conifer forests on the hills; drifting clouds.
- Real-scale props: hand cart (2.2 m, 1.3 m wheels, X-ray shell + inner mechanism), barrels, crates, fences, iron street lanterns, road signs, ridge tents, delivery van with headlights. Houses: stone brick, wood door, framed glass windows, tile roofs.
- Fog: `FogExp2` coloured exactly the sky horizon colour (both skies blend to it at the horizon).
- Register wall AABBs in `walls` so cards near them get the bigger depth pull automatically.

### 4.4 Lighting presets (`web/lighting.js`) + VFX (`web/vfx.js`)
- **brightDay** (reference day palette, vivid blue gradient sky) and **moonCamp** (reference night: navy sky, big blooming moon, warm practicals) were built from the camscan measurements.
- **crispDay**: physical Sky shader, high sun, HemisphereLight sky/ground bounce, light haze, dry ground.
- **nightRain**: moon key + warm PointLight lanterns (pool of 6 nearest the action, flicker), wet ground (roughness 0.22) with specular streaks, rain streaks, blue fog.
- **stormyRoad**: low storm key, SpotLight headlights (+ faint volumetric cones in rain), lightning flashes (`strikes: [f...]`), heavy rain, wet asphalt.
- Extras: **golden**, **memory**. Blend with `lightSeq([[f, "preset"], ...], f)`; a lighting shift counts as a pattern interrupt.
- Sun/moon `DirectionalLight` casts **PCFSoftShadowMap 2048x2048** shadows onto the terrain AND the 2D cards; the shadow camera is centred per shot (`shadow: {c, r}`). Scene IBL comes from the current sky (PMREM, cached).
- Particle presets (frame-pure, seeded): `sparks` (fuse), `debris`, `sawdust`, `smoke` plume, `explosion`, `firework`, `dust`. Emitter: `{id, kind, f0, f1?, at: (g) => [x,y,z], seed, scale, rate?, dir?, col?}`. Plus 2D canvas FX cards (burst, puff, chips, stars, glow) and the ground `shock` ring.

### 4.5 Cast: 2D characters that sit IN the world (`cast.js`, `castdefs.js` → `toon.js`)
- `bodyFrontX` / `bodySideX` draw on a 600x1000 design canvas (soles at y=975, card 2.25 m tall) at 2.4 px per unit; ink is near-black `#0e0c10`. Wide action poses use a 1000x1150 card (`wide: true`).
- Outfits are plain objects (top, kurta, pants, shorts, dhoti, sari, pagri, hair, beard, moustache, gamchha, boots, build). **Reference-style fields:** `skin: "#ffffff"`, `stick: true` (solid-black stick limbs, black hands/feet), `pattern: "stripes" | "ikat" | "check" | "dots"` (+ `patCol`, `patCol2`), `hat: "brim" | "cap" | "kasa" | "topknot"` (+ `hatCol`, `band`). The demo cast in `castdefs.js` uses them. Side modes: walk, stand, hammer; `push: true` (both arms forward on a handle), `armsUp: true` (panic / cheer). Front arm poses: hang, point, up, wave, hip, belly, temple, shoulder, chin, knee, pot...
- Expressions: toon FACE set + sad, stubborn, strain, soft, squint, mock, worried, calm, **rage, whiteout, smug**.
- **Comic overlays** (drawn in head space, follow head tilt): `opts.comic = comicAt(f, [{k: "rage" | "sweat" | "whiteout" | "lines" | "steam", f0, f1, ramp}])`: glowing red rage eyes + vein, falling sweat drops, shocked white-out eyes, radiating impact lines, steam puffs.
- **No "pasted sticker" look** (all automatic in `main.js`): wrapped-Lambert card lighting so cards take the scene light colour (sun, hemisphere, lanterns, headlights) and are normalised so they read at their painted colour; alpha-tested shadow caster (directional shadows on the ground) and shadow receiving; soft contact blob; view-space depth pull 0.3 m default, **0.8 m within 1.5 m of a registered wall** (override with `pull`).
- Side cards need a side camera (|dot(facing, camera right)| ≥ ~0.4). Groups of 3-4 are staggered in depth (front ~5 m, back ~10 m). Rebuild after edits: `cat web/toonbase.js web/cast.js > web/toon.js`; test new designs with `charsheet.html` (`node render.mjs page charsheet.html out.png`).

### 4.6 Continuous camera choreography (`web/motion.js`)
- **No static hard cuts inside a location:** bridge nearby shots with **6-12 frame easeInOutCubic whip-glides** (`camWhipKeys` keys with `whip: n`, or `whipGlide(A, B, f, f0, n)`), which arc sideways, dip fov and roll slightly so the viewer stays oriented in 3D. Hard cut only for place/time jumps, with a ≤6-frame flash (`cut: true` disables motion blur on that frame).
- **Prop / vehicle tracking:** `trackCam(targetAt, f, f0, {offset, lag: 0.08, lookAhead})` for rolling, flying or driving objects; set `mb` 1.2-1.5 for speed.
- **Never static for 4+ frames:** wrap every camera in `alive(cam, f, {push, amp})` (slow push-in + handheld breathing float), or orbit.
- **Heavy impacts:** `kicks: [{f, a}]` → 7-frame damped shake (`dampedShake`) + `shockAt: {f, pos, maxR, dur}` expanding ground ring + debris/dust emitter.
- **Lens:** DOF on close-ups and mediums blurs the background only (`dof: {focus, cInf 8-14}`, bright bokeh); wides sharp; camera motion blur (180° shutter, depth reprojection) on whips and tracking shots, background only. Characters are excluded from DOF, motion blur and bloom. Keep impact shakes ≤ 0.03 so the frame never smears.
- Hit a beat every ~11 frames: something changes on most caption words (an expression, a gesture, a prop move, a camera accent).
- Characters never freeze: `idle`, `blinkAt`, head bobs on stressed words; actions use anticipation → `back` overshoot → `spring` settle.

### 4.7 Look check + retention audit (before ANY full render)
1. `node audit.mjs web/story.js --stills` must print **audit OK**. It checks 1,750-1,950 frames, the 5 beats (hook at frame 0, cutaway/X-ray inside 38-52 s with a 10-frame shell fade, climax event on the last word, no slow outro), no camera static for 4+ frames, a pattern interrupt at least every 90 frames, and **flags any 90-frame (3 s) stretch with no camera move, prop interaction or expression change**. Fix every FLAG.
2. Render the stills it lists: `node render.mjs stills/a "<STILLS list>"` then `python3 sheet.py stills/a stills/sheet_a.jpg 8`. Look at the sheet and fix: hero hidden behind props (move the camera to the hero's open side), camera too close (cards fill the frame), foreground posts across faces, props < 2 m from the lens, mirrored text, dark backlit cards (raise `bright`), repeating ground tiles, cards slicing into walls (`pull`), a camera inside terrain (frameState clamps to ground + 0.6 m). Narrow frame: horizontal half-width = d·tan(hfov/2), hfov = 2·atan(tan(vfov/2)·0.5625).
3. **Send the sheet + the audit summary to the user**, then start the full render.

### 4.8 Sound + captions
- Rewrite the cue table at the top of `audio/audio.py` (frames at 30 fps: whooshes on whips and camera accents, location ambience beds, thunder on strikes, splashes, rattles, fuse fizz, launch, pops, final boom); the synths stay. **No music:** the mystery beat gets tension from SFX (a low wind swell, a fuse fizz, silence before the reveal), and the last word lands on the biggest SFX hit.
- In `audio/`: `python3 audio.py ../voice.mp3 .` (writes `sfx.wav` only) then `python3 mix.py ../voice.mp3 sfx.wav mix.wav`. It must print sfx **-6.0 dB** vs voice and SFX peak ≤ 0.70x voice peak (exit code 2 otherwise: raise the ambience bed a little). The old 3-stem call ignores a music file with a note.
- Captions: `finish.sh` runs `captions.py work/words.json out/captions.ass` automatically: bold white sans (Inter ExtraBold; `CAPTION_FONT=...` to change), **one word per card** (a 1-3 letter word pairs with its neighbour, as in the references), thick black outline + shadow, centred at y = 70 % (1344 px), 92 % → 100 % scale pop over 40 ms, snapped to 30 fps word timestamps, then burned in with libass.
- Lock picture timing before sound; any timing change means re-running audio.py, mix.py and captions.

### 4.9 Render + finish
- `node render.mjs frames "0-<N-1>"` with Bash `run_in_background`, inside a retry loop (`for i in 1 2 3 4 5 6; do RESUME=1 node render.mjs frames "0-<N-1>" && break; done`). Wait with foreground checks of ≤10 min that print the frame count and errors. Re-render only edited ranges.
- `bash finish.sh "Title"`: masters audio (-14.0 LUFS, LRA 2.4-2.9 LU via a slow whole-mix leveller only if needed, -1.0 dBTP), burns captions, encodes H.264 CRF 17 at CFR 30/1 + AAC 256k, verifies 1080x1920@30/1, freeze/black detection, EBU R128 summary, and `out/qa_sheet.jpg`. Frozen spans ≥0.4 s or black frames need a fix (add a creeping push to that shot; flashes cap at 0.9).
- Deliver the MP4 with SendUserFile and a few lines per beat. Offer tweaks or the next idea.

## Engine gotchas (keep them if rebuilding)
- No-blur contract: cards write rgb 0 + depth into the normal/depth target; DOF and motion blur return the sharp pixel for card pixels and give card samples zero weight when blurring the background; the bloom bright-pass skips card pixels; the card shader clamps output to ≤ 0.93 (never clips) with a 62 % readability floor.
- Render targets are linear HalfFloat; the DOF pass encodes sRGB at the end. Grade = exposure, optional world ink (`ink`, 0 for realism), saturation, lift/gain, filmic shoulder, vignette, flash.
- Normal+depth target is FloatType RGBA cleared to alpha 0 (read as far). In that pass: world → normals/depth (alpha-tested materials use a map-aware variant), cards → alpha-tested depth with the same pull, instanced grass / particles / rain / sky / clouds / blobs / beams hidden, fog and shadows off.
- Card material is MeshLambertMaterial with `lights_lambert_pars_fragment` inlined and its `dotNL` wrapped (0.78 + 0.22·N·L), output multiplied by `uGain` = preset-normalised; shadow lookups use the un-pulled world position so a card never shadows itself.
- Constant light counts (6 lantern PointLights, 2 SpotLights, 1 explosion light, always in the scene, intensity 0 when off) so shaders never recompile mid-render.
- Physical Sky output is linearised (`pow 2.2`) and blended to the fog colour below +0.2 elevation; the camera far plane is 8000 m.
- Motion blur reconstructs world position from view depth and reprojects with frameState(f-1)'s camera; it is skipped when the camera jumps > 3.5 m (cuts).
- Particles are analytic (birth time, drag-integrated velocity, gravity, ground bounce), so any frame renders independently (RESUME-safe).
- `#include <fog_vertex>` / `<fog_fragment>` on their own lines in custom shaders; give every `onBeforeCompile` material its own `customProgramCacheKey`.

## Architecture (kit/engine)
- `web/index.html` (importmap: `three`, `three/addons/`) → `main.js` (renderer, lights, IBL, cards, FX, post; `window.renderFrame(f)`).
- `web/world.js` (PBR world builder) · `pbr.js` (texture painters + material factories) · `terrain.js` (heightmap) · `layout.js` (story set dressing, metres) · `lighting.js` (presets) · `vfx.js` (particles, rain, shock ring) · `motion.js` (easing, whips, tracking, breathing, shake, shockwave, shell fade, comicAt) · `story.js` (SHOTS, BEATS, WORDS, frameState; Node-importable) · `toonbase.js` + `cast.js` (Pen API from mromidev/claude-animated-shorts toon.ts, MIT, + cast, poses, overlays) · `castdefs.js` · `paint.js` (storybook painters, clouds) · `charsheet.html`.
- `render.mjs` (Playwright frames / stills / test pages) · `refscan.py` + `camscan.py` (30 fps reference analysis: pacing, camera, framing, colour) · `audit.mjs` (retention audit + stills list) · `pacing.py` (word count / hook lint / duration) · `timing.py` (script-to-voice alignment) · `captions.py` (.ass pop words) · `sheet.py` (contact sheets) · `finish.sh`.
- `audio/`: `audio.py` (SFX cue table + synths, no music), `mix.py` (voice + SFX, -6.0 dB lock + SFX peak cap), `finish_audio.py` (LRA fit, -14 LUFS, -1 dBTP), `dsp.py`, `instruments.py`, `sfx_gen.py` (MIT, mromidev/claude-animated-shorts).
- `example/rocket_cart/` = the v2 demo script (the engine's `story.js` stages it); `example/mountain_man_v1/` = the original toon-world engine and story, for reference only.
