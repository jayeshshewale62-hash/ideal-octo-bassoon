# Motion Animation Studio

*(repository: `ideal-octo-bassoon`. Original description: "For long")*

Motion Animation Studio is an independent, AI-assisted **2D animation production
system** for short videos and long-form animated films. It is designed for real character
animation: original characters with bone rigs, facial expressions and lip-sync, animated
from editable data and rendered deterministically. It does not just move still images
around.

## Approved architecture

A **rig-first, data-driven 2D animation engine with replaceable AI providers and
rendering backends** ([docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)):

- **Python** application. **SVG** character artwork. **PNG/layered** environments.
  **YAML/JSON** project data with versioned schemas.
- **skia** CPU vector rendering (core backend) and **FFmpeg** for encoding and assembly.
  **No GPU required.**
- **AI providers** (image, voice, alignment, language model) sit behind interfaces. They
  are disabled by default, with mocks for tests. Paid services are never required.
- Optional specialist backends later: Blender Grease Pencil, browser/HyperFrames (titles only).
- Sixteen modules, from Story Development to the Asset & Project Manager ([docs/MODULES.md](docs/MODULES.md)).

## Status: Milestone 4 (Facial Expressions, Visemes & Lip-Sync Foundation)

| Implemented | Partial / interface only | Not yet (later milestones) |
|---|---|---|
| M2 foundation: config, schemas, Asset & Project Manager, providers, CLI, CI | Consistency checks are **metadata only** | Body animation cycles, timelines (M5) |
| M3 characters: templates, parts, rig, FK, two-bone IK, turnarounds | Deformers and part swaps: **data fields only** | Scenes, camera, storyboards, rendering (M6–M7) |
| M4 faces: facial rigs, eye/brow/mouth/jaw controls, 12 + custom expressions, blending | Audio alignment: **provider interface only** (`none`/`mock`); no ASR or forced alignment | Speech recognition, TTS, real AI generation |
| M4 visemes, phoneme maps, timestamp lip-sync with transitions and coarticulation | Facial artwork is referenced, not deformed or rendered yet | Any generated artwork: none is created |

Details: [docs/CHARACTERS.md](docs/CHARACTERS.md), [docs/RIGGING.md](docs/RIGGING.md),
[docs/FACE.md](docs/FACE.md).

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/jayeshshewale62-hash/ideal-octo-bassoon.git
cd ideal-octo-bassoon
uv sync
uv run studio version
```

## Quick start

```bash
uv run studio new my-film --title "My Film"      # create projects/my-film
uv run studio project validate projects/my-film
uv run studio asset register projects/my-film ~/art/head.svg \
    --name "Hero head" --category character --license proprietary
uv run studio asset list projects/my-film
uv run studio providers list

# characters and rigs (Milestone 3)
uv run studio character create projects/my-film "Mira Vale"
uv run studio character validate projects/my-film
uv run studio character rig fk projects/my-film chr_mira-vale --rot upper_arm_l=120
uv run studio character rig ik projects/my-film chr_mira-vale arm_l --target 150 400
uv run studio character preview projects/my-film chr_mira-vale --view side --ik arm_l 150 400

# faces and lip-sync (Milestone 4)
uv run studio face create projects/my-film chr_mira-vale
uv run studio face expressions blend projects/my-film chr_mira-vale neutral happy --weight 0.5
uv run studio face phonemes map docs/examples/chr_mira-vale/hello.alignment.json --out hello.lipsync.yaml
uv run studio face lipsync evaluate hello.lipsync.yaml --time 0.3
uv run studio face lipsync preview projects/my-film chr_mira-vale hello.lipsync.yaml --sample 0.1
```

## CLI overview

| Command | Purpose |
|---|---|
| `studio new NAME` | create a project with the standard layout, metadata, registry and placeholders |
| `studio project validate PATH` / `info PATH` | check a project / show its metadata |
| `studio asset register PATH FILE` / `add-version` | register files (copied in, never overwritten) and new versions |
| `studio asset list PATH` / `validate PATH` | list assets / verify files, hashes, references |
| `studio providers list` | selected providers and the provider catalogue |
| `studio character templates` / `create` / `list` / `info` / `validate` | create and inspect characters (structure + rig; no artwork) |
| `studio character set-part-asset` / `set-view-artwork` | attach registered artwork (new character version) |
| `studio character compare --version N` / `--with ID` | identity-metadata comparison |
| `studio character rig validate` / `fk` / `ik` | rig checks, forward kinematics, two-bone IK |
| `studio character turnaround validate` | turnaround views and identity overrides |
| `studio character preview` | diagnostic SVG (structure only, not artwork or animation) |
| `studio face create` / `info` / `validate` / `set-asset` | facial rig for a character (controls; no artwork generated) |
| `studio face expressions list` / `create` / `set` / `preview` / `blend` | built-in and custom expressions, deterministic blending |
| `studio face visemes list`, `studio face phonemes maps` / `map` | viseme set, phoneme maps, phoneme → viseme tracks |
| `studio face lipsync validate` / `evaluate` / `preview` | timestamp lip-sync evaluation and sampled diagnostics |
| `studio face alignment inspect` / `run` | alignment files; provider-based alignment (disabled by default) |
| `studio modules` | the sixteen modules and their status |
| `studio doctor` | check this machine (Python, FFmpeg, optional skia) |
| `studio config validate` / `show` | validate / print configuration |
| `studio schema export [NAME]` | JSON Schema of the data documents |
| `studio version` | version, milestone and config source |

Add `--json` to most commands for machine-readable output.

## Repository layout

```
config/        studio.yaml · render_profiles.yaml · providers.yaml
studio/        Python package: core/ (module 16), providers/, cli.py, module packages
projects/      one folder per film (projects/demo was created with `studio new demo`)
assets/        shared studio asset library (characters, environments, props, fonts, sfx)
tests/         unit/ · integration/ · fixtures/ · golden/
docs/          ARCHITECTURE · MODULES · DATA_SCHEMAS · DEVELOPMENT · LEGACY_REUSE · DECISIONS/
legacy/        index of reusable material in two legacy branches (no copied code)
render-nodes/  future external render workers
.claude/       Claude Code skills; CLAUDE.md holds the working rules
```

## Current limitations

- No animation timeline, video rendering or AI generation exists yet. Characters can be
  posed (FK/IK) and faces evaluated at any time (expressions, lip-sync), but nothing is
  rendered as video.
- Lip-sync needs phoneme timestamps from an alignment file. No speech recognition or
  forced alignment is included, and the `mock` aligner gives word timings only.
- No character artwork is generated: parts reference artwork you register.
- Consistency checks compare metadata, not images. Deformers are not evaluated yet.
- The rendering extra (`uv sync --extra render`) needs the system library `libegl1` on Linux.
- Binary media (PNG, WAV, …) is git-ignored by default. Object storage arrives in a later milestone.
- Two reference files from the planning phase (a short video and a PDF guide) are not in the
  repository. They must be shared privately; third-party video is never committed here.

## Development

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). In short:
`uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`.

## Licence

No open-source licence has been chosen yet: all rights reserved by the repository owner.
Third-party material keeps its own licence (see `docs/LEGACY_REUSE.md`).
