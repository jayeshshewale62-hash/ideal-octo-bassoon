"""Animation storage: clips, sets and meshes per character, versioned like characters.

    characters/<id>/animations/clips/<clip>.yaml
    characters/<id>/animations/sets/<set>.yaml
    characters/<id>/animations/meshes/<mesh>.yaml
    characters/<id>/history/animations/<kind>/<id>.v<N>.yaml   (never overwritten)

Lip-sync sources are a registered asset (YAML/JSON lip-sync track) or a project-relative
path. Both are resolved with ``safe_join``, so no path can escape the project. Artwork is
never written.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from studio.animation.evaluator import AnimationContext
from studio.animation.schemas import AnimationClip, AnimationSet, DeformMesh
from studio.animation.validation import ANIM_DIR, CLIPS_DIR, MESHES_DIR, SETS_DIR
from studio.characters.manager import CharacterStore
from studio.characters.schemas import CharacterDefinition
from studio.core.exceptions import (
    AnimationError,
    AssetNotFoundError,
    ConfigError,
    FaceError,
    SchemaValidationError,
)
from studio.core.paths import check_relative_path, safe_join
from studio.core.project import Project
from studio.core.registry import AssetRegistry
from studio.core.validation import load_model, model_to_yaml, write_text_atomic
from studio.face.library import builtin_expressions, load_viseme_set
from studio.face.schemas import FacialExpression, FacialRig, LipSyncTrack, VisemeSet
from studio.rig.schemas import RigDefinition

M = TypeVar("M", AnimationClip, AnimationSet, DeformMesh)
KIND_DIRS: dict[type[BaseModel], str] = {
    AnimationClip: CLIPS_DIR,
    AnimationSet: SETS_DIR,
    DeformMesh: MESHES_DIR,
}


class AnimationStore:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.characters = CharacterStore(project)

    def _dir(self, character_id: str, model: type[BaseModel]) -> Path:
        return self.characters.folder(character_id) / ANIM_DIR / KIND_DIRS[model]

    def path(self, character_id: str, model: type[BaseModel], item_id: str) -> Path:
        check_relative_path(item_id)
        if "/" in item_id or not item_id.replace("_", "a").isalnum() or not item_id[0].isalpha():
            raise AnimationError(f"invalid id {item_id!r}")
        return self._dir(character_id, model) / f"{item_id}.yaml"

    def ids(self, character_id: str, model: type[BaseModel]) -> list[str]:
        folder = self._dir(character_id, model)
        return sorted(p.stem for p in folder.glob("*.yaml")) if folder.is_dir() else []

    def load(self, character_id: str, model: type[M], item_id: str) -> M:
        path = self.path(character_id, model, item_id)
        if not path.is_file():
            known = ", ".join(self.ids(character_id, model)) or "none"
            raise AnimationError(
                f"no {KIND_DIRS[model][:-1]} {item_id!r} for {character_id} (known: {known})"
            )
        return load_model(model, path)

    def create(self, item: M) -> M:
        self.characters.load(item.character_id)  # character must exist
        path = self.path(item.character_id, type(item), item.id)
        if path.exists():
            raise AnimationError(
                f"{KIND_DIRS[type(item)][:-1]} {item.id!r} already exists; nothing was changed"
            )
        write_text_atomic(path, model_to_yaml(item))
        self.project.touch()
        return item

    def save(self, item: M) -> M:
        """Save an edit: previous version to history, version + 1. Identical content is a no-op."""
        path = self.path(item.character_id, type(item), item.id)
        if not path.is_file():
            raise AnimationError(f"{item.id!r} does not exist; create it first")
        current = load_model(type(item), path)
        if item.version != current.version:
            raise AnimationError(
                f"{item.id!r} was edited elsewhere (file v{current.version}); reload"
            )
        if item == current:
            return current
        folder = self.characters.folder(item.character_id)
        CharacterStore._snapshot(
            folder,
            f"animations/{KIND_DIRS[type(item)]}/{item.id}.v{current.version}.yaml",
            model_to_yaml(current),
        )
        updated = type(item).model_validate(
            item.model_copy(update={"version": current.version + 1}).model_dump()
        )
        write_text_atomic(path, model_to_yaml(updated))
        self.project.touch()
        return updated

    def put(self, item: M, *, replace: bool = False) -> M:
        """Create, or save a new version when ``replace`` (used by generators)."""
        path = self.path(item.character_id, type(item), item.id)
        if not path.exists():
            return self.create(item)
        if not replace:
            raise AnimationError(f"{item.id!r} already exists; use --replace to save a new version")
        current = load_model(type(item), path)
        return self.save(item.model_copy(update={"version": current.version}))

    # --- contexts -------------------------------------------------------------------------------

    def context(self, character_id: str, animation_set: AnimationSet) -> AnimationContext:
        loaded = self.characters.load(character_id)
        if loaded.rig is None:
            raise AnimationError(f"{character_id} has no rig; animation needs one")
        face = None
        if loaded.character.face is not None:
            face = load_model(FacialRig, loaded.folder / "face.yaml")
        return build_context(
            self.project.root,
            loaded.folder,
            loaded.character,
            loaded.rig,
            face,
            animation_set,
            self.project.registry(),
        )


def _expressions_for(char_dir: Path) -> tuple[dict[str, FacialExpression], set[str]]:
    exprs = {e.id: e for e in builtin_expressions()}
    folder = char_dir / "expressions"
    if folder.is_dir():
        for p in sorted(folder.glob("*.yaml")):
            e = load_model(FacialExpression, p)
            exprs[e.id] = e
    return exprs, set(exprs)


def resolve_project_path(project_root: Path, rel: str) -> Path:
    return safe_join(project_root, rel)


def load_lipsync(
    project_root: Path, aset: AnimationSet, registry: AssetRegistry | None
) -> tuple[LipSyncTrack | None, VisemeSet | None]:
    b = aset.lipsync
    if b is None or not b.enabled:
        return None, None
    if b.asset is not None:
        if registry is None:
            raise AnimationError("lip-sync asset cannot be resolved: registry unavailable")
        try:
            record = registry.get(b.asset)
        except AssetNotFoundError:
            raise AnimationError(f"lip-sync asset {b.asset} is not registered") from None
        if record.format not in ("yaml", "json"):
            raise AnimationError(
                f"lip-sync asset {b.asset} is {record.format.upper()}; expected YAML/JSON"
            )
        path = safe_join(project_root, record.current.path)
    else:
        assert b.path is not None
        path = resolve_project_path(project_root, b.path)
    if not path.is_file():
        raise AnimationError(f"lip-sync track file not found: {path.name}")
    track = load_model(LipSyncTrack, path)
    visemes = load_viseme_set(
        b.visemes if b.visemes == "default" else str(resolve_project_path(project_root, b.visemes))
    )
    return track, visemes


def build_context(
    project_root: Path,
    char_dir: Path,
    character: CharacterDefinition,
    rig: RigDefinition,
    face: FacialRig | None,
    aset: AnimationSet,
    registry: AssetRegistry | None,
) -> AnimationContext:
    base = char_dir / ANIM_DIR
    clips: dict[str, AnimationClip] = {}
    for layer in aset.layers:
        path = base / CLIPS_DIR / f"{layer.clip}.yaml"
        if path.is_file():
            clips[layer.clip] = load_model(AnimationClip, path)
    meshes: dict[str, DeformMesh] = {}
    mesh_dir = base / MESHES_DIR
    if mesh_dir.is_dir():
        for p in sorted(mesh_dir.glob("*.yaml")):
            m = load_model(DeformMesh, p)
            meshes[m.id] = m
    exprs, ids = _expressions_for(char_dir)

    def lookup(expr_id: str) -> FacialExpression:
        if expr_id not in exprs:
            raise FaceError(f"unknown expression {expr_id!r}")
        return exprs[expr_id]

    track, visemes = load_lipsync(project_root, aset, registry)
    return AnimationContext(
        character=character,
        rig=rig,
        clips=clips,
        face=face,
        expressions=lookup,
        expression_ids=ids,
        meshes=meshes,
        lipsync=track,
        visemes=visemes,
    )


def load_context_for_validation(
    project_root: Path,
    char_dir: Path,
    character: CharacterDefinition,
    rig: RigDefinition,
    face: FacialRig | None,
    aset: AnimationSet,
) -> AnimationContext:
    try:
        registry: AssetRegistry | None = AssetRegistry.load(
            project_root / "assets" / "registry.json"
        )
    except (ConfigError, SchemaValidationError):
        registry = None  # registry problems are reported by asset validation
    try:
        return build_context(project_root, char_dir, character, rig, face, aset, registry)
    except AnimationError as exc:
        raise FaceError(str(exc)) from None
