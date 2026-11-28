"""Module 5 - Facial Expression Engine, visemes and lip-sync foundation (Milestone 4).

* ``schemas``     facial rig, controls, expressions, blends, visemes, phoneme maps, phoneme
  and viseme events, lip-sync tracks, alignment results (all versioned);
* ``templates``   ``standard`` / ``minimal`` facial rigs sized from the head part (no art);
* ``expressions`` deterministic evaluation, validation, two-way and weighted blending, and
  the time-based ``ExpressionTransition`` interface for later animation milestones;
* ``geometry``    control values -> face-space geometry per component;
* ``phonemes``    phoneme -> viseme mapping with replaceable language tables;
* ``lipsync``     ``evaluate_lipsync(track, time, visemes)`` with transitions, coarticulation,
  silence and exact-boundary rules;
* ``alignment``   bridge to the ``asr`` provider interface (disabled/mock by default);
* ``manager``     face and custom-expression storage with version history;
* ``validation``  FAC/EXP codes; ``preview``: diagnostic SVG panels and sheets.

Reference data (expressions, visemes, phoneme maps) lives in ``studio/face/data``.
Not implemented here: speech recognition, forced alignment, text-to-speech, timelines,
rendering of facial artwork. Facial artwork is never generated.
"""

from __future__ import annotations
