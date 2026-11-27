# ADR 0006: Binary media stays out of ordinary commits

**Status:** Accepted (Milestone 2)

## Decision
- `.gitignore` excludes raster, layered-art and audio formats under `projects/` and
  `assets/`. It also excludes all video files, renders, caches and model weights.
- SVG, YAML, JSON and Markdown assets are committed normally. The registry is always
  committed.
- To commit an approved binary asset: set `license.commit_approved: true` in its registry
  entry and `git add -f` the file.
- Git LFS is **not** configured. GitHub's free LFS quota is small, and paid storage needs
  owner approval. Large binaries will move to S3-compatible object storage in a later
  milestone (registry paths stay the same; a sync tool fetches by content hash).
- `.gitattributes` normalises text files to LF so content hashes match on every platform.
- Third-party reference videos are never committed. The repository is public.
