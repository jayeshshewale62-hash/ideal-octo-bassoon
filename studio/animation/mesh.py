"""Basic 2D mesh deformation: linear blend skinning (LBS) plus blend shapes.

A :class:`DeformMesh` lives in a part's **artwork coordinates**. Its vertices are anchors
into the original drawing, which is never modified. For each frame:

1. blend shapes:  ``v' = v + Σ w_s · delta_s[v]``  (artwork space, before skinning);
2. bind position: ``p0 = A_rest · v'``  where ``A_rest`` is the part's artwork matrix in
   the rest pose (character space);
3. skinning:      ``p = Σ_b w_b · (B_b(t) · B_b(rest)⁻¹) · p0  +  (1 - Σ w_b) · A(t) · v'``.
   Weights that do not sum to 1 leave the remainder rigidly attached to the part
   (unweighted vertices simply follow the part).

Limits (documented): linear blend skinning only (no dual-quaternion or as-rigid-as-possible
warping); no automatic triangulation of artwork outlines (grid meshes are generated);
flipped triangles are *detected and reported*, not repaired.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from studio.animation.schemas import DeformMesh, VertexWeight
from studio.characters.parts import PartWorld
from studio.characters.schemas import CharacterDefinition
from studio.core.exceptions import AnimationError
from studio.rig.fk import FKResult, solve_fk
from studio.rig.math2d import Affine, Vec2
from studio.rig.schemas import RigDefinition

WEIGHT_SUM_TOLERANCE = 1e-3
MAX_INFLUENCES = 4


def _area(a: Vec2, b: Vec2, c: Vec2) -> float:
    return ((b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)) / 2


def check_mesh(
    mesh: DeformMesh, character: CharacterDefinition | None, rig: RigDefinition | None
) -> list[tuple[str, str, str]]:
    """(code, severity, message) for every problem found. Never modifies the mesh."""
    out: list[tuple[str, str, str]] = []

    def err(code: str, message: str) -> None:
        out.append((code, "error", message))

    def warn(code: str, message: str) -> None:
        out.append((code, "warning", message))

    n = len(mesh.vertices)
    part = character.part_map().get(mesh.part) if character else None
    if character is not None and part is None:
        err("MSH001", f"part {mesh.part!r} does not exist on {character.id}")
    if n < 3 or not mesh.triangles:
        err("MSH002", "a mesh needs at least 3 vertices and 1 triangle")
    verts = [Vec2(x, y) for x, y in mesh.vertices]
    for ti, tri in enumerate(mesh.triangles):
        if any(i < 0 or i >= n for i in tri):
            err("MSH003", f"triangle {ti} {list(tri)} references a vertex outside 0..{n - 1}")
            continue
        if len(set(tri)) < 3 or abs(_area(*(verts[i] for i in tri))) < 1e-9:
            err("MSH004", f"triangle {ti} {list(tri)} is degenerate (zero area)")
    if mesh.weights and len(mesh.weights) != n:
        err("MSH005", f"{len(mesh.weights)} weight lists for {n} vertices")
    bones = rig.bone_map() if rig else {}
    for vi, influences in enumerate(mesh.weights):
        names = [w.bone for w in influences]
        if len(set(names)) != len(names):
            err("MSH010", f"vertex {vi} lists a bone twice")
        if len(influences) > MAX_INFLUENCES:
            warn(
                "MSH011",
                f"vertex {vi} has {len(influences)} influences (more than {MAX_INFLUENCES})",
            )
        for w in influences:
            if not 0.0 <= w.weight <= 1.0:
                err("MSH006", f"vertex {vi}: weight {w.weight:g} for {w.bone!r} is outside [0, 1]")
            if rig is not None and w.bone not in bones:
                err("MSH008", f"vertex {vi}: unknown bone {w.bone!r}")
        total = sum(w.weight for w in influences)
        if influences and total > WEIGHT_SUM_TOLERANCE and abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
            err("MSH007", f"vertex {vi}: weights sum to {total:.4f}, expected 1 (or 0 for rigid)")
    for name, deltas in mesh.shapes.items():
        if len(deltas) != n:
            err("MSH009", f"shape {name!r} has {len(deltas)} deltas for {n} vertices")
    if part is not None and part.bounds is not None:
        b = part.bounds
        outside = [
            i
            for i, v in enumerate(verts)
            if not (
                b.x - 1e-6 <= v.x <= b.x + b.width + 1e-6
                and b.y - 1e-6 <= v.y <= b.y + b.height + 1e-6
            )
        ]
        if outside:
            warn("MSH012", f"{len(outside)} vertex/vertices lie outside the part's artwork bounds")
    unweighted = sum(1 for ws in mesh.weights if not ws) if mesh.weights else n
    if unweighted:
        warn("MSH013", f"{unweighted} unweighted vertex/vertices follow the part rigidly")
    return out


@dataclass(frozen=True)
class DeformedMesh:
    mesh_id: str
    vertices: list[Vec2]  # character space
    triangles: list[tuple[int, int, int]]
    flipped: list[int]  # triangles whose orientation reversed vs the bind pose

    def to_dict(self) -> dict[str, object]:
        return {
            "mesh": self.mesh_id,
            "vertices": [list(v.rounded(4)) for v in self.vertices],
            "flipped_triangles": self.flipped,
        }


def deform_mesh(
    mesh: DeformMesh,
    *,
    part_rest: PartWorld,
    part_now: PartWorld,
    bind: FKResult,
    fk: FKResult,
    shape_weights: Mapping[str, float] | None = None,
) -> DeformedMesh:
    shape_weights = shape_weights or {}
    n = len(mesh.vertices)
    local = [Vec2(x, y) for x, y in mesh.vertices]
    for name, w in sorted(shape_weights.items()):
        if name not in mesh.shapes:
            raise AnimationError(f"mesh {mesh.id!r} has no shape {name!r}")
        if not math.isfinite(w):
            raise AnimationError(f"shape weight for {name!r} must be finite")
        deltas = mesh.shapes[name]
        local = [
            Vec2(v.x + w * dx, v.y + w * dy) for v, (dx, dy) in zip(local, deltas, strict=True)
        ]
    skin: dict[str, Affine] = {}
    weights: list[list[VertexWeight]] = mesh.weights or [[] for _ in range(n)]
    out: list[Vec2] = []
    for v, influences in zip(local, weights, strict=True):
        p0 = part_rest.artwork.apply(v)
        acc = Vec2(0.0, 0.0)
        total = 0.0
        for inf in influences:
            if inf.weight <= 0:
                continue
            if inf.bone not in skin:
                skin[inf.bone] = fk[inf.bone].matrix @ bind[inf.bone].matrix.inverse()
            acc = acc + skin[inf.bone].apply(p0) * inf.weight
            total += inf.weight
        rigid = max(0.0, 1.0 - total)
        if rigid > 0:
            acc = acc + part_now.artwork.apply(v) * rigid
        out.append(acc)
    bind_pts = [part_rest.artwork.apply(Vec2(x, y)) for x, y in mesh.vertices]
    flipped = [
        i
        for i, (a, b, c) in enumerate(mesh.triangles)
        if _area(bind_pts[a], bind_pts[b], bind_pts[c]) * _area(out[a], out[b], out[c]) < 0
    ]
    return DeformedMesh(mesh.id, out, [tuple(t) for t in mesh.triangles], flipped)  # type: ignore[misc]


def _distance_to_segment(p: Vec2, a: Vec2, b: Vec2) -> float:
    ab = b - a
    denom = ab.x * ab.x + ab.y * ab.y
    if denom <= 1e-12:
        return p.distance_to(a)
    s = max(0.0, min(1.0, ((p.x - a.x) * ab.x + (p.y - a.y) * ab.y) / denom))
    return p.distance_to(a + ab * s)


def generate_grid_mesh(
    character: CharacterDefinition,
    rig: RigDefinition,
    part_id: str,
    mesh_id: str,
    *,
    columns: int = 4,
    rows: int = 2,
    bones: list[str] | None = None,
    falloff: float = 2.0,
) -> DeformMesh:
    """Regular grid over the part's bounds, skinned to ``bones`` by inverse distance to the
    bone segments in the rest pose (at most two influences per vertex, normalised)."""
    if not 1 <= columns <= 64 or not 1 <= rows <= 64:
        raise AnimationError("grid columns and rows must be 1..64")
    part = character.part_map().get(part_id)
    if part is None or part.bounds is None:
        raise AnimationError(f"part {part_id!r} does not exist or has no bounds")
    bone_ids = bones or ([part.bone] if part.bone else [])
    rest = solve_fk(rig)
    unknown = [b for b in bone_ids if b not in rest.bones]
    if unknown:
        raise AnimationError(f"unknown bone(s): {', '.join(unknown)}")
    from studio.characters.parts import solve_parts

    art = solve_parts(character, rest)[part_id].artwork
    b = part.bounds
    vertices = [
        (round(b.x + b.width * c / columns, 4), round(b.y + b.height * r / rows, 4))
        for r in range(rows + 1)
        for c in range(columns + 1)
    ]
    triangles: list[tuple[int, int, int]] = []
    for r in range(rows):
        for c in range(columns):
            i = r * (columns + 1) + c
            j = i + columns + 1
            triangles += [(i, i + 1, j + 1), (i, j + 1, j)]
    weights: list[list[VertexWeight]] = []
    for x, y in vertices:
        p = art.apply(Vec2(x, y))
        scored = sorted(
            (
                (max(_distance_to_segment(p, rest[bid].head, rest[bid].tip), 1e-6) ** -falloff, bid)
                for bid in bone_ids
            ),
            reverse=True,
        )[:2]
        total = sum(s for s, _ in scored)
        ws = (
            [VertexWeight(bone=bid, weight=round(s / total, 6)) for s, bid in scored]
            if total
            else []
        )
        if ws:  # make the rounded weights sum to exactly 1
            ws[0] = VertexWeight(
                bone=ws[0].bone, weight=round(1.0 - sum(w.weight for w in ws[1:]), 6)
            )
        weights.append(ws)
    return DeformMesh(
        id=mesh_id,
        character_id=character.id,
        part=part_id,
        vertices=vertices,
        triangles=triangles,
        weights=weights,
        notes=f"{columns}x{rows} grid over {part_id}, "
        f"skinned to {', '.join(bone_ids) or 'no bones'}",
    )
