"""Bridge between alignment providers (``studio.providers.asr``) and lip-sync data.

* :func:`document_from_result` turns a provider :class:`AlignmentResult` into a
  versioned :class:`AlignmentDocument` (the "audio alignment result" file).
* :func:`align_audio` runs the configured ``asr`` provider. With the default ``none``
  provider it refuses safely; ``mock`` gives word timings only. No provider is activated,
  no model is downloaded and no network is used.
* :func:`phoneme_events` extracts phoneme timings for mapping. It fails clearly (LIP008)
  when an alignment has none, instead of guessing them.
"""

from __future__ import annotations

from collections.abc import Mapping

from studio.core.exceptions import LipSyncError, ProviderUnavailableError
from studio.core.schemas import ProviderKind, ProviderSelection, utc_now
from studio.face.schemas import (
    AlignmentDocument,
    AlignmentSource,
    PhonemeEvent,
    WordEvent,
)
from studio.providers.asr import AlignmentRequest, AlignmentResult, ASRProvider
from studio.providers.registry import get_provider

PHONEME_CAPABILITY = "phoneme_timestamps"


def document_from_result(
    result: AlignmentResult, *, transcript: str = "", language: str = "en"
) -> AlignmentDocument:
    prov = result.provenance
    return AlignmentDocument(
        source=AlignmentSource(
            provider=str(prov.get("provider", "unknown")),
            model=str(prov.get("model", "")),
            created_at=utc_now(),
        ),
        language=language,
        duration=result.duration_s,
        transcript=transcript,
        words=[WordEvent(word=w.word, start=w.start, end=w.end) for w in result.words],
        phonemes=[
            PhonemeEvent(
                phoneme=p.phoneme,
                start=p.start,
                end=p.end,
                confidence=p.confidence,
                word_index=p.word_index,
                language=language,
            )
            for p in result.phonemes
        ],
    )


def align_audio(
    selection: ProviderSelection,
    wav: bytes,
    transcript: str,
    *,
    language: str = "en",
    allow_network: bool = False,
    environ: Mapping[str, str] | None = None,
    require_phonemes: bool = False,
) -> AlignmentDocument:
    provider = get_provider(
        ProviderKind.ASR, selection, allow_network=allow_network, environ=environ
    )
    assert isinstance(provider, ASRProvider)
    if not provider.enabled:
        raise ProviderUnavailableError(
            "audio alignment is disabled (asr provider: none); provide an alignment file "
            "or configure an alignment provider"
        )
    if require_phonemes and not provider.supports(PHONEME_CAPABILITY):
        raise ProviderUnavailableError(
            f"asr provider {provider.name!r} does not provide phoneme timestamps "
            f"(capabilities: {', '.join(sorted(provider.capabilities())) or 'none'})"
        )
    result = provider.align(AlignmentRequest(wav=wav, transcript=transcript, language=language))
    return document_from_result(result, transcript=transcript, language=language)


def phoneme_events(doc: AlignmentDocument) -> list[PhonemeEvent]:
    if not doc.phonemes:
        raise LipSyncError(
            "alignment has no phoneme timestamps; lip-sync needs phoneme-level alignment",
            [
                "LIP008 word-only alignments are not converted to visemes (timings are never "
                "invented)"
            ],
        )
    return list(doc.phonemes)


def summarize(doc: AlignmentDocument) -> dict[str, object]:
    phon_end = doc.phonemes[-1].end if doc.phonemes else None
    word_end = doc.words[-1].end if doc.words else None
    return {
        "provider": doc.source.provider,
        "model": doc.source.model,
        "language": doc.language,
        "duration": doc.duration,
        "words": len(doc.words),
        "phonemes": len(doc.phonemes),
        "last_word_end": word_end,
        "last_phoneme_end": phon_end,
        "transcript": doc.transcript[:120],
    }
