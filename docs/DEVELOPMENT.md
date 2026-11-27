# Development Guide

## Environment

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12 or 3.13 | Developed on 3.13.18; CI tests both |
| uv | ≥ 0.5 | Dependency and environment manager (`uv.lock` is committed) |
| FFmpeg | any recent | Not needed until rendering (Milestone 7); `studio doctor` reports it |
| GPU | **not required** | Nothing in the project needs one |

Measured Claude Code Cloud VM (Milestone 1): Ubuntu 24.04.5, 4 vCPU, ~15 GiB RAM, no GPU,
no Docker daemon, ephemeral disk. Push work often: the container is reclaimed after
inactivity.

## Install

```bash
uv sync                 # core + dev tools (pydantic, PyYAML, pytest, ruff, mypy)
uv run studio version
```

Optional rendering backend (needed from Milestone 3):

```bash
sudo apt-get install -y libegl1   # skia-python wheels load libEGL.so.1 even for CPU rendering
uv sync --extra render            # skia-python + numpy
uv run pytest -m render
```

Without `uv`: `python -m venv .venv && .venv/bin/pip install -e .` (then install pytest,
ruff and mypy yourself). `uv` is preferred because `uv.lock` pins exact versions.

## Everyday commands

```bash
uv run ruff check .            # lint
uv run ruff format .           # format (CI runs --check)
uv run mypy                    # strict type check of studio/
uv run pytest                  # all tests (render tests skip without the extra)
uv run pytest tests/unit -q    # unit tests only
uv build                       # build sdist + wheel into dist/
```

Run everything CI runs: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`.

## CLI

```bash
uv run studio --help
uv run studio new demo                         # creates projects/demo
uv run studio project validate projects/demo
uv run studio project info projects/demo [--json]
uv run studio asset register projects/demo art/head.svg --name "Hero head" --category character --license proprietary
uv run studio asset add-version projects/demo ast_… art/head_v2.svg --note "bigger eyes"
uv run studio asset list projects/demo [--category character] [--json]
uv run studio asset validate projects/demo
uv run studio providers list [--project projects/demo] [--json]
uv run studio modules
uv run studio doctor
uv run studio config validate | show
uv run studio schema export [name]
```

Global options: `--config-dir DIR` (default: auto-detect `config/`, or `$STUDIO_CONFIG_DIR`)
and `-v` for debug logging. Exit codes: `0` ok, `1` validation failure or error, `2` usage.

## Testing rules

- Tests never touch the network: `tests/conftest.py` blocks sockets for every test.
- Providers in tests are `none` or `mock`. No model weights, no API keys.
- Fixtures are generated at runtime (`samples` fixture); binary fixtures are not committed.
- `tests/golden/` will hold reference frames from Milestone 3 onwards.
- New code needs tests. A bug fix needs a test that fails before the fix.

## CI (`.github/workflows/ci.yml`)

Runs on every push and pull request, on `ubuntu-24.04`:

1. **test** (matrix Python 3.12, 3.13): `uv sync --locked`, ruff lint, ruff format check,
   mypy strict, pytest, CLI smoke test (creates and validates a project, validates
   `projects/demo`), `uv build`, and installs the built wheel into a clean venv and runs it.
2. **render-extra** (Python 3.13): installs `libegl1` and the `render` extra, then runs the
   skia CPU smoke tests and `studio doctor`.

No GPU, Docker, paid API or model download is involved.

## Conventions

- Python ≥ 3.12 syntax, `from __future__ import annotations`, full type hints (mypy strict).
- Ruff line length 100; formatting by `ruff format`.
- Expected failures raise subclasses of `StudioError`, which the CLI prints without a traceback.
- Paths stored in data are relative POSIX paths validated by `studio.core.paths`.
- Data documents are pydantic models with `schema_version` and `extra="forbid"`.
- Writes are atomic (`write_text_atomic`). Assets are never overwritten or deleted.
- Record architectural decisions as ADRs in `docs/DECISIONS/`.
