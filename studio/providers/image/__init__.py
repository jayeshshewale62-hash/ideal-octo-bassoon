"""Image generation providers (module 10).

Scope rule: image generation produces concept art, background plates and textures.
It **never** produces per-frame character animation; characters are animated by rigs.
"""

from __future__ import annotations

import struct
import zlib
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from studio.core.exceptions import ProviderError
from studio.core.hashing import hash_data
from studio.core.schemas import ProviderKind
from studio.providers.base import DisabledMixin, Provider, ProviderInfo

MAX_MOCK_SIDE = 4096


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    width: int = 1024
    height: int = 1024
    seed: int | None = None
    negative_prompt: str = ""
    reference_asset_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImageResult:
    png: bytes
    width: int
    height: int
    provenance: dict[str, Any] = field(default_factory=dict)


class ImageProvider(Provider):
    kind: ClassVar[ProviderKind] = ProviderKind.IMAGE

    @abstractmethod
    def generate(self, request: ImageRequest) -> ImageResult: ...


class DisabledImageProvider(DisabledMixin, ImageProvider):
    info = ProviderInfo("none", ProviderKind.IMAGE, "Image generation disabled")

    def generate(self, request: ImageRequest) -> ImageResult:
        raise self._refuse()


def encode_png_rgb(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """Minimal valid PNG (solid colour) using only the standard library."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    row = b"\x00" + bytes(rgb) * width
    raw = row * height
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


class MockImageProvider(ImageProvider):
    """Deterministic offline stand-in: a solid-colour PNG whose colour derives from the request."""

    info = ProviderInfo(
        "mock",
        ProviderKind.IMAGE,
        "Deterministic solid-colour PNG for tests (no model, no network)",
        capabilities=frozenset({"text_to_image", "seed_control"}),
        deterministic=True,
    )

    def generate(self, request: ImageRequest) -> ImageResult:
        if not request.prompt.strip():
            raise ProviderError("image prompt is empty")
        for side in (request.width, request.height):
            if not 1 <= side <= MAX_MOCK_SIDE:
                raise ProviderError(f"image size must be 1..{MAX_MOCK_SIDE} px, got {side}")
        digest = hash_data({"prompt": request.prompt, "seed": request.seed})
        rgb = (int(digest[7:9], 16), int(digest[9:11], 16), int(digest[11:13], 16))
        png = encode_png_rgb(request.width, request.height, rgb)
        return ImageResult(
            png=png,
            width=request.width,
            height=request.height,
            provenance=self.provenance(
                model="mock-solid-color", seed=request.seed, prompt=request.prompt
            ),
        )


__all__ = [
    "DisabledImageProvider",
    "ImageProvider",
    "ImageRequest",
    "ImageResult",
    "MockImageProvider",
    "encode_png_rgb",
]
