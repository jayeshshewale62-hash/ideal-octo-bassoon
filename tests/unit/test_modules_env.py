from __future__ import annotations

import importlib
import shutil

from studio.core import environment
from studio.modules import MODULES, ModuleStatus
from tests.conftest import REPO_ROOT


def test_sixteen_modules_numbered() -> None:
    assert [m.number for m in MODULES] == list(range(1, 17))


def test_module_packages_exist_and_are_documented() -> None:
    for m in MODULES:
        package = importlib.import_module(m.package)
        assert package.__doc__ and len(package.__doc__) > 80, m.package


def test_implemented_modules_match_milestone_4_scope() -> None:
    foundation = [m.number for m in MODULES if m.status is ModuleStatus.FOUNDATION]
    assert foundation == [16]
    started = sorted(
        m.number for m in MODULES if m.status in (ModuleStatus.IMPLEMENTED, ModuleStatus.PARTIAL)
    )
    assert started == [2, 3, 4, 5]  # M3: characters, consistency, rigging; M4: face
    later = [m for m in MODULES if m.number not in (2, 3, 4, 5, 16)]
    assert all(m.status in (ModuleStatus.PLANNED, ModuleStatus.INTERFACES) for m in later)
    assert all(m.milestone >= 4 for m in later)


def test_modules_doc_mentions_every_module() -> None:
    text = (REPO_ROOT / "docs" / "MODULES.md").read_text()
    for m in MODULES:
        assert f"{m.number}. {m.name}" in text, m.name


def test_placeholder_packages_have_no_code() -> None:
    """Future modules stay placeholders: only a docstring (characters/rig are Milestone 3)."""
    for name in (
        "story",
        "animation",
        "environments",
        "storyboard",
        "scene",
        "compose",
        "render",
        "audio",
        "qc",
    ):
        folder = REPO_ROOT / "studio" / name
        assert sorted(p.name for p in folder.iterdir() if p.suffix == ".py") == ["__init__.py"]
        module = importlib.import_module(f"studio.{name}")
        public = [n for n in vars(module) if not n.startswith("_")]
        assert public == [], (name, public)


def test_doctor_without_ffmpeg(monkeypatch) -> None:
    real = shutil.which
    monkeypatch.setattr(
        shutil, "which", lambda t: None if t in ("ffmpeg", "ffprobe", "nvidia-smi") else real(t)
    )
    checks = {c.name: c for c in environment.run_checks()}
    assert checks["python"].ok and checks["pydantic"].ok and checks["PyYAML"].ok
    assert not checks["ffmpeg"].ok and checks["ffmpeg"].state == "optional-missing"
    assert checks["gpu"].ok and "not required" in checks["gpu"].detail
