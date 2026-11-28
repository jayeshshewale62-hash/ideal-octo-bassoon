# Animation Engine (Milestone 5)

Package `studio.animation` (module 6). Deterministic, rig-driven 2D character animation in
pure Python, CPU only, offline. All motion is **editable keyframe data** evaluated through
the Milestone 3 rig and the Milestone 4 face:
- `solve_fk`, `solve_ik_chain` and `constrain_rotation` for the body;
- `solve_parts` for the part hierarchy;
- `evaluate_expression`, `blend_states`, `LipSyncEvaluator` and `apply_lipsync` for the face.

None of that mathematics is duplicated. Nothing is a slideshow, a sprite sequence or a
per-frame AI image.

| Capability | Status |
|---|---|
| Versioned clips with typed tracks (bone, IK, part, root, face, expression, deform), events, loop/playback | implemented |
| Keyframes in seconds or frames, any fps; insertion/removal with versioning | implemented |
| Curves: step, linear, smooth, ease-in/out/in-out, cubic Bézier, monotone Hermite; angle shortest-path | implemented |
| Bone (FK) animation, animated IK targets with weight/pole/end rotation, constraints reported | implemented |
| Walk and run cycles (IK feet, stance/swing/flight, bob, sway, lean, head stability, arm swing) | implemented (stylized, in place) |
| Idle: breathing, shoulder rise, torso/head motion, weight shift, seeded blinks | implemented |
| Gestures: wave, point (IK), nod | implemented |
| Secondary motion: spring-damper lag (hair, ears, cloth, tails) | implemented (single-axis rotation offsets) |
| Mesh deformation: 2D linear blend skinning + blend shapes, validation, grid generator | implemented (basic) |
| Expression tracks, facial-control keys, blinks; lip-sync integration with mouth/jaw ownership | implemented |
| Unified evaluator with layers (override/additive), masks, normalisation, diagnostics | implemented |
| Diagnostic contact sheets with timeline (keys, events, samples) | implemented |
| Timeline editor, full-body IK, physics/cloth simulation, motion capture, AI motion, video rendering | **not implemented** |

## Files

```
projects/<slug>/characters/<id>/animations/
    clips/<clip>.yaml     AnimationClip
    sets/<set>.yaml       AnimationSet (layers, lip-sync, springs, meshes)
    meshes/<mesh>.yaml    DeformMesh
characters/<id>/history/animations/<clips|sets|meshes>/<id>.v<N>.yaml   earlier versions
```

- Every edit made through the CLI or `AnimationStore.save` writes a new version, and the
  previous file goes to history. History files are never overwritten.
- Character, part and face files are never modified by animation, and neither is artwork.
  A mesh only references a part's drawing.
- Lip-sync sources are a registered asset (`--lipsync-asset`) or a project-relative path
  (`--lipsync-path`). Both are resolved with `safe_join`, so `../` escapes are refused.

## Data model

A **clip** has an `id`, `name`, `character_id`, `duration`, `fps`, `loop`, `playback`,
`tracks`, `events`, an optional `cycle` (how it was generated), `tags` and `metadata`.

| Track | Keyframe | Properties |
|---|---|---|
| `bone` | `BoneKeyframe` | `rotation`, `x`, `y`, `scale_x`, `scale_y`: absolute local values (replace the rest value while keyed) |
| `ik` | `IKKeyframe` | `x`, `y` target (character space), optional `pole_x/pole_y`, `weight` (0 = FK, 1 = IK), `end_rotation` (world angle for the bone after the chain, e.g. a flat foot) |
| `part` | `TransformKeyframe` | `x`, `y`, `rotation`, `scale_x`, `scale_y`, `visible` (stepped), `opacity` |
| `root` | `TransformKeyframe` | moves the whole rig (FK origin) |
| `face` | `ControlKeyframe` | `values: {component.control: number}` (blinks, brows ...) |
| `expression` | `ExpressionKeyframe` | `expression` id + `weight` (0 = neutral, 1 = full) |
| `deform` | `DeformationKeyframe` | `weights: {shape: number}` of a mesh's blend shapes |

- **Timing:** a keyframe has exactly one of `time` (seconds) or `frame` (an integer at the
  clip fps).
- **Compilation:** tracks compile into scalar **channels** (`domain:target.property`). A
  keyframe only keys the properties it sets.
- **Validation:** two keys for the same property at the same time (`ANM009`) and keys
  after the clip end (`ANM010`) are errors.
- **Hold:** before its first key and after its last key, a channel holds that key's
  value. A property no layer keys falls back to the rest pose or default.

## Curves

The curve of a key describes the segment from that key to the next one. With
`u = (t − tᵢ)/(tᵢ₊₁ − tᵢ)`:

| Interpolation | Formula / behaviour |
|---|---|
| `step` | value of the key until the next key (the change happens *at* the next key) |
| `linear` | `u` |
| `smooth` | `3u² − 2u³` (zero slope at both keys) |
| `ease_in` / `ease_out` | `u²` / `1 − (1 − u)²` |
| `ease_in_out` | `4u³` (u < ½), else `1 − (−2u + 2)³/2` |
| `bezier` | CSS `cubic-bezier(x1, y1, x2, y2)` timing, solved for x = u by Newton iteration with a bisection fallback. `x1, x2 ∈ [0, 1]`; `y` outside [0, 1] requires `allow_overshoot: true` |
| `hermite` | cubic Hermite with Catmull-Rom tangents × (1 − `tension`). Fritsch-Carlson limiting means **no overshoot** unless `allow_overshoot`. Looping clips use wrapped neighbours and share one tangent at the seam |

- Every curve except an overshooting Bézier or Hermite stays between its two key values.
- Rotations interpolate numerically by default (350 → 10 goes through 180). With
  `shortest_path: true` on the track, each next key is unwrapped to within ±180° of the
  previous one.
- Facial controls are clamped to their rig limits after interpolation, and every clamp is
  reported.

## Time mapping, loops and events

```
local = (t − layer.time_offset) · layer.speed · clip.playback.speed + clip.playback.offset
once      clamp to [0, duration]         (holds the first/last pose)
loop      local mod duration             (duration maps to 0, so the seam is exact)
pingpong  forwards, then backwards
```

- **Events** (`foot_contact`, `foot_lift`, `hand_contact`, `gesture_start`, `gesture_end`,
  `expression_change`, `marker`) have exact clip times.
- `events_between(clip, start, end)` returns the events in `[start, end)` of layer time. It
  repeats events on every loop and mirrors them for ping-pong.
- The evaluator reports events within an `event_window`. The CLI uses one frame.

## Evaluation order (the unified evaluator)

`CharacterAnimator(context, set).evaluate(t)` (one-off: `evaluate_character(...)`):

1. **Layers**, in ascending `(order, id)`. Each samples its clip at its mapped time.
   - `override` lerps from the value below by `weight` (angles take the shortest way).
   - `additive` adds `weight · (value − rest)`.
   - `mask` limits a layer to `full`, `upper_body` (spine and its descendants), `lower_body`
     (root and legs), `face`, `bone:<id>` (the bone and its descendants), `ik:<chain>` or
     `part:<id>`.
   - `blend.normalize` turns override layers into a weight-normalised average per property.
   - The highest layer that writes a property **owns** it (`owners` in the result).
2. **Pose:** keyed bone values replace rest values. The root track places the rig.
3. **IK:** each keyed chain (sorted by id) runs the M3 two-bone solver on the current pose.
   Its rotations are blended with FK by `weight`, and `end_rotation` sets the next bone's
   world angle.
4. **FK:** the M3 hierarchy evaluation, with joint constraints enforced. Each clamp gives
   `EVL001`.
5. **Secondary motion:** springs driven by the step-4 pose add lagging rotations to bones
   (FK is re-run) or parts.
6. **Parts:** `solve_parts` on an animated *copy* of the character (keyed part transforms,
   visibility, opacity, spring offsets).
7. **Meshes:** linear blend skinning plus blend shapes.
8. **Face:**
   - Expression tracks are evaluated and blended with the M4 functions.
   - Keyed facial controls override those controls.
   - **Lip-sync owns the mouth and jaw**: keyed `mouth.*` / `jaw.*` values are replaced and
     reported as `EVL005`. Mouth corners are added, so a smile survives speech. Eyes and
     brows keep the expression and keys.
   - Before the lip-sync `start`, the mouth belongs to the expression.
9. **Events** in the window, and each layer's **cycle phase**.

**Result** (`CharacterState`):
- `time`;
- `layers` (clip time, weight, phase);
- `pose`, `fk`, `parts`;
- `face`, `lips`, `meshes`;
- `ik` (status, error, weight);
- `owners`;
- `events`;
- `diagnostics` (`EVL001` constraint clamp, `EVL002` IK target not reached, `EVL003` IK
  limited, `EVL004` facial control clamped, `EVL005` lip-sync ownership, `EVL006` spring
  clamped, `EVL007` flipped mesh triangles, `EVL009` facial tracks without a face);
- the animated `character`.

The same inputs and time always give the same state; tests check this, including
evaluation in reverse order.

## Walk and run cycles

`studio animation cycles generate PATH CHAR walk|run [--speed S] [--stride L] [--duration T] [--samples N] [--param NAME=VALUE]`

Any two of speed, stride and duration define the third. If all three are given, they must
agree.

| Parameter | Walk default | Run default | Meaning |
|---|---|---|---|
| duration | 1.0 s | 0.7 s | one full cycle = two steps |
| stride | 1.1 × leg | 2.0 × leg | distance per cycle (character scale adapts automatically) |
| stance | 0.6 | 0.35 | fraction of the cycle each foot is planted |
| lift | 0.12 × leg | 0.32 × leg | swing-foot lift |
| bob | 0.025 × leg | 0.05 × leg | vertical hip motion |
| arm_swing / elbow | 18° / 10° | 35° / 80° | counter-swing, elbow bend |
| lean / sway | 3° / 2° | 10° / 3° | forward lean, pelvis sway |
| recovery | 0 | 0.25 × leg | run: heel pulled back early in the swing |

**Phases:**
- **Contacts:** the left foot touches down at phase 0 and the right at 0.5.
- **Stance:** the planted foot moves backward relative to the hip at constant speed.
- **Swing:** the foot moves forward on a smoothstep path and lifts on a sine.
- **Walk vs run:** walk stance > 0.5, so both feet are on the ground at times (double
  support); run stance < 0.5, so there are **flight** phases.
- **Body:** hips bob (walk lowest at contact, run lowest mid-stance), the pelvis sways,
  the spine leans, and the neck counter-rotates so the head stays level. Arms swing
  against the legs.

**How the generator drives the rig:**
- Feet are **animated IK targets** on `leg_l` and `leg_r`.
- `end_rotation` keeps each foot at its rest angle, kept within the ankle's limits.
- The generator crouches the hips just enough that every pose is reachable.
- Every baked sample is checked with the real IK solver. A lifted foot that would need
  joint clamping is pulled in (with 6 % headroom, so the curve between keys stays within
  limits too); `limit_adjusted_samples` records how often.
- A stride that puts a *planted* foot beyond the joint limits is refused with an error.

**Facing:** knees bend toward the facing side, which is taken from the leg chains' bend
sign. The biped template's knees bend negative, so its cycles face screen-left.

**Output:**
- Keys are baked at `samples` (default 20) evenly spaced phases. Contacts and lift-offs
  land exactly on keys, and the last key repeats the first.
- Foot-contact and foot-lift events are added.
- `cycle.speed` and `distance_per_cycle` are recorded. Cycles are **in place**: moving the
  character through a scene is a later milestone.

Evidence, from the tests (`tests/unit/test_animation_cycles.py`), measured through
IK → FK on 200 samples per cycle:
- zero IK error and zero diagnostics;
- the stance foot is exactly on the ground and the swing foot lifted;
- the two feet alternate half a cycle apart;
- walk has double support and no flight, run has flight and no double support;
- events coincide with contacts;
- pose continuity at t = 0 vs t = T and across T ± 10⁻⁴;
- the cycle repeats seven cycles later;
- speed and stride are consistent, and the cycle scales with the character.

This is **stylized animation, not a biomechanical simulation**.

## Idle and gestures

**`idle`** (default 4 s, loops):
- breathing scales the chest parts and raises the shoulders along the spine;
- gentle spine and neck motion;
- an optional weight shift of the root;
- `blinks` per loop on `eye_l/r.blink` (only if the character has a face).

Variation comes from a **seed** hashed with SHA-256: no global random state, and the same
seed always gives the same clip. `amount` scales every amplitude, and 0 gives a still pose.

**Gestures:**
- `wave`: the arm rises and the forearm oscillates within the elbow limits.
- `point`: an IK arm reaches a target, holds, and blends back through the IK weight.
- `nod`: the head nods.

Each gesture records `gesture_start` / `gesture_end` events.

## Secondary motion

Springs (`SpringDefinition`) make a part or bone lag behind a driver bone's world rotation
or head x/y:

```
m·x'' = k·(d − x) − c·x'
offset = clamp(gain·(x − d), ±max_displacement)   added to the target's rotation (degrees)
```

- **Integration:** semi-implicit Euler on a fixed grid (`step`, default 1/120 s). Steps are
  subdivided so that `h·√(k/m) ≤ 0.5`, which keeps it stable even for very stiff springs.
- **Determinism:** the state at time t is simulated from rest over the preceding `window`
  (default 2 s), aligned to the grid. It is therefore a pure function of t, whatever order
  frames are evaluated in. `t ≤ 0` gives the reset state.
- **Limits:** motion older than the window is forgotten. A spring gives one scalar
  rotation offset (no 2D pendulum, collisions or cloth). `--springs` adds defaults for hair
  and ears.

## Mesh deformation

`studio animation mesh create PATH CHAR MESH --part P --grid 4x2 --bones b1,b2` generates a
grid over the part's artwork bounds. Each vertex gets inverse-distance weights to the
given bones (top two, normalised).

**Deformation** (`deform_mesh`), with vertices in the part's artwork coordinates:

```
v' = v + Σ w_s·delta_s                       blend shapes (deform tracks)
p  = Σ w_b·B_b(t)·B_b(rest)⁻¹·(A_rest·v')  +  (1 − Σ w_b)·A(t)·v'
```

- Unweighted vertices follow the part rigidly.
- Flipped triangles are detected and reported (`EVL007`), not repaired.
- **Validation codes:**

  | Code | Problem |
  |---|---|
  | MSH001 | part missing |
  | MSH002 | too few vertices or no triangles |
  | MSH003 | index out of range |
  | MSH004 | degenerate triangle |
  | MSH005 | weight-list count mismatch |
  | MSH006 | weight outside [0, 1] |
  | MSH007 | weights don't sum to 1 (or 0) |
  | MSH008 | unknown bone |
  | MSH009 | shape length mismatch |
  | MSH010 | duplicate influence |
  | MSH011 | more than 4 influences (warning) |
  | MSH012 | vertex outside part bounds (warning) |
  | MSH013 | unweighted vertices (warning) |

- **Not implemented:** dual-quaternion skinning, as-rigid-as-possible warping, automatic
  triangulation of artwork outlines, and texture mapping (the renderer comes later).

## CLI

```bash
studio animation list PATH CHAR [--json]
studio animation create PATH CHAR CLIP --duration 2 [--fps 24] [--loop once|loop|pingpong]
studio animation key set PATH CHAR CLIP bone:neck --frame 12 --set rotation=10 --interp ease_in_out
studio animation key set PATH CHAR CLIP ik:arm_l --time 1 --set x=150 --set y=400 --interp bezier --bezier 0.25 0.1 0.25 1
studio animation key set PATH CHAR CLIP expression --time 0.8 --expression happy [--weight 0.8]
studio animation key set PATH CHAR CLIP face --time 1.48 --set eye_l.blink=1 [--replace]
studio animation key remove PATH CHAR CLIP bone:neck --time 0
studio animation events add|list PATH CHAR CLIP …
studio animation cycles list | generate PATH CHAR walk|run|idle|wave|point|nod [--replace]
studio animation mesh create|validate|show PATH CHAR …
studio animation set create PATH CHAR SET --layer walk --layer idle:0.5:additive:upper_body \
    --layer greet:1:override:face --lipsync-path audio/hello.lipsync.yaml --springs --mesh torso
studio animation validate PATH CHAR [ITEM]
studio animation info PATH CHAR CLIP [--json]
studio animation evaluate PATH CHAR (--clip C | --set S) (--time T … | --sample STEP [--until T]) [--json] [--parts]
studio animation preview  PATH CHAR (--clip C | --set S) --sample 0.1 [--out FILE]
studio animation blend    PATH CHAR walk run --weight 0.3 --time 0.2 [--out FILE]
```

Exit codes: `0` ok, `1` invalid input or error, `2` usage. Invalid values typed on the
command line are reported as readable `error:` lines, never as tracebacks.

## Examples (generated with the commands above)

`docs/examples/chr_mira-vale/animations/` holds:
- the clips `walk`, `run`, `idle`, `wave` and the hand-keyed `greet` (expression change,
  neck ease, a blink);
- the mesh `torso`;
- the set `performance`: walk, plus additive idle on the upper body, plus greet on the
  face, plus lip-sync, springs and the mesh.

The sheets `anim-walk.svg`, `anim-run.svg` and `anim-performance.svg` are **still
diagnostics**: they show sampled states, not animation.

Real output (`studio animation evaluate … --set performance --time 0.3`):

```
  layer l0_walk: clip walk @ 0.3000s weight 1 phase=0.300
  IK leg_l: target (60.50,968.00) reached error=0.0000 weight=1
  IK leg_r: target (-60.50,923.84) reached error=0.0000 weight=1
  face: neutral+lipsync@0.3s {'jaw.open': 0.63, 'mouth.open': 0.72, …}
  lipsync: segment l, dominant ai
  mesh torso: 12 vertices, 0 flipped
```

## Performance

- Clips compile once per animator: channels are sorted arrays with bisection lookup and
  precomputed Hermite tangents.
- The spring solver caches driver samples per grid step, so frame-by-frame evaluation
  reuses them.
- Measured on the 4-vCPU cloud VM (sequential 24 fps frames):

  | Evaluation | Time per frame |
  |---|---|
  | walk clip alone | ≈ 1.4 ms |
  | the `performance` set (3 layers, lip-sync, 3 springs, mesh) | ≈ 8.3 ms |

  Springs dominate the cost the first time a stretch of time is evaluated. Rendering is
  not part of the evaluator.

## Known limitations

- Cycles are in place and stylized. There is no foot roll or toe break, no terrain
  adaptation and no turning on the spot. Root travel is recorded, not applied.
- The biped template is front-view geometry used for side-view locomotion. Its elbows bend
  in opposite directions, so arm poses are asymmetric.
- Layers blend per channel. There is no animation graph, state machine or transition
  editor, and additive layers are relative to the rig's rest pose.
- Springs are single-axis lag and the window forgets older motion.
- Meshes use linear blend skinning only.
- There is no timeline editor, video rendering, motion capture, physics or AI motion.
