from __future__ import annotations

from studio.core.validation import ValidationReport
from studio.rig.schemas import (
    BendDirection,
    BoneDefinition,
    ControlHandle,
    IKChain,
    JointConstraint,
    RigDefinition,
    Transform2D,
)
from studio.rig.validation import validate_rig


def b(bid, parent, length=10.0, x=0.0, rot=0.0, **kw) -> BoneDefinition:
    return BoneDefinition(
        id=bid, parent=parent, length=length, rest=Transform2D(x=x, rotation=rot), **kw
    )


def check(bones, root="a", chains=(), controls=()) -> ValidationReport:
    rig = RigDefinition(
        id="rig_tt",
        character_id="chr_tt",
        root=root,
        bones=list(bones),
        ik_chains=list(chains),
        controls=list(controls),
    )
    report = ValidationReport("rig")
    validate_rig(rig, report)
    return report


def test_valid_rig() -> None:
    report = check(
        [b("a", None), b("b", "a", x=10), b("c", "b", x=10)],
        chains=[IKChain(id="ik", upper="b", lower="c")],
    )
    assert report.ok and report.warnings == []


def test_structural_codes() -> None:
    assert "RIG001" in check([b("a", None), b("a", None)]).codes()
    assert "RIG002" in check([b("a", None)], root="zzz").codes()
    assert "RIG002" in check([]).codes()
    assert "RIG003" in check([b("a", "b"), b("b", None)]).codes()
    assert "RIG004" in check([b("a", None), b("b", "ghost")]).codes()
    codes = check([b("a", None), b("b", "c"), b("c", "b")]).codes()
    assert "RIG005" in codes
    assert "RIG005" in check([b("a", None), b("s", "s")]).codes()


def test_lengths_and_constraints() -> None:
    assert "RIG007" in check([b("a", None), b("z", "a", length=0)]).codes()
    assert check([b("a", None), b("z", "a", length=0, control=True)]).ok
    assert (
        "RIG008"
        in check(
            [b("a", None, constraint=JointConstraint(min_rotation=5, max_rotation=-5))]
        ).codes()
    )
    assert (
        "RIG009"
        in check(
            [b("a", None, rot=90, constraint=JointConstraint(min_rotation=0, max_rotation=45))]
        ).codes()
    )
    assert "RIG010" in {
        i.code
        for i in check(
            [b("a", None, constraint=JointConstraint(locked=True, min_rotation=0, max_rotation=10))]
        ).warnings
    }
    assert "RIG011" in {
        i.code
        for i in check(
            [b("a", None, constraint=JointConstraint(min_rotation=-300, max_rotation=300))]
        ).warnings
    }
    assert (
        "RIG012"
        in check(
            [
                b(
                    "a",
                    None,
                    constraint=JointConstraint(
                        min_rotation=-90, max_rotation=-10, preferred_bend=BendDirection.POSITIVE
                    ),
                )
            ]
        ).codes()
    )


def test_controls() -> None:
    report = check(
        [b("a", None)],
        controls=[
            ControlHandle(id="t", kind="ik_target", bone="ghost"),
            ControlHandle(id="t", kind="pole"),
        ],
    )
    assert "RIG013" in report.codes()


def test_ik_chain_codes() -> None:
    base = [b("a", None), b("u", "a", x=10), b("l", "u", x=10), b("x", "a", x=5)]
    assert "IK001" in check(base, chains=[IKChain(id="c", upper="u", lower="nope")]).codes()
    assert "IK002" in check(base, chains=[IKChain(id="c", upper="u", lower="x")]).codes()
    off_tip = [b("a", None), b("u", "a"), b("l", "u", x=3)]
    assert "IK003" in {
        i.code for i in check(off_tip, chains=[IKChain(id="c", upper="u", lower="l")]).warnings
    }
    zero = [b("a", None), b("u", "a", length=0, control=True), b("l", "u", x=0)]
    assert "IK004" in check(zero, chains=[IKChain(id="c", upper="u", lower="l")]).codes()
    dup = check(
        base, chains=[IKChain(id="c", upper="u", lower="l"), IKChain(id="c", upper="u", lower="l")]
    )
    assert "IK005" in dup.codes()


def test_contradictory_bend_and_limits() -> None:
    bones = [
        b("a", None),
        b("u", "a"),
        b(
            "l",
            "u",
            x=10,
            constraint=JointConstraint(
                min_rotation=-150, max_rotation=0, preferred_bend=BendDirection.NEGATIVE
            ),
        ),
    ]
    report = check(
        bones, chains=[IKChain(id="c", upper="u", lower="l", bend=BendDirection.POSITIVE)]
    )
    assert "IK006" in report.codes()
    assert check(
        bones, chains=[IKChain(id="c", upper="u", lower="l", bend=BendDirection.NEGATIVE)]
    ).ok


def test_locked_joint_and_scale_warnings() -> None:
    bones = [
        b("a", None),
        b("u", "a", constraint=JointConstraint(locked=True)),
        BoneDefinition(id="l", parent="u", length=10, rest=Transform2D(x=10, scale_x=2)),
    ]
    warnings = {
        i.code for i in check(bones, chains=[IKChain(id="c", upper="u", lower="l")]).warnings
    }
    assert {"IK007", "IK008"} <= warnings


def test_missing_controls_referenced_by_chain() -> None:
    bones = [b("a", None), b("u", "a"), b("l", "u", x=10)]
    report = check(bones, chains=[IKChain(id="c", upper="u", lower="l", target_control="hand_t")])
    assert "IK009" in report.codes()


def test_validation_does_not_modify_rig() -> None:
    rig = RigDefinition(
        id="rig_tt", character_id="chr_tt", root="a", bones=[b("a", None), b("a", None)]
    )
    before = rig.model_dump()
    validate_rig(rig, ValidationReport("r"))
    assert rig.model_dump() == before
