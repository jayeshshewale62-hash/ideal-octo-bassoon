"""Readable validation: file loading, schema parsing and validation reports."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from studio.core.exceptions import ConfigError, SchemaValidationError


def format_errors(error: ValidationError) -> list[str]:
    """One line per problem: ``field.path: message``."""
    lines = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "(document)"
        message = item["msg"].removeprefix("Value error, ")
        if item["type"] == "extra_forbidden":
            message = "unknown field (check the spelling)"
        elif item["type"] == "missing":
            message = "required field is missing"
        lines.append(f"{location}: {message}")
    return lines


def parse_model[M: BaseModel](model: type[M], data: Any, source: str) -> M:
    """Validate ``data`` against ``model``.

    Raises :class:`SchemaValidationError` listing one readable line per problem.
    """
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise SchemaValidationError(
            source, [f"expected a mapping at the top level, got {type(data).__name__}"]
        )
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise SchemaValidationError(source, format_errors(exc)) from None


def read_document(path: Path) -> Any:
    """Load a YAML or JSON file. YAML is parsed with ``safe_load`` (no arbitrary objects)."""
    if not path.is_file():
        raise ConfigError(f"file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from None
    try:
        if path.suffix.lower() == ".json":
            return json.loads(text)
        return yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ConfigError(f"{path} is not valid {path.suffix.lstrip('.').upper()}: {exc}") from None


def load_model[M: BaseModel](model: type[M], path: Path) -> M:
    return parse_model(model, read_document(path), str(path))


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)


def model_to_yaml(model: BaseModel) -> str:
    return dump_yaml(model.model_dump(mode="json"))


def model_to_json(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def write_text_atomic(path: Path, text: str) -> None:
    """Write via a temporary file and rename, so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# --- reports ------------------------------------------------------------------------------


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    severity: Severity
    code: str
    message: str
    location: str = ""

    def __str__(self) -> str:
        where = f" [{self.location}]" if self.location else ""
        return f"{self.severity.value.upper()} {self.code}{where}: {self.message}"


@dataclass
class ValidationReport:
    subject: str
    issues: list[Issue] = field(default_factory=list)
    checks: int = 0

    def error(self, code: str, message: str, location: str = "") -> None:
        self.issues.append(Issue(Severity.ERROR, code, message, location))

    def warning(self, code: str, message: str, location: str = "") -> None:
        self.issues.append(Issue(Severity.WARNING, code, message, location))

    def extend(self, other: ValidationReport) -> None:
        self.issues.extend(other.issues)
        self.checks += other.checks

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def codes(self) -> set[str]:
        return {i.code for i in self.issues}

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "ok": self.ok,
            "checks": self.checks,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "issues": [
                {
                    "severity": i.severity.value,
                    "code": i.code,
                    "message": i.message,
                    "location": i.location,
                }
                for i in self.issues
            ],
        }
