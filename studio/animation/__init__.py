"""Module 6 - Animation Engine (Milestone 5).

Deterministic, rig-driven 2D character animation. All motion is editable keyframe data
evaluated through the Milestone 3 rig (FK, two-bone IK, joint constraints) and the
Milestone 4 face (expressions, lip-sync). Nothing is a slideshow or per-frame image.

* ``schemas``    versioned clips, typed tracks and keyframes, curves, events, loop/playback,
  layers, sets, springs, deformation meshes;
* ``curves``     step/linear/smooth/ease/bezier/monotone-hermite interpolation, angles;
* ``clip``       compilation to channels, loop/pingpong/once time mapping, key editing,
  events;
* ``cycles``     procedural walk, run, idle (breathing, blinks) and gestures (wave, point,
  nod) baked into editable clips;
* ``secondary``  deterministic spring-damper lag for hair, ears, cloth, tails;
* ``mesh``       2D linear blend skinning plus blend shapes, with validation;
* ``evaluator``  ``CharacterAnimator(context, set).evaluate(t)``: the unified evaluator
  (layers -> pose -> IK -> FK -> springs -> parts -> meshes -> face/lip-sync -> events);
* ``validation``, ``store`` (versioned storage), ``preview`` (diagnostic contact sheets).

Not implemented: timeline editor, full-body IK, physics/cloth simulation, motion capture,
AI motion generation, rendering to video. Time is in seconds; frame rates are
per clip.
"""

from __future__ import annotations
