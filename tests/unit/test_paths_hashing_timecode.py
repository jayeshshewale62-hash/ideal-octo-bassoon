from __future__ import annotations

import os
from pathlib import Path

import pytest

from studio.core import timecode as tc
from studio.core.exceptions import PathSafetyError
from studio.core.hashing import hash_bytes, hash_data, hash_file, is_valid_hash
from studio.core.paths import check_relative_path, safe_join, slugify, to_relative

# --- paths -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        "/etc/passwd",
        "../secret.txt",
        "assets/../../x",
        "C:/Windows/system32",
        "assets\\char.svg",
        "a/\x00b",
        ".",
        "./",
    ],
)
def test_check_relative_path_rejects(bad: str) -> None:
    with pytest.raises(PathSafetyError):
        check_relative_path(bad)


def test_check_relative_path_normalises() -> None:
    assert check_relative_path("./assets//characters/./hero.svg") == "assets/characters/hero.svg"


def test_safe_join_inside(tmp_path: Path) -> None:
    assert safe_join(tmp_path, "a/b.svg") == (tmp_path / "a" / "b.svg").resolve()


def test_safe_join_blocks_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "project"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    os.symlink(outside, root / "link")
    with pytest.raises(PathSafetyError, match="outside"):
        safe_join(root, "link/file.svg")


def test_to_relative_rejects_outside(tmp_path: Path) -> None:
    (tmp_path / "p").mkdir()
    with pytest.raises(PathSafetyError):
        to_relative(tmp_path / "p", tmp_path / "other.svg")


@pytest.mark.parametrize(
    ("text", "slug"),
    [
        ("Demo", "demo"),
        ("The Fox & The Moon!", "the-fox-the-moon"),
        ("  ---  ", ""),
        ("Épisode 2", "pisode-2"),
    ],
)
def test_slugify(text: str, slug: str) -> None:
    assert slugify(text) == slug


# --- hashing ---------------------------------------------------------------------------------


def test_hash_format_and_stability(tmp_path: Path) -> None:
    f = tmp_path / "a.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\nabc")
    first = hash_file(f)
    assert is_valid_hash(first)
    assert first == hash_file(f) == hash_bytes(f.read_bytes())


def test_text_hash_ignores_line_endings(tmp_path: Path) -> None:
    lf, crlf = tmp_path / "lf.svg", tmp_path / "crlf.svg"
    lf.write_bytes(b"<svg>\n<g/>\n</svg>\n")
    crlf.write_bytes(b"<svg>\r\n<g/>\r\n</svg>\r\n")
    assert hash_file(lf) == hash_file(crlf)


def test_binary_hash_is_byte_exact(tmp_path: Path) -> None:
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    a.write_bytes(b"RIFF\r\n")
    b.write_bytes(b"RIFF\n")
    assert hash_file(a) != hash_file(b)


def test_hash_data_is_key_order_independent() -> None:
    assert hash_data({"a": 1, "b": [1, 2]}) == hash_data({"b": [1, 2], "a": 1})
    assert hash_data({"a": 1}) != hash_data({"a": 2})


def test_known_sha256_vector() -> None:
    assert hash_bytes(b"abc") == (
        "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


# --- timecode (adapted from legacy captions.py, see docs/LEGACY_REUSE.md) -------------------


def test_seconds_frames_roundtrip() -> None:
    assert tc.seconds_to_frames(1.0, 24) == 24
    assert tc.seconds_to_frames(0.52, 24) == 12
    assert tc.frames_to_seconds(36, 24) == 1.5
    assert tc.snap_to_frame(0.43, 30) == pytest.approx(13 / 30)


def test_snap_matches_legacy_behaviour() -> None:
    # Legacy: snap = lambda t: round(t * FPS) / FPS with FPS = 30
    for t in (0.0, 0.0166, 0.1, 0.43, 1.5, 59.99):
        assert tc.snap_to_frame(t, 30) == round(t * 30) / 30


def test_duration_in_frames() -> None:
    assert tc.duration_in_frames(1.0, 2.5, 24) == 36
    with pytest.raises(ValueError, match="before start"):
        tc.duration_in_frames(2.0, 1.0, 24)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0:00:00.00"),
        (0.43, "0:00:00.43"),
        (61.5, "0:01:01.50"),
        (3599.999, "1:00:00.00"),
        (3725.25, "1:02:05.25"),
    ],
)
def test_ass_time(seconds: float, expected: str) -> None:
    assert tc.format_ass_time(seconds) == expected


def test_ass_time_matches_legacy_formatter() -> None:
    def legacy_ts(t: float) -> str:  # verbatim logic of the legacy `ts` function
        cs = int(round(t * 100))  # noqa: RUF046 - verbatim legacy formula
        h, cs = divmod(cs, 360000)
        m, cs = divmod(cs, 6000)
        s, cs = divmod(cs, 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    for t in (0.0, 0.01, 0.43, 2.3, 59.995, 61.5, 3599.999, 7322.42):
        assert tc.format_ass_time(t) == legacy_ts(t)


def test_smpte() -> None:
    assert tc.format_smpte(0, 24) == "00:00:00:00"
    assert tc.format_smpte(1.5, 24) == "00:00:01:12"
    assert tc.format_smpte(3661 + 23 / 24, 24) == "01:01:01:23"
    assert tc.format_smpte(10, 23.976) == "00:00:10:00"  # 240 frames at nominal 24


@pytest.mark.parametrize("fps", [0, -24, float("nan"), float("inf")])
def test_bad_fps(fps: float) -> None:
    with pytest.raises(ValueError, match="frame rate"):
        tc.seconds_to_frames(1, fps)


def test_negative_time() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        tc.seconds_to_frames(-1, 24)
    with pytest.raises(ValueError):
        tc.frames_to_seconds(-1, 24)
