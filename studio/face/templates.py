"""Facial rig templates. Structure only: no facial artwork is created.

The ``standard`` template builds eyes, brows, mouth, jaw and optional cheeks and nose,
sized from the character's head part. Channels are mostly *normalized* (relative to the
component size) so expressions and visemes transfer between characters of any scale.
"""

from __future__ import annotations

from studio.characters.schemas import CharacterDefinition
from studio.core.exceptions import FaceError
from studio.face.schemas import (
    ComponentKind,
    FaceAnchor,
    FacialChannel,
    FacialComponent,
    FacialRig,
)
from studio.rig.schemas import Point2D

TEMPLATES = ("standard", "minimal")


def _ch(name: str, lo: float, hi: float, default: float, unit: str, text: str) -> FacialChannel:
    return FacialChannel.model_validate(
        {"name": name, "min": lo, "max": hi, "default": default, "unit": unit, "description": text}
    )


def eye_channels() -> list[FacialChannel]:
    return [
        _ch("offset_x", -0.5, 0.5, 0, "normalized", "horizontal shift, x eye width"),
        _ch("offset_y", -0.5, 0.5, 0, "normalized", "vertical shift, x eye height (+ down)"),
        _ch("scale", 0.5, 1.5, 1, "ratio", "eye size"),
        _ch("rotation", -30, 30, 0, "degrees", "eye tilt (+ clockwise on screen)"),
        _ch("pupil_x", -1, 1, 0, "normalized", "gaze left(-)/right(+)"),
        _ch("pupil_y", -1, 1, 0, "normalized", "gaze up(-)/down(+)"),
        _ch("pupil_scale", 0.5, 1.5, 1, "ratio", "pupil size"),
        _ch("blink", 0, 1, 0, "normalized", "upper lid closure (1 = closed)"),
        _ch("squint", 0, 1, 0, "normalized", "lower lid raise"),
        _ch("visible", 0, 1, 1, "toggle", "eye drawn (0/1)"),
    ]


def brow_channels() -> list[FacialChannel]:
    return [
        _ch("offset_x", -0.5, 0.5, 0, "normalized", "horizontal shift, x brow width"),
        _ch("raise", -1, 1, 0, "normalized", "vertical movement (+ up)"),
        _ch("rotation", -30, 30, 0, "degrees", "brow tilt (+ clockwise on screen)"),
        _ch("scale", 0.6, 1.4, 1, "ratio", "brow length"),
        _ch("shape", -1, 1, 0, "normalized", "curve: -1 angled down, +1 arched"),
    ]


def mouth_channels() -> list[FacialChannel]:
    return [
        _ch("offset_x", -0.5, 0.5, 0, "normalized", "horizontal shift, x mouth width"),
        _ch("offset_y", -0.5, 0.5, 0, "normalized", "vertical shift (+ down)"),
        _ch("width", 0.5, 1.6, 1, "ratio", "mouth width"),
        _ch("height", 0.5, 1.6, 1, "ratio", "mouth height when open"),
        _ch("open", 0, 1, 0, "normalized", "lip opening"),
        _ch("corner_l", -1, 1, 0, "normalized", "left corner down(-)/up(+)"),
        _ch("corner_r", -1, 1, 0, "normalized", "right corner down(-)/up(+)"),
        _ch("upper_lip", -1, 1, 0, "normalized", "upper lip pressed(-)/raised(+)"),
        _ch("lower_lip", -1, 1, 0, "normalized", "lower lip pressed(-)/lowered(+)"),
        _ch("pucker", 0, 1, 0, "normalized", "lips pushed forward / rounded"),
    ]


def jaw_channels() -> list[FacialChannel]:
    return [
        _ch("open", 0, 1, 0, "normalized", "jaw drop"),
        _ch("offset_x", -0.5, 0.5, 0, "normalized", "sideways shift"),
    ]


def cheek_channels() -> list[FacialChannel]:
    return [
        _ch("raise", 0, 1, 0, "normalized", "cheek lift (smile)"),
        _ch("puff", 0, 1, 0, "normalized", "cheek puff"),
    ]


def nose_channels() -> list[FacialChannel]:
    return [
        _ch("wrinkle", 0, 1, 0, "normalized", "nose wrinkle"),
        _ch("offset_y", -0.5, 0.5, 0, "normalized", "vertical shift"),
        _ch("scale", 0.8, 1.2, 1, "ratio", "nose size"),
    ]


MOUTH_SHAPES = ("rest", "mbp", "ai", "e", "ee", "o", "u", "ch", "st", "fv", "th", "l", "k", "r")


def build_face(
    character: CharacterDefinition, template: str = "standard", head_part: str = "head"
) -> FacialRig:
    if template not in TEMPLATES:
        raise FaceError(f"unknown face template {template!r} (known: {', '.join(TEMPLATES)})")
    head = character.part_map().get(head_part)
    if head is None:
        raise FaceError(f"{character.id} has no part {head_part!r} to attach a face to")
    if head.bounds is None:
        raise FaceError(f"part {head_part!r} has no bounds; cannot size the face")
    # The biped head part is drawn along its bone: artwork x = up the head, y = across it.
    length, width = head.bounds.width, head.bounds.height
    u = min(length, width)  # face unit
    anchor = FaceAnchor(
        part=head_part, position=Point2D(x=round(0.42 * length, 4), y=round(width / 2, 4))
    )

    def comp(
        cid: str,
        kind: ComponentKind,
        side: str,
        x: float,
        y: float,
        w: float,
        h: float,
        channels: list[FacialChannel],
        optional: bool = False,
    ) -> FacialComponent:
        return FacialComponent.model_validate(
            {
                "id": cid,
                "kind": kind,
                "side": side,
                "position": {"x": round(x * u, 4), "y": round(y * u, 4)},
                "size": (round(w * u, 4), round(h * u, 4)),
                "channels": [c.model_dump() for c in channels],
                "optional": optional,
            }
        )

    components = [
        comp("eye_l", ComponentKind.EYE, "left", 0.2, -0.08, 0.16, 0.14, eye_channels()),
        comp("eye_r", ComponentKind.EYE, "right", -0.2, -0.08, 0.16, 0.14, eye_channels()),
        comp("brow_l", ComponentKind.BROW, "left", 0.2, -0.22, 0.2, 0.04, brow_channels()),
        comp("brow_r", ComponentKind.BROW, "right", -0.2, -0.22, 0.2, 0.04, brow_channels()),
        comp("mouth", ComponentKind.MOUTH, "center", 0.0, 0.22, 0.3, 0.1, mouth_channels()),
        comp("jaw", ComponentKind.JAW, "center", 0.0, 0.34, 0.4, 0.1, jaw_channels()),
    ]
    components[4] = components[4].model_copy(update={"shapes": dict.fromkeys(MOUTH_SHAPES)})
    if template == "standard":
        components += [
            comp(
                "cheek_l",
                ComponentKind.CHEEK,
                "left",
                0.27,
                0.1,
                0.12,
                0.08,
                cheek_channels(),
                True,
            ),
            comp(
                "cheek_r",
                ComponentKind.CHEEK,
                "right",
                -0.27,
                0.1,
                0.12,
                0.08,
                cheek_channels(),
                True,
            ),
            comp("nose", ComponentKind.NOSE, "center", 0.0, 0.06, 0.1, 0.12, nose_channels(), True),
        ]
    return FacialRig(
        id="face_" + character.id.removeprefix("chr_").replace("-", "_"),
        character_id=character.id,
        template=template,
        anchor=anchor,
        components=components,
        notes="Generated face structure; no artwork. Edit positions, sizes and limits freely.",
    )
