"""Exception hierarchy.

Every error raised deliberately by the studio derives from :class:`StudioError`, so the
CLI can turn it into a readable message and a non-zero exit code instead of a traceback.
"""

from __future__ import annotations


class StudioError(Exception):
    """Base class for all expected, user-facing studio errors."""


# --- configuration and schemas -------------------------------------------------------


class ConfigError(StudioError):
    """A configuration file is missing, unreadable or invalid."""


class SchemaValidationError(StudioError):
    """Data failed schema validation. ``problems`` holds one readable line per error."""

    def __init__(self, source: str, problems: list[str]) -> None:
        self.source = source
        self.problems = problems
        lines = "\n".join(f"  - {p}" for p in problems)
        super().__init__(f"{source} is not valid:\n{lines}")


# --- paths -----------------------------------------------------------------------------


class PathSafetyError(StudioError):
    """A path escapes its allowed root (absolute path, '..', or a symlink pointing outside)."""


# --- projects --------------------------------------------------------------------------


class ProjectError(StudioError):
    """Generic project problem."""


class ProjectNotFoundError(ProjectError):
    """The directory is not a studio project (no project.yaml)."""


class ProjectExistsError(ProjectError):
    """Refusing to create a project where one (or any other content) already exists."""


# --- assets ----------------------------------------------------------------------------


class AssetError(StudioError):
    """Generic asset problem."""


class AssetNotFoundError(AssetError):
    """No asset with that ID is registered, or its file is missing."""


class DuplicateAssetError(AssetError):
    """Identical content (same content hash) is already registered."""

    def __init__(self, message: str, existing_id: str) -> None:
        self.existing_id = existing_id
        super().__init__(message)


class InvalidAssetError(AssetError):
    """The file's format is unsupported, or its content does not match its extension."""


class AssetConflictError(AssetError):
    """Registration would overwrite a different existing file."""


# --- providers -------------------------------------------------------------------------


class ProviderError(StudioError):
    """Generic provider problem."""


class ProviderNotFoundError(ProviderError):
    """No provider with that name exists for the requested kind."""


class ProviderUnavailableError(ProviderError):
    """The provider is disabled ('none'), not implemented yet, or cannot run here."""


class MissingCredentialsError(ProviderError):
    """The provider needs credentials (environment variables) that are not set."""


# --- characters and rigs (Milestone 3) ---------------------------------------------------


class CharacterError(StudioError):
    """A character definition is missing, invalid, or an operation on it is refused."""


class CharacterExistsError(CharacterError):
    """Refusing to create a character whose ID is already used in the project."""


class RigError(StudioError):
    """A rig cannot be evaluated (structural problem) or a rig operation is invalid."""


# --- faces and lip-sync (Milestone 4) ----------------------------------------------------


class FaceError(StudioError):
    """A facial rig, expression, viseme or lip-sync operation is invalid."""


class LipSyncError(FaceError):
    """Phoneme/viseme events or a lip-sync track are invalid. ``problems`` lists them."""

    def __init__(self, message: str, problems: list[str] | None = None) -> None:
        self.problems = problems or []
        detail = "".join(f"\n  - {p}" for p in self.problems)
        super().__init__(message + detail)
