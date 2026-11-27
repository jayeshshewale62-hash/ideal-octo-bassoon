"""Path safety helpers.

All paths stored in project data are *relative POSIX paths* inside the project root.
These helpers reject absolute paths, parent-directory segments, Windows drive or
backslash forms and symlinks that resolve outside the root.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from studio.core.exceptions import PathSafetyError

_DRIVE = re.compile(r"^[A-Za-z]:")
_SLUG = re.compile(r"[^a-z0-9]+")


def check_relative_path(value: str) -> str:
    """Validate a stored relative path and return it in normalised POSIX form.

    Raises :class:`PathSafetyError` for anything that could point outside the root.
    """
    if not value or not value.strip():
        raise PathSafetyError("path is empty")
    if "\x00" in value:
        raise PathSafetyError(f"path contains a NUL byte: {value!r}")
    if "\\" in value:
        raise PathSafetyError(f"use forward slashes in stored paths: {value!r}")
    if _DRIVE.match(value) or value.startswith("/"):
        raise PathSafetyError(f"path must be relative to the project root: {value!r}")
    parts = PurePosixPath(value).parts
    if any(p == ".." for p in parts):
        raise PathSafetyError(f"path must not contain '..': {value!r}")
    normalised = PurePosixPath(*[p for p in parts if p not in (".", "")])
    if str(normalised) in ("", "."):
        raise PathSafetyError(f"path does not name a file or folder: {value!r}")
    return normalised.as_posix()


def safe_join(root: Path, relative: str) -> Path:
    """Join ``relative`` onto ``root`` and guarantee the result stays inside ``root``.

    Symlinks are resolved, so a link inside the project that points elsewhere is rejected.
    """
    rel = check_relative_path(relative)
    root_resolved = root.resolve()
    candidate = (root_resolved / rel).resolve()
    if not candidate.is_relative_to(root_resolved):
        raise PathSafetyError(f"{relative!r} resolves outside {root_resolved}")
    return candidate


def to_relative(root: Path, path: Path) -> str:
    """Return ``path`` as a POSIX path relative to ``root`` (which it must be inside)."""
    root_resolved = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise PathSafetyError(f"{path} is outside {root_resolved}")
    return resolved.relative_to(root_resolved).as_posix()


def slugify(text: str, max_length: int = 48) -> str:
    """Lower-case ASCII slug: letters, digits and single hyphens."""
    slug = _SLUG.sub("-", text.lower()).strip("-")
    return slug[:max_length].strip("-")
