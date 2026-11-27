# Rigging: Bones, FK, IK and Constraints (Milestone 3)

Package `studio.rig` (module 4). Pure Python, no rendering dependencies, deterministic.
Original implementation. No legacy code was used (see [LEGACY_REUSE.md](LEGACY_REUSE.md)).

| Capability | Status |
|---|---|
| Rig data model (`rig.yaml`): bones, rest transforms, constraints, IK chains, control handles | **implemented** |
| Forward kinematics with rotation and scale propagation, inherit flags | **implemented** |
| Joint constraints: min/max rotation, locked joints, preferred bend | **implemented** |
| Two-bone analytic IK: reach checks, bend direction, pole point, joint limits, degenerate targets | **implemented** |
| Rig validation (`RIG0xx`, `IK0xx` codes) | **implemented** |
| Mesh/warp deformers, keyed draw-order switches, replacement-part swaps | deferred (M5): parts carry metadata only |
| FK/IK blending over time, multi-bone or full-body IK | **not implemented** |
| Face rig (eyes, lids, brows, visemes) | deferred to Milestone 4 (module 5) |

## Coordinate conventions

- **Character space** = SVG/screen space: +x right, **+y down**. Templates put the top of the
  head at `y = 0`, the soles at `y = height_units` and the centre line at `x = 0`.
- **Angles** are degrees. A positive angle turns +x towards +y, so it looks **clockwise on screen**.
- **Matrices** are 2×3 affine `[a c e; b d f]` (the SVG `matrix()` layout). `A @ B` applies `B` first.
- The character's **own left** is `_l` and appears on screen right in the front view.

## Bones

```yaml
- id: forearm_l
  parent: upper_arm_l
  length: 136.8           # >= 0; zero only for the root or bones marked control: true
  rest: {x: 151.2, y: 0, rotation: 0, scale_x: 1, scale_y: 1}
  constraint: {min_rotation: 0, max_rotation: 150, locked: false, preferred_bend: positive}
  inherit_rotation: true
  inherit_scale: true
```

- A bone's local frame has its origin at the **head (joint)**. The bone points along local
  **+x**, so its tip is at `(length, 0)`.
- `rest.x`/`rest.y` place the head **in the parent's local frame**. A bone attached at its
  parent's tip uses `x = parent.length, y = 0`.
- `rest.rotation` is relative to the parent.

## Forward kinematics (`studio.rig.fk.solve_fk`)

Bones are evaluated root-first, with siblings sorted by ID, so output is deterministic:

```
local = T(x, y) · R(rotation) · S(scale_x, scale_y)      pose values override rest values
world = parent_world · local                             (both inherit flags on: exact)
```

With `inherit_rotation: false` or `inherit_scale: false`, the head position still comes
from the parent. The world matrix is rebuilt as `T(head) · R(inherited? + rotation) · S(inherited? × scale)`.
Results expose `head`, `tip`, `world_rotation`, `world_scale` and the full matrix.

**Constraints** apply to the *local* rotation before composition. A locked joint keeps its
rest rotation. Otherwise the angle is first re-expressed (`±360k`) to the representation
closest to `[min, max]`, then clamped. Every clamp is returned as a `ConstraintEvent`
(`min`/`max`/`locked`), never applied silently. A constraint with `min > max` is refused
(`RigError`) and reported by validation as `RIG008`.

## Two-bone IK (`studio.rig.ik`)

Chain: `upper → lower`. The end effector is the tip of `lower`, and `lower` must be a
direct child of `upper`.

```
d      = |target − root|, clamped to [|l1 − l2|, l1 + l2]
base   = atan2(target − root)
a_root = acos((l1² + d² − l2²) / (2·l1·d))     angle at the root joint
a_mid  = acos((l1² + l2² − d²) / (2·l1·l2))     inner angle at the middle joint
upper  = base − s·a_root                       world direction of the upper bone
lower  = upper + s·(180° − a_mid)              world direction of the lower bone
```

- **Bend sign `s`:** `positive` (+1) means the lower bone turns clockwise on screen relative
  to the upper bone. In the biped template, left elbows bend positive, right elbows and both
  knees negative.
- **Pole:** if given, the middle joint goes on the pole's side of the root→target line.
  A collinear pole falls back to the chain's `bend`.
- **Reach:**
  - `reached` when `|l1 − l2| ≤ d ≤ l1 + l2`;
  - `too_far` gives full extension towards the target;
  - `too_close` gives a fold at minimum reach along the target direction;
  - a target on the root (`d ≈ 0`) is `degenerate`: the current upper direction is kept, so
    the result is always finite.
- **World → local:** solved directions are converted into each bone's parent frame with the
  inverse parent matrix, so parent rotation (and mirrored or scaled parents) is handled.
- **Joint limits:** the solved local rotations pass through the same constraint function as
  FK. A limited solution reports `limited: true`, the clamp events and the remaining
  distance to the target (`error`). The CLI exits with code 3 when a target is not reached
  or limits were applied.

Segment lengths are taken from the actual world joint positions. A lower bone that is not
attached exactly at the upper tip still works, with a warning (`IK003`). Non-uniform scale
in a chain gives a warning (`IK008`) because rotations are no longer exact.

## Validation codes

| Code | Severity | Meaning |
|---|---|---|
| RIG000 | error | `rig.yaml` fails the schema |
| RIG001 | error | duplicate bone id |
| RIG002 | error | no bones, or root bone not defined |
| RIG003 | error | root has a parent, or a non-root bone has none |
| RIG004 | error | parent bone does not exist |
| RIG005 | error | circular parent relationship |
| RIG006 | error | bone not connected to the root |
| RIG007 | error | zero length on a non-control, non-root bone |
| RIG008 | error | `min_rotation > max_rotation` |
| RIG009 | error | rest rotation outside the joint limits |
| RIG010 | warning | locked joint also defines limits (ignored) |
| RIG011 | warning | limit range wider than 360° |
| RIG012 | error | preferred bend impossible within the limits |
| RIG013 | error | control handle duplicated or names an unknown bone |
| RIG014 | error | rest pose cannot be evaluated |
| IK001 | error | chain names an unknown bone |
| IK002 | error | lower bone is not a direct child of the upper bone |
| IK003 | warning | lower bone not attached at the upper tip |
| IK004 | error | zero-length IK segment |
| IK005 | error | duplicate chain id |
| IK006 | error | chain bend contradicts the lower joint's limits or preferred bend |
| IK007 | warning | locked joint in a chain |
| IK008 | warning | non-uniform scale in a chain |
| IK009 | error | chain references an undefined control |

## CLI

```bash
studio character rig validate projects/demo chr_mira-vale
studio character rig fk projects/demo chr_mira-vale --rot upper_arm_l=120 --rot forearm_l=200 [--parts --view side] [--json]
studio character rig ik projects/demo chr_mira-vale arm_l --target 150 400 [--pole 300 250] [--rot spine=-80] [--json]
```

Example (real output, biped template, 1000 units, 5 heads):

```
IK arm_l -> target (150, 400): reached
  rotations: {'upper_arm_l': 112.0608, 'forearm_l': 114.9888}
  root (110.0, 250.0)  mid (250.13, 306.7893)  end (150.0, 400.0)
  distance from end to target: 0.0
```
