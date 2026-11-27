"""Catalogue of the sixteen studio modules: package, milestone and current status.

The source of truth for ``studio modules`` and the summary table in docs/MODULES.md.
A test (tests/unit/test_modules.py) keeps this list, the packages and the docs in sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ModuleStatus(StrEnum):
    FOUNDATION = "foundation"  # implemented in Milestone 2
    INTERFACES = "interfaces"  # contracts + mocks exist; real implementation later
    PLANNED = "planned"  # documented boundary only


@dataclass(frozen=True)
class ModuleSpec:
    number: int
    name: str
    package: str
    milestone: int
    status: ModuleStatus
    summary: str


MODULES: tuple[ModuleSpec, ...] = (
    ModuleSpec(
        1,
        "Story Development Engine",
        "studio.story",
        9,
        ModuleStatus.PLANNED,
        "Premise -> outline -> beat sheet -> script; LLM optional",
    ),
    ModuleSpec(
        2,
        "Character Creation Engine",
        "studio.characters",
        3,
        ModuleStatus.PLANNED,
        "Original characters: SVG parts, palettes, turnarounds, model sheets",
    ),
    ModuleSpec(
        3,
        "Character Consistency Manager",
        "studio.characters",
        8,
        ModuleStatus.PLANNED,
        "Canonical model sheets, palette and proportion checks, drift detection",
    ),
    ModuleSpec(
        4,
        "Character Rigging Engine",
        "studio.rig",
        3,
        ModuleStatus.PLANNED,
        "Bone hierarchy, FK/IK, pivots, limits, draw order, mesh/warp deform",
    ),
    ModuleSpec(
        5,
        "Facial Expression Engine",
        "studio.rig",
        4,
        ModuleStatus.PLANNED,
        "Eyes, lids, brows, visemes, cheeks, expression presets and blends",
    ),
    ModuleSpec(
        6,
        "Animation Engine",
        "studio.animation",
        5,
        ModuleStatus.PLANNED,
        "Curves, cycles, acting library, secondary motion, squash/stretch, line boil",
    ),
    ModuleSpec(
        7,
        "Environment Creation Engine",
        "studio.environments",
        6,
        ModuleStatus.PLANNED,
        "Layered backgrounds with depth, props, lighting tint",
    ),
    ModuleSpec(
        8,
        "Storyboard Engine",
        "studio.storyboard",
        6,
        ModuleStatus.PLANNED,
        "Script -> shot list -> animatic and contact sheets",
    ),
    ModuleSpec(
        9,
        "Camera and Scene Engine",
        "studio.scene",
        6,
        ModuleStatus.PLANNED,
        "Shot sizes, moves, parallax, staging, transitions",
    ),
    ModuleSpec(
        10,
        "AI Image Generation Engine",
        "studio.providers.image",
        9,
        ModuleStatus.INTERFACES,
        "Concept art and background plates via replaceable providers",
    ),
    ModuleSpec(
        11,
        "Voice Generation Engine",
        "studio.providers.tts",
        4,
        ModuleStatus.INTERFACES,
        "TTS or recorded voice per character; alignment for lip-sync",
    ),
    ModuleSpec(
        12,
        "Audio and Sound Effects Engine",
        "studio.audio",
        7,
        ModuleStatus.PLANNED,
        "SFX cues, ambience, music, ducking, loudness mastering",
    ),
    ModuleSpec(
        13,
        "Video Composition Engine",
        "studio.compose",
        7,
        ModuleStatus.PLANNED,
        "Composite characters, backgrounds, FX, titles and captions per shot",
    ),
    ModuleSpec(
        14,
        "Rendering Engine",
        "studio.render",
        7,
        ModuleStatus.PLANNED,
        "Frame scheduling, parallel workers, caching, FFmpeg encode, backends",
    ),
    ModuleSpec(
        15,
        "Quality Control Engine",
        "studio.qc",
        8,
        ModuleStatus.PLANNED,
        "Automatic pass/fail checks on renders and projects",
    ),
    ModuleSpec(
        16,
        "Asset and Project Manager",
        "studio.core",
        2,
        ModuleStatus.FOUNDATION,
        "Projects, asset registry, hashing, versions, provenance, validation",
    ),
)
