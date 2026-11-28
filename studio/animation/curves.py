"""Interpolation curves and compiled scalar channels (pure Python, deterministic).

Conventions (docs/ANIMATION.md#curves):

* A key's ``curve`` describes the segment from that key to the **next** key.
* Before the first key a channel holds the first value; after the last key it holds
  the last value.
* With ``u = (t - t_i) / (t_{i+1} - t_i)`` in [0, 1]:

  ===========  ============================================================
  step         v_i until the next key (the change happens *at* the next key)
  linear       u
  smooth       3u² - 2u³
  ease_in      u²
  ease_out     1 - (1 - u)²
  ease_in_out  4u³ for u < ½, else 1 - (-2u + 2)³ / 2
  bezier       CSS cubic-bezier(x1, y1, x2, y2) timing, solved for x = u
  hermite      cubic Hermite with Catmull-Rom tangents scaled by (1 - tension).
               Fritsch-Carlson limiting prevents overshoot unless the key sets
               ``allow_overshoot``. Loops use wrapped neighbours.
  ===========  ============================================================

* Every curve except overshooting bezier/hermite keeps values within
  [min(v_i, v_i+1), max(v_i, v_i+1)].
* Angle channels with ``shortest_path`` unwrap each next key to within ±180° of the
  previous one before interpolating.
"""

from __future__ import annotations

import bisect
import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass

from studio.animation.schemas import CurveDefinition, Interpolation

EPS = 1e-9


def ease(u: float, curve: CurveDefinition) -> float:
    """Eased fraction for non-hermite curves (u is clamped to [0, 1])."""
    u = 0.0 if u <= 0 else 1.0 if u >= 1 else u
    kind = curve.interpolation
    if kind is Interpolation.STEP:
        return 0.0
    if kind is Interpolation.LINEAR:
        return u
    if kind in (Interpolation.SMOOTH, Interpolation.HERMITE):
        return u * u * (3.0 - 2.0 * u)
    if kind is Interpolation.EASE_IN:
        return u * u
    if kind is Interpolation.EASE_OUT:
        return 1.0 - (1.0 - u) * (1.0 - u)
    if kind is Interpolation.EASE_IN_OUT:
        return 4.0 * u**3 if u < 0.5 else 1.0 - (-2.0 * u + 2.0) ** 3 / 2.0
    if kind is Interpolation.BEZIER:
        assert curve.bezier is not None
        return cubic_bezier(u, *curve.bezier)
    raise ValueError(f"unknown interpolation {kind!r}")  # pragma: no cover


def cubic_bezier(u: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """y for x = u on the curve (0,0)-(x1,y1)-(x2,y2)-(1,1). Deterministic solver."""
    if u <= 0:
        return 0.0
    if u >= 1:
        return 1.0

    def bx(s: float) -> float:
        return 3 * (1 - s) ** 2 * s * x1 + 3 * (1 - s) * s * s * x2 + s**3

    def dbx(s: float) -> float:
        return 3 * (1 - s) ** 2 * x1 + 6 * (1 - s) * s * (x2 - x1) + 3 * s * s * (1 - x2)

    s = u
    for _ in range(8):  # Newton
        d = dbx(s)
        if abs(d) < 1e-7:
            break
        s_next = s - (bx(s) - u) / d
        if not 0.0 <= s_next <= 1.0:
            break
        s = s_next
    if abs(bx(s) - u) > 1e-9:  # bisection fallback (monotone in s because x1, x2 in [0, 1])
        lo, hi = 0.0, 1.0
        for _ in range(60):
            s = (lo + hi) / 2
            if bx(s) < u:
                lo = s
            else:
                hi = s
    return 3 * (1 - s) ** 2 * s * y1 + 3 * (1 - s) * s * s * y2 + s**3


def wrap_degrees(delta: float) -> float:
    """Difference mapped into (-180, 180]."""
    d = math.fmod(delta, 360.0)
    if d <= -180.0:
        d += 360.0
    elif d > 180.0:
        d -= 360.0
    return d


@dataclass(frozen=True)
class CompiledChannel:
    times: tuple[float, ...]
    values: tuple[float, ...]
    curves: tuple[CurveDefinition, ...]
    tangents: tuple[float, ...]
    angle: bool = False

    @staticmethod
    def build(
        keys: Sequence[tuple[float, float, CurveDefinition]],
        *,
        angle: bool = False,
        shortest_path: bool = False,
        periodic: bool = False,
    ) -> CompiledChannel:
        ordered = sorted(keys, key=lambda k: k[0])
        times = [k[0] for k in ordered]
        values = [k[1] for k in ordered]
        curves = [k[2] for k in ordered]
        for a, b in itertools.pairwise(times):
            if b - a <= EPS:
                raise ValueError(f"two keys at the same time ({a:g}s)")
        if angle and shortest_path:
            for i in range(1, len(values)):
                values[i] = values[i - 1] + wrap_degrees(values[i] - values[i - 1])
        tangents = _tangents(times, values, curves, periodic)
        return CompiledChannel(tuple(times), tuple(values), tuple(curves), tuple(tangents), angle)

    def evaluate(self, t: float) -> float:
        times, values = self.times, self.values
        if t <= times[0]:
            return values[0]
        if t >= times[-1]:
            return values[-1]
        i = bisect.bisect_right(times, t) - 1
        t0, t1 = times[i], times[i + 1]
        v0, v1 = values[i], values[i + 1]
        curve = self.curves[i]
        u = (t - t0) / (t1 - t0)
        if curve.interpolation is Interpolation.STEP:
            return v0
        if curve.interpolation is Interpolation.HERMITE:
            dt = t1 - t0
            u2, u3 = u * u, u * u * u
            h00, h10 = 2 * u3 - 3 * u2 + 1, u3 - 2 * u2 + u
            h01, h11 = -2 * u3 + 3 * u2, u3 - u2
            return (
                h00 * v0 + h10 * dt * self.tangents[i] + h01 * v1 + h11 * dt * self.tangents[i + 1]
            )
        return v0 + (v1 - v0) * ease(u, curve)


def _tangents(
    times: list[float], values: list[float], curves: list[CurveDefinition], periodic: bool
) -> list[float]:
    n = len(times)
    if n < 2:
        return [0.0] * n
    secants = [(values[i + 1] - values[i]) / (times[i + 1] - times[i]) for i in range(n - 1)]
    m = [0.0] * n
    for i in range(n):
        if 0 < i < n - 1:
            left, right = secants[i - 1], secants[i]
        elif periodic:
            left, right = secants[-1], secants[0]
        elif i == 0:
            left = right = secants[0]
        else:
            left = right = secants[-1]
        tension = curves[i].tension
        m[i] = (left + right) / 2 * (1 - tension)
        if not curves[i].allow_overshoot and left * right <= 0:
            m[i] = 0.0  # local extremum or flat: no overshoot past the key value
    if periodic:
        m[-1] = m[0]
    # Fritsch-Carlson limiting per segment.
    for i in range(n - 1):
        if curves[i].allow_overshoot:
            continue
        d = secants[i]
        if abs(d) < EPS:
            m[i] = 0.0
            m[i + 1] = 0.0
            continue
        a, b = m[i] / d, m[i + 1] / d
        if a < 0:
            m[i], a = 0.0, 0.0
        if b < 0:
            m[i + 1], b = 0.0, 0.0
        r = a * a + b * b
        if r > 9:
            tau = 3 / math.sqrt(r)
            m[i] = tau * a * d
            m[i + 1] = tau * b * d
    if periodic:  # both ends share one tangent; the smaller one satisfies both limits
        shared = m[0] if abs(m[0]) <= abs(m[-1]) else m[-1]
        m[0] = m[-1] = shared
    return m
