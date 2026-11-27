"""``studio character ...`` commands (Milestone 3)."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from studio.characters.consistency import compare_characters
from studio.characters.manager import CharacterStore
from studio.characters.parts import draw_order, solve_parts
from studio.characters.preview import render_diagnostic_svg
from studio.characters.schemas import ViewDefinition
from studio.characters.templates import TEMPLATES
from studio.characters.validation import validate_turnaround
from studio.core.config import Settings
from studio.core.exceptions import CharacterError, StudioError
from studio.core.paths import to_relative
from studio.core.project import Project
from studio.core.schemas import TurnaroundView
from studio.core.validation import ValidationReport, write_text_atomic
from studio.rig.fk import parse_rotation_overrides, solve_fk
from studio.rig.ik import solve_ik_chain
from studio.rig.math2d import Vec2
from studio.rig.validation import validate_rig

Handler = Callable[[argparse.Namespace, Settings], int]
VIEWS = [v.value for v in TurnaroundView]


def _json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _report(report: ValidationReport, as_json: bool) -> int:
    if as_json:
        _json(report.to_dict())
    else:
        for issue in report.issues:
            print(issue)
        verdict = "VALID" if report.ok else "INVALID"
        print(
            f"{verdict}: {report.subject} ({report.checks} checks, "
            f"{len(report.errors)} errors, {len(report.warnings)} warnings)"
        )
    return 0 if report.ok else 1


def _store(args: argparse.Namespace) -> CharacterStore:
    return CharacterStore(Project.load(Path(args.path)))


def _view(store: CharacterStore, char_id: str, name: str | None) -> ViewDefinition | None:
    if name is None:
        return None
    char = store.load(char_id).character
    found = char.turnaround.get(TurnaroundView(name))
    if found is None:
        raise CharacterError(f"{char_id} has no {name} view")
    return found


# --- commands ------------------------------------------------------------------------------


def cmd_templates(args: argparse.Namespace, settings: Settings) -> int:
    if args.json:
        _json([{"name": t.name, "description": t.description} for t in TEMPLATES.values()])
    else:
        for t in TEMPLATES.values():
            print(f"{t.name:15} {t.description}")
    return 0


def cmd_create(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    loaded = store.create(
        args.name,
        template=args.template,
        character_id=args.id,
        description=args.description or "",
        height_heads=args.height_heads,
        height_units=args.height_units,
        from_character=args.from_character,
    )
    c = loaded.character
    rel = to_relative(store.project.root, loaded.folder)
    print(f"created character {c.id} '{c.name}' v{c.version} in {rel}/")
    print(
        f"  parts: {len(c.parts)}, bones: {len(loaded.rig.bones) if loaded.rig else 0}, "
        f"IK chains: {len(loaded.rig.ik_chains) if loaded.rig else 0}, "
        f"views: {', '.join(v.view.value for v in c.turnaround.views)}"
    )
    print(
        "  no artwork was created; assign registered assets with 'studio character set-part-asset'"
    )
    return _report(store.validate(c.id), as_json=False)


def cmd_list(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    rows = []
    for cid in store.ids():
        try:
            c = store.load(cid).character
            rows.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "version": c.version,
                    "status": c.status.value,
                    "parts": len(c.parts),
                    "rig": c.rig,
                    "template": c.template,
                }
            )
        except StudioError as exc:  # the list must survive one broken file
            rows.append({"id": cid, "error": str(exc).splitlines()[0]})
    if args.json:
        _json(rows)
    elif not rows:
        print(f"no characters in {store.project.metadata.slug}")
    else:
        for r in rows:
            if "error" in r:
                print(f"{r['id']:28} ERROR {r['error']}")
            else:
                print(
                    f"{r['id']:28} v{r['version']:<3} {r['status']:9} parts={r['parts']:<3} "
                    f"rig={r['rig']}  {r['name']}"
                )
        print(f"{len(rows)} character(s)")
    return 0


def cmd_info(args: argparse.Namespace, settings: Settings) -> int:
    loaded = _store(args).load(args.character)
    c, rig = loaded.character, loaded.rig
    if args.json:
        _json(
            {
                "character": c.model_dump(mode="json"),
                "rig": rig.model_dump(mode="json") if rig else None,
            }
        )
        return 0
    ident = c.identity
    print(f"{c.id}  '{c.name}'  v{c.version}  status={c.status.value}  template={c.template}")
    print(
        f"  height {ident.height_units:g} units = {ident.proportions.height_heads:g} heads; "
        f"head {ident.head.shape}, width ratio {ident.head.width_ratio:g}"
    )
    print(f"  palette: {', '.join(f'{k}={v}' for k, v in ident.palette.items()) or '(none)'}")
    print(f"  parts ({len(c.parts)}):")
    for p in sorted(c.parts, key=lambda p: (p.z_order, p.id)):
        print(
            f"    z{p.z_order:<4} {p.id:14} {p.kind.value:13} {p.side.value:6} "
            f"bone={p.bone or '-':12} parent={p.parent or '-':12} asset={p.asset or '-'}"
        )
    if rig:
        print(
            f"  rig {rig.id} v{rig.version}: {len(rig.bones)} bones, root {rig.root}, "
            f"IK chains {', '.join(ch.id for ch in rig.ik_chains) or '-'}"
        )
    print(
        "  views: "
        + ", ".join(
            f"{v.view.value}{'' if (v.artwork or v.part_assets) else ' (no artwork)'}"
            for v in c.turnaround.views
        )
    )
    return 0


def cmd_validate(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    ids = [args.character] if args.character else store.ids()
    if not ids:
        print("no characters to validate")
        return 0
    combined = ValidationReport(subject=", ".join(ids))
    for cid in ids:
        combined.extend(store.validate(cid))
    return _report(combined, args.json)


def cmd_set_part_asset(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    view = TurnaroundView(args.view) if args.view else None
    c = store.set_part_asset(args.character, args.part, args.asset_id, view)
    where = f"view {args.view}" if args.view else "all views (base)"
    print(f"{c.id} v{c.version}: part {args.part} -> {args.asset_id} ({where})")
    return 0


def cmd_set_view_artwork(args: argparse.Namespace, settings: Settings) -> int:
    c = _store(args).set_view_artwork(args.character, TurnaroundView(args.view), args.asset_id)
    print(f"{c.id} v{c.version}: view {args.view} artwork -> {args.asset_id}")
    return 0


def cmd_compare(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    base = store.load(args.character).character
    if args.with_character:
        other = store.load(args.with_character).character
    elif args.version is not None:
        other = store.load_version(args.character, args.version)
    else:
        raise CharacterError("pass --version N or --with CHARACTER")
    report = compare_characters(
        other if args.version is not None else base, base if args.version is not None else other
    )
    if args.json:
        _json(report.to_dict())
    else:
        print(f"identity comparison: {report.base}  ->  {report.other}")
        if not report.differences:
            print("  no identity differences")
        for d in report.differences:
            print(f"  {d.severity.upper():7} {d.role.value:13} {d.prop}: {d.base!r} -> {d.other!r}")
        print(
            "CONSISTENT"
            if report.consistent
            else "INCONSISTENT: required identity properties differ"
        )
    return 0 if report.consistent else 1


def cmd_rig_validate(args: argparse.Namespace, settings: Settings) -> int:
    loaded = _store(args).load(args.character)
    if loaded.rig is None:
        raise CharacterError(f"{args.character} has no rig")
    report = ValidationReport(subject=f"rig {loaded.rig.id}")
    validate_rig(loaded.rig, report, "rig.yaml")
    return _report(report, args.json)


def cmd_rig_fk(args: argparse.Namespace, settings: Settings) -> int:
    loaded = _store(args).load(args.character)
    if loaded.rig is None:
        raise CharacterError(f"{args.character} has no rig")
    pose = parse_rotation_overrides(args.rot or [])
    fk = solve_fk(loaded.rig, pose)
    data = {
        "rig": loaded.rig.id,
        "pose": {k: v.rotation for k, v in pose.items()},
        "constraint_events": [e.__dict__ for e in fk.events],
        "bones": [fk[b].to_dict() for b in fk.order],
    }
    part_order: list[str] = []
    if args.parts:
        parts = solve_parts(loaded.character, fk, _view(_store(args), args.character, args.view))
        part_order = draw_order(parts, include_hidden=True)
        data["parts"] = [parts[p].to_dict() for p in part_order]
    if args.json:
        _json(data)
        return 0
    print(f"FK {loaded.rig.id}: {len(fk.order)} bones (character space, +y down, degrees)")
    for b in fk.order:
        wb = fk[b]
        hx, hy = wb.head.rounded(2)
        tx, ty = wb.tip.rounded(2)
        print(
            f"  {b:12} head=({hx:9.2f},{hy:9.2f}) tip=({tx:9.2f},{ty:9.2f}) "
            f"local={wb.local_rotation:8.2f} world={wb.world_rotation:8.2f}"
        )
    for e in fk.events:
        print(f"  CONSTRAINT {e.bone}: requested {e.requested:g} -> {e.applied:g} ({e.reason})")
    if args.parts:
        print("  parts back-to-front: " + ", ".join(part_order))
    return 0


def cmd_rig_ik(args: argparse.Namespace, settings: Settings) -> int:
    loaded = _store(args).load(args.character)
    if loaded.rig is None:
        raise CharacterError(f"{args.character} has no rig")
    pose = parse_rotation_overrides(args.rot or [])
    pole = Vec2(*args.pole) if args.pole else None
    result = solve_ik_chain(loaded.rig, args.chain, Vec2(*args.target), pole=pole, pose=pose)
    data = result.to_dict()
    if args.json:
        _json(data)
    else:
        joints = data["joints"]
        assert isinstance(joints, dict)
        tx, ty = result.target.rounded(4)
        print(
            f"IK {args.chain} -> target ({tx:g}, {ty:g}): {result.solution.status}"
            f"{' (joint limits applied)' if result.limited else ''}"
        )
        print(f"  rotations: {data['rotations']}")
        print(
            f"  root {tuple(joints['root'])}  mid {tuple(joints['mid'])}  "
            f"end {tuple(joints['end'])}"
        )
        print(f"  distance from end to target: {data['error']}")
        for e in result.limit_events:
            print(f"  LIMIT {e.bone}: {e.requested:.3f} -> {e.applied:.3f} ({e.reason})")
    return 0 if result.solution.reached and not result.limited else 3


def cmd_turnaround_validate(args: argparse.Namespace, settings: Settings) -> int:
    char = _store(args).load(args.character).character
    report = ValidationReport(subject=f"turnaround of {char.id}")
    validate_turnaround(char, report, f"characters/{char.id}/character.yaml")
    return _report(report, args.json)


def cmd_preview(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    loaded = store.load(args.character)
    view = _view(store, args.character, args.view)
    fk = None
    ik = None
    if loaded.rig is not None:
        pose = parse_rotation_overrides(args.rot or [])
        if args.ik:
            chain, x, y = args.ik
            try:
                target = Vec2(float(x), float(y))
            except ValueError:
                raise CharacterError(f"--ik target must be two numbers, got {x!r} {y!r}") from None
            ik = solve_ik_chain(loaded.rig, chain, target, pose=pose)
            fk = ik.fk
        else:
            fk = solve_fk(loaded.rig, pose)
    root = store.project.root
    out = (
        Path(args.out)
        if args.out
        else root
        / "renders"
        / "previews"
        / (f"{loaded.character.id}-{args.view or 'base'}-diagnostic.svg")
    )
    out = out if out.is_absolute() else Path.cwd() / out
    registry = store.project.registry()
    protected = {(root / v.path).resolve() for r in registry for v in r.versions}
    if out.resolve() in protected:
        raise CharacterError(f"{out} is a registered asset; refusing to overwrite it")
    if out.exists() and not args.force and "renders" not in out.resolve().parts:
        raise CharacterError(f"{out} exists; use --force to replace it")
    svg = render_diagnostic_svg(
        loaded.character,
        fk,
        view=view,
        ik=ik,
        registry=registry,
        project_root=root,
        output_dir=out.parent,
    )
    write_text_atomic(out, svg)
    print(f"wrote diagnostic preview {out} ({len(svg)} bytes)")
    print("  structure diagnostic only: not artwork and not animation")
    return 0


# --- parser --------------------------------------------------------------------------------


def register(
    sub: Any,
    add: Callable[[Any, str, Handler, str], argparse.ArgumentParser],
    json_flag: Callable[[argparse.ArgumentParser], None],
    missing: Callable[[argparse.ArgumentParser], int],
) -> None:
    p_char = add(sub, "character", lambda a, s: missing(p_char), "character commands (milestone 3)")
    ch = p_char.add_subparsers(dest="character_command", metavar="ACTION")

    def project_char(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("path", help="project folder, e.g. projects/demo")
        p.add_argument("character", help="character id, e.g. chr_mira")
        return p

    json_flag(add(ch, "templates", cmd_templates, "list character templates"))

    p = add(ch, "create", cmd_create, "create a character (structure + rig, no artwork)")
    p.add_argument("path", help="project folder")
    p.add_argument("name", help="character name")
    p.add_argument("--id", help="character id (default: chr_<name>)")
    p.add_argument("--template", default="biped", choices=sorted(TEMPLATES))
    p.add_argument(
        "--from",
        dest="from_character",
        metavar="CHARACTER",
        help="reuse another character's structure (artwork references are not copied)",
    )
    p.add_argument("--description")
    p.add_argument("--height-heads", type=float, default=5.0, help="height in head-heights")
    p.add_argument("--height-units", type=float, default=1000.0, help="height in design units")

    p = add(ch, "list", cmd_list, "list characters in a project")
    p.add_argument("path")
    json_flag(p)

    json_flag(project_char(add(ch, "info", cmd_info, "show a character")))

    p = add(ch, "validate", cmd_validate, "validate one or all characters")
    p.add_argument("path")
    p.add_argument("character", nargs="?")
    json_flag(p)

    p = project_char(
        add(
            ch,
            "set-part-asset",
            cmd_set_part_asset,
            "assign registered artwork to a part (new character version)",
        )
    )
    p.add_argument("part")
    p.add_argument("asset_id")
    p.add_argument("--view", choices=VIEWS, help="only for this turnaround view")

    p = project_char(
        add(
            ch,
            "set-view-artwork",
            cmd_set_view_artwork,
            "assign a registered turnaround drawing to a view (new version)",
        )
    )
    p.add_argument("view", choices=VIEWS)
    p.add_argument("asset_id")

    p = project_char(
        add(
            ch,
            "compare",
            cmd_compare,
            "compare identity metadata with another version or character",
        )
    )
    p.add_argument("--version", type=int, help="earlier version of the same character")
    p.add_argument("--with", dest="with_character", help="another character (e.g. a variant)")
    json_flag(p)

    p_rig = add(ch, "rig", lambda a, s: missing(p_rig), "rig commands")
    rig = p_rig.add_subparsers(dest="rig_command", metavar="ACTION")
    json_flag(project_char(add(rig, "validate", cmd_rig_validate, "validate a character's rig")))
    p = project_char(add(rig, "fk", cmd_rig_fk, "evaluate forward kinematics"))
    p.add_argument(
        "--rot",
        action="append",
        metavar="BONE=DEGREES",
        help="local rotation override (repeatable)",
    )
    p.add_argument("--parts", action="store_true", help="include part transforms and draw order")
    p.add_argument("--view", choices=VIEWS)
    json_flag(p)
    p = project_char(
        add(rig, "ik", cmd_rig_ik, "solve a two-bone IK chain (exit 3 if not reached)")
    )
    p.add_argument("chain", help="IK chain id, e.g. arm_l")
    p.add_argument("--target", nargs=2, type=float, required=True, metavar=("X", "Y"))
    p.add_argument("--pole", nargs=2, type=float, metavar=("X", "Y"))
    p.add_argument("--rot", action="append", metavar="BONE=DEGREES")
    json_flag(p)

    p_ta = add(ch, "turnaround", lambda a, s: missing(p_ta), "turnaround commands")
    ta = p_ta.add_subparsers(dest="turnaround_command", metavar="ACTION")
    json_flag(
        project_char(
            add(
                ta,
                "validate",
                cmd_turnaround_validate,
                "validate turnaround views and identity overrides",
            )
        )
    )

    p = project_char(
        add(ch, "preview", cmd_preview, "write a diagnostic SVG (structure only, not artwork)")
    )
    p.add_argument("--view", choices=VIEWS)
    p.add_argument("--rot", action="append", metavar="BONE=DEGREES")
    p.add_argument("--ik", nargs=3, metavar=("CHAIN", "X", "Y"))
    p.add_argument("--out", help="output .svg (default: <project>/renders/previews/)")
    p.add_argument("--force", action="store_true", help="replace an existing file outside renders/")
