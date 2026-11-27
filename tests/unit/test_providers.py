from __future__ import annotations

import io
import wave

import pytest

from studio.core.exceptions import (
    MissingCredentialsError,
    ProviderError,
    ProviderNotFoundError,
    ProviderUnavailableError,
)
from studio.core.schemas import ProviderKind, ProvidersConfig, ProviderSelection
from studio.providers import (
    get_provider,
    list_providers,
    provider_status,
    register_provider,
    resolve_selection,
    unregister_provider,
)
from studio.providers.asr import AlignmentRequest
from studio.providers.base import ProviderInfo
from studio.providers.image import ImageRequest
from studio.providers.llm import TextRequest
from studio.providers.tts import MockTTSProvider, SpeechRequest

MOCK = ProviderSelection(provider="mock")
NONE = ProviderSelection(provider="none")


def test_every_kind_has_none_and_mock() -> None:
    for kind in ProviderKind:
        names = {p.name for p in list_providers(kind)}
        assert {"none", "mock"} <= names


def test_mock_image_is_deterministic_png() -> None:
    p = get_provider(ProviderKind.IMAGE, MOCK)
    a = p.generate(ImageRequest("a quiet forest", width=8, height=6, seed=3))
    b = p.generate(ImageRequest("a quiet forest", width=8, height=6, seed=3))
    c = p.generate(ImageRequest("a quiet forest", width=8, height=6, seed=4))
    assert a.png == b.png != c.png
    assert a.png.startswith(b"\x89PNG\r\n\x1a\n")
    assert (a.width, a.height) == (8, 6)
    assert a.provenance["provider"] == "mock" and a.provenance["seed"] == 3
    assert p.supports("text_to_image") and not p.supports("reference_images")
    with pytest.raises(ProviderError, match="empty"):
        p.generate(ImageRequest("  "))
    with pytest.raises(ProviderError, match="size"):
        p.generate(ImageRequest("x", width=0))


def test_mock_tts_and_asr_roundtrip() -> None:
    tts = get_provider(ProviderKind.TTS, MOCK)
    speech = tts.synthesize(SpeechRequest("one two three four five", sample_rate=16000))
    assert speech.duration_s == pytest.approx(2.0)
    with wave.open(io.BytesIO(speech.wav)) as w:
        assert w.getframerate() == 16000 and w.getnframes() == 32000
    asr = get_provider(ProviderKind.ASR, MOCK)
    result = asr.align(AlignmentRequest(speech.wav, "one two three four five"))
    assert [w.word for w in result.words] == ["one", "two", "three", "four", "five"]
    starts = [w.start for w in result.words]
    assert starts == sorted(starts) and result.words[-1].end <= result.duration_s
    for bad in ("", "   "):
        with pytest.raises(ProviderError):
            tts.synthesize(SpeechRequest(bad))
    with pytest.raises(ProviderError, match="WAV"):
        asr.align(AlignmentRequest(b"not audio", "x"))
    with pytest.raises(ProviderError, match="sample rate"):
        tts.synthesize(SpeechRequest("hi", sample_rate=11))


def test_mock_llm() -> None:
    llm = get_provider(ProviderKind.LLM, MOCK)
    out = llm.complete(TextRequest("Write a logline\nabout a fox"))
    assert out.text.startswith("[mock-llm ") and "Write a logline" in out.text
    assert out.text == llm.complete(TextRequest("Write a logline\nabout a fox")).text
    with pytest.raises(ProviderError):
        llm.complete(TextRequest(""))


@pytest.mark.parametrize(
    ("kind", "call"),
    [
        (ProviderKind.IMAGE, lambda p: p.generate(ImageRequest("x"))),
        (ProviderKind.TTS, lambda p: p.synthesize(SpeechRequest("x"))),
        (ProviderKind.ASR, lambda p: p.align(AlignmentRequest(b"", "x"))),
        (ProviderKind.LLM, lambda p: p.complete(TextRequest("x"))),
    ],
)
def test_disabled_providers_refuse(kind, call) -> None:
    provider = get_provider(kind, NONE)
    assert provider.enabled is False
    with pytest.raises(ProviderUnavailableError, match="disabled"):
        call(provider)


def test_unknown_provider() -> None:
    with pytest.raises(ProviderNotFoundError, match="known: "):
        get_provider(ProviderKind.TTS, ProviderSelection(provider="magic-voice"))


def test_planned_provider_unavailable() -> None:
    with pytest.raises(ProviderUnavailableError, match="milestone 4"):
        get_provider(ProviderKind.TTS, ProviderSelection(provider="kokoro"))


@pytest.fixture
def cloud_provider():
    info = ProviderInfo(
        "fake-cloud",
        ProviderKind.LLM,
        "test only",
        local=False,
        requires_network=True,
        credentials_env=("FAKE_CLOUD_KEY",),
    )
    register_provider(info, lambda options: MockTTSProvider(options))
    yield info
    unregister_provider(ProviderKind.LLM, "fake-cloud")


def test_network_provider_blocked_when_network_disabled(cloud_provider) -> None:
    with pytest.raises(ProviderUnavailableError, match="allow_network"):
        get_provider(ProviderKind.LLM, ProviderSelection(provider="fake-cloud"), environ={})


def test_missing_credentials(cloud_provider) -> None:
    sel = ProviderSelection(provider="fake-cloud", credentials_env=["EXTRA_TOKEN_NAME"])
    with pytest.raises(MissingCredentialsError) as err:
        get_provider(ProviderKind.LLM, sel, allow_network=True, environ={"FAKE_CLOUD_KEY": ""})
    assert "FAKE_CLOUD_KEY" in str(err.value) and "EXTRA_TOKEN_NAME" in str(err.value)
    env = {"FAKE_CLOUD_KEY": "k", "EXTRA_TOKEN_NAME": "t"}
    assert get_provider(ProviderKind.LLM, sel, allow_network=True, environ=env) is not None


def test_credentials_values_never_in_error(cloud_provider) -> None:
    with pytest.raises(MissingCredentialsError) as err:
        get_provider(
            ProviderKind.LLM,
            ProviderSelection(provider="fake-cloud", credentials_env=["OTHER_KEY"]),
            allow_network=True,
            environ={"FAKE_CLOUD_KEY": "super-secret-value"},
        )
    assert "super-secret-value" not in str(err.value)


def test_registry_guards() -> None:
    with pytest.raises(ValueError, match="planned"):
        register_provider(
            ProviderInfo("x", ProviderKind.LLM, "d", status="planned"), lambda o: MockTTSProvider(o)
        )
    with pytest.raises(ValueError, match="factory"):
        register_provider(ProviderInfo("x", ProviderKind.LLM, "d"), None)


def test_status_and_project_override() -> None:
    studio = ProvidersConfig()
    assert provider_status(ProviderKind.TTS, studio.tts) == ("disabled", "provider: none")
    override = {ProviderKind.TTS: MOCK}
    selection = resolve_selection(ProviderKind.TTS, studio, override)
    assert selection.provider == "mock"
    assert provider_status(ProviderKind.TTS, selection)[0] == "enabled"
    assert resolve_selection(ProviderKind.IMAGE, studio, override).provider == "none"
    assert (
        provider_status(ProviderKind.TTS, ProviderSelection(provider="kokoro"))[0] == "unavailable"
    )
    assert provider_status(ProviderKind.TTS, ProviderSelection(provider="zzz"))[0] == "error"


def test_mock_options_are_copied() -> None:
    opts = {"style": "ink"}
    p = get_provider(ProviderKind.IMAGE, ProviderSelection(provider="mock", options=opts))
    p.options["style"] = "changed"
    assert opts == {"style": "ink"}
