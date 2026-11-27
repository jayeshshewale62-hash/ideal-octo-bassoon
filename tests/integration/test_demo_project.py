"""The committed demo project (created with `studio new demo`) must stay valid."""

from __future__ import annotations

import json

import yaml

from studio.core.project import Project, validate_project
from tests.conftest import REPO_ROOT

DEMO = REPO_ROOT / "projects" / "demo"


def test_demo_project_is_valid(settings) -> None:
    report = validate_project(DEMO, settings)
    assert report.ok, [str(i) for i in report.issues]
    assert report.warnings == []


def test_demo_project_contents() -> None:
    project = Project.load(DEMO)
    assert project.metadata.slug == "demo"
    registry = json.loads((DEMO / "assets" / "registry.json").read_text())
    assert registry["assets"] == []  # no fake completed animation assets
    story = yaml.safe_load((DEMO / "story" / "story.yaml").read_text())
    assert story["status"] == "placeholder"
    assert "studio new" in (DEMO / "README.md").read_text()
