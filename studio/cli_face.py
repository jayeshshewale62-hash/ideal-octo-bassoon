"""``studio face ...`` commands (Milestone 4)."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from studio.core.config import Settings
from studio.core.exceptions import FaceError, LipSyncError
from studio.core.project import Project
from studio.core.schemas import ProviderKind
from studio.core.validation import (
    ValidationReport,
    load_model,
    model_to_yaml,
    write_text_atomic,
)
from studio.face.alignment import align_audio, phoneme_events, summarize
from studio.face.expressions import (
    FaceState,
    blend_expressions,
    evaluate_expression,
)
from studio.face.geometry import resolve_face
from studio.face.library import load_phoneme_map, load_viseme_set, phoneme_map_names
from studio.face.lipsync import LipSyncEvaluator, apply_lipsync, validate_track
from studio.face.manager import FaceStore
from studio.face.phonemes import map_phonemes
from studio.face.preview import Panel, render_face_sheet
from studio.face.schemas import AlignmentDocument, Ease, LipSyncSettings, LipSyncTrack
from studio.face.templates import TEMPLATES
from studio.providers import resolve_selection

Handler = Callable[[argparse.Namespace, Settings], int]


def _json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _report(report: ValidationReport, as_json: bool) -> int:
    if as_json:
        _json(report.to_dict())
    else:
        for issue in report.issues:
            print(issue)
        print(
            f"{'VALID' if report.ok else 'INVALID'}: {report.subject} ({report.checks} checks, "
            f"{len(report.errors)} errors, {len(report.warnings)} warnings)"
        )
    return 0 if report.ok else 1


def _store(args: argparse.Namespace) -> FaceStore:
    return FaceStore(Project.load(Path(args.path)))


def _parse_values(items: list[str] | None) -> dict[str, float]:
    values: dict[str, float] = {}
    for item in items or []:
        key, sep, raw = item.partition("=")
        if not sep or "." not in key:
            raise FaceError(f"expected COMPONENT.CONTROL=VALUE, got {item!r}")
        try:
            value = float(raw)
        except ValueError:
            raise FaceError(f"value for {key!r} is not a number: {raw!r}") from None
        if not math.isfinite(value):
            raise FaceError(f"value for {key!r} must be finite")
        values[key] = value
    return values


def _parse_shapes(items: list[str] | None) -> dict[str, str]:
    shapes = {}
    for item in items or []:
        comp, sep, shape = item.partition("=")
        if not sep or not comp or not shape:
            raise FaceError(f"expected COMPONENT=SHAPE, got {item!r}")
        shapes[comp] = shape
    return shapes


def _write_out(path: Path, text: str, force: bool) -> None:
    if path.exists() and not force and "renders" not in path.resolve().parts:
        raise FaceError(f"{path} exists; use --force to replace it")
    write_text_atomic(path, text)


def _default_preview(store: FaceStore, char_id: str, name: str) -> Path:
    return store.project.root / "renders" / "previews" / f"{char_id}-face-{name}.svg"


def _issues(state: FaceState) -> None:
    for issue in state.issues:
        print(f"  {issue.severity.upper()} {issue.code}: {issue.message}")


# --- face rig ------------------------------------------------------------------------------


def cmd_create(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    loaded = store.create(args.character, args.template)
    f = loaded.face
    print(
        f"created facial rig {f.id} for {f.character_id} (character now "
        f"v{loaded.character.version})"
    )
    print(f"  components: {', '.join(c.id for c in f.components)}")
    print(f"  controls: {len(f.keys())}; no facial artwork was created")
    return _report(store.validate(args.character), as_json=False)


def cmd_info(args: argparse.Namespace, settings: Settings) -> int:
    face = _store(args).load(args.character).face
    if args.json:
        _json(face.model_dump(mode="json"))
        return 0
    print(
        f"{face.id} v{face.version} for {face.character_id}, template {face.template}, "
        f"anchor {face.anchor.part}@({face.anchor.position.x:g},{face.anchor.position.y:g})"
    )
    for c in face.components:
        art = c.asset or (
            "shapes:" + ",".join(k for k, v in c.shapes.items() if v)
            if any(c.shapes.values())
            else "-"
        )
        print(
            f"  {c.id:8} {c.kind.value:9} at ({c.position.x:8.2f},{c.position.y:8.2f}) "
            f"size {c.size[0]:.1f}x{c.size[1]:.1f}  art={art}{'  (optional)' if c.optional else ''}"
        )
        print(
            "           "
            + ", ".join(f"{ch.name}[{ch.min:g}..{ch.max:g}]={ch.default:g}" for ch in c.channels)
        )
    return 0


def cmd_validate(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    store.load(args.character)  # clear error if there is no face
    return _report(store.validate(args.character), args.json)


def cmd_set_asset(args: argparse.Namespace, settings: Settings) -> int:
    face = _store(args).set_component_asset(
        args.character, args.component, args.asset_id, args.shape
    )
    where = f"shape {args.shape}" if args.shape else "default artwork"
    print(f"{face.id} v{face.version}: {args.component} {where} -> {args.asset_id}")
    return 0


# --- expressions ---------------------------------------------------------------------------


def cmd_expr_list(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    face = store.load(args.character).face
    rows = []
    for e in store.list_expressions(args.character):
        st = evaluate_expression(face, e)
        rows.append(
            {
                "id": e.id,
                "name": e.name,
                "kind": "built-in" if e.builtin else "custom",
                "version": e.version,
                "controls": len(e.values),
                "warnings": len([i for i in st.issues if i.severity == "warning"]),
                "errors": len([i for i in st.issues if i.severity == "error"]),
            }
        )
    if args.json:
        _json(rows)
        return 0
    for r in rows:
        print(
            f"{r['id']:12} {r['kind']:8} v{r['version']:<3} controls={r['controls']:<3} "
            f"warnings={r['warnings']} errors={r['errors']}  {r['name']}"
        )
    print(f"{len(rows)} expression(s)")
    return 0


def cmd_expr_create(args: argparse.Namespace, settings: Settings) -> int:
    expr = _store(args).create_expression(
        args.character,
        args.id,
        args.name,
        base=args.from_expression,
        values=_parse_values(args.set),
        shapes=_parse_shapes(args.shape),
        description=args.description or "",
    )
    print(
        f"created expression {expr.id} v{expr.version} ({len(expr.values)} controls) for rig "
        f"{expr.rig}"
    )
    return 0


def cmd_expr_set(args: argparse.Namespace, settings: Settings) -> int:
    expr = _store(args).update_expression(
        args.character, args.id, _parse_values(args.set), _parse_shapes(args.shape)
    )
    print(f"expression {expr.id} is now v{expr.version}")
    return 0


def cmd_expr_preview(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    face = store.load(args.character).face
    names = args.expressions or ["neutral"]
    panels = []
    for name in names:
        st = evaluate_expression(face, store.get_expression(args.character, name))
        panels.append(Panel(f"expression {name}", st))
    if args.json:
        _json(
            {
                p.caption: {
                    "state": p.state.to_dict(),
                    "geometry": {k: v.to_dict() for k, v in resolve_face(face, p.state).items()},
                }
                for p in panels
            }
        )
        return 0
    out = Path(args.out) if args.out else _default_preview(store, args.character, "-".join(names))
    _write_out(out, render_face_sheet(face, panels, f"{face.id} v{face.version}"), args.force)
    for p in panels:
        _issues(p.state)
    print(f"wrote {out} ({len(panels)} panel(s)); diagnostic only, not artwork or animation")
    return 0


def cmd_expr_blend(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    face = store.load(args.character).face
    a = store.get_expression(args.character, args.a)
    b = store.get_expression(args.character, args.b)
    state = blend_expressions(face, a, b, args.weight, Ease(args.ease))
    if args.json:
        _json(state.to_dict())
    else:
        print(state.label)
        for key, value in sorted(state.values.items()):
            ch = face.channel(key)
            if ch is not None and abs(value - ch.default) > 1e-9:
                print(f"  {key:22} {value:8.4f}")
        _issues(state)
    if args.out:
        start = evaluate_expression(face, a)
        end = evaluate_expression(face, b)
        panels = [
            Panel(f"{args.a} (w=0)", start),
            Panel(state.label, state),
            Panel(f"{args.b} (w=1)", end),
        ]
        _write_out(Path(args.out), render_face_sheet(face, panels, "expression blend"), args.force)
        print(f"wrote {args.out}")
    return 0


# --- visemes, phonemes, lip-sync -------------------------------------------------------------


def cmd_visemes_list(args: argparse.Namespace, settings: Settings) -> int:
    vs = load_viseme_set(args.set)
    if args.json:
        _json(vs.model_dump(mode="json"))
        return 0
    print(f"viseme set {vs.id} (rest: {vs.rest})")
    for v in vs.visemes:
        flags = ("teeth " if v.teeth_visible else "") + ("tongue" if v.tongue_visible else "")
        print(f"  {v.id:5} {v.name:30} {flags:13} {v.articulation}")
    return 0


def cmd_maps_list(args: argparse.Namespace, settings: Settings) -> int:
    rows = []
    for name in phoneme_map_names():
        m = load_phoneme_map(name)
        rows.append(
            {
                "id": m.id,
                "language": m.language,
                "alphabet": m.alphabet,
                "phonemes": len(m.map),
                "unknown": m.unknown,
            }
        )
    if args.json:
        _json(rows)
    else:
        for r in rows:
            print(
                f"{r['id']:12} lang={r['language']:4} {r['phonemes']:3} phonemes  "
                f"unknown->{r['unknown']:8} {r['alphabet']}"
            )
    return 0


def cmd_phonemes_map(args: argparse.Namespace, settings: Settings) -> int:
    doc = load_model(AlignmentDocument, Path(args.alignment))
    pmap = load_phoneme_map(args.map)
    vs = load_viseme_set(args.visemes)
    result = map_phonemes(
        phoneme_events(doc),
        pmap,
        vs,
        merge_adjacent=not args.no_merge,
        fill_silence=not args.no_silence,
    )
    track = LipSyncTrack(
        id=args.id or Path(args.alignment).name.split(".")[0].replace("-", "_").lower() or "track",
        character_id=args.character,
        viseme_set=vs.id,
        phoneme_map=pmap.id,
        duration=doc.duration,
        settings=LipSyncSettings(
            transition=args.transition, coarticulation=args.coarticulation, ease=Ease(args.ease)
        ),
        events=result.events,
    )
    for w in result.warnings:
        print(f"WARNING {w}")
    if args.json:
        _json(track.model_dump(mode="json"))
    else:
        print(
            f"{len(doc.phonemes)} phonemes -> {len(track.events)} viseme events (map {pmap.id}, "
            f"set {vs.id})"
        )
        for e in track.events:
            print(
                f"  {e.start:8.3f}-{e.end:8.3f}  {e.viseme:5} {e.source:8} {' '.join(e.phonemes)}"
            )
    if args.out:
        _write_out(Path(args.out), model_to_yaml(track), args.force)
        print(f"wrote {args.out}")
    return 0


def _load_track(path: str, visemes: str) -> tuple[LipSyncTrack, Any]:
    track = load_model(LipSyncTrack, Path(path))
    vs = load_viseme_set(visemes)
    return track, vs


def cmd_lipsync_validate(args: argparse.Namespace, settings: Settings) -> int:
    track, vs = _load_track(args.track, args.visemes)
    report = ValidationReport(subject=f"lip-sync track {track.id}")
    report.checks += 1 + len(track.events)
    for problem in validate_track(track, vs):
        code, _, message = problem.partition(" ")
        report.error(code, message, args.track)
    return _report(report, args.json)


def _times(args: argparse.Namespace, track: LipSyncTrack) -> list[float]:
    if args.time is not None:
        times = list(args.time)
    elif args.sample:
        end = (
            args.until
            if args.until is not None
            else (track.duration or (track.events[-1].end if track.events else 0))
        )
        if args.sample <= 0 or not math.isfinite(args.sample):
            raise LipSyncError("--sample must be a positive number of seconds")
        n = math.floor(end / args.sample + 1e-9) + 1
        if n > 400:
            raise LipSyncError(f"{n} samples requested; use a larger --sample (max 400)")
        times = [round(i * args.sample, 9) for i in range(n)]
    else:
        raise LipSyncError("pass --time T (repeatable) or --sample STEP")
    return times


def cmd_lipsync_evaluate(args: argparse.Namespace, settings: Settings) -> int:
    track, vs = _load_track(args.track, args.visemes)
    ev = LipSyncEvaluator(track, vs)
    states = [ev.evaluate(t) for t in _times(args, track)]
    if args.json:
        _json([s.to_dict() for s in states])
        return 0
    for s in states:
        weights = " ".join(f"{k}:{v:.3f}" for k, v in sorted(s.weights.items()))
        print(
            f"t={s.time:8.3f}  segment={s.viseme:5} dominant={s.dominant:5} "
            f"open={s.values.get('mouth.open', 0):.3f} jaw={s.values.get('jaw.open', 0):.3f}  "
            f"[{weights}]"
        )
    return 0


def cmd_lipsync_preview(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    face = store.load(args.character).face
    track, vs = _load_track(args.track, args.visemes)
    ev = LipSyncEvaluator(track, vs, face)
    base = evaluate_expression(face, store.get_expression(args.character, args.expression))
    panels = []
    for t in _times(args, track):
        lips = ev.evaluate(t)
        panels.append(
            Panel(
                f"t={t:.3f}s {lips.viseme}->{lips.dominant}",
                apply_lipsync(base, lips, face),
                lips.teeth_visible,
                lips.tongue_visible,
            )
        )
    out = (
        Path(args.out)
        if args.out
        else _default_preview(store, args.character, f"lipsync-{track.id}")
    )
    _write_out(
        out,
        render_face_sheet(face, panels, f"track {track.id}, expression {args.expression}"),
        args.force,
    )
    print(f"wrote {out} ({len(panels)} sampled state(s)); stills for inspection, not animation")
    return 0


def cmd_alignment_inspect(args: argparse.Namespace, settings: Settings) -> int:
    doc = load_model(AlignmentDocument, Path(args.file))
    from studio.face.phonemes import check_timing

    problems = check_timing(doc.phonemes) + [f"words: {p}" for p in check_timing(doc.words)]
    info = summarize(doc) | {
        "problems": problems,
        "lip_sync_ready": bool(doc.phonemes) and not problems,
    }
    if args.json:
        _json(info)
    else:
        for k, v in info.items():
            if k != "problems":
                print(f"{k:>18}: {v}")
        for p in problems:
            print(f"ERROR {p}")
    return 0 if not problems else 1


def cmd_alignment_run(args: argparse.Namespace, settings: Settings) -> int:
    overrides = Project.load(Path(args.project)).settings.providers if args.project else {}
    selection = resolve_selection(ProviderKind.ASR, settings.providers, overrides)
    wav = Path(args.audio).read_bytes()
    doc = align_audio(
        selection,
        wav,
        args.text,
        language=args.language,
        allow_network=settings.providers.allow_network,
    )
    print(
        f"aligned with provider {doc.source.provider!r}: {len(doc.words)} words, "
        f"{len(doc.phonemes)} phonemes"
    )
    if not doc.phonemes:
        print("  note: no phoneme timestamps; this alignment cannot drive lip-sync")
    if args.out:
        _write_out(
            Path(args.out), json.dumps(doc.model_dump(mode="json"), indent=2) + "\n", args.force
        )
        print(f"wrote {args.out}")
    return 0


# --- parser ----------------------------------------------------------------------------------


def register(
    sub: Any,
    add: Callable[[Any, str, Handler, str], argparse.ArgumentParser],
    json_flag: Callable[[argparse.ArgumentParser], None],
    missing: Callable[[argparse.ArgumentParser], int],
) -> None:
    p_face = add(
        sub,
        "face",
        lambda a, s: missing(p_face),
        "facial rigs, expressions, visemes, lip-sync (milestone 4)",
    )
    face = p_face.add_subparsers(dest="face_command", metavar="ACTION")

    def pc(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("path", help="project folder")
        p.add_argument("character", help="character id")
        return p

    def out_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--out", help="output file")
        p.add_argument(
            "--force", action="store_true", help="replace an existing file outside renders/"
        )

    p = pc(add(face, "create", cmd_create, "create a facial rig for a character (no artwork)"))
    p.add_argument("--template", default="standard", choices=TEMPLATES)
    json_flag(pc(add(face, "info", cmd_info, "show facial components and controls")))
    json_flag(pc(add(face, "validate", cmd_validate, "validate the character including its face")))
    p = pc(
        add(
            face,
            "set-asset",
            cmd_set_asset,
            "assign registered artwork to a component (new face version)",
        )
    )
    p.add_argument("component")
    p.add_argument("asset_id")
    p.add_argument("--shape", help="replacement shape id (e.g. a mouth shape)")

    p_ex = add(face, "expressions", lambda a, s: missing(p_ex), "expression commands")
    ex = p_ex.add_subparsers(dest="expressions_command", metavar="ACTION")
    json_flag(pc(add(ex, "list", cmd_expr_list, "list built-in and custom expressions")))
    p = pc(add(ex, "create", cmd_expr_create, "create a custom expression"))
    p.add_argument("id")
    p.add_argument("--name", required=True)
    p.add_argument("--from", dest="from_expression", help="start from another expression")
    p.add_argument("--set", action="append", metavar="COMPONENT.CONTROL=VALUE")
    p.add_argument("--shape", action="append", metavar="COMPONENT=SHAPE")
    p.add_argument("--description")
    p = pc(add(ex, "set", cmd_expr_set, "edit a custom expression (new version)"))
    p.add_argument("id")
    p.add_argument("--set", action="append", metavar="COMPONENT.CONTROL=VALUE")
    p.add_argument("--shape", action="append", metavar="COMPONENT=SHAPE")
    p = pc(add(ex, "preview", cmd_expr_preview, "diagnostic SVG of one or more expressions"))
    p.add_argument("expressions", nargs="*", help="expression ids (default: neutral)")
    out_flags(p)
    json_flag(p)
    p = pc(add(ex, "blend", cmd_expr_blend, "blend two expressions deterministically"))
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--weight", type=float, required=True, help="0 = a, 1 = b (clamped, reported)")
    p.add_argument("--ease", default="linear", choices=[e.value for e in Ease])
    out_flags(p)
    json_flag(p)

    p_vs = add(face, "visemes", lambda a, s: missing(p_vs), "viseme commands")
    vs = p_vs.add_subparsers(dest="visemes_command", metavar="ACTION")
    p = add(vs, "list", cmd_visemes_list, "list a viseme set")
    p.add_argument("--set", default="default", help="'default' or a viseme-set file")
    json_flag(p)

    p_ph = add(face, "phonemes", lambda a, s: missing(p_ph), "phoneme mapping commands")
    ph = p_ph.add_subparsers(dest="phonemes_command", metavar="ACTION")
    json_flag(add(ph, "maps", cmd_maps_list, "list built-in phoneme maps"))
    p = add(ph, "map", cmd_phonemes_map, "map an alignment's phonemes to a viseme track")
    p.add_argument("alignment", help="alignment file (.json/.yaml, AlignmentDocument)")
    p.add_argument("--map", default="en_arpabet", help="built-in map name or map file")
    p.add_argument("--visemes", default="default", help="'default' or a viseme-set file")
    p.add_argument("--id", help="track id")
    p.add_argument("--character", help="character id to record in the track")
    p.add_argument(
        "--no-merge", action="store_true", help="keep adjacent identical visemes separate"
    )
    p.add_argument("--no-silence", action="store_true", help="do not add rest events for gaps")
    p.add_argument("--transition", type=float, default=0.06)
    p.add_argument("--coarticulation", type=float, default=0.0)
    p.add_argument("--ease", default="smoothstep", choices=[e.value for e in Ease])
    out_flags(p)
    json_flag(p)

    p_ls = add(face, "lipsync", lambda a, s: missing(p_ls), "lip-sync track commands")
    ls = p_ls.add_subparsers(dest="lipsync_command", metavar="ACTION")
    p = add(ls, "validate", cmd_lipsync_validate, "validate a lip-sync track")
    p.add_argument("track")
    p.add_argument("--visemes", default="default")
    json_flag(p)

    def time_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--time", type=float, action="append", help="time in seconds (repeatable)")
        p.add_argument("--sample", type=float, help="sample every STEP seconds")
        p.add_argument("--until", type=float, help="last sample time (default: track end)")
        p.add_argument("--visemes", default="default")

    p = add(ls, "evaluate", cmd_lipsync_evaluate, "evaluate mouth state at given times")
    p.add_argument("track")
    time_flags(p)
    json_flag(p)
    p = pc(add(ls, "preview", cmd_lipsync_preview, "diagnostic SVG of sampled lip-sync states"))
    p.add_argument("track")
    time_flags(p)
    p.add_argument("--expression", default="neutral", help="base expression under the speech")
    out_flags(p)

    p_al = add(face, "alignment", lambda a, s: missing(p_al), "audio alignment commands")
    al = p_al.add_subparsers(dest="alignment_command", metavar="ACTION")
    p = add(al, "inspect", cmd_alignment_inspect, "summarize and check an alignment file")
    p.add_argument("file")
    json_flag(p)
    p = add(
        al,
        "run",
        cmd_alignment_run,
        "align audio with the configured asr provider (none by default)",
    )
    p.add_argument("audio", help="WAV file")
    p.add_argument("--text", required=True, help="transcript")
    p.add_argument("--language", default="en")
    p.add_argument("--project", help="apply this project's provider overrides")
    out_flags(p)
