"""Language-model assistance providers (used by module 1, Story Development).

The pipeline must work from hand-written scripts with no LLM at all, so ``none`` is a
fully supported setting.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from studio.core.exceptions import ProviderError
from studio.core.hashing import hash_data
from studio.core.schemas import ProviderKind
from studio.providers.base import DisabledMixin, Provider, ProviderInfo


@dataclass(frozen=True)
class TextRequest:
    prompt: str
    system: str = ""
    max_tokens: int = 1024
    temperature: float = 0.0


@dataclass(frozen=True)
class TextResult:
    text: str
    provenance: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Provider):
    kind: ClassVar[ProviderKind] = ProviderKind.LLM

    @abstractmethod
    def complete(self, request: TextRequest) -> TextResult: ...


class DisabledLLMProvider(DisabledMixin, LLMProvider):
    info = ProviderInfo("none", ProviderKind.LLM, "Language-model assistance disabled")

    def complete(self, request: TextRequest) -> TextResult:
        raise self._refuse()


class MockLLMProvider(LLMProvider):
    """Returns a fixed, clearly-labelled response derived from the prompt hash."""

    info = ProviderInfo(
        "mock",
        ProviderKind.LLM,
        "Deterministic labelled echo for tests (no model, no network)",
        capabilities=frozenset({"text_generation"}),
        deterministic=True,
    )

    def complete(self, request: TextRequest) -> TextResult:
        if not request.prompt.strip():
            raise ProviderError("prompt is empty")
        if request.max_tokens < 1:
            raise ProviderError("max_tokens must be at least 1")
        digest = hash_data({"prompt": request.prompt, "system": request.system})[7:15]
        first_line = request.prompt.strip().splitlines()[0][:80]
        return TextResult(
            text=f"[mock-llm {digest}] {first_line}",
            provenance=self.provenance(model="mock-echo"),
        )


__all__ = ["DisabledLLMProvider", "LLMProvider", "MockLLMProvider", "TextRequest", "TextResult"]
