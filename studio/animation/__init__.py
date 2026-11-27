"""Module 6 - Animation Engine.

Status: PLANNED for Milestone 5. This package is an explicit placeholder that marks
the module boundary. It contains no implementation yet. See docs/MODULES.md.

Evaluates keyed curves into per-frame rig poses: easing and splines, holds on
ones and twos, walk/run/idle cycles, jumps, sit/stand, turns, reaches, lifting and
carrying, secondary motion, overlapping action, follow-through, squash and stretch,
smear frames and controlled line boil. Interaction constraints (contact points, holds,
prop handoffs, eye-lines between characters) are solved here.

Time is in seconds; frames are sampled at render time (see studio.core.timecode).
"""
