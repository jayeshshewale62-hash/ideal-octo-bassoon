from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
import yaml

from studio.characters.consistency import (
    IdentityRole,
    compare_characters,
    identity_properties,
    role_of,
    view_differences,
)
from studio.characters.manager import CharacterStore
from studio.characters.preview import render_diagnostic_svg
from studio.characters.schemas import TurnaroundSet, ViewDefinition
from studio.characters.validation import validate_turnaround
from studio.core.assets import AssetManager
from studio.core.project import Project
from studio.core.schemas import AssetCategory, TurnaroundView
from studio.core.validation import ValidationReport
from studio.rig.fk import solve_fk
from studio.rig.ik import solve_ik_chain
from studio.rig.math2d import Vec2

V = TurnaroundView


@pytest.fixture
def store(project: Project) -> CharacterStore:
    return CharacterStore(project)


@pytest.fixture
def char(store: CharacterStore):
    c = store.create("Mira Vale").character
    ident = c.identity.model_copy(
        update={
            "palette": {"skin": "#C68E6B", "coat": "#2F5D8A"},
            "clothing": ["blue coat", "boots"],
            "hair": "short black bob",
            "distinctive_features": ["scar over left eyebrow"],
        }
    )
    return store.save(c.model_copy(update={"identity": ident}))


def turnaround_report(c) -> ValidationReport:
    report = ValidationReport("t")
    validate_turnaround(c, report, "loc")
    return report


def with_views(c, views, required=None):
    ta = TurnaroundSet(views=views, required_views=required or list(V))
    return c.model_copy(update={"turnaround": ta})


def test_all_five_views_valid(char) -> None:
    report = turnaround_report(char)
    assert report.ok
    assert [v.value for v in V] == ["front", "three_quarter", "side", "three_quarter_back", "back"]


def test_missing_and_duplicate_views(char) -> None:
    missing = with_views(char, [ViewDefinition(view=V.FRONT), ViewDefinition(view=V.SIDE)])
    codes = [i.code for i in turnaround_report(missing).errors]
    assert codes.count("TRN002") == 3
    dup = with_views(char, [ViewDefinition(view=V.FRONT), ViewDefinition(view=V.FRONT)], [V.FRONT])
    assert "TRN001" in turnaround_report(dup).codes()
    no_front = with_views(char, [ViewDefinition(view=V.SIDE)], [V.SIDE])
    assert "TRN011" in turnaround_report(no_front).codes()
    dup_req = with_views(char, [ViewDefinition(view=V.FRONT)], [V.FRONT, V.FRONT])
    assert "TRN010" in turnaround_report(dup_req).codes()


def test_view_specific_override_allowed(char) -> None:
    side = ViewDefinition(view=V.SIDE, identity_overrides={"head.width_ratio": 1.2})
    report = turnaround_report(
        with_views(char, [ViewDefinition(view=V.FRONT), side], [V.FRONT, V.SIDE])
    )
    assert report.ok and not {"TRN005", "TRN006", "TRN007"} & report.codes()


def test_required_identity_cannot_change_per_view(char) -> None:
    front = ViewDefinition(view=V.FRONT)
    bad = ViewDefinition(
        view=V.SIDE,
        identity_overrides={
            "palette.coat": "#FF0000",
            "proportions.height_heads": 7,
            "hair": "long blonde",
            "personality": ["grumpy"],
            "eye_count": 3,
            "head.width_ratio": "wide",
        },
    )
    report = turnaround_report(with_views(char, [front, bad], [V.FRONT, V.SIDE]))
    messages = [i.message for i in report.errors if i.code == "TRN005"]
    assert len(messages) == 3 and any("palette.coat" in m for m in messages)
    assert "TRN006" in {i.code for i in report.warnings}  # optional property changed
    assert "TRN007" in report.codes()  # unknown property
    assert "TRN009" in report.codes()  # wrong type


def test_tolerance_on_numeric_identity(char) -> None:
    tol = char.identity.proportions.tolerance
    within = {"proportions.height_heads": char.identity.proportions.height_heads * (1 + tol / 2)}
    assert view_differences(char, within)[0] == []


def test_policy_can_mark_artistic_variation(char) -> None:
    ident = char.identity.model_copy(update={"policy": {"clothing": IdentityRole.VARIATION}})
    c = char.model_copy(update={"identity": ident})
    assert role_of("clothing", c.identity.policy) is IdentityRole.VARIATION
    assert role_of("palette.skin") is IdentityRole.REQUIRED
    assert role_of("head.width_ratio") is IdentityRole.VIEW_SPECIFIC
    assert role_of("something_new") is IdentityRole.OPTIONAL
    winter = ViewDefinition(view=V.FRONT, identity_overrides={"clothing": ["winter parka"]})
    report = turnaround_report(with_views(c, [winter], [V.FRONT]))
    assert "TRN005" not in report.codes()


def test_identity_properties_tracked(char) -> None:
    props = identity_properties(char)
    for key in (
        "name",
        "height_units",
        "proportions.height_heads",
        "head.shape",
        "palette.coat",
        "clothing",
        "hair",
        "distinctive_features",
        "part_ids",
        "rig",
    ):
        assert key in props


def test_compare_versions_and_variants(store: CharacterStore, char) -> None:
    v_prev = store.load_version(char.id, char.version - 1)
    report = compare_characters(v_prev, char)
    assert not report.consistent  # palette/clothing/hair were added: required identity changed
    assert {d.prop for d in report.differences} >= {"palette.coat", "hair"}
    same = compare_characters(char, char)
    assert same.consistent and same.differences == []
    other = store.create("Tomas").character
    diff = compare_characters(char, other)
    assert not diff.consistent and any(d.prop == "name" for d in diff.differences)


def test_turnaround_shares_identity_and_view_artwork(store: CharacterStore, char, samples) -> None:
    manager = AssetManager(store.project)
    a = manager.register(samples["png"], name="side", category=AssetCategory.CHARACTER).record
    c = store.set_view_artwork(char.id, V.SIDE, a.id)
    report = store.validate(c.id)
    assert report.ok
    trn003 = next(i for i in report.warnings if i.code == "TRN003")
    assert "side" not in trn003.message  # the side view now has artwork
    # a view must not create a new identity: views live inside the one character file
    assert len(store.ids()) == 1


def test_approved_needs_all_artwork(store: CharacterStore, char) -> None:
    path = store.folder(char.id) / "character.yaml"
    data = yaml.safe_load(path.read_text())
    data["status"] = "approved"
    path.write_text(yaml.safe_dump(data))
    assert "CHR009" in store.validate(char.id).codes()


# --- preview --------------------------------------------------------------------------------


def test_diagnostic_svg_is_deterministic_and_well_formed(store: CharacterStore, char) -> None:
    rig = store.load(char.id).rig
    fk = solve_fk(rig)
    ik = solve_ik_chain(rig, "arm_l", Vec2(150, 400))
    side = char.turnaround.get(V.SIDE)
    svg1 = render_diagnostic_svg(char, ik.fk, view=side, ik=ik)
    svg2 = render_diagnostic_svg(char, ik.fk, view=side, ik=ik)
    assert svg1 == svg2
    root = ET.fromstring(svg1)
    ns = {"s": "http://www.w3.org/2000/svg"}
    assert "DIAGNOSTIC" in root.find("s:title", ns).text
    part_ids = [g.get("id") for g in root.find("s:g[@id='parts']", ns)]
    assert len(part_ids) == len(char.parts)
    assert root.find("s:g[@id='bones']", ns) is not None
    assert root.find("s:g[@id='ik-arm_l']", ns) is not None
    zs = [int(g.get("data-z")) for g in root.find("s:g[@id='parts']", ns)]
    assert zs == sorted(zs)  # drawn back to front
    plain = render_diagnostic_svg(char, fk)
    assert "ik-" not in plain


def test_preview_references_artwork_without_copying(
    store: CharacterStore, char, samples, tmp_path
) -> None:
    manager = AssetManager(store.project)
    head = manager.register(samples["svg"], name="head", category=AssetCategory.CHARACTER).record
    c = store.set_part_asset(char.id, "head", head.id)
    before = (store.project.root / head.current.path).read_bytes()
    svg = render_diagnostic_svg(
        c,
        solve_fk(store.load(c.id).rig),
        registry=store.project.registry(),
        project_root=store.project.root,
        output_dir=tmp_path,
    )
    assert "<image href=" in svg and "head.v1.svg" in svg
    assert (store.project.root / head.current.path).read_bytes() == before
