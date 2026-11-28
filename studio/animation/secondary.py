"""Secondary motion: damped springs that make hair, ears, clothing or tails lag behind.

Model (per spring), with a driver signal ``d(t)`` taken from the base animation (a bone's
world rotation, or its head x / y):

    m·x'' = k·(d - x) - c·x'          x follows d with lag and overshoot
    offset = clamp(gain · (x - d), ±max_displacement)   added to the target's rotation (°)

Determinism and stability:

* Integration is semi-implicit (symplectic) Euler on a **fixed grid** ``step`` (default
  1/120 s). Steps are subdivided so that ``h·√(k/m) ≤ 0.5``, well inside the stable
  region. Between grid points the state is interpolated linearly.
* **Reset / warm-up window:** the state at time ``t`` is simulated from rest (``x = d``,
  ``x' = 0``) starting at ``max(0, t - window)``, aligned to the grid. The result is
  therefore a pure function of ``t``, whatever order frames are evaluated in. The cost is
  bounded by ``window / step`` steps. Motion older than the window is forgotten (with the
  default 2 s window, springs with c ≥ 2 have settled well before that).
* ``t ≤ 0`` gives zero offsets (the reset state).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from studio.animation.schemas import SecondaryMotionSettings, SpringDefinition
from studio.core.exceptions import AnimationError

SignalFn = Callable[[float], dict[str, float]]


@dataclass(frozen=True)
class SpringOutput:
    spring: str
    offset: float
    clamped: bool


class SpringSolver:
    def __init__(self, settings: SecondaryMotionSettings, signals: SignalFn) -> None:
        for s in settings.springs:
            check_spring(s)
        self.settings = settings
        self.signals = signals
        self._cache: dict[int, dict[str, float]] = {}

    def _driver(self, k: int) -> dict[str, float]:
        if k not in self._cache:
            self._cache[k] = self.signals(k * self.settings.step)
        return self._cache[k]

    def offsets_at(self, t: float) -> dict[str, SpringOutput]:
        springs = self.settings.springs
        if not springs:
            return {}
        if not math.isfinite(t):
            raise AnimationError(f"time must be finite, got {t!r}")
        if t <= 0:
            return {s.id: SpringOutput(s.id, 0.0, False) for s in springs}
        dt = self.settings.step
        k_end = math.floor(t / dt + 1e-9)
        k_start = max(0, math.floor((t - self.settings.window) / dt + 1e-9))
        first = self._driver(k_start)
        state = {s.id: (first[s.id], 0.0) for s in springs}
        history = {k_start: {sid: st[0] for sid, st in state.items()}}
        for k in range(k_start, k_end + 1):
            d0, d1 = self._driver(k), self._driver(k + 1)
            for s in springs:
                x, v = state[s.id]
                state[s.id] = _integrate(s, x, v, d0[s.id], d1[s.id], dt)
            history[k + 1] = {sid: st[0] for sid, st in state.items()}
        frac = t / dt - k_end
        out: dict[str, SpringOutput] = {}
        drv0, drv1 = self._driver(k_end), self._driver(k_end + 1)
        for s in springs:
            x = history[k_end][s.id] * (1 - frac) + history[k_end + 1][s.id] * frac
            d = drv0[s.id] * (1 - frac) + drv1[s.id] * frac
            raw = s.gain * (x - d)
            clamped = abs(raw) > s.max_displacement
            out[s.id] = SpringOutput(
                s.id, max(-s.max_displacement, min(s.max_displacement, raw)), clamped
            )
        return out


def _integrate(
    s: SpringDefinition, x: float, v: float, d0: float, d1: float, dt: float
) -> tuple[float, float]:
    omega = math.sqrt(s.stiffness / s.mass)
    substeps = max(1, math.ceil(dt * omega / 0.5))
    h = dt / substeps
    for i in range(substeps):
        d = d0 + (d1 - d0) * (i + 1) / substeps
        a = (s.stiffness * (d - x) - s.damping * v) / s.mass
        v += a * h
        x += v * h
    return x, v


def check_spring(s: SpringDefinition) -> None:
    for name in ("stiffness", "damping", "mass", "gain", "max_displacement"):
        if not math.isfinite(getattr(s, name)):
            raise AnimationError(f"spring {s.id!r}: {name} must be finite")


def damping_ratio(s: SpringDefinition) -> float:
    """ζ = c / (2·√(k·m)): < 1 bouncy, 1 critical, > 1 sluggish."""
    return s.damping / (2 * math.sqrt(s.stiffness * s.mass))
