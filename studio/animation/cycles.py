"""Procedural motion cycles and gestures, baked into editable keyframe clips.

Every generator computes poses analytically at ``samples`` evenly spaced times and stores
them as ordinary keyframes on rig tracks. The result is a normal clip that can be edited,
layered and versioned like any hand-keyed clip. Looping clips repeat the first key at the
end, so the loop boundary is exact (tests check continuity numerically).

Biped walk/run conventions (docs/ANIMATION.md#walk-and-run-cycles), in place (no root
travel; ``speed`` and ``distance_per_cycle`` are recorded for later scene placement):

* phase ``p`` in [0, 1): left foot contact at p = 0, right foot at p = 0.5;
* each foot is planted for the **stance** fraction β of the cycle and moves backward
  relative to the hip at constant speed; for the rest (**swing**) it moves forward with a
  lift curve. Walk β ≈ 0.6 (double support), run β ≈ 0.35 (flight phases);
* feet are driven by **animated IK targets** on the ``leg_l``/``leg_r`` chains (ankle
  positions) with ``end_rotation`` keeping the foot bone at its rest world angle;
* hips bob (walk: lowest at contact; run: lowest mid-stance), the pelvis sways, the
  spine leans, the neck counter-rotates so the head stays level, and the arms counter-swing.
* **Facing** comes from the leg chains' bend: knees bend towards the facing side. The
  biped template's knees bend negative, so its cycles face screen-left.

This is stylized animation, not a biomechanical simulation.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass

from studio.animation.curves import wrap_degrees
from studio.animation.schemas import (
    AnimationClip,
    AnimationEvent,
    BoneKeyframe,
    BoneTrack,
    ControlKeyframe,
    CurveDefinition,
    EventKind,
    FaceTrack,
    IKKeyframe,
    IKTrack,
    Interpolation,
    LoopMode,
    LoopSettings,
    MotionCycle,
    PartTrack,
    TransformKeyframe,
)
from studio.characters.schemas import CharacterDefinition
from studio.core.exceptions import AnimationError
from studio.face.schemas import FacialRig
from studio.rig.fk import BonePose, solve_fk
from studio.rig.ik import solve_ik_chain
from studio.rig.math2d import Vec2
from studio.rig.schemas import BendDirection, RigDefinition

HERMITE = CurveDefinition(interpolation=Interpolation.HERMITE)
SMOOTH = CurveDefinition(interpolation=Interpolation.SMOOTH)
LINEAR = CurveDefinition(interpolation=Interpolation.LINEAR)
LIMIT_HEADROOM = 1.06  # baked targets keep 6 % distance from joint limits
REACH = 0.985  # keep legs slightly bent: never ask for more than 98.5 % of the leg length
CYCLES = ("walk", "run", "idle")
GESTURES = ("wave", "point", "nod")


def _smooth(s: float) -> float:
    return s * s * (3 - 2 * s)


def _r(v: float) -> float:
    r = round(v, 4)
    return 0.0 if r == 0 else r


@dataclass(frozen=True)
class LocomotionParams:
    kind: str
    duration: float
    stride: float
    stance: float
    lift: float
    bob: float
    arm_swing: float
    elbow: float
    lean: float
    sway: float
    recovery: float
    samples: int


def _require(rig: RigDefinition, *names: str) -> None:
    bones = rig.bone_map()
    missing = [n for n in names if n not in bones and rig.chain(n) is None]
    if missing:
        raise AnimationError(f"this generator needs {', '.join(missing)} (biped template rig)")


def _leg_length(rig: RigDefinition, chain_id: str) -> float:
    chain = rig.chain(chain_id)
    assert chain is not None
    bones = rig.bone_map()
    return bones[chain.upper].length + bones[chain.lower].length


def _facing(rig: RigDefinition) -> int:
    chain = rig.chain("leg_l")
    assert chain is not None
    return -1 if chain.bend is BendDirection.NEGATIVE else 1


def locomotion_params(
    kind: str,
    rig: RigDefinition,
    *,
    duration: float | None = None,
    stride: float | None = None,
    speed: float | None = None,
    samples: int = 20,
    **overrides: float,
) -> LocomotionParams:
    if kind not in ("walk", "run"):
        raise AnimationError(f"unknown locomotion kind {kind!r}")
    leg = _leg_length(rig, "leg_l")
    walk = kind == "walk"
    defaults = {
        "stance": 0.6 if walk else 0.35,
        "lift": (0.12 if walk else 0.32) * leg,
        "bob": (0.025 if walk else 0.05) * leg,
        "arm_swing": 18.0 if walk else 35.0,
        "elbow": 10.0 if walk else 80.0,
        "lean": 3.0 if walk else 10.0,
        "sway": 2.0 if walk else 3.0,
        "recovery": 0.0 if walk else 0.25 * leg,
    }
    unknown = set(overrides) - set(defaults)
    if unknown:
        raise AnimationError(f"unknown cycle parameter(s): {', '.join(sorted(unknown))}")
    defaults.update(overrides)
    given = [v for v in (duration, stride, speed) if v is not None]
    for v in given:
        if not math.isfinite(v) or v <= 0:
            raise AnimationError("duration, stride and speed must be positive numbers")
    if (
        duration is not None
        and stride is not None
        and speed is not None
        and abs(stride / duration - speed) > 1e-6 * max(1.0, speed)
    ):
        raise AnimationError("stride / duration must equal speed when all three are given")
    if duration is None:
        duration = (
            stride / speed if stride is not None and speed is not None else (1.0 if walk else 0.7)
        )
    if stride is None:
        stride = speed * duration if speed is not None else (1.1 if walk else 2.0) * leg
    if not 0.2 <= defaults["stance"] <= 0.8:
        raise AnimationError("stance fraction must be within [0.2, 0.8]")
    if walk and defaults["stance"] <= 0.5:
        raise AnimationError("a walk needs stance > 0.5 (both feet down at times); use run")
    if not walk and defaults["stance"] >= 0.5:
        raise AnimationError("a run needs stance < 0.5 (a flight phase); use walk")
    if samples < 8 or samples % 2 or samples > 240:
        raise AnimationError("samples must be an even number between 8 and 240")
    return LocomotionParams(kind, duration, stride, samples=samples, **defaults)


def _foot(p: float, prm: LocomotionParams) -> tuple[float, float, bool]:
    """(forward offset from hip, lift above ground, planted) for phase p of one foot."""
    a = prm.stance * prm.stride / 2
    if p < prm.stance:
        return a - 2 * a * (p / prm.stance), 0.0, True
    s = (p - prm.stance) / (1 - prm.stance)
    x = -a + 2 * a * _smooth(s) - prm.recovery * math.sin(math.pi * s) * (1 - s)
    lift = prm.lift * math.sin(math.pi * s) ** (1.0 if prm.kind == "walk" else 0.8)
    return x, lift, False


def _bob(p: float, prm: LocomotionParams) -> float:
    """Hip offset (+ = down). Walk: lowest at contact. Run: lowest mid-stance."""
    shift = 0.0 if prm.kind == "walk" else prm.stance / 2
    return prm.bob * math.cos(4 * math.pi * (p - shift))


def generate_locomotion(
    character: CharacterDefinition,
    rig: RigDefinition,
    prm: LocomotionParams,
    *,
    clip_id: str | None = None,
    fps: float = 24.0,
) -> AnimationClip:
    _require(rig, "root", "spine", "neck", "leg_l", "leg_r")
    bones = rig.bone_map()
    rest = solve_fk(rig)
    f = _facing(rig)
    root = bones[rig.root]
    legs = {}
    for side in ("l", "r"):
        chain = rig.chain(f"leg_{side}")
        assert chain is not None
        legs[side] = (chain, rest[chain.upper].head, rest[chain.lower].tip)
    ground = max(legs["l"][2].y, legs["r"][2].y)
    leg_len = min(_leg_length(rig, "leg_l"), _leg_length(rig, "leg_r"))
    n = prm.samples
    phases = [k / n for k in range(n + 1)]

    # crouch so every pose is reachable (accounts for bob and lifts)
    crouch = 0.0
    for p in phases:
        for side, offset in (("l", 0.0), ("r", 0.5)):
            fx, lift, _ = _foot((p + offset) % 1.0, prm)
            hip = legs[side][1]
            avail = (REACH * leg_len) ** 2 - fx * fx
            if avail <= 0:
                raise AnimationError(
                    f"stride {prm.stride:g} is too long for a leg of {leg_len:g} units"
                )
            need = (ground - lift - (hip.y + _bob(p, prm))) - math.sqrt(avail)
            crouch = max(crouch, need)
    if crouch > 0.35 * leg_len:
        raise AnimationError(
            f"stride {prm.stride:g} would need a crouch of {crouch:.1f} units; shorten it"
        )

    def times() -> list[float]:
        return [prm.duration * p for p in phases]

    t_all = times()
    spine_rest = bones["spine"].rest.rotation
    neck_rest = bones["neck"].rest.rotation
    root_keys, spine_keys, neck_keys = [], [], []
    adjusted = 0
    ik_keys: dict[str, list[IKKeyframe]] = {"l": [], "r": []}
    for p, t in zip(phases, t_all, strict=True):
        sway = prm.sway * math.sin(2 * math.pi * p)
        root_keys.append(
            BoneKeyframe(
                time=_r(t),
                y=_r(root.rest.y + crouch + _bob(p, prm)),
                rotation=_r(root.rest.rotation + sway),
                curve=HERMITE,
            )
        )
        lean = -prm.lean if f == -1 else prm.lean  # lean towards the facing side
        twist = 1.5 * math.sin(2 * math.pi * p) if prm.kind == "walk" else 0.0
        spine_rot = spine_rest + lean + twist
        spine_keys.append(BoneKeyframe(time=_r(t), rotation=_r(spine_rot), curve=HERMITE))
        # head stability: cancel pelvis sway and spine motion so the head stays level
        neck_keys.append(
            BoneKeyframe(
                time=_r(t), rotation=_r(neck_rest - (spine_rot - spine_rest) - sway), curve=HERMITE
            )
        )
        root_pose = {
            rig.root: BonePose(
                y=root.rest.y + crouch + _bob(p, prm), rotation=root.rest.rotation + sway
            )
        }
        for side, offset in (("l", 0.0), ("r", 0.5)):
            fx, lift, _ = _foot((p + offset) % 1.0, prm)
            hip = legs[side][1]
            x, y = hip.x + f * fx, ground - lift
            chain_id = f"leg_{side}"
            if lift > 0:  # keep the baked pose inside the rig's joint limits
                x, y, changed = _within_limits(rig, chain_id, root_pose, hip.x, ground, x, y)
                adjusted += changed
            solved = solve_ik_chain(rig, chain_id, Vec2(x, y), pose=root_pose)
            if solved.limited:
                raise AnimationError(
                    f"{prm.kind} stride {prm.stride:g} puts the planted {side} foot beyond "
                    "the rig's joint "
                    "limits; shorten the stride or lengthen the cycle"
                )
            end = None
            foot = f"foot_{side}"
            if foot in bones:  # keep the foot at its rest angle, within its own limits (margin 5°)
                lower_world = solved.fk[legs[side][0].lower].world_rotation
                fc = bones[foot].constraint
                lo, hi = (fc.min_rotation + 5, fc.max_rotation - 5) if fc else (-180.0, 180.0)
                local = max(lo, min(hi, wrap_degrees(rest[foot].world_rotation - lower_world)))
                end = _r(lower_world + local)
            ik_keys[side].append(
                IKKeyframe(
                    time=_r(t), x=_r(x), y=_r(y), weight=1.0, end_rotation=end, curve=HERMITE
                )
            )
    tracks: list = [  # type: ignore[type-arg]
        BoneTrack(bone=rig.root, keys=root_keys),
        BoneTrack(bone="spine", keys=spine_keys),
        BoneTrack(bone="neck", keys=neck_keys),
        IKTrack(chain="leg_l", keys=ik_keys["l"]),
        IKTrack(chain="leg_r", keys=ik_keys["r"]),
    ]
    for side, sign_phase in (("l", 1.0), ("r", -1.0)):
        upper, fore = f"upper_arm_{side}", f"forearm_{side}"
        if upper not in bones:
            continue
        fore_c = bones[fore].constraint if fore in bones else None
        elbow_sign = 1.0 if fore_c is None or fore_c.max_rotation > 0 else -1.0
        up_keys, fo_keys = [], []
        for p, t in zip(phases, t_all, strict=True):
            fwd = -sign_phase * math.cos(2 * math.pi * p)  # left arm forward when the right leg is
            up_keys.append(
                BoneKeyframe(
                    time=_r(t),
                    rotation=_r(bones[upper].rest.rotation - f * prm.arm_swing * fwd),
                    curve=HERMITE,
                )
            )
            bend = prm.elbow * (1 + 0.3 * max(0.0, fwd))
            fo_keys.append(BoneKeyframe(time=_r(t), rotation=_r(elbow_sign * bend), curve=HERMITE))
        tracks.append(BoneTrack(bone=upper, keys=up_keys))
        if fore in bones:
            tracks.append(BoneTrack(bone=fore, keys=fo_keys))

    events = []
    for side, offset in (("l", 0.0), ("r", 0.5)):
        contact = (1 - offset) % 1.0
        lift = (prm.stance - offset) % 1.0
        events.append(
            AnimationEvent(
                time=_r(prm.duration * contact),
                kind=EventKind.FOOT_CONTACT,
                name=f"contact_{side}",
                data={"foot": side},
            )
        )
        events.append(
            AnimationEvent(
                time=_r(prm.duration * lift),
                kind=EventKind.FOOT_LIFT,
                name=f"lift_{side}",
                data={"foot": side},
            )
        )
    events.sort(key=lambda e: (e.time or 0, e.name))
    speed = prm.stride / prm.duration
    return AnimationClip(
        id=clip_id or prm.kind,
        name=f"{prm.kind.title()} cycle",
        character_id=character.id,
        duration=_r(prm.duration),
        fps=fps,
        loop=LoopSettings(mode=LoopMode.LOOP),
        tracks=tracks,
        events=events,
        cycle=MotionCycle(
            kind=prm.kind,
            parameters={
                "stride": _r(prm.stride),
                "stance": prm.stance,
                "lift": _r(prm.lift),
                "bob": _r(prm.bob),
                "arm_swing": prm.arm_swing,
                "elbow": prm.elbow,
                "lean": prm.lean,
                "sway": prm.sway,
                "recovery": _r(prm.recovery),
                "crouch": _r(crouch),
                "ground_y": _r(ground),
                "limit_adjusted_samples": adjusted,
            },
            facing="left" if f == -1 else "right",
            speed=_r(speed),
            distance_per_cycle=_r(prm.stride),
            samples=n,
        ),
        tags=["cycle", prm.kind, "generated"],
    )


def _within_limits(
    rig: RigDefinition,
    chain: str,
    pose: dict[str, BonePose],
    hip_x: float,
    ground: float,
    x: float,
    y: float,
) -> tuple[float, float, int]:
    """Pull a lifted foot target back towards the planted line under the hip until the IK
    solution needs no joint clamping, with ``LIMIT_HEADROOM`` extra offset so the curve
    between baked keys stays inside the limits too (bisection, deterministic)."""

    def limited(fraction: float) -> bool:
        k = fraction * LIMIT_HEADROOM
        target = Vec2(hip_x + (x - hip_x) * k, ground + (y - ground) * k)
        return solve_ik_chain(rig, chain, target, pose=pose).limited

    if not limited(1.0):
        return x, y, 0
    lo, hi = 0.0, 1.0  # fraction of the requested offset that is kept
    for _ in range(30):
        mid = (lo + hi) / 2
        if limited(mid):
            hi = mid
        else:
            lo = mid
    return hip_x + (x - hip_x) * lo, ground + (y - ground) * lo, 1


# --- idle ----------------------------------------------------------------------------------------


def _seeded(seed: int, label: str) -> float:
    """Deterministic value in [0, 1) from a seed (no global random state)."""
    digest = hashlib.sha256(f"{seed}:{label}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def generate_idle(
    character: CharacterDefinition,
    rig: RigDefinition,
    face: FacialRig | None,
    *,
    clip_id: str = "idle",
    duration: float = 4.0,
    breaths: int = 1,
    amount: float = 1.0,
    blinks: int = 2,
    weight_shift: bool = True,
    seed: int = 0,
    samples: int = 32,
    fps: float = 24.0,
) -> AnimationClip:
    _require(rig, "root", "spine", "neck")
    if duration <= 0 or not math.isfinite(duration):
        raise AnimationError("duration must be positive")
    if breaths < 1 or not 0 <= amount <= 3 or blinks < 0 or samples < 8:
        raise AnimationError("breaths >= 1, amount in [0, 3], blinks >= 0, samples >= 8")
    bones = rig.bone_map()
    parts = character.part_map()
    leg = _leg_length(rig, "leg_l") if rig.chain("leg_l") else bones["spine"].length
    phi = [2 * math.pi * _seeded(seed, f"phase{i}") for i in range(4)]
    n = samples
    pts = [(k / n, _r(duration * k / n)) for k in range(n + 1)]

    def breath(p: float) -> float:  # 0 (exhaled) .. 1 (inhaled), `breaths` per loop
        return (1 - math.cos(2 * math.pi * breaths * p)) / 2

    tracks: list = [  # type: ignore[type-arg]
        BoneTrack(
            bone="spine",
            keys=[
                BoneKeyframe(
                    time=t,
                    rotation=_r(
                        bones["spine"].rest.rotation
                        + 0.8 * amount * math.sin(2 * math.pi * p + phi[0])
                    ),
                    curve=HERMITE,
                )
                for p, t in pts
            ],
        ),
        BoneTrack(
            bone="neck",
            keys=[
                BoneKeyframe(
                    time=t,
                    rotation=_r(
                        bones["neck"].rest.rotation
                        + 1.2 * amount * math.sin(4 * math.pi * p + phi[1])
                    ),
                    curve=HERMITE,
                )
                for p, t in pts
            ],
        ),
    ]
    root = bones[rig.root]
    if weight_shift:
        tracks.append(
            BoneTrack(
                bone=rig.root,
                keys=[
                    BoneKeyframe(
                        time=t,
                        x=_r(
                            root.rest.x + 0.012 * leg * amount * math.sin(2 * math.pi * p + phi[2])
                        ),
                        rotation=_r(
                            root.rest.rotation + 0.6 * amount * math.sin(2 * math.pi * p + phi[2])
                        ),
                        curve=HERMITE,
                    )
                    for p, t in pts
                ],
            )
        )
    for side in ("l", "r"):  # shoulders rise with each breath (along the spine)
        name = f"upper_arm_{side}"
        if name in bones:
            tracks.append(
                BoneTrack(
                    bone=name,
                    keys=[
                        BoneKeyframe(
                            time=t,
                            x=_r(bones[name].rest.x + 0.012 * leg * amount * breath(p)),
                            curve=HERMITE,
                        )
                        for p, t in pts
                    ],
                )
            )
    for pid in ("upper_torso", "chest"):  # chest expands
        if pid in parts:
            tr = parts[pid].transform
            tracks.append(
                PartTrack(
                    part=pid,
                    keys=[
                        TransformKeyframe(
                            time=t,
                            scale_y=_r(tr.scale_y * (1 + 0.025 * amount * breath(p))),
                            curve=HERMITE,
                        )
                        for p, t in pts
                    ],
                )
            )
    events = [
        AnimationEvent(
            time=_r(duration * (i + 0.5) / breaths),
            kind=EventKind.MARKER,
            name=f"inhale_peak_{i + 1}",
        )
        for i in range(breaths)
    ]
    if face is not None and blinks and face.channel("eye_l.blink") and face.channel("eye_r.blink"):
        keys = [
            ControlKeyframe(time=0.0, values={"eye_l.blink": 0.0, "eye_r.blink": 0.0}, curve=LINEAR)
        ]
        for i in range(blinks):
            centre = duration * (i + 0.5 + 0.3 * (_seeded(seed, f"blink{i}") - 0.5)) / blinks
            centre = min(max(centre, 0.15), duration - 0.15)
            for dt, v in ((-0.06, 0.0), (0.0, 1.0), (0.08, 0.0)):
                keys.append(
                    ControlKeyframe(
                        time=_r(centre + dt),
                        values={"eye_l.blink": v, "eye_r.blink": v},
                        curve=LINEAR,
                    )
                )
            events.append(
                AnimationEvent(time=_r(centre), kind=EventKind.MARKER, name=f"blink_{i + 1}")
            )
        keys.append(
            ControlKeyframe(
                time=_r(duration), values={"eye_l.blink": 0.0, "eye_r.blink": 0.0}, curve=LINEAR
            )
        )
        keys.sort(key=lambda k: k.time or 0)
        tracks.append(FaceTrack(id="blink", keys=keys))
    events.sort(key=lambda e: (e.time or 0, e.name))
    return AnimationClip(
        id=clip_id,
        name="Idle (breathing)",
        character_id=character.id,
        duration=_r(duration),
        fps=fps,
        loop=LoopSettings(mode=LoopMode.LOOP),
        tracks=tracks,
        events=events,
        cycle=MotionCycle(
            kind="idle",
            parameters={
                "breaths": breaths,
                "amount": amount,
                "blinks": blinks,
                "seed": seed,
                "weight_shift": weight_shift,
            },
            samples=n,
        ),
        tags=["cycle", "idle", "generated"],
    )


# --- gestures ------------------------------------------------------------------------------------


def _gesture_clip(
    character: CharacterDefinition,
    clip_id: str,
    name: str,
    duration: float,
    tracks: list,  # type: ignore[type-arg]
    events: list[AnimationEvent],
    kind: str,
    params: dict[str, float | int | str | bool],
) -> AnimationClip:
    return AnimationClip(
        id=clip_id,
        name=name,
        character_id=character.id,
        duration=duration,
        tracks=tracks,
        events=events,
        cycle=MotionCycle(kind=kind, parameters=params),
        tags=["gesture", kind, "generated"],
    )


def generate_wave(
    character: CharacterDefinition,
    rig: RigDefinition,
    *,
    clip_id: str = "wave",
    side: str = "l",
    waves: int = 3,
    duration: float = 2.4,
) -> AnimationClip:
    upper, fore = f"upper_arm_{side}", f"forearm_{side}"
    _require(rig, upper, fore, "spine")
    bones = rig.bone_map()
    rest_up = bones[upper].rest.rotation
    c = bones[fore].constraint
    sign = 1.0 if c is None or c.max_rotation > 0 else -1.0
    raised = 30.0 if sign > 0 else 330.0  # arm up and out, within the template limits
    up = [
        BoneKeyframe(time=0.0, rotation=rest_up, curve=SMOOTH),
        BoneKeyframe(time=0.5, rotation=raised, curve=SMOOTH),
        BoneKeyframe(time=_r(duration - 0.5), rotation=raised, curve=SMOOTH),
        BoneKeyframe(time=_r(duration), rotation=rest_up, curve=SMOOTH),
    ]
    fo = [BoneKeyframe(time=0.0, rotation=0.0, curve=SMOOTH)]
    span = duration - 1.2
    for i in range(waves * 2 + 1):
        fo.append(
            BoneKeyframe(
                time=_r(0.6 + span * i / (waves * 2)),
                rotation=_r(sign * (15 if i % 2 == 0 else 60)),
                curve=SMOOTH,
            )
        )
    fo.append(BoneKeyframe(time=_r(duration), rotation=0.0, curve=SMOOTH))
    events = [
        AnimationEvent(time=0.0, kind=EventKind.GESTURE_START, name="wave_start"),
        AnimationEvent(time=_r(duration / 2), kind=EventKind.MARKER, name="wave_peak"),
        AnimationEvent(time=_r(duration), kind=EventKind.GESTURE_END, name="wave_end"),
    ]
    return _gesture_clip(
        character,
        clip_id,
        "Wave",
        duration,
        [BoneTrack(bone=upper, keys=up), BoneTrack(bone=fore, keys=fo)],
        events,
        "wave",
        {"side": side, "waves": waves},
    )


def generate_point(
    character: CharacterDefinition,
    rig: RigDefinition,
    *,
    clip_id: str = "point",
    side: str = "r",
    target: tuple[float, float] | None = None,
    duration: float = 2.0,
) -> AnimationClip:
    chain_id = f"arm_{side}"
    _require(rig, chain_id)
    chain = rig.chain(chain_id)
    assert chain is not None
    rest = solve_fk(rig)
    shoulder = rest[chain.upper].head
    reach = 0.9 * (rig.bone_map()[chain.upper].length + rig.bone_map()[chain.lower].length)
    direction = -1.0 if side == "r" else 1.0
    tx, ty = (
        target if target is not None else (shoulder.x + direction * reach, shoulder.y + 0.1 * reach)
    )
    keys = [
        IKKeyframe(time=t, x=_r(tx), y=_r(ty), weight=w, curve=SMOOTH)
        for t, w in ((0.0, 0.0), (0.5, 1.0), (_r(duration - 0.5), 1.0), (duration, 0.0))
    ]
    events = [
        AnimationEvent(time=0.0, kind=EventKind.GESTURE_START, name="point_start"),
        AnimationEvent(
            time=0.5, kind=EventKind.MARKER, name="point_hold", data={"x": _r(tx), "y": _r(ty)}
        ),
        AnimationEvent(time=_r(duration), kind=EventKind.GESTURE_END, name="point_end"),
    ]
    return _gesture_clip(
        character,
        clip_id,
        "Point",
        duration,
        [IKTrack(chain=chain_id, keys=keys)],
        events,
        "point",
        {"side": side, "x": _r(tx), "y": _r(ty)},
    )


def generate_nod(
    character: CharacterDefinition,
    rig: RigDefinition,
    *,
    clip_id: str = "nod",
    duration: float = 1.2,
) -> AnimationClip:
    _require(rig, "neck")
    rest = rig.bone_map()["neck"].rest.rotation
    pattern = ((0.0, 0.0), (0.25, 12.0), (0.5, -3.0), (0.75, 9.0), (1.0, 0.0))
    keys = [
        BoneKeyframe(time=_r(duration * u), rotation=_r(rest + d), curve=SMOOTH) for u, d in pattern
    ]
    events = [
        AnimationEvent(time=0.0, kind=EventKind.GESTURE_START, name="nod_start"),
        AnimationEvent(time=_r(duration), kind=EventKind.GESTURE_END, name="nod_end"),
    ]
    return _gesture_clip(
        character, clip_id, "Nod", duration, [BoneTrack(bone="neck", keys=keys)], events, "nod", {}
    )


Generator = Callable[..., AnimationClip]
