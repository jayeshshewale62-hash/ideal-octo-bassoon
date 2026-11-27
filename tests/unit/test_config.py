from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from studio.core.config import (
    default_render_profiles,
    find_config_dir,
    load_settings,
)
from studio.core.exceptions import ConfigError, SchemaValidationError
from studio.core.schemas import ProvidersConfig, StudioConfig
from tests.conftest import CONFIG_DIR


def _edit(path: Path, change: dict[str, object]) -> None:
    data = yaml.safe_load(path.read_text())
    data.update(change)
    path.write_text(yaml.safe_dump(data))


def test_repository_config_loads(settings) -> None:
    assert settings.config_dir == CONFIG_DIR.resolve()
    assert settings.studio.studio.name == "Motion Animation Studio"
    assert settings.render_profiles.default == "hd1080p24"
    assert settings.providers.allow_network is False


def test_shipped_files_match_builtin_defaults(settings) -> None:
    assert settings.render_profiles == default_render_profiles()
    assert settings.studio == StudioConfig()
    assert settings.providers == ProvidersConfig()


def test_required_render_profiles(settings) -> None:
    p = settings.render_profiles.profiles
    assert (p["hd1080p24"].width, p["hd1080p24"].height, p["hd1080p24"].fps) == (1920, 1080, 24)
    assert (p["hd1080p30"].width, p["hd1080p30"].height, p["hd1080p30"].fps) == (1920, 1080, 30)
    assert (p["uhd2160p24"].width, p["uhd2160p24"].height, p["uhd2160p24"].fps) == (3840, 2160, 24)
    assert (p["preview540p12"].height, p["preview540p12"].fps) == (540, 12)
    assert p["preview540p12"].purpose == "preview"
    for profile in p.values():
        assert profile.video.codec == "h264" and profile.video.container == "mp4"


def test_all_providers_disabled_by_default(settings) -> None:
    for kind in ("image", "tts", "asr", "llm"):
        assert getattr(settings.providers, kind).provider == "none"


def test_defaults_when_no_config_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = load_settings()
    assert settings.config_dir is None
    assert settings.render_profiles.default == "hd1080p24"


def test_no_config_dir_strict_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError, match="no config directory"):
        load_settings(use_defaults=False)


def test_find_config_dir_walks_up(tmp_path: Path, config_copy: Path, monkeypatch) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert find_config_dir() == config_copy.resolve()


def test_env_var_config_dir(config_copy: Path, monkeypatch) -> None:
    monkeypatch.setenv("STUDIO_CONFIG_DIR", str(config_copy))
    assert load_settings().config_dir == config_copy.resolve()


def test_env_var_pointing_nowhere(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STUDIO_CONFIG_DIR", str(tmp_path / "missing"))
    with pytest.raises(ConfigError, match="not a directory"):
        load_settings()


def test_missing_config_file(config_copy: Path) -> None:
    (config_copy / "providers.yaml").unlink()
    with pytest.raises(ConfigError, match=r"missing: providers\.yaml"):
        load_settings(config_copy)


def test_missing_config_directory(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_settings(tmp_path / "nope")


def test_invalid_yaml_syntax(config_copy: Path) -> None:
    (config_copy / "studio.yaml").write_text("studio: [unclosed\n")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_settings(config_copy)


def test_unknown_field_is_reported(config_copy: Path) -> None:
    _edit(config_copy / "studio.yaml", {"colour_scheme": "dark"})
    with pytest.raises(SchemaValidationError) as err:
        load_settings(config_copy)
    assert "colour_scheme: unknown field (check the spelling)" in err.value.problems


def test_wrong_schema_version(config_copy: Path) -> None:
    _edit(config_copy / "studio.yaml", {"schema_version": 99})
    with pytest.raises(SchemaValidationError, match="schema_version"):
        load_settings(config_copy)


def test_default_profile_must_exist(config_copy: Path) -> None:
    _edit(config_copy / "render_profiles.yaml", {"default": "imax"})
    with pytest.raises(SchemaValidationError, match="'imax' is not defined"):
        load_settings(config_copy)


def test_odd_dimensions_rejected(config_copy: Path) -> None:
    path = config_copy / "render_profiles.yaml"
    data = yaml.safe_load(path.read_text())
    data["profiles"]["hd1080p24"]["width"] = 1921
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(SchemaValidationError, match="must be even"):
        load_settings(config_copy)


def test_invalid_fps_rejected(config_copy: Path) -> None:
    path = config_copy / "render_profiles.yaml"
    data = yaml.safe_load(path.read_text())
    data["profiles"]["hd1080p30"]["fps"] = 0
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(SchemaValidationError, match=r"profiles\.hd1080p30\.fps"):
        load_settings(config_copy)


def test_studio_defaults_must_reference_known_profiles(config_copy: Path) -> None:
    path = config_copy / "studio.yaml"
    data = yaml.safe_load(path.read_text())
    data["project_defaults"]["render_profile"] = "cinema8k"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ConfigError, match="cinema8k"):
        load_settings(config_copy)


def test_secret_in_provider_options_rejected(config_copy: Path) -> None:
    path = config_copy / "providers.yaml"
    data = yaml.safe_load(path.read_text())
    data["llm"]["options"] = {"api_key": "sk-not-real"}
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(SchemaValidationError, match="looks like a secret"):
        load_settings(config_copy)


def test_empty_file_uses_schema_defaults(config_copy: Path) -> None:
    (config_copy / "providers.yaml").write_text("")
    assert load_settings(config_copy).providers == ProvidersConfig()


def test_non_mapping_document(config_copy: Path) -> None:
    (config_copy / "studio.yaml").write_text("- a\n- b\n")
    with pytest.raises(SchemaValidationError, match="expected a mapping"):
        load_settings(config_copy)


def test_unknown_profile_lookup(settings) -> None:
    with pytest.raises(ConfigError, match="unknown render profile"):
        settings.profile("nope")
