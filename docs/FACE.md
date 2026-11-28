# Faces: Facial Rigs, Expressions, Visemes and Lip-Sync (Milestone 4)

Package `studio.face` (module 5). Original, pure Python, CPU-only, deterministic and
offline. Facial performance is **editable control values plus timing data** applied to a
character's facial rig. It is never generated or flattened into images.

| Capability | Status |
|---|---|
| Facial rig schema (components, controls with limits, anchor, part/attachment binding, artwork, shapes) | implemented |
| Templates `standard` (eyes, brows, mouth, jaw, cheeks, nose) and `minimal` (no cheeks/nose), sized from the head part | implemented |
| Eye, eyebrow, mouth, jaw, cheek and nose controls with geometry resolution | implemented |
| 12 built-in expression presets; custom expressions with versioning | implemented |
| Deterministic blending (two-way with ease, weighted multi-way), transition interface | implemented |
| Editable viseme set (14 visemes) and replaceable phoneme maps (`en_arpabet`, `ipa_basic`) | implemented |
| Phoneme → viseme mapping with timing validation, silence, adjacency merge, unknown policy | implemented |
| Timestamp lip-sync evaluation: transitions, coarticulation, exact boundaries | implemented |
| Alignment provider interface (phoneme timestamps), disabled by default; alignment file schema | implemented (interface only) |
| Diagnostic SVG previews (expressions, blends, sampled lip-sync states) | implemented |
| Speech recognition, forced alignment, text-to-speech | **not implemented** (out of scope) |
| Rendering facial *artwork* deformations, animation timelines | **not implemented** (later milestones) |

## Files

```
projects/<slug>/characters/<id>/
    face.yaml                        FacialRig (schema_version 1)
    expressions/<expression-id>.yaml custom FacialExpression
    history/face.v<N>.yaml           earlier face versions (never overwritten)
    history/expressions/<id>.v<N>.yaml
any folder:
    *.alignment.json / .yaml         AlignmentDocument (word/phoneme timestamps)
    *.lipsync.yaml                   LipSyncTrack (viseme events + timing settings)
studio/face/data/                    built-in expressions, viseme set, phoneme maps (YAML)
```

`character.yaml` gains an optional `face: face_<id>` field. Characters without it (all
Milestone 3 files) stay valid. Creating a face bumps the character version. Reusing a
character's structure (`--from`) does not copy its face.

## Facial rig

```bash
studio face create projects/demo chr_mira-vale [--template standard|minimal]
studio face info projects/demo chr_mira-vale [--json]
studio face validate projects/demo chr_mira-vale [--json]
studio face set-asset projects/demo chr_mira-vale eye_l ast_…            # default artwork
studio face set-asset projects/demo chr_mira-vale mouth ast_… --shape ai # mouth drawing for a shape
```

**Face space:** the origin is the face anchor on the head part, +x points to screen right
in the front view, **+y points down**, and units are character design units. The anchor
(`anchor.part`, `anchor.position` or `anchor.attachment`) ties face space to the head
part's artwork coordinates, so the face follows the head bone through the M3 part
hierarchy.

A **component** (`eye_l`, `brow_r`, `mouth`, `jaw`, `cheek_l`, `nose`, or a custom one)
has a kind, a rest `position` and `size` in face space, and a list of **controls**
(channels). Each control has `min`, `max`, `default` (neutral) and a unit. A component can
bind to a character part or attachment point (`attachment`), carry default artwork
(`asset`), and list replacement `shapes` (for example one mouth drawing per viseme). All
artwork goes through the Asset Manager, and only SVG, PNG or WebP is accepted. Not every
character needs every component.

| Component | Controls (standard template) |
|---|---|
| eye_l / eye_r | `offset_x`, `offset_y`, `scale`, `rotation` (°), `pupil_x`, `pupil_y` (gaze, −1..1), `pupil_scale`, `blink` (0 open … 1 closed), `squint`, `visible` (0/1) |
| brow_l / brow_r | `offset_x`, `raise` (−1..1, vertical movement), `rotation` (°), `scale`, `shape` (−1 angled … +1 arched) |
| mouth | `offset_x`, `offset_y`, `width`, `height`, `open`, `corner_l`, `corner_r`, `upper_lip`, `lower_lip`, `pucker`; shapes `rest mbp ai e ee o u ch st fv th l k r` |
| jaw | `open`, `offset_x` |
| cheek_l / cheek_r (optional) | `raise`, `puff` |
| nose (optional) | `wrinkle`, `offset_y`, `scale` |

Control → geometry (`studio.face.geometry.resolve_face`), summarised:
- **Eye:** centre moves by `offset × size`, and size scales by `scale`. The upper lid closes
  with `blink`, the lower lid rises with `squint`, the pupil moves `pupil × 0.3 × size`, and
  the gaze angle is `atan2(pupil_y, pupil_x)`.
- **Brow:** rises `raise × 0.35 × width`, and its arch is `shape × 0.25 × length`.
- **Mouth:** width is `size × width × (1 − 0.35·pucker)`, and the gap is
  `size × height × (open + 0.5·jaw.open)`. Corners move `−corner × 0.35 × height` (positive
  is up), and lips move by `±lip × 0.2 × height`. The jaw drop also lowers the mouth.

Rotations follow the rig convention: positive is clockwise on screen. Because `brow_l` is
drawn on screen right in the front view, "inner end up" means +° for `brow_l` and −° for
`brow_r`.

## Expressions

```bash
studio face expressions list projects/demo chr_mira-vale
studio face expressions create projects/demo chr_mira-vale smug --name Smug --from happy \
    --set mouth.corner_r=-0.2 --set eye_l.blink=0.3 --shape mouth=e
studio face expressions set projects/demo chr_mira-vale smug --set eye_l.blink=0.5   # new version
studio face expressions preview projects/demo chr_mira-vale happy sad angry
studio face expressions blend projects/demo chr_mira-vale neutral happy --weight 0.5 --ease smoothstep
```

**Built-ins:** neutral, happy, sad, angry, surprised, curious, confused, fearful, disgusted,
excited, tired and worried. They are stored in `studio/face/data/expressions.yaml`. They are
generic: a control the rig lacks (for example cheeks on a `minimal` face) is skipped with
warning `EXP002`.

**Custom expressions** are bound to the character's rig, must match it exactly (unknown
controls or shapes are errors), cannot reuse a built-in ID, and are versioned with history.

**Evaluation:**
- Every control starts at its default.
- Expression values override it and are **clamped** to the control's limits; values
  outside the limits are reported as `EXP003`.
- Shapes are categorical selections.

**Blending** (`blend_expressions`):

```
value = a + (b − a) · ease(w),  w ∈ [0, 1],  ease ∈ {linear, smoothstep = 3w² − 2w³}
```

- Both inputs are within limits and the blend is convex, so limits are preserved.
- Weights outside [0, 1] are clamped and reported (`BLD002`). NaN, infinity and non-numbers
  are refused.
- Shapes switch to the target's shape when `ease(w) ≥ 0.5`.
- `blend_many` normalises any non-negative weights (sum > 0) and takes a weighted average.

**Interface for later animation milestones:** `ExpressionTransition(from, to, start,
duration, ease)` and `evaluate_transition(rig, transition, time)` give the face at any
time. This milestone has no timeline editor.

## Visemes

Default set `default` (`studio/face/data/visemes.yaml`). Every viseme is editable, and a
replacement set file can be passed with `--visemes FILE`.

| id | Name | Intended articulation (animation posture, not a phonetic claim) |
|---|---|---|
| rest | Rest / neutral | lips relaxed, closed or barely parted; used for silence |
| mbp | Closed lips | lips pressed together (M, B, P) |
| ai | Open jaw | jaw dropped, mouth open (A, AH, AY) |
| e | Wide mouth | spread wide, medium opening (EH, AE, EY) |
| ee | Wide, narrow opening | spread wide, small opening, corners slightly up (IY, IH, Y) |
| o | Rounded mouth | lips rounded into an open oval (OW, AO, OY) |
| u | Narrow rounded (pucker) | lips forward, small round opening (UW, UH, W) |
| ch | Narrow, teeth together | lips slightly forward, teeth close (CH, JH, SH, ZH) |
| st | Teeth / lip contact | teeth together or nearly, lips parted (D, T, N, S, Z) |
| fv | Lower-lip contact | lower lip against the upper teeth (F, V) |
| th | Tongue between teeth | tongue tip visible (TH, DH); `tongue_visible` |
| l | Tongue tip up | open mouth, tongue tip raised (L); `tongue_visible` |
| k | Back consonant | slightly open, jaw part-way (K, G, NG, HH) |
| r | R-coloured | lips slightly rounded and narrow (R, ER) |

Each viseme sets mouth and jaw control values, an optional mouth `shape` for replacement
drawings, and `teeth_visible` / `tongue_visible` flags.

## Phoneme → viseme mapping

```bash
studio face phonemes maps
studio face phonemes map hello.alignment.json --map en_arpabet --out hello.lipsync.yaml \
    [--visemes FILE] [--no-merge] [--no-silence] [--transition 0.06] [--coarticulation 0.2]
```

Maps are data (`studio/face/data/phoneme_maps/*.yaml`) and can be replaced with
`--map FILE`. Each map has `language`, `alphabet`, `case_sensitive`, `strip_stress`
(ARPAbet `AH0 → AH`), `silence` symbols, an `unknown` policy (`rest` / `previous` /
`error`) and the table.
- `en_arpabet` covers the 39 CMUdict phonemes.
- `ipa_basic` is a small multi-language IPA example.
- Mappings are practical animation choices. **They are not perfect for every language or
  accent.**

The mapper is deterministic and **never invents timestamps**:
- Events must be in time order, non-overlapping, finite, ≥ 0 and have positive duration.
- Silence symbols map to `rest`.
- Gaps between the given events (and before the first one) become explicit `rest` events
  covering exactly those gaps; turn this off with `--no-silence`.
- Touching events with the same viseme are merged, keeping every phoneme label; turn this
  off with `--no-merge`.
- Unknown phonemes follow the map's policy and are reported (`LIP005`).

## Lip-sync timing

```bash
studio face lipsync validate hello.lipsync.yaml
studio face lipsync evaluate hello.lipsync.yaml --time 0.12 --time 0.3 [--json]
studio face lipsync evaluate hello.lipsync.yaml --sample 0.04 [--until 2.0]
studio face lipsync preview projects/demo chr_mira-vale hello.lipsync.yaml --sample 0.1 --expression happy
```

API: `evaluate_lipsync(track, time, visemes, rig=None)`. For per-frame use, build
`LipSyncEvaluator(track, visemes, rig)` once and call `.evaluate(time)`.

- **Intervals are half-open `[start, end)`.** A time exactly on a boundary belongs to the
  later event. Before the first event, in gaps and after the last event, the mouth is `rest`.
- **Transition** (`settings.transition`, default 0.06 s, capped at half the segment):
  entering a segment blends from the previous segment's final state with the configured
  ease (`smoothstep` by default). At the boundary the weight is 0, so the mouth is
  continuous.
- **Coarticulation** (`settings.coarticulation`, 0..1, default 0): in the second half of a
  segment, up to that fraction of the next viseme is mixed in, ramping linearly. The next
  transition starts from that mixed state, so it stays continuous.
- **Output:**
  - viseme weights;
  - mouth and jaw control values: a weighted average, missing values fall back to `rest`,
    then the rig default; clamped to rig limits;
  - the active segment's viseme, the dominant viseme and its shape;
  - teeth and tongue flags.
- **Combining with an expression:** `apply_lipsync(face_state, lips, rig)` lets speech drive
  the mouth and jaw while the expression keeps eyes, brows and cheeks. Mouth corners are
  *added*, so a smile survives speech.
- **Determinism:** the same track, viseme set and time always give the same output, and
  tests check this.

Example (real output, `docs/examples/chr_mira-vale/hello.lipsync.yaml`, coarticulation 0.2):

```
t=   0.120  segment=k     dominant=k     open=0.210 jaw=0.180  [k:0.600 rest:0.400]
t=   0.300  segment=l     dominant=ai    open=0.720 jaw=0.630  [ai:0.800 l:0.200]
t=   0.500  segment=o     dominant=o     open=0.540 jaw=0.442  [o:0.982 rest:0.018]
t=   0.650  segment=rest  dominant=rest  open=0.033 jaw=0.027  [o:0.059 rest:0.941]
```

## Audio alignment providers

The `asr` provider interface (`studio.providers.asr`) now has optional phoneme timestamps
(`AlignmentResult.phonemes`, capability `phoneme_timestamps`).

| Provider | Status | Phonemes |
|---|---|---|
| `none` (default) | disabled: refuses every call with a clear message | n/a |
| `mock` | offline, deterministic, **word timings only** | no (never claims them) |
| `whisper`, `parakeet` | planned (need model weights; not downloaded) | depends on integration |

```bash
studio face alignment inspect hello.alignment.json        # schema + timing checks, "lip_sync_ready"
studio face alignment run line01.wav --text "hello" [--project projects/demo] [--out a.json]
```

- `alignment run` uses the configured `asr` provider. With the default `none` it refuses.
  With `mock` it writes words only, and mapping then fails with `LIP008`; no phoneme
  timings are guessed.
- Alignment files from external tools (or written by hand) use the `alignment_result`
  schema. `studio schema export alignment_result` prints it.
- No network, credentials or models are needed or requested.

## Validation codes

| Code | Severity | Meaning |
|---|---|---|
| FAC001 | error | `face.yaml` missing or invalid |
| FAC002 | error | face belongs to another character / id mismatch |
| FAC003 | error | duplicate component id |
| FAC004 | error | duplicate control in a component |
| FAC005 | error | control min > max, or default outside limits |
| FAC006 | error | component attached to a missing part |
| FAC007 | error | unknown attachment point |
| FAC008 | error | anchor part missing |
| FAC009 | warning | component lacks a typical control (e.g. eye without `blink`) |
| FAC010 | error | component artwork not registered |
| FAC011 | error | component artwork not SVG/PNG/WebP |
| FAC012 | warning | components without artwork |
| FAC013 | error | artwork file missing / unsafe path |
| FAC015 | error | rig has no components |
| FAC016 | error | asset tagged for another character |
| FAC017 | warning | `face.yaml` present but not referenced |
| EXP001 | error | custom expression file invalid |
| EXP002 | error / warning | unknown component or control (warning for generic built-ins) |
| EXP003 | warning | value outside limits (clamped) |
| EXP004 | error / warning | unknown shape |
| EXP005 | error | custom id clashes with a built-in |
| EXP007 | error | expression bound to another rig |
| EXP008 | error | expression id differs from its file name |
| EXP009 | error | custom expression marked `builtin` |
| BLD002 | warning | blend weight clamped |
| LIP001 | error | zero or negative duration |
| LIP002 | error | overlaps the previous event |
| LIP003 | error | events not in time order |
| LIP004 | error | negative or non-finite timestamp |
| LIP005 | warning | unknown phoneme (map policy applied) |
| LIP006 | error | viseme not in the viseme set |
| LIP008 | error | alignment has no phonemes |
| LIP009 | error | map points to an unknown viseme |
| LIP010 | error | track's viseme set differs from the one supplied |
| LIP011 | error | events extend beyond the track duration |

## Diagnostics

Previews are schematic SVG drawings of control values. They show:
- eye outlines with lids and pupils;
- brow curves;
- the mouth outline with corners, teeth and tongue markers;
- the jaw, cheeks and nose;
- the control locations;
- every control that differs from neutral.

A multi-panel sheet of sampled times is titled "sampled facial states (stills, not
continuous animation)". The previews are inspection aids, not artwork and not proof of
animation. Lip-sync behaviour between frames is verified numerically by the tests
(continuity at boundaries, monotonic transitions, coarticulation).

Examples (generated with the commands above): `docs/examples/chr_mira-vale/face.yaml`,
`face-expressions.svg`, `hello.alignment.json`, `hello.lipsync.yaml`,
`face-lipsync-hello.svg`. The example alignment is **hand-timed**, not measured from audio.

## Known limitations

- No speech recognition, forced alignment or TTS. Real phoneme timings must come from an
  external tool or a future local provider.
- Facial controls are evaluated to values and geometry. Deforming and rendering the
  character's facial *artwork* comes with the renderer (later milestones).
- Mouth replacement drawings are selected by shape ID. Blending between two drawings is
  a switch at 50 %, not a morph.
- Phoneme maps are practical approximations for animation, not linguistic analysis.
  Only English ARPAbet and a small IPA table ship.
- Coarticulation is a single look-ahead blend, not a full articulatory model.
- Expression transitions are a single A→B interface. Layering, keyframes and timelines
  belong to the animation milestone.
