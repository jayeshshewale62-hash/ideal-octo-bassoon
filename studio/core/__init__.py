"""Core infrastructure: configuration, schemas, hashing, validation and the
Asset & Project Manager (module 16).

Everything in ``studio.core`` is dependency-light (pydantic + PyYAML), needs no GPU and
makes no network requests.
"""

from __future__ import annotations
