# Characters: Creation, Parts, Turnarounds and Identity (Milestone 3)

Packages: `studio.characters` (modules 2 and 3) and `studio.rig` (module 4, see
[RIGGING.md](RIGGING.md)). A character is **editable components plus data**: a part
hierarchy bound to a bone rig, with artwork referenced from the asset registry. It is
never a flattened picture.

## What is implemented

| Feature | Status |
|---|---|
| Character definition schema (identity, parts, style, turnaround, rig link, provenance, metadata) | implemented |
| Templates `biped` and `biped-minimal` (parts + rig + IK chains + view entries from proportions) | implemented |
| Reuse another character's structure (`--from`), without copying its artwork references | implemented |
| Multiple characters per project, unique IDs, version history (`history/character.vN.yaml`) | implemented |
| Part hierarchy: parent, attachment points, transform, pivot, visibility, opacity, z-order, bone binding | implemented |
| Transform propagation, inherited visibility and opacity, deterministic draw order, per-view overrides | implemented |
| Turnaround: front, three-quarter front (`three_quarter`), side, three-quarter back, back | implemented |
| Identity and consistency manager (metadata comparison with roles) | implemented (metadata only) |
| Artwork assignment through the Asset Manager (part- or view-level) | implemented |
| Validation with codes (CHR, PRT, TRN; plus RIG and IK) | implemented |
| Diagnostic SVG preview (structure, bones, joints, IK, draw order, view) | implemented |
| Deformation (mesh/warp) | metadata only; evaluation deferred (M5) |
| Image-based consistency (golden renders, palette delta-E on pixels) | **not implemented** (M8) |
| Automatic or AI artwork, turnaround drawing generation | **not implemented** (out of scope) |

## Files

```
projects/<slug>/characters/<character-id>/
    character.yaml              CharacterDefinition (schema_version 1)
    rig.yaml                    RigDefinition (schema_version 1)
    history/character.v1.yaml   earlier versions, written on every change; never overwritten
    history/rig.v1.yaml
    face.yaml, expressions/     facial rig and custom expressions (Milestone 4, see FACE.md)
    animations/                 clips, sets, meshes (Milestone 5, see ANIMATION.md)
```

The `characters/` folder is created on demand, so Milestone 2 projects stay valid without
it. `studio project validate` validates every character it finds (ADR 0008).

## Creating characters

```bash
studio character templates
studio character create projects/demo "Mira Vale" --description "Lighthouse keeper's apprentice"
studio character create projects/demo "Bo" --template biped-minimal --height-heads 4 --height-units 800
studio character create projects/demo "Nell" --from chr_mira-vale      # reuse structure, no artwork
studio character list projects/demo
studio character info projects/demo chr_mira-vale [--json]
studio character validate projects/demo [chr_mira-vale] [--json]
```

IDs are `chr_` plus a slug of the name (or `--id`). Creating an existing ID is refused
(`already exists; nothing was changed`). The biped template builds:

- **21 parts:** head, neck, ear_l/r, hair, upper_torso, chest, waist, pelvis,
  upper_arm/forearm/hand ×2, thigh/lower_leg/foot ×2. Ears and hair are marked `optional`.
  `biped-minimal` omits ears, hair, chest and waist.
- **A 16-bone rig:** root control, spine, neck, head, and arms and legs with joint limits.
- **IK chains** `arm_l`, `arm_r`, `leg_l`, `leg_r`, plus target controls.
- **Five turnaround view entries**, with draw-order overrides for side and back views.

**No artwork is created.** Validation warns (`TRN003`, `PRT018`) until artwork is assigned.

## Parts

```yaml
- id: forearm_l
  kind: forearm            # head, neck, ear, hair, head_accessory, chest, upper_torso, waist,
                           # pelvis, upper_arm, forearm, hand, thigh, lower_leg, foot, accessory, custom
  side: left               # the character's own left
  parent: null             # hierarchy parent (part id)
  parent_attachment: null  # named attachment point on the parent
  bone: forearm_l          # rig binding (takes precedence over parent for the transform)
  transform: {x: 0, y: 0, rotation: 0, scale_x: 1, scale_y: 1}
  pivot: {x: 0, y: 17.28}  # artwork point that sits on the transform origin
  bounds: {x: 0, y: 0, width: 136.8, height: 34.56}
  visible: true
  opacity: 1.0
  z_order: 34              # unique per view (PRT005); lower draws first
  asset: null              # registered asset id (SVG/PNG/WebP)
  attachment_points: []
  deformation: null        # metadata only in M3
  optional: false
```

Transform rules (`studio.characters.parts`):

```
frame   = anchor · TRS(transform)       anchor = bone world matrix | parent frame | parent attachment | identity
artwork = frame · translate(−pivot)
```

Moving a parent moves all of its descendants. Hiding a parent hides its children, and
opacity multiplies down the tree. Draw order is ascending `z_order`, with ties broken by ID.
A view can override `z_order`, `hidden_parts`, `part_transforms` and `part_assets`.

## Artwork (Asset Manager integration)

```bash
studio asset register projects/demo art/mira_head.svg --name "Mira head" --category character --license proprietary
studio character set-part-asset projects/demo chr_mira-vale head ast_…            # all views
studio character set-part-asset projects/demo chr_mira-vale head ast_… --view side # one view
studio character set-view-artwork projects/demo chr_mira-vale side ast_…           # full turnaround drawing
```

- Part artwork must be SVG, PNG or WebP. View drawings may also be JPG, ORA, PSD or KRA.
- The asset must be registered in the project; files are never copied or modified by
  character commands.
- Every change writes a new character version.
- An asset tagged `chr_<other>` is reported if another character uses it (`PRT011`).

## Turnarounds

All views live inside one `character.yaml`, so a view can never create a second identity.

- `required_views` defaults to all five and must include `front`.
- Each view can carry its own artwork, part artwork, visibility, draw order, transforms and
  `identity_overrides`. Overrides are allowed only for **view-specific** or **variation**
  properties; changing a **required** identity property in a view is an error (`TRN005`).

## Identity and consistency

`identity` holds height (design units), proportions in head-heights (with a tolerance),
head shape and width ratio, named palette colours, clothing, hair, distinctive features,
personality and voice. The consistency manager flattens these into properties and
compares them. **It compares metadata, not images.** There is no visual recognition and
no similarity score.

| Default role | Properties |
|---|---|
| required (error) | name, height_units, proportions.height_heads, head.shape, palette.*, clothing, hair, distinctive_features, part_ids, rig |
| view_specific (allowed per view) | head.width_ratio, proportions.shoulder_width_heads |
| optional (warning) | proportions.arm_length_heads, proportions.leg_length_heads, personality, voice |
| variation (allowed) | none by default; set e.g. `policy: {clothing: variation}` for outfit changes |

```bash
studio character compare projects/demo chr_mira-vale --version 1     # earlier version -> current
studio character compare projects/demo chr_mira-vale --with chr_nell # character vs variant
```

`compare` exits with 1 when a required property differs. Numbers are compared with the
character's `proportions.tolerance` (relative), and lists ignore order and case.

## Diagnostic preview

```bash
studio character preview projects/demo chr_mira-vale --view side --ik arm_l 150 400
# -> projects/demo/renders/previews/chr_mira-vale-side-diagnostic.svg (git-ignored)
```

The SVG shows part boxes in draw order (labelled with z-order), pivots, bones, joints and
the solved IK chain with its target. Registered artwork is referenced with `<image>`
pointing at the original file. The preview refuses to overwrite a registered asset, and
it refuses to replace any other existing file outside `renders/` without `--force`. Its
title says **"DIAGNOSTIC: structure only (not artwork, not animation)"**. It is an
inspection aid, not evidence of animation.

Example: [examples/chr_mira-vale/](examples/chr_mira-vale/) (character, rig and side-view
diagnostic, generated with the commands above).

## Validation codes (characters, parts, turnarounds)

| Code | Severity | Meaning |
|---|---|---|
| CHR001 | error | `character.yaml` missing or invalid |
| CHR002 | error | id does not match its folder |
| CHR003 | error | character belongs to another project |
| CHR004 | error | rig referenced but `rig.yaml` missing |
| CHR005 | error | rig id / rig character_id mismatch |
| CHR006 | error | character id used twice in the project |
| CHR007 | warning | history versions inconsistent |
| CHR008 | error | model-sheet asset missing or invalid |
| CHR009 | error | status `approved` without artwork for every view |
| CHR010 | error | status `rigged`/`approved` without a rig |
| CHR011 | warning | `rig.yaml` present but not referenced |
| CHR012 | warning | folder in `characters/` without `character.yaml` |
| PRT001 | error | duplicate part id |
| PRT002 | error | parent part does not exist |
| PRT003 | error | circular part hierarchy |
| PRT004 | error | part bound to an unknown bone (or no rig) |
| PRT005 | error | duplicate z-order within a view |
| PRT006 | error | part asset not registered |
| PRT007 | error | part asset has an unsupported format |
| PRT008 | error | artwork file missing or path unsafe |
| PRT009 | error | unknown parent attachment point |
| PRT010 | warning | parent part's bone is not an ancestor of the part's bone |
| PRT011 | error | asset tagged for another character |
| PRT012 | error | character has no parts |
| PRT013 | warning | asset category is not character/prop/texture |
| PRT014 | error | `parent_attachment` without `parent` |
| PRT015 | error | duplicate attachment point names |
| PRT016 | warning | mesh/warp deformation is metadata only |
| PRT017 | error | part transforms cannot be evaluated |
| PRT018 | warning | parts without artwork |
| TRN001 | error | view defined twice |
| TRN002 | error | required view missing |
| TRN003 | warning | views without artwork |
| TRN004 | error | view references unknown parts |
| TRN005 | error | view changes a required identity property |
| TRN006 | warning | view changes an optional identity property |
| TRN007 | error | unknown identity property in a view override |
| TRN008 | error | view artwork asset missing or invalid |
| TRN009 | error | identity override has the wrong type |
| TRN010 | error | `required_views` has duplicates |
| TRN011 | error | `required_views` does not include `front` |

## Known limitations

- Templates are humanoid only. Front-view limb geometry is a sensible starting point and
  must be edited per character design.
- `side` from the character's own left is assumed. Mirrored views are not generated.
- Deformers, replacement-part swaps and line boil are data fields only. They are evaluated
  in later milestones.
- Consistency checks are metadata-based. Golden-image checks arrive in Milestone 8.
- Diagnostics are SVG only. Raster previews through skia arrive with the renderer.
- One writer per character: a save based on an older version is refused, not merged.
