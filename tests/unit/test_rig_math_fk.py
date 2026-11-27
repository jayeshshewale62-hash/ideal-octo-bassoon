from __future__ import annotations

import math

import pytest

from studio.core.exceptions import RigError
from studio.rig.fk import BonePose, parse_rotation_overrides, solve_fk
from studio.rig.math2d import Affine, Vec2, normalize_angle, wrap_into_range
from studio.rig.schemas import BoneDefinition, JointConstraint, RigDefinition, Transform2D


def bone(bid, parent, length, x=0.0, y=0.0, rot=0.0, sx=1.0, sy=1.0, **kw) -> BoneDefinition:
    return BoneDefinition(
        id=bid,
        parent=parent,
        length=length,
        rest=Transform2D(x=x, y=y, rotation=rot, scale_x=sx, scale_y=sy),
        **kw,
    )


def rig_of(*bones: BoneDefinition, root: str = "a") -> RigDefinition:
    return RigDefinition(id="rig_test", character_id="chr_test", root=root, bones=list(bones))


def approx(p: Vec2, x: float, y: float, tol: float = 1e-9) -> bool:
    return abs(p.x - x) <= tol and abs(p.y - y) <= tol


# --- math -----------------------------------------------------------------------------------


def test_affine_composition_and_inverse() -> None:
    m = Affine.from_trs(10, 20, 30, 2, 3)
    p = Vec2(1.5, -4)
    back = m.inverse().apply(m.apply(p))
    assert approx(back, p.x, p.y, 1e-12)
    assert (m @ Affine.identity()).almost_equal(m)
    # composition applies the right-hand matrix first
    t, r = Affine.translation(5, 0), Affine.rotation(90)
    assert approx((t @ r).apply(Vec2(1, 0)), 5, 1)
    assert approx((r @ t).apply(Vec2(1, 0)), 0, 6)


def test_rotation_is_clockwise_on_screen() -> None:
    # +90 degrees turns +x (right) into +y (down) in screen space
    assert approx(Affine.rotation(90).apply(Vec2(1, 0)), 0, 1, 1e-12)


def test_singular_matrix() -> None:
    with pytest.raises(ValueError, match="singular"):
        Affine.scaling(0, 1).inverse()


@pytest.mark.parametrize(
    ("a", "n"), [(0, 0), (180, 180), (-180, 180), (190, -170), (540, 180), (-725, -5)]
)
def test_normalize_angle(a: float, n: float) -> None:
    assert normalize_angle(a) == pytest.approx(n)


@pytest.mark.parametrize(
    ("a", "lo", "hi", "out"),
    [
        (-90, 0, 360, 270),
        (370, -10, 30, 10),
        (200, -180, 0, -160),
        (100, -10, 10, 100),
        (-100, -10, 10, -100),
        (350, -10, 10, -10),
    ],
)
def test_wrap_into_range(a: float, lo: float, hi: float, out: float) -> None:
    assert wrap_into_range(a, lo, hi) == pytest.approx(out)


# --- FK ------------------------------------------------------------------------------------


def test_single_bone() -> None:
    fk = solve_fk(rig_of(bone("a", None, 10, x=5, y=5, rot=90)))
    assert approx(fk["a"].head, 5, 5)
    assert approx(fk["a"].tip, 5, 15)
    assert fk["a"].world_rotation == pytest.approx(90)


def test_nested_chain_and_parent_rotation() -> None:
    rig = rig_of(
        bone("a", None, 10),
        bone("b", "a", 5, x=10),
        bone("c", "b", 2, x=5),
    )
    fk = solve_fk(rig)
    assert approx(fk["c"].tip, 17, 0)
    # rotating the parent moves every descendant
    fk = solve_fk(rig, {"a": BonePose(rotation=90)})
    assert approx(fk["b"].head, 0, 10, 1e-9)
    assert approx(fk["c"].tip, 0, 17, 1e-9)
    # child rotation is relative to the parent
    fk = solve_fk(rig, {"a": BonePose(rotation=90), "b": BonePose(rotation=-90)})
    assert fk["b"].world_rotation == pytest.approx(0)
    assert approx(fk["c"].tip, 7, 10, 1e-9)


def test_child_offset_and_scale_propagation() -> None:
    rig = rig_of(bone("a", None, 10, sx=2, sy=2), bone("b", "a", 5, x=10, y=1))
    fk = solve_fk(rig)
    assert approx(fk["b"].head, 20, 2)
    assert approx(fk["b"].tip, 30, 2)
    assert fk["b"].world_scale == pytest.approx((2, 2))


def test_inherit_flags() -> None:
    rig = rig_of(
        bone("a", None, 10, rot=90, sx=2, sy=2),
        bone("b", "a", 5, x=10, inherit_rotation=False),
        bone("c", "a", 5, x=10, inherit_scale=False),
    )
    fk = solve_fk(rig)
    assert approx(fk["b"].head, 0, 20, 1e-9)
    assert fk["b"].world_rotation == pytest.approx(0)
    assert approx(fk["b"].tip, 10, 20, 1e-9)  # scale 2 still inherited
    assert fk["c"].world_scale == pytest.approx((1, 1))
    assert approx(fk["c"].tip, 0, 25, 1e-9)


def test_deterministic_results() -> None:
    rig = rig_of(
        bone("a", None, 3), bone("z", "a", 1, x=3, rot=33.3), bone("m", "a", 2, x=3, rot=-12)
    )
    first = solve_fk(rig, {"z": BonePose(rotation=12.5)})
    second = solve_fk(rig, {"z": BonePose(rotation=12.5)})
    assert first.order == second.order == ["a", "m", "z"]
    assert all(first[b].matrix == second[b].matrix for b in first.order)


def test_constraints_clamp_and_lock() -> None:
    rig = rig_of(
        bone("a", None, 10),
        bone("b", "a", 5, x=10, constraint=JointConstraint(min_rotation=-30, max_rotation=45)),
        bone("c", "b", 5, x=5, rot=10, constraint=JointConstraint(locked=True)),
    )
    fk = solve_fk(rig, {"b": BonePose(rotation=90), "c": BonePose(rotation=-50)})
    assert fk["b"].local_rotation == 45
    assert fk["c"].local_rotation == 10
    assert {(e.bone, e.reason) for e in fk.events} == {("b", "max"), ("c", "locked")}
    fk = solve_fk(rig, {"b": BonePose(rotation=-100)})
    assert fk["b"].local_rotation == -30
    # an equivalent angle (360 + 20) is re-expressed, not reported as a clamp
    fk = solve_fk(rig, {"b": BonePose(rotation=380)})
    assert fk["b"].local_rotation == pytest.approx(20)
    assert fk.events == []


def test_contradictory_constraint_refused() -> None:
    rig = rig_of(bone("a", None, 1, constraint=JointConstraint(min_rotation=10, max_rotation=-10)))
    with pytest.raises(RigError, match="greater than"):
        solve_fk(rig)


@pytest.mark.parametrize(
    ("bones", "message"),
    [
        ((bone("a", None, 1), bone("a", None, 1)), "duplicate"),
        ((bone("b", None, 1),), "root bone 'a' is not defined"),
        ((bone("a", "x", 1),), "must not have a parent"),
        ((bone("a", None, 1), bone("b", None, 1)), "no parent"),
        ((bone("a", None, 1), bone("b", "ghost", 1)), "unknown parent"),
        ((bone("a", None, 1), bone("b", "c", 1), bone("c", "b", 1)), "not connected"),
    ],
)
def test_structural_errors(bones, message: str) -> None:
    with pytest.raises(RigError, match=message):
        solve_fk(rig_of(*bones))


def test_pose_unknown_bone() -> None:
    with pytest.raises(RigError, match="unknown bones"):
        solve_fk(rig_of(bone("a", None, 1)), {"nope": BonePose(rotation=1)})


def test_invalid_transform_values_rejected() -> None:
    with pytest.raises(ValueError):
        Transform2D(x=math.nan)
    with pytest.raises(ValueError):
        Transform2D(rotation=math.inf)
    with pytest.raises(ValueError, match="zero"):
        Transform2D(scale_x=0)
    with pytest.raises(ValueError):
        BoneDefinition(id="a", length=-1)
    with pytest.raises(ValueError):
        BonePose(rotation=math.nan)


def test_parse_rotation_overrides() -> None:
    assert parse_rotation_overrides(["a=10", "b=-2.5"])["b"].rotation == -2.5
    for bad in ("a", "=3", "a=x", "a=nan"):
        with pytest.raises(RigError):
            parse_rotation_overrides([bad])
