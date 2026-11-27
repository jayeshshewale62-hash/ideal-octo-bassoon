# Studio Modules

Motion Animation Studio is split into sixteen independent modules. Each one has a Python
package (or provider kind), a milestone and clear data boundaries. `studio modules` prints
the live status. `studio/modules.py` is the source of truth, and a test keeps this
document in sync with it.

| # | Module | Package | Milestone | Status after M2 |
|---|---|---|---|---|
| 1 | Story Development Engine | `studio.story` | M9 | planned |
| 2 | Character Creation Engine | `studio.characters` | M3 | planned (identity schema exists) |
| 3 | Character Consistency Manager | `studio.characters` | M8 | planned |
| 4 | Character Rigging Engine | `studio.rig` | M3 (FK), M5 (IK, deform) | planned |
| 5 | Facial Expression Engine | `studio.rig` | M4 | planned |
| 6 | Animation Engine | `studio.animation` | M5 | planned |
| 7 | Environment Creation Engine | `studio.environments` | M6 | planned (metadata schema exists) |
| 8 | Storyboard Engine | `studio.storyboard` | M6 | planned |
| 9 | Camera and Scene Engine | `studio.scene` | M6 | planned |
| 10 | AI Image Generation Engine | `studio.providers.image` | M9 | interfaces + mock |
| 11 | Voice Generation Engine | `studio.providers.tts` (+ `studio.audio`) | M4 | interfaces + mock |
| 12 | Audio and Sound Effects Engine | `studio.audio` | M7 | planned |
| 13 | Video Composition Engine | `studio.compose` | M7 | planned |
| 14 | Rendering Engine | `studio.render` | M7, M10 | planned (profiles defined) |
| 15 | Quality Control Engine | `studio.qc` | M8 | planned (project validation exists) |
| 16 | Asset and Project Manager | `studio.core` | **M2** | **implemented (foundation)** |

**Architectural rule.** The animation system creates *actual animated character
movement*: rigs posed frame by frame from editable curves. It is never built on static
character images panned by a camera, slideshows, per-frame AI images, or a fixed set of
uneditable poses.

---

## 1. Story Development Engine

- **Purpose:** turn a brief into a premise, outline, beat sheet and a script with dialogue per character.
- **Technology:** Python, YAML. The optional `llm` provider (mock in tests) assists. Hand-written scripts always work without it.
- **Inputs → outputs:** `brief.yaml` → `story/story.yaml`, script text registered as `script` assets.
- **Dependencies:** module 16, `studio.providers.llm`.
- **Testing:** schema validation; word count vs target duration per profile frame rate; script lint (sentence length, re-hooks); mock LLM only in CI.

## 2. Character Creation Engine

- **Purpose:** define **original** characters: layered SVG parts, canonical palette, proportions in head-heights, personality, voice mapping, model sheets.
- **Technology:** SVG part templates, Python. Optional concept art from module 10 (always redrawn as rig parts, never used as frames).
- **Inputs → outputs:** character brief + artwork → `assets/characters/<id>/character.yaml` (`CharacterIdentity` schema), `parts.svg`, model sheet.
- **Dependencies:** 16; consumed by 3 and 4.
- **Testing:** required parts and layer names present; palette and proportions within schema; turnaround views complete (front, three-quarter, side, back); silhouette distinctness between cast members.

## 3. Character Consistency Manager

- **Purpose:** lock each character's canonical design and detect drift (identity and version control).
- **Technology:** golden-image comparison of fixed poses, palette delta-E checks, proportion tolerance from `CharacterProportions.tolerance`. Reference images for AI concept work.
- **Inputs → outputs:** renders + `character.yaml` → consistency report.
- **Dependencies:** 2, 4, 15.
- **Testing:** golden frames in `tests/golden/`; deliberate off-model fixtures must fail.

## 4. Character Rigging Engine

- **Purpose:** hierarchical bone rigs that pose SVG parts.
- **Technology:** Python + NumPy transforms. Versioned `rig.json` (data contract in `studio/rig/__init__.py`).
- **Capabilities to support:** bone hierarchy; forward kinematics; two-bone inverse kinematics with pole targets and FK/IK blend; joint pivots and rotation/scale limits; draw-order switching (per view and keyed); mesh and warp deformation; independent body-part controls; replacement-part sets; turnaround views.
- **Inputs → outputs:** `parts.svg` + `rig.json` → posable rig → posed vector geometry.
- **Dependencies:** 2, 16; consumed by 5, 6.
- **Testing:** FK/IK maths unit tests; joint-limit enforcement; pose fuzzing (no detached parts at extreme poses); save/load round trip; golden frames.

## 5. Facial Expression Engine

- **Purpose:** expressive faces driven by parameters.
- **Capabilities to support:** independent eye controls; pupil and gaze direction; eyelids; blinking (with cadence); eyebrows; phoneme→viseme mouth shapes; cheek deformation; expression presets; smooth blends between expressions.
- **Technology:** parameter-driven face rig layered on module 4. Visemes come from `asr` word/phoneme timings.
- **Inputs → outputs:** alignment + emotion cues → face-control curves.
- **Dependencies:** 4, 11 (alignment).
- **Testing:** viseme coverage for every phoneme class; blink cadence; lip-sync offset ≤ 1 frame on a fixture clip.

## 6. Animation Engine

- **Purpose:** turn keyed, editable curves into per-frame rig poses.
- **Capabilities to support:** walk, run and idle cycles; jumping; sitting and standing; turning; reaching; lifting and carrying; secondary motion; overlapping action; follow-through; squash and stretch; holds on ones and twos.
- **Hand and object interaction:** pointing, grabbing, holding, releasing, object manipulation, character-to-character interaction, contact constraints, eye-line coordination, prop handoffs.
- **Hand-drawn quality:** variable-width, pressure-tapered ink strokes; slight line irregularity; optional line boil (2–3 controlled redraw variants); smear frames; frame-by-frame replacement parts; organic rather than mechanical motion.
- **Technology:** Python curve evaluation. The clock is in seconds, and frames are sampled per render profile (`studio.core.timecode`).
- **Dependencies:** 4, 5, 9.
- **Testing:** curve maths; cycles loop seamlessly; identical output at 24/25/30 fps sampling; golden frames.

## 7. Environment Creation Engine

- **Purpose:** illustrated environments as parallax layers.
- **Technology:** layered PNG/ORA/SVG, `EnvironmentMetadata` schema (layers with depth and blur, palette, time of day). Painted plates may come from module 10, always after human review and with AI provenance recorded.
- **Dependencies:** 10 (optional), 16.
- **Testing:** layer sizes cover overscan; depth ordering; unique layer names.

## 8. Storyboard Engine

- **Purpose:** script + timing → shot list → animatic and contact sheets.
- **Technology:** Python, YAML (`storyboard/storyboard.yaml`; a placeholder already exists in every project).
- **Dependencies:** 1, 9, 11.
- **Testing:** every script line covered by a shot; static-hold and pacing audits; animatic length equals audio length.
- **Legacy reference:** Branch A `audit.py` (see LEGACY_REUSE.md).

## 9. Camera and Scene Engine

- **Purpose:** per-shot scene graph: framing, camera moves, staging and transitions.
- **Capabilities to support:** shot sizes on thirds; push, pull, punch, glide and tilt; handheld float; 2.5D parallax with the floor pivot locked so feet never slide; depth blur; multi-character staging; transitions (cut, dissolve, wipe, match cut, iris) as data.
- **Dependencies:** 6, 7.
- **Testing:** framing maths; overscan clamp; transition timing.
- **Legacy reference:** Branch A `camera.py` design (reference only, no licence).

## 10. AI Image Generation Engine

- **Purpose:** concept art, background plates and textures. **Never per-frame character animation.**
- **Technology:** `ImageProvider` interface (`studio.providers.image`). `none` and `mock` are implemented. Planned: `comfyui` (SDXL/Flux on a GPU render node) and an optional `cloud-image` adapter.
- **Inputs → outputs:** `ImageRequest` (prompt, size, seed, references) → PNG + provenance, registered with `source.kind: ai_generated` and `ai_provenance`.
- **Testing:** mock provider in CI; seed determinism; provenance required by schema.

## 11. Voice Generation Engine

- **Purpose:** dialogue and narration per character, plus alignment for lip-sync.
- **Technology:** `TTSProvider` and `ASRProvider` interfaces. `none` and `mock` are implemented. Planned: `kokoro`, `recorded`, `whisper`, `parakeet`, and an optional `cloud-tts`.
- **Inputs → outputs:** script lines + voice map → WAV per line + word timings.
- **Testing:** mock TTS → mock ASR round trip in CI; clipping and silence checks; alignment error on fixtures.

## 12. Audio and Sound Effects Engine

- **Purpose:** SFX cues, ambience beds, music, ducking and loudness mastering.
- **Technology:** FFmpeg (loudnorm, sidechain compression) and Python. Targets come from the render profile (`loudness_lufs`, `true_peak_dbtp`).
- **Dependencies:** 11, 16.
- **Testing:** integrated loudness within ±1 LU; true peak ≤ target; zero A/V drift.
- **Legacy reference:** Branch B `finish_audio.py` / `mix.py`.

## 13. Video Composition Engine

- **Purpose:** composite rig renders, environment layers, effects, titles and captions into shots, then assemble shots.
- **Technology:** skia compositing; libass captions; an optional browser/HyperFrames backend for titles only.
- **Testing:** pixel-diff golden frames; alpha correctness; caption safe areas.

## 14. Rendering Engine

- **Purpose:** frame scheduling, parallel workers, content-hash caching, encoding and backends.
- **Technology:** Python multiprocessing, FFmpeg (libx264). Profiles in `config/render_profiles.yaml` (1080p24, 1080p30, 2160p24, 540p12 preview). skia CPU backend is the core. Optional backends: Blender Grease Pencil, browser.
- **Testing:** resumable after interruption; cache hits; output matches profile (ffprobe).

## 15. Quality Control Engine

- **Purpose:** automatic pass/fail on renders and projects.
- **Technology:** ffprobe, loudness metering, frame analysis, consistency checks. Builds on module 16's `ValidationReport`.
- **Testing:** fails on wrong resolution or frame rate, A/V offset, black or frozen frames, loudness out of range, missing assets, off-model characters.

## 16. Asset and Project Manager

- **Purpose:** projects, asset registry, hashing, versions, dependencies, provenance and licences. **Implemented in Milestone 2.**
- **Technology:** `studio.core`: pydantic schemas, a file-based JSON registry (ADR 0003), SHA-256 content hashes, path-safety checks.
- **Inputs → outputs:** files + metadata → `assets/registry.json`; projects → validation reports.
- **Testing:** `tests/unit/test_project.py`, `test_assets.py`, `test_schemas.py`, `tests/integration/test_cli.py`.
