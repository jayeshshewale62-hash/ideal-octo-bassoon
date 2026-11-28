"""Shared fixtures. All tests run offline: outbound connections are blocked."""

from __future__ import annotations

import shutil
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

from studio.core.config import Settings, load_settings
from studio.core.project import Project
from studio.providers.image import encode_png_rgb
from studio.providers.tts import silent_wav

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "config"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that tries to open a network connection."""

    def guard(*args: object, **kwargs: object) -> None:
        raise RuntimeError("network access is not allowed in tests")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STUDIO_CONFIG_DIR", raising=False)


@pytest.fixture
def settings() -> Settings:
    return load_settings(CONFIG_DIR)


@pytest.fixture
def config_copy(tmp_path: Path) -> Path:
    """A writable copy of the repository's config directory."""
    target = tmp_path / "config"
    shutil.copytree(CONFIG_DIR, target)
    return target


@pytest.fixture
def projects_dir(tmp_path: Path) -> Path:
    path = tmp_path / "projects"
    path.mkdir()
    return path


@pytest.fixture
def project(settings: Settings, projects_dir: Path) -> Project:
    return Project.create("Test Film", settings, projects_dir=projects_dir)


@pytest.fixture
def samples(tmp_path: Path) -> Iterator[dict[str, Path]]:
    """Valid sample files of each main format, outside any project."""
    src = tmp_path / "incoming"
    src.mkdir()
    files = {
        "svg": src / "head.svg",
        "svg2": src / "head_v2.svg",
        "png": src / "sky.png",
        "wav": src / "line01.wav",
        "mp3": src / "theme.mp3",
        "json": src / "rig.json",
        "yaml": src / "notes.yaml",
    }
    files["svg"].write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        '<circle r="4" cx="5" cy="5"/></svg>\n'
    )
    files["svg2"].write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        '<circle r="3" cx="5" cy="5"/></svg>\n'
    )
    files["png"].write_bytes(encode_png_rgb(4, 4, (10, 20, 30)))
    files["wav"].write_bytes(silent_wav(0.25, 16000))
    files["mp3"].write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 64)
    files["json"].write_text('{"bones": []}\n')
    files["yaml"].write_text("title: test\n")
    yield files
