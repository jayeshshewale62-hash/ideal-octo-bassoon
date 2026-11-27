from __future__ import annotations

import math

import pytest

from studio.core.exceptions import RigError
from studio.rig.fk import BonePose
from studio.rig.ik import solve_ik_chain, solve_two_bone
from studio.rig.math2d import Vec2
from studio.rig.schemas import (
    BendDirection,
    BoneDefinition,
    IKChain,
    JointConstraint,
    RigDefinition,
    Transform2D,
)

ORIGIN = Vec2(0, 0)
P, N = BendDirection.POSITIVE, BendDirection.NEGATIVE


def close(a: Vec2, b: Vec2, tol: float = 1e-7) -> bool:
    return a.distance_to(b) <= tol


# --- pure solver -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "target", [Vec2(1.2, 0.3), Vec2(-0.5, 1.4), Vec2(0.1, -1.7), Vec2(0.6, 0.0)]
)
@pytest.mark.parametrize("bend", [P, N])
def test_reachable_targets_are_hit_exactly(target: Vec2, bend: BendDirection) -> None:
    s = solve_two_bone(ORIGIN, 1.0, 1.0, target, bend=bend)
    assert s.status == "reached"
    assert close(s.end, target)
    assert s.mid.distance_to(ORIGIN) == pytest.approx(1.0)
    assert s.end.distance_to(s.mid) == pytest.approx(1.0)


def test_bend_direction_sign() -> None:
    target = Vec2(math.sqrt(2), 0)
    pos = solve_two_bone(ORIGIN, 1, 1, target, bend=P)
    neg = solve_two_bone(ORIGIN, 1, 1, target, bend=N)
    # positive: lower bone turns clockwise on screen relative to the upper bone
    assert pos.lower_angle - pos.upper_angle == pytest.approx(90)
    assert neg.lower_angle - neg.upper_angle == pytest.approx(-90)
    assert pos.mid.y < 0 < neg.mid.y  # mirror images across the root->target line
    assert close(pos.end, target) and close(neg.end, target)


def test_pole_selects_side() -> None:
    target = Vec2(math.sqrt(2), 0)
    below = solve_two_bone(ORIGIN, 1, 1, target, bend=P, pole=Vec2(0.7, 3))
    above = solve_two_bone(ORIGIN, 1, 1, target, bend=N, pole=Vec2(0.7, -3))
    assert below.mid.y > 0 and above.mid.y < 0
    collinear = solve_two_bone(ORIGIN, 1, 1, target, bend=P, pole=Vec2(5, 0))
    assert collinear.bend_sign == 1  # falls back to the configured bend


def test_maximum_extension() -> None:
    s = solve_two_bone(ORIGIN, 2, 1, Vec2(3, 0))
    assert s.status == "reached"
    assert close(s.mid, Vec2(2, 0)) and close(s.end, Vec2(3, 0))


def test_unreachable_far_target_extends_towards_it() -> None:
    s = solve_two_bone(ORIGIN, 2, 1, Vec2(0, 10))
    assert s.status == "too_far" and not s.reached
    assert close(s.end, Vec2(0, 3))


def test_minimum_reach() -> None:
    exact = solve_two_bone(ORIGIN, 2, 1, Vec2(1, 0))
    assert exact.status == "reached" and close(exact.end, Vec2(1, 0))
    too_close = solve_two_bone(ORIGIN, 2, 1, Vec2(0.25, 0))
    assert too_close.status == "too_close"
    assert close(too_close.end, Vec2(1, 0))  # folded at the minimum reach along the line
    longer_lower = solve_two_bone(ORIGIN, 1, 2, Vec2(0.5, 0))
    assert longer_lower.status == "too_close"
    assert close(longer_lower.end, Vec2(1, 0))


def test_degenerate_target_on_root() -> None:
    s = solve_two_bone(ORIGIN, 1, 1, Vec2(0, 0), fallback_angle=90)
    assert s.status == "degenerate"
    assert close(s.end, ORIGIN, 1e-6)  # equal lengths fold back to the root
    assert all(math.isfinite(v) for v in (s.mid.x, s.mid.y, s.end.x, s.end.y))
    s2 = solve_two_bone(ORIGIN, 2, 1, Vec2(1e-12, 0), fallback_angle=0)
    assert s2.status in ("degenerate", "too_close")
    assert all(math.isfinite(v) for v in (s2.end.x, s2.end.y))


def test_invalid_inputs() -> None:
    with pytest.raises(RigError):
        solve_two_bone(ORIGIN, 0, 1, Vec2(1, 0))
    with pytest.raises(RigError):
        solve_two_bone(ORIGIN, 1, math.nan, Vec2(1, 0))
    with pytest.raises(RigError):
        solve_two_bone(ORIGIN, 1, 1, Vec2(math.inf, 0))


def test_deterministic() -> None:
    a = solve_two_bone(ORIGIN, 1.3, 0.9, Vec2(0.7, 1.1), bend=N)
    b = solve_two_bone(ORIGIN, 1.3, 0.9, Vec2(0.7, 1.1), bend=N)
    assert a == b


# --- rig chain ----------------------------------------------------------------------------------


def arm_rig(
    elbow: JointConstraint | None = None, shoulder: JointConstraint | None = None
) -> RigDefinition:
    return RigDefinition(
        id="rig_arm",
        character_id="chr_arm",
        root="body",
        bones=[
            BoneDefinition(id="body", length=0, control=True, rest=Transform2D(x=100, y=100)),
            BoneDefinition(
                id="upper",
                parent="body",
                length=50,
                rest=Transform2D(rotation=90),
                constraint=shoulder,
            ),
            BoneDefinition(
                id="lower", parent="upper", length=40, rest=Transform2D(x=50), constraint=elbow
            ),
        ],
        ik_chains=[IKChain(id="arm", upper="upper", lower="lower", bend=P)],
    )


def test_chain_reaches_target_and_fk_agrees() -> None:
    target = Vec2(140, 160)
    result = solve_ik_chain(arm_rig(), "arm", target)
    assert result.solution.reached and not result.limited
    assert result.error < 1e-7
    assert close(result.fk["lower"].tip, target)
    assert result.fk["upper"].head == Vec2(100, 100)


def test_chain_respects_parent_rotation() -> None:
    target = Vec2(60, 150)
    result = solve_ik_chain(arm_rig(), "arm", target, pose={"body": BonePose(rotation=37)})
    assert result.error < 1e-7


def test_chain_joint_limits_enforced() -> None:
    elbow = JointConstraint(min_rotation=0, max_rotation=30, preferred_bend=P)
    result = solve_ik_chain(arm_rig(elbow=elbow), "arm", Vec2(110, 120))  # needs a deep bend
    assert result.limited
    assert result.pose["lower"].rotation == 30
    assert result.error > 1.0  # the target cannot be reached within the limit
    assert 0 <= result.fk["lower"].local_rotation <= 30


def test_chain_locked_joint() -> None:
    result = solve_ik_chain(arm_rig(shoulder=JointConstraint(locked=True)), "arm", Vec2(160, 150))
    assert result.pose["upper"].rotation == 90
    assert any(e.reason == "locked" for e in result.limit_events)


def test_chain_unreachable_target() -> None:
    result = solve_ik_chain(arm_rig(), "arm", Vec2(1000, 100))
    assert result.solution.status == "too_far"
    assert close(result.end, Vec2(190, 100), 1e-6)


def test_chain_errors() -> None:
    with pytest.raises(RigError, match="unknown IK chain"):
        solve_ik_chain(arm_rig(), "leg", Vec2(0, 0))
    rig = arm_rig()
    bad = rig.model_copy(update={"ik_chains": [IKChain(id="arm", upper="lower", lower="upper")]})
    with pytest.raises(RigError, match="not a child"):
        solve_ik_chain(bad, "arm", Vec2(0, 0))
