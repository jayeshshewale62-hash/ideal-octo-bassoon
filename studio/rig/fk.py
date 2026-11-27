"""Forward kinematics: local bone transforms -> world (character-space) transforms.

For each bone, in deterministic parent-before-child order (siblings sorted by ID):

    local  = T(x, y) @ R(rotation) @ S(scale_x, scale_y)       (rest values, overridden by a pose)
    world  = parent_world @ local                                (both inherit flags on: exact)

If ``inherit_rotation`` or ``inherit_scale`` is off, the head position still comes from
the parent (``parent_world.apply((x, y))``). The world matrix is then rebuilt from the
inherited parts only:
``T(head) @ R(parent_rot? + rotation) @ S(parent_scale? * scale)``.

Joint constraints are applied to the *local rotation* before composition:
``locked`` keeps the rest rotation; otherwise the rotation is wrapped
(``wrap_into_range``) and clamped to ``[min_rotation, max_rotation]``. Every adjustment is
reported, never applied silently.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from studio.core.exceptions import RigError
from studio.rig.math2d import Affine, Vec2, clamp, wrap_into_range
from studio.rig.schemas import BoneDefinition, GeometryModel, RigDefinition

TOLERANCE = 1e-9


class BonePose(GeometryModel):
    """Pose override for one bone. ``None`` fields keep the rest value."""

    rotation: float | None = None
    x: float | None = None
    y: float | None = None
    scale_x: float | None = None
    scale_y: float | None = None


Pose = Mapping[str, BonePose]


@dataclass(frozen=True)
class ConstraintEvent:
    bone: str
    requested: float
    applied: float
    reason: str  # "locked" | "min" | "max"


@dataclass(frozen=True)
class WorldBone:
    id: str
    matrix: Affine
    local_rotation: float  # after constraints
    length: float

    @property
    def head(self) -> Vec2:
        return self.matrix.origin

    @property
    def tip(self) -> Vec2:
        return self.matrix.apply(Vec2(self.length, 0.0))

    @property
    def world_rotation(self) -> float:
        return self.matrix.rotation_degrees

    @property
    def world_scale(self) -> tuple[float, float]:
        return self.matrix.scale

    def to_dict(self) -> dict[str, object]:
        sx, sy = self.world_scale
        return {
            "bone": self.id,
            "head": list(self.head.rounded(4)),
            "tip": list(self.tip.rounded(4)),
            "local_rotation": round(self.local_rotation, 4),
            "world_rotation": round(self.world_rotation, 4),
            "world_scale": [round(sx, 6), round(sy, 6)],
        }


@dataclass
class FKResult:
    bones: dict[str, WorldBone]
    order: list[str]
    events: list[ConstraintEvent] = field(default_factory=list)

    def __getitem__(self, bone_id: str) -> WorldBone:
        return self.bones[bone_id]


def bone_order(rig: RigDefinition) -> list[str]:
    """Parent-before-child order from the root; raises RigError on structural problems."""
    bones = rig.bone_map()
    if len(bones) != len(rig.bones):
        raise RigError("rig has duplicate bone IDs; run 'studio character rig validate'")
    if rig.root not in bones:
        raise RigError(f"root bone {rig.root!r} is not defined")
    if bones[rig.root].parent is not None:
        raise RigError(f"root bone {rig.root!r} must not have a parent")
    children: dict[str, list[str]] = {b: [] for b in bones}
    for bone in bones.values():
        if bone.id == rig.root:
            continue
        if bone.parent is None:
            raise RigError(f"bone {bone.id!r} has no parent but is not the root")
        if bone.parent not in bones:
            raise RigError(f"bone {bone.id!r} has unknown parent {bone.parent!r}")
        children[bone.parent].append(bone.id)
    order: list[str] = []
    stack = [rig.root]
    while stack:
        current = stack.pop()
        order.append(current)
        stack.extend(sorted(children[current], reverse=True))
    if len(order) != len(bones):
        missing = sorted(set(bones) - set(order))
        raise RigError(f"bones not connected to the root (cycle or detached): {', '.join(missing)}")
    return order


def constrain_rotation(bone: BoneDefinition, requested: float) -> tuple[float, str | None]:
    """Apply the bone's joint constraint to a requested local rotation."""
    c = bone.constraint
    if c is None:
        return requested, None
    if c.locked:
        applied = bone.rest.rotation
        return applied, (None if abs(applied - requested) <= TOLERANCE else "locked")
    if c.min_rotation > c.max_rotation:
        raise RigError(f"bone {bone.id!r}: min_rotation is greater than max_rotation")
    wrapped = wrap_into_range(requested, c.min_rotation, c.max_rotation)
    applied = clamp(wrapped, c.min_rotation, c.max_rotation)
    if applied == wrapped:
        # same angle, only re-expressed: not a constraint event
        return applied, None
    return applied, ("min" if applied == c.min_rotation else "max")


def local_matrix(bone: BoneDefinition, pose: BonePose | None, rotation: float) -> Affine:
    rest = bone.rest
    p = pose or BonePose()
    return Affine.from_trs(
        rest.x if p.x is None else p.x,
        rest.y if p.y is None else p.y,
        rotation,
        rest.scale_x if p.scale_x is None else p.scale_x,
        rest.scale_y if p.scale_y is None else p.scale_y,
    )


def solve_fk(
    rig: RigDefinition, pose: Pose | None = None, *, origin: Affine | None = None
) -> FKResult:
    """World transforms for every bone. ``origin`` places the rig's root in character space."""
    pose = pose or {}
    unknown = sorted(set(pose) - {b.id for b in rig.bones})
    if unknown:
        raise RigError(f"pose names unknown bones: {', '.join(unknown)}")
    bones = rig.bone_map()
    order = bone_order(rig)
    base = origin or Affine.identity()
    result: dict[str, WorldBone] = {}
    events: list[ConstraintEvent] = []
    for bone_id in order:
        bone = bones[bone_id]
        bp = pose.get(bone_id)
        requested = bone.rest.rotation if bp is None or bp.rotation is None else bp.rotation
        rotation, reason = constrain_rotation(bone, requested)
        if reason:
            events.append(ConstraintEvent(bone_id, requested, rotation, reason))
        local = local_matrix(bone, bp, rotation)
        parent = base if bone.parent is None else result[bone.parent].matrix
        if bone.inherit_rotation and bone.inherit_scale:
            world = parent @ local
        else:
            head = parent.apply(local.origin)
            prot = parent.rotation_degrees if bone.inherit_rotation else 0.0
            psx, psy = parent.scale if bone.inherit_scale else (1.0, 1.0)
            sx = (bone.rest.scale_x if bp is None or bp.scale_x is None else bp.scale_x) * psx
            sy = (bone.rest.scale_y if bp is None or bp.scale_y is None else bp.scale_y) * psy
            world = Affine.from_trs(head.x, head.y, prot + rotation, sx, sy)
        result[bone_id] = WorldBone(bone_id, world, rotation, bone.length)
    return FKResult(result, order, events)


def parse_rotation_overrides(items: list[str]) -> dict[str, BonePose]:
    """Parse CLI ``bone=degrees`` items into a pose."""
    pose: dict[str, BonePose] = {}
    for item in items:
        name, sep, value = item.partition("=")
        if not sep or not name:
            raise RigError(f"expected BONE=DEGREES, got {item!r}")
        try:
            degrees = float(value)
        except ValueError:
            raise RigError(f"rotation for {name!r} is not a number: {value!r}") from None
        if degrees != degrees or degrees in (float("inf"), float("-inf")):
            raise RigError(f"rotation for {name!r} must be finite")
        pose[name] = BonePose(rotation=degrees)
    return pose
