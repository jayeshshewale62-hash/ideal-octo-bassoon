# legacy/: index of legacy branches (no copied code)

This folder holds **no legacy code**. It records where reusable legacy material lives, so
later milestones can find it without merging whole branches. The full assessment is in
[`docs/LEGACY_REUSE.md`](../docs/LEGACY_REUSE.md).

| Branch | Pinned commit | Path | Status |
|---|---|---|---|
| `ccr-f3c28d1b-6ialqh` | `c312cfd16b72dd3f84228cd05aa45206a3bc666b` | `reachmora-2d-longform/` | **Third-party, no permission: must not be reused** (owner confirmation, M3) |
| `ccr-5cb67ed4-c3se5u` | `431161b44c11e644e14ee5901d9a9111f245b83d` | `cartoon-audio-short/kit/` | Partly reusable (session-authored tools, MIT third-party parts) |

Read a legacy file without checking the branch out:

```bash
git fetch origin ccr-5cb67ed4-c3se5u
git show 431161b:cartoon-audio-short/kit/engine/captions.py
```

Rules:

- Never merge, rebase, delete or force-push these branches.
- Adapt a component only when its milestone needs it, after it passes tests, with
  provenance recorded in the new file's header and in `docs/LEGACY_REUSE.md`.
- Keep third-party licence notices with any adapted third-party code.
