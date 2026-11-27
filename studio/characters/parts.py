"""Part hierarchy: world transforms, visibility, opacity and draw order.

For a part with local transform ``T`` and pivot ``p`` (in its artwork coordinates):

    frame    = anchor @ TRS(T)            the part's frame; its origin is where the pivot sits
    artwork  = frame @ translate(-p)      maps artwork coordinates to character space

The anchor is chosen in this order:

1. ``bone`` set      -> the bone's FK world matrix (origin at the bone head);
2. ``parent`` set    -> the parent's ``frame``, or the parent's artwork-space attachment
   point if ``parent_attachment`` names one;
3. neither           -> character space (identity).

A parent's transform therefore propagates to all of its descendants. Visibility is
inherited (a hidden parent hides its children) and opacity multiplies down the tree.
Draw order is ascending ``z_order`` (a view may override it), with ties broken by part
ID so output is always deterministic. Validation reports duplicate values (PRT005).
"""

from __future__ import annotations

from dataclasses import dataclass

from studio.characters.schemas import CharacterDefinition, PartDefinition, ViewDefinition
from studio.core.exceptions import CharacterError
from studio.rig.fk import FKResult
from studio.rig.math2d import Affine, Vec2


@dataclass(frozen=True)
class PartWorld:
    id: str
    frame: Affine
    artwork: Affine
    visible: bool
    opacity: float
    z_order: int
    asset: str | None

    @property
    def pivot_world(self) -> Vec2:
        return self.frame.origin

    def to_dict(self) -> dict[str, object]:
        return {
            "part": self.id,
            "pivot": list(self.pivot_world.rounded(4)),
            "rotation": round(self.frame.rotation_degrees, 4),
            "scale": [round(v, 6) for v in self.frame.scale],
            "visible": self.visible,
            "opacity": round(self.opacity, 4),
            "z_order": self.z_order,
            "asset": self.asset,
            "artwork_matrix": self.artwork.svg(),
        }


def part_order(character: CharacterDefinition) -> list[str]:
    """Parents before children (siblings by ID). Raises CharacterError on bad hierarchies."""
    parts = character.part_map()
    if len(parts) != len(character.parts):
        raise CharacterError("duplicate part IDs; run 'studio character validate'")
    children: dict[str | None, list[str]] = {None: []}
    for part in parts.values():
        if part.parent is not None and part.parent not in parts:
            raise CharacterError(f"part {part.id!r} has unknown parent {part.parent!r}")
        children.setdefault(part.parent, []).append(part.id)
    order: list[str] = []
    stack = sorted(children[None], reverse=True)
    while stack:
        current = stack.pop()
        order.append(current)
        stack.extend(sorted(children.get(current, []), reverse=True))
    if len(order) != len(parts):
        cyc = sorted(set(parts) - set(order))
        raise CharacterError("circular part hierarchy: " + ", ".join(cyc))
    return order


def _attachment(parent: PartDefinition, name: str) -> Vec2:
    for point in parent.attachment_points:
        if point.name == name:
            return Vec2(point.position.x, point.position.y)
    raise CharacterError(f"part {parent.id!r} has no attachment point {name!r}")


def solve_parts(
    character: CharacterDefinition,
    fk: FKResult | None = None,
    view: ViewDefinition | None = None,
) -> dict[str, PartWorld]:
    """World transforms of every part for one view (``None`` = the base definition)."""
    parts = character.part_map()
    hidden = set(view.hidden_parts) if view else set()
    result: dict[str, PartWorld] = {}
    for part_id in part_order(character):
        part = parts[part_id]
        transform = view.part_transforms.get(part_id, part.transform) if view else part.transform
        if part.bone is not None:
            if fk is None or part.bone not in fk.bones:
                raise CharacterError(f"part {part_id!r} is bound to bone {part.bone!r}, not in rig")
            anchor = fk[part.bone].matrix
        elif part.parent is not None:
            parent_world = result[part.parent]
            if part.parent_attachment:
                point = _attachment(parts[part.parent], part.parent_attachment)
                anchor = parent_world.artwork @ Affine.translation(point.x, point.y)
            else:
                anchor = parent_world.frame
        else:
            anchor = Affine.identity()
        frame = anchor @ Affine.from_trs(
            transform.x, transform.y, transform.rotation, transform.scale_x, transform.scale_y
        )
        artwork = frame @ Affine.translation(-part.pivot.x, -part.pivot.y)
        parent_pw = result.get(part.parent) if part.parent else None
        visible = part.visible and part_id not in hidden
        opacity = part.opacity
        if parent_pw is not None:
            visible = visible and parent_pw.visible
            opacity *= parent_pw.opacity
        z = view.z_order.get(part_id, part.z_order) if view else part.z_order
        asset = view.part_assets.get(part_id, part.asset) if view else part.asset
        result[part_id] = PartWorld(part_id, frame, artwork, visible, opacity, z, asset)
    return result


def draw_order(parts: dict[str, PartWorld], *, include_hidden: bool = False) -> list[str]:
    """Back-to-front order: ascending z_order, ties by part ID."""
    chosen = [p for p in parts.values() if include_hidden or p.visible]
    return [p.id for p in sorted(chosen, key=lambda p: (p.z_order, p.id))]
