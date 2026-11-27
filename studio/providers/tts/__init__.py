"""Text-to-speech providers (module 11).

Planned local default: Kokoro (needs model weights, which are not downloaded in this
milestone). Recorded human voice-over remains a first-class alternative.
"""

from __future__ import annotations

import io
import wave
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from studio.core.exceptions import ProviderError
from studio.core.schemas import ProviderKind
from studio.providers.base import DisabledMixin, Provider, ProviderInfo

MOCK_WORDS_PER_SECOND = 2.5


@dataclass(frozen=True)
class SpeechRequest:
    text: str
    voice: str = "default"
    sample_rate: int = 48000
    speed: float = 1.0


@dataclass(frozen=True)
class SpeechResult:
    wav: bytes
    sample_rate: int
    duration_s: float
    provenance: dict[str, Any] = field(default_factory=dict)


class TTSProvider(Provider):
    kind: ClassVar[ProviderKind] = ProviderKind.TTS

    @abstractmethod
    def synthesize(self, request: SpeechRequest) -> SpeechResult: ...


class DisabledTTSProvider(DisabledMixin, TTSProvider):
    info = ProviderInfo("none", ProviderKind.TTS, "Speech synthesis disabled")

    def synthesize(self, request: SpeechRequest) -> SpeechResult:
        raise self._refuse()


def silent_wav(duration_s: float, sample_rate: int) -> bytes:
    frames = round(duration_s * sample_rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(b"\x00\x00" * frames)
    return buffer.getvalue()


class MockTTSProvider(TTSProvider):
    """Silent mono WAV whose length follows the word count (2.5 words/s at speed 1)."""

    info = ProviderInfo(
        "mock",
        ProviderKind.TTS,
        "Deterministic silent WAV sized to the text (no model, no network)",
        capabilities=frozenset({"text_to_speech"}),
        deterministic=True,
    )

    def synthesize(self, request: SpeechRequest) -> SpeechResult:
        words = request.text.split()
        if not words:
            raise ProviderError("speech text is empty")
        if request.sample_rate not in (16000, 22050, 24000, 44100, 48000):
            raise ProviderError(f"unsupported sample rate {request.sample_rate}")
        if not 0.25 <= request.speed <= 4.0:
            raise ProviderError(f"speed must be 0.25..4.0, got {request.speed}")
        duration = max(0.5, len(words) / (MOCK_WORDS_PER_SECOND * request.speed))
        return SpeechResult(
            wav=silent_wav(duration, request.sample_rate),
            sample_rate=request.sample_rate,
            duration_s=round(duration, 6),
            provenance=self.provenance(model="mock-silence", voice=request.voice),
        )


__all__ = [
    "DisabledTTSProvider",
    "MockTTSProvider",
    "SpeechRequest",
    "SpeechResult",
    "TTSProvider",
    "silent_wav",
]
