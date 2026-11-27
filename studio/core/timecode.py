"""Frame and timecode utilities.

Provenance (see docs/LEGACY_REUSE.md):
    Adapted from legacy branch ``ccr-5cb67ed4-c3se5u``,
    file ``cartoon-audio-short/kit/engine/captions.py`` (commit 02e0c3e): the frame
    snapping ``snap`` lambda and the ASS timestamp formatter ``ts``. That file was written
    in a Claude Code session for this repository's owner. It is not part of the
    MIT-licensed third-party code in that branch.

Changes made during adaptation:
    * the frame rate is a parameter instead of a hard-coded 30 fps constant;
    * input validation (negative times, non-positive frame rates) was added;
    * SMPTE-style ``HH:MM:SS:FF`` formatting was added;
    * the functions are typed and covered by tests/unit/test_timecode.py.

The animation clock is in seconds. Frames are only sampled at render time, so every
module stays independent of frame rate (24, 25, 30 fps ...).
"""

from __future__ import annotations

import math


def _check_fps(fps: float) -> None:
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError(f"frame rate must be a positive number, got {fps!r}")


def _check_time(seconds: float) -> None:
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError(f"time must be a non-negative number of seconds, got {seconds!r}")


def seconds_to_frames(seconds: float, fps: float) -> int:
    """Nearest frame index for a time in seconds (round half to even, like the legacy code)."""
    _check_fps(fps)
    _check_time(seconds)
    return round(seconds * fps)


def frames_to_seconds(frames: int, fps: float) -> float:
    _check_fps(fps)
    if frames < 0:
        raise ValueError(f"frame count must be non-negative, got {frames}")
    return frames / fps


def snap_to_frame(seconds: float, fps: float) -> float:
    """Snap a time to the nearest frame boundary (legacy ``snap``)."""
    return frames_to_seconds(seconds_to_frames(seconds, fps), fps)


def duration_in_frames(start: float, end: float, fps: float) -> int:
    """Frames covered by [start, end) once both ends are snapped to frame boundaries."""
    if end < start:
        raise ValueError(f"end ({end}) is before start ({start})")
    return seconds_to_frames(end, fps) - seconds_to_frames(start, fps)


def format_ass_time(seconds: float) -> str:
    """ASS/SSA subtitle timestamp ``H:MM:SS.cc`` (centiseconds), legacy ``ts``."""
    _check_time(seconds)
    cs = round(seconds * 100)
    hours, cs = divmod(cs, 360_000)
    minutes, cs = divmod(cs, 6_000)
    secs, cs = divmod(cs, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def format_smpte(seconds: float, fps: float) -> str:
    """Non-drop-frame timecode ``HH:MM:SS:FF`` at the nearest whole frame rate."""
    _check_fps(fps)
    nominal = round(fps)
    if nominal < 1:
        raise ValueError(f"frame rate too low for SMPTE timecode: {fps}")
    total = seconds_to_frames(seconds, fps)
    frames = total % nominal
    total_seconds = total // nominal
    hours, rem = divmod(total_seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"
