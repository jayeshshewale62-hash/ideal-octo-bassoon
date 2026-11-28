"""Module 14 - Rendering Engine.

Status: PLANNED for Milestones 7 and 10. This package is an explicit placeholder that marks
the module boundary. It contains no implementation yet. See docs/MODULES.md.

Schedules frames per shot across worker processes (and later remote workers),
caches by content hash, encodes with FFmpeg per the render profiles in
config/render_profiles.yaml, and concatenates shots. Backends: skia CPU (core),
optional Blender Grease Pencil and browser renderers. No GPU is required for the core
path.
"""
