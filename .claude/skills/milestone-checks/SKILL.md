---
name: milestone-checks
description: Run every Motion Animation Studio quality gate (lint, format, types, tests, CLI smoke test, demo validation, build) and report the real results. Use before committing, before reporting a milestone as complete, or when asked "does everything pass?".
---

# Milestone checks

Run these from the repository root, in order. Report each as passed or failed, with the
actual output summary. Never report a check you did not run as passing.

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run studio config validate
uv run studio project validate projects/demo
tmp=$(mktemp -d) && uv run studio new smoke --projects-dir "$tmp" && uv run studio project validate "$tmp/smoke"
uv build
```

Optional render backend (needs the system library `libegl1`):

```bash
uv sync --locked --extra render && uv run pytest -m render
```

After pushing, check the GitHub Actions run for the pushed commit and report its real status.

Rules:
- Do not "fix" a failing check by skipping, deleting or weakening a test.
- If a check cannot run here (for example, no network), say so and why.
- Stop at the end of a milestone and wait for the owner's approval (CLAUDE.md).
