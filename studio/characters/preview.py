"""Deterministic diagnostic previews (SVG), pure Python, no rendering dependencies.

A diagnostic shows the *structure*: part boxes in draw order (labelled with z-order),
pivots, bones from head to tip, joints, and optionally an IK target with the solved
chain. Registered part artwork is referenced with ``<image href>`` pointing at the
original file. It is never copied or modified.

A diagnostic is a still inspection aid. It is **not** character animation and not
finished artwork, and the file says so in its title and banner.
"""

from __future__ import annotations

import html
import os
from dataclasses import dataclass
from pathlib import Path

from studio.characters.parts import PartWorld, draw_order, solve_parts
from studio.characters.schemas import CharacterDefinition, ViewDefinition
from studio.core.exceptions import CharacterError
from studio.core.paths import safe_join
from studio.core.registry import AssetRegistry
from studio.rig.fk import FKResult
from studio.rig.ik import IKResult
from studio.rig.math2d import Vec2

PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#B279A2", "#E45756", "#72B7B2", "#EECA3B"]


@dataclass(frozen=True)
class PreviewOptions:
    show_parts: bool = True
    show_bones: bool = True
    show_labels: bool = True
    margin: float = 120.0


def _fmt(v: float) -> str:
    text = f"{round(v, 3):g}"
    return "0" if text == "-0" else text


def _bounds(points: list[Vec2]) -> tuple[float, float, float, float]:
    xs, ys = [p.x for p in points], [p.y for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def render_diagnostic_svg(
    character: CharacterDefinition,
    fk: FKResult | None,
    *,
    view: ViewDefinition | None = None,
    ik: IKResult | None = None,
    registry: AssetRegistry | None = None,
    project_root: Path | None = None,
    output_dir: Path | None = None,
    options: PreviewOptions | None = None,
) -> str:
    opts = options or PreviewOptions()
    parts = solve_parts(character, fk, view)
    order = draw_order(parts)
    pts: list[Vec2] = []
    boxes: dict[str, list[Vec2]] = {}
    part_defs = character.part_map()
    for pid, pw in parts.items():
        b = part_defs[pid].bounds
        if b is not None:
            corners = [
                Vec2(b.x, b.y),
                Vec2(b.x + b.width, b.y),
                Vec2(b.x + b.width, b.y + b.height),
                Vec2(b.x, b.y + b.height),
            ]
            boxes[pid] = [pw.artwork.apply(c) for c in corners]
            pts += boxes[pid]
        pts.append(pw.pivot_world)
    if fk is not None:
        for wb in fk.bones.values():
            pts += [wb.head, wb.tip]
    if ik is not None:
        pts.append(ik.target)
    if not pts:
        raise CharacterError("nothing to draw")
    x0, y0, x1, y1 = _bounds(pts)
    m = opts.margin
    vb = (x0 - m, y0 - m - 50, (x1 - x0) + 2 * m, (y1 - y0) + 2 * m + 50)
    view_name = view.view.value if view else "base"
    banner = "DIAGNOSTIC: structure only (not artwork, not animation)"
    subtitle = f"{character.name} [{character.id} v{character.version}], view {view_name}"
    title = f"{banner}: {subtitle}"
    font = max(8.0, min(18.0, vb[2] / (0.62 * max(len(banner), len(subtitle)) + 24)))
    vx, vy, vw, vh = (_fmt(v) for v in vb)
    out: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="{vx} {vy} {vw} {vh}" width="{vw}" height="{vh}">',
        f"<title>{html.escape(title)}</title>",
        f'<rect x="{vx}" y="{vy}" width="{vw}" height="{vh}" fill="#FAFAF7"/>',
        f'<text x="{_fmt(vb[0] + 12)}" y="{_fmt(vb[1] + font + 6)}" font-family="monospace" '
        f'font-size="{_fmt(font)}" fill="#B00020">{html.escape(banner)}</text>',
        f'<text x="{_fmt(vb[0] + 12)}" y="{_fmt(vb[1] + 2 * font + 12)}" font-family="monospace" '
        f'font-size="{_fmt(font)}" fill="#333">{html.escape(subtitle)}</text>',
    ]
    if opts.show_parts:
        out.append('<g id="parts">')
        for index, pid in enumerate(order):
            pw = parts[pid]
            colour = PALETTE[index % len(PALETTE)]
            out.append(f'<g id="part-{pid}" data-z="{pw.z_order}" opacity="{_fmt(pw.opacity)}">')
            href = _artwork_href(pw, registry, project_root, output_dir)
            b = part_defs[pid].bounds
            if href and b is not None:
                out.append(
                    f'<image href="{html.escape(href)}" x="{_fmt(b.x)}" y="{_fmt(b.y)}" '
                    f'width="{_fmt(b.width)}" height="{_fmt(b.height)}" '
                    f'transform="{pw.artwork.svg()}" preserveAspectRatio="none"/>'
                )
            if pid in boxes:
                path = " ".join(f"{_fmt(p.x)},{_fmt(p.y)}" for p in boxes[pid])
                out.append(
                    f'<polygon points="{path}" fill="{colour}" fill-opacity="0.18" '
                    f'stroke="{colour}" stroke-width="2"/>'
                )
            pv = pw.pivot_world
            out.append(f'<circle cx="{_fmt(pv.x)}" cy="{_fmt(pv.y)}" r="4" fill="{colour}"/>')
            if opts.show_labels:
                out.append(
                    f'<text x="{_fmt(pv.x + 6)}" y="{_fmt(pv.y - 6)}" font-family="monospace" '
                    f'font-size="12" fill="#333">{html.escape(pid)} z{pw.z_order}</text>'
                )
            out.append("</g>")
        out.append("</g>")
    if opts.show_bones and fk is not None:
        out.append('<g id="bones">')
        for bone_id in fk.order:
            wb = fk[bone_id]
            h, t = wb.head, wb.tip
            out.append(
                f'<line id="bone-{bone_id}" x1="{_fmt(h.x)}" y1="{_fmt(h.y)}" x2="{_fmt(t.x)}" '
                f'y2="{_fmt(t.y)}" stroke="#222" stroke-width="3" stroke-linecap="round"/>'
            )
            out.append(
                f'<circle cx="{_fmt(h.x)}" cy="{_fmt(h.y)}" r="6" fill="none" '
                'stroke="#222" stroke-width="2"/>'
            )
        out.append("</g>")
    if ik is not None:
        t = ik.target
        joints = ik.to_dict()["joints"]
        assert isinstance(joints, dict)
        r, mid, end = (Vec2(*joints[k]) for k in ("root", "mid", "end"))
        colour = "#2E7D32" if ik.solution.reached and not ik.limited else "#C62828"
        chain_points = " ".join(f"{_fmt(p.x)},{_fmt(p.y)}" for p in (r, mid, end))
        cross = f"M{_fmt(t.x - 12)},{_fmt(t.y)} h24 M{_fmt(t.x)},{_fmt(t.y - 12)} v24"
        label = f"IK {ik.chain}: {ik.solution.status}{' (limited)' if ik.limited else ''}"
        out += [
            f'<g id="ik-{ik.chain}">',
            f'<polyline points="{chain_points}" fill="none" stroke="{colour}" '
            'stroke-width="5" stroke-opacity="0.7"/>',
            f'<path d="{cross}" stroke="{colour}" stroke-width="3"/>',
            f'<text x="{_fmt(t.x + 14)}" y="{_fmt(t.y + 14)}" font-family="monospace" '
            f'font-size="14" fill="{colour}">{html.escape(label)}</text>',
            "</g>",
        ]
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _artwork_href(
    pw: PartWorld, registry: AssetRegistry | None, root: Path | None, out_dir: Path | None
) -> str | None:
    if pw.asset is None or registry is None or root is None or pw.asset not in registry:
        return None
    path = safe_join(root, registry.get(pw.asset).current.path)
    if not path.is_file():
        return None
    if out_dir is None:
        return path.as_posix()
    return Path(os.path.relpath(path, out_dir)).as_posix()
