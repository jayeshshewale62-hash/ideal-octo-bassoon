"""Face store: create, version and edit a character's facial rig and custom expressions.

Files (next to ``character.yaml``)::

    face.yaml                          FacialRig
    expressions/<id>.yaml              custom FacialExpression
    history/face.v<N>.yaml             earlier face versions (never overwritten)
    history/expressions/<id>.v<N>.yaml earlier expression versions
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from studio.characters.manager import CharacterStore
from studio.characters.schemas import CharacterDefinition
from studio.core.exceptions import FaceError, InvalidAssetError
from studio.core.project import Project
from studio.core.validation import ValidationReport, load_model, model_to_yaml, write_text_atomic
from studio.face.expressions import check_expression
from studio.face.library import builtin_expression, builtin_expressions
from studio.face.schemas import FacialExpression, FacialRig
from studio.face.templates import build_face
from studio.face.validation import EXPRESSIONS_DIR, FACE_ART_FORMATS, FACE_FILE


@dataclass
class LoadedFace:
    character: CharacterDefinition
    face: FacialRig


class FaceStore:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.characters = CharacterStore(project)

    # --- face rig ----------------------------------------------------------------------

    def create(self, character_id: str, template: str = "standard") -> LoadedFace:
        loaded = self.characters.load(character_id)
        char = loaded.character
        path = loaded.folder / FACE_FILE
        if char.face is not None or path.exists():
            raise FaceError(f"{character_id} already has a facial rig; nothing was changed")
        face = build_face(char, template)
        write_text_atomic(path, model_to_yaml(face))
        updated = self.characters.save(char.model_copy(update={"face": face.id}))
        return LoadedFace(updated, face)

    def load(self, character_id: str) -> LoadedFace:
        loaded = self.characters.load(character_id)
        char = loaded.character
        if char.face is None:
            raise FaceError(f"{character_id} has no facial rig; run 'studio face create'")
        path = loaded.folder / FACE_FILE
        if not path.is_file():
            raise FaceError(f"{character_id}: {FACE_FILE} is missing")
        return LoadedFace(char, load_model(FacialRig, path))

    def save(self, face: FacialRig) -> FacialRig:
        """Save an edited face: snapshot the previous version, bump ``version``."""
        folder = self.characters.folder(face.character_id)
        path = folder / FACE_FILE
        current = load_model(FacialRig, path)
        if face.version != current.version:
            raise FaceError(f"{face.id} was edited elsewhere (file v{current.version}); reload")
        if face == current:
            return current
        CharacterStore._snapshot(folder, f"face.v{current.version}.yaml", model_to_yaml(current))
        updated = FacialRig.model_validate(
            face.model_copy(update={"version": current.version + 1}).model_dump()
        )
        write_text_atomic(path, model_to_yaml(updated))
        self.project.touch()
        return updated

    def set_component_asset(
        self, character_id: str, component_id: str, asset_id: str, shape: str | None = None
    ) -> FacialRig:
        face = self.load(character_id).face
        comp = face.component(component_id)
        if comp is None:
            raise FaceError(f"{face.id} has no component {component_id!r}")
        record = self.project.registry().get(asset_id)
        if record.format not in FACE_ART_FORMATS:
            raise InvalidAssetError(
                f"asset {asset_id} is {record.format.upper()}; use SVG, PNG or WebP"
            )
        if shape is None:
            new_comp = comp.model_copy(update={"asset": asset_id})
        else:
            if shape not in comp.shapes:
                raise FaceError(
                    f"component {component_id!r} has no shape {shape!r} "
                    f"(shapes: {', '.join(comp.shapes) or 'none'})"
                )
            new_comp = comp.model_copy(update={"shapes": {**comp.shapes, shape: asset_id}})
        components = [new_comp if c.id == component_id else c for c in face.components]
        return self.save(face.model_copy(update={"components": components}))

    def validate(self, character_id: str) -> ValidationReport:
        """Character validation includes the face (and custom expressions)."""
        return self.characters.validate(character_id)

    # --- expressions -------------------------------------------------------------------

    def _expr_dir(self, character_id: str) -> Path:
        return self.characters.folder(character_id) / EXPRESSIONS_DIR

    def custom_expressions(self, character_id: str) -> list[FacialExpression]:
        folder = self._expr_dir(character_id)
        if not folder.is_dir():
            return []
        return [load_model(FacialExpression, p) for p in sorted(folder.glob("*.yaml"))]

    def list_expressions(self, character_id: str) -> list[FacialExpression]:
        return [*builtin_expressions(), *self.custom_expressions(character_id)]

    def get_expression(self, character_id: str, expression_id: str) -> FacialExpression:
        path = self._expr_dir(character_id) / f"{expression_id}.yaml"
        if path.is_file():
            return load_model(FacialExpression, path)
        builtin = builtin_expression(expression_id)
        if builtin is not None:
            return builtin
        known = ", ".join(e.id for e in self.list_expressions(character_id))
        raise FaceError(f"unknown expression {expression_id!r} (known: {known})")

    def create_expression(
        self,
        character_id: str,
        expression_id: str,
        name: str,
        *,
        base: str | None = None,
        values: dict[str, float] | None = None,
        shapes: dict[str, str] | None = None,
        description: str = "",
    ) -> FacialExpression:
        face = self.load(character_id).face
        if builtin_expression(expression_id) is not None:
            raise FaceError(f"{expression_id!r} is a built-in expression id; choose another")
        path = self._expr_dir(character_id) / f"{expression_id}.yaml"
        if path.exists():
            raise FaceError(f"expression {expression_id!r} already exists; nothing was changed")
        merged_values: dict[str, float] = {}
        merged_shapes: dict[str, str] = {}
        if base is not None:
            base_expr = self.get_expression(character_id, base)
            merged_values.update({k: v for k, v in base_expr.values.items() if face.channel(k)})
            merged_shapes.update({k: v for k, v in base_expr.shapes.items() if face.component(k)})
        merged_values.update(values or {})
        merged_shapes.update(shapes or {})
        expr = FacialExpression(
            id=expression_id,
            name=name,
            rig=face.id,
            values=merged_values,
            shapes=merged_shapes,
            description=description or (f"Based on {base}." if base else ""),
        )
        errors = [i for i in check_expression(face, expr) if i.severity == "error"]
        if errors:
            raise FaceError(
                "expression is not compatible with the facial rig:\n"
                + "\n".join(f"  - {e.code} {e.message}" for e in errors)
            )
        write_text_atomic(path, model_to_yaml(expr))
        self.project.touch()
        return expr

    def update_expression(
        self,
        character_id: str,
        expression_id: str,
        values: dict[str, float],
        shapes: dict[str, str] | None = None,
    ) -> FacialExpression:
        face = self.load(character_id).face
        path = self._expr_dir(character_id) / f"{expression_id}.yaml"
        if not path.is_file():
            raise FaceError(
                f"{expression_id!r} is not a custom expression of {character_id} "
                "(built-ins are read-only; create a custom one with --from)"
            )
        current = load_model(FacialExpression, path)
        edited = current.model_copy(
            update={
                "values": {**current.values, **values},
                "shapes": {**current.shapes, **(shapes or {})},
            }
        )
        errors = [i for i in check_expression(face, edited) if i.severity == "error"]
        if errors:
            raise FaceError(
                "edit is not compatible with the facial rig:\n"
                + "\n".join(f"  - {e.code} {e.message}" for e in errors)
            )
        if edited == current:
            return current
        folder = self.characters.folder(character_id)
        CharacterStore._snapshot(
            folder,
            f"{EXPRESSIONS_DIR}/{expression_id}.v{current.version}.yaml",
            model_to_yaml(current),
        )
        updated = FacialExpression.model_validate(
            edited.model_copy(update={"version": current.version + 1}).model_dump()
        )
        write_text_atomic(path, model_to_yaml(updated))
        self.project.touch()
        return updated
