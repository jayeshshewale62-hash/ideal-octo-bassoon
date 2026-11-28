"""AI provider layer: replaceable implementations behind stable interfaces.

Kinds: ``image`` (module 10), ``tts`` (module 11), ``asr`` (alignment for modules 5/11),
``llm`` (module 1). Every kind ships ``none`` (disabled, default) and ``mock``
(deterministic, offline). Real providers are registered as *planned* until a later
milestone implements them.
"""

from __future__ import annotations

from studio.providers.base import Provider, ProviderInfo
from studio.providers.registry import (
    get_provider,
    list_providers,
    provider_info,
    provider_status,
    register_provider,
    resolve_selection,
    unregister_provider,
)

__all__ = [
    "Provider",
    "ProviderInfo",
    "get_provider",
    "list_providers",
    "provider_info",
    "provider_status",
    "register_provider",
    "resolve_selection",
    "unregister_provider",
]
