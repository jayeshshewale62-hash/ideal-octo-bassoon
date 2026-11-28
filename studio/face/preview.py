"""Facial diagnostic previews (SVG, pure Python, deterministic).

A panel draws the face schematically in face space: eye outlines with lids and pupils,
brow curves, the mouth outline with corners and lip positions, jaw, cheeks, nose and
control markers. It also lists every control that differs from neutral. A *sheet* places
several panels side by side, for example lip-sync states sampled at given times.

These are inspection diagrams of control values, **not artwork and not animation**. A
sheet of sampled times is a set of stills, not continuous playback, and the title says so.
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from dataclasses import dataclass

from studio.face.expressions import FaceState, neutral_state
from studio.face.geometry import ResolvedComponent, resolve_face
from studio.face.schemas import ComponentKind, FacialRig
from studio.rig.math2d import Vec2

BANNER = "DIAGNOSTIC: facial controls (not artwork, not animation)"
SHEET_BANNER = "DIAGNOSTIC: sampled facial states (stills, not continuous animation)"


@dataclass(frozen=True)
class Panel:
    caption: str
    state: FaceState
    teeth_visible: bool = False
    tongue_visible: bool = False


def _f(v: float) -> str:
    t = f"{round(v, 3):g}"
    return "0" if t == "-0" else t


def _extent(rig: FacialRig) -> tuple[float, float, float, float]:
    xs, ys = [0.0], [0.0]
    for c in rig.components:
        w, h = c.size
        xs += [c.position.x - w, c.position.x + w]
        ys += [c.position.y - 2 * h - 0.6 * w, c.position.y + 2 * h]
    pad = 0.15 * (max(xs) - min(xs))
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def _component_svg(rc: ResolvedComponent, panel: Panel) -> list[str]:
    cx, cy = rc.center.x, rc.center.y
    rot = f' transform="rotate({_f(rc.rotation)} {_f(cx)} {_f(cy)})"' if rc.rotation else ""
    p = rc.params
    out: list[str] = [f'<g id="c-{rc.id}" data-kind="{rc.kind.value}"{rot}>']
    if rc.kind is ComponentKind.EYE:
        w, h = rc.size
        if rc.visible:
            top, bottom = p["upper_lid_y"], p["lower_lid_y"]
            ry = max(0.0, (bottom - top) / 2)
            mid = (top + bottom) / 2
            out.append(
                f'<ellipse cx="{_f(cx)}" cy="{_f(cy)}" rx="{_f(w / 2)}" ry="{_f(h / 2)}" '
                'fill="none" stroke="#999" stroke-dasharray="3 2"/>'
            )
            out.append(
                f'<ellipse cx="{_f(cx)}" cy="{_f(mid)}" rx="{_f(w / 2)}" ry="{_f(ry)}" '
                'fill="#FFF" stroke="#222" stroke-width="2"/>'
            )
            if ry > 0.15 * h / 2:
                out.append(
                    f'<circle cx="{_f(p["pupil_x"])}" '
                    f'cy="{_f(min(max(p["pupil_y"], top), bottom))}" '
                    f'r="{_f(min(p["pupil_radius"], ry))}" fill="#222"/>'
                )
            out.append(
                f'<line x1="{_f(cx - w / 2)}" y1="{_f(top)}" x2="{_f(cx + w / 2)}" y2="{_f(top)}" '
                'stroke="#C2185B" stroke-width="1.5"/>'
            )
        else:
            out.append(
                f'<text x="{_f(cx)}" y="{_f(cy)}" font-size="8" text-anchor="middle">hidden</text>'
            )
    elif rc.kind is ComponentKind.BROW:
        half = p["length"] / 2
        out.append(
            f'<path d="M{_f(cx - half)},{_f(cy)} Q{_f(cx)},{_f(cy - 2 * p["arch"])} '
            f'{_f(cx + half)},{_f(cy)}" fill="none" stroke="#3E2723" '
            f'stroke-width="{_f(max(2.0, p["thickness"]))}" stroke-linecap="round"/>'
        )
    elif rc.kind is ComponentKind.MOUTH:
        half = p["width"] / 2
        left = Vec2(cx - half, cy + p["corner_r_y"])  # character's right corner = screen left
        right = Vec2(cx + half, cy + p["corner_l_y"])
        top_y = cy + 2 * p["upper_lip_y"] - (p["corner_l_y"] + p["corner_r_y"]) / 2
        bot_y = cy + 2 * p["lower_lip_y"] - (p["corner_l_y"] + p["corner_r_y"]) / 2
        d = (
            f"M{_f(left.x)},{_f(left.y)} Q{_f(cx)},{_f(top_y)} {_f(right.x)},{_f(right.y)} "
            f"Q{_f(cx)},{_f(bot_y)} {_f(left.x)},{_f(left.y)} Z"
        )
        fill = "#5D1A1A" if p["gap"] > 0.5 else "none"
        out.append(f'<path d="{d}" fill="{fill}" stroke="#222" stroke-width="2"/>')
        if panel.teeth_visible and p["gap"] > 0.5:
            out.append(
                f'<rect x="{_f(cx - half * 0.6)}" y="{_f(cy + p["upper_lip_y"])}" '
                f'width="{_f(half * 1.2)}" '
                f'height="{_f(max(1.0, p["gap"] * 0.25))}" fill="#FFF"/>'
            )
        if panel.tongue_visible and p["gap"] > 0.5:
            out.append(
                f'<ellipse cx="{_f(cx)}" cy="{_f(cy + p["gap"] * 0.2)}" rx="{_f(half * 0.4)}" '
                f'ry="{_f(max(1.0, p["gap"] * 0.2))}" fill="#E57373"/>'
            )
        if rc.shape:
            out.append(
                f'<text x="{_f(cx)}" y="{_f(cy + max(p["gap"], 4) + 14)}" font-size="9" '
                f'text-anchor="middle" fill="#555">shape {html.escape(rc.shape)}</text>'
            )
    elif rc.kind is ComponentKind.JAW:
        w, _h = rc.size
        out.append(
            f'<path d="M{_f(cx - w / 2)},{_f(cy)} Q{_f(cx)},{_f(cy + w * 0.25)} '
            f'{_f(cx + w / 2)},{_f(cy)}" '
            'fill="none" stroke="#777" stroke-dasharray="5 3" stroke-width="1.5"/>'
        )
    elif rc.kind is ComponentKind.CHEEK:
        w, h = rc.size
        alpha = 0.15 + 0.5 * p["raise"]
        out.append(
            f'<ellipse cx="{_f(cx)}" cy="{_f(cy)}" rx="{_f(w / 2)}" ry="{_f(h / 2)}" '
            f'fill="#F48FB1" fill-opacity="{_f(alpha)}" stroke="none"/>'
        )
    elif rc.kind is ComponentKind.NOSE:
        w, h = rc.size
        out.append(
            f'<path d="M{_f(cx)},{_f(cy - h / 2)} L{_f(cx + w / 3)},{_f(cy + h / 2)} '
            f'L{_f(cx - w / 3)},{_f(cy + h / 2)}" fill="none" stroke="#555" stroke-width="1.5"/>'
        )
        for i in range(round(3 * p["wrinkle"])):
            yy = cy - h / 2 + 3 + 3 * i
            out.append(
                f'<line x1="{_f(cx - w / 4)}" y1="{_f(yy)}" x2="{_f(cx + w / 4)}" y2="{_f(yy)}" '
                'stroke="#999"/>'
            )
    else:
        w, h = rc.size
        out.append(
            f'<rect x="{_f(cx - w / 2)}" y="{_f(cy - h / 2)}" width="{_f(w)}" height="{_f(h)}" '
            'fill="none" stroke="#6A1B9A" stroke-dasharray="2 2"/>'
        )
    out.append(f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="1.5" fill="#1565C0"/>')  # control location
    out.append("</g>")
    return out


def _panel_svg(
    rig: FacialRig, panel: Panel, x0: float, y0: float, ext: tuple[float, ...], neutral: FaceState
) -> list[str]:
    ex0, ey0, ex1, ey1 = ext
    resolved = resolve_face(rig, panel.state)
    out = [
        f'<g class="panel" data-caption="{html.escape(panel.caption)}" '
        f'transform="translate({_f(x0 - ex0)} {_f(y0 - ey0)})">',
        f'<ellipse cx="{_f((ex0 + ex1) / 2)}" cy="{_f((ey0 + ey1) / 2)}" '
        f'rx="{_f((ex1 - ex0) / 2)}" '
        f'ry="{_f((ey1 - ey0) / 2)}" fill="#FFF3E0" stroke="#BCAAA4"/>',
    ]
    for comp in rig.components:
        out += _component_svg(resolved[comp.id], panel)
    out.append(
        f'<text x="{_f(ex0)}" y="{_f(ey1 + 14)}" font-family="monospace" font-size="11" '
        f'fill="#000">{html.escape(panel.caption)}</text>'
    )
    changed = [
        (k, v)
        for k, v in sorted(panel.state.values.items())
        if abs(v - neutral.values.get(k, v)) > 1e-9
    ]
    for i, (k, v) in enumerate(changed[:24]):
        out.append(
            f'<text x="{_f(ex0)}" y="{_f(ey1 + 28 + 11 * i)}" font-family="monospace" '
            f'font-size="9" fill="#444">{html.escape(k)}={v:.3f}</text>'
        )
    out.append("</g>")
    return out


def render_face_sheet(rig: FacialRig, panels: Sequence[Panel], title: str = "") -> str:
    if not panels:
        raise ValueError("at least one panel is required")
    ext = _extent(rig)
    pw, ph = ext[2] - ext[0], ext[3] - ext[1]
    gap = 30.0
    text_h = 30 + 11 * 24
    width = len(panels) * (pw + gap) + gap
    height = ph + text_h + 70
    banner = BANNER if len(panels) == 1 else SHEET_BANNER
    neutral = neutral_state(rig)
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_f(width)} {_f(height)}" '
        f'width="{_f(width)}" height="{_f(height)}">',
        f"<title>{html.escape(banner + (': ' + title if title else ''))}</title>",
        f'<rect width="{_f(width)}" height="{_f(height)}" fill="#FAFAF7"/>',
        '<text x="10" y="18" font-family="monospace" font-size="13" '
        f'fill="#B00020">{html.escape(banner)}</text>',
        '<text x="10" y="34" font-family="monospace" font-size="11" '
        f'fill="#333">{html.escape(title)}</text>',
    ]
    for i, panel in enumerate(panels):
        out += _panel_svg(rig, panel, gap + i * (pw + gap), 50.0, ext, neutral)
    out.append("</svg>")
    return "\n".join(out) + "\n"


def render_face_svg(rig: FacialRig, state: FaceState, caption: str = "", title: str = "") -> str:
    return render_face_sheet(rig, [Panel(caption or state.label, state)], title)
