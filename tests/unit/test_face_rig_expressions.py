from __future__ import annotations

import math

import pytest
import yaml

from studio.characters.manager import CharacterStore
from studio.core.assets import AssetManager
from studio.core.exceptions import FaceError, InvalidAssetError
from studio.core.project import Project, validate_project
from studio.core.schemas import AssetCategory
from studio.face.expressions import (
    ExpressionTransition,
    blend_expressions,
    blend_many,
    check_expression,
    ease_weight,
    evaluate_expression,
    evaluate_transition,
    neutral_state,
)
from studio.face.geometry import resolve_face
from studio.face.library import builtin_expression, builtin_expressions
from studio.face.manager import FaceStore
from studio.face.schemas import Ease, FacialChannel, FacialExpression, FacialRig
from studio.face.templates import build_face

CID = "chr_mira-vale"
BUILTINS = [
    "neutral",
    "happy",
    "sad",
    "angry",
    "surprised",
    "curious",
    "confused",
    "fearful",
    "disgusted",
    "excited",
    "tired",
    "worried",
]


@pytest.fixture
def faces(project: Project) -> FaceStore:
    CharacterStore(project).create("Mira Vale")
    store = FaceStore(project)
    store.create(CID)
    return store


@pytest.fixture
def rig(faces: FaceStore) -> FacialRig:
    return faces.load(CID).face


def expr(**values: float) -> FacialExpression:
    return FacialExpression(
        id="t", name="t", values={k.replace("__", "."): v for k, v in values.items()}
    )


# --- facial rig ----------------------------------------------------------------------------


def test_standard_face_structure(faces: FaceStore, rig: FacialRig) -> None:
    assert [c.id for c in rig.components] == [
        "eye_l",
        "eye_r",
        "brow_l",
        "brow_r",
        "mouth",
        "jaw",
        "cheek_l",
        "cheek_r",
        "nose",
    ]
    eye = rig.component("eye_l")
    assert {
        "offset_x",
        "offset_y",
        "scale",
        "rotation",
        "pupil_x",
        "pupil_y",
        "pupil_scale",
        "blink",
        "visible",
    } <= {c.name for c in eye.channels}
    assert {"raise", "rotation", "scale", "shape", "offset_x"} <= {
        c.name for c in rig.component("brow_l").channels
    }
    assert {
        "width",
        "height",
        "open",
        "corner_l",
        "corner_r",
        "upper_lip",
        "lower_lip",
        "offset_y",
    } <= {c.name for c in rig.component("mouth").channels}
    assert "open" in {c.name for c in rig.component("jaw").channels}
    assert rig.component("mouth").shapes and all(
        v is None for v in rig.component("mouth").shapes.values()
    )
    loaded = faces.load(CID)
    assert loaded.character.face == rig.id and loaded.character.version == 2
    report = faces.validate(CID)
    assert report.ok and "FAC012" in {i.code for i in report.warnings}


def test_minimal_template_and_duplicate_create(project: Project) -> None:
    CharacterStore(project).create("Bo")
    store = FaceStore(project)
    face = store.create("chr_bo", "minimal").face
    assert not {"cheek_l", "nose"} & {c.id for c in face.components}
    with pytest.raises(FaceError, match="already has"):
        store.create("chr_bo")
    with pytest.raises(FaceError, match="unknown face template"):
        build_face(CharacterStore(project).load("chr_bo").character, "alien")


def test_face_requires_head_part(project: Project) -> None:
    store = CharacterStore(project)
    c = store.create("Bo").character
    no_head = c.model_copy(update={"parts": [p for p in c.parts if p.id != "head"]})
    with pytest.raises(FaceError, match="no part 'head'"):
        build_face(no_head)


def _edit_face(faces: FaceStore, mutate) -> None:
    path = faces.characters.folder(CID) / "face.yaml"
    data = yaml.safe_load(path.read_text())
    mutate(data)
    path.write_text(yaml.safe_dump(data))


def test_face_validation_codes(faces: FaceStore) -> None:
    def mutate(d):
        comps = d["components"]
        comps.append(dict(comps[0]))  # duplicate component id
        comps[1]["channels"].append(dict(comps[1]["channels"][0]))  # duplicate control
        comps[2]["channels"][0].update({"min": 2, "max": 1})  # min > max
        comps[3]["channels"][0].update({"default": 5})  # default outside limits
        comps[4]["attachment"] = {"part": "tail"}  # missing part
        comps[5]["attachment"] = {"part": "head", "point": "nowhere"}  # invalid attachment
        d["anchor"]["part"] = "ghost"
        d["character_id"] = "chr_other"

    _edit_face(faces, mutate)
    codes = faces.validate(CID).codes()
    assert {"FAC002", "FAC003", "FAC004", "FAC005", "FAC006", "FAC007", "FAC008"} <= codes


def test_missing_face_file_and_bad_schema(faces: FaceStore) -> None:
    path = faces.characters.folder(CID) / "face.yaml"
    path.write_text("schema_version: 1\nid: face_mira_vale\nbogus: 1\n")
    assert "FAC001" in faces.validate(CID).codes()
    path.unlink()
    assert "FAC001" in faces.validate(CID).codes()


def test_required_controls_warning(faces: FaceStore) -> None:
    def mutate(d):
        d["components"][0]["channels"] = [
            c for c in d["components"][0]["channels"] if c["name"] != "blink"
        ]

    _edit_face(faces, mutate)
    assert "FAC009" in {i.code for i in faces.validate(CID).warnings}


def test_component_assets(faces: FaceStore, samples) -> None:
    am = AssetManager(faces.project)
    eye = am.register(samples["svg"], name="eye", category=AssetCategory.CHARACTER).record
    shape = am.register(samples["png"], name="mouth ai", category=AssetCategory.CHARACTER).record
    data = am.register(samples["json"], name="data", category=AssetCategory.DATA).record
    before = samples["svg"].read_bytes()
    face = faces.set_component_asset(CID, "eye_l", eye.id)
    assert face.version == 2 and face.component("eye_l").asset == eye.id
    face = faces.set_component_asset(CID, "mouth", shape.id, shape="ai")
    assert face.component("mouth").shapes["ai"] == shape.id and face.version == 3
    assert (faces.characters.folder(CID) / "history" / "face.v1.yaml").is_file()
    with pytest.raises(InvalidAssetError):
        faces.set_component_asset(CID, "eye_r", data.id)
    with pytest.raises(FaceError, match="no shape"):
        faces.set_component_asset(CID, "mouth", shape.id, shape="zz")
    with pytest.raises(FaceError, match="no component"):
        faces.set_component_asset(CID, "tail", eye.id)
    assert faces.validate(CID).ok
    (faces.project.root / eye.current.path).unlink()
    assert "FAC013" in faces.validate(CID).codes()
    assert samples["svg"].read_bytes() == before


def test_unregistered_face_asset_reported(faces: FaceStore) -> None:
    _edit_face(faces, lambda d: d["components"][0].update({"asset": "ast_aaaaaaaaaaaaaaaa"}))
    assert "FAC010" in faces.validate(CID).codes()


def test_project_validation_includes_face(faces: FaceStore, settings) -> None:
    _edit_face(faces, lambda d: d["components"][0].update({"asset": "ast_aaaaaaaaaaaaaaaa"}))
    report = validate_project(faces.project.root, settings)
    assert not report.ok and "FAC010" in report.codes()


def test_identity_unchanged_by_face(project: Project) -> None:
    from studio.characters.consistency import compare_characters

    chars = CharacterStore(project)
    v1 = chars.create("Mira Vale").character
    FaceStore(project).create(CID)
    current = chars.load(CID).character
    report = compare_characters(v1, current)
    assert report.consistent and report.differences == []


def test_reused_structure_does_not_copy_face(faces: FaceStore) -> None:
    twin = faces.characters.create("Nell", from_character=CID).character
    assert twin.face is None
    assert faces.characters.validate("chr_nell").ok


def test_channel_schema_rejects_bad_values() -> None:
    with pytest.raises(ValueError):
        FacialChannel(name="x", min=math.nan)
    with pytest.raises(ValueError):
        FacialChannel(name="Bad Name")
    with pytest.raises(ValueError):
        FacialExpression(id="x", name="x", values={"nodot": 1})


# --- controls -> geometry ------------------------------------------------------------------


def test_eye_controls(rig: FacialRig) -> None:
    base = resolve_face(rig, neutral_state(rig))["eye_l"]
    st = evaluate_expression(
        rig,
        expr(
            eye_l__blink=1,
            eye_l__pupil_x=1,
            eye_l__scale=1.5,
            eye_l__rotation=10,
            eye_l__offset_y=0.5,
        ),
    )
    eye = resolve_face(rig, st)["eye_l"]
    assert base.params["openness"] == 1 and eye.params["openness"] == 0
    assert eye.params["pupil_x"] > base.params["pupil_x"]
    assert eye.size[0] == pytest.approx(base.size[0] * 1.5)
    assert eye.rotation == 10 and eye.center.y > base.center.y
    assert eye.params["gaze_angle"] == 0 and eye.params["gaze_amount"] == 1
    hidden = resolve_face(rig, evaluate_expression(rig, expr(eye_r__visible=0)))["eye_r"]
    assert hidden.visible is False
    small = resolve_face(rig, evaluate_expression(rig, expr(eye_l__pupil_scale=0.5)))["eye_l"]
    assert small.params["pupil_radius"] == pytest.approx(base.params["pupil_radius"] * 0.5)


def test_brow_controls(rig: FacialRig) -> None:
    base = resolve_face(rig, neutral_state(rig))["brow_l"]
    up = resolve_face(
        rig,
        evaluate_expression(
            rig, expr(brow_l__raise=1, brow_l__shape=1, brow_l__rotation=-20, brow_l__scale=1.4)
        ),
    )["brow_l"]
    assert up.center.y < base.center.y  # raise moves up (negative y)
    assert up.params["arch"] > 0 and base.params["arch"] == 0
    assert up.rotation == -20 and up.params["length"] == pytest.approx(base.params["length"] * 1.4)


def test_mouth_and_jaw_controls(rig: FacialRig) -> None:
    base = resolve_face(rig, neutral_state(rig))
    st = evaluate_expression(
        rig,
        expr(
            mouth__open=1,
            mouth__width=1.5,
            mouth__corner_l=1,
            mouth__corner_r=-1,
            mouth__upper_lip=1,
            jaw__open=1,
        ),
    )
    res = resolve_face(rig, st)
    m, m0 = res["mouth"], base["mouth"]
    assert m0.params["gap"] == 0 and m.params["gap"] > 0
    assert m.params["width"] == pytest.approx(m0.params["width"] * 1.5)
    assert m.params["corner_l_y"] < 0 < m.params["corner_r_y"]  # left up, right down
    assert m.params["upper_lip_y"] < -m.params["gap"] / 2
    assert res["jaw"].params["drop"] > 0 and m.center.y > m0.center.y  # jaw drop lowers mouth
    shaped = evaluate_expression(rig, FacialExpression(id="s", name="s", shapes={"mouth": "o"}))
    assert resolve_face(rig, shaped)["mouth"].shape == "o"


# --- expressions ---------------------------------------------------------------------------


def test_all_builtins_valid_on_standard_rig(rig: FacialRig) -> None:
    assert [e.id for e in builtin_expressions()] == BUILTINS
    for e in builtin_expressions():
        st = evaluate_expression(rig, e)
        assert st.issues == [], (e.id, st.issues)
        for key, value in st.values.items():
            ch = rig.channel(key)
            assert ch.min <= value <= ch.max
    assert (
        evaluate_expression(rig, builtin_expression("neutral")).values == neutral_state(rig).values
    )


def test_builtins_on_minimal_rig_skip_missing_components(project: Project) -> None:
    CharacterStore(project).create("Bo")
    face = FaceStore(project).create("chr_bo", "minimal").face
    st = evaluate_expression(face, builtin_expression("happy"))
    assert {i.code for i in st.issues} == {"EXP002"}
    assert all(i.severity == "warning" for i in st.issues)
    assert "cheek_l.raise" not in st.values


def test_out_of_range_values_clamped_and_reported(rig: FacialRig) -> None:
    st = evaluate_expression(rig, expr(mouth__open=5, eye_l__rotation=-90))
    assert st.values["mouth.open"] == 1 and st.values["eye_l.rotation"] == -30
    assert {i.code for i in st.issues} == {"EXP003"}


def test_custom_expression_strictness(rig: FacialRig) -> None:
    bad = FacialExpression(
        id="x",
        name="x",
        values={"tail.wag": 1, "mouth.smirk": 1},
        shapes={"mouth": "zz"},
        rig="face_other_rig",
    )
    codes = {(i.code, i.severity) for i in check_expression(rig, bad)}
    assert {("EXP002", "error"), ("EXP004", "error"), ("EXP007", "error")} <= codes


def test_create_and_edit_custom_expression(faces: FaceStore) -> None:
    e = faces.create_expression(
        CID,
        "smug",
        "Smug",
        base="happy",
        values={"mouth.corner_r": -0.2, "eye_l.blink": 0.3},
        shapes={"mouth": "e"},
    )
    assert e.rig == "face_mira_vale" and e.values["mouth.corner_l"] == 0.8
    assert e.values["mouth.corner_r"] == -0.2 and e.version == 1
    assert "smug" in [x.id for x in faces.list_expressions(CID)]
    e2 = faces.update_expression(CID, "smug", {"eye_l.blink": 0.5})
    assert e2.version == 2 and e2.values["eye_l.blink"] == 0.5
    hist = faces.characters.folder(CID) / "history" / "expressions" / "smug.v1.yaml"
    assert hist.is_file()
    assert faces.update_expression(CID, "smug", {"eye_l.blink": 0.5}).version == 2  # no-op
    with pytest.raises(FaceError, match="already exists"):
        faces.create_expression(CID, "smug", "Again")
    with pytest.raises(FaceError, match="built-in"):
        faces.create_expression(CID, "happy", "Mine")
    with pytest.raises(FaceError, match="not compatible"):
        faces.create_expression(CID, "weird", "Weird", values={"tail.wag": 1})
    with pytest.raises(FaceError, match="read-only"):
        faces.update_expression(CID, "sad", {"mouth.open": 1})
    with pytest.raises(FaceError, match="unknown expression"):
        faces.get_expression(CID, "nope")
    assert faces.validate(CID).ok


def test_invalid_custom_expression_file_reported(faces: FaceStore) -> None:
    folder = faces.characters.folder(CID) / "expressions"
    folder.mkdir(exist_ok=True)
    (folder / "broken.yaml").write_text("schema_version: 1\nid: broken\n")
    (folder / "renamed.yaml").write_text(
        "schema_version: 1\nid: other\nname: x\nvalues: {tail.wag: 1}\n"
    )
    (folder / "happy.yaml").write_text("schema_version: 1\nid: happy\nname: x\n")
    codes = faces.validate(CID).codes()
    assert {"EXP001", "EXP008", "EXP002", "EXP005"} <= codes


# --- blending ------------------------------------------------------------------------------


def test_blend_endpoints_midpoint_and_determinism(rig: FacialRig) -> None:
    n, h = builtin_expression("neutral"), builtin_expression("happy")
    assert blend_expressions(rig, n, h, 0).values == evaluate_expression(rig, n).values
    assert blend_expressions(rig, n, h, 1).values == evaluate_expression(rig, h).values
    mid = blend_expressions(rig, n, h, 0.5)
    assert mid.values["mouth.corner_l"] == pytest.approx(0.4)
    assert mid.values["mouth.width"] == pytest.approx(1.075)
    assert mid.values == blend_expressions(rig, n, h, 0.5).values


def test_blend_preserves_limits_and_is_monotonic(rig: FacialRig) -> None:
    a, b = builtin_expression("angry"), builtin_expression("surprised")
    prev = None
    for i in range(11):
        st = blend_expressions(rig, a, b, i / 10, Ease.SMOOTHSTEP)
        for key, value in st.values.items():
            ch = rig.channel(key)
            assert ch.min - 1e-12 <= value <= ch.max + 1e-12
        if prev is not None:
            assert st.values["brow_l.raise"] >= prev - 1e-12  # -0.5 -> 0.9, no jumps backwards
        prev = st.values["brow_l.raise"]


def test_blend_weights_validation(rig: FacialRig) -> None:
    n, h = builtin_expression("neutral"), builtin_expression("happy")
    over = blend_expressions(rig, n, h, 1.7)
    assert over.values == evaluate_expression(rig, h).values
    assert any(i.code == "BLD002" for i in over.issues)
    under = blend_expressions(rig, n, h, -3)
    assert under.values == evaluate_expression(rig, n).values
    for bad in (math.nan, math.inf, "0.5", True):
        with pytest.raises(FaceError):
            blend_expressions(rig, n, h, bad)  # type: ignore[arg-type]


def test_ease_and_shapes_switch_at_half(rig: FacialRig) -> None:
    assert ease_weight(0.5, Ease.SMOOTHSTEP) == 0.5
    assert ease_weight(0.25, Ease.SMOOTHSTEP) == pytest.approx(0.15625)
    a = FacialExpression(id="a", name="a", shapes={"mouth": "rest"})
    b = FacialExpression(id="b", name="b", shapes={"mouth": "o"})
    assert blend_expressions(rig, a, b, 0.49).shapes["mouth"] == "rest"
    assert blend_expressions(rig, a, b, 0.5).shapes["mouth"] == "o"


def test_blend_many_normalizes(rig: FacialRig) -> None:
    n, h, s = (builtin_expression(x) for x in ("neutral", "happy", "sad"))
    mix = blend_many(rig, [(h, 2), (s, 2)])
    assert mix.values["mouth.corner_l"] == pytest.approx((0.8 - 0.7) / 2)
    same = blend_many(rig, [(h, 0.5), (s, 0.5)])
    assert mix.values == same.values
    assert blend_many(rig, [(n, 0), (h, 3)]).values == evaluate_expression(rig, h).values
    for items in ([], [(h, -1)], [(h, 0)], [(h, math.nan)]):
        with pytest.raises(FaceError):
            blend_many(rig, items)


def test_transition_interface(rig: FacialRig) -> None:
    n, h = builtin_expression("neutral"), builtin_expression("happy")
    tr = ExpressionTransition(n, h, start=1.0, duration=0.5, ease=Ease.LINEAR)
    assert tr.weight_at(0.0) == 0 and tr.weight_at(1.25) == 0.5 and tr.weight_at(9) == 1
    assert evaluate_transition(rig, tr, 1.25).values["mouth.corner_l"] == pytest.approx(0.4)
    assert ExpressionTransition(n, h, 1.0, 0.0).weight_at(1.0) == 1
    with pytest.raises(FaceError):
        ExpressionTransition(n, h, 1.0, -1).weight_at(1.5)
    with pytest.raises(FaceError):
        tr.weight_at(math.nan)
