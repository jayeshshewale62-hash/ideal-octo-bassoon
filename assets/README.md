# Studio asset library

Shared, reusable studio assets that are not tied to one project. Each folder will hold
assets with metadata (`character.yaml`, `environment.yaml`) from later milestones.

| Folder | Contents | Introduced |
|---|---|---|
| `characters/` | Original characters: `<id>/character.yaml`, SVG parts, rig JSON, model sheets | M3 |
| `environments/` | Reusable environments: `<id>/environment.yaml` + layers | M6 |
| `props/` | Reusable props (SVG) | M6 |
| `fonts/` | Fonts with their licence files (OFL/Apache only) | M7 |
| `sfx/` | Sound effects with licence/provenance notes | M7 |

Rules: original or properly licensed material only; record source and licence; binary
media is git-ignored unless approved (ADR 0006). It is currently empty on purpose: no
placeholder artwork is committed.
