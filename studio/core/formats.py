"""Supported asset formats and content sniffing.

Registration checks that a file's bytes match its extension (a ``.png`` must start with
the PNG signature, an ``.svg`` must parse as XML with an ``<svg>`` root ...). This catches
renamed or corrupt files before they enter a registry.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from studio.core.exceptions import InvalidAssetError

MAX_TEXT_PARSE_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class FormatInfo:
    name: str
    binary: bool
    description: str


FORMATS: dict[str, FormatInfo] = {
    "svg": FormatInfo("svg", False, "SVG vector artwork (character parts, props)"),
    "png": FormatInfo("png", True, "PNG raster (backgrounds, textures, model sheets)"),
    "jpg": FormatInfo("jpg", True, "JPEG raster (reference/concept only)"),
    "webp": FormatInfo("webp", True, "WebP raster"),
    "ora": FormatInfo("ora", True, "OpenRaster layered artwork (Krita/MyPaint/GIMP)"),
    "psd": FormatInfo("psd", True, "Photoshop layered artwork"),
    "kra": FormatInfo("kra", True, "Krita layered artwork"),
    "wav": FormatInfo("wav", True, "WAV audio (voice, sfx, stems)"),
    "mp3": FormatInfo("mp3", True, "MP3 audio"),
    "flac": FormatInfo("flac", True, "FLAC audio"),
    "ogg": FormatInfo("ogg", True, "Ogg audio"),
    "json": FormatInfo("json", False, "JSON data (rigs, curves, alignment)"),
    "yaml": FormatInfo("yaml", False, "YAML data (scenes, characters, story)"),
    "txt": FormatInfo("txt", False, "Plain text (scripts)"),
    "md": FormatInfo("md", False, "Markdown text"),
    "ttf": FormatInfo("ttf", True, "TrueType font"),
    "otf": FormatInfo("otf", True, "OpenType font"),
    "woff2": FormatInfo("woff2", True, "WOFF2 font"),
}

ALIASES = {"jpeg": "jpg", "yml": "yaml"}


def format_for(path: Path) -> FormatInfo:
    ext = path.suffix.lower().lstrip(".")
    ext = ALIASES.get(ext, ext)
    if ext not in FORMATS:
        supported = ", ".join(sorted(FORMATS))
        raise InvalidAssetError(
            f"unsupported asset format '.{ext}' ({path.name}); supported: {supported}"
        )
    return FORMATS[ext]


def _head(path: Path, n: int = 64) -> bytes:
    with path.open("rb") as fh:
        return fh.read(n)


def _check_binary(fmt: str, head: bytes) -> bool:
    checks: dict[str, Callable[[bytes], bool]] = {
        "png": lambda h: h.startswith(b"\x89PNG\r\n\x1a\n"),
        "jpg": lambda h: h.startswith(b"\xff\xd8\xff"),
        "webp": lambda h: h[:4] == b"RIFF" and h[8:12] == b"WEBP",
        "ora": lambda h: h.startswith(b"PK\x03\x04"),
        "kra": lambda h: h.startswith(b"PK\x03\x04"),
        "psd": lambda h: h.startswith(b"8BPS"),
        "wav": lambda h: h[:4] in (b"RIFF", b"RF64") and h[8:12] == b"WAVE",
        "mp3": lambda h: (
            h.startswith(b"ID3") or (len(h) > 1 and h[0] == 0xFF and h[1] & 0xE0 == 0xE0)
        ),
        "flac": lambda h: h.startswith(b"fLaC"),
        "ogg": lambda h: h.startswith(b"OggS"),
        "ttf": lambda h: h[:4] in (b"\x00\x01\x00\x00", b"true"),
        "otf": lambda h: h.startswith(b"OTTO"),
        "woff2": lambda h: h.startswith(b"wOF2"),
    }
    return checks[fmt](head)


def sniff(path: Path) -> FormatInfo:
    """Return the format of ``path`` after checking its content; raise if it does not match."""
    info = format_for(path)
    if not path.is_file():
        raise InvalidAssetError(f"not a regular file: {path}")
    size = path.stat().st_size
    if size == 0:
        raise InvalidAssetError(f"file is empty: {path.name}")
    if info.binary:
        if not _check_binary(info.name, _head(path)):
            raise InvalidAssetError(f"{path.name} does not contain valid {info.name.upper()} data")
        return info
    if size > MAX_TEXT_PARSE_BYTES:
        raise InvalidAssetError(f"{path.name} is too large for a text asset ({size} bytes)")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise InvalidAssetError(f"{path.name} is not UTF-8 text") from None
    try:
        if info.name == "svg":
            if "<!ENTITY" in text:
                raise InvalidAssetError(f"{path.name}: SVG with entity declarations is not allowed")
            root = ET.fromstring(text)  # noqa: S314 - entity declarations rejected above
            if root.tag.rsplit("}", 1)[-1] != "svg":
                raise InvalidAssetError(f"{path.name}: root element is <{root.tag}>, not <svg>")
        elif info.name == "json":
            json.loads(text)
        elif info.name == "yaml":
            yaml.safe_load(text)
    except (ET.ParseError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise InvalidAssetError(f"{path.name} is not valid {info.name.upper()}: {exc}") from None
    return info
