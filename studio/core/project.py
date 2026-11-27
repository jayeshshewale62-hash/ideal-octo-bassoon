"""Projects: creation, loading and validation (module 16, part 1).

Standard layout of ``projects/<slug>/``::

    project.yaml            ProjectMetadata (identity, title, kind, timestamps)
    settings.yaml           ProjectSettings (render profiles, provider overrides)
    README.md               what this folder is and how to work with it
    story/story.yaml        story placeholder (module 1, later milestone)
    storyboard/storyboard.yaml   storyboard placeholder (module 8, later milestone)
    scenes/                 scene files (modules 6/9, later milestones)
    assets/registry.json    the asset registry
    assets/<category>/      registered asset files
    renders/ cache/         created on demand; git-ignored
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from studio import __version__
from studio.core.config import Settings
from studio.core.exceptions import (
    ConfigError,
    ProjectExistsError,
    ProjectNotFoundError,
    SchemaValidationError,
    StudioError,
)
from studio.core.paths import slugify
from studio.core.registry import AssetRegistry
from studio.core.schemas import (
    AssetCategory,
    ProjectKind,
    ProjectMetadata,
    ProjectSettings,
    utc_now,
)
from studio.core.validation import (
    ValidationReport,
    dump_yaml,
    load_model,
    model_to_yaml,
    read_document,
    write_text_atomic,
)

PROJECT_FILE = "project.yaml"
SETTINGS_FILE = "settings.yaml"
README_FILE = "README.md"
REGISTRY_FILE = "assets/registry.json"
STORY_FILE = "story/story.yaml"
STORYBOARD_FILE = "storyboard/storyboard.yaml"

CATEGORY_DIRS: dict[AssetCategory, str] = {
    AssetCategory.CHARACTER: "assets/characters",
    AssetCategory.ENVIRONMENT: "assets/environments",
    AssetCategory.PROP: "assets/props",
    AssetCategory.TEXTURE: "assets/textures",
    AssetCategory.AUDIO: "assets/audio",
    AssetCategory.VOICE: "assets/audio/voice",
    AssetCategory.SFX: "assets/audio/sfx",
    AssetCategory.MUSIC: "assets/audio/music",
    AssetCategory.FONT: "assets/fonts",
    AssetCategory.SCRIPT: "story",
    AssetCategory.STORYBOARD: "storyboard",
    AssetCategory.DATA: "assets/data",
    AssetCategory.REFERENCE: "assets/references",
    AssetCategory.OTHER: "assets/other",
}

REQUIRED_DIRS: tuple[str, ...] = tuple(
    sorted({"assets", "scenes", "story", "storyboard", *CATEGORY_DIRS.values()})
)
GENERATED_DIRS: tuple[str, ...] = ("renders", "cache")


def new_project_id() -> str:
    return "prj_" + uuid.uuid4().hex


@dataclass
class Project:
    root: Path
    metadata: ProjectMetadata
    settings: ProjectSettings

    @property
    def id(self) -> str:
        return self.metadata.id

    @property
    def registry_path(self) -> Path:
        return self.root / REGISTRY_FILE

    def registry(self) -> AssetRegistry:
        return AssetRegistry.load(self.registry_path)

    # --- loading -------------------------------------------------------------------------

    @classmethod
    def load(cls, root: Path) -> Project:
        root = root.resolve()
        if not (root / PROJECT_FILE).is_file():
            raise ProjectNotFoundError(f"{root} is not a studio project (no {PROJECT_FILE})")
        metadata = load_model(ProjectMetadata, root / PROJECT_FILE)
        settings_path = root / SETTINGS_FILE
        if not settings_path.is_file():
            raise ProjectNotFoundError(f"{root} is missing {SETTINGS_FILE}")
        settings = load_model(ProjectSettings, settings_path)
        return cls(root=root, metadata=metadata, settings=settings)

    # --- creation ------------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        name: str,
        settings: Settings,
        *,
        projects_dir: Path | None = None,
        title: str | None = None,
        kind: ProjectKind | None = None,
        description: str = "",
        render_profile: str | None = None,
    ) -> Project:
        slug = slugify(name)
        if not slug:
            raise StudioError(f"project name {name!r} has no letters or digits")
        defaults = settings.studio.project_defaults
        profile = render_profile or defaults.render_profile
        settings.profile(profile)  # raises ConfigError for unknown names
        settings.profile(defaults.preview_profile)

        base = projects_dir if projects_dir is not None else settings.projects_dir
        root = (base / slug).resolve()
        if root.exists() and (not root.is_dir() or any(root.iterdir())):
            raise ProjectExistsError(f"{root} already exists and is not empty; nothing was changed")

        now = utc_now()
        metadata = ProjectMetadata(
            id=new_project_id(),
            slug=slug,
            title=title or name,
            kind=kind or defaults.kind,
            description=description,
            language=defaults.language,
            created_at=now,
            updated_at=now,
            studio_version=__version__,
        )
        project_settings = ProjectSettings(
            render_profile=profile, preview_profile=defaults.preview_profile
        )

        root.mkdir(parents=True, exist_ok=True)
        for rel in REQUIRED_DIRS:
            (root / rel).mkdir(parents=True, exist_ok=True)
        write_text_atomic(root / PROJECT_FILE, model_to_yaml(metadata))
        write_text_atomic(root / SETTINGS_FILE, model_to_yaml(project_settings))
        write_text_atomic(root / STORY_FILE, _story_placeholder(metadata))
        write_text_atomic(root / STORYBOARD_FILE, _storyboard_placeholder(metadata))
        write_text_atomic(root / README_FILE, _project_readme(metadata, project_settings))
        AssetRegistry.create(root / REGISTRY_FILE, metadata.id)
        # Keep empty folders in git so a fresh clone still validates.
        for rel in REQUIRED_DIRS:
            directory = root / rel
            if not any(directory.iterdir()):
                (directory / ".gitkeep").touch()
        return cls(root=root, metadata=metadata, settings=project_settings)

    def touch(self) -> None:
        """Update ``updated_at`` and save project.yaml."""
        self.metadata.updated_at = utc_now()
        write_text_atomic(self.root / PROJECT_FILE, model_to_yaml(self.metadata))


# --- validation ----------------------------------------------------------------------------


def validate_project(root: Path, settings: Settings) -> ValidationReport:
    """Check a project folder and return every problem found (never raises for bad data)."""
    from studio.core.assets import validate_assets  # local import: assets imports project

    root = root.resolve()
    report = ValidationReport(subject=str(root))

    report.checks += 1
    if not root.is_dir():
        report.error("PRJ000", "project directory does not exist", str(root))
        return report
    if not (root / PROJECT_FILE).is_file():
        report.error(
            "PRJ001", f"missing {PROJECT_FILE}: this is not a studio project", PROJECT_FILE
        )
        return report

    metadata: ProjectMetadata | None = None
    report.checks += 1
    try:
        metadata = load_model(ProjectMetadata, root / PROJECT_FILE)
    except (SchemaValidationError, ConfigError) as exc:
        report.error("PRJ002", str(exc), PROJECT_FILE)

    project_settings: ProjectSettings | None = None
    report.checks += 1
    if not (root / SETTINGS_FILE).is_file():
        report.error("PRJ003", f"missing {SETTINGS_FILE}", SETTINGS_FILE)
    else:
        try:
            project_settings = load_model(ProjectSettings, root / SETTINGS_FILE)
        except (SchemaValidationError, ConfigError) as exc:
            report.error("PRJ003", str(exc), SETTINGS_FILE)

    for rel in REQUIRED_DIRS:
        report.checks += 1
        if not (root / rel).is_dir():
            report.error("PRJ004", "required directory is missing", rel + "/")

    if project_settings is not None:
        for label, name in (
            ("render_profile", project_settings.render_profile),
            ("preview_profile", project_settings.preview_profile),
        ):
            report.checks += 1
            if name not in settings.render_profiles.profiles:
                report.error(
                    "PRJ005", f"{label} {name!r} is not a known render profile", SETTINGS_FILE
                )

    for rel in (STORY_FILE, STORYBOARD_FILE):
        report.checks += 1
        path = root / rel
        if not path.is_file():
            report.warning("PRJ006", "placeholder file is missing", rel)
            continue
        try:
            data = read_document(path)
        except ConfigError as exc:
            report.error("PRJ007", str(exc), rel)
            continue
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            report.error("PRJ007", "expected a mapping with schema_version: 1", rel)

    report.checks += 1
    if not (root / README_FILE).is_file():
        report.warning("PRJ008", "project README is missing", README_FILE)

    if metadata is not None:
        if root.name != metadata.slug:
            report.warning(
                "PRJ009",
                f"folder name {root.name!r} differs from slug {metadata.slug!r}",
                PROJECT_FILE,
            )
        validate_assets(root, metadata.id, report)
    return report


# --- placeholder content -------------------------------------------------------------------


def _story_placeholder(meta: ProjectMetadata) -> str:
    header = (
        "# Story placeholder. Story Development (module 1) arrives in a later milestone.\n"
        "# Fill in the logline and acts by hand for now; nothing here is generated.\n"
    )
    body = {
        "schema_version": 1,
        "status": "placeholder",
        "title": meta.title,
        "logline": "",
        "characters": [],
        "acts": [],
    }
    return header + dump_yaml(body)


def _storyboard_placeholder(meta: ProjectMetadata) -> str:
    header = (
        "# Storyboard placeholder. The Storyboard Engine (module 8) arrives in a later milestone.\n"
    )
    body = {"schema_version": 1, "status": "placeholder", "project": meta.id, "shots": []}
    return header + dump_yaml(body)


def _project_readme(meta: ProjectMetadata, settings: ProjectSettings) -> str:
    dirs = "\n".join(f"| `{d}/` | {_DIR_PURPOSE.get(d, '')} |" for d in REQUIRED_DIRS)
    return f"""# {meta.title}

Motion Animation Studio project `{meta.slug}` (`{meta.id}`), kind **{meta.kind.value}**.
Created {meta.created_at.isoformat()} with studio {meta.studio_version}.

This project was created with `studio new`. It contains **no artwork, audio or animation
yet**. The story and storyboard files are placeholders until those modules are built.

## Files

| Path | Purpose |
|---|---|
| `project.yaml` | Project identity and metadata (do not change `id`) |
| `settings.yaml` | Render profile `{settings.render_profile}`, \
preview `{settings.preview_profile}`, provider overrides |
| `assets/registry.json` | Asset registry: IDs, versions, content hashes, provenance, licences |
{dirs}
| `renders/`, `cache/` | Created on demand; never committed |

## Commands

```bash
studio project info {_rel_hint(meta)}
studio project validate {_rel_hint(meta)}
studio asset register {_rel_hint(meta)} path/to/file.svg --category character --name "Hero head"
studio asset list {_rel_hint(meta)}
studio asset validate {_rel_hint(meta)}
```

Binary files (PNG, WAV, MP3 ...) are git-ignored by default. Keep them in object storage,
or record explicit approval before committing one (see docs/DECISIONS/0006).
"""


def _rel_hint(meta: ProjectMetadata) -> str:
    return f"projects/{meta.slug}"


_DIR_PURPOSE = {
    "assets": "Registered asset files",
    "assets/audio": "General audio assets",
    "assets/audio/music": "Music",
    "assets/audio/sfx": "Sound effects",
    "assets/audio/voice": "Dialogue and narration recordings",
    "assets/characters": "Character parts, model sheets, character.yaml",
    "assets/data": "Data assets (rig JSON, curves, alignment)",
    "assets/environments": "Background layers and environment.yaml",
    "assets/fonts": "Fonts (with licence)",
    "assets/other": "Anything else",
    "assets/props": "Props",
    "assets/references": "Private reference material (never third-party video)",
    "assets/textures": "Paper, brush and fill textures",
    "scenes": "Scene files (later milestones)",
    "story": "Story and script",
    "storyboard": "Storyboard and animatic data",
}
