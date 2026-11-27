# ADR 0002: Python 3.12+/3.13, uv, minimal dependencies

**Status:** Accepted (Milestone 2)

## Decision
- `requires-python >= 3.12`. Developed on 3.13.18 (the cloud VM), and CI tests 3.12 and 3.13.
  **No downgrade was needed:** every dependency publishes wheels for CPython 3.13 on
  Linux x86_64. Checked on PyPI in Milestone 2: pydantic 2.14, PyYAML 6.0.x, skia-python
  144.1 (cp313), numpy 2.5, sherpa-onnx 2.0.3 (cp313), scipy 1.18 (cp313), bpy 5.3 (cp313 only).
- uv manages the environment, and `uv.lock` is committed for reproducible CI.
- Core runtime dependencies are only **pydantic** (schemas and validation errors) and
  **PyYAML** (`safe_load`). The CLI uses the standard library's `argparse`.
- skia-python and numpy are the optional `render` extra. They are not needed until
  Milestone 3, and skia needs the system library `libEGL.so.1` (Ubuntu `libegl1`).
  This was verified in the dev VM: without it the import fails; with it, CPU rendering of
  paths and SVG works.
- Dev tools: pytest, ruff, mypy (strict, pydantic plugin), types-PyYAML.

## Rejected
- click/typer for the CLI: an extra dependency with no real benefit at this size.
- jsonschema: pydantic already produces JSON Schema and readable errors.
- Pinning Python 3.12: unnecessary, since 3.13 works.
