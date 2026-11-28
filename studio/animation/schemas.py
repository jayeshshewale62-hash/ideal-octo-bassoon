"""Versioned animation data contracts (Milestone 5).

Files per character (``projects/<slug>/characters/<id>/animations/``)::

    clips/<clip-id>.yaml     AnimationClip: tracks of typed keyframes, events, loop/playback
    sets/<set-id>.yaml       AnimationSet: layers of clips + lip-sync + secondary motion
    meshes/<mesh-id>.yaml    DeformMesh: vertices, triangles, bone weights, shapes

Authoring model: a clip holds **tracks**. Each track targets one thing (a bone, an IK
chain, a part, the root, facial controls, expressions or a deformation mesh) and holds
typed keyframes. At load time, tracks compile into scalar **channels**
(``AnimationChannel``: one property, sorted ``Keyframe`` values), which the curve engine
evaluates. A keyframe gives its time in seconds (``time``) *or* as a frame number
(``frame``, converted with the clip's ``fps``).

Bone and part values are **absolute local values** (they replace the rest value while
keyed). Rotations are in degrees. Character space is +y down (docs/ANIMATION.md).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

from studio.rig.schemas import GeometryModel

ID = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")]
ControlKey = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,47}\.[a-z][a-z0-9_]{0,47}$")]
Finite = Annotated[float, Field(allow_inf_nan=False)]
CHARACTER_ID = r"^chr_[a-z0-9][a-z0-9_-]{1,47}$"


# =========================================================================================
# Curves and keyframes
# =========================================================================================


class Interpolation(StrEnum):
    STEP = "step"  # hold the key's value until the next key
    LINEAR = "linear"
    SMOOTH = "smooth"  # smoothstep 3u² - 2u³ (zero slope at both keys)
    EASE_IN = "ease_in"  # u²
    EASE_OUT = "ease_out"  # 1 - (1 - u)²
    EASE_IN_OUT = "ease_in_out"  # cubic in-out
    BEZIER = "bezier"  # CSS-style cubic-bezier(x1, y1, x2, y2) timing
    HERMITE = "hermite"  # cubic Hermite through neighbours (monotone unless overshoot allowed)


class CurveDefinition(GeometryModel):
    """How the value travels from this key to the next one."""

    interpolation: Interpolation = Interpolation.LINEAR
    bezier: tuple[Finite, Finite, Finite, Finite] | None = None  # x1, y1, x2, y2
    tension: Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)] = 0.0  # hermite
    allow_overshoot: bool = False

    @model_validator(mode="after")
    def _check(self) -> CurveDefinition:
        if self.interpolation is Interpolation.BEZIER:
            if self.bezier is None:
                raise ValueError("bezier interpolation needs bezier: [x1, y1, x2, y2]")
            x1, y1, x2, y2 = self.bezier
            if not (0 <= x1 <= 1 and 0 <= x2 <= 1):
                raise ValueError("bezier x1 and x2 must be within [0, 1]")
            if not self.allow_overshoot and not (0 <= y1 <= 1 and 0 <= y2 <= 1):
                raise ValueError(
                    "bezier y1/y2 outside [0, 1] overshoot; set allow_overshoot: true to allow"
                )
        elif self.bezier is not None:
            raise ValueError("bezier control points are only used with interpolation: bezier")
        return self


class KeyTime(GeometryModel):
    """Exactly one of ``time`` (seconds) or ``frame`` (integer frame at the clip fps)."""

    time: Annotated[float, Field(ge=0, le=86_400, allow_inf_nan=False)] | None = None
    frame: Annotated[int, Field(ge=0, le=10_000_000)] | None = None
    curve: CurveDefinition = Field(default_factory=CurveDefinition)

    @model_validator(mode="after")
    def _one_time(self) -> KeyTime:
        if (self.time is None) == (self.frame is None):
            raise ValueError("a keyframe needs exactly one of 'time' or 'frame'")
        return self

    def seconds(self, fps: float) -> float:
        return self.time if self.time is not None else (self.frame or 0) / fps


class Keyframe(KeyTime):
    """Scalar keyframe of a compiled channel."""

    value: Finite


class TransformKeyframe(KeyTime):
    """Part or root transform keyframe. Unset fields are not keyed at this time."""

    x: Finite | None = None
    y: Finite | None = None
    rotation: Finite | None = None
    scale_x: Finite | None = None
    scale_y: Finite | None = None
    visible: bool | None = None
    opacity: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None


class BoneKeyframe(KeyTime):
    """Bone keyframe: absolute local values replacing the rest transform while keyed."""

    rotation: Finite | None = None
    x: Finite | None = None
    y: Finite | None = None
    scale_x: Finite | None = None
    scale_y: Finite | None = None


class IKKeyframe(KeyTime):
    """Animated IK target in character space (optionally a pole, a blend weight and a
    world rotation for the bone after the chain, e.g. a foot kept flat)."""

    x: Finite
    y: Finite
    pole_x: Finite | None = None
    pole_y: Finite | None = None
    weight: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    end_rotation: Finite | None = None


class ControlKeyframe(KeyTime):
    """Facial control values (``component.control``), e.g. blinks or brow raises."""

    values: dict[ControlKey, Finite]


class ExpressionKeyframe(KeyTime):
    """Expression to reach at this time, at a weight (0 = neutral, 1 = full)."""

    expression: ID
    weight: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 1.0


class DeformationKeyframe(KeyTime):
    """Blend-shape weights of a deformation mesh."""

    weights: dict[ID, Finite]


# =========================================================================================
# Tracks
# =========================================================================================


class _TrackBase(GeometryModel):
    id: ID | None = None  # default: derived from kind and target
    enabled: bool = True
    shortest_path: bool = False  # rotations take the shortest way between keys


class BoneTrack(_TrackBase):
    kind: Literal["bone"] = "bone"
    bone: ID
    keys: list[BoneKeyframe]


class IKTrack(_TrackBase):
    kind: Literal["ik"] = "ik"
    chain: ID
    keys: list[IKKeyframe]


class PartTrack(_TrackBase):
    kind: Literal["part"] = "part"
    part: ID
    keys: list[TransformKeyframe]


class RootTrack(_TrackBase):
    """Moves the whole character (origin of the rig) in character space."""

    kind: Literal["root"] = "root"
    keys: list[TransformKeyframe]


class FaceTrack(_TrackBase):
    kind: Literal["face"] = "face"
    keys: list[ControlKeyframe]


class ExpressionTrack(_TrackBase):
    kind: Literal["expression"] = "expression"
    keys: list[ExpressionKeyframe]


class DeformTrack(_TrackBase):
    kind: Literal["deform"] = "deform"
    mesh: ID
    keys: list[DeformationKeyframe]


AnimationTrack = Annotated[
    BoneTrack | IKTrack | PartTrack | RootTrack | FaceTrack | ExpressionTrack | DeformTrack,
    Field(discriminator="kind"),
]


def track_id(track: Any) -> str:
    if track.id:
        return str(track.id)
    target = (
        getattr(track, "bone", None)
        or getattr(track, "chain", None)
        or getattr(track, "part", None)
        or getattr(track, "mesh", None)
    )
    return f"{track.kind}:{target}" if target else str(track.kind)


class AnimationChannel(GeometryModel):
    """Compiled scalar channel (produced from tracks; also usable for inspection)."""

    domain: Literal["bone", "ik", "part", "root", "face", "deform"]
    target: Annotated[str, Field(max_length=100)]
    property: Annotated[str, Field(max_length=100)]
    angle: bool = False
    shortest_path: bool = False
    keys: list[Keyframe]


# =========================================================================================
# Events, loop and playback, clips
# =========================================================================================


class EventKind(StrEnum):
    FOOT_CONTACT = "foot_contact"
    FOOT_LIFT = "foot_lift"
    HAND_CONTACT = "hand_contact"
    GESTURE_START = "gesture_start"
    GESTURE_END = "gesture_end"
    EXPRESSION_CHANGE = "expression_change"
    MARKER = "marker"


class AnimationEvent(GeometryModel):
    time: Annotated[float, Field(ge=0, le=86_400, allow_inf_nan=False)] | None = None
    frame: Annotated[int, Field(ge=0)] | None = None
    kind: EventKind
    name: Annotated[str, Field(min_length=1, max_length=80)]
    data: dict[Annotated[str, Field(max_length=40)], str | int | float | bool] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def _one_time(self) -> AnimationEvent:
        if (self.time is None) == (self.frame is None):
            raise ValueError("an event needs exactly one of 'time' or 'frame'")
        return self

    def seconds(self, fps: float) -> float:
        return self.time if self.time is not None else (self.frame or 0) / fps


class LoopMode(StrEnum):
    ONCE = "once"  # hold the first/last pose outside [0, duration]
    LOOP = "loop"  # wrap time modulo duration
    PINGPONG = "pingpong"  # forwards then backwards


class LoopSettings(GeometryModel):
    mode: LoopMode = LoopMode.ONCE


class PlaybackSettings(GeometryModel):
    speed: Annotated[float, Field(gt=0, le=100, allow_inf_nan=False)] = 1.0
    offset: Annotated[float, Field(allow_inf_nan=False, ge=-86_400, le=86_400)] = 0.0


class MotionCycle(GeometryModel):
    """Records how a generated clip was made (so it can be regenerated or inspected)."""

    kind: Literal["walk", "run", "idle", "wave", "point", "nod"]
    parameters: dict[Annotated[str, Field(max_length=40)], float | int | str | bool] = Field(
        default_factory=dict
    )
    facing: Literal["left", "right", "none"] = "none"
    speed: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.0  # units / second
    distance_per_cycle: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.0
    samples: Annotated[int, Field(ge=0, le=1000)] = 0


class AnimationClip(GeometryModel):
    schema_version: Literal[1] = 1
    id: ID
    name: Annotated[str, Field(min_length=1, max_length=120)]
    version: Annotated[int, Field(ge=1)] = 1
    character_id: Annotated[str, Field(pattern=CHARACTER_ID)]
    duration: Annotated[float, Field(gt=0, le=86_400, allow_inf_nan=False)]
    fps: Annotated[float, Field(gt=0, le=240, allow_inf_nan=False)] = 24.0
    loop: LoopSettings = Field(default_factory=LoopSettings)
    playback: PlaybackSettings = Field(default_factory=PlaybackSettings)
    tracks: list[AnimationTrack] = Field(default_factory=list)
    events: list[AnimationEvent] = Field(default_factory=list)
    cycle: MotionCycle | None = None
    tags: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(default_factory=list)
    metadata: dict[Annotated[str, Field(max_length=60)], str | int | float | bool] = Field(
        default_factory=dict
    )


# =========================================================================================
# Layers, blending, sets, secondary motion
# =========================================================================================


class LayerMode(StrEnum):
    OVERRIDE = "override"  # lerp from what is below towards this layer by weight
    ADDITIVE = "additive"  # add weight x (value - rest/default) on top


class AnimationLayer(GeometryModel):
    id: ID
    clip: ID
    weight: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 1.0
    mode: LayerMode = LayerMode.OVERRIDE
    mask: list[Annotated[str, Field(max_length=60)]] = Field(default_factory=lambda: ["full"])
    order: int = 0
    time_offset: Annotated[float, Field(allow_inf_nan=False, ge=-86_400, le=86_400)] = 0.0
    speed: Annotated[float, Field(gt=0, le=100, allow_inf_nan=False)] = 1.0


class BlendSettings(GeometryModel):
    normalize: bool = False  # normalise override weights per property (weights sum to 1)


class LipSyncBinding(GeometryModel):
    """Lip-sync for this set: a registered asset (preferred) or a project-relative path."""

    asset: Annotated[str, Field(pattern=r"^ast_[0-9a-f]{16}$")] | None = None
    path: Annotated[str, Field(min_length=1, max_length=400)] | None = None
    start: Annotated[float, Field(allow_inf_nan=False, ge=-86_400, le=86_400)] = 0.0
    visemes: Annotated[str, Field(min_length=1, max_length=400)] = "default"
    enabled: bool = True

    @model_validator(mode="after")
    def _one_source(self) -> LipSyncBinding:
        if (self.asset is None) == (self.path is None):
            raise ValueError("lip-sync needs exactly one of 'asset' or 'path'")
        return self


class SpringDriver(GeometryModel):
    bone: ID
    signal: Literal["rotation", "x", "y"] = "rotation"


class SpringDefinition(GeometryModel):
    """Damped spring that makes a part or bone lag behind a driving bone."""

    id: ID
    target_kind: Literal["part", "bone"] = "part"
    target: ID
    driver: SpringDriver
    stiffness: Annotated[float, Field(gt=0, le=10_000, allow_inf_nan=False)] = 120.0
    damping: Annotated[float, Field(ge=0, le=1_000, allow_inf_nan=False)] = 12.0
    mass: Annotated[float, Field(gt=0, le=1_000, allow_inf_nan=False)] = 1.0
    gain: Annotated[float, Field(ge=-100, le=100, allow_inf_nan=False)] = 1.0  # degrees per unit
    max_displacement: Annotated[float, Field(gt=0, le=180, allow_inf_nan=False)] = 25.0


class SecondaryMotionSettings(GeometryModel):
    enabled: bool = True
    step: Annotated[float, Field(gt=0, le=0.1, allow_inf_nan=False)] = 1 / 120
    window: Annotated[float, Field(gt=0, le=30, allow_inf_nan=False)] = 2.0
    springs: list[SpringDefinition] = Field(default_factory=list)


class AnimationSet(GeometryModel):
    schema_version: Literal[1] = 1
    id: ID
    name: Annotated[str, Field(min_length=1, max_length=120)]
    version: Annotated[int, Field(ge=1)] = 1
    character_id: Annotated[str, Field(pattern=CHARACTER_ID)]
    layers: list[AnimationLayer] = Field(default_factory=list)
    blend: BlendSettings = Field(default_factory=BlendSettings)
    lipsync: LipSyncBinding | None = None
    secondary: SecondaryMotionSettings = Field(default_factory=SecondaryMotionSettings)
    meshes: list[ID] = Field(default_factory=list)
    view: Annotated[str, Field(max_length=40)] | None = None


# =========================================================================================
# Deformation meshes
# =========================================================================================


class VertexWeight(GeometryModel):
    bone: ID
    weight: Annotated[float, Field(allow_inf_nan=False)]


class DeformMesh(GeometryModel):
    """2D mesh over a part's artwork (artwork coordinates), skinned to bones.

    The artwork itself is never modified: the vertices are UV-like anchors into it, and
    deformation produces new positions in character space.
    """

    schema_version: Literal[1] = 1
    id: ID
    version: Annotated[int, Field(ge=1)] = 1
    character_id: Annotated[str, Field(pattern=CHARACTER_ID)]
    part: ID
    vertices: list[tuple[Finite, Finite]]
    triangles: list[tuple[int, int, int]]
    weights: list[list[VertexWeight]] = Field(default_factory=list)  # one list per vertex
    shapes: dict[ID, list[tuple[Finite, Finite]]] = Field(default_factory=dict)  # per-vertex deltas
    notes: Annotated[str, Field(max_length=1000)] = ""


ANIMATION_SCHEMAS: dict[str, type[BaseModel]] = {
    "animation_clip": AnimationClip,
    "animation_track_bone": BoneTrack,
    "animation_track_ik": IKTrack,
    "animation_track_part": PartTrack,
    "animation_track_root": RootTrack,
    "animation_track_face": FaceTrack,
    "animation_track_expression": ExpressionTrack,
    "animation_track_deform": DeformTrack,
    "animation_channel": AnimationChannel,
    "keyframe": Keyframe,
    "transform_keyframe": TransformKeyframe,
    "bone_keyframe": BoneKeyframe,
    "ik_keyframe": IKKeyframe,
    "control_keyframe": ControlKeyframe,
    "expression_keyframe": ExpressionKeyframe,
    "deformation_keyframe": DeformationKeyframe,
    "curve_definition": CurveDefinition,
    "animation_event": AnimationEvent,
    "loop_settings": LoopSettings,
    "playback_settings": PlaybackSettings,
    "animation_layer": AnimationLayer,
    "blend_settings": BlendSettings,
    "motion_cycle": MotionCycle,
    "animation_set": AnimationSet,
    "spring_definition": SpringDefinition,
    "deform_mesh": DeformMesh,
}
