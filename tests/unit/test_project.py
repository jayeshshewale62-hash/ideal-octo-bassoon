from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from studio.core.exceptions import (
    ConfigError,
    ProjectExistsError,
    ProjectNotFoundError,
    SchemaValidationError,
    StudioError,
)
from studio.core.project import (
    PROJECT_FILE,
    REGISTRY_FILE,
    REQUIRED_DIRS,
    SETTINGS_FILE,
    STORY_FILE,
    STORYBOARD_FILE,
    Project,
    validate_project,
)
from studio.core.schemas import ProjectKind


def test_create_project_layout(project: Project, settings) -> None:
    root = project.root
    assert root.name == "test-film"
    for rel in (
        PROJECT_FILE,
        SETTINGS_FILE,
        "README.md",
        REGISTRY_FILE,
        STORY_FILE,
        STORYBOARD_FILE,
    ):
        assert (root / rel).is_file(), rel
    for rel in REQUIRED_DIRS:
        assert (root / rel).is_dir(), rel
    assert project.metadata.title == "Test Film"
    assert project.metadata.kind is ProjectKind.SHORT
    assert project.settings.render_profile == "hd1080p24"
    assert len(project.registry()) == 0
    report = validate_project(root, settings)
    assert report.ok, [str(i) for i in report.issues]
    assert report.warnings == []


def test_project_ids_are_unique(settings, projects_dir: Path) -> None:
    ids = {Project.create(f"film {i}", settings, projects_dir=projects_dir).id for i in range(25)}
    assert len(ids) == 25
    assert all(i.startswith("prj_") and len(i) == 36 for i in ids)


def test_load_roundtrip(project: Project) -> None:
    loaded = Project.load(project.root)
    assert loaded.metadata == project.metadata
    assert loaded.settings == project.settings


def test_options(settings, projects_dir: Path) -> None:
    p = Project.create(
        "Moon",
        settings,
        projects_dir=projects_dir,
        title="The Moon Keeper",
        kind=ProjectKind.FEATURE,
        description="A long film",
        render_profile="hd1080p30",
    )
    assert (p.metadata.title, p.metadata.kind, p.settings.render_profile) == (
        "The Moon Keeper",
        ProjectKind.FEATURE,
        "hd1080p30",
    )


def test_refuses_existing_nonempty_dir(project: Project, settings) -> None:
    with pytest.raises(ProjectExistsError):
        Project.create("Test Film", settings, projects_dir=project.root.parent)


def test_accepts_existing_empty_dir(settings, projects_dir: Path) -> None:
    (projects_dir / "empty").mkdir()
    assert Project.create("empty", settings, projects_dir=projects_dir).root.name == "empty"


def test_unknown_profile_rejected_before_writing(settings, projects_dir: Path) -> None:
    with pytest.raises(ConfigError):
        Project.create("x", settings, projects_dir=projects_dir, render_profile="nope")
    assert not (projects_dir / "x").exists()


def test_name_without_letters(settings, projects_dir: Path) -> None:
    with pytest.raises(StudioError, match="no letters"):
        Project.create("!!!", settings, projects_dir=projects_dir)


def test_load_non_project(tmp_path: Path) -> None:
    with pytest.raises(ProjectNotFoundError):
        Project.load(tmp_path)


def test_load_invalid_metadata(project: Project) -> None:
    path = project.root / PROJECT_FILE
    data = yaml.safe_load(path.read_text())
    data["id"] = "not-an-id"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(SchemaValidationError, match="id"):
        Project.load(project.root)


# --- validation reports ------------------------------------------------------------------


def test_validate_missing_directory(project: Project, settings) -> None:
    shutil.rmtree(project.root / "assets" / "props")
    report = validate_project(project.root, settings)
    assert not report.ok
    assert "PRJ004" in report.codes()


def test_validate_not_a_project(tmp_path: Path, settings) -> None:
    report = validate_project(tmp_path, settings)
    assert report.codes() == {"PRJ001"}


def test_validate_nonexistent(tmp_path: Path, settings) -> None:
    assert validate_project(tmp_path / "ghost", settings).codes() == {"PRJ000"}


def test_validate_invalid_metadata(project: Project, settings) -> None:
    path = project.root / PROJECT_FILE
    data = yaml.safe_load(path.read_text())
    data["created_at"] = "yesterday"
    path.write_text(yaml.safe_dump(data))
    assert "PRJ002" in validate_project(project.root, settings).codes()


def test_validate_timestamps_order(project: Project, settings) -> None:
    path = project.root / PROJECT_FILE
    data = yaml.safe_load(path.read_text())
    data["updated_at"] = "2000-01-01T00:00:00Z"
    path.write_text(yaml.safe_dump(data))
    report = validate_project(project.root, settings)
    assert any("updated_at is earlier" in i.message for i in report.errors)


def test_validate_missing_settings(project: Project, settings) -> None:
    (project.root / SETTINGS_FILE).unlink()
    assert "PRJ003" in validate_project(project.root, settings).codes()


def test_validate_unknown_profile_in_settings(project: Project, settings) -> None:
    path = project.root / SETTINGS_FILE
    data = yaml.safe_load(path.read_text())
    data["render_profile"] = "vhs"
    path.write_text(yaml.safe_dump(data))
    assert "PRJ005" in validate_project(project.root, settings).codes()


def test_validate_missing_registry(project: Project, settings) -> None:
    (project.root / REGISTRY_FILE).unlink()
    assert "AST001" in validate_project(project.root, settings).codes()


def test_validate_corrupt_registry(project: Project, settings) -> None:
    (project.root / REGISTRY_FILE).write_text("{not json")
    assert "AST002" in validate_project(project.root, settings).codes()


def test_validate_placeholders(project: Project, settings) -> None:
    (project.root / STORY_FILE).unlink()
    (project.root / STORYBOARD_FILE).write_text("- just a list\n")
    report = validate_project(project.root, settings)
    assert "PRJ006" in {i.code for i in report.warnings}
    assert "PRJ007" in {i.code for i in report.errors}


def test_touch_updates_timestamp(project: Project) -> None:
    before = project.metadata.updated_at
    project.touch()
    loaded = Project.load(project.root).metadata
    assert loaded.updated_at >= before >= loaded.created_at


def test_metadata_assignment_is_validated(project: Project) -> None:
    before = project.metadata.updated_at
    with pytest.raises(ValueError, match="earlier than created_at"):
        project.metadata.updated_at = before.replace(year=before.year - 1)
