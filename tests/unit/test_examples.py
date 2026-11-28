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


def test_example_face_alignment_and_lipsync_are_valid() -> None:
    from studio.face.alignment import phoneme_events
    from studio.face.expressions import evaluate_expression
    from studio.face.library import builtin_expressions, load_phoneme_map, load_viseme_set
    from studio.face.lipsync import LipSyncEvaluator
    from studio.face.phonemes import map_phonemes
    from studio.face.schemas import AlignmentDocument, FacialRig, LipSyncTrack
    from studio.face.validation import validate_face

    char = load_model(CharacterDefinition, EXAMPLE / "character.yaml")
    face = load_model(FacialRig, EXAMPLE / "face.yaml")
    assert char.face == face.id
    report = ValidationReport("example face")
    validate_face(face, char, report, "face.yaml")
    assert report.ok, [str(i) for i in report.errors]
    for expr in builtin_expressions():
        assert evaluate_expression(face, expr).issues == []
    doc = load_model(AlignmentDocument, EXAMPLE / "hello.alignment.json")
    track = load_model(LipSyncTrack, EXAMPLE / "hello.lipsync.yaml")
    mapped = map_phonemes(phoneme_events(doc), load_phoneme_map(), load_viseme_set())
    assert [e.viseme for e in mapped.events] == [e.viseme for e in track.events]
    state = LipSyncEvaluator(track, load_viseme_set(), face).evaluate(0.5)
    assert state.viseme == "o"
    for svg in ("face-expressions.svg", "face-lipsync-hello.svg"):
        title = ET.fromstring((EXAMPLE / svg).read_text()).find("{http://www.w3.org/2000/svg}title")
        assert title is not None and "DIAGNOSTIC" in title.text


def test_example_animations_evaluate() -> None:
    from studio.animation.evaluator import AnimationContext, CharacterAnimator
    from studio.animation.mesh import check_mesh
    from studio.animation.schemas import AnimationClip, AnimationSet, DeformMesh
    from studio.animation.validation import check_clip_references
    from studio.face.library import builtin_expression, load_viseme_set
    from studio.face.schemas import FacialRig, LipSyncTrack

    char = load_model(CharacterDefinition, EXAMPLE / "character.yaml")
    rig = load_model(RigDefinition, EXAMPLE / "rig.yaml")
    face = load_model(FacialRig, EXAMPLE / "face.yaml")
    anim = EXAMPLE / "animations"
    clips = {p.stem: load_model(AnimationClip, p) for p in sorted((anim / "clips").glob("*.yaml"))}
    meshes = {p.stem: load_model(DeformMesh, p) for p in sorted((anim / "meshes").glob("*.yaml"))}
    assert set(clips) == {"greet", "idle", "run", "walk", "wave"}
    for clip in clips.values():
        issues = check_clip_references(clip, char, rig, face, None, set(meshes))
        assert [i for i in issues if i[1] == "error"] == [], clip.id
    for mesh in meshes.values():
        assert [i for i in check_mesh(mesh, char, rig) if i[1] == "error"] == []
    aset = load_model(AnimationSet, anim / "sets" / "performance.yaml")
    ctx = AnimationContext(
        character=char,
        rig=rig,
        clips=clips,
        face=face,
        expressions=builtin_expression,
        meshes=meshes,
        lipsync=load_model(LipSyncTrack, EXAMPLE / "hello.lipsync.yaml"),
        visemes=load_viseme_set(),
    )
    animator = CharacterAnimator(ctx, aset)
    for t in (0.0, 0.3, 0.77, 1.5):
        state = animator.evaluate(t)
        assert all(ik["status"] == "reached" and ik["error"] < 1e-6 for ik in state.ik)
        assert [d for d in state.diagnostics if d.severity == "warning"] == []
    assert animator.evaluate(0.3).lips is not None
    for svg in ("anim-walk.svg", "anim-run.svg", "anim-performance.svg"):
        title = ET.fromstring((EXAMPLE / svg).read_text()).find("{http://www.w3.org/2000/svg}title")
        assert title is not None and "not animation" in title.text
