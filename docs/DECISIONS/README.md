# Architecture Decision Records

Short records of decisions that shape the project. Change one only with the repository
owner's approval. To supersede one, add a new ADR that references it rather than editing
the old one.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-rig-first-architecture.md) | Rig-first, data-driven 2D engine with replaceable providers | Accepted (M1) |
| [0002](0002-python-uv-and-dependencies.md) | Python 3.12+/3.13, uv, minimal dependencies, skia as optional extra | Accepted (M2) |
| [0003](0003-file-based-asset-registry.md) | Per-project JSON asset registry instead of a database | Accepted (M2) |
| [0004](0004-provider-interfaces.md) | Provider interfaces with `none`/`mock`, disabled by default, credentials via env | Accepted (M2) |
| [0005](0005-legacy-reuse-policy.md) | Legacy branches are sources, not architecture | Accepted (M2) |
| [0006](0006-binary-assets-out-of-git.md) | Binary media stays out of ordinary commits; no LFS yet | Accepted (M2) |
| [0007](0007-structure-adjustments.md) | Small changes to the requested folder structure | Accepted (M2) |
| [0008](0008-character-storage-and-rig-conventions.md) | Character storage, versioning, rig/IK conventions, turnaround enum | Accepted (M3) |
