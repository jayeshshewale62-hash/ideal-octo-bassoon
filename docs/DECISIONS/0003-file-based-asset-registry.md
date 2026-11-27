# ADR 0003: File-based asset registry

**Status:** Accepted (Milestone 2)

## Context
Module 16 must register assets with IDs, versions, hashes, provenance, licences and
dependencies, and detect broken references.

## Decision
Each project stores one `assets/registry.json`, validated by `AssetRegistryFile`:

- written atomically (temporary file + rename), sorted by ID, with stable two-space
  formatting, so diffs are small and reviewable in git;
- loaded fully into memory. Lookups by ID, hash and path are linear scans, which is fine
  for thousands of assets;
- all access goes through `studio.core.registry.AssetRegistry`.

## Migration path
If a project reaches tens of thousands of assets, or several writers at once (render
farm, shared server), replace `AssetRegistry`'s storage with SQLite (stdlib `sqlite3`).
Keep the same public methods and the same pydantic records, and export to JSON for
review. No caller outside `registry.py` changes. Concurrent writers are not supported
today; the studio has one writer per project.
