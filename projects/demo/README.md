# Demo Project

Motion Animation Studio project `demo` (`prj_d5e80bb76e6c4232ba836173b764ca67`), kind **short**.
Created 2026-11-27T17:29:20+00:00 with studio 0.2.0.

This project was created with `studio new`. It contains **no artwork, audio or animation
yet**. The story and storyboard files are placeholders until those modules are built.

## Files

| Path | Purpose |
|---|---|
| `project.yaml` | Project identity and metadata (do not change `id`) |
| `settings.yaml` | Render profile `hd1080p24`, preview `preview540p12`, provider overrides |
| `assets/registry.json` | Asset registry: IDs, versions, content hashes, provenance, licences |
| `assets/` | Registered asset files |
| `assets/audio/` | General audio assets |
| `assets/audio/music/` | Music |
| `assets/audio/sfx/` | Sound effects |
| `assets/audio/voice/` | Dialogue and narration recordings |
| `assets/characters/` | Character parts, model sheets, character.yaml |
| `assets/data/` | Data assets (rig JSON, curves, alignment) |
| `assets/environments/` | Background layers and environment.yaml |
| `assets/fonts/` | Fonts (with licence) |
| `assets/other/` | Anything else |
| `assets/props/` | Props |
| `assets/references/` | Private reference material (never third-party video) |
| `assets/textures/` | Paper, brush and fill textures |
| `scenes/` | Scene files (later milestones) |
| `story/` | Story and script |
| `storyboard/` | Storyboard and animatic data |
| `renders/`, `cache/` | Created on demand; never committed |

## Commands

```bash
studio project info projects/demo
studio project validate projects/demo
studio asset register projects/demo path/to/file.svg --category character --name "Hero head"
studio asset list projects/demo
studio asset validate projects/demo
```

Binary files (PNG, WAV, MP3 ...) are git-ignored by default. Keep them in object storage,
or record explicit approval before committing one (see docs/DECISIONS/0006).
