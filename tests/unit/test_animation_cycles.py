"""Motion cycles are verified numerically through the real rig (IK -> FK -> foot positions)."""

from __future__ import annotations

import itertools

import pytest

from studio.animation.clip import events_between, sorted_events
from studio.animation.cycles import (
    generate_idle,
    generate_locomotion,
    generate_nod,
    generate_point,
    generate_wave,
    locomotion_params,
)
from studio.animation.evaluator import AnimationContext, CharacterAnimator, single_clip_set
from studio.animation.schemas import AnimationClip
from studio.characters.manager import CharacterStore
from studio.core.exceptions import AnimationError
from studio.core.project import Project
from studio.face.library import builtin_expression
from studio.face.manager import FaceStore

CID = "chr_mira-vale"
GROUND_TOL = 1e-6


@pytest.fixture(scope="module")
def rigged(tmp_path_factory):
    from studio.core.config import load_settings
    from tests.conftest import CONFIG_DIR

    project = Project.create(
        "cycles", load_settings(CONFIG_DIR), projects_dir=tmp_path_factory.mktemp("p")
    )
    CharacterStore(project).create("Mira Vale")
    face = FaceStore(project).create(CID).face
    loaded = CharacterStore(project).load(CID)
    return loaded.character, loaded.rig, face


def animator(rigged, clip: AnimationClip) -> CharacterAnimator:
    character, rig, face = rigged
    ctx = AnimationContext(
        character=character,
        rig=rig,
        clips={clip.id: clip},
        face=face,
        expressions=builtin_expression,
    )
    return CharacterAnimator(ctx, single_clip_set(clip))


def sample(an: CharacterAnimator, clip: AnimationClip, n: int = 200):
    return [an.evaluate(clip.duration * i / n) for i in range(n + 1)]


def contacts(clip: AnimationClip, state) -> dict[str, bool]:
    ground = clip.cycle.parameters["ground_y"]
    return {s: abs(state.fk[f"shin_{s}"].tip.y - ground) < GROUND_TOL for s in ("l", "r")}


@pytest.fixture(scope="module")
def walk(rigged):
    character, rig, _ = rigged
    clip = generate_locomotion(character, rig, locomotion_params("walk", rig))
    return clip, animator(rigged, clip)


@pytest.fixture(scope="module")
def run_clip(rigged):
    character, rig, _ = rigged
    clip = generate_locomotion(character, rig, locomotion_params("run", rig))
    return clip, animator(rigged, clip)


# --- walk ----------------------------------------------------------------------------------------


def test_walk_drives_rig_through_ik_without_errors(walk) -> None:
    clip, an = walk
    for s in sample(an, clip):
        assert [ik["status"] for ik in s.ik] == ["reached", "reached"]
        assert max(ik["error"] for ik in s.ik) < 1e-6
        assert s.diagnostics == []  # no clamps, no IK misses anywhere in the cycle


def test_walk_stance_swing_and_alternation(walk) -> None:
    clip, an = walk
    beta = clip.cycle.parameters["stance"]
    states = sample(an, clip, 100)
    planted = [contacts(clip, s) for s in states]
    left_phase = [p for p, c in zip(range(101), planted, strict=True) if c["l"]]
    assert all(
        i / 100 <= beta + 1e-9 or i == 100 for i in left_phase
    )  # left planted only in stance
    assert sum(c["l"] for c in planted) == pytest.approx(beta * 100, abs=2)
    swing_l = [s.fk["shin_l"].tip.y for i, s in enumerate(states) if 0.65 <= i / 100 <= 0.95]
    assert min(swing_l) < clip.cycle.parameters["ground_y"] - 20  # foot lift
    assert any(c["l"] and c["r"] for c in planted)  # double support: a walk
    assert not any(not c["l"] and not c["r"] for c in planted)  # never airborne
    # alternation: right foot is half a cycle behind the left
    for i in range(50):
        assert planted[i]["l"] == planted[i + 50]["r"]


def test_walk_stance_foot_moves_backward_relative_to_hip(walk) -> None:
    clip, an = walk
    xs = [an.evaluate(clip.duration * i / 20).fk["shin_l"].tip.x for i in range(0, 12)]
    facing = -1 if clip.cycle.facing == "left" else 1
    deltas = [b - a for a, b in itertools.pairwise(xs)]
    assert all(d * facing < 0 for d in deltas)  # moves opposite to the facing direction


def test_walk_hip_bob_head_stable_arm_counter_swing(walk) -> None:
    clip, an = walk
    s0, s_pass = an.evaluate(0.0), an.evaluate(clip.duration * 0.25)
    assert s0.fk["root"].head.y > s_pass.fk["root"].head.y  # lowest at contact (+y down)
    heads = [s.fk["head"].world_rotation for s in sample(an, clip, 40)]
    assert max(heads) - min(heads) < 1e-3  # head stays level (keys are stored to 4 decimals)
    left = [s.fk["upper_arm_l"].world_rotation for s in sample(an, clip, 40)]
    right = [s.fk["upper_arm_r"].world_rotation for s in sample(an, clip, 40)]
    corr = sum((a - left[0]) * (b - right[0]) for a, b in zip(left, right, strict=True))
    assert corr < 0  # arms swing in opposition


def test_walk_loop_continuity(walk) -> None:
    clip, an = walk
    a, b = an.evaluate(0.0), an.evaluate(clip.duration)
    for bone in a.fk.order:
        assert a.fk[bone].head.distance_to(b.fk[bone].head) < 1e-9
    eps = 1e-4
    before, after = an.evaluate(clip.duration - eps), an.evaluate(clip.duration + eps)
    for bone in ("root", "shin_l", "foot_r", "upper_arm_l", "head"):
        assert before.fk[bone].tip.distance_to(after.fk[bone].tip) < 0.5  # no jump across the seam
    # arbitrary timestamps, including many cycles later, repeat the cycle
    for t in (0.137, 0.73, 0.999):
        assert (
            an.evaluate(t)
            .fk["shin_r"]
            .tip.distance_to(an.evaluate(t + 7 * clip.duration).fk["shin_r"].tip)
            < 1e-6
        )


def test_walk_events_match_contacts(walk) -> None:
    clip, an = walk
    for t, ev in sorted_events(clip):
        state = an.evaluate(t)
        side = ev.data["foot"]
        if ev.kind.value == "foot_contact":
            assert contacts(clip, state)[side]
        elif ev.kind.value == "foot_lift":
            assert abs(state.fk[f"shin_{side}"].tip.y - clip.cycle.parameters["ground_y"]) < 1e-6
            assert not contacts(clip, an.evaluate(t + 0.03))[side]
    assert len(events_between(clip, 0, 3 * clip.duration)) == 12


def test_walk_speed_and_stride(rigged) -> None:
    character, rig, _ = rigged
    slow = generate_locomotion(
        character, rig, locomotion_params("walk", rig, stride=300, duration=1.0)
    )
    fast = generate_locomotion(
        character, rig, locomotion_params("walk", rig, speed=600, duration=0.75)
    )
    assert slow.cycle.speed == pytest.approx(300) and fast.cycle.speed == pytest.approx(600)
    assert fast.cycle.distance_per_cycle == pytest.approx(450)
    an = animator(rigged, fast)
    assert all(max(ik["error"] for ik in s.ik) < 1e-6 for s in sample(an, fast, 60))
    with pytest.raises(AnimationError, match=r"joint limits|too long"):
        generate_locomotion(character, rig, locomotion_params("walk", rig, speed=900, duration=1.0))
    with pytest.raises(AnimationError, match="must equal speed"):
        locomotion_params("walk", rig, stride=300, duration=1.0, speed=500)
    with pytest.raises(AnimationError):
        locomotion_params("walk", rig, stance=0.4)
    with pytest.raises(AnimationError, match="unknown cycle parameter"):
        locomotion_params("walk", rig, wobble=1.0)


def test_character_scale_adaptation(project) -> None:
    store = CharacterStore(project)
    small = store.create("Pip", height_units=500)
    big = store.create("Gus", height_units=1500)
    s = generate_locomotion(small.character, small.rig, locomotion_params("walk", small.rig))
    b = generate_locomotion(big.character, big.rig, locomotion_params("walk", big.rig))
    assert b.cycle.distance_per_cycle == pytest.approx(3 * s.cycle.distance_per_cycle, rel=1e-3)


# --- run -----------------------------------------------------------------------------------------


def test_run_flight_landing_recovery_and_distinct_from_walk(run_clip, walk) -> None:
    clip, an = run_clip
    states = sample(an, clip, 140)
    planted = [contacts(clip, s) for s in states]
    assert any(not c["l"] and not c["r"] for c in planted)  # flight phase
    assert not any(c["l"] and c["r"] for c in planted)  # never double support
    for s in states:
        assert max(ik["error"] for ik in s.ik) < 1e-6 and s.diagnostics == []
    landings = [(t, e) for t, e in sorted_events(clip) if e.kind.value == "foot_contact"]
    assert len(landings) == 2
    for t, e in landings:
        assert contacts(clip, an.evaluate(t))[e.data["foot"]]
    # recovery: early swing pulls the foot back behind the lift-off point
    facing = -1 if clip.cycle.facing == "left" else 1
    lift_t = clip.cycle.parameters["stance"] * clip.duration
    x_lift = an.evaluate(lift_t).fk["shin_l"].tip.x
    x_after = an.evaluate(lift_t + 0.05).fk["shin_l"].tip.x
    assert (x_after - x_lift) * facing < 0
    walk_clip, _ = walk
    assert clip.cycle.speed > walk_clip.cycle.speed
    assert clip.cycle.parameters["stance"] < 0.5 < walk_clip.cycle.parameters["stance"]


def test_run_loop_continuity(run_clip) -> None:
    clip, an = run_clip
    a, b = an.evaluate(0.0), an.evaluate(clip.duration)
    assert all(a.fk[x].tip.distance_to(b.fk[x].tip) < 1e-9 for x in a.fk.order)
    eps = 1e-4
    before, after = an.evaluate(clip.duration - eps), an.evaluate(clip.duration + eps)
    assert all(before.fk[x].tip.distance_to(after.fk[x].tip) < 1.0 for x in a.fk.order)


# --- idle ----------------------------------------------------------------------------------------


def test_idle_breathing_deterministic_and_amplitude(rigged) -> None:
    character, rig, face = rigged
    clip = generate_idle(character, rig, face, seed=7)
    an = animator(rigged, clip)
    exhale = an.evaluate(0.0)
    inhale = an.evaluate(clip.duration / 2)
    assert inhale.parts["upper_torso"].frame.scale[1] > exhale.parts["upper_torso"].frame.scale[1]
    assert inhale.fk["upper_arm_l"].head.y < exhale.fk["upper_arm_l"].head.y  # shoulders rise
    again = generate_idle(character, rig, face, seed=7)
    assert again == clip
    assert generate_idle(character, rig, face, seed=8) != clip
    still = generate_idle(character, rig, face, amount=0.0, blinks=0, weight_shift=False)
    an0 = animator(rigged, still)
    a, b = an0.evaluate(0.3), an0.evaluate(2.1)
    assert all(a.fk[x].tip.distance_to(b.fk[x].tip) < 1e-9 for x in a.fk.order)
    with pytest.raises(AnimationError):
        generate_idle(character, rig, face, breaths=0)


def test_idle_blinks_optional(rigged) -> None:
    character, rig, face = rigged
    clip = generate_idle(character, rig, face, blinks=2)
    an = animator(rigged, clip)
    blink_times = [t for t, e in sorted_events(clip) if e.name.startswith("blink")]
    assert len(blink_times) == 2
    assert an.evaluate(blink_times[0]).face.values["eye_l.blink"] == pytest.approx(1.0)
    assert an.evaluate(0.0).face.values["eye_l.blink"] == 0
    no_face = generate_idle(character, rig, None, blinks=2)
    assert not any(t.kind == "face" for t in no_face.tracks)
    loop_a, loop_b = an.evaluate(0.0), an.evaluate(clip.duration)
    assert all(loop_a.fk[x].tip.distance_to(loop_b.fk[x].tip) < 1e-9 for x in loop_a.fk.order)


# --- gestures ------------------------------------------------------------------------------------


def test_gestures(rigged) -> None:
    character, rig, _ = rigged
    wave = generate_wave(character, rig)
    an = animator(rigged, wave)
    raised = an.evaluate(1.0)
    assert raised.fk["hand_l"].head.y < an.evaluate(0.0).fk["hand_l"].head.y - 200  # hand up
    assert [e.kind.value for _t, e in sorted_events(wave)] == [
        "gesture_start",
        "marker",
        "gesture_end",
    ]
    point = generate_point(character, rig)
    held = animator(rigged, point).evaluate(1.0)
    target = point.cycle.parameters
    assert held.ik[0]["status"] == "reached" and held.ik[0]["error"] < 1e-6
    assert (
        held.fk["forearm_r"].tip.distance_to(
            __import__("studio.rig.math2d", fromlist=["Vec2"]).Vec2(target["x"], target["y"])
        )
        < 1e-6
    )
    nod = generate_nod(character, rig)
    assert animator(rigged, nod).evaluate(0.3).pose["neck"].rotation > 5
