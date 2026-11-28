"""Module 4 - Character Rigging Engine (Milestone 3). The face rig is ``studio.face`` (M4).

Implemented in Milestone 3:

* ``studio.rig.schemas``    versioned rig data contract (bones, rest transforms, joint
  constraints, two-bone IK chains, control handles) stored as ``rig.yaml``;
* ``studio.rig.math2d``     pure-Python 2D affine maths and angle helpers;
* ``studio.rig.fk``         forward kinematics with constraint enforcement;
* ``studio.rig.ik``         analytic two-bone IK (reach checks, bend/pole, joint limits,
  degenerate targets);
* ``studio.rig.validation`` coded rig checks (RIG0xx, IK0xx).

Deferred (later milestones): mesh/warp deformers, keyed draw-order switches,
replacement-part swaps, FK/IK blending over time and multi-bone/full-body IK. The face rig
(module 5) lives in ``studio.face`` (Milestone 4).

Rule: animation comes from posing rigs frame by frame. It never comes from static
images panned by a camera or from per-frame AI images.

Conventions: screen space (+y down), degrees, positive = clockwise on screen. A bone's
head is its local origin and it points along local +x. See docs/RIGGING.md.
"""

from __future__ import annotations
