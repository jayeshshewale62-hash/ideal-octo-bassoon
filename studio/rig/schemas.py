"""Versioned rig data contract (``characters/<character-id>/rig.yaml``).

Bone convention (docs/RIGGING.md):

* A bone's local frame has its **origin at the bone's head (joint)**. The bone points
  along its local **+x axis**, so its tip is at ``(length, 0)`` in local space.
* ``rest.x``/``rest.y`` place the bone's head **in the parent bone's local frame**: a
  child attached at the tip of its parent has ``rest = {x: parent.length, y: 0}``.
* ``rest.rotation`` is the bone's rotation relative to its parent, in degrees
  (screen space, +y down, positive = clockwise on screen).

Field-level rules (types, finite numbers, ranges) are enforced by the models.
Cross-references (parents, cycles, constraints vs rest pose, IK chain topology) are
checked by :mod:`studio.rig.validation`, which reports *all* problems with codes instead
of stopping at the first.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ID = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")]
Finite = Annotated[float, Field(allow_inf_nan=False)]
Degrees = Annotated[float, Field(ge=-720, le=720, allow_inf_nan=False)]
NonZeroScale = Annotated[float, Field(allow_inf_nan=False, ge=-100, le=100)]


class GeometryModel(BaseModel):
    """Strict model that also rejects NaN and infinity in every float field."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True, allow_inf_nan=False)


class Point2D(GeometryModel):
    x: Finite = 0.0
    y: Finite = 0.0


class Transform2D(GeometryModel):
    """Local transform: translate (x, y), then rotate, then scale (scale applied first)."""

    x: Finite = 0.0
    y: Finite = 0.0
    rotation: Degrees = 0.0
    scale_x: NonZeroScale = 1.0
    scale_y: NonZeroScale = 1.0

    @field_validator("scale_x", "scale_y")
    @classmethod
    def _non_zero(cls, value: float) -> float:
        if abs(value) < 1e-6:
            raise ValueError("scale must not be zero (the transform would collapse)")
        return value


class BendDirection(StrEnum):
    """Sign of the lower bone's local rotation when an IK chain bends."""

    POSITIVE = "positive"  # lower bone rotates clockwise on screen relative to the upper
    NEGATIVE = "negative"


class JointConstraint(GeometryModel):
    """Limits on a bone's *local* rotation (relative to its parent), in degrees."""

    min_rotation: Degrees = -180.0
    max_rotation: Degrees = 180.0
    locked: bool = False  # the joint keeps its rest rotation
    preferred_bend: BendDirection | None = None


class BoneDefinition(GeometryModel):
    id: ID
    parent: ID | None = None
    length: Annotated[float, Field(ge=0, le=100_000, allow_inf_nan=False)]
    rest: Transform2D = Field(default_factory=Transform2D)
    constraint: JointConstraint | None = None
    inherit_rotation: bool = True
    inherit_scale: bool = True
    control: bool = False  # helper bone (may have zero length)
    label: Annotated[str, Field(max_length=80)] = ""


class IKChain(GeometryModel):
    """Two-bone chain: ``upper`` -> ``lower``. The end effector is the tip of ``lower``."""

    id: ID
    upper: ID
    lower: ID
    bend: BendDirection = BendDirection.POSITIVE
    target_control: ID | None = None
    pole_control: ID | None = None


class ControlHandle(GeometryModel):
    id: ID
    kind: Literal["ik_target", "pole", "fk"]
    bone: ID | None = None  # bone the handle is attached to (fk) or drives (ik_target)
    position: Point2D = Field(default_factory=Point2D)  # character space


class RigDefinition(GeometryModel):
    schema_version: Literal[1] = 1
    id: Annotated[str, Field(pattern=r"^rig_[a-z0-9][a-z0-9_]{1,47}$")]
    version: Annotated[int, Field(ge=1)] = 1
    character_id: Annotated[str, Field(pattern=r"^chr_[a-z0-9][a-z0-9_-]{1,47}$")]
    root: ID
    bones: list[BoneDefinition] = Field(default_factory=list)
    ik_chains: list[IKChain] = Field(default_factory=list)
    controls: list[ControlHandle] = Field(default_factory=list)
    notes: Annotated[str, Field(max_length=2000)] = ""

    def bone_map(self) -> dict[str, BoneDefinition]:
        """First definition wins for duplicate IDs (validation reports duplicates)."""
        result: dict[str, BoneDefinition] = {}
        for bone in self.bones:
            result.setdefault(bone.id, bone)
        return result

    def chain(self, chain_id: str) -> IKChain | None:
        return next((c for c in self.ik_chains if c.id == chain_id), None)
