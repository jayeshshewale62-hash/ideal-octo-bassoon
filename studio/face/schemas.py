"""Versioned facial-animation data contracts (Milestone 4).

Files in ``projects/<slug>/characters/<character-id>/``::

    face.yaml                    FacialRig: components (eyes, brows, mouth, jaw, ...) and channels
    expressions/<id>.yaml        custom FacialExpression (built-ins ship with the package)

Stand-alone documents (anywhere; usually ``audio/`` or ``scenes/``)::

    *.alignment.json|yaml        AlignmentDocument: word / phoneme timestamps from an aligner
    *.lipsync.yaml               LipSyncTrack: viseme events + timing settings

Packaged reference data (``studio/face/data``): built-in expression presets, the default
viseme set and phoneme->viseme maps. Each can be replaced by a file of the same schema.

Conventions (docs/FACE.md):

* **Face space**: origin at the face anchor on the head part, +x towards screen right in
  the front view, **+y down**, units = character design units.
* A **control key** is ``"<component>.<channel>"``, e.g. ``mouth.open``. Channel values
  are plain numbers with ``min``/``max`` limits and a ``default`` (the neutral face).
* Times are seconds. Event intervals are **half-open** ``[start, end)``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from studio.rig.schemas import GeometryModel, Point2D

ID = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")]
AssetId = Annotated[str, Field(pattern=r"^ast_[0-9a-f]{16}$")]
Finite = Annotated[float, Field(allow_inf_nan=False)]
Seconds = Annotated[float, Field(allow_inf_nan=False, ge=0, le=86_400)]
ControlKey = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,47}\.[a-z][a-z0-9_]{0,47}$")]
FACE_ID = r"^face_[a-z0-9][a-z0-9_]{1,47}$"


# =========================================================================================
# Facial rig
# =========================================================================================


class ComponentKind(StrEnum):
    EYE = "eye"
    BROW = "brow"
    MOUTH = "mouth"
    JAW = "jaw"
    CHEEK = "cheek"
    NOSE = "nose"
    ACCESSORY = "accessory"
    CUSTOM = "custom"


class FacialChannel(GeometryModel):
    """One editable scalar control of a component (a "facial control")."""

    name: ID
    min: Finite = 0.0
    max: Finite = 1.0
    default: Finite = 0.0
    unit: Literal["normalized", "ratio", "degrees", "units", "toggle"] = "normalized"
    description: Annotated[str, Field(max_length=200)] = ""


class ComponentAttachment(GeometryModel):
    """Bind a component to a character part, optionally to a named attachment point."""

    part: ID
    point: ID | None = None


class FacialComponent(GeometryModel):
    id: ID
    kind: ComponentKind
    side: Literal["left", "right", "center"] = "center"
    position: Point2D = Field(default_factory=Point2D)  # rest position in face space
    size: tuple[
        Annotated[float, Field(gt=0, le=100_000, allow_inf_nan=False)],
        Annotated[float, Field(gt=0, le=100_000, allow_inf_nan=False)],
    ] = (10.0, 10.0)
    channels: list[FacialChannel] = Field(default_factory=list)
    attachment: ComponentAttachment | None = None  # character part / attachment point
    asset: AssetId | None = None  # default artwork (registered asset)
    shapes: dict[ID, AssetId | None] = Field(default_factory=dict)  # replacement drawings
    optional: bool = False

    def channel(self, name: str) -> FacialChannel | None:
        return next((c for c in self.channels if c.name == name), None)


class FaceAnchor(GeometryModel):
    """Where face space sits on the character: a point in the head part's artwork space."""

    part: ID = "head"
    attachment: ID | None = None  # named attachment point on that part (overrides position)
    position: Point2D = Field(default_factory=Point2D)


class FacialRig(GeometryModel):
    schema_version: Literal[1] = 1
    id: Annotated[str, Field(pattern=FACE_ID)]
    version: Annotated[int, Field(ge=1)] = 1
    character_id: Annotated[str, Field(pattern=r"^chr_[a-z0-9][a-z0-9_-]{1,47}$")]
    template: Annotated[str, Field(max_length=60)] | None = None
    anchor: FaceAnchor = Field(default_factory=FaceAnchor)
    components: list[FacialComponent] = Field(default_factory=list)
    notes: Annotated[str, Field(max_length=2000)] = ""

    def component(self, component_id: str) -> FacialComponent | None:
        return next((c for c in self.components if c.id == component_id), None)

    def channel(self, key: str) -> FacialChannel | None:
        comp_id, _, name = key.partition(".")
        comp = self.component(comp_id)
        return comp.channel(name) if comp else None

    def keys(self) -> list[str]:
        return [f"{c.id}.{ch.name}" for c in self.components for ch in c.channels]


# =========================================================================================
# Expressions
# =========================================================================================


class FacialExpression(GeometryModel):
    """Values for facial controls. Unlisted controls keep their rig default (neutral)."""

    schema_version: Literal[1] = 1
    id: ID
    name: Annotated[str, Field(min_length=1, max_length=80)]
    version: Annotated[int, Field(ge=1)] = 1
    rig: Annotated[str, Field(pattern=FACE_ID)] | None = None  # None = generic preset
    values: dict[ControlKey, Finite] = Field(default_factory=dict)
    shapes: dict[ID, ID] = Field(default_factory=dict)  # component -> shape id
    description: Annotated[str, Field(max_length=500)] = ""
    tags: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(default_factory=list)
    builtin: bool = False


class ExpressionLibrary(GeometryModel):
    schema_version: Literal[1] = 1
    expressions: list[FacialExpression]


class Ease(StrEnum):
    LINEAR = "linear"
    SMOOTHSTEP = "smoothstep"  # 3w² - 2w³: zero slope at both ends


class ExpressionBlend(GeometryModel):
    """Blend from expression ``a`` (weight 0) to ``b`` (weight 1)."""

    a: ID
    b: ID
    weight: float  # validated (and clamped with a report) by the blend engine
    ease: Ease = Ease.LINEAR


# =========================================================================================
# Visemes and phonemes
# =========================================================================================


class Viseme(GeometryModel):
    id: ID
    name: Annotated[str, Field(min_length=1, max_length=80)]
    articulation: Annotated[str, Field(max_length=300)] = ""
    values: dict[ControlKey, Finite] = Field(default_factory=dict)  # mouth/jaw controls
    shape: ID | None = None  # mouth replacement-drawing id, if the rig has shapes
    teeth_visible: bool = False
    tongue_visible: bool = False


class VisemeSet(GeometryModel):
    schema_version: Literal[1] = 1
    id: ID
    rest: ID = "rest"
    visemes: list[Viseme]

    def get(self, viseme_id: str) -> Viseme | None:
        return next((v for v in self.visemes if v.id == viseme_id), None)

    @model_validator(mode="after")
    def _rest_defined(self) -> VisemeSet:
        ids = [v.id for v in self.visemes]
        if len(set(ids)) != len(ids):
            raise ValueError("viseme ids must be unique")
        if self.rest not in ids:
            raise ValueError(f"rest viseme {self.rest!r} is not defined")
        return self


class PhonemeMap(GeometryModel):
    """Language-specific, replaceable phoneme -> viseme table."""

    schema_version: Literal[1] = 1
    id: ID
    language: Annotated[str, Field(pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")]
    alphabet: Annotated[str, Field(min_length=1, max_length=40)]
    viseme_set: ID = "default"
    case_sensitive: bool = False
    strip_stress: bool = True  # ARPAbet stress digits: AH0 -> AH
    silence: list[Annotated[str, Field(max_length=16)]] = Field(default_factory=list)
    unknown: Literal["rest", "previous", "error"] = "rest"
    map: dict[Annotated[str, Field(min_length=1, max_length=16)], ID]
    notes: Annotated[str, Field(max_length=1000)] = ""


class PhonemeEvent(GeometryModel):
    phoneme: Annotated[str, Field(max_length=16)]
    start: Finite
    end: Finite
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    language: Annotated[str, Field(max_length=16)] | None = None
    word_index: Annotated[int, Field(ge=0)] | None = None


class VisemeEvent(GeometryModel):
    viseme: ID
    start: Seconds
    end: Seconds
    phonemes: list[Annotated[str, Field(max_length=16)]] = Field(default_factory=list)
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    source: Literal["phoneme", "silence", "unknown", "manual"] = "phoneme"


# =========================================================================================
# Alignment results and lip-sync tracks
# =========================================================================================


class WordEvent(GeometryModel):
    word: Annotated[str, Field(max_length=100)]
    start: Finite
    end: Finite
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None


class AlignmentSource(GeometryModel):
    provider: Annotated[str, Field(min_length=1, max_length=60)]
    model: Annotated[str, Field(max_length=120)] = ""
    created_at: datetime | None = None
    notes: Annotated[str, Field(max_length=500)] = ""


class AlignmentDocument(GeometryModel):
    """Audio alignment result: word and/or phoneme timestamps for one audio clip.

    The studio never invents timestamps. A document comes from an alignment provider or
    an external tool, or is written by hand.
    """

    schema_version: Literal[1] = 1
    source: AlignmentSource
    language: Annotated[str, Field(max_length=16)] = "en"
    audio_asset: AssetId | None = None
    duration: Seconds | None = None
    transcript: Annotated[str, Field(max_length=100_000)] = ""
    words: list[WordEvent] = Field(default_factory=list)
    phonemes: list[PhonemeEvent] = Field(default_factory=list)


class LipSyncSettings(GeometryModel):
    transition: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 0.06
    coarticulation: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 0.0
    ease: Ease = Ease.SMOOTHSTEP


class LipSyncTrack(GeometryModel):
    schema_version: Literal[1] = 1
    id: ID
    character_id: Annotated[str, Field(pattern=r"^chr_[a-z0-9][a-z0-9_-]{1,47}$")] | None = None
    viseme_set: ID = "default"
    phoneme_map: ID | None = None
    duration: Seconds | None = None
    settings: LipSyncSettings = Field(default_factory=LipSyncSettings)
    events: list[VisemeEvent] = Field(default_factory=list)


FACE_SCHEMAS: dict[str, type[BaseModel]] = {
    "facial_rig": FacialRig,
    "facial_component": FacialComponent,
    "facial_control": FacialChannel,
    "facial_expression": FacialExpression,
    "expression_blend": ExpressionBlend,
    "viseme": Viseme,
    "viseme_set": VisemeSet,
    "phoneme_map": PhonemeMap,
    "phoneme_event": PhonemeEvent,
    "viseme_event": VisemeEvent,
    "lipsync_track": LipSyncTrack,
    "alignment_result": AlignmentDocument,
}
