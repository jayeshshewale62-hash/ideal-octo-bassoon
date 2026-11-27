"""Reusable character templates: body-part structure + matching rig, built from proportions.

Templates produce **structure only**: parts with bounds, a bone rig, IK chains, controls
and turnaround view entries. They never create or reference artwork; artwork is attached
later as registered assets (``studio character set-part-asset``).

Geometry (character space, +y down): the top of the head is at ``y = 0``, the soles at
``y = height_units``, and the body centre line at ``x = 0``. The character's own left
appears on screen right in the front view.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from studio.characters.schemas import (
    AttachmentPoint,
    Bounds,
    IdentityProfile,
    PartDefinition,
    PartKind,
    Side,
    TurnaroundSet,
    ViewDefinition,
)
from studio.core.exceptions import CharacterError
from studio.core.schemas import TurnaroundView
from studio.rig.fk import solve_fk
from studio.rig.schemas import (
    BendDirection,
    BoneDefinition,
    ControlHandle,
    IKChain,
    JointConstraint,
    Point2D,
    RigDefinition,
    Transform2D,
)


@dataclass(frozen=True)
class TemplateResult:
    parts: list[PartDefinition]
    rig: RigDefinition
    turnaround: TurnaroundSet


@dataclass(frozen=True)
class Template:
    name: str
    description: str
    build: Callable[[str, IdentityProfile], TemplateResult]


def _bone(
    bone_id: str,
    parent: str | None,
    length: float,
    x: float = 0.0,
    y: float = 0.0,
    rotation: float = 0.0,
    limits: tuple[float, float] | None = None,
    bend: BendDirection | None = None,
    control: bool = False,
) -> BoneDefinition:
    constraint = None
    if limits is not None:
        constraint = JointConstraint(
            min_rotation=limits[0], max_rotation=limits[1], preferred_bend=bend
        )
    return BoneDefinition(
        id=bone_id,
        parent=parent,
        length=round(length, 4),
        rest=Transform2D(x=round(x, 4), y=round(y, 4), rotation=rotation),
        constraint=constraint,
        control=control,
    )


def _limb_part(
    part_id: str, kind: PartKind, side: Side, bone: str, length: float, width: float, z: int
) -> PartDefinition:
    """A part drawn along its bone: artwork box (0,0)-(length,width), pivot at mid-left."""
    return PartDefinition(
        id=part_id,
        label=part_id.replace("_", " "),
        kind=kind,
        side=side,
        bone=bone,
        pivot=Point2D(x=0, y=round(width / 2, 4)),
        bounds=Bounds(width=round(max(length, 1.0), 4), height=round(width, 4)),
        z_order=z,
    )


def _build_biped(character_id: str, identity: IdentityProfile, *, minimal: bool) -> TemplateResult:
    H = identity.height_units
    p = identity.proportions
    h = H / p.height_heads  # head height
    leg = (p.leg_length_heads or 0.4 * p.height_heads) * h
    arm = (p.arm_length_heads or 0.36 * p.height_heads) * h
    shoulder_w = (p.shoulder_width_heads or 1.1) * h
    shoulder_y = 1.25 * h
    hip_y = H - leg
    if hip_y - shoulder_y < 0.4 * h:
        raise CharacterError(
            "proportions leave no room for a torso: reduce leg_length_heads or raise height_heads"
        )
    spine = hip_y - shoulder_y
    hip_w = 0.55 * shoulder_w
    ua, fa, hd = 0.42 * arm, 0.38 * arm, 0.20 * arm
    th, sh, ft = 0.48 * leg, 0.44 * leg, 0.08 * leg
    limb_w = 0.28 * h

    P, N = BendDirection.POSITIVE, BendDirection.NEGATIVE
    bones = [
        _bone("root", None, 0, x=0, y=hip_y, control=True),
        _bone("spine", "root", spine, rotation=-90, limits=(-135, -45)),
        _bone("neck", "spine", 0.25 * h, x=spine, limits=(-40, 40)),
        _bone("head", "neck", h, x=0.25 * h, limits=(-45, 45)),
    ]
    for side, sign, bend, elbow in (("l", 1, P, (0.0, 150.0)), ("r", -1, N, (-150.0, 0.0))):
        bones += [
            _bone(
                f"upper_arm_{side}",
                "spine",
                ua,
                x=spine,
                y=sign * shoulder_w / 2,
                rotation=180,
                limits=(20, 340),
            ),
            _bone(f"forearm_{side}", f"upper_arm_{side}", fa, x=ua, limits=elbow, bend=bend),
            _bone(f"hand_{side}", f"forearm_{side}", hd, x=fa, limits=(-60, 60)),
        ]
    for side, sign in (("l", 1), ("r", -1)):
        bones += [
            _bone(f"thigh_{side}", "root", th, x=sign * hip_w / 2, rotation=90, limits=(30, 150)),
            _bone(f"shin_{side}", f"thigh_{side}", sh, x=th, limits=(-150, 0), bend=N),
            _bone(f"foot_{side}", f"shin_{side}", ft, x=sh, limits=(-45, 45)),
        ]
    chains = [
        IKChain(
            id="arm_l",
            upper="upper_arm_l",
            lower="forearm_l",
            bend=P,
            target_control="hand_l_target",
        ),
        IKChain(
            id="arm_r",
            upper="upper_arm_r",
            lower="forearm_r",
            bend=N,
            target_control="hand_r_target",
        ),
        IKChain(
            id="leg_l", upper="thigh_l", lower="shin_l", bend=N, target_control="foot_l_target"
        ),
        IKChain(
            id="leg_r", upper="thigh_r", lower="shin_r", bend=N, target_control="foot_r_target"
        ),
    ]
    rig = RigDefinition(
        id="rig_" + character_id.removeprefix("chr_").replace("-", "_"),
        character_id=character_id,
        root="root",
        bones=bones,
        ik_chains=chains,
        notes="Generated from the biped template; edit freely.",
    )
    fk = solve_fk(rig)
    controls = [
        ControlHandle(
            id=f"{name}_target",
            kind="ik_target",
            bone=lower,
            position=Point2D(x=round(fk[lower].tip.x, 4), y=round(fk[lower].tip.y, 4)),
        )
        for name, lower in (
            ("hand_l", "forearm_l"),
            ("hand_r", "forearm_r"),
            ("foot_l", "shin_l"),
            ("foot_r", "shin_r"),
        )
    ]
    rig = rig.model_copy(update={"controls": controls})

    C, L, R = Side.CENTER, Side.LEFT, Side.RIGHT
    parts: list[PartDefinition] = []
    for side, sd, z0 in (("r", R, 10), ("l", L, 13)):
        parts += [
            _limb_part(f"thigh_{side}", PartKind.THIGH, sd, f"thigh_{side}", th, 0.32 * h, z0),
            _limb_part(
                f"lower_leg_{side}", PartKind.LOWER_LEG, sd, f"shin_{side}", sh, limb_w, z0 + 1
            ),
            _limb_part(f"foot_{side}", PartKind.FOOT, sd, f"foot_{side}", ft, 0.3 * h, z0 + 2),
        ]
    # pelvis: a horizontal box centred on the hip joint (the root bone is unrotated)
    parts.append(_limb_part("pelvis", PartKind.PELVIS, C, "root", 1.8 * hip_w, 0.4 * h, 20))
    parts[-1] = parts[-1].model_copy(
        update={
            "pivot": Point2D(x=round(0.9 * hip_w, 4), y=round(0.2 * h, 4)),
            "bounds": Bounds(width=round(1.8 * hip_w, 4), height=round(0.4 * h, 4)),
        }
    )
    parts.append(_limb_part("upper_torso", PartKind.UPPER_TORSO, C, "spine", spine, shoulder_w, 22))
    if not minimal:
        parts.append(
            _limb_part("waist", PartKind.WAIST, C, "spine", 0.35 * spine, 0.8 * shoulder_w, 21)
        )
        parts.append(
            PartDefinition(
                id="chest",
                label="chest",
                kind=PartKind.CHEST,
                side=C,
                parent="upper_torso",
                parent_attachment="chest_center",
                pivot=Point2D(x=0.2 * h, y=0.35 * shoulder_w),
                bounds=Bounds(width=round(0.4 * h, 4), height=round(0.7 * shoulder_w, 4)),
                z_order=23,
            )
        )
        torso = next(pt for pt in parts if pt.id == "upper_torso")
        parts[parts.index(torso)] = torso.model_copy(
            update={
                "attachment_points": [
                    AttachmentPoint(
                        name="chest_center",
                        position=Point2D(x=round(0.7 * spine, 4), y=round(shoulder_w / 2, 4)),
                    )
                ]
            }
        )
    for side, sd, z0 in (("r", R, 30), ("l", L, 33)):
        parts += [
            _limb_part(
                f"upper_arm_{side}", PartKind.UPPER_ARM, sd, f"upper_arm_{side}", ua, limb_w, z0
            ),
            _limb_part(
                f"forearm_{side}", PartKind.FOREARM, sd, f"forearm_{side}", fa, 0.24 * h, z0 + 1
            ),
            _limb_part(f"hand_{side}", PartKind.HAND, sd, f"hand_{side}", hd, 0.3 * h, z0 + 2),
        ]
    parts.append(_limb_part("neck", PartKind.NECK, C, "neck", 0.25 * h, 0.35 * h, 40))
    head_w = identity.head.width_ratio * h
    head = _limb_part("head", PartKind.HEAD, C, "head", h, head_w, 43)
    if not minimal:
        head = head.model_copy(
            update={
                "attachment_points": [
                    AttachmentPoint(
                        name="ear_l", position=Point2D(x=round(0.5 * h, 4), y=round(head_w, 4))
                    ),
                    AttachmentPoint(name="ear_r", position=Point2D(x=round(0.5 * h, 4), y=0)),
                    AttachmentPoint(
                        name="crown", position=Point2D(x=round(0.85 * h, 4), y=round(head_w / 2, 4))
                    ),
                ]
            }
        )
    parts.append(head)
    if not minimal:
        for side, sd, z in (("l", L, 41), ("r", R, 42)):
            parts.append(
                PartDefinition(
                    id=f"ear_{side}",
                    label=f"ear {side}",
                    kind=PartKind.EAR,
                    side=sd,
                    parent="head",
                    parent_attachment=f"ear_{side}",
                    pivot=Point2D(x=0.1 * h, y=0.1 * h),
                    bounds=Bounds(width=round(0.2 * h, 4), height=round(0.2 * h, 4)),
                    z_order=z,
                    optional=True,
                )
            )
        parts.append(
            PartDefinition(
                id="hair",
                label="hair",
                kind=PartKind.HAIR,
                side=C,
                parent="head",
                parent_attachment="crown",
                pivot=Point2D(x=0.3 * h, y=round(head_w * 0.55, 4)),
                bounds=Bounds(width=round(0.6 * h, 4), height=round(head_w * 1.1, 4)),
                z_order=44,
                optional=True,
            )
        )

    # Turnaround entries: data only, no artwork. Far-side limbs go behind the torso in
    # side views; arms go behind the torso from the back.
    far_side = {
        pid: -5 - i
        for i, pid in enumerate(
            ["upper_arm_r", "forearm_r", "hand_r", "thigh_r", "lower_leg_r", "foot_r"]
        )
    }
    back = {
        pid: -15 - i
        for i, pid in enumerate(
            ["upper_arm_l", "forearm_l", "hand_l", "upper_arm_r", "forearm_r", "hand_r"]
        )
    }
    views = [
        ViewDefinition(view=TurnaroundView.FRONT),
        ViewDefinition(view=TurnaroundView.THREE_QUARTER, z_order=dict(far_side)),
        ViewDefinition(
            view=TurnaroundView.SIDE,
            z_order=dict(far_side),
            identity_overrides={"head.width_ratio": round(identity.head.width_ratio * 1.1, 4)},
        ),
        ViewDefinition(view=TurnaroundView.THREE_QUARTER_BACK, z_order=dict(back)),
        ViewDefinition(view=TurnaroundView.BACK, z_order=dict(back)),
    ]
    return TemplateResult(parts, rig, TurnaroundSet(views=views))


TEMPLATES: dict[str, Template] = {
    "biped": Template(
        "biped",
        "Full humanoid: head, neck, ears, hair, upper torso, chest, waist, pelvis, arms, "
        "hands, legs, feet; 16-bone rig (root control + 15) with arm and leg IK chains",
        lambda cid, ident: _build_biped(cid, ident, minimal=False),
    ),
    "biped-minimal": Template(
        "biped-minimal",
        "Simplified humanoid without ears, hair, chest or waist parts (same rig)",
        lambda cid, ident: _build_biped(cid, ident, minimal=True),
    ),
}


def get_template(name: str) -> Template:
    try:
        return TEMPLATES[name]
    except KeyError:
        known = ", ".join(sorted(TEMPLATES))
        raise CharacterError(f"unknown template {name!r} (known: {known})") from None
