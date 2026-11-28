# ADR 0008: Character storage and rig conventions

**Status:** Accepted (Milestone 3)

## Decisions
- **Storage.** Characters live in `projects/<slug>/characters/<character-id>/` as
  `character.yaml` and `rig.yaml`, with earlier versions in `history/`. These are editable
  project data, like `story/` and `scenes/`. They are not registered assets, so they do not
  belong under `assets/`, which holds registered files. Artwork stays in the asset
  registry and is referenced by asset ID. The `characters/` folder is created on demand,
  so Milestone 2 projects remain valid. Milestone 2 docs had mentioned
  `assets/characters/<id>/character.yaml`; this ADR supersedes that note.
- **Versioning.** Every saved change increments `version` and writes the previous file to
  `history/character.v<N>.yaml` (same for rigs). A save based on an older version is
  refused instead of overwriting newer work. History files are never overwritten.
- **Coordinates.** SVG/screen space (+y down), degrees, positive = clockwise on screen. A
  bone's head is its local origin and it points along +x. Child rest positions are in the
  parent's local frame.
- **IK scope.** Analytic two-bone IK only, with an explicit bend sign (sign of the lower
  bone's relative rotation) or a pole point. Joint limits clamp the solution and the
  remaining error is reported. Multi-bone and full-body IK are out of scope.
- **Draw order.** Integer `z_order`, unique per view (overrides included). Ties are still
  broken by ID at runtime, so output is deterministic even for invalid data.
- **Turnaround enum.** `three_quarter_back` was added. The M2 value `three_quarter` keeps
  its meaning (three-quarter front). This change is additive.
- **Consistency.** Identity checks compare structured metadata with explicit roles
  (required / optional / view_specific / variation). No image analysis or similarity
  score is claimed.
- **Previews.** Diagnostics are SVG, written to git-ignored `renders/previews/`. They are
  labelled as diagnostics, reference artwork by path, and never overwrite registered assets.
- **Originality.** All Milestone 3 code is original. Legacy Branch A is third-party and
  must not be reused (ADR 0005, LEGACY_REUSE.md).
