"""Motion Animation Studio.

A rig-first, data-driven 2D animation production system. Characters are animated by
editable, deterministic 2D rigs; AI services are optional, replaceable providers.

Milestone 2 delivered the foundation (configuration, schemas, Asset & Project Manager,
provider interfaces, CLI). Milestone 3 adds characters, identity consistency and 2D rigging
(FK, two-bone IK, joint constraints, turnarounds, diagnostics). Milestone 4 adds facial
rigs, expressions, visemes, phoneme mapping and timestamp-based lip-sync.
"""

from __future__ import annotations

__version__ = "0.4.0"
MILESTONE = 4

__all__ = ["MILESTONE", "__version__"]
