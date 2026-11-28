"""Resolve control values into facial geometry (face space: +x right, +y down).

This turns a :class:`FaceState` into concrete positions, sizes and shapes per
component. Previews draw this today; the renderer will use it to place and deform
facial parts in later milestones. The formulas are documented in docs/FACE.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from studio.face.expressions import FaceState
from studio.face.schemas import ComponentKind, FacialComponent, FacialRig
from studio.rig.math2d import Vec2


@dataclass(frozen=True)
class ResolvedComponent:
    id: str
    kind: ComponentKind
    center: Vec2
    rotation: float
    size: tuple[float, float]
    params: dict[str, float] = field(default_factory=dict)
    visible: bool = True
    shape: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "center": list(self.center.rounded(4)),
            "rotation": round(self.rotation, 4),
            "size": [round(self.size[0], 4), round(self.size[1], 4)],
            "visible": self.visible,
            "shape": self.shape,
            "params": {k: round(v, 4) for k, v in sorted(self.params.items())},
        }


def _v(state: FaceState, comp: FacialComponent, name: str, fallback: float) -> float:
    return state.values.get(f"{comp.id}.{name}", fallback)


def resolve_face(rig: FacialRig, state: FaceState) -> dict[str, ResolvedComponent]:
    out: dict[str, ResolvedComponent] = {}
    jaw = next((c for c in rig.components if c.kind is ComponentKind.JAW), None)
    jaw_open = _v(state, jaw, "open", 0.0) if jaw else 0.0
    for comp in rig.components:
        w0, h0 = comp.size
        p = Vec2(comp.position.x, comp.position.y)

        def g(name: str, fb: float = 0.0, _c: FacialComponent = comp) -> float:
            return _v(state, _c, name, fb)

        shape = state.shapes.get(comp.id)
        if comp.kind is ComponentKind.EYE:
            s = g("scale", 1.0)
            center = p + Vec2(g("offset_x") * w0, g("offset_y") * h0)
            w, h = w0 * s, h0 * s
            px, py = g("pupil_x"), g("pupil_y")
            openness = max(0.0, 1.0 - g("blink")) * (1.0 - 0.5 * g("squint"))
            params = {
                "openness": openness,
                "upper_lid_y": center.y - h / 2 + h * g("blink"),
                "lower_lid_y": center.y + h / 2 - h * 0.5 * g("squint"),
                "pupil_x": center.x + px * 0.3 * w,
                "pupil_y": center.y + py * 0.3 * h,
                "pupil_radius": 0.22 * min(w, h) * g("pupil_scale", 1.0),
                "gaze_angle": math.degrees(math.atan2(py, px)) if (px or py) else 0.0,
                "gaze_amount": min(1.0, math.hypot(px, py)),
            }
            out[comp.id] = ResolvedComponent(
                comp.id,
                comp.kind,
                center,
                g("rotation"),
                (w, h),
                params,
                g("visible", 1.0) >= 0.5,
                shape,
            )
        elif comp.kind is ComponentKind.BROW:
            length = w0 * g("scale", 1.0)
            center = p + Vec2(g("offset_x") * w0, -g("raise") * 0.35 * w0)
            params = {"length": length, "arch": g("shape") * 0.25 * length, "thickness": h0}
            out[comp.id] = ResolvedComponent(
                comp.id, comp.kind, center, g("rotation"), (length, h0), params, True, shape
            )
        elif comp.kind is ComponentKind.MOUTH:
            center = p + Vec2(g("offset_x") * w0, g("offset_y") * h0 + jaw_open * 0.25 * h0)
            width = w0 * g("width", 1.0) * (1.0 - 0.35 * g("pucker"))
            gap = max(0.0, h0 * g("height", 1.0) * (g("open") + 0.5 * jaw_open))
            params = {
                "width": width,
                "gap": gap,
                "corner_l_y": -g("corner_l") * 0.35 * h0,
                "corner_r_y": -g("corner_r") * 0.35 * h0,
                "upper_lip_y": -gap / 2 - g("upper_lip") * 0.2 * h0,
                "lower_lip_y": gap / 2 + g("lower_lip") * 0.2 * h0,
                "pucker": g("pucker"),
            }
            out[comp.id] = ResolvedComponent(
                comp.id, comp.kind, center, 0.0, (width, gap), params, True, shape
            )
        elif comp.kind is ComponentKind.JAW:
            center = p + Vec2(g("offset_x") * w0, g("open") * 0.5 * h0)
            out[comp.id] = ResolvedComponent(
                comp.id,
                comp.kind,
                center,
                0.0,
                (w0, h0),
                {"drop": g("open") * 0.5 * h0},
                True,
                shape,
            )
        elif comp.kind is ComponentKind.CHEEK:
            center = p + Vec2(0.0, -g("raise") * 0.3 * h0)
            k = 1.0 + 0.3 * g("puff")
            out[comp.id] = ResolvedComponent(
                comp.id,
                comp.kind,
                center,
                0.0,
                (w0 * k, h0 * k),
                {"raise": g("raise"), "puff": g("puff")},
                True,
                shape,
            )
        elif comp.kind is ComponentKind.NOSE:
            k = g("scale", 1.0)
            center = p + Vec2(0.0, g("offset_y") * h0)
            out[comp.id] = ResolvedComponent(
                comp.id,
                comp.kind,
                center,
                0.0,
                (w0 * k, h0 * k),
                {"wrinkle": g("wrinkle")},
                True,
                shape,
            )
        else:  # accessory / custom: raw channel values, no built-in geometry
            raw = {ch.name: g(ch.name, ch.default) for ch in comp.channels}
            out[comp.id] = ResolvedComponent(
                comp.id,
                comp.kind,
                p,
                raw.get("rotation", 0.0),
                (w0, h0),
                raw,
                raw.get("visible", 1.0) >= 0.5,
                shape,
            )
    return out
