# CLAUDE.md: working rules for Motion Animation Studio

## Project purpose
An independent, AI-assisted 2D animation production studio. Characters are **original**
and animated with **editable, deterministic 2D rigs** (bones, IK, deformers, face rigs,
lip-sync). AI is an optional helper behind replaceable providers.

## Architecture rules (approved; do not change without the owner's approval)
- Rig-first, data-driven engine: Python, SVG parts, YAML/JSON data, skia CPU rendering, FFmpeg.
- Character animation must never be static images panned by a camera, slideshows,
  per-frame AI-generated images, or a fixed set of uneditable poses.
- Blender is never a mandatory dependency. Paid services are never required.
- Every AI capability goes through `studio.providers` and defaults to `none`.
- The core must run without a GPU. CI must not download models.
- Read `docs/ARCHITECTURE.md`, `docs/MODULES.md` and `docs/DECISIONS/` before structural work.

## Milestone workflow
- Work on **one milestone at a time**. Implement only the current milestone's scope.
- At the end of a milestone: run every check, push, report results truthfully (including
  anything incomplete), then **stop and wait for the owner's explicit approval** before
  starting the next milestone.
- Never claim success from an untested assumption. Show the commands and their output.
- Current milestone: **2 (Foundation)**, complete pending approval. Next: 3 (character core: creation + FK rig).

## Commands
```bash
uv sync                                    # install (add --extra render for skia; needs libegl1)
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest                              # tests block network access
uv run studio --help
uv run studio project validate projects/demo
```

## Coding conventions
- Python ≥ 3.12, `from __future__ import annotations`, full type hints (mypy strict), ruff (line 100).
- Data documents are pydantic models with `schema_version` and `extra="forbid"`.
- Expected errors raise `StudioError` subclasses. The CLI prints them without tracebacks.
- Stored paths are relative POSIX paths, validated with `studio.core.paths`.
- Never overwrite or delete assets. Write files atomically.
- Every new behaviour gets tests. Placeholder module packages stay code-free until their milestone.

## Safety rules
- **No unapproved paid services, subscriptions or API keys.** Never put secrets in config or git.
- **No new network permissions** (environment allowlists, `allow_network: true`) without the
  owner's explicit approval. Never try to bypass network restrictions.
- Do not download large models. Do not install Blender.
- Keep renders, caches, model weights, videos and unapproved binaries out of git.
- Never commit third-party reference media. The repository is public.

## Git rules
- Never force-push, rewrite published history, or delete branches.
- Preserve the legacy branches `ccr-f3c28d1b-6ialqh` and `ccr-5cb67ed4-c3se5u`. Never merge
  them wholesale. Follow `docs/LEGACY_REUSE.md` and ADR 0005 when adapting a component.
- Focused commits with clear messages. Push only to the assigned working branch.
- Do not open pull requests unless the owner asks.
