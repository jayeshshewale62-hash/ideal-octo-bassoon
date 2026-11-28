"""Clip compilation, time mapping, sampling, key editing and events.

``compile_clip`` turns typed tracks into scalar channels once. ``ClipSampler.sample``
then evaluates all channels at a clip time. Channels missing at a time are simply
absent: the evaluator falls back to the rest pose or the layers below.

Time mapping (``clip_time``)::

    local = (t - layer.time_offset) * layer.speed * clip.playback.speed + clip.playback.offset
    once      -> clamp(local, 0, duration)      (holds the first/last pose outside)
    loop      -> local mod duration             (duration itself maps to 0)
    pingpong  -> forward on even passes, backward on odd passes
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from studio.animation.curves import EPS, CompiledChannel, ease
from studio.animation.schemas import (
    AnimationClip,
    AnimationEvent,
    BoneKeyframe,
    BoneTrack,
    ControlKeyframe,
    CurveDefinition,
    DeformationKeyframe,
    DeformTrack,
    ExpressionKeyframe,
    ExpressionTrack,
    FaceTrack,
    IKKeyframe,
    IKTrack,
    Interpolation,
    KeyTime,
    LoopMode,
    PartTrack,
    RootTrack,
    TransformKeyframe,
    track_id,
)
from studio.core.exceptions import AnimationError

ChannelKey = tuple[str, str, str]  # (domain, target, property)
ANGLE_PROPERTIES = frozenset({"rotation", "end_rotation"})
STEP = CurveDefinition(interpolation=Interpolation.STEP)


@dataclass(frozen=True)
class ExpressionSample:
    """Expression state: blend from (a, weight_a) to (b, weight_b) by eased ``u``."""

    a: str
    weight_a: float
    b: str
    weight_b: float
    u: float


@dataclass
class ClipSample:
    time: float
    values: dict[ChannelKey, float] = field(default_factory=dict)
    expression: ExpressionSample | None = None


@dataclass(frozen=True)
class _ExprKey:
    time: float
    expression: str
    weight: float
    curve: CurveDefinition


@dataclass
class CompiledClip:
    clip: AnimationClip
    channels: dict[ChannelKey, CompiledChannel]
    expression_keys: list[_ExprKey]
    key_times: dict[str, list[float]]  # track id -> sorted key times (for previews)


def _key_fields(kind: str) -> tuple[str, ...]:
    return {
        "bone": ("rotation", "x", "y", "scale_x", "scale_y"),
        "part": ("x", "y", "rotation", "scale_x", "scale_y", "visible", "opacity"),
        "root": ("x", "y", "rotation", "scale_x", "scale_y"),
        "ik": ("x", "y", "pole_x", "pole_y", "weight", "end_rotation"),
    }[kind]


def check_clip(clip: AnimationClip) -> list[str]:
    """Clip-internal problems (codes ANM009-ANM015). References to rigs are checked elsewhere."""
    problems: list[str] = []
    ids = [track_id(t) for t in clip.tracks]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"ANM014 duplicate track {dup!r}")
    for track in clip.tracks:
        tid = track_id(track)
        if not track.keys:
            problems.append(f"ANM013 track {tid!r} has no keys")
            continue
        seen: dict[str, list[float]] = {}
        for key in track.keys:
            t = key.seconds(clip.fps)
            if t > clip.duration + EPS:
                problems.append(
                    f"ANM010 track {tid!r}: key at {t:g}s is after the clip end "
                    f"({clip.duration:g}s)"
                )
            for prop in _keyed_properties(track.kind, key):
                times = seen.setdefault(prop, [])
                if any(abs(t - other) <= EPS for other in times):
                    problems.append(f"ANM009 track {tid!r}: two keys for {prop!r} at {t:g}s")
                times.append(t)
    for i, ev in enumerate(clip.events):
        t = ev.seconds(clip.fps)
        if t > clip.duration + EPS:
            problems.append(f"ANM015 event {i} ({ev.name}) at {t:g}s is after the clip end")
    return problems


def _keyed_properties(kind: str, key: KeyTime) -> list[str]:
    if isinstance(key, ControlKeyframe):
        return list(key.values)
    if isinstance(key, DeformationKeyframe):
        return list(key.weights)
    if isinstance(key, ExpressionKeyframe):
        return ["expression"]
    return [f for f in _key_fields(kind) if getattr(key, f, None) is not None]


def _periodic(clip: AnimationClip, keys: list[tuple[float, float, CurveDefinition]]) -> bool:
    if clip.loop.mode is not LoopMode.LOOP or len(keys) < 2:
        return False
    ordered = sorted(keys, key=lambda k: k[0])
    return (
        abs(ordered[0][0]) <= EPS
        and abs(ordered[-1][0] - clip.duration) <= EPS
        and abs(ordered[0][1] - ordered[-1][1]) <= 1e-9
    )


def compile_clip(clip: AnimationClip) -> CompiledClip:
    problems = check_clip(clip)
    if problems:
        raise AnimationError(f"clip {clip.id!r} is invalid", problems)
    raw: dict[ChannelKey, list[tuple[float, float, CurveDefinition]]] = {}
    shortest: dict[ChannelKey, bool] = {}
    expr_keys: list[_ExprKey] = []
    key_times: dict[str, list[float]] = {}
    for track in clip.tracks:
        if not track.enabled:
            continue
        tid = track_id(track)
        key_times[tid] = sorted({k.seconds(clip.fps) for k in track.keys})
        if isinstance(track, ExpressionTrack):
            for k in track.keys:
                expr_keys.append(_ExprKey(k.seconds(clip.fps), k.expression, k.weight, k.curve))
            continue
        if isinstance(track, FaceTrack):
            for fk in track.keys:
                for ctl, value in fk.values.items():
                    raw.setdefault(("face", "face", ctl), []).append(
                        (fk.seconds(clip.fps), value, fk.curve)
                    )
            continue
        if isinstance(track, DeformTrack):
            for dk in track.keys:
                for shape, value in dk.weights.items():
                    raw.setdefault(("deform", track.mesh, shape), []).append(
                        (dk.seconds(clip.fps), value, dk.curve)
                    )
            continue
        domain, target = _domain_target(track)
        for key in track.keys:
            assert isinstance(key, BoneKeyframe | TransformKeyframe | IKKeyframe)
            for prop in _key_fields(track.kind):
                raw_value = getattr(key, prop, None)
                if raw_value is None:
                    continue
                curve = STEP if prop == "visible" else key.curve
                ck = (domain, target, prop)
                raw.setdefault(ck, []).append((key.seconds(clip.fps), float(raw_value), curve))
                shortest[ck] = track.shortest_path
    channels = {
        ck: CompiledChannel.build(
            keys,
            angle=ck[2] in ANGLE_PROPERTIES,
            shortest_path=shortest.get(ck, False),
            periodic=_periodic(clip, keys),
        )
        for ck, keys in sorted(raw.items())
    }
    expr_keys.sort(key=lambda k: k.time)
    return CompiledClip(clip, channels, expr_keys, key_times)


def _domain_target(track: BoneTrack | IKTrack | PartTrack | RootTrack) -> tuple[str, str]:
    if isinstance(track, BoneTrack):
        return "bone", track.bone
    if isinstance(track, IKTrack):
        return "ik", track.chain
    if isinstance(track, PartTrack):
        return "part", track.part
    return "root", "root"


def clip_time(
    clip: AnimationClip, t: float, *, time_offset: float = 0.0, speed: float = 1.0
) -> float:
    if not math.isfinite(t):
        raise AnimationError(f"time must be a finite number, got {t!r}")
    d = clip.duration
    local = (t - time_offset) * speed * clip.playback.speed + clip.playback.offset
    mode = clip.loop.mode
    if mode is LoopMode.ONCE:
        return min(d, max(0.0, local))
    if mode is LoopMode.LOOP:
        r = math.fmod(local, d)
        return r + d if r < 0 else r
    period = 2 * d
    r = math.fmod(local, period)
    r = r + period if r < 0 else r
    return r if r <= d else period - r


def cycle_phase(clip: AnimationClip, ct: float) -> float:
    return ct / clip.duration


def sample_clip(compiled: CompiledClip, ct: float) -> ClipSample:
    sample = ClipSample(ct)
    for ck, ch in compiled.channels.items():
        sample.values[ck] = ch.evaluate(ct)
    keys = compiled.expression_keys
    if keys:
        if ct <= keys[0].time:
            k = keys[0]
            sample.expression = ExpressionSample(
                k.expression, k.weight, k.expression, k.weight, 0.0
            )
        elif ct >= keys[-1].time:
            k = keys[-1]
            sample.expression = ExpressionSample(
                k.expression, k.weight, k.expression, k.weight, 1.0
            )
        else:
            i = max(j for j, k in enumerate(keys) if k.time <= ct)
            a, b = keys[i], keys[i + 1]
            u = (ct - a.time) / (b.time - a.time)
            sample.expression = ExpressionSample(
                a.expression, a.weight, b.expression, b.weight, ease(u, a.curve)
            )
    return sample


# --- key editing (returns new clips; never mutates) ---------------------------------------------


def find_track(clip: AnimationClip, tid: str) -> int | None:
    return next((i for i, t in enumerate(clip.tracks) if track_id(t) == tid), None)


def insert_key(
    clip: AnimationClip, track: object, key: KeyTime, *, replace: bool = False
) -> AnimationClip:
    """Insert ``key`` into the track with the same id as ``track`` (adding the track if
    needed). A key at an existing time is refused unless ``replace``."""
    tid = track_id(track)
    index = find_track(clip, tid)
    tracks = list(clip.tracks)
    t_new = key.seconds(clip.fps)
    if t_new > clip.duration + EPS:
        raise AnimationError(f"key time {t_new:g}s is after the clip end ({clip.duration:g}s)")
    if index is None:
        new_track = track.model_copy(update={"keys": [key]})  # type: ignore[attr-defined]
        tracks.append(new_track)
    else:
        existing = tracks[index]
        keys: list[Any] = [k for k in existing.keys if abs(k.seconds(clip.fps) - t_new) > EPS]
        if len(keys) != len(existing.keys) and not replace:
            raise AnimationError(f"track {tid!r} already has a key at {t_new:g}s (use replace)")
        keys.append(key)
        keys.sort(key=lambda k: k.seconds(clip.fps))
        tracks[index] = existing.model_copy(update={"keys": keys})
    return AnimationClip.model_validate(clip.model_copy(update={"tracks": tracks}).model_dump())


def remove_key(clip: AnimationClip, tid: str, time: float) -> AnimationClip:
    index = find_track(clip, tid)
    if index is None:
        raise AnimationError(f"clip {clip.id!r} has no track {tid!r}")
    track = clip.tracks[index]
    keys = [k for k in track.keys if abs(k.seconds(clip.fps) - time) > EPS]
    if len(keys) == len(track.keys):
        raise AnimationError(f"track {tid!r} has no key at {time:g}s")
    tracks = list(clip.tracks)
    if keys:
        tracks[index] = track.model_copy(update={"keys": keys})
    else:
        del tracks[index]
    return AnimationClip.model_validate(clip.model_copy(update={"tracks": tracks}).model_dump())


# --- events --------------------------------------------------------------------------------------


def sorted_events(clip: AnimationClip) -> list[tuple[float, AnimationEvent]]:
    return sorted(((e.seconds(clip.fps), e) for e in clip.events), key=lambda x: (x[0], x[1].name))


def events_between(
    clip: AnimationClip, start: float, end: float
) -> list[tuple[float, AnimationEvent]]:
    """Events whose clip time lies in [start, end) of *absolute layer time*. Looping clips
    repeat their events every cycle; ``once`` clips fire each event at most once."""
    if end < start:
        raise AnimationError("event window end is before its start")
    events = sorted_events(clip)
    d = clip.duration
    out: list[tuple[float, AnimationEvent]] = []
    if clip.loop.mode is LoopMode.ONCE:
        return [(t, e) for t, e in events if start <= t < end or (t == d and start <= t <= end)]
    if clip.loop.mode is LoopMode.LOOP:
        first = math.floor(start / d)
        last = math.floor(end / d)
        for cycle in range(first, last + 1):
            for t, e in events:
                abs_t = cycle * d + t
                if start <= abs_t < end and not (t == d and abs_t == (cycle + 1) * d):
                    out.append((abs_t, e))
        return sorted(out, key=lambda x: (x[0], x[1].name))
    # pingpong: forward pass then mirrored pass
    period = 2 * d
    first = math.floor(start / period)
    last = math.floor(end / period)
    for cycle in range(first, last + 1):
        for t, e in events:
            for abs_t in sorted({cycle * period + t, cycle * period + period - t}):
                if start <= abs_t < end:
                    out.append((abs_t, e))
    return sorted(out, key=lambda x: (x[0], x[1].name))
