# ADR 0001: Rig-first, data-driven 2D animation engine

**Status:** Accepted (Milestone 1 report, approved by the owner for Milestone 2)

## Context
The studio must produce real character animation (movement, rigging, expressions) on a
GPU-less cloud development VM, with optional paid services only.

## Decision
- Characters are original SVG parts bound to deterministic bone rigs, posed from editable
  curves and rendered by skia on the CPU. FFmpeg encodes the result.
- Project data is text (YAML/JSON) validated by versioned schemas.
- AI is used through replaceable providers, for concept art, background plates, voice and
  alignment. It is **never** used for per-frame character animation.
- Blender Grease Pencil and browser/HyperFrames rendering are optional specialist backends,
  never core dependencies.

## Consequences
- Deterministic output enables golden-frame tests in CI.
- The core runs without a GPU. Heavy work scales out to external workers later.
- A rig system has to be built (Milestones 3–5) instead of using a ready-made 3D tool.
