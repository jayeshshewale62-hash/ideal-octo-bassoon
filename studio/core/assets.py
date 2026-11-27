"""Asset management (module 16, part 2): registration, versioning and integrity checks.

Safety rules enforced here:

* Source files are only **read**. Files from outside the project are *copied* into the
  project's category folder, and the original is never moved or changed.
* An existing file with different content is **never overwritten** (AssetConflictError).
* Identical content cannot be registered twice unless explicitly allowed (DuplicateAssetError).
* Every stored path is relative, contains no ``..`` and resolves inside the project.
* Nothing is ever deleted. Versions only accumulate.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from studio.core.exceptions import (
    AssetConflictError,
    AssetNotFoundError,
    ConfigError,
    DuplicateAssetError,
    InvalidAssetError,
    PathSafetyError,
    SchemaValidationError,
)
from studio.core.formats import format_for, sniff
from studio.core.hashing import hash_file
from studio.core.paths import safe_join, slugify, to_relative
from studio.core.project import CATEGORY_DIRS, REGISTRY_FILE, Project
from studio.core.registry import AssetRegistry
from studio.core.schemas import (
    AIProvenance,
    AssetCategory,
    AssetLicense,
    AssetRecord,
    AssetSource,
    AssetVersion,
    utc_now,
)
from studio.core.validation import ValidationReport

LARGE_FILE_BYTES = 10 * 1024 * 1024
IGNORED_NAMES = frozenset(
    {".gitkeep", "README.md", "registry.json", "character.yaml", "environment.yaml"}
)


@dataclass(frozen=True)
class RegistrationResult:
    record: AssetRecord
    copied: bool  # True when the file was copied into the project
    destination: Path


class AssetManager:
    """Registers and versions the assets of one project."""

    def __init__(self, project: Project) -> None:
        self.project = project
        self.root = project.root
        self.registry: AssetRegistry = project.registry()

    # --- registration --------------------------------------------------------------------

    def register(
        self,
        source: Path,
        *,
        name: str,
        category: AssetCategory,
        source_info: AssetSource | None = None,
        license: AssetLicense | None = None,
        ai_provenance: AIProvenance | None = None,
        dependencies: Iterable[str] = (),
        tags: Iterable[str] = (),
        note: str = "",
        allow_duplicate: bool = False,
    ) -> RegistrationResult:
        info = sniff(self._existing_file(source))
        content_hash = hash_file(source)
        duplicate = self.registry.find_by_hash(content_hash)
        if duplicate is not None and not allow_duplicate:
            raise DuplicateAssetError(
                f"identical content is already registered as {duplicate.id} ({duplicate.name})",
                existing_id=duplicate.id,
            )
        deps = list(dict.fromkeys(dependencies))
        for dep in deps:
            if dep not in self.registry:
                raise AssetNotFoundError(f"dependency {dep} is not registered in this project")

        asset_id = self.registry.new_id()
        destination, copied = self._place(source, category, name, 1, info.name, content_hash)
        now = utc_now()
        record = AssetRecord(
            id=asset_id,
            name=name,
            category=category,
            format=info.name,
            project_id=self.project.id,
            versions=[
                AssetVersion(
                    version=1,
                    path=to_relative(self.root, destination),
                    content_hash=content_hash,
                    size_bytes=destination.stat().st_size,
                    created_at=now,
                    note=note,
                )
            ],
            source=source_info or AssetSource(),
            license=license or AssetLicense(),
            ai_provenance=ai_provenance,
            dependencies=deps,
            tags=list(dict.fromkeys(tags)),
            created_at=now,
            updated_at=now,
        )
        self.registry.add(record)
        self.registry.save()
        self.project.touch()
        return RegistrationResult(record, copied, destination)

    def add_version(self, asset_id: str, source: Path, *, note: str = "") -> RegistrationResult:
        record = self.registry.get(asset_id)
        info = sniff(self._existing_file(source))
        if info.name != record.format:
            raise InvalidAssetError(
                f"new version is {info.name.upper()} but {asset_id} is {record.format.upper()}"
            )
        content_hash = hash_file(source)
        if content_hash == record.current.content_hash:
            raise DuplicateAssetError(
                f"content is identical to version {record.current_version} of {asset_id}",
                existing_id=asset_id,
            )
        other = self.registry.find_by_hash(content_hash)
        if other is not None and other.id != asset_id:
            raise DuplicateAssetError(
                f"identical content is already registered as {other.id} ({other.name})",
                existing_id=other.id,
            )
        number = record.current_version + 1
        destination, copied = self._place(
            source, record.category, record.name, number, info.name, content_hash
        )
        now = utc_now()
        updated = record.model_copy(deep=True)
        updated.versions.append(
            AssetVersion(
                version=number,
                path=to_relative(self.root, destination),
                content_hash=content_hash,
                size_bytes=destination.stat().st_size,
                created_at=now,
                note=note,
            )
        )
        updated.updated_at = now
        updated = AssetRecord.model_validate(updated.model_dump())
        self.registry.update(updated)
        self.registry.save()
        self.project.touch()
        return RegistrationResult(updated, copied, destination)

    # --- helpers -------------------------------------------------------------------------

    @staticmethod
    def _existing_file(source: Path) -> Path:
        if not source.exists():
            raise AssetNotFoundError(f"file not found: {source}")
        if not source.is_file():
            raise InvalidAssetError(f"not a regular file: {source}")
        format_for(source)  # unsupported extension -> InvalidAssetError
        return source

    def _place(
        self,
        source: Path,
        category: AssetCategory,
        name: str,
        version: int,
        fmt: str,
        content_hash: str,
    ) -> tuple[Path, bool]:
        """Decide where the file lives; copy it in if it is outside the project."""
        resolved = source.resolve()
        if resolved.is_relative_to(self.root):
            rel = to_relative(self.root, resolved)
            safe_join(self.root, rel)
            if rel in {"project.yaml", "settings.yaml", REGISTRY_FILE}:
                raise InvalidAssetError(f"{rel} is a project control file, not an asset")
            existing = self.registry.find_by_path(rel)
            if existing is not None:
                raise AssetConflictError(f"{rel} is already registered as {existing.id}")
            return resolved, False

        stem = slugify(name) or "asset"
        rel = f"{CATEGORY_DIRS[category]}/{stem}.v{version}.{fmt}"
        destination = safe_join(self.root, rel)
        if destination.exists():
            if destination.is_file() and hash_file(destination) == content_hash:
                return destination, False
            raise AssetConflictError(
                f"{rel} already exists with different content; refusing to overwrite it"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(resolved, destination)
        return destination, True


# --- validation ----------------------------------------------------------------------------


def validate_assets(root: Path, project_id: str, report: ValidationReport) -> None:
    """Add every asset problem in the project at ``root`` to ``report``."""
    report.checks += 1
    registry_path = root / REGISTRY_FILE
    if not registry_path.is_file():
        report.error("AST001", "asset registry is missing", REGISTRY_FILE)
        return
    try:
        registry = AssetRegistry.load(registry_path)
    except (SchemaValidationError, ConfigError) as exc:
        report.error("AST002", str(exc), REGISTRY_FILE)
        return
    report.checks += 1
    if registry.project_id != project_id:
        report.error(
            "AST003",
            f"registry belongs to {registry.project_id}, project is {project_id}",
            REGISTRY_FILE,
        )

    seen_hashes: dict[str, str] = {}
    registered_paths: set[str] = set()
    for record in registry:
        for version in record.versions:
            report.checks += 1
            where = f"{record.id} v{version.version}"
            registered_paths.add(version.path)
            try:
                path = safe_join(root, version.path)
            except PathSafetyError as exc:
                report.error("AST012", str(exc), where)
                continue
            if not path.is_file():
                report.error("AST010", f"file is missing: {version.path}", where)
                continue
            actual = hash_file(path)
            if actual != version.content_hash:
                report.error(
                    "AST011",
                    f"content changed since registration ({version.path}); register a new version",
                    where,
                )
            try:
                info = sniff(path)
                if info.name != record.format:
                    report.error(
                        "AST016", f"file is {info.name}, registry says {record.format}", where
                    )
            except InvalidAssetError as exc:
                report.error("AST016", str(exc), where)
                continue
            if (
                version.content_hash in seen_hashes
                and seen_hashes[version.content_hash] != record.id
            ):
                report.warning(
                    "AST015",
                    f"same content as {seen_hashes[version.content_hash]}",
                    where,
                )
            seen_hashes.setdefault(version.content_hash, record.id)
            if (
                version is record.current
                and info.binary
                and version.size_bytes > LARGE_FILE_BYTES
                and not record.license.commit_approved
            ):
                report.warning(
                    "AST017",
                    f"large binary ({version.size_bytes // 1024 // 1024} MB) is git-ignored; "
                    "keep it in object storage",
                    where,
                )

    for asset_id, dep in registry.missing_dependencies():
        report.error("AST013", f"depends on {dep}, which is not registered", asset_id)
    for cycle in registry.dependency_cycles():
        report.error("AST014", "dependency cycle: " + " -> ".join(cycle), cycle[0])

    assets_dir = root / "assets"
    if assets_dir.is_dir():
        for path in sorted(assets_dir.rglob("*")):
            if path.is_file() and path.name not in IGNORED_NAMES:
                rel = path.relative_to(root).as_posix()
                if rel not in registered_paths:
                    report.warning("AST018", "file in assets/ is not registered", rel)
