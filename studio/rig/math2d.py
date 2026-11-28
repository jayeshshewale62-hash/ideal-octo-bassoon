"""Pure-Python 2D geometry for rigs: points, affine matrices and angle helpers.

Conventions (shared by FK, IK, parts and previews; see docs/RIGGING.md):

* Coordinates are **SVG/screen space**: +x to the right, **+y downwards**.
* Angles are in **degrees**. A positive angle rotates +x towards +y, which looks
  **clockwise on screen**.
* Matrices are 2x3 affine transforms ``[a c e; b d f]``, applied to column vectors:
  ``x' = a*x + c*y + e``, ``y' = b*x + d*y + f`` (the same layout as SVG ``matrix()``).
* Composition ``m1 @ m2`` applies ``m2`` first, then ``m1``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EPSILON = 1e-9


@dataclass(frozen=True)
class Vec2:
    x: float
    y: float

    def __add__(self, other: Vec2) -> Vec2:
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vec2) -> Vec2:
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, k: float) -> Vec2:
        return Vec2(self.x * k, self.y * k)

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def angle(self) -> float:
        """Direction in degrees (atan2 in screen space)."""
        return math.degrees(math.atan2(self.y, self.x))

    def cross(self, other: Vec2) -> float:
        return self.x * other.y - self.y * other.x

    def distance_to(self, other: Vec2) -> float:
        return (self - other).length()

    def rounded(self, digits: int = 6) -> tuple[float, float]:
        return (_clean(round(self.x, digits)), _clean(round(self.y, digits)))

    @staticmethod
    def polar(length: float, degrees: float) -> Vec2:
        r = math.radians(degrees)
        return Vec2(length * math.cos(r), length * math.sin(r))


def _clean(value: float) -> float:
    """Turn -0.0 into 0.0 so output is stable."""
    return 0.0 if value == 0 else value


@dataclass(frozen=True)
class Affine:
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    @staticmethod
    def identity() -> Affine:
        return Affine()

    @staticmethod
    def translation(x: float, y: float) -> Affine:
        return Affine(e=x, f=y)

    @staticmethod
    def rotation(degrees: float) -> Affine:
        r = math.radians(degrees)
        cos, sin = math.cos(r), math.sin(r)
        return Affine(a=cos, b=sin, c=-sin, d=cos)

    @staticmethod
    def scaling(sx: float, sy: float) -> Affine:
        return Affine(a=sx, d=sy)

    @staticmethod
    def from_trs(x: float, y: float, degrees: float, sx: float = 1.0, sy: float = 1.0) -> Affine:
        """Translate @ Rotate @ Scale (scale applied first)."""
        return Affine.translation(x, y) @ Affine.rotation(degrees) @ Affine.scaling(sx, sy)

    def __matmul__(self, o: Affine) -> Affine:
        return Affine(
            a=self.a * o.a + self.c * o.b,
            b=self.b * o.a + self.d * o.b,
            c=self.a * o.c + self.c * o.d,
            d=self.b * o.c + self.d * o.d,
            e=self.a * o.e + self.c * o.f + self.e,
            f=self.b * o.e + self.d * o.f + self.f,
        )

    def apply(self, p: Vec2) -> Vec2:
        return Vec2(self.a * p.x + self.c * p.y + self.e, self.b * p.x + self.d * p.y + self.f)

    def apply_vector(self, v: Vec2) -> Vec2:
        """Transform a direction (ignores translation)."""
        return Vec2(self.a * v.x + self.c * v.y, self.b * v.x + self.d * v.y)

    def determinant(self) -> float:
        return self.a * self.d - self.b * self.c

    def inverse(self) -> Affine:
        det = self.determinant()
        if abs(det) < EPSILON:
            raise ValueError("matrix is singular (zero scale) and cannot be inverted")
        a, b, c, d = self.d / det, -self.b / det, -self.c / det, self.a / det
        return Affine(
            a=a, b=b, c=c, d=d, e=-(a * self.e + c * self.f), f=-(b * self.e + d * self.f)
        )

    @property
    def origin(self) -> Vec2:
        return Vec2(self.e, self.f)

    @property
    def rotation_degrees(self) -> float:
        """Rotation of the local +x axis."""
        return math.degrees(math.atan2(self.b, self.a))

    @property
    def scale(self) -> tuple[float, float]:
        """Lengths of the transformed unit axes (always positive)."""
        return (math.hypot(self.a, self.b), math.hypot(self.c, self.d))

    def svg(self, digits: int = 4) -> str:
        values = (self.a, self.b, self.c, self.d, self.e, self.f)
        return "matrix(" + " ".join(f"{_clean(round(v, digits)):g}" for v in values) + ")"

    def almost_equal(self, other: Affine, tol: float = 1e-9) -> bool:
        return all(
            abs(x - y) <= tol
            for x, y in zip(
                (self.a, self.b, self.c, self.d, self.e, self.f),
                (other.a, other.b, other.c, other.d, other.e, other.f),
                strict=True,
            )
        )


def normalize_angle(degrees: float) -> float:
    """Map an angle into (-180, 180]."""
    a = math.fmod(degrees, 360.0)
    if a <= -180.0:
        a += 360.0
    elif a > 180.0:
        a -= 360.0
    return _clean(a)


def wrap_into_range(degrees: float, low: float, high: float) -> float:
    """Pick the representation ``degrees + 360k`` inside [low, high], or else the one
    closest to that interval. Deterministic: ties prefer the smaller value."""
    base = normalize_angle(degrees)
    best: float | None = None
    best_distance = math.inf
    for k in range(-3, 4):
        candidate = base + 360.0 * k
        if low <= candidate <= high:
            distance = 0.0
        else:
            distance = min(abs(candidate - low), abs(candidate - high))
        if distance < best_distance - EPSILON:
            best, best_distance = candidate, distance
    assert best is not None
    return best


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
