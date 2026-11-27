"""Two-bone inverse kinematics (analytic, law of cosines).

Supported: chains of exactly two bones (upper -> lower, e.g. upper arm -> forearm or
thigh -> shin). The end effector is the tip of the lower bone. Full-body IK and
multi-bone chains are **not** implemented.

Maths (character space, +y down, degrees; see docs/RIGGING.md):

    d        = |target - root|, clamped into [|l1 - l2|, l1 + l2]
    base     = atan2(target - root)
    a_root   = acos((l1² + d² - l2²) / (2·l1·d))        angle at the root joint
    a_mid    = acos((l1² + l2² - d²) / (2·l1·l2))       inner angle at the middle joint
    upper    = base - s·a_root                          world direction of the upper bone
    lower    = upper + s·(180° - a_mid)                 world direction of the lower bone

``s`` is the bend sign: +1 ("positive") means the lower bone turns clockwise on screen
relative to the upper bone. A pole point overrides the bend: the middle joint is placed
on the pole's side of the root->target line. If the pole lies on that line, the chain's
configured bend is used.

Edge cases are deterministic:

* target beyond reach (d > l1 + l2): fully extended towards the target, status ``too_far``;
* target too close (d < |l1 - l2|): fully folded towards the target, status ``too_close``;
* target on the root (d ≈ 0): the direction is undefined, so the current upper-bone
  direction is kept and the chain folds, status ``degenerate``;
* joint limits: the solved local rotations are clamped by the bones' constraints. The
  result reports ``limited`` and the remaining distance to the target.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from studio.core.exceptions import RigError
from studio.rig.fk import BonePose, ConstraintEvent, FKResult, Pose, constrain_rotation, solve_fk
from studio.rig.math2d import EPSILON, Affine, Vec2, clamp
from studio.rig.schemas import BendDirection, RigDefinition

REACH_TOLERANCE = 1e-7


@dataclass(frozen=True)
class TwoBoneSolution:
    upper_angle: float  # world direction of the upper bone, degrees
    lower_angle: float  # world direction of the lower bone, degrees
    root: Vec2
    mid: Vec2
    end: Vec2
    distance: float  # |target - root|
    status: str  # "reached" | "too_far" | "too_close" | "degenerate"
    bend_sign: int

    @property
    def reached(self) -> bool:
        return self.status == "reached"


def solve_two_bone(
    root: Vec2,
    upper_length: float,
    lower_length: float,
    target: Vec2,
    *,
    bend: BendDirection = BendDirection.POSITIVE,
    pole: Vec2 | None = None,
    fallback_angle: float = 0.0,
) -> TwoBoneSolution:
    """Pure geometric two-bone solve (no rig, no limits)."""
    l1, l2 = upper_length, lower_length
    for name, value in (("upper", l1), ("lower", l2)):
        if not math.isfinite(value) or value <= EPSILON:
            raise RigError(f"{name} segment length must be positive, got {value}")
    if not (math.isfinite(target.x) and math.isfinite(target.y)):
        raise RigError("IK target must be finite")

    sign = 1 if bend is BendDirection.POSITIVE else -1
    to_target = target - root
    distance = to_target.length()
    if pole is not None:
        side = to_target.cross(pole - root)
        if abs(side) > EPSILON * max(1.0, distance):
            # mid joint on the pole's side: positive cross -> mid at +90° from base -> s = -1
            sign = -1 if side > 0 else 1

    max_reach, min_reach = l1 + l2, abs(l1 - l2)
    if distance <= EPSILON:
        status, base = "degenerate", fallback_angle
        d = max(min_reach, EPSILON)
    else:
        base = to_target.angle()
        if distance > max_reach * (1 + REACH_TOLERANCE):
            status = "too_far"
        elif distance < min_reach * (1 - REACH_TOLERANCE):
            status = "too_close"
        else:
            status = "reached"
        d = clamp(distance, min_reach, max_reach)

    if d <= EPSILON:  # equal lengths folded completely onto the root
        a_root, a_mid = 90.0, 0.0
    else:
        a_root = math.degrees(math.acos(clamp((l1 * l1 + d * d - l2 * l2) / (2 * l1 * d), -1, 1)))
        a_mid = math.degrees(math.acos(clamp((l1 * l1 + l2 * l2 - d * d) / (2 * l1 * l2), -1, 1)))
    upper = base - sign * a_root
    lower = upper + sign * (180.0 - a_mid)
    mid = root + Vec2.polar(l1, upper)
    end = mid + Vec2.polar(l2, lower)
    return TwoBoneSolution(upper, lower, root, mid, end, distance, status, sign)


@dataclass
class IKResult:
    chain: str
    target: Vec2
    solution: TwoBoneSolution
    pose: dict[str, BonePose]
    fk: FKResult
    upper: str
    lower: str
    limit_events: list[ConstraintEvent] = field(default_factory=list)

    @property
    def end(self) -> Vec2:
        return self.fk[self.lower].tip

    @property
    def error(self) -> float:
        """Distance from the solved end effector to the target (0 when reached)."""
        return self.end.distance_to(self.target)

    @property
    def limited(self) -> bool:
        return bool(self.limit_events)

    def to_dict(self) -> dict[str, object]:
        return {
            "chain": self.chain,
            "target": list(self.target.rounded(4)),
            "status": self.solution.status,
            "bend_sign": self.solution.bend_sign,
            "limited": self.limited,
            "limit_events": [e.__dict__ for e in self.limit_events],
            "rotations": {
                self.upper: round(self.pose[self.upper].rotation or 0.0, 4),
                self.lower: round(self.pose[self.lower].rotation or 0.0, 4),
            },
            "joints": {
                "root": list(self.fk[self.upper].head.rounded(4)),
                "mid": list(self.fk[self.lower].head.rounded(4)),
                "end": list(self.end.rounded(4)),
            },
            "error": round(self.error, 6),
        }


def _local_rotation_for(
    direction_deg: float, parent: Affine, own_scale_x: float, inherit_rotation: bool
) -> float:
    """Local rotation that makes a bone point along a world direction under ``parent``."""
    if not inherit_rotation:
        parent = Affine.identity()
    local_dir = parent.inverse().apply_vector(Vec2.polar(1.0, direction_deg))
    angle = local_dir.angle()
    if own_scale_x < 0:
        angle += 180.0
    return angle


def solve_ik_chain(
    rig: RigDefinition,
    chain_id: str,
    target: Vec2,
    *,
    pole: Vec2 | None = None,
    pose: Pose | None = None,
    origin: Affine | None = None,
) -> IKResult:
    """Solve one of the rig's IK chains and return the resulting pose and FK."""
    chain = rig.chain(chain_id)
    if chain is None:
        known = ", ".join(c.id for c in rig.ik_chains) or "none"
        raise RigError(f"unknown IK chain {chain_id!r} (chains: {known})")
    bones = rig.bone_map()
    upper_def, lower_def = bones.get(chain.upper), bones.get(chain.lower)
    if upper_def is None or lower_def is None:
        raise RigError(f"chain {chain_id!r} names a bone that does not exist")
    if lower_def.parent != upper_def.id:
        raise RigError(f"chain {chain_id!r}: {lower_def.id!r} is not a child of {upper_def.id!r}")

    base_pose: dict[str, BonePose] = dict(pose or {})
    current = solve_fk(rig, base_pose, origin=origin)
    upper_w, lower_w = current[upper_def.id], current[lower_def.id]
    root = upper_w.head
    l1 = root.distance_to(lower_w.head)
    l2 = lower_def.length * lower_w.world_scale[0]
    if l1 <= EPSILON or l2 <= EPSILON:
        raise RigError(f"chain {chain_id!r} has a zero-length segment")

    solution = solve_two_bone(
        root, l1, l2, target, bend=chain.bend, pole=pole, fallback_angle=upper_w.world_rotation
    )

    # Offset between the upper bone's axis and the root->mid segment (non-zero if the lower
    # bone is not attached exactly at the upper tip).
    seg_angle = (lower_w.head - root).angle()
    axis_offset = upper_w.world_rotation - seg_angle
    upper_world_dir = solution.upper_angle + axis_offset

    parent_matrix = (
        current[upper_def.parent].matrix
        if upper_def.parent is not None
        else (origin or Affine.identity())
    )
    upper_scale_x = (base_pose.get(upper_def.id) or BonePose()).scale_x or upper_def.rest.scale_x
    upper_rot = _local_rotation_for(
        upper_world_dir, parent_matrix, upper_scale_x, upper_def.inherit_rotation
    )

    events: list[ConstraintEvent] = []
    upper_applied, reason = constrain_rotation(upper_def, upper_rot)
    if reason:
        events.append(ConstraintEvent(upper_def.id, upper_rot, upper_applied, reason))
    new_pose = dict(base_pose)
    prev_upper = base_pose.get(upper_def.id) or BonePose()
    new_pose[upper_def.id] = prev_upper.model_copy(update={"rotation": upper_applied})

    # Lower bone: relative to the (possibly limited) new upper bone.
    mid_fk = solve_fk(rig, new_pose, origin=origin)
    lower_scale_x = (base_pose.get(lower_def.id) or BonePose()).scale_x or lower_def.rest.scale_x
    lower_rot = _local_rotation_for(
        solution.lower_angle, mid_fk[upper_def.id].matrix, lower_scale_x, lower_def.inherit_rotation
    )
    lower_applied, reason = constrain_rotation(lower_def, lower_rot)
    if reason:
        events.append(ConstraintEvent(lower_def.id, lower_rot, lower_applied, reason))
    prev_lower = base_pose.get(lower_def.id) or BonePose()
    new_pose[lower_def.id] = prev_lower.model_copy(update={"rotation": lower_applied})

    final = solve_fk(rig, new_pose, origin=origin)
    return IKResult(chain_id, target, solution, new_pose, final, upper_def.id, lower_def.id, events)
