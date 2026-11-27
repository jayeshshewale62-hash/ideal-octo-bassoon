"""Character identity and consistency manager (module 3, metadata level).

Compares *structured identity metadata* between turnaround views, character versions and
character variants. It does **not** look at pixels: there is no image recognition and no
AI similarity score. Visual (golden-image) checks are planned for Milestone 8.

Every identity property has a role (see :class:`IdentityRole`):

==============  ==========================================================  ===========
Role            Meaning                                                     Difference
==============  ==========================================================  ===========
required        defines who the character is; must not change              error
optional        tracked; a change is worth a look                          warning
view_specific   expected to differ between turnaround views                info
variation       editable artistic variation (e.g. an outfit change)        info
==============  ==========================================================  ===========

Defaults are in :data:`DEFAULT_ROLES`. A character can override any property (or a whole
group such as ``palette``) in ``identity.policy``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from studio.characters.schemas import CharacterDefinition, IdentityRole, IdentityValue

DEFAULT_ROLES: dict[str, IdentityRole] = {
    "name": IdentityRole.REQUIRED,
    "height_units": IdentityRole.REQUIRED,
    "proportions.height_heads": IdentityRole.REQUIRED,
    "proportions.shoulder_width_heads": IdentityRole.VIEW_SPECIFIC,
    "proportions.arm_length_heads": IdentityRole.OPTIONAL,
    "proportions.leg_length_heads": IdentityRole.OPTIONAL,
    "head.shape": IdentityRole.REQUIRED,
    "head.width_ratio": IdentityRole.VIEW_SPECIFIC,
    "palette": IdentityRole.REQUIRED,  # applies to every palette.<colour>
    "clothing": IdentityRole.REQUIRED,
    "hair": IdentityRole.REQUIRED,
    "distinctive_features": IdentityRole.REQUIRED,
    "personality": IdentityRole.OPTIONAL,
    "voice": IdentityRole.OPTIONAL,
    "part_ids": IdentityRole.REQUIRED,
    "rig": IdentityRole.REQUIRED,
}

NUMERIC_PROPERTIES = frozenset(
    {
        "height_units",
        "proportions.height_heads",
        "proportions.shoulder_width_heads",
        "proportions.arm_length_heads",
        "proportions.leg_length_heads",
        "head.width_ratio",
    }
)
SEVERITY = {
    IdentityRole.REQUIRED: "error",
    IdentityRole.OPTIONAL: "warning",
    IdentityRole.VIEW_SPECIFIC: "info",
    IdentityRole.VARIATION: "info",
}


def identity_properties(character: CharacterDefinition) -> dict[str, IdentityValue]:
    """Flatten the identity metadata into comparable properties."""
    ident = character.identity
    props: dict[str, IdentityValue] = {
        "name": character.name,
        "height_units": ident.height_units,
        "proportions.height_heads": ident.proportions.height_heads,
        "head.shape": ident.head.shape,
        "head.width_ratio": ident.head.width_ratio,
        "clothing": sorted(ident.clothing),
        "hair": ident.hair,
        "distinctive_features": sorted(ident.distinctive_features),
        "personality": sorted(ident.personality),
        "voice": f"{ident.voice.provider}:{ident.voice.voice_id}",
        "part_ids": sorted(p.id for p in character.parts),
        "rig": character.rig or "",
    }
    for key in ("shoulder_width_heads", "arm_length_heads", "leg_length_heads"):
        value = getattr(ident.proportions, key)
        if value is not None:
            props[f"proportions.{key}"] = value
    for colour, value in ident.palette.items():
        props[f"palette.{colour}"] = value
    return props


def role_of(prop: str, policy: dict[str, IdentityRole] | None = None) -> IdentityRole:
    policy = policy or {}
    group = prop.split(".", 1)[0]
    for key in (prop, group):
        if key in policy:
            return policy[key]
    for key in (prop, group):
        if key in DEFAULT_ROLES:
            return DEFAULT_ROLES[key]
    return IdentityRole.OPTIONAL


def is_known_property(prop: str, props: dict[str, IdentityValue]) -> bool:
    """Known if present on the character, or a defined property / palette colour name."""
    if prop in props or prop in DEFAULT_ROLES or prop in NUMERIC_PROPERTIES:
        return True
    return prop.startswith("palette.") and len(prop) > len("palette.")


def values_equal(prop: str, a: IdentityValue | None, b: IdentityValue | None, tol: float) -> bool:
    if a is None or b is None:
        return a is b
    if prop in NUMERIC_PROPERTIES or (isinstance(a, int | float) and isinstance(b, int | float)):
        if not isinstance(a, int | float) or not isinstance(b, int | float):
            return False
        fa, fb = float(a), float(b)
        return math.isclose(fa, fb, rel_tol=tol, abs_tol=1e-9)
    if isinstance(a, list) or isinstance(b, list):
        if not isinstance(a, list) or not isinstance(b, list):
            return False
        return sorted(s.strip().lower() for s in a) == sorted(s.strip().lower() for s in b)
    return str(a).strip().lower() == str(b).strip().lower()


@dataclass(frozen=True)
class IdentityDifference:
    prop: str
    role: IdentityRole
    base: IdentityValue | None
    other: IdentityValue | None

    @property
    def severity(self) -> str:
        return SEVERITY[self.role]

    def to_dict(self) -> dict[str, object]:
        return {
            "property": self.prop,
            "role": self.role.value,
            "severity": self.severity,
            "base": self.base,
            "other": self.other,
        }


@dataclass
class ConsistencyReport:
    base: str
    other: str
    differences: list[IdentityDifference]

    @property
    def consistent(self) -> bool:
        """True when no *required* identity property differs."""
        return not any(d.role is IdentityRole.REQUIRED for d in self.differences)

    def to_dict(self) -> dict[str, object]:
        return {
            "base": self.base,
            "other": self.other,
            "consistent": self.consistent,
            "differences": [d.to_dict() for d in self.differences],
        }


def compare_properties(
    base: dict[str, IdentityValue],
    other: dict[str, IdentityValue],
    policy: dict[str, IdentityRole] | None,
    tolerance: float,
) -> list[IdentityDifference]:
    diffs = []
    for prop in sorted(set(base) | set(other)):
        a, b = base.get(prop), other.get(prop)
        if not values_equal(prop, a, b, tolerance):
            diffs.append(IdentityDifference(prop, role_of(prop, policy), a, b))
    return diffs


def compare_characters(base: CharacterDefinition, other: CharacterDefinition) -> ConsistencyReport:
    """Compare two definitions: two versions of one character, or a character and a variant.
    The base character's policy and tolerance decide the roles."""
    diffs = compare_properties(
        identity_properties(base),
        identity_properties(other),
        base.identity.policy,
        base.identity.proportions.tolerance,
    )
    return ConsistencyReport(f"{base.id} v{base.version}", f"{other.id} v{other.version}", diffs)


def view_differences(
    character: CharacterDefinition, overrides: dict[str, IdentityValue]
) -> tuple[list[IdentityDifference], list[str], list[str]]:
    """Differences a view's ``identity_overrides`` introduce.

    Returns (differences, unknown_property_names, type_errors).
    """
    base = identity_properties(character)
    diffs: list[IdentityDifference] = []
    unknown: list[str] = []
    type_errors: list[str] = []
    for prop, value in sorted(overrides.items()):
        if not is_known_property(prop, base):
            unknown.append(prop)
            continue
        if prop in NUMERIC_PROPERTIES and (
            isinstance(value, bool) or not isinstance(value, int | float)
        ):
            type_errors.append(f"{prop} must be a number")
            continue
        if not values_equal(prop, base.get(prop), value, character.identity.proportions.tolerance):
            diffs.append(
                IdentityDifference(
                    prop, role_of(prop, character.identity.policy), base.get(prop), value
                )
            )
    return diffs, unknown, type_errors
