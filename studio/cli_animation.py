"""``studio animation ...`` commands (Milestone 5)."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from studio.animation.clip import (
    compile_clip,
    events_between,
    insert_key,
    remove_key,
    sorted_events,
)
from studio.animation.cycles import (
    CYCLES,
    GESTURES,
    generate_idle,
    generate_locomotion,
    generate_nod,
    generate_point,
    generate_wave,
    locomotion_params,
)
from studio.animation.evaluator import CharacterAnimator, CharacterState, single_clip_set
from studio.animation.mesh import check_mesh, generate_grid_mesh
from studio.animation.preview import render_animation_sheet
from studio.animation.schemas import (
    AnimationClip,
    AnimationEvent,
    AnimationLayer,
    AnimationSet,
    BlendSettings,
    BoneKeyframe,
    BoneTrack,
    ControlKeyframe,
    CurveDefinition,
    DeformationKeyframe,
    DeformMesh,
    DeformTrack,
    EventKind,
    ExpressionKeyframe,
    ExpressionTrack,
    FaceTrack,
    IKKeyframe,
    IKTrack,
    Interpolation,
    LayerMode,
    LipSyncBinding,
    LoopMode,
    LoopSettings,
    PartTrack,
    RootTrack,
    SecondaryMotionSettings,
    SpringDefinition,
    SpringDriver,
    TransformKeyframe,
    track_id,
)
from studio.animation.store import AnimationStore
from studio.core.config import Settings
from studio.core.exceptions import AnimationError
from studio.core.project import Project
from studio.core.validation import ValidationReport, model_to_yaml, write_text_atomic

Handler = Callable[[argparse.Namespace, Settings], int]


def _json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _store(args: argparse.Namespace) -> AnimationStore:
    return AnimationStore(Project.load(Path(args.path)))


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


def _floats(items: list[str] | None, what: str = "PROPERTY=VALUE") -> dict[str, float]:
    out: dict[str, float] = {}
    for item in items or []:
        key, sep, raw = item.partition("=")
        if not sep or not key:
            raise AnimationError(f"expected {what}, got {item!r}")
        if raw.lower() in ("true", "false"):
            out[key] = 1.0 if raw.lower() == "true" else 0.0
            continue
        try:
            value = float(raw)
        except ValueError:
            raise AnimationError(f"value for {key!r} is not a number: {raw!r}") from None
        if not math.isfinite(value):
            raise AnimationError(f"value for {key!r} must be finite")
        out[key] = value
    return out


def _times(args: argparse.Namespace, duration: float) -> list[float]:
    if args.time:
        return list(args.time)
    if args.sample:
        if args.sample <= 0 or not math.isfinite(args.sample):
            raise AnimationError("--sample must be a positive number of seconds")
        end = args.until if args.until is not None else duration
        n = math.floor(end / args.sample + 1e-9) + 1
        if n > 200:
            raise AnimationError(f"{n} samples requested; use a larger --sample (max 200)")
        return [round(i * args.sample, 9) for i in range(n)]
    raise AnimationError("pass --time T (repeatable) or --sample STEP")


def _animator(
    args: argparse.Namespace, store: AnimationStore
) -> tuple[CharacterAnimator, AnimationSet, AnimationClip]:
    if bool(args.clip) == bool(args.set):
        raise AnimationError("pass exactly one of --clip or --set")
    if args.clip:
        clip = store.load(args.character, AnimationClip, args.clip)
        aset = single_clip_set(clip)
        if args.lipsync:
            aset = aset.model_copy(update={"lipsync": LipSyncBinding(path=args.lipsync)})
    else:
        aset = store.load(args.character, AnimationSet, args.set)
        first = sorted(aset.layers, key=lambda lyr: (lyr.order, lyr.id))
        if not first:
            raise AnimationError(f"set {aset.id!r} has no layers")
        clip = store.load(args.character, AnimationClip, first[0].clip)
    context = store.context(args.character, aset)
    return CharacterAnimator(context, aset), aset, clip


# --- clips ---------------------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    store.characters.load(args.character)
    data: dict[str, Any] = {
        "clips": [],
        "sets": store.ids(args.character, AnimationSet),
        "meshes": store.ids(args.character, DeformMesh),
    }
    for cid in store.ids(args.character, AnimationClip):
        clip = store.load(args.character, AnimationClip, cid)
        c = clip
        data["clips"].append(
            {
                "id": c.id,
                "name": c.name,
                "version": c.version,
                "duration": c.duration,
                "fps": c.fps,
                "loop": c.loop.mode.value,
                "tracks": len(c.tracks),
                "events": len(c.events),
                "cycle": c.cycle.kind if c.cycle else None,
            }
        )
    if args.json:
        _json(data)
        return 0
    for c in data["clips"]:
        print(
            f"clip {c['id']:12} v{c['version']:<3} {c['duration']:6.3f}s @{c['fps']:g}fps "
            f"{c['loop']:8} "
            f"tracks={c['tracks']:<3} events={c['events']:<3} {c['cycle'] or ''}  {c['name']}"
        )
    for s in data["sets"]:
        print(f"set  {s}")
    for m in data["meshes"]:
        print(f"mesh {m}")
    print(
        f"{len(data['clips'])} clip(s), {len(data['sets'])} set(s), {len(data['meshes'])} mesh(es)"
    )
    return 0


def cmd_create(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    clip = AnimationClip(
        id=args.clip,
        name=args.name or args.clip,
        character_id=args.character,
        duration=args.duration,
        fps=args.fps,
        loop=LoopSettings(mode=LoopMode(args.loop)),
        tags=args.tag or [],
    )
    store.create(clip)
    print(
        f"created clip {clip.id} ({clip.duration:g}s @ {clip.fps:g} fps, {clip.loop.mode.value}); "
        "add keys with "
        "'studio animation key set'"
    )
    return 0


def _curve(args: argparse.Namespace) -> CurveDefinition:
    return CurveDefinition(
        interpolation=Interpolation(args.interp),
        bezier=tuple(args.bezier) if args.bezier else None,
        tension=args.tension,
        allow_overshoot=args.overshoot,
    )


def _key_and_track(args: argparse.Namespace) -> tuple[Any, Any]:
    timing: dict[str, Any] = {"time": args.time} if args.time is not None else {"frame": args.frame}
    if (args.time is None) == (args.frame is None):
        raise AnimationError("pass exactly one of --time or --frame")
    timing["curve"] = _curve(args)
    kind, _, target = args.target.partition(":")
    values = _floats(args.set)
    if kind == "bone":
        key: Any = BoneKeyframe(**timing, **values)
        return key, BoneTrack(bone=target, keys=[key])
    if kind in ("part", "root"):
        if "visible" in values:
            values["visible"] = float(values["visible"] >= 0.5)
        key = TransformKeyframe(**timing, **values)
        return key, (
            PartTrack(part=target, keys=[key]) if kind == "part" else RootTrack(keys=[key])
        )
    if kind == "ik":
        key = IKKeyframe(**timing, **values)
        return key, IKTrack(chain=target, keys=[key])
    if kind == "face":
        key = ControlKeyframe(**timing, values=values)
        return key, FaceTrack(keys=[key])
    if kind == "expression":
        if not args.expression:
            raise AnimationError("expression keys need --expression ID [--weight W]")
        key = ExpressionKeyframe(**timing, expression=args.expression, weight=args.weight)
        return key, ExpressionTrack(keys=[key])
    if kind == "deform":
        key = DeformationKeyframe(**timing, weights=values)
        return key, DeformTrack(mesh=target, keys=[key])
    raise AnimationError(
        f"unknown target {args.target!r}: use bone:ID, part:ID, root, ik:CHAIN, face, "
        "expression or deform:MESH"
    )


def cmd_key_set(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    clip = store.load(args.character, AnimationClip, args.clip)
    key, track = _key_and_track(args)
    edited = insert_key(clip, track, key, replace=args.replace)
    compile_clip(edited)  # refuse edits that leave the clip invalid
    saved = store.save(edited)
    print(
        f"{saved.id} v{saved.version}: key at {key.seconds(clip.fps):g}s on track {track_id(track)}"
    )
    return 0


def cmd_key_remove(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    clip = store.load(args.character, AnimationClip, args.clip)
    if (args.time is None) == (args.frame is None):
        raise AnimationError("pass exactly one of --time or --frame")
    t = args.time if args.time is not None else args.frame / clip.fps
    saved = store.save(remove_key(clip, args.track, t))
    print(f"{saved.id} v{saved.version}: removed key at {t:g}s from {args.track}")
    return 0


def cmd_event_add(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    clip = store.load(args.character, AnimationClip, args.clip)
    timing: dict[str, Any] = {"time": args.time} if args.time is not None else {"frame": args.frame}
    ev = AnimationEvent(kind=EventKind(args.kind), name=args.name, **timing)
    edited = AnimationClip.model_validate(
        clip.model_copy(update={"events": [*clip.events, ev]}).model_dump()
    )
    compile_clip(edited)
    saved = store.save(edited)
    print(
        f"{saved.id} v{saved.version}: event {ev.name} ({ev.kind.value}) at "
        f"{ev.seconds(clip.fps):g}s"
    )
    return 0


def cmd_events_list(args: argparse.Namespace, settings: Settings) -> int:
    clip = _store(args).load(args.character, AnimationClip, args.clip)
    if args.start is not None or args.end is not None:
        start = args.start if args.start is not None else 0.0
        end = args.end if args.end is not None else clip.duration
        events = events_between(clip, start, end)
    else:
        events = sorted_events(clip)
    rows = [
        {"time": round(t, 6), "kind": e.kind.value, "name": e.name, "data": e.data}
        for t, e in events
    ]
    if args.json:
        _json(rows)
        return 0
    for r in rows:
        print(f"{r['time']:9.4f}s  {r['kind']:17} {r['name']:16} {r['data'] or ''}")
    print(f"{len(rows)} event(s)")
    return 0


def cmd_validate(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    full = store.characters.validate(args.character)
    report = ValidationReport(subject=f"animations of {args.character}", checks=full.checks)
    for issue in full.issues:
        if "/animations/" in issue.location and (
            not args.item or f"/{args.item}.yaml" in issue.location
        ):
            report.issues.append(issue)
    return _report(report, args.json)


def cmd_info(args: argparse.Namespace, settings: Settings) -> int:
    clip = _store(args).load(args.character, AnimationClip, args.clip)
    compiled = compile_clip(clip)
    if args.json:
        _json(
            {
                "clip": clip.model_dump(mode="json"),
                "channels": [f"{d}:{t}.{p}" for (d, t, p) in compiled.channels],
            }
        )
        return 0
    print(
        f"{clip.id} v{clip.version} '{clip.name}': {clip.duration:g}s @ {clip.fps:g} fps, loop "
        f"{clip.loop.mode.value}, "
        f"speed {clip.playback.speed:g}"
    )
    if clip.cycle:
        c = clip.cycle
        print(
            f"  cycle {c.kind}: facing {c.facing}, speed {c.speed:g} u/s, "
            f"{c.distance_per_cycle:g} u/cycle, "
            f"{c.samples} samples, {dict(c.parameters)}"
        )
    for track in clip.tracks:
        times = sorted({k.seconds(clip.fps) for k in track.keys})
        print(
            f"  track {track_id(track):18} {len(track.keys):3} keys  "
            f"{times[0]:.3f}..{times[-1]:.3f}s"
        )
    print(f"  channels: {len(compiled.channels)}; events: {len(clip.events)}")
    return 0


# --- generators ----------------------------------------------------------------------------------


def cmd_cycles_list(args: argparse.Namespace, settings: Settings) -> int:
    rows = [
        ("walk", "biped walk: IK feet, stance/swing, hip bob, sway, lean, arm counter-swing"),
        ("run", "biped run: flight phases, landing, leg recovery, lean, bent-arm swing"),
        ("idle", "breathing, shoulder rise, torso/head motion, weight shift, blinks (seeded)"),
        ("wave", "gesture: raise arm, wave forearm"),
        ("point", "gesture: IK arm reaches a target and holds"),
        ("nod", "gesture: head nod"),
    ]
    for name, text in rows:
        print(f"{name:6} {text}")
    return 0


def cmd_cycles_generate(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    loaded = store.characters.load(args.character)
    if loaded.rig is None:
        raise AnimationError(f"{args.character} has no rig")
    extra = _floats(args.param)
    kind = args.kind
    clip_id = args.id or kind
    if kind in ("walk", "run"):
        prm = locomotion_params(
            kind,
            loaded.rig,
            duration=args.duration,
            stride=args.stride,
            speed=args.speed,
            samples=args.samples or 20,
            **extra,
        )
        clip = generate_locomotion(loaded.character, loaded.rig, prm, clip_id=clip_id, fps=args.fps)
    elif kind == "idle":
        face = (
            store.context(
                args.character, AnimationSet(id="x", name="x", character_id=args.character)
            ).face
            if loaded.character.face
            else None
        )
        clip = generate_idle(
            loaded.character,
            loaded.rig,
            face,
            clip_id=clip_id,
            duration=args.duration or 4.0,
            breaths=int(extra.pop("breaths", 1)),
            amount=extra.pop("amount", 1.0),
            blinks=int(extra.pop("blinks", 2)),
            seed=args.seed,
            samples=args.samples or 32,
            fps=args.fps,
        )
    elif kind == "wave":
        clip = generate_wave(loaded.character, loaded.rig, clip_id=clip_id, side=args.side or "l")
    elif kind == "point":
        clip = generate_point(loaded.character, loaded.rig, clip_id=clip_id, side=args.side or "r")
    else:
        clip = generate_nod(loaded.character, loaded.rig, clip_id=clip_id)
    saved = store.put(clip, replace=args.replace)
    cyc = saved.cycle
    print(
        f"generated {kind} clip {saved.id} v{saved.version}: {saved.duration:g}s, "
        f"{len(saved.tracks)} tracks, "
        f"{len(saved.events)} events" + (f", speed {cyc.speed:g} u/s" if cyc and cyc.speed else "")
    )
    return 0


def _default_springs(store: AnimationStore, character: str) -> list[SpringDefinition]:
    parts = store.characters.load(character).character.part_map()
    springs = []
    for pid, gain in (("hair", 0.35), ("ear_l", 0.25), ("ear_r", 0.25)):
        if pid in parts:
            springs.append(
                SpringDefinition(
                    id=f"{pid}_lag",
                    target=pid,
                    driver=SpringDriver(bone="head", signal="x"),
                    gain=gain,
                    max_displacement=20.0,
                )
            )
    return springs


def cmd_set_create(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    layers = []
    for i, spec in enumerate(args.layer or []):
        parts = spec.split(":")
        clip = parts[0]
        weight = float(parts[1]) if len(parts) > 1 and parts[1] else 1.0
        mode = LayerMode(parts[2]) if len(parts) > 2 and parts[2] else LayerMode.OVERRIDE
        mask = parts[3].split("+") if len(parts) > 3 and parts[3] else ["full"]
        layers.append(
            AnimationLayer(
                id=f"l{i}_{clip}"[:48], clip=clip, weight=weight, mode=mode, mask=mask, order=i
            )
        )
    lipsync = None
    if args.lipsync_path or args.lipsync_asset:
        lipsync = LipSyncBinding(
            path=args.lipsync_path, asset=args.lipsync_asset, start=args.lipsync_start
        )
    springs = _default_springs(store, args.character) if args.springs else []
    aset = AnimationSet(
        id=args.set,
        name=args.name or args.set,
        character_id=args.character,
        layers=layers,
        blend=BlendSettings(normalize=args.normalize),
        lipsync=lipsync,
        secondary=SecondaryMotionSettings(springs=springs),
        meshes=args.mesh or [],
        view=args.view,
    )
    store.context(args.character, aset)  # resolves clips, meshes and lip-sync now (clear errors)
    CharacterAnimator(store.context(args.character, aset), aset)
    store.create(aset)
    print(
        f"created set {aset.id}: {len(layers)} layer(s), lipsync={'yes' if lipsync else 'no'}, "
        f"springs={len(springs)}, meshes={len(aset.meshes)}"
    )
    return 0


# --- evaluation and previews ---------------------------------------------------------------------


def _summary(state: CharacterState) -> list[str]:
    lines = []
    for layer in state.layers:
        phase = f" phase={layer.phase:.3f}" if layer.phase is not None else ""
        lines.append(
            f"  layer {layer.id}: clip {layer.clip} @ {layer.clip_time:.4f}s weight "
            f"{layer.weight:g}{phase}"
        )
    for bone in ("root", "spine", "neck", "head"):
        if bone in state.fk.bones:
            wb = state.fk[bone]
            lines.append(
                f"  {bone:6} head=({wb.head.x:8.2f},{wb.head.y:8.2f}) "
                f"world_rot={wb.world_rotation:8.3f}"
            )
    for ik in state.ik:
        lines.append(
            f"  IK {ik['chain']}: target ({ik['target'][0]:.2f},{ik['target'][1]:.2f}) "
            f"{ik['status']} "
            f"error={ik['error']:.4f} weight={ik['weight']:g}"
        )
    if state.face is not None:
        changed = {
            k: round(v, 3)
            for k, v in sorted(state.face.values.items())
            if k.startswith(
                ("eye_l.blink", "mouth.open", "mouth.corner_l", "brow_l.raise", "jaw.open")
            )
        }
        lines.append(f"  face: {state.face.label} {changed}")
    if state.lips is not None:
        lines.append(f"  lipsync: segment {state.lips.viseme}, dominant {state.lips.dominant}")
    for mesh in state.meshes.values():
        lines.append(
            f"  mesh {mesh.mesh_id}: {len(mesh.vertices)} vertices, {len(mesh.flipped)} flipped"
        )
    for ev in state.events:
        lines.append(f"  event {ev['kind']} {ev['name']} @ clip {ev['clip_time']:.4f}s")
    for d in state.diagnostics:
        lines.append(f"  {d.severity.upper()} {d.code}: {d.message}")
    return lines


def cmd_evaluate(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    animator, _aset, clip = _animator(args, store)
    window = 1.0 / clip.fps
    states = [animator.evaluate(t, event_window=window) for t in _times(args, clip.duration)]
    if args.json:
        _json([s.to_dict(include_parts=args.parts) for s in states])
        return 0
    for s in states:
        print(f"t={s.time:.4f}s")
        print("\n".join(_summary(s)))
    return 1 if any(d.severity == "error" for s in states for d in s.diagnostics) else 0


def cmd_preview(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    animator, _aset, clip = _animator(args, store)
    window = 1.0 / clip.fps
    states = [animator.evaluate(t, event_window=window) for t in _times(args, clip.duration)]
    name = args.clip or args.set
    out = (
        Path(args.out)
        if args.out
        else store.project.root / "renders" / "previews" / f"{args.character}-anim-{name}.svg"
    )
    if out.exists() and not args.force and "renders" not in out.resolve().parts:
        raise AnimationError(f"{out} exists; use --force to replace it")
    svg = render_animation_sheet(
        states,
        title=f"{args.character} {'clip' if args.clip else 'set'} {name}",
        face=animator.ctx.face,
        timeline=animator.compiled.get(clip.id),
        columns=args.columns,
    )
    write_text_atomic(out, svg)
    print(f"wrote {out} ({len(states)} sampled state(s)); still diagnostics, not animation")
    return 0


def cmd_blend(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    if not math.isfinite(args.weight) or not 0 <= args.weight <= 1:
        raise AnimationError("--weight must be within [0, 1]")
    a = store.load(args.character, AnimationClip, args.a)
    store.load(args.character, AnimationClip, args.b)
    aset = AnimationSet(
        id="blend",
        name=f"blend {args.a}/{args.b}",
        character_id=args.character,
        blend=BlendSettings(normalize=True),
        layers=[
            AnimationLayer(id="a", clip=args.a, weight=1 - args.weight, order=0),
            AnimationLayer(id="b", clip=args.b, weight=args.weight, order=1),
        ],
    )
    animator = CharacterAnimator(store.context(args.character, aset), aset)
    states = [animator.evaluate(t) for t in (args.time or [0.0])]
    if args.json:
        _json([s.to_dict() for s in states])
    else:
        for s in states:
            print(
                f"t={s.time:.4f}s  normalized weights {args.a}={1 - args.weight:g} "
                f"{args.b}={args.weight:g}"
            )
            print("\n".join(_summary(s)))
    if args.out:
        write_text_atomic(
            Path(args.out),
            render_animation_sheet(
                states,
                title=f"blend {args.a}/{args.b} w={args.weight:g}",
                face=animator.ctx.face,
                timeline=animator.compiled[a.id],
            ),
        )
        print(f"wrote {args.out}")
    return 0


# --- meshes --------------------------------------------------------------------------------------


def cmd_mesh_create(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    loaded = store.characters.load(args.character)
    if loaded.rig is None:
        raise AnimationError(f"{args.character} has no rig")
    try:
        cols, rows = (int(v) for v in args.grid.lower().split("x"))
    except ValueError:
        raise AnimationError(f"--grid must look like 4x2, got {args.grid!r}") from None
    bones = [b for b in (args.bones or "").split(",") if b] or None
    mesh = generate_grid_mesh(
        loaded.character, loaded.rig, args.part, args.mesh, columns=cols, rows=rows, bones=bones
    )
    store.create(mesh)
    print(
        f"created mesh {mesh.id} on part {mesh.part}: {len(mesh.vertices)} vertices, "
        f"{len(mesh.triangles)} triangles"
    )
    return 0


def cmd_mesh_validate(args: argparse.Namespace, settings: Settings) -> int:
    store = _store(args)
    loaded = store.characters.load(args.character)
    ids = [args.mesh] if args.mesh else store.ids(args.character, DeformMesh)
    report = ValidationReport(subject=f"meshes of {args.character}")
    for mid in ids:
        mesh = store.load(args.character, DeformMesh, mid)
        report.checks += 1
        for code, sev, msg in check_mesh(mesh, loaded.character, loaded.rig):
            (report.error if sev == "error" else report.warning)(code, msg, f"meshes/{mid}.yaml")
    return _report(report, args.json)


def cmd_mesh_export(args: argparse.Namespace, settings: Settings) -> int:
    mesh = _store(args).load(args.character, DeformMesh, args.mesh)
    print(model_to_yaml(mesh), end="")
    return 0


# --- parser --------------------------------------------------------------------------------------


def register(
    sub: Any,
    add: Callable[[Any, str, Handler, str], argparse.ArgumentParser],
    json_flag: Callable[[argparse.ArgumentParser], None],
    missing: Callable[[argparse.ArgumentParser], int],
) -> None:
    p_anim = add(
        sub,
        "animation",
        lambda a, s: missing(p_anim),
        "animation clips, cycles, sets, meshes (milestone 5)",
    )
    an = p_anim.add_subparsers(dest="animation_command", metavar="ACTION")

    def pc(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("path", help="project folder")
        p.add_argument("character", help="character id")
        return p

    def timing(p: argparse.ArgumentParser) -> None:
        p.add_argument("--time", type=float, help="seconds")
        p.add_argument("--frame", type=int, help="frame number at the clip fps")

    def sampling(p: argparse.ArgumentParser) -> None:
        g = p.add_mutually_exclusive_group()
        g.add_argument("--clip")
        g.add_argument("--set")
        p.add_argument("--time", type=float, action="append", help="time in seconds (repeatable)")
        p.add_argument("--sample", type=float, help="sample every STEP seconds")
        p.add_argument("--until", type=float, help="last sample time (default: clip duration)")
        p.add_argument("--lipsync", help="with --clip: project-relative lip-sync track to include")

    json_flag(pc(add(an, "list", cmd_list, "list clips, sets and meshes of a character")))
    p = pc(add(an, "create", cmd_create, "create an empty clip"))
    p.add_argument("clip")
    p.add_argument("--name")
    p.add_argument("--duration", type=float, required=True)
    p.add_argument("--fps", type=float, default=24.0)
    p.add_argument("--loop", default="once", choices=[m.value for m in LoopMode])
    p.add_argument("--tag", action="append")
    p = pc(add(an, "validate", cmd_validate, "validate a character's clips, sets and meshes"))
    p.add_argument("item", nargs="?", help="clip, set or mesh id")
    json_flag(p)
    p = pc(add(an, "info", cmd_info, "show a clip's tracks, channels and cycle data"))
    p.add_argument("clip")
    json_flag(p)

    p_key = add(an, "key", lambda a, s: missing(p_key), "keyframe editing")
    key = p_key.add_subparsers(dest="key_command", metavar="ACTION")
    p = pc(
        add(
            key,
            "set",
            cmd_key_set,
            "insert (or with --replace, replace) a keyframe; saves a new version",
        )
    )
    p.add_argument("clip")
    p.add_argument("target", help="bone:ID, part:ID, root, ik:CHAIN, face, expression, deform:MESH")
    timing(p)
    p.add_argument("--set", action="append", metavar="PROPERTY=VALUE")
    p.add_argument("--expression")
    p.add_argument("--weight", type=float, default=1.0)
    p.add_argument("--interp", default="linear", choices=[i.value for i in Interpolation])
    p.add_argument("--bezier", nargs=4, type=float, metavar=("X1", "Y1", "X2", "Y2"))
    p.add_argument("--tension", type=float, default=0.0)
    p.add_argument("--overshoot", action="store_true", help="allow bezier/hermite overshoot")
    p.add_argument("--replace", action="store_true")
    p = pc(add(key, "remove", cmd_key_remove, "remove a keyframe (new version)"))
    p.add_argument("clip")
    p.add_argument("track", help="track id, e.g. bone:upper_arm_l")
    timing(p)

    p_ev = add(an, "events", lambda a, s: missing(p_ev), "animation events")
    ev = p_ev.add_subparsers(dest="events_command", metavar="ACTION")
    p = pc(add(ev, "list", cmd_events_list, "list events (optionally in a loop-aware time window)"))
    p.add_argument("clip")
    p.add_argument("--from", dest="start", type=float)
    p.add_argument("--to", dest="end", type=float)
    json_flag(p)
    p = pc(add(ev, "add", cmd_event_add, "add an event to a clip (new version)"))
    p.add_argument("clip")
    p.add_argument("--kind", required=True, choices=[k.value for k in EventKind])
    p.add_argument("--name", required=True)
    timing(p)

    p_cy = add(an, "cycles", lambda a, s: missing(p_cy), "procedural cycles and gestures")
    cy = p_cy.add_subparsers(dest="cycles_command", metavar="ACTION")
    add(cy, "list", cmd_cycles_list, "list generators")
    p = pc(
        add(
            cy, "generate", cmd_cycles_generate, "generate an editable clip from a cycle or gesture"
        )
    )
    p.add_argument("kind", choices=[*CYCLES, *GESTURES])
    p.add_argument("--id")
    p.add_argument("--duration", type=float)
    p.add_argument("--stride", type=float)
    p.add_argument("--speed", type=float)
    p.add_argument("--samples", type=int)
    p.add_argument("--fps", type=float, default=24.0)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--side", choices=["l", "r"])
    p.add_argument(
        "--param",
        action="append",
        metavar="NAME=VALUE",
        help="walk/run: stance, lift, bob, arm_swing, elbow, lean, sway, recovery; "
        "idle: breaths, amount, blinks",
    )
    p.add_argument(
        "--replace", action="store_true", help="save as a new version if the clip exists"
    )

    p_set = add(an, "set", lambda a, s: missing(p_set), "animation sets (layers)")
    st = p_set.add_subparsers(dest="set_command", metavar="ACTION")
    p = pc(
        add(
            st,
            "create",
            cmd_set_create,
            "create a set of layered clips (+ lip-sync, springs, meshes)",
        )
    )
    p.add_argument("set")
    p.add_argument("--name")
    p.add_argument(
        "--layer", action="append", required=True, metavar="CLIP[:WEIGHT[:MODE[:MASK+MASK]]]"
    )
    p.add_argument("--normalize", action="store_true")
    p.add_argument("--lipsync-path")
    p.add_argument("--lipsync-asset")
    p.add_argument("--lipsync-start", type=float, default=0.0)
    p.add_argument(
        "--springs", action="store_true", help="add default springs (hair, ears follow the head)"
    )
    p.add_argument("--mesh", action="append")
    p.add_argument("--view")

    p = pc(add(an, "evaluate", cmd_evaluate, "evaluate the character at times (structured state)"))
    sampling(p)
    p.add_argument("--parts", action="store_true", help="include part transforms in --json")
    json_flag(p)
    p = pc(add(an, "preview", cmd_preview, "diagnostic contact sheet of sampled states (SVG)"))
    sampling(p)
    p.add_argument("--columns", type=int, default=6)
    p.add_argument("--out")
    p.add_argument("--force", action="store_true")
    p = pc(add(an, "blend", cmd_blend, "evaluate a normalized blend of two clips"))
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--weight", type=float, required=True, help="0 = a, 1 = b")
    p.add_argument("--time", type=float, action="append")
    p.add_argument("--out")
    json_flag(p)

    p_m = add(an, "mesh", lambda a, s: missing(p_m), "deformation meshes")
    me = p_m.add_subparsers(dest="mesh_command", metavar="ACTION")
    p = pc(
        add(
            me,
            "create",
            cmd_mesh_create,
            "create a skinned grid mesh over a part (artwork untouched)",
        )
    )
    p.add_argument("mesh")
    p.add_argument("--part", required=True)
    p.add_argument("--grid", default="4x2")
    p.add_argument("--bones", help="comma-separated bones (default: the part's bone)")
    p = pc(add(me, "validate", cmd_mesh_validate, "validate meshes"))
    p.add_argument("mesh", nargs="?")
    json_flag(p)
    p = pc(add(me, "show", cmd_mesh_export, "print a mesh as YAML"))
    p.add_argument("mesh")
