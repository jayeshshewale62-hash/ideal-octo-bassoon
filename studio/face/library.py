"""Loaders for the packaged reference data (expressions, viseme sets, phoneme maps).

Every loader accepts either a built-in name or a path to a file with the same schema, so
language mappings and viseme sets can be replaced without touching engine code.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from studio.core.exceptions import FaceError
from studio.core.validation import load_model
from studio.face.schemas import ExpressionLibrary, FacialExpression, PhonemeMap, VisemeSet

DATA_DIR = Path(__file__).resolve().parent / "data"
MAPS_DIR = DATA_DIR / "phoneme_maps"
DEFAULT_MAP = "en_arpabet"


@cache
def builtin_expressions() -> tuple[FacialExpression, ...]:
    library = load_model(ExpressionLibrary, DATA_DIR / "expressions.yaml")
    return tuple(library.expressions)


def builtin_expression(expression_id: str) -> FacialExpression | None:
    return next((e for e in builtin_expressions() if e.id == expression_id), None)


@cache
def _builtin_viseme_set() -> VisemeSet:
    return load_model(VisemeSet, DATA_DIR / "visemes.yaml")


def load_viseme_set(name_or_path: str = "default") -> VisemeSet:
    if name_or_path == "default":
        return _builtin_viseme_set()
    path = Path(name_or_path)
    if not path.is_file():
        raise FaceError(f"viseme set {name_or_path!r} not found (built-in: default)")
    return load_model(VisemeSet, path)


def phoneme_map_names() -> list[str]:
    return sorted(p.stem for p in MAPS_DIR.glob("*.yaml"))


def load_phoneme_map(name_or_path: str = DEFAULT_MAP) -> PhonemeMap:
    builtin = MAPS_DIR / f"{name_or_path}.yaml"
    if builtin.is_file():
        return load_model(PhonemeMap, builtin)
    path = Path(name_or_path)
    if not path.is_file():
        known = ", ".join(phoneme_map_names())
        raise FaceError(f"phoneme map {name_or_path!r} not found (built-in: {known})")
    return load_model(PhonemeMap, path)
