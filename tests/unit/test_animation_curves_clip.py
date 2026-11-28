from __future__ import annotations

import math

import pytest

from studio.animation.clip import (
    check_clip,
    clip_time,
    compile_clip,
    events_between,
    insert_key,
    remove_key,
    sample_clip,
)
from studio.animation.curves import CompiledChannel, cubic_bezier, ease, wrap_degrees
from studio.animation.schemas import (
    AnimationClip,
    AnimationEvent,
    BoneKeyframe,
    BoneTrack,
    CurveDefinition,
    EventKind,
    ExpressionKeyframe,
    ExpressionTrack,
    Interpolation,
    LoopMode,
    LoopSettings,
    PartTrack,
    PlaybackSettings,
    TransformKeyframe,
)
from studio.core.exceptions import AnimationError

I = Interpolation  # noqa: E741


def curve(kind: Interpolation, **kw) -> CurveDefinition:
    return CurveDefinition(interpolation=kind, **kw)


def channel(keys, **kw) -> CompiledChannel:
    return CompiledChannel.build([(t, v, c) for t, v, c in keys], **kw)


# --- curves --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "u", "expected"),
    [
        (I.LINEAR, 0.25, 0.25),
        (I.SMOOTH, 0.25, 0.15625),
        (I.EASE_IN, 0.5, 0.25),
        (I.EASE_OUT, 0.5, 0.75),
        (I.EASE_IN_OUT, 0.25, 0.0625),
        (I.EASE_IN_OUT, 0.75, 0.9375),
        (I.STEP, 0.99, 0.0),
    ],
)
def test_ease_values(kind, u, expected) -> None:
    assert ease(u, curve(kind)) == pytest.approx(expected)


@pytest.mark.parametrize("kind", [k for k in Interpolation if k not in (I.BEZIER, I.HERMITE)])
def test_ease_boundaries(kind) -> None:
    c = curve(kind)
    assert ease(0.0, c) == 0.0 and ease(-3, c) == 0.0
    assert ease(1.0, c) == (0.0 if kind is I.STEP else 1.0) and ease(7, c) == ease(1.0, c)


def test_bezier() -> None:
    assert cubic_bezier(0.5, 0.42, 0, 0.58, 1) == pytest.approx(0.5)
    assert cubic_bezier(0.0, 0.25, 0.1, 0.25, 1) == 0 and cubic_bezier(1.0, 0.25, 0.1, 0.25, 1) == 1
    linear_like = [cubic_bezier(u / 10, 1 / 3, 1 / 3, 2 / 3, 2 / 3) for u in range(11)]
    assert linear_like == pytest.approx([u / 10 for u in range(11)], abs=1e-6)
    values = [cubic_bezier(u / 50, 0.1, 0.9, 0.2, 1.0) for u in range(51)]
    assert values == sorted(values)  # monotone, within [0, 1]
    assert all(0 <= v <= 1 for v in values)


def test_bezier_validation() -> None:
    with pytest.raises(ValueError, match="needs bezier"):
        CurveDefinition(interpolation=I.BEZIER)
    with pytest.raises(ValueError, match="x1 and x2"):
        CurveDefinition(interpolation=I.BEZIER, bezier=(1.5, 0, 0.5, 1))
    with pytest.raises(ValueError, match="overshoot"):
        CurveDefinition(interpolation=I.BEZIER, bezier=(0.3, -0.5, 0.6, 1.5))
    over = CurveDefinition(
        interpolation=I.BEZIER, bezier=(0.3, -0.5, 0.6, 1.5), allow_overshoot=True
    )
    assert min(cubic_bezier(u / 100, *over.bezier) for u in range(101)) < 0
    with pytest.raises(ValueError, match="only used"):
        CurveDefinition(interpolation=I.LINEAR, bezier=(0, 0, 1, 1))
    with pytest.raises(ValueError):
        CurveDefinition(interpolation=I.HERMITE, tension=2)


def test_channel_hold_before_after_and_step() -> None:
    ch = channel([(1.0, 5.0, curve(I.STEP)), (2.0, 9.0, curve(I.STEP))])
    assert ch.evaluate(0.0) == 5 and ch.evaluate(-100) == 5
    assert ch.evaluate(1.999) == 5 and ch.evaluate(2.0) == 9 and ch.evaluate(50) == 9
    single = channel([(0.5, 3.0, curve(I.LINEAR))])
    assert single.evaluate(0) == single.evaluate(10) == 3


def test_hermite_monotone_no_overshoot() -> None:
    c = curve(I.HERMITE)
    ch = channel([(0, 0, c), (1, 10, c), (2, 10, c), (3, 0, c), (4, 0, c)])
    values = [ch.evaluate(t / 100) for t in range(401)]
    assert min(values) >= -1e-9 and max(values) <= 10 + 1e-9
    assert all(v == pytest.approx(10) for v in values[100:201])  # flat hold stays flat
    assert ch.evaluate(1) == 10 and ch.evaluate(3) == 0  # passes through keys


def test_hermite_overshoot_when_allowed() -> None:
    c = curve(I.HERMITE, allow_overshoot=True)
    ch = channel([(0, 0, c), (1, 10, c), (2, 10, c), (3, 0, c)])
    assert max(ch.evaluate(t / 100) for t in range(301)) > 10


def test_hermite_smoother_than_linear_and_periodic() -> None:
    c = curve(I.HERMITE)
    keys = [(i / 8, math.sin(2 * math.pi * i / 8), c) for i in range(9)]
    ch = channel(keys, periodic=True)
    assert ch.evaluate(1 / 16) == pytest.approx(math.sin(math.pi / 8), abs=0.03)
    assert ch.tangents[0] == ch.tangents[-1]  # loop seam has one tangent
    slope_start = (ch.evaluate(1e-4) - ch.evaluate(0)) / 1e-4
    slope_end = (ch.evaluate(1) - ch.evaluate(1 - 1e-4)) / 1e-4
    assert slope_start == pytest.approx(slope_end, rel=1e-2)


def test_angles_and_shortest_path() -> None:
    assert wrap_degrees(350) == -10 and wrap_degrees(-190) == 170 and wrap_degrees(180) == 180
    keys = [(0, 350.0, curve(I.LINEAR)), (1, 10.0, curve(I.LINEAR))]
    assert channel(keys, angle=True).evaluate(0.5) == pytest.approx(180)  # numeric by default
    assert channel(keys, angle=True, shortest_path=True).evaluate(0.5) == pytest.approx(360)


def test_duplicate_times_refused() -> None:
    with pytest.raises(ValueError, match="same time"):
        channel([(1, 0, curve(I.LINEAR)), (1, 2, curve(I.LINEAR))])


def test_deterministic() -> None:
    c = curve(I.BEZIER, bezier=(0.2, 0.1, 0.3, 0.9))
    ch = channel([(0, 1, c), (0.7, -4, c), (1.3, 2, c)])
    assert [ch.evaluate(t / 37) for t in range(60)] == [ch.evaluate(t / 37) for t in range(60)]


# --- clips ---------------------------------------------------------------------------------------


def make_clip(**kw) -> AnimationClip:
    base = dict(
        id="c",
        name="c",
        character_id="chr_test",
        duration=2.0,
        fps=24.0,
        tracks=[
            BoneTrack(
                bone="arm",
                keys=[
                    BoneKeyframe(time=0, rotation=0),
                    BoneKeyframe(frame=24, rotation=90),
                    BoneKeyframe(time=2, rotation=0, x=5),
                ],
            ),
        ],
    )
    base.update(kw)
    return AnimationClip(**base)


def test_compile_and_sample_frame_keys() -> None:
    compiled = compile_clip(make_clip())
    assert set(compiled.channels) == {("bone", "arm", "rotation"), ("bone", "arm", "x")}
    s = sample_clip(compiled, 0.5)
    assert s.values[("bone", "arm", "rotation")] == pytest.approx(45)  # frame 24 @ 24 fps = 1 s
    assert s.values[("bone", "arm", "x")] == 5  # single key holds


def test_keyframe_time_xor_frame() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        BoneKeyframe(rotation=1)
    with pytest.raises(ValueError, match="exactly one"):
        BoneKeyframe(time=1, frame=2, rotation=1)
    with pytest.raises(ValueError):
        BoneKeyframe(time=-1, rotation=1)


def test_check_clip_codes() -> None:
    bad = make_clip(
        tracks=[
            BoneTrack(
                bone="a",
                keys=[
                    BoneKeyframe(time=0, rotation=1),
                    BoneKeyframe(frame=0, rotation=2),
                    BoneKeyframe(time=5, rotation=3),
                ],
            ),
            BoneTrack(bone="a", keys=[BoneKeyframe(time=0, x=1)]),
            PartTrack(part="p", keys=[]),
        ],
        events=[AnimationEvent(time=9, kind=EventKind.MARKER, name="late")],
    )
    codes = {p.split()[0] for p in check_clip(bad)}
    assert {"ANM009", "ANM010", "ANM013", "ANM014", "ANM015"} <= codes
    with pytest.raises(AnimationError):
        compile_clip(bad)
    # different properties at the same time are fine
    assert (
        check_clip(
            make_clip(
                tracks=[
                    BoneTrack(
                        bone="a",
                        keys=[BoneKeyframe(time=0, rotation=1), BoneKeyframe(time=0.0 + 1, x=2)],
                    )
                ]
            )
        )
        == []
    )


@pytest.mark.parametrize(
    ("mode", "t", "expected"),
    [
        ("once", -1, 0),
        ("once", 1.5, 1.5),
        ("once", 9, 2),
        ("loop", 2.0, 0),
        ("loop", 2.5, 0.5),
        ("loop", -0.5, 1.5),
        ("pingpong", 2.5, 1.5),
        ("pingpong", 3.9, 0.1),
        ("pingpong", 4.2, 0.2),
    ],
)
def test_clip_time_modes(mode, t, expected) -> None:
    clip = make_clip(loop=LoopSettings(mode=LoopMode(mode)))
    assert clip_time(clip, t) == pytest.approx(expected)


def test_clip_time_speed_offset() -> None:
    clip = make_clip(
        loop=LoopSettings(mode=LoopMode.LOOP), playback=PlaybackSettings(speed=2, offset=0.25)
    )
    assert clip_time(clip, 0.5) == pytest.approx(1.25)
    assert clip_time(clip, 1.0, time_offset=0.5, speed=0.5) == pytest.approx(
        0.75
    )  # (1-0.5)*0.5*2+0.25
    with pytest.raises(AnimationError):
        clip_time(clip, math.nan)


def test_part_visibility_is_stepped() -> None:
    clip = make_clip(
        tracks=[
            PartTrack(
                part="hat",
                keys=[
                    TransformKeyframe(time=0, visible=True),
                    TransformKeyframe(time=1, visible=False),
                ],
            )
        ]
    )
    c = compile_clip(clip)
    assert sample_clip(c, 0.99).values[("part", "hat", "visible")] == 1
    assert sample_clip(c, 1.0).values[("part", "hat", "visible")] == 0


def test_expression_track_sampling() -> None:
    clip = make_clip(
        tracks=[
            ExpressionTrack(
                keys=[
                    ExpressionKeyframe(time=0.5, expression="neutral"),
                    ExpressionKeyframe(
                        time=1.5, expression="happy", weight=0.8, curve=curve(I.LINEAR)
                    ),
                ]
            )
        ]
    )
    c = compile_clip(clip)
    assert sample_clip(c, 0).expression.a == "neutral"
    mid = sample_clip(c, 1.0).expression
    assert (mid.a, mid.b, mid.weight_b) == ("neutral", "happy", 0.8) and mid.u == pytest.approx(0.5)
    end = sample_clip(c, 2.0).expression
    assert end.b == "happy" and end.u == 1.0


def test_insert_and_remove_keys() -> None:
    clip = make_clip()
    track = BoneTrack(bone="arm", keys=[])
    c2 = insert_key(clip, track, BoneKeyframe(time=0.5, rotation=10))
    times = [k.seconds(24) for k in c2.tracks[0].keys]
    assert times == sorted(times) and 0.5 in times and c2 is not clip
    with pytest.raises(AnimationError, match="already has a key"):
        insert_key(c2, track, BoneKeyframe(time=0.5, rotation=20))
    c3 = insert_key(c2, track, BoneKeyframe(time=0.5, rotation=20), replace=True)
    assert [k.rotation for k in c3.tracks[0].keys if k.time == 0.5] == [20]
    c4 = insert_key(c3, BoneTrack(bone="leg", keys=[]), BoneKeyframe(time=1, rotation=5))
    assert len(c4.tracks) == 2
    with pytest.raises(AnimationError, match="after the clip end"):
        insert_key(c4, track, BoneKeyframe(time=9, rotation=1))
    c5 = remove_key(c4, "bone:leg", 1.0)
    assert len(c5.tracks) == 1  # empty track removed
    with pytest.raises(AnimationError, match="no key"):
        remove_key(c5, "bone:arm", 0.123)
    with pytest.raises(AnimationError, match="no track"):
        remove_key(c5, "bone:tail", 0)
    assert len(clip.tracks[0].keys) == 3  # original untouched


def test_events_windows() -> None:
    evs = [
        AnimationEvent(time=0, kind=EventKind.FOOT_CONTACT, name="a"),
        AnimationEvent(time=1.5, kind=EventKind.FOOT_LIFT, name="b"),
    ]
    once = make_clip(events=evs)
    assert [e.name for _t, e in events_between(once, 0, 10)] == ["a", "b"]
    loop = make_clip(events=evs, loop=LoopSettings(mode=LoopMode.LOOP))
    got = [(t, e.name) for t, e in events_between(loop, 0, 4.0)]
    assert got == [(0, "a"), (1.5, "b"), (2.0, "a"), (3.5, "b")]
    ping = make_clip(events=evs, loop=LoopSettings(mode=LoopMode.PINGPONG))
    assert [round(t, 3) for t, _e in events_between(ping, 0, 4.0)] == [0, 1.5, 2.5]
    with pytest.raises(AnimationError):
        events_between(loop, 2, 1)
