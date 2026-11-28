from __future__ import annotations

import pytest
import yaml

from studio.characters.manager import CharacterStore, character_id_for
from studio.characters.parts import draw_order, part_order, solve_parts
from studio.characters.schemas import CharacterDefinition, PartDefinition, PartKind
from studio.characters.templates import TEMPLATES, get_template
from studio.core.assets import AssetManager
from studio.core.exceptions import (
    AssetNotFoundError,
    CharacterError,
    CharacterExistsError,
    InvalidAssetError,
)
from studio.core.project import Project, validate_project
from studio.core.schemas import AssetCategory, TurnaroundView
from studio.rig.fk import BonePose, solve_fk
from studio.rig.math2d import Vec2

SPEC_PARTS = {
    "head",
    "neck",
    "ear_l",
    "ear_r",
    "hair",
    "upper_torso",
    "pelvis",
    "chest",
    "waist",
    "upper_arm_l",
    "forearm_l",
    "hand_l",
    "upper_arm_r",
    "forearm_r",
    "hand_r",
    "thigh_l",
    "lower_leg_l",
    "foot_l",
    "thigh_r",
    "lower_leg_r",
    "foot_r",
}


@pytest.fixture
def store(project: Project) -> CharacterStore:
    return CharacterStore(project)


@pytest.fixture
def mira(store: CharacterStore):
    return store.create("Mira Vale", description="An original test character")


def char_file(store: CharacterStore, cid: str):
    return store.folder(cid) / "character.yaml"


# --- creation ------------------------------------------------------------------------------


def test_create_from_biped_template(store: CharacterStore, mira) -> None:
    c, rig = mira.character, mira.rig
    assert c.id == "chr_mira-vale" and c.version == 1 and c.project_id == store.project.id
    assert {p.id for p in c.parts} == SPEC_PARTS
    assert rig is not None and rig.id == "rig_mira_vale" and rig.character_id == c.id
    assert {ch.id for ch in rig.ik_chains} == {"arm_l", "arm_r", "leg_l", "leg_r"}
    assert [v.view for v in c.turnaround.views] == list(TurnaroundView)
    assert all(p.asset is None for p in c.parts)  # no artwork invented
    assert c.identity.original_design is True
    report = store.validate(c.id)
    assert report.ok, [str(i) for i in report.errors]
    assert {i.code for i in report.warnings} == {"TRN003", "PRT018"}


def test_template_geometry_matches_proportions(mira) -> None:
    fk = solve_fk(mira.rig)
    assert fk["head"].tip.rounded(6) == (0.0, 0.0)  # top of the head at y = 0
    assert fk["foot_l"].tip.y == pytest.approx(1000)  # soles at the height
    head_len = mira.rig.bone_map()["head"].length
    assert head_len == pytest.approx(1000 / 5)


def test_minimal_template_uses_fewer_parts(store: CharacterStore) -> None:
    c = store.create("Bo", character_id="chr_bo", template="biped-minimal").character
    ids = {p.id for p in c.parts}
    assert not ids & {"ear_l", "ear_r", "hair", "chest", "waist"}
    assert store.validate("chr_bo").ok


def test_multiple_characters_and_duplicates(store: CharacterStore, mira) -> None:
    store.create("Tomas", height_heads=6.5, height_units=1300)
    assert store.ids() == ["chr_mira-vale", "chr_tomas"]
    with pytest.raises(CharacterExistsError):
        store.create("Mira Vale")
    with pytest.raises(CharacterError, match="invalid character id"):
        store.create("x", character_id="../escape")
    with pytest.raises(CharacterError, match="derive"):
        character_id_for("!")


def test_impossible_proportions(store: CharacterStore) -> None:
    from studio.characters.schemas import IdentityProfile
    from studio.core.schemas import CharacterProportions

    ident = IdentityProfile(proportions=CharacterProportions(height_heads=3, leg_length_heads=2.5))
    with pytest.raises(CharacterError, match="no room"):
        get_template("biped").build("chr_x1", ident)
    with pytest.raises(CharacterError, match="unknown template"):
        get_template("quadruped")
    assert set(TEMPLATES) == {"biped", "biped-minimal"}


def test_reuse_structure_from_existing(store: CharacterStore, mira, samples) -> None:
    asset = (
        AssetManager(store.project)
        .register(samples["svg"], name="Mira head", category=AssetCategory.CHARACTER)
        .record
    )
    store.set_part_asset(mira.character.id, "head", asset.id)
    twin = store.create("Nell", from_character=mira.character.id)
    assert {p.id for p in twin.character.parts} == SPEC_PARTS
    assert all(p.asset is None for p in twin.character.parts)  # artwork is not copied
    assert twin.rig is not None and twin.rig.character_id == "chr_nell"
    assert twin.character.template == "from:chr_mira-vale"
    assert store.validate("chr_nell").ok


def test_invalid_definition_rejected() -> None:
    with pytest.raises(ValueError):
        CharacterDefinition.model_validate({"id": "mira"})
    with pytest.raises(ValueError, match="original"):
        from studio.characters.schemas import IdentityProfile
        from studio.core.schemas import CharacterProportions

        IdentityProfile(proportions=CharacterProportions(height_heads=5), original_design=False)


def test_invalid_file_reported(store: CharacterStore, mira) -> None:
    path = char_file(store, mira.character.id)
    data = yaml.safe_load(path.read_text())
    data["unexpected"] = 1
    path.write_text(yaml.safe_dump(data))
    report = store.validate(mira.character.id)
    assert "CHR001" in report.codes()
    with pytest.raises(Exception, match="unknown field"):
        store.load(mira.character.id)


# --- versioning ------------------------------------------------------------------------------


def test_versioning_and_history(store: CharacterStore, mira) -> None:
    c = mira.character
    edited = c.model_copy(update={"description": "Changed"})
    saved = store.save(edited)
    assert saved.version == 2
    history = store.folder(c.id) / "history" / "character.v1.yaml"
    assert history.is_file()
    assert store.load_version(c.id, 1).description == "An original test character"
    # unchanged content does not bump the version
    assert store.save(saved).version == 2
    # editing a stale copy is refused instead of overwriting newer work
    with pytest.raises(CharacterError, match="edited elsewhere"):
        store.save(c.model_copy(update={"description": "stale"}))
    with pytest.raises(CharacterError, match="no saved version"):
        store.load_version(c.id, 7)
    assert store.validate(c.id).ok


# --- assets ------------------------------------------------------------------------------------


def test_assign_part_and_view_artwork(store: CharacterStore, mira, samples) -> None:
    manager = AssetManager(store.project)
    head = manager.register(
        samples["svg"], name="Mira head", category=AssetCategory.CHARACTER
    ).record
    side = manager.register(
        samples["png"], name="Mira side", category=AssetCategory.CHARACTER
    ).record
    original = samples["svg"].read_bytes()
    c = store.set_part_asset(mira.character.id, "head", head.id)
    assert c.part_map()["head"].asset == head.id and c.version == 2
    c = store.set_part_asset(mira.character.id, "head", side.id, TurnaroundView.SIDE)
    c = store.set_view_artwork(mira.character.id, TurnaroundView.SIDE, side.id)
    assert c.turnaround.get(TurnaroundView.SIDE).artwork == side.id
    assert c.version == 4
    assert samples["svg"].read_bytes() == original
    assert store.validate(mira.character.id).ok


def test_asset_errors(store: CharacterStore, mira, samples, settings) -> None:
    manager = AssetManager(store.project)
    data = manager.register(samples["json"], name="rig data", category=AssetCategory.DATA).record
    with pytest.raises(InvalidAssetError, match="JSON"):
        store.set_part_asset(mira.character.id, "head", data.id)
    with pytest.raises(AssetNotFoundError):
        store.set_part_asset(mira.character.id, "head", "ast_0000000000000000")
    with pytest.raises(CharacterError, match="no part"):
        store.set_part_asset(mira.character.id, "tail", data.id)
    # a hand-edited file referencing an unregistered asset is reported
    path = char_file(store, mira.character.id)
    text = path.read_text().replace("asset: null", "asset: ast_aaaaaaaaaaaaaaaa", 1)
    path.write_text(text)
    report = validate_project(store.project.root, settings)
    assert "PRT006" in report.codes()


def test_missing_artwork_file_and_wrong_owner(store: CharacterStore, mira, samples) -> None:
    manager = AssetManager(store.project)
    rec = manager.register(
        samples["svg"], name="head", category=AssetCategory.CHARACTER, tags=["chr_someone-else"]
    ).record
    store.set_part_asset(mira.character.id, "head", rec.id)
    (store.project.root / rec.current.path).unlink()
    codes = store.validate(mira.character.id).codes()
    assert {"PRT008", "PRT011"} <= codes


# --- parts ---------------------------------------------------------------------------------------


def _part(pid, parent=None, z=0, **kw) -> PartDefinition:
    return PartDefinition(id=pid, parent=parent, z_order=z, **kw)


def _with_parts(c: CharacterDefinition, parts) -> CharacterDefinition:
    return c.model_copy(update={"parts": parts, "rig": None})


def test_part_hierarchy_transform_propagation(mira) -> None:
    from studio.rig.schemas import Transform2D

    c = _with_parts(
        mira.character,
        [
            _part("body", transform=Transform2D(x=100, y=50, rotation=90), z=1),
            _part("arm", "body", transform=Transform2D(x=10), z=2),
            _part("hand", "arm", transform=Transform2D(x=5, rotation=-90), z=3),
        ],
    )
    parts = solve_parts(c)
    assert parts["arm"].pivot_world.rounded(6) == (100.0, 60.0)
    assert parts["hand"].pivot_world.rounded(6) == (100.0, 65.0)
    assert parts["hand"].frame.rotation_degrees == pytest.approx(0)
    moved = _with_parts(
        c, [c.parts[0].model_copy(update={"transform": Transform2D(x=0, y=0)}), *c.parts[1:]]
    )
    assert solve_parts(moved)["hand"].pivot_world.rounded(6) == (15.0, 0.0)


def test_parts_follow_bones(mira) -> None:
    fk = solve_fk(mira.rig, {"upper_arm_l": BonePose(rotation=90)})
    parts = solve_parts(mira.character, fk)
    assert parts["hand_l"].pivot_world.distance_to(fk["hand_l"].head) < 1e-9
    # ears attach to the head's attachment points, so bending the neck moves them
    rest = solve_parts(mira.character, solve_fk(mira.rig))
    bent = solve_parts(mira.character, solve_fk(mira.rig, {"neck": BonePose(rotation=30)}))
    assert bent["ear_l"].pivot_world.distance_to(rest["ear_l"].pivot_world) > 1.0
    # ...and they stay on the head: distance to the head pivot is unchanged
    d_rest = rest["ear_l"].pivot_world.distance_to(rest["head"].pivot_world)
    d_bent = bent["ear_l"].pivot_world.distance_to(bent["head"].pivot_world)
    assert d_bent == pytest.approx(d_rest)


def test_pivot_and_artwork_matrix(mira) -> None:
    from studio.rig.schemas import Point2D, Transform2D

    c = _with_parts(
        mira.character, [_part("p", transform=Transform2D(x=50, y=50), pivot=Point2D(x=10, y=20))]
    )
    pw = solve_parts(c)["p"]
    assert pw.artwork.apply(Vec2(10, 20)).rounded() == (50.0, 50.0)  # pivot lands on the transform
    assert pw.artwork.apply(Vec2(0, 0)).rounded() == (40.0, 30.0)


def test_visibility_opacity_inherit(mira) -> None:
    c = _with_parts(
        mira.character,
        [
            _part("a", z=1, opacity=0.5),
            _part("b", "a", z=2, opacity=0.5),
            _part("c", "b", z=3, visible=True),
            _part("d", z=4, visible=False),
        ],
    )
    view = c.turnaround.views[0].model_copy(update={"hidden_parts": ["b"], "z_order": {}})
    parts = solve_parts(c)
    assert parts["b"].opacity == pytest.approx(0.25)
    assert draw_order(parts) == ["a", "b", "c"]
    hidden = solve_parts(c, None, view)
    assert draw_order(hidden) == ["a"]  # hiding b hides its child c
    assert draw_order(hidden, include_hidden=True) == ["a", "b", "c", "d"]


def test_draw_order_view_override_and_ties(mira) -> None:
    c = _with_parts(mira.character, [_part("x", z=5), _part("y", z=1), _part("z", z=3)])
    assert draw_order(solve_parts(c)) == ["y", "z", "x"]
    view = c.turnaround.views[0].model_copy(update={"z_order": {"x": 0}})
    assert draw_order(solve_parts(c, None, view)) == ["x", "y", "z"]
    tie = _with_parts(c, [_part("b", z=1), _part("a", z=1)])
    assert draw_order(solve_parts(tie)) == ["a", "b"]  # deterministic tie-break by ID


def test_bad_hierarchies(mira) -> None:
    with pytest.raises(CharacterError, match="unknown parent"):
        part_order(_with_parts(mira.character, [_part("a", "ghost")]))
    with pytest.raises(CharacterError, match="circular"):
        part_order(_with_parts(mira.character, [_part("a", "b"), _part("b", "a", z=1)]))
    with pytest.raises(CharacterError, match="duplicate"):
        part_order(_with_parts(mira.character, [_part("a"), _part("a", z=1)]))


def test_part_validation_codes(store: CharacterStore, mira) -> None:
    path = char_file(store, mira.character.id)
    data = yaml.safe_load(path.read_text())
    parts = {p["id"]: p for p in data["parts"]}
    parts["hand_l"]["z_order"] = parts["hand_r"]["z_order"]  # duplicate draw order
    parts["hair"]["parent"] = "ghost"  # missing parent
    parts["ear_l"]["parent_attachment"] = "nowhere"  # unknown attachment
    parts["foot_l"]["bone"] = "tail"  # unknown bone
    data["parts"].append({**parts["neck"], "id": "neck"})  # duplicate id
    data["parts"].append({"id": "loop_a", "parent": "loop_b", "z_order": 900})
    data["parts"].append({"id": "loop_b", "parent": "loop_a", "z_order": 901})
    path.write_text(yaml.safe_dump(data))
    codes = store.validate(mira.character.id).codes()
    assert {"PRT001", "PRT002", "PRT003", "PRT004", "PRT005", "PRT009"} <= codes


def test_rig_problems_reported_through_character(store: CharacterStore, mira) -> None:
    rig_path = store.folder(mira.character.id) / "rig.yaml"
    data = yaml.safe_load(rig_path.read_text())
    data["bones"][3]["length"] = 0  # head bone
    data["character_id"] = "chr_other"
    rig_path.write_text(yaml.safe_dump(data))
    codes = store.validate(mira.character.id).codes()
    assert {"RIG007", "CHR005"} <= codes
    rig_path.unlink()
    assert "CHR004" in store.validate(mira.character.id).codes()


def test_part_kind_enum_covers_spec() -> None:
    required = {
        "head",
        "neck",
        "ear",
        "hair",
        "head_accessory",
        "chest",
        "upper_torso",
        "waist",
        "pelvis",
        "upper_arm",
        "forearm",
        "hand",
        "thigh",
        "lower_leg",
        "foot",
        "custom",
    }
    assert required <= {k.value for k in PartKind}
