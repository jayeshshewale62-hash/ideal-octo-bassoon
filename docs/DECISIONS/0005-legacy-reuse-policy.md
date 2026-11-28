# ADR 0005: Legacy branches are sources, not architecture

**Status:** Accepted (Milestone 2)

## Decision
- Branches `ccr-f3c28d1b-6ialqh` and `ccr-5cb67ed4-c3se5u` are preserved unchanged and
  never merged wholesale.
- A component is adapted only when the milestone that needs it starts, after inspection
  and tests, and only with a clear licence. Its file header and `docs/LEGACY_REUSE.md`
  record branch, commit, path, changes and licence.
- Milestone 2 adapted only the frame/timecode helpers from Branch B's session-authored
  `captions.py`, with equivalence tests against the legacy formulas.
- Branch A has no licence file and is treated as reference only until the owner clarifies
  its status.
- `legacy/` holds an index pointing at pinned commits, not copied code.
