"""Module 2 - Character Creation Engine and 3 - Character Consistency Manager (Milestone 3).

Implemented in Milestone 3:

* ``schemas``      versioned character contract: identity profile, parts, turnaround views,
  visual style, provenance (``characters/<id>/character.yaml``);
* ``templates``    reusable structure templates (``biped``, ``biped-minimal``) that build
  parts and a matching rig from proportions; no artwork is generated;
* ``parts``        hierarchical part transforms, inherited visibility/opacity, draw order;
* ``manager``      create/load/save with version history, artwork assignment via the
  asset registry, structure reuse from another character;
* ``consistency``  metadata-level identity comparison (views, versions, variants) with
  required / optional / view-specific / variation roles;
* ``validation``   coded checks (CHR, PRT, TRN; plus RIG/IK from studio.rig);
* ``preview``      deterministic diagnostic SVG (structure only).

Not implemented here: image-based consistency (golden images, palette delta-E on
renders) is planned for Milestone 8. Artwork creation is manual or comes from a later
image-provider milestone; this package never invents artwork.
"""

from __future__ import annotations
