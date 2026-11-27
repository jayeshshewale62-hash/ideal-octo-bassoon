"""Module 4 - Character Rigging Engine and 5 - Facial Expression Engine.

Status: PLANNED for Milestones 3 (FK), 4 (face), 5 (IK/deform). This package is an
explicit placeholder that marks the module boundary. It contains no implementation
yet. See docs/MODULES.md.

Planned rig data contract (rig.json, versioned):
    bones        hierarchy with pivots, rest transforms, rotation/scale limits
    parts        SVG part IDs bound to bones (rigid) or to meshes (deforming)
    ik_chains    two-bone IK with pole targets and per-chain FK/IK blend
    deformers    mesh/warp lattices for organic squash and bends
    draw_order   per-view orders plus keyed draw-order switches
    swaps        replacement-part sets (hands, mouth shapes, smears, line-boil variants)
    views        turnaround variants (front / three_quarter / side / back)

Face rig (module 5): independent eye controls (gaze, pupils, lids, blinks), brows,
phoneme->viseme mouth sets, cheek deformation, expression presets with smooth blends.

Rule: animation comes from posing rigs frame by frame. It never comes from static
images panned by a camera or from per-frame AI images.
"""
