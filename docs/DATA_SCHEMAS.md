# Data Schemas

All schemas are pydantic v2 models in `studio/core/schemas.py`. Every persisted document
has `schema_version` (currently `1`). Unknown fields are rejected so typos surface
immediately. Print machine-readable JSON Schema with:

```bash
studio schema export            # all
studio schema export character  # one
```

| Schema name | Model | File |
|---|---|---|
| `studio_config` | `StudioConfig` | `config/studio.yaml` |
| `render_profiles` | `RenderProfilesFile` | `config/render_profiles.yaml` |
| `providers` | `ProvidersConfig` | `config/providers.yaml` |
| `project` | `ProjectMetadata` | `projects/<slug>/project.yaml` |
| `project_settings` | `ProjectSettings` | `projects/<slug>/settings.yaml` |
| `asset_registry` | `AssetRegistryFile` (+ `AssetRecord`, `AssetVersion`) | `projects/<slug>/assets/registry.json` |
| `character` | `CharacterIdentity` | `assets/characters/<id>/character.yaml` (from M3) |
| `environment` | `EnvironmentMetadata` | `assets/environments/<id>/environment.yaml` (from M6) |

## Identifiers

| Kind | Format | Example |
|---|---|---|
| Project | `prj_` + 32 hex (UUID4) | `prj_d5e80bb76e6c4232ba836173b764ca67` |
| Asset | `ast_` + 16 hex (random, unique per registry) | `ast_3f9c0a1b2c3d4e5f` |
| Character | `chr_` + slug | `chr_mira` |
| Environment | `env_` + slug | `env_forest_night` |
| Content hash | `sha256:` + 64 hex | text formats hashed with LF line endings |

## Asset record

```json
{
  "id": "ast_3f9c0a1b2c3d4e5f",
  "name": "Hero head",
  "category": "character",
  "format": "svg",
  "project_id": "prj_…",
  "versions": [
    {"version": 1, "path": "assets/characters/hero-head.v1.svg",
     "content_hash": "sha256:…", "size_bytes": 1234,
     "created_at": "2026-11-27T17:00:00Z", "note": ""}
  ],
  "source": {"kind": "original", "author": "", "url": "", "notes": ""},
  "license": {"spdx": "proprietary", "attribution": "", "url": "", "commit_approved": false},
  "ai_provenance": null,
  "dependencies": [],
  "tags": ["hero"],
  "created_at": "…", "updated_at": "…"
}
```

Rules enforced:

- versions are numbered 1..n in order;
- paths are relative, have no `..` and are POSIX;
- `source.kind: ai_generated` requires `ai_provenance` (provider, model, prompt, seed, parameters, time, human review flag);
- an asset cannot depend on itself or list duplicate dependencies;
- asset IDs are unique per registry, and every asset belongs to the registry's project.

**Categories:** character, environment, prop, texture, audio, voice, sfx, music, font, script,
storyboard, data, reference, other.
**Formats:** svg, png, jpg, webp, ora, psd, kra, wav, mp3, flac, ogg, json, yaml, txt, md, ttf,
otf, woff2. Content is sniffed: a renamed or corrupt file is rejected. Video files are not
asset formats.

## Render profile

Fields: `label`, `purpose` (final/preview), `width`, `height` (even for yuv420p), `fps`
(0–120, fractional allowed), and `video` (mp4/h264/libx264, profile, yuv420p, crf 0–51,
preset, bt709, faststart). Also `audio` (aac, 44.1/48 kHz, channels, bitrate,
`loudness_lufs`, `true_peak_dbtp`). The file's `default` must name a defined profile.

## Provider selection

`provider` (`none` | `mock` | catalogue name), `options` (secret-looking keys rejected) and
`credentials_env` (environment-variable *names*, upper case). `allow_network` gates
network providers.

## Character identity (metadata only in M2)

`id`, `name`, `version`, `status` (concept → designed → rigged → approved; rigged or
approved requires `rig_asset`), `description`, `personality`, `palette` (`#RRGGBB`),
`proportions` (in head-heights, with tolerance), `required_views` (must include `front`;
default front, three_quarter, side, back), `model_sheet_asset`, `rig_asset`, `voice`, and
`original_design` (must be true).

## Validation issue codes

| Code | Severity | Meaning |
|---|---|---|
| PRJ000 | error | project directory does not exist |
| PRJ001 | error | `project.yaml` missing: not a project |
| PRJ002 | error | `project.yaml` invalid |
| PRJ003 | error | `settings.yaml` missing or invalid |
| PRJ004 | error | required directory missing |
| PRJ005 | error | settings reference an unknown render profile |
| PRJ006 | warning | story/storyboard placeholder missing |
| PRJ007 | error | story/storyboard file malformed |
| PRJ008 | warning | project README missing |
| PRJ009 | warning | folder name differs from slug |
| AST001 | error | registry missing |
| AST002 | error | registry invalid (schema, JSON, unsafe path) |
| AST003 | error | registry belongs to another project |
| AST010 | error | registered file missing |
| AST011 | error | file content changed since registration |
| AST012 | error | path escapes the project (e.g. via symlink) |
| AST013 | error | dependency not registered |
| AST014 | error | dependency cycle |
| AST015 | warning | same content registered under two assets |
| AST016 | error | file format does not match the registry |
| AST017 | warning | large binary not approved for git (use object storage) |
| AST018 | warning | file in `assets/` is not registered |

## Schema evolution

Bump `schema_version` when a change is not backwards compatible, and add a migration
function from N-1 → N. Loading an old version must either migrate it or fail with a
clear message. It never guesses silently.
