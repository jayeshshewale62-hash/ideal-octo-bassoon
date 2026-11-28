"""Animation diagnostic contact sheets (SVG, pure Python, deterministic).

Each panel is the evaluated character at one sampled time: part boxes in draw order,
bones and joints, IK targets (crosses: green reached, red not), deformed mesh outlines
(red for flipped triangles), and a caption with time, clip time, cycle phase, events,
expression and viseme. When the character has a face, a facial-controls panel
(Milestone 4 renderer) sits under the body. A timeline strip under the sheet shows the
clip duration, every keyframe time (ticks), events (diamonds) and the sampled times.

A sheet is a set of **still diagnostics**. It is not animation, and it does not prove
smooth motion or loop continuity. Tests verify those numerically.
"""

from __future__ import annotations

import html
import re
from collections.abc import Sequence

from studio.animation.clip import CompiledClip, sorted_events
from studio.animation.evaluator import CharacterState
from studio.characters.parts import draw_order
from studio.face.preview import render_face_svg
from studio.face.schemas import FacialRig
from studio.rig.math2d import Vec2

BANNER = (
    "DIAGNOSTIC: sampled animation states (stills, not animation; continuity is tested numerically)"
)
PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#B279A2", "#E45756", "#72B7B2", "#EECA3B"]


def _f(v: float) -> str:
    t = f"{round(v, 2):g}"
    return "0" if t == "-0" else t


def _state_points(state: CharacterState) -> list[Vec2]:
    pts: list[Vec2] = []
    for wb in state.fk.bones.values():
        pts += [wb.head, wb.tip]
    parts = state.character.part_map()
    for pid, pw in state.parts.items():
        b = parts[pid].bounds
        if b is not None:
            pts += [
                pw.artwork.apply(Vec2(b.x + dx, b.y + dy))
                for dx in (0, b.width)
                for dy in (0, b.height)
            ]
    for ik in state.ik:
        pts.append(Vec2(*ik["target"]))
    for mesh in state.meshes.values():
        pts += mesh.vertices
    return pts


def _body(state: CharacterState) -> list[str]:
    out: list[str] = []
    parts = state.character.part_map()
    for i, pid in enumerate(draw_order(state.parts)):
        pw, b = state.parts[pid], parts[pid].bounds
        if b is None:
            continue
        corners = [
            pw.artwork.apply(Vec2(b.x + dx, b.y + dy))
            for dx, dy in ((0, 0), (b.width, 0), (b.width, b.height), (0, b.height))
        ]
        colour = PALETTE[i % len(PALETTE)]
        out.append(
            f'<polygon class="part" data-part="{pid}" '
            f'points="{" ".join(f"{_f(p.x)},{_f(p.y)}" for p in corners)}" '
            f'fill="{colour}" fill-opacity="{_f(0.15 * pw.opacity)}" stroke="{colour}" '
            'stroke-width="2"/>'
        )
    for mesh in state.meshes.values():
        for ti, (a, b2, c) in enumerate(mesh.triangles):
            pa, pb, pc = mesh.vertices[a], mesh.vertices[b2], mesh.vertices[c]
            stroke = "#D32F2F" if ti in mesh.flipped else "#6A1B9A"
            out.append(
                f'<polygon class="mesh" points="{_f(pa.x)},{_f(pa.y)} {_f(pb.x)},{_f(pb.y)} '
                f'{_f(pc.x)},{_f(pc.y)}" '
                f'fill="none" stroke="{stroke}" stroke-width="1"/>'
            )
    for bone in state.fk.order:
        wb = state.fk[bone]
        out.append(
            f'<line class="bone" data-bone="{bone}" x1="{_f(wb.head.x)}" y1="{_f(wb.head.y)}" '
            f'x2="{_f(wb.tip.x)}" y2="{_f(wb.tip.y)}" stroke="#222" stroke-width="4" '
            'stroke-linecap="round"/>'
        )
        out.append(
            f'<circle cx="{_f(wb.head.x)}" cy="{_f(wb.head.y)}" r="6" fill="#FFF" stroke="#222" '
            'stroke-width="2"/>'
        )
    for ik in state.ik:
        x, y = ik["target"]
        colour = "#2E7D32" if ik["status"] == "reached" and not ik["limited"] else "#C62828"
        out.append(
            f'<path class="ik-target" d="M{_f(x - 14)},{_f(y)} h28 M{_f(x)},{_f(y - 14)} v28" '
            f'stroke="{colour}" stroke-width="3"/>'
        )
    return out


def _embed(svg: str, x: float, y: float, width: float, height: float) -> str:
    body = re.sub(r"^<\?xml[^>]*>\s*", "", svg)
    body = re.sub(
        r'(<svg [^>]*?)\swidth="[^"]*"\sheight="[^"]*"',
        rf'\1 x="{_f(x)}" y="{_f(y)}" width="{_f(width)}" height="{_f(height)}"',
        body,
        count=1,
    )
    return body


def render_animation_sheet(
    states: Sequence[CharacterState],
    *,
    title: str,
    face: FacialRig | None = None,
    timeline: CompiledClip | None = None,
    columns: int = 6,
) -> str:
    if not states:
        raise ValueError("at least one state is required")
    pts = [p for s in states for p in _state_points(s)]
    x0, x1 = min(p.x for p in pts) - 60, max(p.x for p in pts) + 60
    y0, y1 = min(p.y for p in pts) - 60, max(p.y for p in pts) + 60
    body_w, body_h = 300.0, 300.0 * (y1 - y0) / max(1.0, x1 - x0)
    face_h = 260.0 if face is not None and any(s.face for s in states) else 0.0
    cap_h, gap = 64.0, 20.0
    cols = max(1, min(columns, len(states)))
    rows = (len(states) + cols - 1) // cols
    cell_h = body_h + face_h + cap_h
    timeline_h = 70.0 if timeline is not None else 0.0
    width = gap + cols * (body_w + gap)
    height = 60 + rows * (cell_h + gap) + timeline_h
    scale = body_w / (x1 - x0)
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_f(width)} {_f(height)}" '
        f'width="{_f(width)}" height="{_f(height)}">',
        f"<title>{html.escape(BANNER + ': ' + title)}</title>",
        f'<rect width="{_f(width)}" height="{_f(height)}" fill="#FAFAF7"/>',
        '<text x="10" y="20" font-family="monospace" font-size="13" '
        f'fill="#B00020">{html.escape(BANNER)}</text>',
        '<text x="10" y="38" font-family="monospace" font-size="12" '
        f'fill="#333">{html.escape(title)}</text>',
    ]
    for i, state in enumerate(states):
        cx = gap + (i % cols) * (body_w + gap)
        cy = 50 + (i // cols) * (cell_h + gap)
        out.append(
            f'<g class="frame" data-time="{state.time:g}" transform="translate({_f(cx)} {_f(cy)})">'
        )
        out.append(f'<rect width="{_f(body_w)}" height="{_f(body_h)}" fill="#FFF" stroke="#DDD"/>')
        out.append(f'<g transform="scale({scale:.6f}) translate({_f(-x0)} {_f(-y0)})">')
        out += _body(state)
        out.append("</g>")
        if face_h and state.face is not None and face is not None:
            out.append(
                _embed(
                    render_face_svg(face, state.face, caption=state.face.label),
                    0,
                    body_h,
                    body_w,
                    face_h,
                )
            )
        layer = state.layers[0] if state.layers else None
        phase = f" phase {layer.phase:.2f}" if layer and layer.phase is not None else ""
        lines = [
            f"t={state.time:.3f}s clip {layer.clip}@{layer.clip_time:.3f}{phase}"
            if layer
            else f"t={state.time:.3f}s"
        ]
        extra = []
        if state.face is not None:
            extra.append(f"expr {state.face.label.split('+')[0]}")
        if state.lips is not None:
            extra.append(f"viseme {state.lips.dominant}")
        if state.events:
            extra.append("events " + ",".join(e["name"] for e in state.events))
        warn = [d for d in state.diagnostics if d.severity != "info"]
        if warn:
            extra.append(f"{len(warn)} warning(s)")
        lines.append(" | ".join(extra))
        for j, line in enumerate(lines):
            out.append(
                f'<text x="2" y="{_f(body_h + face_h + 16 + 14 * j)}" font-family="monospace" '
                'font-size="10" '
                f'fill="#222">{html.escape(line)}</text>'
            )
        out.append("</g>")
    if timeline is not None:
        clip = timeline.clip
        ty = height - timeline_h + 20
        tw = width - 2 * gap
        sx = tw / clip.duration
        out.append(f'<g class="timeline" transform="translate({_f(gap)} {_f(ty)})">')
        out.append(f'<line x1="0" y1="10" x2="{_f(tw)}" y2="10" stroke="#555" stroke-width="2"/>')
        keys = sorted({t for times in timeline.key_times.values() for t in times})
        for t in keys:
            out.append(
                f'<line class="key" x1="{_f(t * sx)}" y1="2" x2="{_f(t * sx)}" y2="18" '
                'stroke="#1565C0"/>'
            )
        for t, ev in sorted_events(clip):
            out.append(
                f'<path class="event" d="M{_f(t * sx)},24 l5,6 l-5,6 l-5,-6 z" fill="#F57C00">'
                f"<title>{html.escape(ev.name)}</title></path>"
            )
        for s in states:
            for layer in s.layers[:1]:
                out.append(
                    f'<circle class="sample" cx="{_f(layer.clip_time * sx)}" cy="10" r="4" '
                    'fill="#C62828"/>'
                )
        out.append(
            '<text x="0" y="52" font-family="monospace" font-size="10" fill="#333">clip '
            f"{html.escape(clip.id)}: "
            f"{clip.duration:g}s, {len(keys)} key times (blue), {len(clip.events)} events "
            "(orange), "
            f"samples (red)</text>"
        )
        out.append("</g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"
