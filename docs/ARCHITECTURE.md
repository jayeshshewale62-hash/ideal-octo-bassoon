# Architecture

**Approved architecture:** a rig-first, data-driven 2D animation engine with replaceable AI
providers and rendering backends (Milestone 1, approved for Milestone 2).

```
 DEVELOPMENT LAYER   Claude Code Cloud · GitHub · pytest · ruff · mypy · GitHub Actions
        │ code, schemas, tests
 PRODUCTION LAYER    projects/<slug>/  project.yaml · settings.yaml · story/ · storyboard/
 (data, editable)                      scenes/ · assets/registry.json · assets/<category>/
        │                                           │
 RENDERING LAYER     skia CPU renderer (core)        AI PROVIDER LAYER   image · tts · asr · llm
                     FFmpeg encode/mux               none (default) · mock · local · cloud
                     optional: Blender GP, browser   selected in config, credentials via env
                     local VM → external workers     cached by content hash
```

## Core engine (`studio/`)

One Python package. Its subpackages map onto the sixteen modules (docs/MODULES.md).
Milestone 2 implemented `studio.core` (module 16), the provider contracts and the CLI.
Milestone 3 added `studio.characters` (modules 2 and 3) and `studio.rig` (module 4): character
definitions, part hierarchies, turnarounds, identity checks, bones, FK, two-bone IK and
diagnostic SVG previews ([CHARACTERS.md](CHARACTERS.md), [RIGGING.md](RIGGING.md)). The rig
maths is pure Python and independent of rendering. Every other module package is still an
explicitly documented placeholder.

Characters will be animated by **deterministic rigs**: SVG parts bound to bones, posed
from editable curves and rendered by skia on the CPU. The same inputs and engine version
always produce the same frames, which makes golden-frame testing possible.

## Data layer

- **Text first.** Project data is YAML/JSON validated by pydantic models with an explicit
  `schema_version` and `extra="forbid"` (docs/DATA_SCHEMAS.md).
- **Configuration** lives in `config/` (studio, render profiles, providers). Each project
  has `settings.yaml` overrides.
- **Assets** are tracked in a per-project JSON registry (ADR 0003): IDs, versions, content
  hashes, provenance, licences and dependencies. Text assets (SVG, YAML, JSON) are
  committed. Binary media is git-ignored by default (ADR 0006).
- **Time** is in seconds. Frames are sampled at render time (`studio.core.timecode`), so
  24/25/30 fps or any other rate needs no data changes.

## Rendering layer (planned, Milestones 3, 7 and 10)

- **Core backend:** skia-python on the CPU. The optional `render` extra was verified on
  Python 3.13: wheel 144.1 installs, draws vector paths and renders SVG. It needs the
  system library `libEGL.so.1` (Ubuntu package `libegl1`). No GPU is used.
- **Encoding:** FFmpeg libx264, configured by render profiles (H.264 High, yuv420p, BT.709,
  AAC 48 kHz).
- **Tiers:** previews and short finals on the 4-vCPU development VM. Long films on external
  CPU workers built from the same locked environment (`render-nodes/`).
- **Optional backends:** Blender Grease Pencil (specialist shots, never a core
  dependency) and a browser/HyperFrames renderer for titles and captions only.

## Provider layer (`studio/providers/`)

Each kind (`image`, `tts`, `asr`, `llm`) has an abstract interface, a `none`
implementation (disabled, default) and a deterministic `mock`. Real providers appear in
the catalogue as *planned*, with their milestone. Selection is configuration-driven:
`config/providers.yaml`, overridden per project.

Safety rules in code:

- `allow_network: false` makes every network provider unavailable;
- credentials come only from environment variables named in `credentials_env`;
- secret-looking option names are rejected by validation;
- tests block all sockets.

## Asset management (module 16)

`Project` creates, loads and validates the standard layout. `AssetManager` registers
files (copying from outside the project, never modifying originals, never overwriting),
versions them, and validates them. Checks cover existence, hash integrity, format
sniffing, path safety including symlinks, missing dependencies, cycles, duplicates and
unregistered files. Problems are reported as coded `ValidationReport` issues (`PRJ0xx`,
`AST0xx`).

## Integration points for later milestones

| Later module | Plugs into |
|---|---|
| Face rig (5) | `studio.rig` (bones, constraints), `PartDefinition` swaps/attachments; part bindings to head bones |
| Animation (6) | `studio.rig.fk.solve_fk(rig, pose)`, `solve_ik_chain`; `BonePose` is the per-frame pose unit |
| Animation / scene (6, 9) | `scenes/` folder; `studio.core.timecode`; render profile frame rates |
| Environments (7) | `EnvironmentMetadata` schema; `environment` and `texture` categories |
| Voice / alignment (11) | `get_provider(ProviderKind.TTS / ASR, …)`; `voice` category |
| Image generation (10) | `ImageProvider`; `AIProvenance` required on `ai_generated` assets |
| Rendering (14) | `RenderProfile` models; `.cache/` and `renders/` (git-ignored); `hash_data` for cache keys |
| QC (15) | `ValidationReport` and issue codes |
