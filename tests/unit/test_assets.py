from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from studio.core.assets import AssetManager
from studio.core.exceptions import (
    AssetConflictError,
    AssetNotFoundError,
    DuplicateAssetError,
    InvalidAssetError,
    PathSafetyError,
)
from studio.core.hashing import hash_file
from studio.core.project import REGISTRY_FILE, Project, validate_project
from studio.core.registry import AssetRegistry
from studio.core.schemas import (
    AIProvenance,
    AssetCategory,
    AssetLicense,
    AssetSource,
    SourceKind,
)


def _register(manager: AssetManager, path: Path, name: str, category=AssetCategory.CHARACTER, **kw):
    return manager.register(path, name=name, category=category, **kw)


def test_register_copies_and_records(project: Project, samples) -> None:
    original = samples["svg"].read_bytes()
    manager = AssetManager(project)
    result = _register(
        manager,
        samples["svg"],
        "Hero head",
        license=AssetLicense(spdx="proprietary"),
        source_info=AssetSource(kind=SourceKind.ORIGINAL, author="Studio"),
        tags=["hero", "hero"],
    )
    record = result.record
    assert result.copied is True
    assert record.id.startswith("ast_") and len(record.id) == 20
    assert record.current.path == "assets/characters/hero-head.v1.svg"
    assert record.format == "svg" and record.current_version == 1
    assert record.current.content_hash == hash_file(samples["svg"])
    assert record.tags == ["hero"]
    assert record.project_id == project.id
    # the original user file is untouched
    assert samples["svg"].read_bytes() == original
    assert (project.root / record.current.path).read_bytes() == original
    # persisted
    reloaded = AssetRegistry.load(project.root / REGISTRY_FILE)
    assert reloaded.get(record.id) == record


@pytest.mark.parametrize(
    ("key", "category", "folder"),
    [
        ("png", AssetCategory.ENVIRONMENT, "assets/environments"),
        ("wav", AssetCategory.VOICE, "assets/audio/voice"),
        ("mp3", AssetCategory.MUSIC, "assets/audio/music"),
        ("json", AssetCategory.DATA, "assets/data"),
        ("yaml", AssetCategory.SCRIPT, "story"),
    ],
)
def test_supported_formats(project: Project, samples, key, category, folder) -> None:
    record = _register(AssetManager(project), samples[key], f"sample {key}", category).record
    assert record.current.path.startswith(folder + "/")


def test_duplicate_content_detected(project: Project, samples, tmp_path: Path) -> None:
    manager = AssetManager(project)
    first = _register(manager, samples["svg"], "Hero head").record
    copy = tmp_path / "copy.svg"
    copy.write_bytes(samples["svg"].read_bytes().replace(b"\n", b"\r\n"))  # same content, CRLF
    with pytest.raises(DuplicateAssetError) as err:
        _register(manager, copy, "Another name")
    assert err.value.existing_id == first.id
    second = _register(manager, copy, "Deliberate copy", allow_duplicate=True).record
    assert second.id != first.id
    report = validate_project(project.root, project_settings_for(project))
    assert "AST015" in {i.code for i in report.warnings}


def project_settings_for(project: Project):
    from studio.core.config import load_settings
    from tests.conftest import CONFIG_DIR

    return load_settings(CONFIG_DIR)


def test_versions(project: Project, samples) -> None:
    manager = AssetManager(project)
    record = _register(manager, samples["svg"], "Hero head").record
    updated = manager.add_version(record.id, samples["svg2"], note="smaller eye").record
    assert updated.current_version == 2
    assert [v.version for v in updated.versions] == [1, 2]
    assert updated.current.path == "assets/characters/hero-head.v2.svg"
    assert updated.versions[0].path == "assets/characters/hero-head.v1.svg"
    assert (project.root / updated.versions[0].path).is_file()  # old version kept
    with pytest.raises(DuplicateAssetError, match="identical to version 2"):
        manager.add_version(record.id, samples["svg2"])


def test_version_format_must_match(project: Project, samples) -> None:
    manager = AssetManager(project)
    record = _register(manager, samples["svg"], "Hero head").record
    with pytest.raises(InvalidAssetError, match="is PNG"):
        manager.add_version(record.id, samples["png"])


def test_version_of_unknown_asset(project: Project, samples) -> None:
    with pytest.raises(AssetNotFoundError):
        AssetManager(project).add_version("ast_0000000000000000", samples["svg"])


def test_dependencies(project: Project, samples) -> None:
    manager = AssetManager(project)
    head = _register(manager, samples["svg"], "Hero head").record
    rig = _register(
        manager, samples["json"], "Hero rig", AssetCategory.DATA, dependencies=[head.id]
    ).record
    assert rig.dependencies == [head.id]
    assert manager.registry.dependents_of(head.id) == [rig.id]
    with pytest.raises(AssetNotFoundError, match="dependency"):
        _register(
            manager, samples["yaml"], "x", AssetCategory.DATA, dependencies=["ast_ffffffffffffffff"]
        )


def test_broken_references_detected(project: Project, samples, settings) -> None:
    manager = AssetManager(project)
    head = _register(manager, samples["svg"], "Hero head").record
    rig = _register(
        manager, samples["json"], "Hero rig", AssetCategory.DATA, dependencies=[head.id]
    ).record
    path = project.root / REGISTRY_FILE
    data = json.loads(path.read_text())
    for item in data["assets"]:
        if item["id"] == rig.id:
            item["dependencies"] = ["ast_aaaaaaaaaaaaaaaa"]
        if item["id"] == head.id:
            item["dependencies"] = [rig.id]
    path.write_text(json.dumps(data))
    report = validate_project(project.root, settings)
    assert {"AST013"} <= report.codes()


def test_dependency_cycle_detected(project: Project, samples, settings) -> None:
    manager = AssetManager(project)
    a = _register(manager, samples["svg"], "A").record
    b = _register(manager, samples["json"], "B", AssetCategory.DATA, dependencies=[a.id]).record
    path = project.root / REGISTRY_FILE
    data = json.loads(path.read_text())
    for item in data["assets"]:
        if item["id"] == a.id:
            item["dependencies"] = [b.id]
    path.write_text(json.dumps(data))
    assert "AST014" in validate_project(project.root, settings).codes()


def test_missing_file_and_modified_content(project: Project, samples, settings) -> None:
    manager = AssetManager(project)
    head = _register(manager, samples["svg"], "Hero head").record
    sky = _register(manager, samples["png"], "Sky", AssetCategory.ENVIRONMENT).record
    (project.root / sky.current.path).unlink()
    (project.root / head.current.path).write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    report = validate_project(project.root, settings)
    assert {"AST010", "AST011"} <= report.codes()
    assert not report.ok


def test_unregistered_file_warning(project: Project, settings) -> None:
    (project.root / "assets" / "props" / "stray.svg").write_text("<svg/>")
    report = validate_project(project.root, settings)
    assert report.ok
    assert "AST018" in {i.code for i in report.warnings}


def test_registry_path_traversal_detected(project: Project, samples, settings) -> None:
    record = _register(AssetManager(project), samples["svg"], "Hero head").record
    path = project.root / REGISTRY_FILE
    data = json.loads(path.read_text())
    data["assets"][0]["versions"][0]["path"] = "../../etc/passwd"
    path.write_text(json.dumps(data))
    report = validate_project(project.root, settings)
    assert "AST002" in report.codes()  # schema refuses the unsafe path
    assert record.id


def test_symlink_escape_detected(project: Project, samples, settings, tmp_path: Path) -> None:
    record = _register(AssetManager(project), samples["svg"], "Hero head").record
    target = project.root / record.current.path
    outside = tmp_path / "outside.svg"
    outside.write_bytes(target.read_bytes())
    target.unlink()
    os.symlink(outside, target)
    assert "AST012" in validate_project(project.root, settings).codes()


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("fake.png", b"this is text", "does not contain valid PNG"),
        ("empty.svg", b"", "empty"),
        ("bad.svg", b"<svg><unclosed></svg>", "not valid SVG"),
        ("html.svg", b"<html></html>", "not <svg>"),
        ("xxe.svg", b'<!DOCTYPE s [<!ENTITY x "y">]><svg/>', "entity"),
        ("bad.json", b"{oops", "not valid JSON"),
        ("bad.yaml", b"a: [1,", "not valid YAML"),
        ("noise.wav", b"RIFF0000AVI LIST", "WAV"),
        ("movie.mp4", b"\x00\x00\x00\x18ftypmp42", "unsupported asset format"),
        ("tool.exe", b"MZ", "unsupported"),
        ("bin.txt", b"\xff\xfe\x00", "not UTF-8"),
    ],
)
def test_invalid_files_rejected(project: Project, tmp_path: Path, name, content, message) -> None:
    f = tmp_path / name
    f.write_bytes(content)
    with pytest.raises(InvalidAssetError, match=message):
        _register(AssetManager(project), f, "bad")
    assert len(project.registry()) == 0


def test_missing_source(project: Project, tmp_path: Path) -> None:
    with pytest.raises(AssetNotFoundError):
        _register(AssetManager(project), tmp_path / "nope.svg", "x")


def test_directory_source(project: Project, tmp_path: Path) -> None:
    d = tmp_path / "dir.svg"
    d.mkdir()
    with pytest.raises(InvalidAssetError, match="regular file"):
        _register(AssetManager(project), d, "x")


def test_never_overwrites_existing_file(project: Project, samples) -> None:
    existing = project.root / "assets" / "characters" / "hero-head.v1.svg"
    existing.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>')
    before = existing.read_bytes()
    with pytest.raises(AssetConflictError, match="refusing to overwrite"):
        _register(AssetManager(project), samples["svg"], "Hero head")
    assert existing.read_bytes() == before


def test_register_in_place(project: Project, samples) -> None:
    inside = project.root / "assets" / "props" / "lamp.svg"
    inside.write_bytes(samples["svg"].read_bytes())
    manager = AssetManager(project)
    result = _register(manager, inside, "Lamp", AssetCategory.PROP)
    assert result.copied is False
    assert result.record.current.path == "assets/props/lamp.svg"
    with pytest.raises((AssetConflictError, DuplicateAssetError)):
        _register(manager, inside, "Lamp again", AssetCategory.PROP, allow_duplicate=True)


def test_control_files_cannot_be_assets(project: Project) -> None:
    with pytest.raises(InvalidAssetError, match="control file"):
        _register(AssetManager(project), project.root / "project.yaml", "meta", AssetCategory.DATA)


def test_ai_generated_requires_provenance(project: Project, samples) -> None:
    manager = AssetManager(project)
    with pytest.raises(Exception, match="ai_provenance"):
        _register(
            manager,
            samples["png"],
            "Plate",
            AssetCategory.ENVIRONMENT,
            source_info=AssetSource(kind=SourceKind.AI_GENERATED),
        )
    provenance = AIProvenance(
        provider="mock",
        model="mock-solid-color",
        prompt="sky",
        seed=1,
        generated_at=datetime.now(UTC),
    )
    record = _register(
        manager,
        samples["png"],
        "Plate",
        AssetCategory.ENVIRONMENT,
        source_info=AssetSource(kind=SourceKind.AI_GENERATED),
        ai_provenance=provenance,
    ).record
    assert record.ai_provenance is not None and record.ai_provenance.seed == 1


def test_asset_name_slug_cannot_traverse(project: Project, samples) -> None:
    record = _register(AssetManager(project), samples["svg"], "../../../etc/passwd").record
    assert record.current.path == "assets/characters/etc-passwd.v1.svg"


def test_unsafe_relative_path_rejected_by_safe_join(project: Project) -> None:
    from studio.core.paths import safe_join

    with pytest.raises(PathSafetyError):
        safe_join(project.root, "../outside.svg")
