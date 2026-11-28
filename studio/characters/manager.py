"""Character store: create, load, version and edit characters inside a project.

Layout per character (editable text, safe to commit)::

    characters/<character-id>/character.yaml     CharacterDefinition
    characters/<character-id>/rig.yaml           RigDefinition
    characters/<character-id>/history/character.v<N>.yaml   previous versions (never overwritten)
    characters/<character-id>/history/rig.v<N>.yaml

Artwork is never stored here; parts and views reference registered assets by ID.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from studio import __version__
from studio.characters.schemas import (
    CHARACTER_ID,
    CharacterDefinition,
    CharacterProvenance,
    IdentityProfile,
)
from studio.characters.templates import get_template
from studio.characters.validation import (
    ART_FORMATS,
    CHARACTER_FILE,
    CHARACTERS_DIR,
    HISTORY_DIR,
    PART_ART_FORMATS,
    RIG_FILE,
    validate_character_dir,
)
from studio.core.exceptions import (
    CharacterError,
    CharacterExistsError,
    ConfigError,
    InvalidAssetError,
    SchemaValidationError,
)
from studio.core.paths import slugify
from studio.core.project import Project
from studio.core.registry import AssetRegistry
from studio.core.schemas import (
    AssetLicense,
    AssetSource,
    CharacterProportions,
    CharacterStatus,
    SourceKind,
    TurnaroundView,
    utc_now,
)
from studio.core.validation import ValidationReport, load_model, model_to_yaml, write_text_atomic
from studio.rig.schemas import RigDefinition

_ID = re.compile(CHARACTER_ID)


def character_id_for(name: str) -> str:
    slug = slugify(name, max_length=40)
    if len(slug) < 2:
        raise CharacterError(f"cannot derive a character id from {name!r}; pass --id chr_<name>")
    return f"chr_{slug}"


@dataclass
class LoadedCharacter:
    character: CharacterDefinition
    rig: RigDefinition | None
    folder: Path


class CharacterStore:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.base = project.root / CHARACTERS_DIR

    # --- paths ---------------------------------------------------------------------------

    def folder(self, character_id: str) -> Path:
        if not _ID.match(character_id):
            raise CharacterError(
                f"invalid character id {character_id!r}: expected chr_ followed by lower-case "
                "letters, digits, '-' or '_'"
            )
        return self.base / character_id

    def ids(self) -> list[str]:
        if not self.base.is_dir():
            return []
        return sorted(p.name for p in self.base.iterdir() if (p / CHARACTER_FILE).is_file())

    # --- load ----------------------------------------------------------------------------

    def load(self, character_id: str) -> LoadedCharacter:
        folder = self.folder(character_id)
        path = folder / CHARACTER_FILE
        if not path.is_file():
            known = ", ".join(self.ids()) or "none"
            raise CharacterError(
                f"no character {character_id!r} in this project (characters: {known})"
            )
        character = load_model(CharacterDefinition, path)
        rig = None
        if character.rig is not None:
            rig_path = folder / RIG_FILE
            if not rig_path.is_file():
                raise CharacterError(f"{character_id}: {RIG_FILE} is missing")
            rig = load_model(RigDefinition, rig_path)
        return LoadedCharacter(character, rig, folder)

    def load_version(self, character_id: str, version: int) -> CharacterDefinition:
        current = self.load(character_id).character
        if version == current.version:
            return current
        path = self.folder(character_id) / HISTORY_DIR / f"character.v{version}.yaml"
        if not path.is_file():
            raise CharacterError(f"{character_id} has no saved version {version}")
        return load_model(CharacterDefinition, path)

    # --- create --------------------------------------------------------------------------

    def create(
        self,
        name: str,
        *,
        template: str = "biped",
        character_id: str | None = None,
        description: str = "",
        height_heads: float = 5.0,
        height_units: float = 1000.0,
        from_character: str | None = None,
    ) -> LoadedCharacter:
        cid = character_id or character_id_for(name)
        folder = self.folder(cid)
        if folder.exists():
            raise CharacterExistsError(f"character {cid!r} already exists; nothing was changed")
        now = utc_now()
        provenance = CharacterProvenance(
            source=AssetSource(kind=SourceKind.ORIGINAL),
            license=AssetLicense(spdx="proprietary"),
            created_at=now,
            updated_at=now,
            studio_version=__version__,
        )
        if from_character is not None:
            character, rig = self._from_existing(from_character, cid, name, description, provenance)
        else:
            identity = IdentityProfile(
                height_units=height_units,
                proportions=CharacterProportions(height_heads=height_heads),
            )
            built = get_template(template).build(cid, identity)
            rig = built.rig
            character = CharacterDefinition(
                id=cid,
                name=name,
                description=description,
                project_id=self.project.id,
                template=template,
                identity=identity,
                parts=built.parts,
                turnaround=built.turnaround,
                rig=rig.id,
                provenance=provenance,
            )
        folder.mkdir(parents=True)
        write_text_atomic(folder / RIG_FILE, model_to_yaml(rig))
        write_text_atomic(folder / CHARACTER_FILE, model_to_yaml(character))
        self.project.touch()
        return LoadedCharacter(character, rig, folder)

    def _from_existing(
        self,
        source_id: str,
        cid: str,
        name: str,
        description: str,
        provenance: CharacterProvenance,
    ) -> tuple[CharacterDefinition, RigDefinition]:
        """Reuse another character's structure. Artwork references are *not* copied."""
        src = self.load(source_id)
        if src.rig is None:
            raise CharacterError(f"{source_id} has no rig to reuse")
        rig = src.rig.model_copy(
            update={
                "id": "rig_" + cid.removeprefix("chr_").replace("-", "_"),
                "character_id": cid,
                "version": 1,
                "notes": f"Structure reused from {source_id} v{src.character.version}.",
            }
        )
        parts = [p.model_copy(update={"asset": None}) for p in src.character.parts]
        views = [
            v.model_copy(update={"artwork": None, "part_assets": {}})
            for v in src.character.turnaround.views
        ]
        character = src.character.model_copy(
            update={
                "id": cid,
                "name": name,
                "description": description,
                "version": 1,
                "status": CharacterStatus.CONCEPT,
                "template": f"from:{source_id}",
                "parts": parts,
                "turnaround": src.character.turnaround.model_copy(update={"views": views}),
                "rig": rig.id,
                "face": None,  # facial rigs are per character; create one with 'studio face create'
                "model_sheet_asset": None,
                "provenance": provenance,
            },
            deep=True,
        )
        return CharacterDefinition.model_validate(
            character.model_dump()
        ), RigDefinition.model_validate(rig.model_dump())

    # --- save with version history -----------------------------------------------------

    def save(
        self, character: CharacterDefinition, rig: RigDefinition | None = None
    ) -> CharacterDefinition:
        """Save an edited character. The previous version is kept in history/ and the
        version number increases. Saving identical content changes nothing."""
        folder = self.folder(character.id)
        path = folder / CHARACTER_FILE
        if not path.is_file():
            raise CharacterError(f"{character.id} does not exist; create it first")
        current = load_model(CharacterDefinition, path)
        if character.version != current.version:
            raise CharacterError(
                f"{character.id} was edited elsewhere (file is v{current.version}, "
                f"edit is based on v{character.version}); reload and try again"
            )
        if rig is not None:
            self._save_rig(folder, rig)
        comparable = character.model_copy(update={"provenance": current.provenance})
        if comparable == current:
            return current
        self._snapshot(folder, f"character.v{current.version}.yaml", model_to_yaml(current))
        updated = character.model_copy(
            update={
                "version": current.version + 1,
                "provenance": character.provenance.model_copy(update={"updated_at": utc_now()}),
            }
        )
        updated = CharacterDefinition.model_validate(updated.model_dump())
        write_text_atomic(path, model_to_yaml(updated))
        self.project.touch()
        return updated

    def _save_rig(self, folder: Path, rig: RigDefinition) -> None:
        path = folder / RIG_FILE
        current = load_model(RigDefinition, path) if path.is_file() else None
        if current is not None and current == rig:
            return
        if current is not None:
            if rig.version != current.version:
                raise CharacterError("rig was edited elsewhere; reload and try again")
            self._snapshot(folder, f"rig.v{current.version}.yaml", model_to_yaml(current))
            rig = rig.model_copy(update={"version": current.version + 1})
        write_text_atomic(path, model_to_yaml(rig))

    @staticmethod
    def _snapshot(folder: Path, name: str, text: str) -> None:
        target = folder / HISTORY_DIR / name
        if target.exists():
            if target.read_text(encoding="utf-8") == text:
                return
            raise CharacterError(f"history file {target.name} already exists with other content")
        write_text_atomic(target, text)

    # --- edits ---------------------------------------------------------------------------

    def _art_record_format(self, asset_id: str, formats: frozenset[str]) -> None:
        record = self.project.registry().get(asset_id)  # AssetNotFoundError if unknown
        if record.format not in formats:
            raise InvalidAssetError(
                f"asset {asset_id} is {record.format.upper()}; "
                f"use one of {', '.join(sorted(formats))}"
            )

    def set_part_asset(
        self, character_id: str, part_id: str, asset_id: str, view: TurnaroundView | None = None
    ) -> CharacterDefinition:
        loaded = self.load(character_id)
        char = loaded.character
        if part_id not in char.part_map():
            raise CharacterError(f"{character_id} has no part {part_id!r}")
        self._art_record_format(asset_id, PART_ART_FORMATS)
        if view is None:
            parts = [
                p.model_copy(update={"asset": asset_id}) if p.id == part_id else p
                for p in char.parts
            ]
            edited = char.model_copy(update={"parts": parts})
        else:
            views = list(char.turnaround.views)
            index = next((i for i, v in enumerate(views) if v.view == view), None)
            if index is None:
                raise CharacterError(f"{character_id} has no {view.value} view")
            v = views[index]
            views[index] = v.model_copy(
                update={"part_assets": {**v.part_assets, part_id: asset_id}}
            )
            edited = char.model_copy(
                update={"turnaround": char.turnaround.model_copy(update={"views": views})}
            )
        return self.save(CharacterDefinition.model_validate(edited.model_dump()))

    def set_view_artwork(
        self, character_id: str, view: TurnaroundView, asset_id: str
    ) -> CharacterDefinition:
        char = self.load(character_id).character
        self._art_record_format(asset_id, ART_FORMATS)
        views = list(char.turnaround.views)
        index = next((i for i, v in enumerate(views) if v.view == view), None)
        if index is None:
            raise CharacterError(f"{character_id} has no {view.value} view")
        views[index] = views[index].model_copy(update={"artwork": asset_id})
        edited = char.model_copy(
            update={"turnaround": char.turnaround.model_copy(update={"views": views})}
        )
        return self.save(CharacterDefinition.model_validate(edited.model_dump()))

    # --- validation ----------------------------------------------------------------------

    def validate(self, character_id: str) -> ValidationReport:
        folder = self.folder(character_id)
        report = ValidationReport(subject=f"{CHARACTERS_DIR}/{character_id}")
        if not (folder / CHARACTER_FILE).is_file():
            report.error(
                "CHR001", f"{CHARACTER_FILE} not found", f"{CHARACTERS_DIR}/{character_id}"
            )
            return report
        try:
            registry: AssetRegistry | None = self.project.registry()
        except (SchemaValidationError, ConfigError):
            registry = None  # every asset reference is then reported as unverifiable
        validate_character_dir(self.project.root, folder, self.project.id, registry, report)
        return report
