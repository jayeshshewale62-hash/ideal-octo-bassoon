# ADR 0009: Face package, control model and lip-sync timing

**Status:** Accepted (Milestone 4)

## Decisions
- **Package.** Module 5 lives in its own package, `studio.face`. Earlier docs placed it
  in `studio.rig`. Faces depend on rigs and characters, but not the other way round, which
  keeps `studio.rig` focused on bones and kinematics.
- **Control model.** A facial rig is a set of components, each with named scalar controls
  (`min`/`max`/`default`). Expressions, visemes and lip-sync all produce values for
  `"<component>.<control>"` keys. This makes performance editable data that is clamped and
  deterministic, independent of artwork. Categorical mouth drawings are `shapes`.
- **Generic vs bound expressions.** Built-in presets are generic: missing components are
  skipped with warnings, so a `minimal` face still works. Custom expressions are bound to
  one rig and validated strictly.
- **Data, not code.** Built-in expressions, the viseme set and phoneme maps are packaged
  YAML files with schemas. Any of them can be replaced with a file, so language mappings
  can be swapped without code changes.
- **Timing.** Half-open intervals; boundaries belong to the later event; implicit rest
  around and between events; a capped eased entry transition; optional single look-ahead
  coarticulation that stays continuous. The mapper never invents timestamps. It only fills
  silence over gaps that already exist between the given events.
- **Speech + expression.** Speech overrides mouth and jaw controls; mouth corners are
  added to the expression's corners.
- **Alignment.** The existing `asr` provider interface gains optional phoneme timestamps
  and a `phoneme_timestamps` capability. `none` stays the default. `mock` returns words
  only and never pretends to provide phonemes. External or hand-made alignments use the
  versioned `AlignmentDocument` schema.
- **Previews** are labelled schematic SVG. Behaviour between frames is proven by numeric
  tests, not by images.
- **Originality.** All Milestone 4 code is original. Legacy Branch A is not used (ADR 0005).
