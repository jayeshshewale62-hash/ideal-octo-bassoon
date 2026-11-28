"""Facial rig and custom-expression validation (FAC0xx, EXP0xx). Never modifies files."""

from __future__ import annotations

from pathlib import Path

from studio.characters.schemas import CharacterDefinition
from studio.core.exceptions import (
    AssetNotFoundError,
    ConfigError,
    PathSafetyError,
    SchemaValidationError,
)
from studio.core.paths import safe_join
from studio.core.registry import AssetRegistry
from studio.core.validation import ValidationReport, load_model
from studio.face.expressions import check_expression
from studio.face.library import builtin_expression
from studio.face.schemas import ComponentKind, FacialExpression, FacialRig

FACE_FILE = "face.yaml"
EXPRESSIONS_DIR = "expressions"
FACE_ART_FORMATS = frozenset({"svg", "png", "webp"})
REQUIRED_CHANNELS: dict[ComponentKind, tuple[str, ...]] = {
    ComponentKind.EYE: ("blink", "pupil_x", "pupil_y"),
    ComponentKind.BROW: ("raise",),
    ComponentKind.MOUTH: ("open",),
    ComponentKind.JAW: ("open",),
}


def _asset(
    asset_id: str,
    registry: AssetRegistry | None,
    root: Path,
    char_id: str,
    report: ValidationReport,
    loc: str,
) -> None:
    report.checks += 1
    if registry is None:
        report.error("FAC010", f"asset {asset_id} cannot be checked: registry unavailable", loc)
        return
    try:
        rec = registry.get(asset_id)
    except AssetNotFoundError:
        report.error("FAC010", f"asset {asset_id} is not registered in this project", loc)
        return
    if rec.format not in FACE_ART_FORMATS:
        report.error(
            "FAC011", f"asset {asset_id} is {rec.format.upper()}; use SVG, PNG or WebP", loc
        )
    try:
        path = safe_join(root, rec.current.path)
    except PathSafetyError as exc:
        report.error("FAC013", str(exc), loc)
        return
    if not path.is_file():
        report.error("FAC013", f"artwork file missing: {rec.current.path}", loc)
    other = sorted(t for t in rec.tags if t.startswith("chr_") and t != char_id)
    if other:
        report.error("FAC016", f"asset {asset_id} is tagged for another character: {other[0]}", loc)


def validate_face(
    face: FacialRig,
    char: CharacterDefinition,
    report: ValidationReport,
    loc: str,
    *,
    registry: AssetRegistry | None = None,
    project_root: Path | None = None,
) -> None:
    report.checks += 1
    if face.character_id != char.id:
        report.error("FAC002", f"face belongs to {face.character_id!r}, not {char.id!r}", loc)
    if char.face is not None and char.face != face.id:
        report.error("FAC002", f"character references face {char.face!r}, file is {face.id!r}", loc)
    if not face.components:
        report.error("FAC015", "facial rig has no components", loc)
    parts = char.part_map()
    anchor = face.anchor
    if anchor.part not in parts:
        report.error("FAC008", f"anchor part {anchor.part!r} does not exist on the character", loc)
    elif anchor.attachment and anchor.attachment not in {
        a.name for a in parts[anchor.part].attachment_points
    }:
        report.error(
            "FAC007", f"part {anchor.part!r} has no attachment point {anchor.attachment!r}", loc
        )

    ids = [c.id for c in face.components]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        report.error("FAC003", f"duplicate component id {dup!r}", loc)
    without_art = []
    for comp in face.components:
        report.checks += 1
        cloc = f"{loc}: {comp.id}"
        names = [c.name for c in comp.channels]
        for dup in sorted({n for n in names if names.count(n) > 1}):
            report.error("FAC004", f"duplicate control {dup!r}", cloc)
        for ch in comp.channels:
            if ch.min > ch.max:
                report.error("FAC005", f"{ch.name}: min {ch.min:g} > max {ch.max:g}", cloc)
            elif not ch.min <= ch.default <= ch.max:
                report.error(
                    "FAC005",
                    f"{ch.name}: default {ch.default:g} outside [{ch.min:g}, {ch.max:g}]",
                    cloc,
                )
        missing = [n for n in REQUIRED_CHANNELS.get(comp.kind, ()) if n not in names]
        if missing:
            report.warning(
                "FAC009", f"{comp.kind.value} without control(s): {', '.join(missing)}", cloc
            )
        if comp.attachment is not None:
            part = parts.get(comp.attachment.part)
            if part is None:
                report.error("FAC006", f"attached to missing part {comp.attachment.part!r}", cloc)
            elif comp.attachment.point and comp.attachment.point not in {
                a.name for a in part.attachment_points
            }:
                report.error(
                    "FAC007",
                    f"part {part.id!r} has no attachment point {comp.attachment.point!r}",
                    cloc,
                )
        if project_root is not None:
            if comp.asset:
                _asset(comp.asset, registry, project_root, char.id, report, cloc)
            for shape, aid in sorted(comp.shapes.items()):
                if aid:
                    _asset(aid, registry, project_root, char.id, report, f"{cloc} shape {shape}")
        if not comp.optional and comp.asset is None and not any(comp.shapes.values()):
            without_art.append(comp.id)
    if without_art:
        report.warning("FAC012", "no artwork assigned yet for: " + ", ".join(without_art), loc)


def validate_expressions_dir(
    folder: Path, face: FacialRig, report: ValidationReport, loc: str
) -> list[FacialExpression]:
    found: list[FacialExpression] = []
    if not folder.is_dir():
        return found
    for path in sorted(folder.glob("*.yaml")):
        report.checks += 1
        eloc = f"{loc}/{path.name}"
        try:
            expr = load_model(FacialExpression, path)
        except (SchemaValidationError, ConfigError) as exc:
            report.error("EXP001", str(exc), eloc)
            continue
        if expr.id != path.stem:
            report.error("EXP008", f"id {expr.id!r} does not match file name {path.stem!r}", eloc)
        if builtin_expression(expr.id) is not None:
            report.error(
                "EXP005", f"custom expression id {expr.id!r} clashes with a built-in", eloc
            )
        if expr.builtin:
            report.error("EXP009", "custom expressions must not set builtin: true", eloc)
        for issue in check_expression(face, expr):
            if issue.severity == "error":
                report.error(issue.code, issue.message, eloc)
            else:
                report.warning(issue.code, issue.message, eloc)
        found.append(expr)
    return found


def validate_character_face(
    char_dir: Path,
    char: CharacterDefinition,
    report: ValidationReport,
    loc: str,
    *,
    registry: AssetRegistry | None,
    project_root: Path,
) -> FacialRig | None:
    """Hook called by character validation for every character."""
    path = char_dir / FACE_FILE
    if char.face is None:
        if path.is_file():
            report.warning(
                "FAC017", f"{FACE_FILE} exists but the character does not reference it", loc
            )
        return None
    report.checks += 1
    if not path.is_file():
        report.error("FAC001", f"face {char.face!r} is referenced but {FACE_FILE} is missing", loc)
        return None
    floc = f"{loc.rsplit('/', 1)[0]}/{FACE_FILE}"
    try:
        face = load_model(FacialRig, path)
    except (SchemaValidationError, ConfigError) as exc:
        report.error("FAC001", str(exc), floc)
        return None
    validate_face(face, char, report, floc, registry=registry, project_root=project_root)
    validate_expressions_dir(
        char_dir / EXPRESSIONS_DIR, face, report, f"{loc.rsplit('/', 1)[0]}/{EXPRESSIONS_DIR}"
    )
    return face
