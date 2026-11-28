"""Timestamp-based lip-sync evaluation: ``evaluate_lipsync(track, time, visemes)``.

Timing model (docs/FACE.md#lip-sync-timing):

* Events are half-open intervals ``[start, end)``. A time exactly on a boundary belongs to
  the *later* event. Before the first event, in gaps, and after the last event the mouth
  is at ``rest``.
* **Transition:** entering a segment blends from the previous segment's final mouth state
  to this segment's target over ``settings.transition`` seconds, capped at half the
  segment, with the configured ease. At the boundary itself the weight is 0, so the mouth
  is continuous.
* **Coarticulation** ``c`` (0..1): during the second half of a segment, up to ``c`` of
  the *next* viseme is mixed in, ramping linearly. The next transition starts from that
  mixed state, so this stays continuous too.
* Mouth control values are the weight-averaged viseme values. A control a viseme does not
  set falls back to the rest viseme, then to the rig default (or 0). The drawn mouth
  *shape* is the viseme with the largest weight (ties: the current segment's viseme).

The same track, viseme set and time always give the same result.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field

from studio.core.exceptions import LipSyncError
from studio.face.expressions import FaceState, ease_weight
from studio.face.phonemes import check_timing
from studio.face.schemas import FacialRig, LipSyncTrack, VisemeSet

LIP_OVERRIDE_EXCEPT = frozenset({"mouth.corner_l", "mouth.corner_r"})  # added, not replaced


@dataclass(frozen=True)
class _Segment:
    start: float
    end: float
    viseme: str


@dataclass
class LipSyncState:
    time: float
    viseme: str  # viseme of the active segment
    dominant: str  # viseme with the largest weight
    weights: dict[str, float]
    values: dict[str, float]
    shape: str | None
    teeth_visible: bool = False
    tongue_visible: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "time": self.time,
            "viseme": self.viseme,
            "dominant": self.dominant,
            "weights": {k: round(v, 6) for k, v in sorted(self.weights.items())},
            "values": {k: round(v, 6) for k, v in sorted(self.values.items())},
            "shape": self.shape,
            "teeth_visible": self.teeth_visible,
            "tongue_visible": self.tongue_visible,
        }


def validate_track(track: LipSyncTrack, visemes: VisemeSet) -> list[str]:
    problems = check_timing(track.events)
    known = {v.id for v in visemes.visemes}
    for i, ev in enumerate(track.events):
        if ev.viseme not in known:
            problems.append(f"LIP006 event {i}: unknown viseme {ev.viseme!r} (set {visemes.id})")
    if track.viseme_set != visemes.id:
        problems.append(f"LIP010 track uses viseme set {track.viseme_set!r}, got {visemes.id!r}")
    if track.duration is not None and track.events and track.events[-1].end > track.duration + 1e-9:
        problems.append("LIP011 events extend beyond the track duration")
    return problems


class LipSyncEvaluator:
    """Pre-compiles a track once; :meth:`evaluate` is then cheap per frame."""

    def __init__(self, track: LipSyncTrack, visemes: VisemeSet, rig: FacialRig | None = None):
        problems = validate_track(track, visemes)
        if problems:
            raise LipSyncError(f"lip-sync track {track.id!r} is invalid", problems)
        self.track = track
        self.visemes = visemes
        self.rest = visemes.rest
        segs: list[_Segment] = []
        cursor = -math.inf
        for ev in track.events:
            if ev.start > cursor + 1e-12:
                segs.append(_Segment(cursor, ev.start, self.rest))
            segs.append(_Segment(ev.start, ev.end, ev.viseme))
            cursor = ev.end
        segs.append(_Segment(cursor, math.inf, self.rest))
        self.segments = segs
        self.starts = [s.start for s in segs]
        rest_values = (visemes.get(self.rest) or visemes.visemes[0]).values
        keys = sorted({k for v in visemes.visemes for k in v.values})
        self.defaults: dict[str, float] = {}
        for key in keys:
            channel = rig.channel(key) if rig else None
            self.defaults[key] = rest_values.get(key, channel.default if channel else 0.0)
        self.rig = rig

    # --- weights --------------------------------------------------------------------------

    def _target(self, index: int, time: float) -> dict[str, float]:
        seg = self.segments[index]
        c = self.track.settings.coarticulation
        nxt = self.segments[index + 1].viseme if index + 1 < len(self.segments) else None
        if c <= 0 or nxt is None or nxt == seg.viseme or not math.isfinite(seg.end):
            return {seg.viseme: 1.0}
        if math.isfinite(seg.start):
            mid = (seg.start + seg.end) / 2
        else:
            mid = seg.end - self.track.settings.transition
        if seg.end - mid <= 0:
            return {seg.viseme: 1.0}
        r = min(1.0, max(0.0, (time - mid) / (seg.end - mid)))
        if r <= 0:
            return {seg.viseme: 1.0}
        return {seg.viseme: 1.0 - c * r, nxt: c * r}

    def weights_at(self, time: float) -> tuple[int, dict[str, float]]:
        if not math.isfinite(time) or time < 0:
            raise LipSyncError(f"time must be a finite number >= 0, got {time!r}")
        index = bisect.bisect_right(self.starts, time) - 1
        seg = self.segments[index]
        target = self._target(index, time)
        if index == 0 or not math.isfinite(seg.start):
            return index, target
        span = seg.end - seg.start
        tr = min(self.track.settings.transition, span / 2)
        if tr <= 0 or time >= seg.start + tr:
            return index, target
        w = ease_weight((time - seg.start) / tr, self.track.settings.ease)
        source = self._target(index - 1, self.segments[index - 1].end)
        mixed: dict[str, float] = {}
        for key in sorted(set(source) | set(target)):
            mixed[key] = source.get(key, 0.0) * (1 - w) + target.get(key, 0.0) * w
        return index, {k: v for k, v in mixed.items() if v > 1e-12}

    # --- evaluation -------------------------------------------------------------------------

    def evaluate(self, time: float) -> LipSyncState:
        index, weights = self.weights_at(time)
        total = sum(weights.values()) or 1.0
        values = {}
        for key, default in self.defaults.items():
            acc = 0.0
            for vid, w in weights.items():
                vis = self.visemes.get(vid)
                acc += (vis.values.get(key, default) if vis else default) * w
            value = acc / total
            channel = self.rig.channel(key) if self.rig else None
            if channel is not None:
                value = min(channel.max, max(channel.min, value))
            values[key] = value
        current = self.segments[index].viseme
        dominant = max(weights, key=lambda v: (weights[v], v == current, v))
        vis = self.visemes.get(dominant)
        return LipSyncState(
            time=time,
            viseme=current,
            dominant=dominant,
            weights=weights,
            values=values,
            shape=vis.shape if vis else None,
            teeth_visible=bool(vis and vis.teeth_visible),
            tongue_visible=bool(vis and vis.tongue_visible),
        )


def evaluate_lipsync(
    track: LipSyncTrack, time: float, visemes: VisemeSet, rig: FacialRig | None = None
) -> LipSyncState:
    """Mouth state of ``track`` at ``time`` (seconds). Deterministic."""
    return LipSyncEvaluator(track, visemes, rig).evaluate(time)


def apply_lipsync(face: FaceState, lips: LipSyncState, rig: FacialRig) -> FaceState:
    """Speech drives the mouth and jaw; the expression keeps everything else.
    Mouth corners are *added* to the expression's corners (so a smile survives speech)."""
    values = dict(face.values)
    for key, value in lips.values.items():
        channel = rig.channel(key)
        if channel is None:
            continue
        if key in LIP_OVERRIDE_EXCEPT:
            value = face.values.get(key, channel.default) + (value - channel.default)
        values[key] = min(channel.max, max(channel.min, value))
    shapes = dict(face.shapes)
    mouth = next((c for c in rig.components if c.kind.value == "mouth"), None)
    if mouth is not None and lips.shape in mouth.shapes:
        shapes[mouth.id] = lips.shape
    return FaceState(values, shapes, f"{face.label}+lipsync@{lips.time:g}s", list(face.issues))
