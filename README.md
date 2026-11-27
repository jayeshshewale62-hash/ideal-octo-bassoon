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

## Status: Milestone 3 (Characters, Consistency & 2D Rigging)

| Implemented | Partial | Not yet (later milestones) |
|---|---|---|
| M2 foundation: config, schemas, Asset & Project Manager, providers (`none`/`mock`), CLI, CI | Consistency checks are **metadata only** (no image analysis) | Facial expressions, visemes, lip-sync (M4) |
| Character definitions, templates (`biped`, `biped-minimal`), versions | Deformers (mesh/warp), part swaps, line boil: **data fields only** | Walk/run cycles, animation timeline (M5) |
| Part hierarchy, transforms, pivots, visibility, opacity, draw order | | Scenes, camera, storyboards, rendering (M6–M7) |
| Rig: bones, FK, joint limits, analytic two-bone IK | | Real AI image/voice generation, Blender, GPU |
| Turnarounds (5 views) under one identity; diagnostic SVG previews | | Any character artwork: none is generated |

Details: [docs/CHARACTERS.md](docs/CHARACTERS.md) and [docs/RIGGING.md](docs/RIGGING.md).

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

- No animation over time, video rendering or AI generation exists yet. Characters can be
  posed (FK/IK) and inspected, but not animated.
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
