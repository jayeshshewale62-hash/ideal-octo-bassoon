"""Speech recognition / forced-alignment providers (used by modules 5, 11 and captions).

Planned local options: Whisper (faster-whisper / whisper.cpp) and Parakeet via sherpa-onnx
(the approach used by legacy branch ``ccr-f3c28d1b-6ialqh``). Both need model weights,
which are not downloaded in this milestone.
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


@dataclass(frozen=True)
class WordTiming:
    word: str
    start: float
    end: float


@dataclass(frozen=True)
class AlignmentRequest:
    wav: bytes
    transcript: str
    language: str = "en"


@dataclass(frozen=True)
class AlignmentResult:
    words: list[WordTiming]
    duration_s: float
    provenance: dict[str, Any] = field(default_factory=dict)


class ASRProvider(Provider):
    kind: ClassVar[ProviderKind] = ProviderKind.ASR

    @abstractmethod
    def align(self, request: AlignmentRequest) -> AlignmentResult: ...


class DisabledASRProvider(DisabledMixin, ASRProvider):
    info = ProviderInfo("none", ProviderKind.ASR, "Speech alignment disabled")

    def align(self, request: AlignmentRequest) -> AlignmentResult:
        raise self._refuse()


def wav_duration(data: bytes) -> float:
    try:
        with wave.open(io.BytesIO(data), "rb") as reader:
            return reader.getnframes() / reader.getframerate()
    except (wave.Error, EOFError) as exc:
        raise ProviderError(f"audio is not a readable PCM WAV: {exc}") from None


class MockASRProvider(ASRProvider):
    """Spreads the transcript's words over the audio, weighted by word length."""

    info = ProviderInfo(
        "mock",
        ProviderKind.ASR,
        "Deterministic proportional alignment (no model, no network)",
        capabilities=frozenset({"forced_alignment", "word_timestamps"}),
        deterministic=True,
    )

    def align(self, request: AlignmentRequest) -> AlignmentResult:
        words = request.transcript.split()
        if not words:
            raise ProviderError("transcript is empty; the mock aligner needs the script text")
        duration = wav_duration(request.wav)
        if duration <= 0:
            raise ProviderError("audio has no samples")
        weights = [len(w) + 1 for w in words]
        total = sum(weights)
        timings: list[WordTiming] = []
        cursor = 0.0
        for word, weight in zip(words, weights, strict=True):
            span = duration * weight / total
            timings.append(WordTiming(word, round(cursor, 4), round(cursor + span * 0.9, 4)))
            cursor += span
        return AlignmentResult(
            words=timings,
            duration_s=round(duration, 6),
            provenance=self.provenance(model="mock-proportional"),
        )


__all__ = [
    "ASRProvider",
    "AlignmentRequest",
    "AlignmentResult",
    "DisabledASRProvider",
    "MockASRProvider",
    "WordTiming",
    "wav_duration",
]
