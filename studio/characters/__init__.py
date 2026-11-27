"""Module 2 - Character Creation Engine and 3 - Character Consistency Manager.

Status: PLANNED for Milestones 3 and 8. This package is an explicit placeholder that marks
the module boundary. It contains no implementation yet. See docs/MODULES.md.

Character creation (module 2) produces *original* characters as layered SVG
parts with a canonical palette, proportions in head-heights, turnaround views
(front, three-quarter, side, back) and a model sheet. Identity metadata already has a
schema: :class:`studio.core.schemas.CharacterIdentity`.

The consistency manager (module 3) compares renders of fixed poses against golden
images and checks palette (delta-E) and proportion tolerances, so characters never
drift between shots.

Boundaries:
    inputs   character brief, artwork files
    outputs  assets/characters/<id>/character.yaml, parts.svg, model sheet (registered assets)
    depends  studio.core; module 4 (rig) consumes parts.svg
"""
