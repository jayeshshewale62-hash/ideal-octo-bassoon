"""Unified character animation evaluator: ``CharacterAnimator(context, set).evaluate(t)``.

Evaluation order (docs/ANIMATION.md#evaluation-order). Every step reuses the
Milestone 3/4 implementations instead of re-implementing them:

1. **Layers.** Each layer maps ``t`` to its clip time (loop/pingpong/once, speed, offset)
   and samples its compiled channels. Layers apply in ascending ``(order, id)``:
   ``override`` lerps from the value below towards the layer by its weight (angles take
   the shortest way); ``additive`` adds ``weight·(value - rest)``. Masks limit a layer to
   body groups. With ``blend.normalize``, override layers that key a property contribute
   a weight-normalised average. The highest layer that writes a property *owns* it.
2. **Bone pose.** Keyed bone values replace rest values (``studio.rig.fk.BonePose``);
   the root track places the whole rig (FK ``origin``).
3. **IK.** For every keyed chain (sorted by id), ``studio.rig.ik.solve_ik_chain`` runs on
   the current pose; its rotations are blended with FK by the chain's ``weight``. An
   ``end_rotation`` keeps the bone after the chain (e.g. a foot) at a world angle.
4. **FK.** ``studio.rig.fk.solve_fk`` evaluates the hierarchy and enforces joint
   constraints. Every clamp is reported.
5. **Secondary motion.** Springs driven by the step-4 result add lagging rotation offsets
   to bones (FK is then re-run) and parts.
6. **Parts.** ``studio.characters.parts.solve_parts`` on a copy of the character whose
   part transforms, visibility and opacity include keyed values and spring offsets.
   The stored character file is never changed.
7. **Meshes.** Linear blend skinning plus blend shapes (``studio.animation.mesh``).
8. **Face.** Expression tracks give a ``FaceState`` via the Milestone 4 evaluator and
   blends. Keyed facial controls override those controls (clamped to limits). Lip-sync
   (``LipSyncEvaluator`` + ``apply_lipsync``) then **owns the mouth and jaw**: keyed
   mouth/jaw values are replaced (corners are added), and eyes and brows stay with the
   expression and keys.
9. **Events** within the requested window, and the cycle phase of each layer.

The same context, set and time always give the same state.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from studio.animation.clip import (
    ChannelKey,
    ClipSample,
    CompiledClip,
    clip_time,
    compile_clip,
    events_between,
    sample_clip,
)
from studio.animation.curves import wrap_degrees
from studio.animation.mesh import DeformedMesh, deform_mesh
from studio.animation.schemas import (
    AnimationClip,
    AnimationLayer,
    AnimationSet,
    DeformMesh,
    LayerMode,
)
from studio.animation.secondary import SpringSolver
from studio.characters.parts import PartWorld, solve_parts
from studio.characters.schemas import CharacterDefinition
from studio.core.exceptions import AnimationError, CharacterError
from studio.face.expressions import FaceState, blend_states, evaluate_expression, neutral_state
from studio.face.lipsync import LipSyncEvaluator, LipSyncState, apply_lipsync
from studio.face.schemas import FacialExpression, FacialRig, LipSyncTrack, VisemeSet
from studio.rig.fk import BonePose, ConstraintEvent, FKResult, constrain_rotation, solve_fk
from studio.rig.ik import solve_ik_chain
from studio.rig.math2d import Affine, Vec2
from studio.rig.schemas import RigDefinition

BONE_PROPS = ("rotation", "x", "y", "scale_x", "scale_y")
LIP_OWNED_PREFIXES = ("mouth.", "jaw.")
BODY_GROUPS = ("full", "upper_body", "lower_body", "face")


@dataclass
class AnimationContext:
    """Everything the evaluator needs, already loaded (see store.load_context)."""

    character: CharacterDefinition
    rig: RigDefinition
    clips: dict[str, AnimationClip]
    face: FacialRig | None = None
    expressions: Callable[[str], FacialExpression] | None = None
    expression_ids: set[str] | None = None
    meshes: dict[str, DeformMesh] = field(default_factory=dict)
    lipsync: LipSyncTrack | None = None
    visemes: VisemeSet | None = None


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: str  # "info" | "warning" | "error"
    message: str


@dataclass
class LayerState:
    id: str
    clip: str
    clip_time: float
    weight: float
    phase: float | None


@dataclass
class CharacterState:
    time: float
    layers: list[LayerState]
    pose: dict[str, BonePose]
    origin: Affine
    fk: FKResult
    parts: dict[str, PartWorld]
    face: FaceState | None
    lips: LipSyncState | None
    meshes: dict[str, DeformedMesh]
    ik: list[dict[str, Any]]
    owners: dict[str, str]
    events: list[dict[str, Any]]
    diagnostics: list[Diagnostic]
    constraint_events: list[ConstraintEvent]
    character: CharacterDefinition  # animated copy (part transforms); the file is untouched

    def to_dict(self, *, include_parts: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "time": self.time,
            "layers": [lyr.__dict__ for lyr in self.layers],
            "bones": [self.fk[b].to_dict() for b in self.fk.order],
            "ik": self.ik,
            "face": self.face.to_dict() if self.face else None,
            "lipsync": self.lips.to_dict() if self.lips else None,
            "meshes": {k: v.to_dict() for k, v in sorted(self.meshes.items())},
            "events": self.events,
            "owners": dict(sorted(self.owners.items())),
            "diagnostics": [d.__dict__ for d in self.diagnostics],
        }
        if include_parts:
            data["parts"] = [p.to_dict() for p in self.parts.values()]
        return data


def _key_name(ck: ChannelKey) -> str:
    return f"{ck[0]}:{ck[1]}.{ck[2]}"


class CharacterAnimator:
    def __init__(self, context: AnimationContext, animation_set: AnimationSet) -> None:
        from studio.animation.validation import check_set_references

        problems = [
            f"{code} {m}"
            for code, sev, m in check_set_references(context, animation_set)
            if sev == "error"
        ]
        if problems:
            raise AnimationError(
                f"animation set {animation_set.id!r} cannot be evaluated", problems
            )
        self.ctx = context
        self.set = animation_set
        self.layers = sorted(animation_set.layers, key=lambda lyr: (lyr.order, lyr.id))
        self.compiled: dict[str, CompiledClip] = {
            lyr.clip: compile_clip(context.clips[lyr.clip]) for lyr in self.layers
        }
        rig = context.rig
        self.bones = rig.bone_map()
        self.bind = solve_fk(rig)
        self.rest_parts = solve_parts(context.character, self.bind)
        self._groups = self._body_groups()
        self._lips = (
            LipSyncEvaluator(context.lipsync, context.visemes, context.face)
            if context.lipsync is not None
            and context.visemes is not None
            and animation_set.lipsync is not None
            and animation_set.lipsync.enabled
            else None
        )
        self._base_cache: dict[float, tuple[dict[str, BonePose], Affine, FKResult]] = {}
        self._springs = (
            SpringSolver(animation_set.secondary, self._spring_signals)
            if animation_set.secondary.enabled and animation_set.secondary.springs
            else None
        )

    # --- groups and rest values -------------------------------------------------------------

    def _descendants(self, root: str) -> set[str]:
        out, stack = set(), [root]
        while stack:
            b = stack.pop()
            if b in out:
                continue
            out.add(b)
            stack.extend(x.id for x in self.bones.values() if x.parent == b)
        return out

    def _body_groups(self) -> dict[str, set[str]]:
        rig = self.ctx.rig
        upper = self._descendants("spine") if "spine" in self.bones else set()
        lower = set(self.bones) - upper
        groups = {"upper_body": upper, "lower_body": lower, "full": set(self.bones)}
        for b in self.bones:
            groups[f"bone:{b}"] = self._descendants(b)
        for chain in rig.ik_chains:
            groups[f"ik:{chain.id}"] = {chain.upper, chain.lower}
        return groups

    def _in_mask(self, ck: ChannelKey, mask: list[str]) -> bool:
        if "full" in mask:
            return True
        domain, target, _prop = ck
        if domain == "face":
            return "face" in mask
        if domain == "root":
            return "lower_body" in mask
        bones: set[str] = set()
        if domain == "bone":
            bones = {target}
        elif domain == "ik":
            chain = self.ctx.rig.chain(target)
            bones = {chain.upper, chain.lower} if chain else set()
        elif domain == "part":
            part = self.ctx.character.part_map().get(target)
            bones = {part.bone} if part and part.bone else set()
            if f"part:{target}" in mask:
                return True
        elif domain == "deform":
            mesh = self.ctx.meshes.get(target)
            part = self.ctx.character.part_map().get(mesh.part) if mesh else None
            bones = {part.bone} if part and part.bone else set()
        for name in mask:
            members = self._groups.get(name, set())
            if bones and bones <= members:
                return True
        return False

    def rest_value(self, ck: ChannelKey) -> float:
        domain, target, prop = ck
        if domain == "bone":
            return float(getattr(self.bones[target].rest, prop))
        if domain == "part":
            part = self.ctx.character.part_map()[target]
            if prop == "visible":
                return 1.0 if part.visible else 0.0
            if prop == "opacity":
                return part.opacity
            return float(getattr(part.transform, prop))
        if domain == "root":
            return 1.0 if prop.startswith("scale") else 0.0
        if domain == "face" and self.ctx.face is not None:
            channel = self.ctx.face.channel(prop)
            return channel.default if channel else 0.0
        if domain == "ik" and prop == "weight":
            return 1.0
        return 0.0

    # --- step 1: layers ---------------------------------------------------------------------------

    def _layers(
        self, t: float
    ) -> tuple[
        dict[ChannelKey, float],
        dict[str, str],
        list[tuple[AnimationLayer, ClipSample]],
        list[LayerState],
    ]:
        values: dict[ChannelKey, float] = {}
        owners: dict[str, str] = {}
        samples: list[tuple[AnimationLayer, ClipSample]] = []
        states: list[LayerState] = []
        norm_sum: dict[ChannelKey, float] = {}
        norm_w: dict[ChannelKey, float] = {}
        normalize = self.set.blend.normalize
        for layer in self.layers:
            clip = self.ctx.clips[layer.clip]
            ct = clip_time(clip, t, time_offset=layer.time_offset, speed=layer.speed)
            sample = sample_clip(self.compiled[layer.clip], ct)
            samples.append((layer, sample))
            states.append(
                LayerState(
                    layer.id, clip.id, ct, layer.weight, ct / clip.duration if clip.cycle else None
                )
            )
            if layer.weight <= 0:
                continue
            for ck, v in sample.values.items():
                if not self._in_mask(ck, layer.mask):
                    continue
                angle = ck[2] in ("rotation", "end_rotation")
                if layer.mode is LayerMode.ADDITIVE:
                    rest = self.rest_value(ck)
                    base = values.get(ck, rest)
                    delta = wrap_degrees(v - rest) if angle else v - rest
                    values[ck] = base + layer.weight * delta
                elif normalize:
                    # accumulate around the first contributor to keep angles continuous
                    ref = norm_sum.get(ck)
                    if ref is not None and angle:
                        v = ref / norm_w[ck] + wrap_degrees(v - ref / norm_w[ck])
                    norm_sum[ck] = norm_sum.get(ck, 0.0) + layer.weight * v
                    norm_w[ck] = norm_w.get(ck, 0.0) + layer.weight
                    values[ck] = norm_sum[ck] / norm_w[ck]
                else:
                    base = values.get(ck, self.rest_value(ck))
                    delta = wrap_degrees(v - base) if angle else v - base
                    values[ck] = base + layer.weight * delta
                owners[_key_name(ck)] = layer.id
        return values, owners, samples, states

    # --- steps 2-4: pose, IK, FK ---------------------------------------------------------------

    def _pose(
        self,
        values: dict[ChannelKey, float],
        diags: list[Diagnostic] | None,
        ik_out: list[dict[str, Any]] | None,
    ) -> tuple[dict[str, BonePose], Affine, FKResult]:
        rig = self.ctx.rig
        pose: dict[str, BonePose] = {}
        for (domain, target, prop), v in values.items():
            if domain != "bone":
                continue
            current = pose.get(target) or BonePose()
            pose[target] = current.model_copy(update={prop: v})
        root = {
            p: values.get(("root", "root", p), 1.0 if p.startswith("scale") else 0.0)
            for p in BONE_PROPS
        }
        origin = Affine.from_trs(
            root["x"], root["y"], root["rotation"], root["scale_x"], root["scale_y"]
        )
        chains = sorted({t for (d, t, _p) in values if d == "ik"})
        for chain_id in chains:
            x = values.get(("ik", chain_id, "x"))
            y = values.get(("ik", chain_id, "y"))
            if x is None or y is None:
                continue
            weight = min(1.0, max(0.0, values.get(("ik", chain_id, "weight"), 1.0)))
            chain = rig.chain(chain_id)
            assert chain is not None
            if weight > 0:
                px, py = (
                    values.get(("ik", chain_id, "pole_x")),
                    values.get(("ik", chain_id, "pole_y")),
                )
                pole = Vec2(px, py) if px is not None and py is not None else None
                result = solve_ik_chain(
                    rig, chain_id, Vec2(x, y), pole=pole, pose=pose, origin=origin
                )
                for bone in (chain.upper, chain.lower):
                    fk_rot = (pose.get(bone) or BonePose()).rotation
                    fk_rot = self.bones[bone].rest.rotation if fk_rot is None else fk_rot
                    ik_rot = result.pose[bone].rotation or 0.0
                    blended = fk_rot + weight * wrap_degrees(ik_rot - fk_rot)
                    pose[bone] = (pose.get(bone) or BonePose()).model_copy(
                        update={"rotation": blended}
                    )
                if ik_out is not None:
                    ik_out.append(
                        {
                            "chain": chain_id,
                            "target": [x, y],
                            "weight": weight,
                            "status": result.solution.status,
                            "error": round(result.error, 6),
                            "limited": result.limited,
                        }
                    )
                if diags is not None:
                    if not result.solution.reached:
                        diags.append(
                            Diagnostic(
                                "EVL002",
                                "warning",
                                f"IK {chain_id}: target ({x:g}, {y:g}) {result.solution.status}, "
                                f"error {result.error:.3f}",
                            )
                        )
                    for ev in result.limit_events:
                        diags.append(
                            Diagnostic(
                                "EVL003",
                                "info",
                                f"IK {chain_id}: {ev.bone} {ev.requested:.2f} -> {ev.applied:.2f} "
                                f"({ev.reason})",
                            )
                        )
            end = values.get(("ik", chain_id, "end_rotation"))
            if end is not None:
                children = sorted(b.id for b in self.bones.values() if b.parent == chain.lower)
                if children:
                    child = children[0]
                    fk_mid = solve_fk(rig, pose, origin=origin)
                    local = wrap_degrees(end - fk_mid[chain.lower].world_rotation)
                    applied, reason = constrain_rotation(self.bones[child], local)
                    pose[child] = (pose.get(child) or BonePose()).model_copy(
                        update={"rotation": applied}
                    )
                    if reason and diags is not None:
                        diags.append(
                            Diagnostic(
                                "EVL001", "info", f"{child}: end rotation limited ({reason})"
                            )
                        )
        fk = solve_fk(rig, pose, origin=origin)
        return pose, origin, fk

    def _base(self, t: float) -> tuple[dict[str, BonePose], Affine, FKResult]:
        key = round(t, 9)
        if key not in self._base_cache:
            values, *_ = self._layers(t)
            self._base_cache[key] = self._pose(values, None, None)
        return self._base_cache[key]

    def _spring_signals(self, t: float) -> dict[str, float]:
        _pose, _origin, fk = self._base(t)
        out = {}
        for s in self.set.secondary.springs:
            wb = fk[s.driver.bone]
            out[s.id] = {"rotation": wb.world_rotation, "x": wb.head.x, "y": wb.head.y}[
                s.driver.signal
            ]
        return out

    # --- full evaluation -------------------------------------------------------------------------

    def evaluate(self, t: float, *, event_window: float | None = None) -> CharacterState:
        if not isinstance(t, int | float) or isinstance(t, bool) or not math.isfinite(t):
            raise AnimationError(f"time must be a finite number, got {t!r}")
        diags: list[Diagnostic] = []
        ik_out: list[dict[str, Any]] = []
        values, owners, samples, layer_states = self._layers(t)
        pose, origin, fk = self._pose(values, diags, ik_out)

        part_offsets: dict[str, float] = {}
        if self._springs is not None:
            for sid, out in sorted(self._springs.offsets_at(t).items()):
                spring = next(s for s in self.set.secondary.springs if s.id == sid)
                if out.clamped:
                    diags.append(
                        Diagnostic(
                            "EVL006",
                            "info",
                            f"spring {sid}: offset clamped to ±{spring.max_displacement:g}°",
                        )
                    )
                if spring.target_kind == "bone":
                    current = pose.get(spring.target) or BonePose()
                    rot = (
                        current.rotation
                        if current.rotation is not None
                        else self.bones[spring.target].rest.rotation
                    )
                    pose[spring.target] = current.model_copy(update={"rotation": rot + out.offset})
                else:
                    part_offsets[spring.target] = part_offsets.get(spring.target, 0.0) + out.offset
            fk = solve_fk(self.ctx.rig, pose, origin=origin)
        for ev in fk.events:
            diags.append(
                Diagnostic(
                    "EVL001",
                    "info",
                    f"{ev.bone}: rotation {ev.requested:.2f} -> {ev.applied:.2f} ({ev.reason})",
                )
            )

        character = self._animated_character(values, part_offsets)
        view = character.turnaround.get(self.set.view) if self.set.view else None  # type: ignore[arg-type]
        try:
            parts = solve_parts(character, fk, view)
        except CharacterError as exc:
            raise AnimationError(f"parts cannot be evaluated: {exc}") from None

        meshes: dict[str, DeformedMesh] = {}
        for mesh_id in self.set.meshes:
            mesh = self.ctx.meshes[mesh_id]
            weights = {p: v for (d, tg, p), v in values.items() if d == "deform" and tg == mesh_id}
            dm = deform_mesh(
                mesh,
                part_rest=self.rest_parts[mesh.part],
                part_now=parts[mesh.part],
                bind=self.bind,
                fk=fk,
                shape_weights=weights,
            )
            if dm.flipped:
                diags.append(
                    Diagnostic(
                        "EVL007",
                        "warning",
                        f"mesh {mesh_id}: {len(dm.flipped)} triangle(s) flipped (invalid geometry)",
                    )
                )
            meshes[mesh_id] = dm

        face, lips = self._face(t, values, samples, owners, diags)
        events = self._events(t, event_window) if event_window is not None else []
        return CharacterState(
            t,
            layer_states,
            pose,
            origin,
            fk,
            parts,
            face,
            lips,
            meshes,
            ik_out,
            owners,
            events,
            diags,
            list(fk.events),
            character,
        )

    def _animated_character(
        self, values: dict[ChannelKey, float], offsets: dict[str, float]
    ) -> CharacterDefinition:
        keyed = {t for (d, t, _p) in values if d == "part"} | set(offsets)
        if not keyed:
            return self.ctx.character
        parts = []
        for part in self.ctx.character.parts:
            if part.id not in keyed:
                parts.append(part)
                continue
            tr = part.transform.model_copy(
                update={
                    p: values[("part", part.id, p)]
                    for p in BONE_PROPS
                    if ("part", part.id, p) in values
                }
            )
            if part.id in offsets:
                tr = tr.model_copy(update={"rotation": tr.rotation + offsets[part.id]})
            update: dict[str, Any] = {"transform": tr}
            if ("part", part.id, "visible") in values:
                update["visible"] = values[("part", part.id, "visible")] >= 0.5
            if ("part", part.id, "opacity") in values:
                update["opacity"] = min(1.0, max(0.0, values[("part", part.id, "opacity")]))
            parts.append(part.model_copy(update=update))
        return self.ctx.character.model_copy(update={"parts": parts})

    def _face(
        self,
        t: float,
        values: dict[ChannelKey, float],
        samples: list[tuple[AnimationLayer, ClipSample]],
        owners: dict[str, str],
        diags: list[Diagnostic],
    ) -> tuple[FaceState | None, LipSyncState | None]:
        rig = self.ctx.face
        if rig is None:
            if any(d == "face" for (d, _t, _p) in values) or any(s.expression for _l, s in samples):
                diags.append(
                    Diagnostic(
                        "EVL009",
                        "warning",
                        "facial tracks ignored: the character has no facial rig",
                    )
                )
            return None, None
        state = neutral_state(rig)
        lookup = self.ctx.expressions
        for layer, sample in samples:
            ex = sample.expression
            if (
                ex is None
                or layer.weight <= 0
                or lookup is None
                or ("face" not in layer.mask and "full" not in layer.mask)
            ):
                continue
            neutral = neutral_state(rig)
            sa = blend_states(neutral, evaluate_expression(rig, lookup(ex.a)), ex.weight_a)
            sb = blend_states(neutral, evaluate_expression(rig, lookup(ex.b)), ex.weight_b)
            layer_state = blend_states(sa, sb, ex.u)
            layer_state.label = ex.a if ex.u < 0.5 else ex.b
            state = blend_states(state, layer_state, layer.weight)
            state.label = layer_state.label
            owners["face:expression"] = layer.id
        for (domain, _target, key), v in sorted(values.items()):
            if domain != "face":
                continue
            channel = rig.channel(key)
            if channel is None:
                diags.append(Diagnostic("EVL008", "warning", f"unknown facial control {key!r}"))
                continue
            clamped = min(channel.max, max(channel.min, v))
            if clamped != v:
                diags.append(
                    Diagnostic("EVL004", "info", f"{key} = {v:.3f} clamped to {clamped:.3f}")
                )
            state.values[key] = clamped
        lips = None
        if self._lips is not None and self.set.lipsync is not None:
            local = t - self.set.lipsync.start
            if local >= 0:
                lips = self._lips.evaluate(local)
                overridden = sorted(
                    k
                    for (d, _t, k) in values
                    if d == "face"
                    and k.startswith(LIP_OWNED_PREFIXES)
                    and k not in ("mouth.corner_l", "mouth.corner_r")
                )
                if overridden:
                    diags.append(
                        Diagnostic(
                            "EVL005",
                            "info",
                            "lip-sync owns " + ", ".join(overridden) + " (keyed values replaced)",
                        )
                    )
                state = apply_lipsync(state, lips, rig)
                for key in lips.values:
                    owners[f"face:face.{key}"] = "lipsync"
        state.issues = [i for i in state.issues if i.severity == "error"]
        return state, lips

    def _events(self, t: float, window: float) -> list[dict[str, Any]]:
        out = []
        for layer in self.layers:
            clip = self.ctx.clips[layer.clip]
            scale = layer.speed * clip.playback.speed
            end = (t - layer.time_offset) * scale + clip.playback.offset
            start = end - window * scale
            for abs_t, ev in events_between(clip, start, end + 1e-9):
                out.append(
                    {
                        "layer": layer.id,
                        "clip": clip.id,
                        "kind": ev.kind.value,
                        "name": ev.name,
                        "clip_time": round(abs_t, 6),
                        "data": ev.data,
                    }
                )
        return out


def single_clip_set(clip: AnimationClip, **kwargs: Any) -> AnimationSet:
    return AnimationSet(
        id="adhoc",
        name=f"clip {clip.id}",
        character_id=clip.character_id,
        layers=[AnimationLayer(id="base", clip=clip.id)],
        **kwargs,
    )


def evaluate_character(
    context: AnimationContext,
    animation_set: AnimationSet,
    time: float,
    *,
    event_window: float | None = None,
) -> CharacterState:
    """One-off evaluation. For many frames, keep a ``CharacterAnimator`` (it caches)."""
    return CharacterAnimator(context, animation_set).evaluate(time, event_window=event_window)


__all__ = [
    "AnimationContext",
    "CharacterAnimator",
    "CharacterState",
    "Diagnostic",
    "evaluate_character",
    "single_clip_set",
]
