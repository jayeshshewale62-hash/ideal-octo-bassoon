"""Configuration loading.

The canonical, editable configuration lives in the repository's ``config/`` directory:

* ``config/studio.yaml``          -> :class:`StudioConfig`
* ``config/render_profiles.yaml`` -> :class:`RenderProfilesFile`
* ``config/providers.yaml``       -> :class:`ProvidersConfig`

The directory is located in this order:

1. an explicit ``config_dir`` argument (CLI ``--config-dir``);
2. the ``STUDIO_CONFIG_DIR`` environment variable;
3. the first ``config/studio.yaml`` found walking up from the current directory.

If none is found, built-in defaults are used (identical to the shipped files), so an
installed package works outside the repository. A config directory that *is* found but
holds an invalid or partial file is an error. It never falls back silently.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from studio.core.exceptions import ConfigError
from studio.core.schemas import (
    AudioSettings,
    ProvidersConfig,
    RenderProfile,
    RenderProfilesFile,
    StudioConfig,
    VideoSettings,
)
from studio.core.validation import load_model

ENV_CONFIG_DIR = "STUDIO_CONFIG_DIR"
STUDIO_FILE = "studio.yaml"
PROFILES_FILE = "render_profiles.yaml"
PROVIDERS_FILE = "providers.yaml"
CONFIG_FILES = (STUDIO_FILE, PROFILES_FILE, PROVIDERS_FILE)

log = logging.getLogger(__name__)


def default_render_profiles() -> RenderProfilesFile:
    """Built-in profiles (mirrors config/render_profiles.yaml)."""
    return RenderProfilesFile(
        default="hd1080p24",
        profiles={
            "hd1080p24": RenderProfile(
                label="Full HD 1920x1080 @ 24 fps (default delivery)",
                purpose="final",
                width=1920,
                height=1080,
                fps=24,
            ),
            "hd1080p30": RenderProfile(
                label="Full HD 1920x1080 @ 30 fps",
                purpose="final",
                width=1920,
                height=1080,
                fps=30,
            ),
            "uhd2160p24": RenderProfile(
                label="4K UHD 3840x2160 @ 24 fps (external render node recommended)",
                purpose="final",
                width=3840,
                height=2160,
                fps=24,
                video=VideoSettings(crf=18, preset="slow"),
                audio=AudioSettings(bitrate_kbps=320),
            ),
            "preview540p12": RenderProfile(
                label="Preview 960x540 @ 12 fps (animatics, fast checks)",
                purpose="preview",
                width=960,
                height=540,
                fps=12,
                video=VideoSettings(crf=26, preset="veryfast"),
                audio=AudioSettings(bitrate_kbps=128),
            ),
        },
    )


@dataclass(frozen=True)
class Settings:
    """All studio configuration, plus where it came from."""

    studio: StudioConfig
    render_profiles: RenderProfilesFile
    providers: ProvidersConfig
    config_dir: Path | None  # None -> built-in defaults

    @property
    def root(self) -> Path:
        """Directory that relative studio paths resolve against."""
        return self.config_dir.parent if self.config_dir else Path.cwd()

    @property
    def projects_dir(self) -> Path:
        return self.root / self.studio.paths.projects_dir

    def profile(self, name: str) -> RenderProfile:
        try:
            return self.render_profiles.profiles[name]
        except KeyError:
            known = ", ".join(sorted(self.render_profiles.profiles))
            raise ConfigError(f"unknown render profile {name!r} (known: {known})") from None


def find_config_dir(start: Path | None = None) -> Path | None:
    env = os.environ.get(ENV_CONFIG_DIR)
    if env:
        path = Path(env)
        if not path.is_dir():
            raise ConfigError(f"{ENV_CONFIG_DIR}={env} is not a directory")
        return path
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / "config"
        if (candidate / STUDIO_FILE).is_file():
            return candidate
    return None


def load_settings(config_dir: Path | None = None, *, use_defaults: bool = True) -> Settings:
    """Load and validate all configuration files."""
    directory = config_dir if config_dir is not None else find_config_dir()
    if directory is None:
        if not use_defaults:
            raise ConfigError("no config directory found (looked for config/studio.yaml)")
        log.debug("no config directory found; using built-in defaults")
        return Settings(StudioConfig(), default_render_profiles(), ProvidersConfig(), None)
    if not directory.is_dir():
        raise ConfigError(f"config directory not found: {directory}")
    missing = [name for name in CONFIG_FILES if not (directory / name).is_file()]
    if missing:
        raise ConfigError(f"config directory {directory} is missing: {', '.join(missing)}")
    settings = Settings(
        studio=load_model(StudioConfig, directory / STUDIO_FILE),
        render_profiles=load_model(RenderProfilesFile, directory / PROFILES_FILE),
        providers=load_model(ProvidersConfig, directory / PROVIDERS_FILE),
        config_dir=directory.resolve(),
    )
    _cross_check(settings)
    return settings


def _cross_check(settings: Settings) -> None:
    defaults = settings.studio.project_defaults
    for label, name in (
        ("render_profile", defaults.render_profile),
        ("preview_profile", defaults.preview_profile),
    ):
        if name not in settings.render_profiles.profiles:
            known = ", ".join(sorted(settings.render_profiles.profiles))
            raise ConfigError(
                f"studio.yaml project_defaults.{label} = {name!r} is not defined in "
                f"render_profiles.yaml (known: {known})"
            )


def configure_logging(settings: Settings, verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else getattr(logging, settings.studio.logging.level)
    logging.basicConfig(level=level, format=settings.studio.logging.format, force=True)
