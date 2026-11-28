"""Stable content hashing.

Hashes are written as ``sha256:<64 hex>``.

* Binary formats are hashed byte-for-byte.
* Text formats (SVG, JSON, YAML, TXT, MD) have CRLF/CR line endings normalised to LF
  first, so a checkout on Windows produces the same hash as one on Linux.
* :func:`hash_data` hashes JSON-compatible data canonically (sorted keys, no whitespace).
  Later milestones use it to key render and provider caches.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

PREFIX = "sha256:"
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
TEXT_SUFFIXES = frozenset({".svg", ".json", ".yaml", ".yml", ".txt", ".md", ".ass", ".srt"})
_CHUNK = 1024 * 1024


def hash_bytes(data: bytes) -> str:
    return PREFIX + hashlib.sha256(data).hexdigest()


def _normalise_newlines(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def hash_file(path: Path) -> str:
    """Content hash of a file. Text formats are newline-normalised (see module doc)."""
    if path.suffix.lower() in TEXT_SUFFIXES:
        return hash_bytes(_normalise_newlines(path.read_bytes()))
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return PREFIX + digest.hexdigest()


def hash_data(data: Any) -> str:
    """Canonical hash of JSON-compatible data (dict key order does not matter)."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hash_bytes(canonical.encode("utf-8"))


def is_valid_hash(value: str) -> bool:
    return bool(HASH_PATTERN.match(value))
