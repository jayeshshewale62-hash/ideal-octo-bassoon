"""Versioned character data contract (``characters/<character-id>/character.yaml``).

A character is **editable components plus data**, never a flattened picture:

* ``identity``  canonical identity profile (proportions, head, palette, clothing, hair,
  distinctive features), checked by the consistency manager;
* ``parts``     body-part hierarchy: each part has a parent, local transform, pivot,
  visibility, opacity, draw order, an optional rig-bone binding and optional artwork
  (a registered asset ID);
* ``views``     turnaround views (front, three-quarter front, side, three-quarter back,
  back). Each view has its own artwork and per-view overrides, under one shared identity;
* ``rig``       the ID of the rig stored next to it in ``rig.yaml``.

Field-level rules live in the models. Cross-references (parents, bones, assets, views,
identity overrides) are checked by :mod:`studio.characters.validation`, which reports
every problem with a code.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from studio.core.schemas import (
    AssetLicense,
    AssetSource,
    CharacterProportions,
    CharacterStatus,
    CharacterVoice,
    HexColor,
    TurnaroundView,
)
from studio.rig.schemas import (
    BoneDefinition,
    GeometryModel,
    IKChain,
    JointConstraint,
    Point2D,
    RigDefinition,
    Transform2D,
)

CHARACTER_ID = r"^chr_[a-z0-9][a-z0-9_-]{1,47}$"
PART_ID = r"^[a-z][a-z0-9_]{0,47}$"
ASSET_ID = r"^ast_[0-9a-f]{16}$"
ALL_VIEWS: tuple[TurnaroundView, ...] = (
    TurnaroundView.FRONT,
    TurnaroundView.THREE_QUARTER,
    TurnaroundView.SIDE,
    TurnaroundView.THREE_QUARTER_BACK,
    TurnaroundView.BACK,
)

PartId = Annotated[str, Field(pattern=PART_ID)]
AssetId = Annotated[str, Field(pattern=ASSET_ID)]
ShortText = Annotated[str, Field(max_length=200)]
IdentityValue = float | int | str | list[str]


class PartKind(StrEnum):
    HEAD = "head"
    NECK = "neck"
    EAR = "ear"
    HAIR = "hair"
    HEAD_ACCESSORY = "head_accessory"
    CHEST = "chest"
    UPPER_TORSO = "upper_torso"
    WAIST = "waist"
    PELVIS = "pelvis"  # lower torso
    UPPER_ARM = "upper_arm"
    FOREARM = "forearm"
    HAND = "hand"
    THIGH = "thigh"
    LOWER_LEG = "lower_leg"
    FOOT = "foot"
    ACCESSORY = "accessory"
    CUSTOM = "custom"


class Side(StrEnum):
    LEFT = "left"  # the character's own left
    RIGHT = "right"
    CENTER = "center"


class AttachmentPoint(GeometryModel):
    """Named point in a part's artwork space where child parts can attach."""

    name: Annotated[str, Field(pattern=PART_ID)]
    position: Point2D = Field(default_factory=Point2D)


class Bounds(GeometryModel):
    """Artwork box in the part's own coordinates (used by diagnostics and validation)."""

    x: float = 0.0
    y: float = 0.0
    width: Annotated[float, Field(gt=0, le=100_000)]
    height: Annotated[float, Field(gt=0, le=100_000)]


class DeformationMode(StrEnum):
    RIGID = "rigid"
    MESH = "mesh"
    WARP = "warp"


class DeformationMetadata(GeometryModel):
    """Metadata only in Milestone 3: deformers are evaluated in a later milestone."""

    mode: DeformationMode = DeformationMode.RIGID
    grid: tuple[Annotated[int, Field(ge=1, le=64)], Annotated[int, Field(ge=1, le=64)]] = (1, 1)
    weighted_bones: list[Annotated[str, Field(pattern=PART_ID)]] = Field(default_factory=list)


class PartDefinition(GeometryModel):
    id: PartId
    label: ShortText = ""
    kind: PartKind = PartKind.CUSTOM
    side: Side = Side.CENTER
    parent: PartId | None = None
    parent_attachment: Annotated[str, Field(pattern=PART_ID)] | None = None
    bone: Annotated[str, Field(pattern=PART_ID)] | None = None
    transform: Transform2D = Field(default_factory=Transform2D)
    pivot: Point2D = Field(default_factory=Point2D)
    bounds: Bounds | None = None
    visible: bool = True
    opacity: Annotated[float, Field(ge=0, le=1)] = 1.0
    z_order: Annotated[int, Field(ge=-10_000, le=10_000)]
    asset: AssetId | None = None
    attachment_points: list[AttachmentPoint] = Field(default_factory=list)
    deformation: DeformationMetadata | None = None
    optional: bool = False  # e.g. ears or hair: may have no artwork yet


class IdentityRole(StrEnum):
    """How strictly an identity property must stay the same."""

    REQUIRED = "required"  # must match across views and variants
    OPTIONAL = "optional"  # differences are reported as warnings
    VIEW_SPECIFIC = "view_specific"  # expected to differ between turnaround views
    VARIATION = "variation"  # editable artistic variation (e.g. an outfit change)


class HeadProfile(GeometryModel):
    shape: Literal["round", "oval", "square", "triangle", "heart", "pear", "custom"] = "round"
    width_ratio: Annotated[float, Field(gt=0.2, le=3)] = 0.9  # head width / head height


class IdentityProfile(GeometryModel):
    height_units: Annotated[float, Field(gt=0, le=100_000)] = 1000.0  # design-space height
    proportions: CharacterProportions
    head: HeadProfile = Field(default_factory=HeadProfile)
    palette: dict[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")], HexColor] = Field(
        default_factory=dict
    )
    clothing: list[ShortText] = Field(default_factory=list)
    hair: ShortText = ""
    distinctive_features: list[ShortText] = Field(default_factory=list)
    personality: list[ShortText] = Field(default_factory=list)
    voice: CharacterVoice = Field(default_factory=CharacterVoice)
    policy: dict[Annotated[str, Field(min_length=1, max_length=80)], IdentityRole] = Field(
        default_factory=dict
    )
    original_design: bool = True

    @field_validator("original_design")
    @classmethod
    def _original_only(cls, value: bool) -> bool:
        if not value:
            raise ValueError("only original character designs are allowed")
        return value


class VisualStyle(GeometryModel):
    line_color: HexColor = "#1A1A1A"
    line_width: Annotated[float, Field(gt=0, le=64)] = 4.0
    line_taper: Annotated[float, Field(ge=0, le=1)] = 0.6  # 0 = uniform, 1 = fully tapered ends
    line_irregularity: Annotated[float, Field(ge=0, le=1)] = 0.15
    line_boil_variants: Annotated[int, Field(ge=0, le=3)] = 0
    fill: Literal["flat", "cel", "none"] = "flat"


class ViewDefinition(GeometryModel):
    view: TurnaroundView
    artwork: AssetId | None = None  # full drawing of this view, if any
    part_assets: dict[PartId, AssetId] = Field(default_factory=dict)
    hidden_parts: list[PartId] = Field(default_factory=list)
    z_order: dict[PartId, Annotated[int, Field(ge=-10_000, le=10_000)]] = Field(
        default_factory=dict
    )
    part_transforms: dict[PartId, Transform2D] = Field(default_factory=dict)
    identity_overrides: dict[Annotated[str, Field(min_length=1, max_length=80)], IdentityValue] = (
        Field(default_factory=dict)
    )
    notes: Annotated[str, Field(max_length=2000)] = ""


class TurnaroundSet(GeometryModel):
    required_views: list[TurnaroundView] = Field(default_factory=lambda: list(ALL_VIEWS))
    views: list[ViewDefinition] = Field(default_factory=list)

    def get(self, view: TurnaroundView) -> ViewDefinition | None:
        return next((v for v in self.views if v.view == view), None)


class CharacterProvenance(GeometryModel):
    source: AssetSource = Field(default_factory=AssetSource)
    license: AssetLicense = Field(default_factory=AssetLicense)
    created_at: datetime
    updated_at: datetime
    studio_version: Annotated[str, Field(min_length=1, max_length=40)]


class CharacterDefinition(GeometryModel):
    schema_version: Literal[1] = 1
    id: Annotated[str, Field(pattern=CHARACTER_ID)]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(max_length=4000)] = ""
    version: Annotated[int, Field(ge=1)] = 1
    project_id: Annotated[str, Field(pattern=r"^prj_[0-9a-f]{32}$")]
    status: CharacterStatus = CharacterStatus.CONCEPT
    template: Annotated[str, Field(max_length=60)] | None = None
    identity: IdentityProfile
    style: VisualStyle = Field(default_factory=VisualStyle)
    parts: list[PartDefinition] = Field(default_factory=list)
    turnaround: TurnaroundSet = Field(default_factory=TurnaroundSet)
    rig: Annotated[str, Field(pattern=r"^rig_[a-z0-9][a-z0-9_]{1,47}$")] | None = None
    face: Annotated[str, Field(pattern=r"^face_[a-z0-9][a-z0-9_]{1,47}$")] | None = None  # M4
    model_sheet_asset: AssetId | None = None
    provenance: CharacterProvenance
    metadata: dict[Annotated[str, Field(min_length=1, max_length=60)], str | int | float | bool] = (
        Field(default_factory=dict)
    )

    def part_map(self) -> dict[str, PartDefinition]:
        result: dict[str, PartDefinition] = {}
        for part in self.parts:
            result.setdefault(part.id, part)
        return result


CHARACTER_SCHEMAS: dict[str, type[BaseModel]] = {
    "character_definition": CharacterDefinition,
    "character_identity_profile": IdentityProfile,
    "character_part": PartDefinition,
    "turnaround": TurnaroundSet,
    "turnaround_view": ViewDefinition,
    "rig": RigDefinition,
    "bone": BoneDefinition,
    "joint_constraint": JointConstraint,
    "ik_chain": IKChain,
    "transform_2d": Transform2D,
}
"""Milestone 3 schemas exported by ``studio schema export`` (in addition to core SCHEMAS)."""
