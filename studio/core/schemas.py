"""Versioned data schemas (pydantic v2).

Every persisted document carries ``schema_version``. Models reject unknown fields
(``extra="forbid"``) so typos are reported instead of silently ignored.
:func:`studio.core.validation.parse_model` turns validation errors into readable lines.

Documents defined here:

==========================  ==========================  ==============
Model                       Stored in                   Schema version
==========================  ==========================  ==============
StudioConfig                config/studio.yaml          1
RenderProfilesFile          config/render_profiles.yaml 1
ProvidersConfig             config/providers.yaml       1
ProjectMetadata             <project>/project.yaml      1
ProjectSettings             <project>/settings.yaml     1
AssetRegistryFile           <project>/assets/registry.json 1
CharacterIdentity           assets/characters/<id>/character.yaml 1
EnvironmentMetadata         assets/environments/<id>/environment.yaml 1
==========================  ==========================  ==============
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from studio.core.exceptions import PathSafetyError
from studio.core.hashing import is_valid_hash
from studio.core.paths import check_relative_path

SCHEMA_VERSION = 1

# --- shared field types ------------------------------------------------------------------

ID_PATTERN = r"^[a-z]{3}_[0-9a-z][0-9a-z_-]{2,63}$"
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
SECRET_KEY_HINTS = ("api_key", "apikey", "token", "secret", "password", "passwd", "credential")


def _relative_path(value: str) -> str:
    try:
        return check_relative_path(value)
    except PathSafetyError as exc:
        raise ValueError(str(exc)) from None


def _content_hash(value: str) -> str:
    if not is_valid_hash(value):
        raise ValueError("must look like 'sha256:' followed by 64 lower-case hex characters")
    return value


def _hex_color(value: str) -> str:
    if not HEX_COLOR.match(value):
        raise ValueError(f"colour {value!r} must be '#RRGGBB'")
    return value.upper()


RelativePath = Annotated[str, AfterValidator(_relative_path)]
ContentHash = Annotated[str, AfterValidator(_content_hash)]
HexColor = Annotated[str, AfterValidator(_hex_color)]
Identifier = Annotated[str, Field(pattern=ID_PATTERN)]
Slug = Annotated[str, Field(pattern=SLUG_PATTERN, min_length=1, max_length=48)]
NonEmpty = Annotated[str, Field(min_length=1, max_length=200)]


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, use_enum_values=False)


# =========================================================================================
# Studio configuration
# =========================================================================================


class StudioInfo(StrictModel):
    name: NonEmpty = "Motion Animation Studio"
    version: NonEmpty = "0.2.0"


class StudioPaths(StrictModel):
    """Directories relative to the repository root (the parent of the config directory)."""

    projects_dir: RelativePath = "projects"
    assets_dir: RelativePath = "assets"
    cache_dir: RelativePath = ".cache/studio"
    output_dir: RelativePath = "renders"


class ProjectKind(StrEnum):
    SHORT = "short"  # up to ~3 minutes
    EPISODE = "episode"  # ~3-30 minutes
    FEATURE = "feature"  # long-form film


class ProjectDefaults(StrictModel):
    render_profile: Annotated[str, Field(min_length=1)] = "hd1080p24"
    preview_profile: Annotated[str, Field(min_length=1)] = "preview540p12"
    kind: ProjectKind = ProjectKind.SHORT
    language: Annotated[str, Field(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")] = "en"


class LoggingConfig(StrictModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    format: NonEmpty = "%(levelname)s %(name)s: %(message)s"


class StudioConfig(StrictModel):
    schema_version: Literal[1] = 1
    studio: StudioInfo = Field(default_factory=StudioInfo)
    paths: StudioPaths = Field(default_factory=StudioPaths)
    project_defaults: ProjectDefaults = Field(default_factory=ProjectDefaults)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


# =========================================================================================
# Render profiles (definitions only; the renderer arrives in later milestones)
# =========================================================================================


class VideoSettings(StrictModel):
    container: Literal["mp4"] = "mp4"
    codec: Literal["h264"] = "h264"
    encoder: Literal["libx264"] = "libx264"
    profile: Literal["baseline", "main", "high"] = "high"
    pix_fmt: Literal["yuv420p"] = "yuv420p"
    crf: Annotated[int, Field(ge=0, le=51)] = 18
    preset: Literal[
        "ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower"
    ] = "medium"
    color_space: Literal["bt709"] = "bt709"
    faststart: bool = True


class AudioSettings(StrictModel):
    codec: Literal["aac"] = "aac"
    sample_rate: Literal[44100, 48000] = 48000
    channels: Annotated[int, Field(ge=1, le=2)] = 2
    bitrate_kbps: Annotated[int, Field(ge=64, le=512)] = 256
    loudness_lufs: Annotated[float, Field(ge=-36, le=-6)] = -14.0
    true_peak_dbtp: Annotated[float, Field(ge=-9, le=0)] = -1.0


class RenderProfile(StrictModel):
    label: NonEmpty
    purpose: Literal["final", "preview"]
    width: Annotated[int, Field(ge=16, le=8192)]
    height: Annotated[int, Field(ge=16, le=8192)]
    fps: Annotated[float, Field(gt=0, le=120)]
    video: VideoSettings = Field(default_factory=VideoSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)

    @model_validator(mode="after")
    def _even_dimensions(self) -> RenderProfile:
        if self.video.pix_fmt == "yuv420p" and (self.width % 2 or self.height % 2):
            raise ValueError(
                f"width and height must be even for yuv420p (got {self.width}x{self.height})"
            )
        return self

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height


class RenderProfilesFile(StrictModel):
    schema_version: Literal[1] = 1
    default: Annotated[str, Field(min_length=1)]
    profiles: dict[Annotated[str, Field(pattern=r"^[a-z0-9_]+$")], RenderProfile]

    @model_validator(mode="after")
    def _default_exists(self) -> RenderProfilesFile:
        if not self.profiles:
            raise ValueError("at least one render profile is required")
        if self.default not in self.profiles:
            known = ", ".join(sorted(self.profiles))
            raise ValueError(f"default profile {self.default!r} is not defined (known: {known})")
        return self


# =========================================================================================
# Provider configuration
# =========================================================================================


class ProviderKind(StrEnum):
    IMAGE = "image"
    TTS = "tts"
    ASR = "asr"
    LLM = "llm"


class ProviderSelection(StrictModel):
    """Which implementation serves one provider kind.

    ``provider`` is ``none`` (disabled, the default), ``mock`` (deterministic, offline) or
    the name of a local/cloud provider. Secrets never go here: a provider that needs a key
    reads it from the environment variable named in ``credentials_env``.
    """

    provider: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")] = "none"
    options: dict[str, Any] = Field(default_factory=dict)
    credentials_env: list[Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]*$")]] = Field(
        default_factory=list
    )

    @field_validator("options")
    @classmethod
    def _no_secrets_in_options(cls, value: dict[str, Any]) -> dict[str, Any]:
        for key in value:
            lowered = key.lower()
            if any(hint in lowered for hint in SECRET_KEY_HINTS):
                raise ValueError(
                    f"option {key!r} looks like a secret. Never store secrets in config files; "
                    "list the environment variable name in 'credentials_env' instead"
                )
        return value


class ProvidersConfig(StrictModel):
    schema_version: Literal[1] = 1
    allow_network: bool = False
    image: ProviderSelection = Field(default_factory=ProviderSelection)
    tts: ProviderSelection = Field(default_factory=ProviderSelection)
    asr: ProviderSelection = Field(default_factory=ProviderSelection)
    llm: ProviderSelection = Field(default_factory=ProviderSelection)

    def selection(self, kind: ProviderKind) -> ProviderSelection:
        result: ProviderSelection = getattr(self, kind.value)
        return result


# =========================================================================================
# Projects
# =========================================================================================


class ProjectMetadata(StrictModel):
    schema_version: Literal[1] = 1
    id: Annotated[str, Field(pattern=r"^prj_[0-9a-f]{32}$")]
    slug: Slug
    title: NonEmpty
    kind: ProjectKind = ProjectKind.SHORT
    description: Annotated[str, Field(max_length=2000)] = ""
    language: Annotated[str, Field(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")] = "en"
    target_duration_s: Annotated[float, Field(gt=0, le=6 * 3600)] | None = None
    created_at: datetime
    updated_at: datetime
    studio_version: NonEmpty

    @model_validator(mode="after")
    def _times_ordered(self) -> ProjectMetadata:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at is earlier than created_at")
        return self


class ProjectSettings(StrictModel):
    """Per-project configuration. Provider entries override config/providers.yaml."""

    schema_version: Literal[1] = 1
    render_profile: Annotated[str, Field(min_length=1)] = "hd1080p24"
    preview_profile: Annotated[str, Field(min_length=1)] = "preview540p12"
    fps_override: Annotated[float, Field(gt=0, le=120)] | None = None
    providers: dict[ProviderKind, ProviderSelection] = Field(default_factory=dict)


# =========================================================================================
# Assets
# =========================================================================================


class AssetCategory(StrEnum):
    CHARACTER = "character"
    ENVIRONMENT = "environment"
    PROP = "prop"
    TEXTURE = "texture"
    AUDIO = "audio"
    VOICE = "voice"
    SFX = "sfx"
    MUSIC = "music"
    FONT = "font"
    SCRIPT = "script"
    STORYBOARD = "storyboard"
    DATA = "data"
    REFERENCE = "reference"
    OTHER = "other"


class SourceKind(StrEnum):
    ORIGINAL = "original"  # made for this studio
    AI_GENERATED = "ai_generated"  # produced by a provider; needs ai_provenance
    LICENSED = "licensed"  # bought or licensed from a third party
    THIRD_PARTY = "third_party"  # open-licensed third-party work (fonts, CC0 sfx ...)
    LEGACY_IMPORT = "legacy_import"  # adapted from a legacy branch of this repository


class AssetSource(StrictModel):
    kind: SourceKind = SourceKind.ORIGINAL
    author: Annotated[str, Field(max_length=200)] = ""
    url: Annotated[str, Field(max_length=500)] = ""
    notes: Annotated[str, Field(max_length=2000)] = ""


class AssetLicense(StrictModel):
    """``spdx`` is an SPDX identifier (e.g. 'CC0-1.0', 'OFL-1.1') or 'proprietary'/'unknown'."""

    spdx: Annotated[str, Field(min_length=1, max_length=64)] = "unknown"
    attribution: Annotated[str, Field(max_length=500)] = ""
    url: Annotated[str, Field(max_length=500)] = ""
    commit_approved: bool = False  # explicit approval to commit a binary file to git


class AIProvenance(StrictModel):
    provider: NonEmpty
    model: NonEmpty
    prompt: Annotated[str, Field(max_length=8000)] = ""
    negative_prompt: Annotated[str, Field(max_length=8000)] = ""
    seed: int | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime
    reviewed_by_human: bool = False


class AssetVersion(StrictModel):
    version: Annotated[int, Field(ge=1)]
    path: RelativePath
    content_hash: ContentHash
    size_bytes: Annotated[int, Field(ge=0)]
    created_at: datetime
    note: Annotated[str, Field(max_length=500)] = ""


class AssetRecord(StrictModel):
    id: Annotated[str, Field(pattern=r"^ast_[0-9a-f]{16}$")]
    name: NonEmpty
    category: AssetCategory
    format: Annotated[str, Field(pattern=r"^[a-z0-9]{2,6}$")]
    project_id: Annotated[str, Field(pattern=r"^prj_[0-9a-f]{32}$")]
    versions: Annotated[list[AssetVersion], Field(min_length=1)]
    source: AssetSource = Field(default_factory=AssetSource)
    license: AssetLicense = Field(default_factory=AssetLicense)
    ai_provenance: AIProvenance | None = None
    dependencies: list[Annotated[str, Field(pattern=r"^ast_[0-9a-f]{16}$")]] = Field(
        default_factory=list
    )
    tags: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _consistency(self) -> AssetRecord:
        numbers = [v.version for v in self.versions]
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError(f"versions must be numbered 1..n in order, got {numbers}")
        if self.source.kind is SourceKind.AI_GENERATED and self.ai_provenance is None:
            raise ValueError("source.kind is 'ai_generated' but ai_provenance is missing")
        if self.id in self.dependencies:
            raise ValueError("an asset cannot depend on itself")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("dependencies contain duplicates")
        return self

    @property
    def current(self) -> AssetVersion:
        return self.versions[-1]

    @property
    def current_version(self) -> int:
        return self.versions[-1].version


class AssetRegistryFile(StrictModel):
    schema_version: Literal[1] = 1
    project_id: Annotated[str, Field(pattern=r"^prj_[0-9a-f]{32}$")]
    assets: list[AssetRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> AssetRegistryFile:
        seen: set[str] = set()
        for record in self.assets:
            if record.id in seen:
                raise ValueError(f"asset id {record.id} appears more than once")
            seen.add(record.id)
            if record.project_id != self.project_id:
                raise ValueError(
                    f"asset {record.id} belongs to {record.project_id}, not {self.project_id}"
                )
        return self


# =========================================================================================
# Character identity (metadata only; artwork and rigs arrive in Milestone 3+)
# =========================================================================================


class TurnaroundView(StrEnum):
    FRONT = "front"
    THREE_QUARTER = "three_quarter"
    SIDE = "side"
    BACK = "back"


class CharacterStatus(StrEnum):
    CONCEPT = "concept"
    DESIGNED = "designed"
    RIGGED = "rigged"
    APPROVED = "approved"


class CharacterProportions(StrictModel):
    """Canonical proportions. Lengths are in head-heights so they are scale-free."""

    height_heads: Annotated[float, Field(gt=0.5, le=12)]
    shoulder_width_heads: Annotated[float, Field(gt=0, le=6)] | None = None
    arm_length_heads: Annotated[float, Field(gt=0, le=8)] | None = None
    leg_length_heads: Annotated[float, Field(gt=0, le=8)] | None = None
    tolerance: Annotated[float, Field(ge=0, le=0.5)] = 0.03


class CharacterVoice(StrictModel):
    provider: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")] = "none"
    voice_id: Annotated[str, Field(max_length=100)] = ""


class CharacterIdentity(StrictModel):
    schema_version: Literal[1] = 1
    id: Annotated[str, Field(pattern=r"^chr_[a-z0-9][a-z0-9_-]{1,47}$")]
    name: NonEmpty
    version: Annotated[int, Field(ge=1)] = 1
    status: CharacterStatus = CharacterStatus.CONCEPT
    description: Annotated[str, Field(max_length=4000)] = ""
    personality: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list
    )
    palette: dict[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")], HexColor] = Field(
        default_factory=dict
    )
    proportions: CharacterProportions
    required_views: list[TurnaroundView] = Field(
        default_factory=lambda: [
            TurnaroundView.FRONT,
            TurnaroundView.THREE_QUARTER,
            TurnaroundView.SIDE,
            TurnaroundView.BACK,
        ]
    )
    model_sheet_asset: Annotated[str, Field(pattern=r"^ast_[0-9a-f]{16}$")] | None = None
    rig_asset: Annotated[str, Field(pattern=r"^ast_[0-9a-f]{16}$")] | None = None
    voice: CharacterVoice = Field(default_factory=CharacterVoice)
    original_design: bool = True

    @model_validator(mode="after")
    def _rules(self) -> CharacterIdentity:
        if not self.original_design:
            raise ValueError("only original character designs are allowed (original_design: true)")
        if TurnaroundView.FRONT not in self.required_views:
            raise ValueError("required_views must include 'front'")
        if len(set(self.required_views)) != len(self.required_views):
            raise ValueError("required_views contains duplicates")
        if self.status in (CharacterStatus.RIGGED, CharacterStatus.APPROVED) and not self.rig_asset:
            raise ValueError(f"status {self.status.value!r} requires rig_asset")
        return self


# =========================================================================================
# Environment metadata
# =========================================================================================


class EnvironmentLayer(StrictModel):
    """One parallax layer. depth 1.0 = character plane, <1 background, >1 foreground."""

    name: Annotated[str, Field(pattern=r"^[a-z0-9_]+$")]
    depth: Annotated[float, Field(gt=0, le=4)]
    asset: Annotated[str, Field(pattern=r"^ast_[0-9a-f]{16}$")] | None = None
    blur: Annotated[float, Field(ge=0, le=64)] = 0.0


class EnvironmentMetadata(StrictModel):
    schema_version: Literal[1] = 1
    id: Annotated[str, Field(pattern=r"^env_[a-z0-9][a-z0-9_-]{1,47}$")]
    name: NonEmpty
    version: Annotated[int, Field(ge=1)] = 1
    description: Annotated[str, Field(max_length=4000)] = ""
    width: Annotated[int, Field(ge=16, le=16384)] = 2400
    height: Annotated[int, Field(ge=16, le=16384)] = 1350
    time_of_day: Literal["dawn", "day", "dusk", "night", "interior", "unspecified"] = "unspecified"
    palette: dict[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")], HexColor] = Field(
        default_factory=dict
    )
    layers: list[EnvironmentLayer] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_layers(self) -> EnvironmentMetadata:
        names = [layer.name for layer in self.layers]
        if len(set(names)) != len(names):
            raise ValueError("layer names must be unique")
        return self


SCHEMAS: dict[str, type[BaseModel]] = {
    "studio_config": StudioConfig,
    "render_profiles": RenderProfilesFile,
    "providers": ProvidersConfig,
    "project": ProjectMetadata,
    "project_settings": ProjectSettings,
    "asset_registry": AssetRegistryFile,
    "character": CharacterIdentity,
    "environment": EnvironmentMetadata,
}
"""Name -> model, used by ``studio schema export`` and docs/DATA_SCHEMAS.md."""
