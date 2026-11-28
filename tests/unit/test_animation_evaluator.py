from __future__ import annotations

import math

import pytest

from studio.animation.evaluator import (
    AnimationContext,
    CharacterAnimator,
    evaluate_character,
    single_clip_set,
)
from studio.animation.mesh import check_mesh, deform_mesh, generate_grid_mesh
from studio.animation.schemas import (
    AnimationClip,
    AnimationEvent,
    AnimationLayer,
    AnimationSet,
    BlendSettings,
    BoneKeyframe,
    BoneTrack,
    ControlKeyframe,
    DeformationKeyframe,
    DeformMesh,
    DeformTrack,
    EventKind,
    ExpressionKeyframe,
    ExpressionTrack,
    FaceTrack,
    IKKeyframe,
    IKTrack,
    LayerMode,
    LoopMode,
    LoopSettings,
    PartTrack,
    RootTrack,
    SecondaryMotionSettings,
    SpringDefinition,
    SpringDriver,
    TransformKeyframe,
    VertexWeight,
)
from studio.animation.secondary import SpringSolver, damping_ratio
from studio.characters.manager import CharacterStore
from studio.characters.parts import solve_parts
from studio.core.exceptions import AnimationError
from studio.core.project import Project
from studio.face.library import builtin_expression, load_viseme_set
from studio.face.manager import FaceStore
from studio.face.schemas import LipSyncTrack, VisemeEvent
from studio.rig.fk import solve_fk
from studio.rig.math2d import Vec2

CID = "chr_mira-vale"


@pytest.fixture
def ctx(project: Project) -> AnimationContext:
    CharacterStore(project).create("Mira Vale")
    face = FaceStore(project).create(CID).face
    loaded = CharacterStore(project).load(CID)
    return AnimationContext(
        character=loaded.character,
        rig=loaded.rig,
        clips={},
        face=face,
        expressions=lambda i: builtin_expression(i),
        expression_ids=None,
    )


def clip(tracks, *, duration=2.0, loop=LoopMode.ONCE, events=(), cid="c") -> AnimationClip:
    return AnimationClip(
        id=cid,
        name=cid,
        character_id=CID,
        duration=duration,
        tracks=tracks,
        loop=LoopSettings(mode=loop),
        events=list(events),
    )


def run(ctx: AnimationContext, c: AnimationClip, t: float, **set_kw):
    ctx.clips = {c.id: c}
    return CharacterAnimator(ctx, single_clip_set(c, **set_kw)).evaluate(t)


# --- bone / FK animation -------------------------------------------------------------------------


def test_bone_keys_animate_fk_hierarchy(ctx) -> None:
    c = clip(
        [
            BoneTrack(
                bone="upper_arm_l",
                keys=[BoneKeyframe(time=0, rotation=180), BoneKeyframe(time=1, rotation=90)],
            )
        ]
    )
    s0, s_half, s1 = (run(ctx, c, t) for t in (0, 0.5, 1))
    assert s_half.pose["upper_arm_l"].rotation == pytest.approx(135)
    assert s1.fk["upper_arm_l"].world_rotation == pytest.approx(0)  # spine -90 + 90
    # the child (hand) moves with the parent
    assert s0.fk["hand_l"].head.distance_to(s1.fk["hand_l"].head) > 100
    assert s1.fk["forearm_l"].head.distance_to(s1.fk["upper_arm_l"].tip) < 1e-9


def test_parent_movement_and_scale(ctx) -> None:
    c = clip(
        [
            BoneTrack(
                bone="spine",
                keys=[
                    BoneKeyframe(time=0, rotation=-90, scale_x=1),
                    BoneKeyframe(time=1, rotation=-60, scale_x=1.2),
                ],
            )
        ]
    )
    rest, moved = run(ctx, c, 0), run(ctx, c, 1)
    assert moved.fk["head"].tip.distance_to(rest.fk["head"].tip) > 50
    assert moved.fk["spine"].world_scale[0] == pytest.approx(1.2)


def test_joint_constraints_enforced_and_reported(ctx) -> None:
    c = clip(
        [
            BoneTrack(
                bone="forearm_l",
                keys=[BoneKeyframe(time=0, rotation=0), BoneKeyframe(time=1, rotation=200)],
            )
        ]
    )
    s = run(ctx, c, 1)
    assert s.fk["forearm_l"].local_rotation == 150
    assert any(d.code == "EVL001" and "forearm_l" in d.message for d in s.diagnostics)


def test_root_track_moves_whole_character(ctx) -> None:
    c = clip([RootTrack(keys=[TransformKeyframe(time=0, x=0), TransformKeyframe(time=1, x=100)])])
    a, b = run(ctx, c, 0), run(ctx, c, 1)
    for bone in ("root", "head", "foot_l"):
        assert b.fk[bone].head.x - a.fk[bone].head.x == pytest.approx(100)


def test_animated_ik_target(ctx) -> None:
    c = clip(
        [
            IKTrack(
                chain="arm_l",
                keys=[IKKeyframe(time=0, x=150, y=400), IKKeyframe(time=1, x=250, y=300)],
            )
        ]
    )
    for t, target in ((0, Vec2(150, 400)), (1, Vec2(250, 300)), (0.5, Vec2(200, 350))):
        s = run(ctx, c, t)
        assert s.fk["forearm_l"].tip.distance_to(target) < 1e-6
        assert s.ik[0]["status"] == "reached"
    far = clip([IKTrack(chain="arm_l", keys=[IKKeyframe(time=0, x=2000, y=0)])])
    s = run(ctx, far, 0)
    assert s.ik[0]["status"] == "too_far" and any(d.code == "EVL002" for d in s.diagnostics)


def test_ik_weight_blends_with_fk(ctx) -> None:
    c = clip([IKTrack(chain="arm_l", keys=[IKKeyframe(time=0, x=250, y=300, weight=0.0)])])
    s = run(ctx, c, 0)
    rest = solve_fk(ctx.rig)
    assert s.fk["forearm_l"].tip.distance_to(rest["forearm_l"].tip) < 1e-6  # weight 0 = pure FK


def test_part_tracks_and_visibility(ctx) -> None:
    c = clip(
        [
            PartTrack(
                part="hair",
                keys=[
                    TransformKeyframe(time=0, rotation=0, opacity=1),
                    TransformKeyframe(time=1, rotation=30, opacity=0.5, visible=False),
                ],
            )
        ]
    )
    s = run(ctx, c, 1)
    assert s.parts["hair"].visible is False and s.parts["hair"].opacity == pytest.approx(0.5)
    assert ctx.character.part_map()["hair"].transform.rotation == 0  # stored character untouched


# --- looping, determinism, invalid input ---------------------------------------------------------


def test_looping_and_once_outside_duration(ctx) -> None:
    keys = [
        BoneKeyframe(time=0, rotation=-90),
        BoneKeyframe(time=1, rotation=-60),
        BoneKeyframe(time=2, rotation=-90),
    ]
    once = clip([BoneTrack(bone="spine", keys=keys)])
    loop = clip([BoneTrack(bone="spine", keys=keys)], loop=LoopMode.LOOP, cid="l")
    assert run(ctx, once, 3.0).pose["spine"].rotation == -90  # holds last
    assert run(ctx, once, -1.0).pose["spine"].rotation == -90  # holds first
    assert run(ctx, loop, 3.0).pose["spine"].rotation == pytest.approx(-60)  # wraps
    assert run(ctx, loop, 2.0).pose["spine"].rotation == pytest.approx(
        run(ctx, loop, 0.0).pose["spine"].rotation
    )


def test_deterministic_and_invalid_time(ctx) -> None:
    c = clip(
        [
            BoneTrack(
                bone="neck",
                keys=[BoneKeyframe(time=0, rotation=0), BoneKeyframe(time=2, rotation=20)],
            )
        ]
    )
    ctx.clips = {c.id: c}
    an = CharacterAnimator(ctx, single_clip_set(c))
    a = [an.evaluate(t / 7).to_dict() for t in range(15)]
    b = [
        CharacterAnimator(ctx, single_clip_set(c)).evaluate(t / 7).to_dict()
        for t in reversed(range(15))
    ][::-1]
    assert a == b
    for bad in (math.nan, math.inf, "1"):
        with pytest.raises(AnimationError):
            an.evaluate(bad)  # type: ignore[arg-type]


def test_invalid_references_refused(ctx) -> None:
    c = clip(
        [
            BoneTrack(bone="wing", keys=[BoneKeyframe(time=0, rotation=1)]),
            FaceTrack(keys=[ControlKeyframe(time=0, values={"tail.wag": 1})]),
            ExpressionTrack(keys=[ExpressionKeyframe(time=0, expression="smug")]),
        ]
    )
    ctx.clips = {c.id: c}
    with pytest.raises(AnimationError) as err:
        CharacterAnimator(ctx, single_clip_set(c))
    text = str(err.value)
    assert "ANM004" not in text or "wing" in text
    assert "wing" in text and "tail.wag" in text and "smug" in text


# --- layers --------------------------------------------------------------------------------------


def _two_layer(ctx, mode, weight, mask=("full",), normalize=False):
    a = clip([BoneTrack(bone="neck", keys=[BoneKeyframe(time=0, rotation=10)])], cid="a")
    b = clip([BoneTrack(bone="neck", keys=[BoneKeyframe(time=0, rotation=30)])], cid="b")
    ctx.clips = {"a": a, "b": b}
    s = AnimationSet(
        id="s",
        name="s",
        character_id=CID,
        blend=BlendSettings(normalize=normalize),
        layers=[
            AnimationLayer(id="base", clip="a", order=0),
            AnimationLayer(id="top", clip="b", order=1, mode=mode, weight=weight, mask=list(mask)),
        ],
    )
    return CharacterAnimator(ctx, s).evaluate(0)


def test_layer_override_and_additive(ctx) -> None:
    assert _two_layer(ctx, LayerMode.OVERRIDE, 0.25).pose["neck"].rotation == pytest.approx(15)
    assert _two_layer(ctx, LayerMode.OVERRIDE, 1.0).pose["neck"].rotation == pytest.approx(30)
    # additive adds weight * (value - rest); neck rest is 0
    assert _two_layer(ctx, LayerMode.ADDITIVE, 0.5).pose["neck"].rotation == pytest.approx(25)
    state = _two_layer(ctx, LayerMode.OVERRIDE, 1.0)
    assert state.owners["bone:neck.rotation"] == "top"


def test_layer_masks_and_normalize(ctx) -> None:
    lower = _two_layer(ctx, LayerMode.OVERRIDE, 1.0, mask=("lower_body",))
    assert lower.pose["neck"].rotation == pytest.approx(10)  # neck is upper body: masked out
    upper = _two_layer(ctx, LayerMode.OVERRIDE, 1.0, mask=("upper_body",))
    assert upper.pose["neck"].rotation == pytest.approx(30)
    norm = _two_layer(ctx, LayerMode.OVERRIDE, 1.0, normalize=True)
    assert norm.pose["neck"].rotation == pytest.approx(20)  # (1*10 + 1*30) / 2


# --- face and lip-sync ---------------------------------------------------------------------------


def test_expression_transition_and_facial_keys(ctx) -> None:
    c = clip(
        [
            ExpressionTrack(
                keys=[
                    ExpressionKeyframe(time=0, expression="neutral"),
                    ExpressionKeyframe(time=1, expression="happy"),
                ]
            ),
            FaceTrack(
                keys=[
                    ControlKeyframe(time=0.4, values={"eye_l.blink": 0}),
                    ControlKeyframe(time=0.5, values={"eye_l.blink": 1}),
                    ControlKeyframe(time=0.6, values={"eye_l.blink": 0}),
                ]
            ),
        ]
    )
    start, mid, end = run(ctx, c, 0), run(ctx, c, 0.5), run(ctx, c, 1.5)
    assert start.face.values["mouth.corner_l"] == 0
    assert mid.face.values["mouth.corner_l"] == pytest.approx(0.4)
    assert end.face.values["mouth.corner_l"] == pytest.approx(0.8)
    assert mid.face.values["eye_l.blink"] == 1 and end.face.values["eye_l.blink"] == 0
    assert end.face.values["eye_l.squint"] == pytest.approx(0.35)  # expression still drives eyes


def test_expression_weight(ctx) -> None:
    c = clip([ExpressionTrack(keys=[ExpressionKeyframe(time=0, expression="happy", weight=0.5)])])
    assert run(ctx, c, 0).face.values["mouth.corner_l"] == pytest.approx(0.4)


def test_face_control_clamped(ctx) -> None:
    c = clip([FaceTrack(keys=[ControlKeyframe(time=0, values={"mouth.open": 3})])])
    s = run(ctx, c, 0)
    assert s.face.values["mouth.open"] == 1 and any(d.code == "EVL004" for d in s.diagnostics)


def test_lipsync_owns_mouth_expression_keeps_eyes(ctx) -> None:
    ctx.lipsync = LipSyncTrack(id="t", events=[VisemeEvent(viseme="ai", start=0.2, end=0.6)])
    ctx.visemes = load_viseme_set()
    from studio.animation.schemas import LipSyncBinding

    c = clip(
        [
            ExpressionTrack(keys=[ExpressionKeyframe(time=0, expression="happy")]),
            FaceTrack(
                keys=[ControlKeyframe(time=0, values={"mouth.open": 0.1, "brow_l.raise": 0.5})]
            ),
        ]
    )
    s = run(ctx, c, 0.4, lipsync=LipSyncBinding(path="x.yaml"))
    assert s.lips is not None and s.lips.viseme == "ai"
    assert s.face.values["mouth.open"] == pytest.approx(0.8)  # speech wins over the key
    assert s.face.values["brow_l.raise"] == pytest.approx(0.5)  # key kept for brows
    assert s.face.values["eye_l.squint"] == pytest.approx(0.35)  # expression keeps the eyes
    assert s.face.values["mouth.corner_l"] == pytest.approx(
        0.8
    )  # corners: expression + rest viseme
    assert any(d.code == "EVL005" for d in s.diagnostics)
    assert s.owners["face:face.mouth.open"] == "lipsync"
    before = run(ctx, c, 0.0, lipsync=LipSyncBinding(path="x.yaml", start=0.5))
    assert before.lips is None and before.face.values["mouth.open"] == pytest.approx(0.1)


def test_face_tracks_without_face_rig(ctx) -> None:
    ctx.face = None
    c = clip([FaceTrack(keys=[ControlKeyframe(time=0, values={"mouth.open": 1})])])
    ctx.clips = {c.id: c}
    with pytest.raises(AnimationError, match="no facial rig"):
        CharacterAnimator(ctx, single_clip_set(c))


# --- events --------------------------------------------------------------------------------------


def test_events_in_evaluation_window(ctx) -> None:
    c = clip(
        [BoneTrack(bone="neck", keys=[BoneKeyframe(time=0, rotation=0)])],
        loop=LoopMode.LOOP,
        events=[AnimationEvent(time=0.5, kind=EventKind.HAND_CONTACT, name="touch")],
    )
    ctx.clips = {c.id: c}
    an = CharacterAnimator(ctx, single_clip_set(c))
    assert an.evaluate(0.5, event_window=1 / 24).events[0]["name"] == "touch"
    assert an.evaluate(0.6, event_window=1 / 24).events == []
    assert an.evaluate(2.5, event_window=1 / 24).events[0]["kind"] == "hand_contact"  # next loop


# --- secondary motion ----------------------------------------------------------------------------


def _spring(**kw) -> SpringDefinition:
    base = dict(
        id="s",
        target="hair",
        driver=SpringDriver(bone="head", signal="x"),
        gain=1.0,
        max_displacement=50,
    )
    base.update(kw)
    return SpringDefinition(**base)


def _step_signal(t: float) -> dict[str, float]:
    return {"s": 10.0 if t >= 0.1 else 0.0}


def test_spring_lags_overshoots_and_settles() -> None:
    solver = SpringSolver(
        SecondaryMotionSettings(springs=[_spring(stiffness=200, damping=8)], window=3), _step_signal
    )
    just_after = solver.offsets_at(0.11)["s"].offset
    later = [solver.offsets_at(0.1 + k * 0.02)["s"].offset for k in range(1, 60)]
    assert just_after < -8  # lags behind the jump
    assert max(later) > 0  # overshoots (under-damped)
    assert abs(solver.offsets_at(2.5)["s"].offset) < 0.05  # settles


def test_spring_damping_and_clamp() -> None:
    heavy = SpringSolver(
        SecondaryMotionSettings(springs=[_spring(stiffness=200, damping=60)]), _step_signal
    )
    assert all(
        heavy.offsets_at(0.1 + k * 0.02)["s"].offset <= 1e-9 for k in range(1, 80)
    )  # no overshoot
    assert damping_ratio(_spring(stiffness=200, damping=60)) > 1
    clamped = SpringSolver(
        SecondaryMotionSettings(springs=[_spring(max_displacement=3)]), _step_signal
    )
    out = clamped.offsets_at(0.11)["s"]
    assert out.offset == -3 and out.clamped


def test_spring_stability_and_determinism() -> None:
    stiff = _spring(stiffness=10_000, damping=1, mass=0.01)  # far beyond the explicit-step limit
    solver = SpringSolver(
        SecondaryMotionSettings(springs=[stiff]), lambda t: {"s": math.sin(7 * t)}
    )
    values = [solver.offsets_at(t / 13)["s"].offset for t in range(60)]
    assert all(math.isfinite(v) and abs(v) <= 50 for v in values)
    fresh = SpringSolver(SecondaryMotionSettings(springs=[stiff]), lambda t: {"s": math.sin(7 * t)})
    assert [fresh.offsets_at(t / 13)["s"].offset for t in reversed(range(60))][::-1] == values
    assert solver.offsets_at(0)["s"].offset == 0 and solver.offsets_at(-1)["s"].offset == 0  # reset


def test_springs_in_evaluator(ctx) -> None:
    c = clip(
        [
            RootTrack(
                keys=[
                    TransformKeyframe(time=0, x=0),
                    TransformKeyframe(time=0.2, x=200),
                    TransformKeyframe(time=2, x=200),
                ]
            )
        ]
    )
    ctx.clips = {c.id: c}
    s = single_clip_set(
        c, secondary=SecondaryMotionSettings(springs=[_spring(gain=0.3, max_displacement=20)])
    )
    an = CharacterAnimator(ctx, s)
    moving = an.evaluate(0.2)
    settled = an.evaluate(1.9)
    rest_rot = solve_parts(ctx.character, solve_fk(ctx.rig))["hair"].frame.rotation_degrees
    assert abs(moving.parts["hair"].frame.rotation_degrees - rest_rot) > 1
    assert abs(settled.parts["hair"].frame.rotation_degrees - rest_rot) < 0.5


# --- meshes --------------------------------------------------------------------------------------


def test_grid_mesh_valid_and_follows_bones(ctx) -> None:
    mesh = generate_grid_mesh(
        ctx.character,
        ctx.rig,
        "upper_arm_l",
        "arm",
        columns=4,
        rows=1,
        bones=["upper_arm_l", "forearm_l"],
    )
    assert [i for i in check_mesh(mesh, ctx.character, ctx.rig) if i[1] == "error"] == []
    for ws in mesh.weights:
        assert sum(w.weight for w in ws) == pytest.approx(1.0)
    ctx.meshes = {"arm": mesh}
    c = clip(
        [
            BoneTrack(
                bone="upper_arm_l",
                keys=[BoneKeyframe(time=0, rotation=180), BoneKeyframe(time=1, rotation=120)],
            )
        ]
    )
    rest, moved = run(ctx, c, 0, meshes=["arm"]), run(ctx, c, 1, meshes=["arm"])
    rest_mesh, moved_mesh = rest.meshes["arm"], moved.meshes["arm"]
    bind_pts = [
        solve_parts(ctx.character, solve_fk(ctx.rig))["upper_arm_l"].artwork.apply(Vec2(x, y))
        for x, y in mesh.vertices
    ]
    assert all(
        a.distance_to(b) < 1e-6 for a, b in zip(rest_mesh.vertices, bind_pts, strict=True)
    )  # rest = bind
    assert (
        max(a.distance_to(b) for a, b in zip(rest_mesh.vertices, moved_mesh.vertices, strict=True))
        > 50
    )
    assert moved_mesh.flipped == []


def test_mesh_validation_codes(ctx) -> None:
    bad = DeformMesh(
        id="m",
        character_id=CID,
        part="nope",
        vertices=[(0, 0), (1, 0), (2, 0)],
        triangles=[(0, 1, 5), (0, 1, 2), (0, 0, 1)],
        weights=[
            [VertexWeight(bone="spine", weight=0.7)],
            [VertexWeight(bone="ghost", weight=1.5)],
            [VertexWeight(bone="spine", weight=0.5), VertexWeight(bone="spine", weight=0.5)],
        ],
        shapes={"squash": [(0, 1)]},
    )
    codes = {c for c, _s, _m in check_mesh(bad, ctx.character, ctx.rig)}
    assert {"MSH001", "MSH003", "MSH004", "MSH006", "MSH007", "MSH008", "MSH009", "MSH010"} <= codes
    empty = DeformMesh(id="e", character_id=CID, part="head", vertices=[], triangles=[])
    assert "MSH002" in {c for c, _s, _m in check_mesh(empty, ctx.character, ctx.rig)}


def test_unweighted_vertices_rigid_and_shapes(ctx) -> None:
    rest = solve_fk(ctx.rig)
    parts = solve_parts(ctx.character, rest)
    mesh = DeformMesh(
        id="m",
        character_id=CID,
        part="head",
        vertices=[(0, 0), (10, 0), (0, 10)],
        triangles=[(0, 1, 2)],
        weights=[[], [], []],
        shapes={"stretch": [(0, 0), (5, 0), (0, 0)]},
    )
    out = deform_mesh(
        mesh,
        part_rest=parts["head"],
        part_now=parts["head"],
        bind=rest,
        fk=rest,
        shape_weights={"stretch": 1.0},
    )
    expected = parts["head"].artwork.apply(Vec2(15, 0))
    assert out.vertices[1].distance_to(expected) < 1e-9
    with pytest.raises(AnimationError, match="no shape"):
        deform_mesh(
            mesh,
            part_rest=parts["head"],
            part_now=parts["head"],
            bind=rest,
            fk=rest,
            shape_weights={"bulge": 1},
        )
    flip = DeformMesh(
        id="f",
        character_id=CID,
        part="head",
        vertices=[(0, 0), (10, 0), (0, 10)],
        triangles=[(0, 1, 2)],
        weights=[[], [], []],
        shapes={"flip": [(0, 0), (-20, 0), (0, 0)]},
    )
    flipped = deform_mesh(
        flip,
        part_rest=parts["head"],
        part_now=parts["head"],
        bind=rest,
        fk=rest,
        shape_weights={"flip": 1.0},
    )
    assert flipped.flipped == [0]


def test_deform_track_drives_shapes(ctx) -> None:
    mesh = DeformMesh(
        id="m",
        character_id=CID,
        part="head",
        vertices=[(0, 0), (10, 0), (0, 10)],
        triangles=[(0, 1, 2)],
        weights=[[], [], []],
        shapes={"stretch": [(0, 0), (5, 0), (0, 0)]},
    )
    ctx.meshes = {"m": mesh}
    c = clip(
        [
            DeformTrack(
                mesh="m",
                keys=[
                    DeformationKeyframe(time=0, weights={"stretch": 0}),
                    DeformationKeyframe(time=1, weights={"stretch": 1}),
                ],
            )
        ]
    )
    a, b = run(ctx, c, 0, meshes=["m"]), run(ctx, c, 1, meshes=["m"])
    assert a.meshes["m"].vertices[1].distance_to(b.meshes["m"].vertices[1]) == pytest.approx(5)


def test_evaluate_character_helper(ctx) -> None:
    c = clip([BoneTrack(bone="neck", keys=[BoneKeyframe(time=0, rotation=5)])])
    ctx.clips = {c.id: c}
    assert evaluate_character(ctx, single_clip_set(c), 0.0).pose["neck"].rotation == 5
