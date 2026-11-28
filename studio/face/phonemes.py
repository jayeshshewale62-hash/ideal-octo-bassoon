"""Phoneme -> viseme mapping (deterministic; tables live in data files, not code).

The mapper only ever uses the timestamps it is given. It never invents phoneme timings.
The single exception is optional *silence* fill: gaps between (and before) the given
events become explicit ``rest`` events covering exactly those gaps.

Validation codes (also used for viseme tracks):

========  =========  ==========================================================
LIP001    error      event has zero or negative duration (end <= start)
LIP002    error      event starts before the previous one ends (overlap)
LIP003    error      events are not in time order
LIP004    error      negative or non-finite timestamp
LIP005    warning    unknown phoneme (handled by the map's ``unknown`` policy)
LIP006    error      viseme id not in the viseme set
LIP008    error      the alignment contains no phonemes
LIP009    error      the phoneme map points at a viseme the set does not define
========  =========  ==========================================================
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from studio.core.exceptions import LipSyncError
from studio.face.schemas import PhonemeEvent, PhonemeMap, VisemeEvent, VisemeSet

EPS = 1e-9
_STRESS = re.compile(r"[0-9]+$")


@dataclass
class MappingResult:
    events: list[VisemeEvent]
    warnings: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)


class Timed(Protocol):
    @property
    def start(self) -> float: ...
    @property
    def end(self) -> float: ...


def check_timing(events: Sequence[Timed]) -> list[str]:
    problems: list[str] = []
    prev_start, prev_end = -math.inf, -math.inf
    for i, ev in enumerate(events):
        label = (
            getattr(ev, "phoneme", None) or getattr(ev, "viseme", None) or getattr(ev, "word", "?")
        )
        where = f"event {i} ({label!r} {ev.start:g}-{ev.end:g})"
        if not (math.isfinite(ev.start) and math.isfinite(ev.end)) or ev.start < 0 or ev.end < 0:
            problems.append(f"LIP004 {where}: timestamps must be finite and >= 0")
            continue
        if ev.end <= ev.start:
            problems.append(f"LIP001 {where}: duration must be positive (end > start)")
        if ev.start < prev_start:
            problems.append(
                f"LIP003 {where}: starts before the previous event; sort events by time"
            )
        elif ev.start < prev_end - EPS:
            problems.append(f"LIP002 {where}: overlaps the previous event (ends {prev_end:g})")
        prev_start, prev_end = ev.start, max(prev_end, ev.end)
    return problems


def check_map(pmap: PhonemeMap, visemes: VisemeSet) -> list[str]:
    known = {v.id for v in visemes.visemes}
    return [
        f"LIP009 phoneme {ph!r} maps to unknown viseme {vis!r}"
        for ph, vis in sorted(pmap.map.items())
        if vis not in known
    ]


def normalize(symbol: str, pmap: PhonemeMap) -> str:
    s = symbol.strip()
    if pmap.strip_stress:
        s = _STRESS.sub("", s)
    return s if pmap.case_sensitive else s.upper()


def map_phonemes(
    events: Sequence[PhonemeEvent],
    pmap: PhonemeMap,
    visemes: VisemeSet,
    *,
    merge_adjacent: bool = True,
    fill_silence: bool = True,
) -> MappingResult:
    problems = check_timing(events) + check_map(pmap, visemes)
    if problems:
        raise LipSyncError("phoneme events cannot be mapped", problems)
    table = {normalize(k, pmap): v for k, v in pmap.map.items()}
    silence = {normalize(s, pmap) for s in pmap.silence}
    rest = visemes.rest
    result = MappingResult(events=[])
    out: list[VisemeEvent] = []
    previous = rest
    cursor = 0.0
    for ev in events:
        if fill_silence and ev.start > cursor + EPS:
            out.append(VisemeEvent(viseme=rest, start=cursor, end=ev.start, source="silence"))
        key = normalize(ev.phoneme, pmap)
        if key in silence:
            viseme, source = rest, "silence"
        elif key in table:
            viseme, source = table[key], "phoneme"
        else:
            result.unknown.append(ev.phoneme)
            message = f"LIP005 unknown phoneme {ev.phoneme!r} at {ev.start:g}s"
            if pmap.unknown == "error":
                raise LipSyncError("unknown phoneme", [message])
            viseme = previous if pmap.unknown == "previous" else rest
            source = "unknown"
            result.warnings.append(f"{message} -> {viseme!r} ({pmap.unknown} policy)")
        out.append(
            VisemeEvent(
                viseme=viseme,
                start=ev.start,
                end=ev.end,
                phonemes=[ev.phoneme],
                confidence=ev.confidence,
                source=source,
            )
        )
        previous = viseme
        cursor = ev.end
    result.events = merge_events(out) if merge_adjacent else out
    return result


def merge_events(events: list[VisemeEvent]) -> list[VisemeEvent]:
    """Join touching events that show the same viseme (keeps every phoneme label)."""
    merged: list[VisemeEvent] = []
    for ev in events:
        last = merged[-1] if merged else None
        if last is not None and last.viseme == ev.viseme and abs(last.end - ev.start) <= EPS:
            confs = [c for c in (last.confidence, ev.confidence) if c is not None]
            merged[-1] = last.model_copy(
                update={
                    "end": ev.end,
                    "phonemes": [*last.phonemes, *ev.phonemes],
                    "confidence": min(confs) if confs else None,
                    "source": last.source if last.source == ev.source else "phoneme",
                }
            )
        else:
            merged.append(ev)
    return merged
