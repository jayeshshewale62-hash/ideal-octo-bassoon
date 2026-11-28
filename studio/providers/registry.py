"""Provider catalogue and configuration-driven selection.

``get_provider`` resolves a :class:`ProviderSelection` (from config/providers.yaml or a
project's settings.yaml) to a provider instance:

* unknown name                     -> ProviderNotFoundError
* ``none``                         -> a disabled provider (``enabled`` is False; calls raise)
* ``planned`` (not implemented)    -> ProviderUnavailableError naming the milestone
* needs network, network disabled  -> ProviderUnavailableError
* required env vars missing        -> MissingCredentialsError (names only, never values)

Credentials are only ever read from environment variables, never from config files.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from studio.core.exceptions import (
    MissingCredentialsError,
    ProviderNotFoundError,
    ProviderUnavailableError,
)
from studio.core.schemas import ProviderKind, ProvidersConfig, ProviderSelection
from studio.providers.asr import DisabledASRProvider, MockASRProvider
from studio.providers.base import Provider, ProviderInfo
from studio.providers.image import DisabledImageProvider, MockImageProvider
from studio.providers.llm import DisabledLLMProvider, MockLLMProvider
from studio.providers.tts import DisabledTTSProvider, MockTTSProvider

Factory = Callable[[dict[str, Any]], Provider]


@dataclass(frozen=True)
class ProviderSpec:
    info: ProviderInfo
    factory: Factory | None  # None -> planned, not implemented yet


_CATALOG: dict[ProviderKind, dict[str, ProviderSpec]] = {kind: {} for kind in ProviderKind}


def register_provider(info: ProviderInfo, factory: Factory | None) -> None:
    """Add a provider to the catalogue (later milestones and tests use this)."""
    if info.status == "planned" and factory is not None:
        raise ValueError("a planned provider cannot have a factory")
    if info.status == "available" and factory is None:
        raise ValueError("an available provider needs a factory")
    _CATALOG[info.kind][info.name] = ProviderSpec(info, factory)


def unregister_provider(kind: ProviderKind, name: str) -> None:
    _CATALOG[kind].pop(name, None)


def _planned(
    kind: ProviderKind,
    name: str,
    description: str,
    milestone: int,
    *,
    local: bool,
    gpu: bool = False,
    credentials: tuple[str, ...] = (),
    capabilities: frozenset[str] = frozenset(),
) -> None:
    register_provider(
        ProviderInfo(
            name=name,
            kind=kind,
            description=description,
            capabilities=capabilities,
            local=local,
            requires_network=not local,
            requires_gpu=gpu,
            credentials_env=credentials,
            status="planned",
            planned_milestone=milestone,
        ),
        None,
    )


def _builtin() -> None:
    for disabled, mock in (
        (DisabledImageProvider, MockImageProvider),
        (DisabledTTSProvider, MockTTSProvider),
        (DisabledASRProvider, MockASRProvider),
        (DisabledLLMProvider, MockLLMProvider),
    ):
        register_provider(disabled.info, disabled)
        register_provider(mock.info, mock)

    img, tts, asr, llm = ProviderKind.IMAGE, ProviderKind.TTS, ProviderKind.ASR, ProviderKind.LLM
    _planned(
        img,
        "comfyui",
        "Local SDXL/Flux via a ComfyUI API on a GPU render node",
        9,
        local=True,
        gpu=True,
        capabilities=frozenset({"text_to_image", "seed_control", "reference_images"}),
    )
    _planned(
        img,
        "cloud-image",
        "Generic hosted image API adapter (optional, paid)",
        9,
        local=False,
        credentials=("STUDIO_IMAGE_API_KEY",),
        capabilities=frozenset({"text_to_image"}),
    )
    _planned(
        tts,
        "kokoro",
        "Kokoro-82M local TTS (Apache-2.0); weights need an approved download",
        4,
        local=True,
        capabilities=frozenset({"text_to_speech", "multi_voice"}),
    )
    _planned(
        tts,
        "recorded",
        "Recorded human voice-over imported as audio assets",
        4,
        local=True,
        capabilities=frozenset({"text_to_speech"}),
    )
    _planned(
        tts,
        "cloud-tts",
        "Generic hosted TTS adapter (optional, paid)",
        9,
        local=False,
        credentials=("STUDIO_TTS_API_KEY",),
        capabilities=frozenset({"text_to_speech", "multi_voice"}),
    )
    _planned(
        asr,
        "whisper",
        "faster-whisper word timestamps on CPU; weights need an approved download",
        4,
        local=True,
        capabilities=frozenset({"transcription", "word_timestamps", "forced_alignment"}),
    )
    _planned(
        asr,
        "parakeet",
        "Parakeet TDT via sherpa-onnx (legacy branch approach)",
        4,
        local=True,
        capabilities=frozenset({"transcription", "word_timestamps", "forced_alignment"}),
    )
    _planned(
        llm,
        "anthropic",
        "Claude via the Anthropic API (optional, paid)",
        9,
        local=False,
        credentials=("ANTHROPIC_API_KEY",),
        capabilities=frozenset({"text_generation"}),
    )


_builtin()


def list_providers(kind: ProviderKind | None = None) -> list[ProviderInfo]:
    kinds = [kind] if kind else list(ProviderKind)
    return [spec.info for k in kinds for _, spec in sorted(_CATALOG[k].items())]


def provider_info(kind: ProviderKind, name: str) -> ProviderInfo:
    try:
        return _CATALOG[kind][name].info
    except KeyError:
        known = ", ".join(sorted(_CATALOG[kind]))
        raise ProviderNotFoundError(
            f"unknown {kind.value} provider {name!r} (known: {known})"
        ) from None


def get_provider(
    kind: ProviderKind,
    selection: ProviderSelection,
    *,
    allow_network: bool = False,
    environ: Mapping[str, str] | None = None,
) -> Provider:
    info = provider_info(kind, selection.provider)
    spec = _CATALOG[kind][selection.provider]
    if spec.factory is None:
        raise ProviderUnavailableError(
            f"{kind.value} provider {info.name!r} is planned for milestone "
            f"{info.planned_milestone} and is not implemented yet"
        )
    if info.requires_network and not allow_network:
        raise ProviderUnavailableError(
            f"{kind.value} provider {info.name!r} needs network access, but allow_network is "
            "false in config/providers.yaml"
        )
    env = os.environ if environ is None else environ
    required = list(dict.fromkeys([*info.credentials_env, *selection.credentials_env]))
    missing = [name for name in required if not env.get(name)]
    if missing:
        raise MissingCredentialsError(
            f"{kind.value} provider {info.name!r} needs environment variable(s) "
            f"{', '.join(missing)}; set them in your shell or secret store, never in config files"
        )
    return spec.factory(dict(selection.options))


def resolve_selection(
    kind: ProviderKind,
    studio_providers: ProvidersConfig,
    project_overrides: Mapping[ProviderKind, ProviderSelection] | None = None,
) -> ProviderSelection:
    """Project settings override the studio-wide selection for the same kind."""
    if project_overrides and kind in project_overrides:
        return project_overrides[kind]
    return studio_providers.selection(kind)


def provider_status(
    kind: ProviderKind,
    selection: ProviderSelection,
    *,
    allow_network: bool = False,
    environ: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    """(state, detail) for display: state is enabled / disabled / unavailable / error."""
    try:
        provider = get_provider(kind, selection, allow_network=allow_network, environ=environ)
    except ProviderNotFoundError as exc:
        return "error", str(exc)
    except (ProviderUnavailableError, MissingCredentialsError) as exc:
        return "unavailable", str(exc)
    if not provider.enabled:
        return "disabled", "provider: none"
    return "enabled", provider.info.description
