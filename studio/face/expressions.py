"""Expression evaluation and blending (module 5). Deterministic and pure Python.

* :func:`evaluate_expression` -> a :class:`FaceState`: every rig control starts at its
  default; the expression's values override it, clamped to the control limits.
* :func:`blend_expressions` -> linear interpolation between two evaluated states with an
  optional ease. Both inputs are already within limits and the blend is convex, so the
  result is too.
* :func:`blend_many` -> normalized weighted average of several expressions.
* :class:`ExpressionTransition` / :func:`evaluate_transition` -> the time-based interface
  later animation milestones use (an expression change starting at a time and lasting a
  duration). It is not a timeline editor.

Categorical *shape* selections (mouth replacement drawings) cannot be interpolated. They
switch to the target's shape once the eased weight reaches 0.5.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from studio.core.exceptions import FaceError
from studio.face.schemas import Ease, FacialExpression, FacialRig


@dataclass(frozen=True)
class FaceIssue:
    code: str
    severity: str  # "error" | "warning"
    message: str


@dataclass
class FaceState:
    """Resolved control values for one moment: ``values[key]`` for every rig control."""

    values: dict[str, float]
    shapes: dict[str, str] = field(default_factory=dict)
    label: str = ""
    issues: list[FaceIssue] = field(default_factory=list)

    def get(self, key: str, default: float = 0.0) -> float:
        return self.values.get(key, default)

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "values": {k: round(v, 6) for k, v in sorted(self.values.items())},
            "shapes": dict(sorted(self.shapes.items())),
            "issues": [i.__dict__ for i in self.issues],
        }


def ease_weight(weight: float, ease: Ease) -> float:
    if ease is Ease.SMOOTHSTEP:
        return weight * weight * (3.0 - 2.0 * weight)
    return weight


def neutral_state(rig: FacialRig) -> FaceState:
    values = {f"{c.id}.{ch.name}": ch.default for c in rig.components for ch in c.channels}
    return FaceState(values, {}, "neutral")


def check_expression(rig: FacialRig, expression: FacialExpression) -> list[FaceIssue]:
    """Compatibility of an expression with a rig. Generic built-in presets may name
    components a rig does not have (warnings); custom expressions must match (errors)."""
    issues: list[FaceIssue] = []
    strict = not expression.builtin
    if expression.rig is not None and expression.rig != rig.id:
        issues.append(
            FaceIssue("EXP007", "error", f"expression is bound to {expression.rig}, not {rig.id}")
        )
    for key, value in sorted(expression.values.items()):
        comp_id, _, name = key.partition(".")
        comp = rig.component(comp_id)
        if comp is None:
            sev = "error" if strict else "warning"
            issues.append(FaceIssue("EXP002", sev, f"{key}: rig has no component {comp_id!r}"))
            continue
        channel = comp.channel(name)
        if channel is None:
            sev = "error" if strict else "warning"
            issues.append(
                FaceIssue("EXP002", sev, f"{key}: component {comp_id!r} has no control {name!r}")
            )
            continue
        if not channel.min <= value <= channel.max:
            issues.append(
                FaceIssue(
                    "EXP003",
                    "warning",
                    f"{key} = {value:g} is outside [{channel.min:g}, {channel.max:g}] and will be "
                    "clamped",
                )
            )
    for comp_id, shape in sorted(expression.shapes.items()):
        comp = rig.component(comp_id)
        sev = "error" if strict else "warning"
        if comp is None:
            issues.append(FaceIssue("EXP004", sev, f"shape for unknown component {comp_id!r}"))
        elif shape not in comp.shapes:
            issues.append(FaceIssue("EXP004", sev, f"component {comp_id!r} has no shape {shape!r}"))
    return issues


def evaluate_expression(rig: FacialRig, expression: FacialExpression) -> FaceState:
    state = neutral_state(rig)
    state.label = expression.id
    state.issues = check_expression(rig, expression)
    for key, value in expression.values.items():
        channel = rig.channel(key)
        if channel is None:
            continue  # reported above
        state.values[key] = min(channel.max, max(channel.min, value))
    for comp_id, shape in expression.shapes.items():
        comp = rig.component(comp_id)
        if comp is not None and shape in comp.shapes:
            state.shapes[comp_id] = shape
    return state


def _check_weight(weight: float) -> tuple[float, list[FaceIssue]]:
    if not isinstance(weight, int | float) or isinstance(weight, bool) or not math.isfinite(weight):
        raise FaceError(f"blend weight must be a finite number, got {weight!r}")
    if 0.0 <= weight <= 1.0:
        return float(weight), []
    clamped = min(1.0, max(0.0, float(weight)))
    return clamped, [
        FaceIssue("BLD002", "warning", f"blend weight {weight:g} clamped to {clamped:g}")
    ]


def blend_states(a: FaceState, b: FaceState, weight: float, ease: Ease = Ease.LINEAR) -> FaceState:
    w, issues = _check_weight(weight)
    e = ease_weight(w, ease)
    keys = sorted(set(a.values) | set(b.values))
    values = {}
    for key in keys:
        va = a.values.get(key, b.values.get(key, 0.0))
        vb = b.values.get(key, va)
        values[key] = va + (vb - va) * e
    shapes = {}
    for comp in sorted(set(a.shapes) | set(b.shapes)):
        chosen = b.shapes.get(comp) if e >= 0.5 else a.shapes.get(comp)
        if chosen is not None:
            shapes[comp] = chosen
    label = f"blend({a.label}->{b.label}, w={w:g}, {ease.value})"
    return FaceState(values, shapes, label, [*a.issues, *b.issues, *issues])


def blend_expressions(
    rig: FacialRig,
    a: FacialExpression,
    b: FacialExpression,
    weight: float,
    ease: Ease = Ease.LINEAR,
) -> FaceState:
    """Blend from ``a`` (weight 0) to ``b`` (weight 1)."""
    return blend_states(evaluate_expression(rig, a), evaluate_expression(rig, b), weight, ease)


def blend_many(rig: FacialRig, items: Sequence[tuple[FacialExpression, float]]) -> FaceState:
    """Weighted average of several expressions; weights are normalized to sum to 1."""
    if not items:
        raise FaceError("blend_many needs at least one expression")
    weights = []
    for expr, w in items:
        if isinstance(w, bool) or not isinstance(w, int | float) or not math.isfinite(w) or w < 0:
            raise FaceError(f"weight for {expr.id!r} must be a finite number >= 0, got {w!r}")
        weights.append(float(w))
    total = sum(weights)
    if total <= 0:
        raise FaceError("blend weights sum to zero")
    states = [evaluate_expression(rig, e) for e, _ in items]
    norm = [w / total for w in weights]
    values = {
        key: sum(s.values[key] * n for s, n in zip(states, norm, strict=True))
        for key in states[0].values
    }
    best = max(range(len(states)), key=lambda i: (norm[i], -i))
    issues = [i for s in states for i in s.issues]
    label = (
        "mix(" + ", ".join(f"{e.id}:{n:.3g}" for (e, _), n in zip(items, norm, strict=True)) + ")"
    )
    return FaceState(values, dict(states[best].shapes), label, issues)


@dataclass(frozen=True)
class ExpressionTransition:
    """Change from one expression to another starting at ``start`` over ``duration`` seconds."""

    from_expression: FacialExpression
    to_expression: FacialExpression
    start: float
    duration: float
    ease: Ease = Ease.SMOOTHSTEP

    def weight_at(self, time: float) -> float:
        for name, value in (("time", time), ("start", self.start), ("duration", self.duration)):
            if not math.isfinite(value):
                raise FaceError(f"transition {name} must be finite")
        if self.duration < 0:
            raise FaceError("transition duration must be >= 0")
        if time < self.start:
            return 0.0
        if self.duration == 0 or time >= self.start + self.duration:
            return 1.0
        return (time - self.start) / self.duration


def evaluate_transition(rig: FacialRig, transition: ExpressionTransition, time: float) -> FaceState:
    return blend_expressions(
        rig,
        transition.from_expression,
        transition.to_expression,
        transition.weight_at(time),
        transition.ease,
    )
