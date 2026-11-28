"""Compatibility smoke test for the intended core vector backend (skia-python).

Runs only when the optional 'render' extra is installed (CI has a dedicated job).
It checks that skia can draw anti-aliased vector paths on the CPU without a GPU.
It does not render any animation (that work starts in Milestone 3).
"""

from __future__ import annotations

import pytest

skia = pytest.importorskip("skia", reason="optional 'render' extra not installed")
np = pytest.importorskip("numpy")

pytestmark = pytest.mark.render


def test_cpu_raster_surface_draws_vector_path() -> None:
    surface = skia.Surface(64, 64)  # CPU raster surface, no GPU context
    with surface as canvas:
        canvas.clear(skia.ColorWHITE)
        paint = skia.Paint(
            AntiAlias=True,
            Color=skia.ColorBLACK,
            Style=skia.Paint.kStroke_Style,
            StrokeWidth=4,
            StrokeCap=skia.Paint.kRound_Cap,
        )
        path = skia.Path()
        path.moveTo(8, 32)
        path.cubicTo(20, 4, 44, 60, 56, 32)
        canvas.drawPath(path, paint)
    pixels = surface.makeImageSnapshot().toarray()
    assert pixels.shape == (64, 64, 4)
    dark = (pixels[..., :3].mean(axis=2) < 128).sum()
    assert 50 < dark < 1500  # a stroke was drawn, the canvas is not filled


def test_svg_document_renders() -> None:
    """SVG artwork (the studio's character-part format) renders through skia's SVG DOM."""
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40">'
        b'<rect x="10" y="10" width="20" height="20" fill="black"/></svg>'
    )
    dom = skia.SVGDOM.MakeFromStream(skia.MemoryStream(svg))
    assert (dom.containerSize().width(), dom.containerSize().height()) == (40, 40)
    surface = skia.Surface(40, 40)
    with surface as canvas:
        canvas.clear(skia.ColorWHITE)
        dom.render(canvas)
    pixels = surface.makeImageSnapshot().toarray()
    assert (pixels[..., :3].mean(axis=2) < 128).sum() == 400  # exactly the 20x20 square
