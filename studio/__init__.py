"""Motion Animation Studio.

A rig-first, data-driven 2D animation production system. Characters are animated by
editable, deterministic 2D rigs; AI services are optional, replaceable providers.

Milestone 2 delivered the foundation (configuration, schemas, Asset & Project Manager,
provider interfaces, CLI). Milestone 3 adds characters, identity consistency and 2D rigging
(FK, two-bone IK, joint constraints, turnarounds, diagnostics).
"""

from __future__ import annotations

__version__ = "0.3.0"
MILESTONE = 3

__all__ = ["MILESTONE", "__version__"]
