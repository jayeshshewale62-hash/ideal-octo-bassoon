"""End-to-end CLI tests: they call ``studio.cli.main`` in-process and one real subprocess."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from studio import __version__
from studio.cli import main
from studio.core.project import Project, validate_project
from tests.conftest import CONFIG_DIR, REPO_ROOT


def run(capsys, *args: str) -> tuple[int, str, str]:
    code = main(["--config-dir", str(CONFIG_DIR), *args])
    out, err = capsys.readouterr()
    return code, out, err


def test_help(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for command in ("new", "project", "asset", "providers", "version", "doctor", "modules"):
        assert command in out


def test_no_command_prints_help(capsys) -> None:
    assert main([]) == 0
    assert "usage: studio" in capsys.readouterr().out


def test_group_without_action(capsys) -> None:
    code, _, err = run(capsys, "project")
    assert code == 2 and "validate" in err


def test_version(capsys) -> None:
    code, out, _ = run(capsys, "version")
    assert code == 0 and __version__ in out and "milestone 5" in out
    code, out, _ = run(capsys, "version", "--json")
    assert json.loads(out)["version"] == __version__


def test_new_validate_info_list(capsys, tmp_path: Path, settings) -> None:
    code, out, _ = run(capsys, "new", "demo", "--projects-dir", str(tmp_path))
    assert code == 0, out
    assert "created project demo" in out and "VALID" in out
    root = tmp_path / "demo"
    assert validate_project(root, settings).ok

    code, out, _ = run(capsys, "project", "validate", str(root))
    assert code == 0 and out.strip().startswith("VALID")
    code, out, _ = run(capsys, "project", "validate", str(root), "--json")
    assert json.loads(out)["ok"] is True

    code, out, _ = run(capsys, "project", "info", str(root), "--json")
    info = json.loads(out)
    assert info["slug"] == "demo" and info["output"] == "1920x1080 @ 24 fps" and info["assets"] == 0

    code, out, _ = run(capsys, "asset", "list", str(root))
    assert code == 0 and "no assets registered" in out
    code, out, _ = run(capsys, "asset", "validate", str(root))
    assert code == 0 and "VALID" in out


def test_register_and_list_assets(capsys, tmp_path: Path, samples) -> None:
    run(capsys, "new", "film", "--projects-dir", str(tmp_path))
    root = tmp_path / "film"
    code, out, _ = run(
        capsys,
        "asset",
        "register",
        str(root),
        str(samples["svg"]),
        "--name",
        "Hero head",
        "--category",
        "character",
        "--license",
        "proprietary",
        "--tag",
        "hero",
    )
    assert code == 0 and "copied to assets/characters/hero-head.v1.svg" in out
    asset_id = out.split()[1]
    code, out, _ = run(
        capsys,
        "asset",
        "register",
        str(root),
        str(samples["svg"]),
        "--name",
        "Again",
        "--category",
        "character",
    )
    assert code == 1
    code, out, _ = run(capsys, "asset", "add-version", str(root), asset_id, str(samples["svg2"]))
    assert code == 0 and "v2" in out
    code, out, _ = run(capsys, "asset", "list", str(root))
    assert "Hero head" in out and "v2" in out and "1 asset(s)" in out
    code, out, _ = run(capsys, "asset", "list", str(root), "--json", "--category", "character")
    assert json.loads(out)[0]["id"] == asset_id


def test_invalid_project_exit_code(capsys, tmp_path: Path) -> None:
    run(capsys, "new", "broken", "--projects-dir", str(tmp_path))
    (tmp_path / "broken" / "settings.yaml").unlink()
    code, out, _ = run(capsys, "project", "validate", str(tmp_path / "broken"))
    assert code == 1 and "INVALID" in out and "PRJ003" in out


def test_errors_are_messages_not_tracebacks(capsys, tmp_path: Path) -> None:
    code, _, err = run(capsys, "project", "info", str(tmp_path))
    assert code == 1 and err.startswith("error:") and "Traceback" not in err
    run(capsys, "new", "dup", "--projects-dir", str(tmp_path))
    code, _, err = run(capsys, "new", "dup", "--projects-dir", str(tmp_path))
    assert code == 1 and "already exists" in err


def test_providers_list(capsys, tmp_path: Path) -> None:
    code, out, _ = run(capsys, "providers", "list")
    assert code == 0 and "disabled" in out and "kokoro" in out
    data = json.loads(run(capsys, "providers", "list", "--json")[1])
    assert data["allow_network"] is False
    assert {v["state"] for v in data["selected"].values()} == {"disabled"}
    # project override to mock
    run(capsys, "new", "p", "--projects-dir", str(tmp_path))
    settings_file = tmp_path / "p" / "settings.yaml"
    settings_file.write_text(
        settings_file.read_text().replace("providers: {}", "providers:\n  tts:\n    provider: mock")
    )
    data = json.loads(
        run(capsys, "providers", "list", "--project", str(tmp_path / "p"), "--json")[1]
    )
    assert data["selected"]["tts"]["state"] == "enabled"


def test_modules_doctor_config_schema(capsys) -> None:
    code, out, _ = run(capsys, "modules")
    assert code == 0 and "Asset and Project Manager" in out and "foundation" in out
    code, out, _ = run(capsys, "doctor", "--json")
    assert code == 0 and any(c["name"] == "python" for c in json.loads(out))
    code, out, _ = run(capsys, "config", "validate")
    assert code == 0 and "configuration OK" in out
    code, out, _ = run(capsys, "config", "show")
    assert json.loads(out)["providers"]["allow_network"] is False
    code, out, _ = run(capsys, "schema", "export", "character")
    assert "properties" in json.loads(out)["character"]
    code, _, err = run(capsys, "schema", "export", "nope")
    assert code == 1 and "unknown schema" in err


def test_bad_config_dir(capsys, tmp_path: Path) -> None:
    code = main(["--config-dir", str(tmp_path / "missing"), "version"])
    assert code == 1 and "config directory not found" in capsys.readouterr().err


def test_console_script_subprocess(tmp_path: Path) -> None:
    """The installed entry point works as a real process (python -m studio)."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "studio",
            "--config-dir",
            str(CONFIG_DIR),
            "new",
            "demo",
            "--projects-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert Project.load(tmp_path / "demo").metadata.slug == "demo"
