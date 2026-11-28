"""Animation validation (ANM, SET, MSH codes). Never modifies files.

Clip-internal checks live in ``clip.check_clip`` (ANM009-ANM015). This module checks
references against the character: bones, parts, IK chains, facial controls,
expressions, meshes, clips, lip-sync sources and springs. It also hooks into character
validation, so ``studio project validate`` covers animations too.
"""

from __future__ import annotations

import math
from pathlib import Path

from pydantic import BaseModel

from studio.animation.clip import check_clip
from studio.animation.mesh import check_mesh
from studio.animation.schemas import (
    AnimationClip,
    AnimationSet,
    BoneTrack,
    DeformMesh,
    DeformTrack,
    ExpressionTrack,
    FaceTrack,
    IKTrack,
    PartTrack,
    track_id,
)
from studio.characters.schemas import CharacterDefinition
from studio.core.exceptions import ConfigError, FaceError, PathSafetyError, SchemaValidationError
from studio.core.validation import ValidationReport, load_model
from studio.face.schemas import FacialRig
from studio.rig.schemas import RigDefinition

Issue = tuple[str, str, str]  # (code, severity, message)
ANIM_DIR = "animations"
CLIPS_DIR = "clips"
SETS_DIR = "sets"
MESHES_DIR = "meshes"
KNOWN_GROUPS = ("full", "upper_body", "lower_body", "face")


def check_clip_references(
    clip: AnimationClip,
    character: CharacterDefinition,
    rig: RigDefinition | None,
    face: FacialRig | None,
    expression_ids: set[str] | None,
    mesh_ids: set[str],
) -> list[Issue]:
    out: list[Issue] = []
    for problem in check_clip(clip):
        code, _, msg = problem.partition(" ")
        out.append((code, "error", msg))
    if clip.character_id != character.id:
        out.append(("ANM003", "error", f"clip belongs to {clip.character_id}, not {character.id}"))
    bones = rig.bone_map() if rig else {}
    chains = {c.id for c in rig.ik_chains} if rig else set()
    parts = character.part_map()
    bone_tracks, ik_bones = set(), set()
    for track in clip.tracks:
        tid = track_id(track)
        if isinstance(track, BoneTrack):
            bone_tracks.add(track.bone)
            if track.bone not in bones:
                out.append(("ANM004", "error", f"track {tid!r}: unknown bone {track.bone!r}"))
        elif isinstance(track, IKTrack):
            if track.chain not in chains:
                out.append(("ANM006", "error", f"track {tid!r}: unknown IK chain {track.chain!r}"))
            elif rig is not None:
                chain = rig.chain(track.chain)
                assert chain is not None
                ik_bones |= {chain.upper, chain.lower}
        elif isinstance(track, PartTrack):
            if track.part not in parts:
                out.append(("ANM005", "error", f"track {tid!r}: unknown part {track.part!r}"))
        elif isinstance(track, FaceTrack):
            if face is None:
                out.append(("ANM007", "error", f"track {tid!r}: the character has no facial rig"))
            else:
                for key in track.keys:
                    for ctl in key.values:
                        if face.channel(ctl) is None:
                            out.append(
                                (
                                    "ANM007",
                                    "error",
                                    f"track {tid!r}: unknown facial control {ctl!r}",
                                )
                            )
        elif isinstance(track, ExpressionTrack):
            if face is None:
                out.append(("ANM007", "error", f"track {tid!r}: the character has no facial rig"))
            for ek in track.keys:
                if expression_ids is not None and ek.expression not in expression_ids:
                    out.append(
                        ("ANM008", "error", f"track {tid!r}: unknown expression {ek.expression!r}")
                    )
        elif isinstance(track, DeformTrack) and track.mesh not in mesh_ids:
            out.append(("ANM016", "error", f"track {tid!r}: unknown mesh {track.mesh!r}"))
    overlap = sorted(bone_tracks & ik_bones)
    for b in overlap:
        out.append(
            (
                "ANM017",
                "warning",
                f"bone {b!r} has a bone track and is driven by IK (IK wins where its weight is 1)",
            )
        )
    if rig is None and any(isinstance(t, BoneTrack | IKTrack) for t in clip.tracks):
        out.append(("ANM004", "error", "clip animates bones but the character has no rig"))
    return out


def check_set_references(context: object, animation_set: AnimationSet) -> list[Issue]:
    """References of a set against an AnimationContext (clips, meshes, lip-sync, springs)."""
    from studio.animation.evaluator import AnimationContext

    assert isinstance(context, AnimationContext)
    out: list[Issue] = []
    if animation_set.character_id != context.character.id:
        out.append(
            (
                "SET001",
                "error",
                f"set belongs to {animation_set.character_id}, not {context.character.id}",
            )
        )
    ids = [lyr.id for lyr in animation_set.layers]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        out.append(("SET002", "error", f"duplicate layer id {dup!r}"))
    if not animation_set.layers:
        out.append(("SET003", "error", "the set has no layers"))
    groups = (
        set(KNOWN_GROUPS)
        | {f"bone:{b}" for b in context.rig.bone_map()}
        | {f"ik:{c.id}" for c in context.rig.ik_chains}
        | {f"part:{p.id}" for p in context.character.parts}
    )
    expression_ids = _expression_ids(context)
    for layer in animation_set.layers:
        if layer.clip not in context.clips:
            out.append(("SET004", "error", f"layer {layer.id!r}: clip {layer.clip!r} not found"))
            continue
        for name in layer.mask:
            if name not in groups:
                out.append(("SET005", "error", f"layer {layer.id!r}: unknown mask group {name!r}"))
        clip = context.clips[layer.clip]
        for code, sev, msg in check_clip_references(
            clip, context.character, context.rig, context.face, expression_ids, set(context.meshes)
        ):
            out.append((code, sev, f"clip {clip.id}: {msg}"))
    for mesh_id in animation_set.meshes:
        if mesh_id not in context.meshes:
            out.append(("SET006", "error", f"mesh {mesh_id!r} not found"))
        else:
            for code, sev, msg in check_mesh(
                context.meshes[mesh_id], context.character, context.rig
            ):
                if sev == "error":
                    out.append((code, sev, f"mesh {mesh_id}: {msg}"))
    if animation_set.lipsync is not None and animation_set.lipsync.enabled:
        if context.lipsync is None or context.visemes is None:
            out.append(
                ("SET007", "error", "lip-sync is configured but its track could not be loaded")
            )
        elif context.face is None:
            out.append(("SET007", "error", "lip-sync needs a facial rig"))
    bones = context.rig.bone_map()
    parts = context.character.part_map()
    spring_ids = [s.id for s in animation_set.secondary.springs]
    for s in animation_set.secondary.springs:
        if spring_ids.count(s.id) > 1:
            out.append(("SET008", "error", f"duplicate spring id {s.id!r}"))
        if s.driver.bone not in bones:
            out.append(
                ("SET008", "error", f"spring {s.id!r}: unknown driver bone {s.driver.bone!r}")
            )
        if (s.target_kind == "bone" and s.target not in bones) or (
            s.target_kind == "part" and s.target not in parts
        ):
            out.append(
                ("SET008", "error", f"spring {s.id!r}: unknown {s.target_kind} {s.target!r}")
            )
        zeta = s.damping / (2 * math.sqrt(s.stiffness * s.mass))
        if zeta < 0.05:
            out.append(
                (
                    "SET009",
                    "warning",
                    f"spring {s.id!r}: very low damping (ratio {zeta:.3f}) keeps oscillating",
                )
            )
    return out


def _expression_ids(context: object) -> set[str] | None:
    from studio.face.library import builtin_expressions

    ids = getattr(context, "expression_ids", None)
    return set(ids) if ids is not None else {e.id for e in builtin_expressions()}


def validate_character_animations(
    char_dir: Path,
    character: CharacterDefinition,
    report: ValidationReport,
    loc: str,
    *,
    project_root: Path,
) -> None:
    """Hook called by character validation: every clip, mesh and set of the character."""
    base = char_dir / ANIM_DIR
    if not base.is_dir():
        return
    from studio.animation.store import load_context_for_validation

    rel = f"{loc.rsplit('/', 1)[0]}/{ANIM_DIR}"
    rig = _load_optional(char_dir / "rig.yaml", RigDefinition) if character.rig else None
    face = _load_optional(char_dir / "face.yaml", FacialRig) if character.face else None
    custom_expr = (
        {p.stem for p in (char_dir / "expressions").glob("*.yaml")}
        if (char_dir / "expressions").is_dir()
        else set()
    )
    from studio.face.library import builtin_expressions

    expr_ids = custom_expr | {e.id for e in builtin_expressions()}
    meshes: dict[str, DeformMesh] = {}
    for path in sorted((base / MESHES_DIR).glob("*.yaml")) if (base / MESHES_DIR).is_dir() else []:
        report.checks += 1
        mloc = f"{rel}/{MESHES_DIR}/{path.name}"
        try:
            mesh = load_model(DeformMesh, path)
        except (SchemaValidationError, ConfigError) as exc:
            report.error("MSH000", str(exc), mloc)
            continue
        if mesh.id != path.stem:
            report.error("MSH014", f"id {mesh.id!r} differs from file name", mloc)
        meshes[mesh.id] = mesh
        for code, sev, msg in check_mesh(mesh, character, rig):
            (report.error if sev == "error" else report.warning)(code, msg, mloc)
    for path in sorted((base / CLIPS_DIR).glob("*.yaml")) if (base / CLIPS_DIR).is_dir() else []:
        report.checks += 1
        cloc = f"{rel}/{CLIPS_DIR}/{path.name}"
        try:
            clip = load_model(AnimationClip, path)
        except (SchemaValidationError, ConfigError) as exc:
            report.error("ANM001", str(exc), cloc)
            continue
        if clip.id != path.stem:
            report.error("ANM002", f"id {clip.id!r} differs from file name", cloc)
        for code, sev, msg in check_clip_references(
            clip, character, rig, face, expr_ids, set(meshes)
        ):
            (report.error if sev == "error" else report.warning)(code, msg, cloc)
    for path in sorted((base / SETS_DIR).glob("*.yaml")) if (base / SETS_DIR).is_dir() else []:
        report.checks += 1
        sloc = f"{rel}/{SETS_DIR}/{path.name}"
        try:
            aset = load_model(AnimationSet, path)
        except (SchemaValidationError, ConfigError) as exc:
            report.error("SET000", str(exc), sloc)
            continue
        if aset.id != path.stem:
            report.error("SET010", f"id {aset.id!r} differs from file name", sloc)
        if rig is None:
            report.error("SET011", "animation sets need a character rig", sloc)
            continue
        try:
            context = load_context_for_validation(
                project_root, char_dir, character, rig, face, aset
            )
        except (SchemaValidationError, ConfigError, FaceError, PathSafetyError) as exc:
            report.error("SET007", f"cannot load set dependencies: {exc}", sloc)
            continue
        for code, sev, msg in check_set_references(context, aset):
            if code.startswith(("ANM", "MSH")):
                continue  # already reported per file above
            (report.error if sev == "error" else report.warning)(code, msg, sloc)


def _load_optional[M: BaseModel](path: Path, model: type[M]) -> M | None:
    if not path.is_file():
        return None
    try:
        return load_model(model, path)
    except (SchemaValidationError, ConfigError):
        return None  # reported by character/face validation
