"""The documented example character and rig (docs/examples) must stay valid."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from studio.characters.parts import draw_order, solve_parts
from studio.characters.schemas import CharacterDefinition
from studio.characters.validation import validate_parts, validate_turnaround
from studio.core.validation import ValidationReport, load_model
from studio.rig.fk import solve_fk
from studio.rig.ik import solve_ik_chain
from studio.rig.math2d import Vec2
from studio.rig.schemas import RigDefinition
from studio.rig.validation import validate_rig
from tests.conftest import REPO_ROOT

EXAMPLE = REPO_ROOT / "docs" / "examples" / "chr_mira-vale"


def test_example_character_and_rig_are_valid() -> None:
    char = load_model(CharacterDefinition, EXAMPLE / "character.yaml")
    rig = load_model(RigDefinition, EXAMPLE / "rig.yaml")
    assert char.rig == rig.id and rig.character_id == char.id
    report = ValidationReport("example")
    validate_rig(rig, report)
    validate_parts(char, rig, report, "example")
    validate_turnaround(char, report, "example")
    assert report.ok, [str(i) for i in report.errors]
    parts = solve_parts(char, solve_fk(rig))
    assert len(draw_order(parts)) == len(char.parts)
    ik = solve_ik_chain(rig, "arm_l", Vec2(150, 400))
    assert ik.solution.reached and ik.error < 1e-6


def test_example_diagnostic_is_labelled() -> None:
    root = ET.fromstring((EXAMPLE / "diagnostic-side.svg").read_text())
    title = root.find("{http://www.w3.org/2000/svg}title")
    assert title is not None and "not artwork, not animation" in title.text
