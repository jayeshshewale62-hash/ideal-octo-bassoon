"""Character validation: every problem reported with a code; nothing is modified or repaired.

Codes (documented in docs/DATA_SCHEMAS.md): CHR0xx character file, PRT0xx parts,
RIG0xx/IK0xx rig (studio.rig.validation), TRN0xx turnaround, IDN0xx identity.
"""

from __future__ import annotations

from pathlib import Path

from studio.characters.consistency import view_differences
from studio.characters.parts import solve_parts
from studio.characters.schemas import ALL_VIEWS, CharacterDefinition, IdentityRole
from studio.core.exceptions import (
    AssetNotFoundError,
    CharacterError,
    ConfigError,
    PathSafetyError,
    RigError,
    SchemaValidationError,
)
from studio.core.paths import safe_join
from studio.core.registry import AssetRegistry
from studio.core.schemas import AssetCategory, CharacterStatus, TurnaroundView
from studio.core.validation import ValidationReport, load_model
from studio.rig.fk import solve_fk
from studio.rig.schemas import RigDefinition
from studio.rig.validation import validate_rig

CHARACTERS_DIR = "characters"
CHARACTER_FILE = "character.yaml"
RIG_FILE = "rig.yaml"
HISTORY_DIR = "history"
ART_FORMATS = frozenset({"svg", "png", "webp", "jpg", "ora", "psd", "kra"})
PART_ART_FORMATS = frozenset({"svg", "png", "webp"})
ART_CATEGORIES = frozenset({AssetCategory.CHARACTER, AssetCategory.PROP, AssetCategory.TEXTURE})


def _cycle_members(parents: dict[str, str | None]) -> list[str]:
    members: set[str] = set()
    for start in parents:
        seen: list[str] = []
        cur: str | None = start
        while cur is not None and cur in parents:
            if cur in seen:
                members.update(seen[seen.index(cur) :])
                break
            seen.append(cur)
            cur = parents[cur]
    return sorted(members)


def _check_asset(
    asset_id: str,
    registry: AssetRegistry | None,
    root: Path,
    report: ValidationReport,
    loc: str,
    *,
    formats: frozenset[str],
    character_id: str,
    missing_code: str,
) -> None:
    report.checks += 1
    if registry is None:
        report.error(missing_code, f"asset {asset_id} cannot be checked: registry unavailable", loc)
        return
    try:
        record = registry.get(asset_id)
    except AssetNotFoundError:
        report.error(missing_code, f"asset {asset_id} is not registered in this project", loc)
        return
    if record.format not in formats:
        report.error(
            "PRT007",
            f"asset {asset_id} is {record.format.upper()}; expected one of "
            f"{', '.join(sorted(formats))}",
            loc,
        )
    if record.category not in ART_CATEGORIES:
        report.warning("PRT013", f"asset {asset_id} has category {record.category.value}", loc)
    try:
        path = safe_join(root, record.current.path)
    except PathSafetyError as exc:
        report.error("PRT008", str(exc), loc)
        return
    if not path.is_file():
        report.error("PRT008", f"artwork file missing: {record.current.path}", loc)
    other = sorted(t for t in record.tags if t.startswith("chr_") and t != character_id)
    if other:
        report.error("PRT011", f"asset {asset_id} is tagged for another character: {other[0]}", loc)


def validate_parts(
    char: CharacterDefinition,
    rig: RigDefinition | None,
    report: ValidationReport,
    loc: str,
) -> bool:
    """Structural part checks. Returns True if the hierarchy can be solved."""
    ok = True
    report.checks += 1
    if not char.parts:
        report.error("PRT012", "character has no parts", loc)
        return False
    ids = [p.id for p in char.parts]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        report.error("PRT001", f"duplicate part id {dup!r}", loc)
        ok = False
    parts = char.part_map()
    parents = {p.id: p.parent for p in parts.values()}
    bones = rig.bone_map() if rig else {}
    for part in parts.values():
        report.checks += 1
        ploc = f"{loc}: part {part.id}"
        if part.parent is not None and part.parent not in parts:
            report.error("PRT002", f"parent {part.parent!r} does not exist", ploc)
            ok = False
        if part.parent == part.id:
            report.error("PRT003", "part is its own parent", ploc)
            ok = False
        if part.parent_attachment is not None:
            if part.parent is None:
                report.error("PRT014", "parent_attachment set without a parent", ploc)
                ok = False
            elif part.parent in parts and part.parent_attachment not in {
                a.name for a in parts[part.parent].attachment_points
            }:
                report.error(
                    "PRT009",
                    f"parent {part.parent!r} has no attachment point {part.parent_attachment!r}",
                    ploc,
                )
                ok = False
        names = [a.name for a in part.attachment_points]
        if len(set(names)) != len(names):
            report.error("PRT015", "duplicate attachment point names", ploc)
        if part.bone is not None:
            if rig is None:
                report.error(
                    "PRT004", f"bound to bone {part.bone!r} but the character has no rig", ploc
                )
                ok = False
            elif part.bone not in bones:
                report.error("PRT004", f"bound to unknown bone {part.bone!r}", ploc)
                ok = False
            elif part.parent in parts and parts[part.parent].bone is not None:
                parent_bone = parts[part.parent].bone
                ancestors, cur = set(), bones.get(part.bone)
                while cur is not None and cur.id not in ancestors:
                    ancestors.add(cur.id)
                    cur = bones.get(cur.parent) if cur.parent else None
                if parent_bone not in ancestors:
                    report.warning(
                        "PRT010",
                        f"parent part's bone {parent_bone!r} is not an ancestor of {part.bone!r}",
                        ploc,
                    )
        if part.deformation is not None and part.deformation.mode.value != "rigid":
            report.warning(
                "PRT016", "mesh/warp deformation is metadata only until a later milestone", ploc
            )
    cycle = _cycle_members(parents)
    if cycle:
        report.error("PRT003", "circular part hierarchy: " + ", ".join(cycle), loc)
        ok = False

    # draw order: unique per view (base definition + each view's overrides)
    for view in [None, *char.turnaround.views]:
        report.checks += 1
        z = {p.id: p.z_order for p in parts.values()}
        if view is not None:
            z.update({k: v for k, v in view.z_order.items() if k in z})
        seen: dict[int, list[str]] = {}
        for pid, value in z.items():
            seen.setdefault(value, []).append(pid)
        for value, members in sorted(seen.items()):
            if len(members) > 1:
                where = f"view {view.view.value}" if view else "base"
                report.error(
                    "PRT005",
                    f"duplicate z_order {value} ({where}): {', '.join(sorted(members))}",
                    loc,
                )
    return ok


def validate_turnaround(char: CharacterDefinition, report: ValidationReport, loc: str) -> None:
    ta = char.turnaround
    report.checks += 1
    req = list(ta.required_views)
    if len(set(req)) != len(req):
        report.error("TRN010", "required_views contains duplicates", loc)
    if TurnaroundView.FRONT not in req:
        report.error("TRN011", "required_views must include 'front'", loc)
    present = [v.view for v in ta.views]
    for dup in sorted({v for v in present if present.count(v) > 1}, key=lambda v: v.value):
        report.error("TRN001", f"view {dup.value!r} is defined more than once", loc)
    for required in req:
        if required not in present:
            report.error("TRN002", f"required view {required.value!r} is missing", loc)
    parts = char.part_map()
    without_art = []
    for view in ta.views:
        report.checks += 1
        vloc = f"{loc}: view {view.view.value}"
        refs = (
            set(view.part_assets)
            | set(view.hidden_parts)
            | set(view.z_order)
            | set(view.part_transforms)
        )
        unknown_parts = sorted(r for r in refs if r not in parts)
        if unknown_parts:
            report.error("TRN004", "unknown part(s): " + ", ".join(unknown_parts), vloc)
        has_art = (
            view.artwork is not None
            or bool(view.part_assets)
            or all(p.asset is not None or p.optional for p in parts.values())
        )
        if not has_art:
            without_art.append(view.view.value)
        diffs, unknown, type_errors = view_differences(char, view.identity_overrides)
        for prop in unknown:
            report.error("TRN007", f"unknown identity property {prop!r}", vloc)
        for message in type_errors:
            report.error("TRN009", message, vloc)
        for diff in diffs:
            if diff.role is IdentityRole.REQUIRED:
                report.error(
                    "TRN005",
                    f"view changes required identity property {diff.prop!r} "
                    f"({diff.base!r} -> {diff.other!r}); "
                    "a view must not create a different identity",
                    vloc,
                )
            elif diff.role is IdentityRole.OPTIONAL:
                report.warning("TRN006", f"view changes optional property {diff.prop!r}", vloc)
    if without_art:
        order = [v.value for v in ALL_VIEWS]
        without_art.sort(key=lambda v: order.index(v) if v in order else 99)
        report.warning(
            "TRN003", "no artwork assigned yet for view(s): " + ", ".join(without_art), loc
        )
    if char.status is CharacterStatus.APPROVED and without_art:
        report.error("CHR009", "status 'approved' requires artwork for every view", loc)


def validate_character_dir(
    project_root: Path,
    char_dir: Path,
    project_id: str,
    registry: AssetRegistry | None,
    report: ValidationReport,
) -> CharacterDefinition | None:
    rel = f"{CHARACTERS_DIR}/{char_dir.name}"
    loc = f"{rel}/{CHARACTER_FILE}"
    report.checks += 1
    try:
        char = load_model(CharacterDefinition, char_dir / CHARACTER_FILE)
    except (SchemaValidationError, ConfigError) as exc:
        report.error("CHR001", str(exc), loc)
        return None
    if char.id != char_dir.name:
        report.error("CHR002", f"id {char.id!r} does not match folder name {char_dir.name!r}", loc)
    if char.project_id != project_id:
        report.error("CHR003", f"belongs to {char.project_id}, not {project_id}", loc)
    if char.status in (CharacterStatus.RIGGED, CharacterStatus.APPROVED) and char.rig is None:
        report.error("CHR010", f"status {char.status.value!r} requires a rig", loc)

    rig: RigDefinition | None = None
    rig_ok = False
    rig_path = char_dir / RIG_FILE
    rig_loc = f"{rel}/{RIG_FILE}"
    if char.rig is not None:
        report.checks += 1
        if not rig_path.is_file():
            report.error("CHR004", f"rig {char.rig!r} is referenced but {RIG_FILE} is missing", loc)
        else:
            try:
                rig = load_model(RigDefinition, rig_path)
            except (SchemaValidationError, ConfigError) as exc:
                report.error("RIG000", str(exc), rig_loc)
            if rig is not None:
                if rig.id != char.rig:
                    report.error(
                        "CHR005", f"rig file id {rig.id!r} != character rig {char.rig!r}", loc
                    )
                if rig.character_id != char.id:
                    report.error("CHR005", f"rig belongs to {rig.character_id!r}", rig_loc)
                before = len(report.errors)
                validate_rig(rig, report, rig_loc)
                rig_ok = len(report.errors) == before
    elif rig_path.is_file():
        report.warning(
            "CHR011", f"{RIG_FILE} exists but the character does not reference a rig", loc
        )

    parts_ok = validate_parts(char, rig, report, loc)
    validate_turnaround(char, report, loc)

    if rig is not None and rig_ok:
        report.checks += 1
        try:
            fk = solve_fk(rig)
        except RigError as exc:
            report.error("RIG014", f"rest pose cannot be evaluated: {exc}", rig_loc)
            fk = None
        if fk is not None and parts_ok:
            try:
                solve_parts(char, fk)
                for view in char.turnaround.views:
                    solve_parts(char, fk, view)
            except CharacterError as exc:
                report.error("PRT017", f"part transforms cannot be evaluated: {exc}", loc)
    elif rig is None and parts_ok and not any(p.bone for p in char.parts):
        try:
            solve_parts(char, None)
        except CharacterError as exc:
            report.error("PRT017", f"part transforms cannot be evaluated: {exc}", loc)

    # assets
    for part in char.parts:
        if part.asset:
            _check_asset(
                part.asset,
                registry,
                project_root,
                report,
                f"{loc}: part {part.id}",
                formats=PART_ART_FORMATS,
                character_id=char.id,
                missing_code="PRT006",
            )
    for view in char.turnaround.views:
        vloc = f"{loc}: view {view.view.value}"
        if view.artwork:
            _check_asset(
                view.artwork,
                registry,
                project_root,
                report,
                vloc,
                formats=ART_FORMATS,
                character_id=char.id,
                missing_code="TRN008",
            )
        for pid, aid in sorted(view.part_assets.items()):
            _check_asset(
                aid,
                registry,
                project_root,
                report,
                f"{vloc}: part {pid}",
                formats=PART_ART_FORMATS,
                character_id=char.id,
                missing_code="PRT006",
            )
    if char.model_sheet_asset:
        _check_asset(
            char.model_sheet_asset,
            registry,
            project_root,
            report,
            loc,
            formats=ART_FORMATS,
            character_id=char.id,
            missing_code="CHR008",
        )
    unassigned = sorted(p.id for p in char.parts if p.asset is None and not p.optional)
    if unassigned and len(unassigned) == len([p for p in char.parts if not p.optional]):
        report.warning("PRT018", "no part has artwork yet (structure only)", loc)
    elif unassigned:
        report.warning("PRT018", "parts without artwork: " + ", ".join(unassigned), loc)

    from studio.face.validation import validate_character_face  # face rigs (Milestone 4)

    validate_character_face(
        char_dir, char, report, loc, registry=registry, project_root=project_root
    )
    _validate_history(char_dir, char, report, rel)
    return char


def _validate_history(
    char_dir: Path, char: CharacterDefinition, report: ValidationReport, rel: str
) -> None:
    history = char_dir / HISTORY_DIR
    if not history.is_dir():
        return
    report.checks += 1
    versions = []
    for f in sorted(history.glob("character.v*.yaml")):
        try:
            versions.append(int(f.stem.split(".v", 1)[1]))
        except ValueError:
            report.warning(
                "CHR007", f"unexpected history file name {f.name}", f"{rel}/{HISTORY_DIR}"
            )
    if versions and (
        max(versions) >= char.version or sorted(versions) != list(range(1, len(versions) + 1))
    ):
        report.warning(
            "CHR007",
            f"history versions {sorted(versions)} do not fit current version {char.version}",
            f"{rel}/{HISTORY_DIR}",
        )


def validate_characters(project_root: Path, project_id: str, report: ValidationReport) -> None:
    """Validate every character folder of a project (no-op if there is no characters/)."""
    base = project_root / CHARACTERS_DIR
    if not base.is_dir():
        return
    try:
        registry: AssetRegistry | None = AssetRegistry.load(
            project_root / "assets" / "registry.json"
        )
    except (SchemaValidationError, ConfigError):
        registry = None  # already reported by asset validation
    seen: dict[str, str] = {}
    for char_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        if not (char_dir / CHARACTER_FILE).is_file():
            report.warning(
                "CHR012", "folder has no character.yaml", f"{CHARACTERS_DIR}/{char_dir.name}"
            )
            continue
        char = validate_character_dir(project_root, char_dir, project_id, registry, report)
        if char is not None:
            if char.id in seen:
                report.error(
                    "CHR006",
                    f"character id {char.id!r} also used by {seen[char.id]}",
                    f"{CHARACTERS_DIR}/{char_dir.name}",
                )
            seen.setdefault(char.id, f"{CHARACTERS_DIR}/{char_dir.name}")
