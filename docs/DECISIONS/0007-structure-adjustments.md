# ADR 0007: Adjustments to the requested folder structure

**Status:** Accepted (Milestone 2)

The Milestone 2 brief listed a target structure. It is implemented as given, with these
justified additions:

| Addition | Why |
|---|---|
| `studio/__main__.py` | `python -m studio` works without the console script (used in tests and on machines without the entry point on PATH) |
| `studio/modules.py` | Single source of truth for the sixteen modules (`studio modules`, docs sync test) |
| `studio/core/paths.py` | Path-safety helpers used by schemas, projects and assets |
| `studio/core/formats.py` | Supported formats and content sniffing for asset registration |
| `studio/core/timecode.py` | Frame/timecode utilities (adapted legacy code) |
| `studio/core/environment.py` | Machine checks behind `studio doctor` |
| `studio/providers/base.py`, `registry.py` | Shared provider contract and configuration-driven selection |
| `.gitattributes` | LF normalisation for stable content hashes |
| `docs/DECISIONS/` ADRs 0001–0007 | Decision records requested by the brief |

Placeholder module packages (`story`, `characters`, `rig`, `animation`, `environments`,
`storyboard`, `scene`, `compose`, `render`, `audio`, `qc`) contain only a docstring
describing their boundary and data contract. A test enforces that they hold no
implementation in Milestone 2. Modules 3 and 5 share packages with 2 and 4 (`characters`,
`rig`), because they operate on the same data.
