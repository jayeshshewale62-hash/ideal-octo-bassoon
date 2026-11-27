"""Rig validation: reports every structural problem with a code (RIG0xx, IK0xx).

Validation never modifies the rig. Codes are documented in docs/DATA_SCHEMAS.md.
"""

from __future__ import annotations

from studio.core.validation import ValidationReport
from studio.rig.schemas import BendDirection, RigDefinition

TIP_TOLERANCE = 1e-6


def _ancestors_cycle(bones: dict[str, str | None]) -> list[str]:
    """Bones that take part in a parent cycle."""
    in_cycle: set[str] = set()
    for start in bones:
        seen: list[str] = []
        current: str | None = start
        while current is not None and current in bones:
            if current in seen:
                in_cycle.update(seen[seen.index(current) :])
                break
            seen.append(current)
            current = bones[current]
    return sorted(in_cycle)


def validate_rig(rig: RigDefinition, report: ValidationReport, where: str = "rig.yaml") -> None:
    ids = [b.id for b in rig.bones]
    report.checks += 1
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    for dup in duplicates:
        report.error("RIG001", f"duplicate bone id {dup!r}", where)
    bones = rig.bone_map()
    parents = {b.id: b.parent for b in bones.values()}

    report.checks += 1
    if not bones:
        report.error("RIG002", "rig has no bones", where)
        return
    if rig.root not in bones:
        report.error("RIG002", f"root bone {rig.root!r} is not defined", where)
    elif bones[rig.root].parent is not None:
        report.error("RIG003", f"root bone {rig.root!r} must not have a parent", where)
    for bone in bones.values():
        if bone.id != rig.root and bone.parent is None:
            report.error("RIG003", f"bone {bone.id!r} has no parent but is not the root", where)
        if bone.parent is not None and bone.parent not in bones:
            report.error(
                "RIG004", f"bone {bone.id!r}: parent {bone.parent!r} does not exist", where
            )
        if bone.parent == bone.id:
            report.error("RIG005", f"bone {bone.id!r} is its own parent", where)

    report.checks += 1
    cycle = _ancestors_cycle(parents)
    if cycle:
        report.error("RIG005", "circular parent relationship: " + ", ".join(cycle), where)

    # reachability from root
    report.checks += 1
    if rig.root in bones:
        children: dict[str, list[str]] = {b: [] for b in bones}
        for b, p in parents.items():
            if p in children and b != rig.root:
                children[p].append(b)
        reached, stack = set(), [rig.root]
        while stack:
            cur = stack.pop()
            if cur in reached:
                continue
            reached.add(cur)
            stack.extend(children[cur])
        detached = sorted(set(bones) - reached - set(cycle))
        if detached:
            report.error("RIG006", "bones not connected to the root: " + ", ".join(detached), where)

    for bone in bones.values():
        report.checks += 1
        loc = f"{where}: {bone.id}"
        if bone.length == 0 and not bone.control and bone.id != rig.root:
            report.error(
                "RIG007", "bone length is zero (mark helper bones with control: true)", loc
            )
        c = bone.constraint
        if c is None:
            continue
        if c.min_rotation > c.max_rotation:
            report.error(
                "RIG008", f"min_rotation {c.min_rotation} > max_rotation {c.max_rotation}", loc
            )
            continue
        if c.max_rotation - c.min_rotation > 360:
            report.warning("RIG011", "rotation range wider than 360 degrees has no effect", loc)
        rest = bone.rest.rotation
        if not c.locked and not (c.min_rotation <= rest <= c.max_rotation):
            report.error(
                "RIG009",
                f"rest rotation {rest} is outside [{c.min_rotation}, {c.max_rotation}]",
                loc,
            )
        if c.locked and (c.min_rotation, c.max_rotation) != (-180.0, 180.0):
            report.warning("RIG010", "locked joint: min/max limits are ignored", loc)
        if c.preferred_bend is BendDirection.POSITIVE and c.max_rotation < 0:
            report.error("RIG012", "preferred_bend positive but max_rotation < 0", loc)
        if c.preferred_bend is BendDirection.NEGATIVE and c.min_rotation > 0:
            report.error("RIG012", "preferred_bend negative but min_rotation > 0", loc)

    control_ids = [h.id for h in rig.controls]
    for handle in rig.controls:
        report.checks += 1
        if control_ids.count(handle.id) > 1:
            report.error("RIG013", f"duplicate control id {handle.id!r}", where)
        if handle.bone is not None and handle.bone not in bones:
            report.error(
                "RIG013", f"control {handle.id!r} names unknown bone {handle.bone!r}", where
            )

    _validate_chains(rig, report, where, set(control_ids))


def _validate_chains(
    rig: RigDefinition, report: ValidationReport, where: str, controls: set[str]
) -> None:
    bones = rig.bone_map()
    chain_ids = [c.id for c in rig.ik_chains]
    for chain in rig.ik_chains:
        report.checks += 1
        loc = f"{where}: ik {chain.id}"
        if chain_ids.count(chain.id) > 1:
            report.error("IK005", f"duplicate IK chain id {chain.id!r}", loc)
        upper, lower = bones.get(chain.upper), bones.get(chain.lower)
        missing = [n for n, b in ((chain.upper, upper), (chain.lower, lower)) if b is None]
        if missing:
            report.error("IK001", "unknown bone(s): " + ", ".join(missing), loc)
            continue
        assert upper is not None and lower is not None
        if lower.parent != upper.id:
            report.error("IK002", f"{lower.id!r} must be a direct child of {upper.id!r}", loc)
            continue
        if abs(lower.rest.x - upper.length) > TIP_TOLERANCE or abs(lower.rest.y) > TIP_TOLERANCE:
            report.warning(
                "IK003",
                f"{lower.id!r} is not attached at the tip of {upper.id!r}; "
                "the solver uses the actual joint positions",
                loc,
            )
        if upper.length <= 0 or lower.length <= 0:
            report.error("IK004", "IK segments must have positive length", loc)
        lc = lower.constraint
        if lc is not None and lc.preferred_bend is not None and lc.preferred_bend != chain.bend:
            report.error(
                "IK006",
                f"chain bend {chain.bend.value!r} contradicts {lower.id!r} preferred_bend "
                f"{lc.preferred_bend.value!r}",
                loc,
            )
        if lc is not None and not lc.locked:
            if chain.bend is BendDirection.POSITIVE and lc.max_rotation <= 0:
                report.error(
                    "IK006", f"positive bend impossible: {lower.id!r} max_rotation <= 0", loc
                )
            if chain.bend is BendDirection.NEGATIVE and lc.min_rotation >= 0:
                report.error(
                    "IK006", f"negative bend impossible: {lower.id!r} min_rotation >= 0", loc
                )
        for b in (upper, lower):
            if b.constraint is not None and b.constraint.locked:
                report.warning("IK007", f"{b.id!r} is locked; IK cannot move it", loc)
            if abs(abs(b.rest.scale_x) - abs(b.rest.scale_y)) > 1e-9:
                report.warning("IK008", f"{b.id!r} has non-uniform scale; IK may be inexact", loc)
        for ref in (chain.target_control, chain.pole_control):
            if ref is not None and ref not in controls:
                report.error("IK009", f"control {ref!r} is not defined", loc)
