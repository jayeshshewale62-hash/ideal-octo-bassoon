"""Common provider contract.

A provider is one replaceable implementation of an AI capability (image, tts, asr, llm).
Every kind has an abstract interface, a ``disabled`` implementation (selected by ``none``)
and a deterministic ``mock`` implementation for tests. Real local or cloud providers are
added in later milestones without changing callers.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, ClassVar

from studio.core.exceptions import ProviderUnavailableError
from studio.core.schemas import ProviderKind


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    kind: ProviderKind
    description: str
    capabilities: frozenset[str] = frozenset()
    local: bool = True  # runs on this machine (or a node you control)
    requires_network: bool = False
    requires_gpu: bool = False
    deterministic: bool = False
    credentials_env: tuple[str, ...] = ()
    status: str = "available"  # "available" | "planned"
    planned_milestone: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "status": self.status,
            "description": self.description,
            "capabilities": sorted(self.capabilities),
            "local": self.local,
            "requires_network": self.requires_network,
            "requires_gpu": self.requires_gpu,
            "deterministic": self.deterministic,
            "credentials_env": list(self.credentials_env),
            "planned_milestone": self.planned_milestone,
        }


class Provider(ABC):
    """Base class shared by every provider kind."""

    kind: ClassVar[ProviderKind]
    info: ClassVar[ProviderInfo]

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self.options: dict[str, Any] = dict(options or {})

    @property
    def name(self) -> str:
        return self.info.name

    @property
    def enabled(self) -> bool:
        return True

    def capabilities(self) -> frozenset[str]:
        return self.info.capabilities

    def supports(self, capability: str) -> bool:
        return capability in self.info.capabilities

    def provenance(self, **extra: Any) -> dict[str, Any]:
        """Base provenance stored with any generated asset (see AIProvenance)."""
        return {"provider": self.info.name, "kind": self.kind.value, **extra}


class DisabledMixin:
    """Behaviour of the ``none`` provider: reports itself disabled, refuses every call."""

    kind: ClassVar[ProviderKind]

    @property
    def enabled(self) -> bool:
        return False

    def _refuse(self) -> ProviderUnavailableError:
        return ProviderUnavailableError(
            f"the {self.kind.value} provider is disabled (provider: none). "
            f"Select 'mock' or a real provider for '{self.kind.value}' in config/providers.yaml "
            "or the project's settings.yaml"
        )


@dataclass(frozen=True)
class GenerationContext:
    """Optional metadata passed along with requests (project, shot, cache key ...)."""

    project_id: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
