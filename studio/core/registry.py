"""File-based asset registry: one JSON document per project.

Storage decision (docs/DECISIONS/0003-file-based-asset-registry.md):
    ``<project>/assets/registry.json`` is a plain, diff-friendly JSON file validated by
    :class:`~studio.core.schemas.AssetRegistryFile`. It is written atomically, with
    records sorted by ID and stable formatting, so git diffs stay small. All access goes
    through :class:`AssetRegistry`, so a later move to SQLite (or a server) only replaces
    this class. Callers do not change.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from pathlib import Path

from studio.core.exceptions import AssetError, AssetNotFoundError
from studio.core.schemas import AssetRecord, AssetRegistryFile
from studio.core.validation import load_model, model_to_json, write_text_atomic


def new_asset_id() -> str:
    return "ast_" + secrets.token_hex(8)


class AssetRegistry:
    def __init__(self, path: Path, document: AssetRegistryFile) -> None:
        self.path = path
        self._doc = document
        self._by_id: dict[str, AssetRecord] = {r.id: r for r in document.assets}

    # --- persistence ---------------------------------------------------------------------

    @classmethod
    def create(cls, path: Path, project_id: str) -> AssetRegistry:
        if path.exists():
            raise AssetError(f"registry already exists: {path}")
        registry = cls(path, AssetRegistryFile(project_id=project_id))
        registry.save()
        return registry

    @classmethod
    def load(cls, path: Path) -> AssetRegistry:
        return cls(path, load_model(AssetRegistryFile, path))

    def save(self) -> None:
        self._doc.assets = sorted(self._by_id.values(), key=lambda r: r.id)
        # Re-validate the whole document before writing (unique IDs, project ownership).
        document = AssetRegistryFile.model_validate(self._doc.model_dump())
        write_text_atomic(self.path, model_to_json(document))

    # --- queries -------------------------------------------------------------------------

    @property
    def project_id(self) -> str:
        return self._doc.project_id

    def __len__(self) -> int:
        return len(self._by_id)

    def __iter__(self) -> Iterator[AssetRecord]:
        return iter(sorted(self._by_id.values(), key=lambda r: (r.category.value, r.name, r.id)))

    def __contains__(self, asset_id: object) -> bool:
        return asset_id in self._by_id

    def get(self, asset_id: str) -> AssetRecord:
        try:
            return self._by_id[asset_id]
        except KeyError:
            raise AssetNotFoundError(f"no asset with id {asset_id}") from None

    def find_by_hash(self, content_hash: str) -> AssetRecord | None:
        """The asset holding this exact content in any of its versions, if any."""
        for record in self._by_id.values():
            if any(v.content_hash == content_hash for v in record.versions):
                return record
        return None

    def find_by_path(self, path: str) -> AssetRecord | None:
        for record in self._by_id.values():
            if any(v.path == path for v in record.versions):
                return record
        return None

    def new_id(self) -> str:
        while True:
            candidate = new_asset_id()
            if candidate not in self._by_id:
                return candidate

    # --- mutation (never deletes) --------------------------------------------------------

    def add(self, record: AssetRecord) -> None:
        if record.id in self._by_id:
            raise AssetError(f"asset id {record.id} is already registered")
        if record.project_id != self.project_id:
            raise AssetError(f"asset {record.id} belongs to another project")
        self._by_id[record.id] = record

    def update(self, record: AssetRecord) -> None:
        if record.id not in self._by_id:
            raise AssetNotFoundError(f"no asset with id {record.id}")
        self._by_id[record.id] = record

    # --- dependency graph ----------------------------------------------------------------

    def missing_dependencies(self) -> list[tuple[str, str]]:
        """(asset_id, missing_dependency_id) pairs."""
        return [
            (r.id, dep)
            for r in self._by_id.values()
            for dep in r.dependencies
            if dep not in self._by_id
        ]

    def dependency_cycles(self) -> list[list[str]]:
        """Each cycle found, as a list of IDs (first ID repeated at the end)."""
        cycles: list[list[str]] = []
        state: dict[str, int] = {}  # 1 = visiting, 2 = done
        stack: list[str] = []

        def visit(node: str) -> None:
            state[node] = 1
            stack.append(node)
            for dep in self._by_id[node].dependencies:
                if dep not in self._by_id:
                    continue
                if state.get(dep) == 1:
                    cycles.append([*stack[stack.index(dep) :], dep])
                elif dep not in state:
                    visit(dep)
            stack.pop()
            state[node] = 2

        for asset_id in sorted(self._by_id):
            if asset_id not in state:
                visit(asset_id)
        return cycles

    def dependents_of(self, asset_id: str) -> list[str]:
        return sorted(r.id for r in self._by_id.values() if asset_id in r.dependencies)
