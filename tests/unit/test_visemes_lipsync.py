from __future__ import annotations

import io
import math
import wave

import pytest

from studio.core.exceptions import FaceError, LipSyncError, ProviderUnavailableError
from studio.core.schemas import ProviderKind, ProviderSelection
from studio.face.alignment import align_audio, document_from_result, phoneme_events, summarize
from studio.face.expressions import evaluate_expression
from studio.face.library import (
    builtin_expression,
    load_phoneme_map,
    load_viseme_set,
    phoneme_map_names,
)
from studio.face.lipsync import LipSyncEvaluator, apply_lipsync, evaluate_lipsync, validate_track
from studio.face.phonemes import check_timing, map_phonemes, merge_events, normalize
from studio.face.schemas import (
    AlignmentDocument,
    AlignmentSource,
    LipSyncSettings,
    LipSyncTrack,
    PhonemeEvent,
    PhonemeMap,
    VisemeEvent,
    VisemeSet,
)
from studio.providers import register_provider, unregister_provider
from studio.providers.asr import AlignmentResult, ASRProvider, PhonemeTiming, WordTiming
from studio.providers.base import ProviderInfo
from studio.providers.tts import silent_wav

VS = load_viseme_set()
EN = load_phoneme_map()


def ph(*items: tuple[str, float, float]) -> list[PhonemeEvent]:
    return [PhonemeEvent(phoneme=p, start=s, end=e) for p, s, e in items]


def track(events: list[tuple[str, float, float]], **settings: float) -> LipSyncTrack:
    return LipSyncTrack(
        id="t",
        events=[VisemeEvent(viseme=v, start=s, end=e) for v, s, e in events],
        settings=LipSyncSettings(**settings),
    )


# --- visemes and maps ----------------------------------------------------------------------


def test_default_viseme_set_covers_required_shapes() -> None:
    ids = {v.id for v in VS.visemes}
    assert {"rest", "mbp", "ai", "e", "ee", "o", "u", "ch", "st", "fv", "th", "l"} <= ids
    assert VS.get("mbp").values["mouth.open"] == 0  # closed lips
    assert VS.get("ai").values["jaw.open"] > 0.5  # open jaw
    assert VS.get("e").values["mouth.width"] > 1  # wide
    assert VS.get("o").values["mouth.pucker"] > 0  # rounded
    assert VS.get("u").values["mouth.width"] < 1  # narrow
    assert VS.get("st").teeth_visible and VS.get("fv").teeth_visible
    assert VS.get("th").tongue_visible and VS.get("l").tongue_visible
    assert all(v.articulation for v in VS.visemes)


def test_viseme_set_is_editable(tmp_path) -> None:
    data = VS.model_dump()
    data["visemes"][1]["values"]["mouth.open"] = 0.05
    data["id"] = "custom"
    path = tmp_path / "visemes.yaml"
    import yaml

    path.write_text(yaml.safe_dump(data))
    custom = load_viseme_set(str(path))
    assert custom.id == "custom" and custom.get("mbp").values["mouth.open"] == 0.05
    with pytest.raises(ValueError, match="rest viseme"):
        VisemeSet(id="x", rest="nope", visemes=[])
    with pytest.raises(FaceError):
        load_viseme_set("missing.yaml")


def test_phoneme_maps_and_normalization() -> None:
    assert set(phoneme_map_names()) >= {"en_arpabet", "ipa_basic"}
    assert len(EN.map) == 39
    assert normalize("ah1", EN) == "AH" and normalize(" OW0 ", EN) == "OW"
    ipa = load_phoneme_map("ipa_basic")
    assert ipa.language == "mul" and normalize("θ", ipa) == "θ"
    with pytest.raises(FaceError):
        load_phoneme_map("klingon")


def test_english_mapping_and_silence_fill() -> None:
    res = map_phonemes(
        ph(("HH", 0.1, 0.18), ("AH0", 0.18, 0.3), ("L", 0.3, 0.38), ("OW1", 0.38, 0.6)), EN, VS
    )
    assert [(e.viseme, e.start, e.end, e.source) for e in res.events] == [
        ("rest", 0.0, 0.1, "silence"),
        ("k", 0.1, 0.18, "phoneme"),
        ("ai", 0.18, 0.3, "phoneme"),
        ("l", 0.3, 0.38, "phoneme"),
        ("o", 0.38, 0.6, "phoneme"),
    ]
    no_fill = map_phonemes(ph(("M", 0.2, 0.3)), EN, VS, fill_silence=False)
    assert [e.viseme for e in no_fill.events] == ["mbp"]


def test_language_specific_map() -> None:
    ipa = load_phoneme_map("ipa_basic")
    res = map_phonemes(ph(("m", 0, 0.1), ("a", 0.1, 0.3), ("θ", 0.3, 0.4)), ipa, VS)
    assert [e.viseme for e in res.events] == ["mbp", "ai", "th"]


def test_gaps_and_silence_symbols() -> None:
    res = map_phonemes(ph(("M", 0.0, 0.1), ("sil", 0.1, 0.3), ("AA", 0.5, 0.7)), EN, VS)
    assert [(e.viseme, e.start, e.end) for e in res.events] == [
        ("mbp", 0.0, 0.1),
        ("rest", 0.1, 0.5),
        ("ai", 0.5, 0.7),
    ]  # silence + gap merged


def test_adjacent_merge_keeps_phonemes() -> None:
    res = map_phonemes(ph(("P", 0.0, 0.05), ("B", 0.05, 0.1), ("M", 0.1, 0.2)), EN, VS)
    assert len(res.events) == 1 and res.events[0].phonemes == ["P", "B", "M"]
    split = map_phonemes(ph(("P", 0.0, 0.05), ("B", 0.05, 0.1)), EN, VS, merge_adjacent=False)
    assert len(split.events) == 2
    assert merge_events([]) == []


@pytest.mark.parametrize(("policy", "expected"), [("rest", "rest"), ("previous", "mbp")])
def test_unknown_phonemes(policy: str, expected: str) -> None:
    pmap = EN.model_copy(update={"unknown": policy})
    res = map_phonemes(ph(("M", 0, 0.1), ("QX", 0.1, 0.2)), pmap, VS, merge_adjacent=False)
    assert res.events[1].viseme == expected and res.events[1].source == "unknown"
    assert res.unknown == ["QX"] and "LIP005" in res.warnings[0]


def test_unknown_phoneme_error_policy() -> None:
    with pytest.raises(LipSyncError, match="unknown phoneme"):
        map_phonemes(ph(("QX", 0, 0.1)), EN.model_copy(update={"unknown": "error"}), VS)


def test_map_pointing_to_unknown_viseme() -> None:
    bad = PhonemeMap(id="bad", language="en", alphabet="x", map={"A": "nope"})
    with pytest.raises(LipSyncError) as err:
        map_phonemes(ph(("A", 0, 1)), bad, VS)
    assert "LIP009" in str(err.value)


@pytest.mark.parametrize(
    ("events", "code"),
    [
        ((("AA", 0.2, 0.2),), "LIP001"),
        ((("AA", 0.3, 0.2),), "LIP001"),
        ((("AA", 0.0, 0.3), ("M", 0.2, 0.4)), "LIP002"),
        ((("AA", 0.5, 0.6), ("M", 0.1, 0.2)), "LIP003"),
        ((("AA", -0.1, 0.2),), "LIP004"),
        ((("AA", 0.0, math.inf),), "LIP004"),
    ],
)
def test_timing_validation(events, code: str) -> None:
    evs = [PhonemeEvent.model_construct(phoneme=p, start=s, end=e) for p, s, e in events]
    problems = check_timing(evs)
    assert any(p.startswith(code) for p in problems), problems
    with pytest.raises(LipSyncError):
        map_phonemes(evs, EN, VS)


def test_mapping_is_deterministic() -> None:
    evs = ph(
        ("DH", 0.0, 0.05),
        ("AH0", 0.05, 0.1),
        ("K", 0.12, 0.2),
        ("AE1", 0.2, 0.35),
        ("T", 0.35, 0.4),
    )
    assert map_phonemes(evs, EN, VS).events == map_phonemes(evs, EN, VS).events


# --- lip-sync evaluation -------------------------------------------------------------------------


def test_before_after_and_gaps_are_rest() -> None:
    tr = track([("ai", 0.5, 1.0), ("o", 1.5, 2.0)], transition=0.0)
    assert evaluate_lipsync(tr, 0.0, VS).viseme == "rest"
    assert evaluate_lipsync(tr, 1.2, VS).viseme == "rest"
    assert evaluate_lipsync(tr, 2.5, VS).viseme == "rest"
    assert evaluate_lipsync(tr, 2.5, VS).values["mouth.open"] == 0


def test_exact_boundaries_belong_to_later_event() -> None:
    tr = track([("mbp", 0.0, 0.2), ("ai", 0.2, 0.4)], transition=0.0)
    assert evaluate_lipsync(tr, 0.2, VS).viseme == "ai"
    assert evaluate_lipsync(tr, 0.19999, VS).viseme == "mbp"
    assert evaluate_lipsync(tr, 0.4, VS).viseme == "rest"  # end is exclusive


def test_transition_interpolation_is_continuous() -> None:
    tr = track([("mbp", 0.0, 0.2), ("ai", 0.2, 0.6)], transition=0.1, ease="linear")
    ev = LipSyncEvaluator(tr, VS)
    left = ev.evaluate(0.2 - 1e-9).values["mouth.open"]
    at = ev.evaluate(0.2).values["mouth.open"]
    mid = ev.evaluate(0.25).values["mouth.open"]
    done = ev.evaluate(0.3).values["mouth.open"]
    assert at == pytest.approx(left, abs=1e-6) == 0
    assert mid == pytest.approx(0.4)  # halfway from 0 (mbp) to 0.8 (ai)
    assert done == pytest.approx(0.8)
    samples = [ev.evaluate(0.2 + i * 0.01).values["mouth.open"] for i in range(11)]
    assert samples == sorted(samples)


def test_transition_capped_at_half_segment() -> None:
    tr = track([("mbp", 0.0, 0.2), ("ai", 0.2, 0.26)], transition=0.5, ease="linear")
    st = evaluate_lipsync(tr, 0.23, VS)
    assert st.weights == {"ai": pytest.approx(1.0)}


def test_coarticulation_anticipates_next_and_stays_continuous() -> None:
    tr = track(
        [("ai", 0.0, 0.4), ("u", 0.4, 0.8)], transition=0.05, coarticulation=0.5, ease="linear"
    )
    ev = LipSyncEvaluator(tr, VS)
    first_half = ev.evaluate(0.15)
    assert first_half.weights == {"ai": pytest.approx(1.0)}
    late = ev.evaluate(0.39)
    assert 0.4 < late.weights["ai"] < 0.6 and late.weights["u"] > 0.4
    before = ev.evaluate(0.4 - 1e-9).values["mouth.width"]
    after = ev.evaluate(0.4).values["mouth.width"]
    assert after == pytest.approx(before, abs=1e-6)
    no_co = LipSyncEvaluator(track([("ai", 0.0, 0.4), ("u", 0.4, 0.8)]), VS).evaluate(0.39)
    assert no_co.weights == {"ai": pytest.approx(1.0)}


def test_silence_transition_back_to_rest() -> None:
    tr = track([("ai", 0.0, 0.2)], transition=0.1, ease="linear")
    assert evaluate_lipsync(tr, 0.2, VS).values["mouth.open"] == pytest.approx(0.8)
    assert evaluate_lipsync(tr, 0.25, VS).values["mouth.open"] == pytest.approx(0.4)
    assert evaluate_lipsync(tr, 0.3, VS).values["mouth.open"] == pytest.approx(0.0)


def test_lipsync_determinism_and_flags() -> None:
    tr = track([("th", 0.0, 0.3), ("fv", 0.3, 0.6)], coarticulation=0.3)
    a = [evaluate_lipsync(tr, t / 20, VS).to_dict() for t in range(15)]
    b = [evaluate_lipsync(tr, t / 20, VS).to_dict() for t in range(15)]
    assert a == b
    s = evaluate_lipsync(tr, 0.15, VS)
    assert s.tongue_visible and s.teeth_visible and s.shape == "th"


def test_invalid_tracks_and_times() -> None:
    with pytest.raises(LipSyncError, match="LIP006"):
        LipSyncEvaluator(track([("zz", 0, 1)]), VS)
    overlapping = LipSyncTrack.model_construct(
        schema_version=1,
        id="t",
        character_id=None,
        viseme_set="default",
        phoneme_map=None,
        duration=None,
        settings=LipSyncSettings(),
        events=[
            VisemeEvent(viseme="ai", start=0, end=0.5),
            VisemeEvent(viseme="o", start=0.4, end=0.6),
        ],
    )
    assert any(p.startswith("LIP002") for p in validate_track(overlapping, VS))
    long = track([("ai", 0, 2)]).model_copy(update={"duration": 1.0})
    assert any(p.startswith("LIP011") for p in validate_track(long, VS))
    ev = LipSyncEvaluator(track([("ai", 0, 1)]), VS)
    for bad in (math.nan, -0.1, math.inf):
        with pytest.raises(LipSyncError):
            ev.evaluate(bad)
    with pytest.raises(ValueError):
        VisemeEvent(viseme="ai", start=-1, end=0.5)


def test_apply_lipsync_keeps_expression_and_adds_corners(project) -> None:
    from studio.characters.manager import CharacterStore
    from studio.face.manager import FaceStore

    CharacterStore(project).create("Mira Vale")
    rig = FaceStore(project).create("chr_mira-vale").face
    happy = evaluate_expression(rig, builtin_expression("happy"))
    lips = LipSyncEvaluator(track([("ee", 0.0, 0.5)], transition=0.0), VS, rig).evaluate(0.2)
    combined = apply_lipsync(happy, lips, rig)
    assert combined.values["mouth.open"] == pytest.approx(0.25)  # speech drives the mouth
    assert combined.values["eye_l.squint"] == 0.35  # expression keeps the eyes
    assert combined.values["mouth.corner_l"] == pytest.approx(1.0)  # 0.8 + 0.2, clamped to max 1
    assert combined.shapes["mouth"] == "ee"


# --- alignment provider interface --------------------------------------------------------------


def _wav() -> bytes:
    return silent_wav(1.0, 16000)


def test_alignment_disabled_by_default() -> None:
    with pytest.raises(ProviderUnavailableError, match="disabled"):
        align_audio(ProviderSelection(provider="none"), _wav(), "hello")


def test_mock_alignment_words_only_and_no_invented_phonemes() -> None:
    doc = align_audio(ProviderSelection(provider="mock"), _wav(), "hello world")
    assert [w.word for w in doc.words] == ["hello", "world"] and doc.phonemes == []
    assert doc.source.provider == "mock"
    with pytest.raises(LipSyncError, match="LIP008"):
        phoneme_events(doc)
    with pytest.raises(ProviderUnavailableError, match="phoneme timestamps"):
        align_audio(ProviderSelection(provider="mock"), _wav(), "hi", require_phonemes=True)


class _FakePhonemeAligner(ASRProvider):
    info = ProviderInfo(
        "fake-phonemes",
        ProviderKind.ASR,
        "test-only phoneme aligner",
        capabilities=frozenset({"forced_alignment", "phoneme_timestamps"}),
    )

    def align(self, request):  # type: ignore[no-untyped-def]
        with wave.open(io.BytesIO(request.wav)) as w:
            dur = w.getnframes() / w.getframerate()
        return AlignmentResult(
            words=[WordTiming("hi", 0.1, 0.4)],
            duration_s=dur,
            provenance=self.provenance(model="fixed-test-timings"),
            phonemes=[
                PhonemeTiming("HH", 0.1, 0.2, 0.9, 0),
                PhonemeTiming("AY1", 0.2, 0.4, 0.8, 0),
            ],
        )


def test_phoneme_capable_provider_end_to_end() -> None:
    register_provider(_FakePhonemeAligner.info, _FakePhonemeAligner)
    try:
        doc = align_audio(
            ProviderSelection(provider="fake-phonemes"), _wav(), "hi", require_phonemes=True
        )
    finally:
        unregister_provider(ProviderKind.ASR, "fake-phonemes")
    assert [p.phoneme for p in doc.phonemes] == ["HH", "AY1"] and doc.duration == 1.0
    res = map_phonemes(phoneme_events(doc), EN, VS)
    assert [e.viseme for e in res.events] == ["rest", "k", "ai"]
    assert res.events[1].confidence == 0.9
    summary = summarize(doc)
    assert summary["phonemes"] == 2 and summary["provider"] == "fake-phonemes"


def test_document_from_result_and_schema() -> None:
    result = AlignmentResult(
        words=[WordTiming("a", 0, 1)], duration_s=1.0, provenance={"provider": "x"}
    )
    doc = document_from_result(result, transcript="a")
    assert doc.words[0].word == "a" and doc.phonemes == [] and doc.transcript == "a"
    with pytest.raises(ValueError):
        AlignmentDocument(source=AlignmentSource(provider="x"), unexpected=1)  # type: ignore[call-arg]
