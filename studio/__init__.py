"""Motion Animation Studio.

A rig-first, data-driven 2D animation production system. Characters are animated by
editable, deterministic 2D rigs; AI services are optional, replaceable providers.

Milestone 2 delivered the foundation (configuration, schemas, Asset & Project Manager,
provider interfaces, CLI). Milestone 3 adds characters, identity consistency and 2D rigging
(FK, two-bone IK, joint constraints, turnarounds, diagnostics). Milestone 4 adds facial
rigs, expressions, visemes, phoneme mapping and timestamp-based lip-sync. Milestone 5 adds
the keyframe animation engine, motion cycles and the unified character evaluator.
"""

from __future__ import annotations

__version__ = "0.5.0"
MILESTONE = 5

__all__ = ["MILESTONE", "__version__"]
