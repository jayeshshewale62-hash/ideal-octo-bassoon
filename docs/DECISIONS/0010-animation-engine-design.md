# ADR 0010: Animation engine design

**Status:** Accepted (Milestone 5)

## Decisions
- **Reuse, don't fork.** The evaluator calls `solve_fk`, `solve_ik_chain`,
  `constrain_rotation`, `solve_parts`, `evaluate_expression`, `blend_states`,
  `LipSyncEvaluator` and `apply_lipsync`. No rig or face maths is duplicated.
- **Typed tracks, scalar channels.** Authors write typed keyframes per target (bone, IK,
  part, root, face, expression, deform). These compile into scalar channels so a single
  curve engine serves everything. Keys hold absolute local values, which match the
  M3 `BonePose`.
- **Curves.** The key's curve applies to the segment that follows it. Hermite tangents are
  monotone-limited by default, so bounded controls never overshoot unexpectedly.
  Overshoot must be opted into.
- **Generated cycles are baked keyframes.** Walk/run/idle/gestures are computed
  analytically, then stored as ordinary editable clips with loop-exact seams. Feet use
  animated IK targets. Baked samples are validated against the rig's joint limits with the
  real IK solver, and impossible strides are refused rather than producing clamped
  cycles.
- **Layers.** Per-channel override/additive blending with masks from the bone hierarchy,
  optional weight normalisation, and an `owners` map for conflict transparency. Lip-sync
  owns mouth and jaw controls.
- **Secondary motion** is a spring-damper on a fixed grid with a warm-up window, so a
  frame's result depends only on its time (order-independent and reproducible).
- **Meshes** use 2D linear blend skinning against the rest pose plus blend shapes. The
  artwork is referenced, never modified.
- **Storage** follows ADR 0008: per-character YAML with version history. Lip-sync sources
  are assets or project-relative paths resolved with `safe_join`.
- **Originality.** All Milestone 5 code is original. Legacy Branch A is not used (ADR 0005).
