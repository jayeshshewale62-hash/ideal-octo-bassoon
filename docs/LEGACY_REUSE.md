# Legacy Branch Reuse Record

The repository has two earlier, unmerged branches from previous Claude Code sessions.
Milestone 2 inspected them **component by component**. They are sources of reusable parts,
not the architecture of this project.

**Both branches are preserved unchanged.** They were fetched read-only. Nothing was merged,
rebased, deleted or force-pushed.

| Branch | Head commit | Commits | Content |
|---|---|---|---|
| `ccr-f3c28d1b-6ialqh` ("Branch A") | `c312cfd` | 4 (2026-11-19) | `reachmora-2d-longform/`: Python 2D long-form engine (skia-python + FFmpeg) |
| `ccr-5cb67ed4-c3se5u` ("Branch B") | `431161b` | 5 (2026-11-20) | `cartoon-audio-short/`: three.js/WebGL shorts engine with Python tools |

## How the investigation was done

1. Fetched both branches (`git fetch origin <branch>`) and listed every file with sizes.
2. Read the history (`git log`) to learn who wrote each file. This matters for licensing:
   - files from a commit titled "as uploaded" came from a third-party skill;
   - files added in later commits were written in Claude Code sessions for the repository owner.
3. Read the licence and credit files.
4. Extracted each branch with `git archive` into a scratch directory **outside the
   repository**, and ran the candidate components:
   - **Branch A `engine/timing.py`** (`sentences`, `norm`, `syllables`): ran on sample text
     with Python 3.13. Works. Abbreviations ("Dr.", "a.m.") are kept inside sentences.
     The syllable heuristic undercounts some words ("animation" → 4).
   - **Branch A `engine/timeline.py`**: import fails without `skia` (it imports `kit.py`,
     which needs skia at import time). Not runnable in isolation.
   - **Branch B `engine/captions.py`**: ran on a 7-word `words.json` fixture. It produced 4
     valid ASS cards, with frame snapping and hold logic as documented.
   - **Branch B `engine/pacing.py`**: ran on a short script. It correctly warned on word count
     and exited with code 1.
   - **Branch B `engine/audio/finish_audio.py`**: import fails without `scipy` (via `dsp.py`).
     It is also tied to a fixed -14 LUFS / LRA 2.4–2.9 shorts spec.
5. **Neither branch contains any automated tests.** All existing code is written as
   command-line scripts. Many files parse `argparse` or run work at import time, so they
   cannot be imported as libraries without being rewritten.

## Licensing findings

| Material | Licence status | Consequence |
|---|---|---|
| Branch A `reachmora-2d-longform/` (all engine code) | **No licence file.** `CREDITS.md` says "Made by ReachMora … Keep this credit when sharing the skill". Part of `kit.py` is "adapted from the 'Claude 2D Animation Long Form' skill by aivxer". | No code copied. Copying needs explicit permission or a licence from the authors. **The repository owner needs to clarify this** (see "Open question" below). |
| Branch A fonts (Caveat Brush, Kalam: OFL-1.1; Permanent Marker: Apache-2.0) | Open licences, licence files included | Could be reused later in `assets/fonts/` with their licence files. Not needed in Milestone 2. |
| Branch B files from commit `ed48256` "Import cartoon-audio-short skill (v1, as uploaded)" (`toonbase.js`, `cast.js`, audio synth modules, `timing.py`, …) | MIT, "Copyright (c) 2026 Mr omi" (`THIRD_PARTY_LICENSE_claude-animated-shorts.txt`) | Reusable with the MIT notice kept. None needed in Milestone 2. |
| Branch B files first added in later commits (`captions.py`, `pacing.py`, `refscan.py`, `camscan.py`, `audit.mjs`, `mix.py`/`finish_audio.py` v2 changes) | Written in Claude Code sessions for the repository owner (commits `02e0c3e`, `991eb11`, `3b80e33`, `431161b`) | Reusable by the owner. |

## Components reused in Milestone 2

| New file | Origin | What was taken | Changes made | Tests |
|---|---|---|---|---|
| `studio/core/timecode.py` | Branch B, `cartoon-audio-short/kit/engine/captions.py` @ `02e0c3e` (session-authored) | `snap` (frame snapping) and `ts` (ASS `H:MM:SS.cc` timestamp) | Frame rate is a parameter instead of fixed 30 fps; input validation added; SMPTE timecode, frame/seconds conversions and duration helpers added; typed | `tests/unit/test_paths_hashing_timecode.py`. It includes **equivalence tests against the legacy formulas** (`test_snap_matches_legacy_behaviour`, `test_ass_time_matches_legacy_formatter`). |

**Why only this:** Milestone 2 is foundation work. Frame and timecode conversion is a
foundation concern, used by render profiles, alignment and captions. Every other candidate
belongs to a module scheduled for a later milestone. Importing it now would mean
implementing future modules early. Those candidates stay where they are, recorded below for
the milestone that needs them.

The `legacy/` folder therefore holds **an index, not copies**: `legacy/README.md` points
to the exact branch, commit and path of every candidate. Nothing was duplicated without a
reason.

## Components deliberately not reused (yet), with reasons

| Component | Branch | Decision | Reason | Revisit in |
|---|---|---|---|---|
| `engine/camera.py` (shot sizes, angles, presets, moves, parallax, overscan clamp) | A | Not copied | No licence. Depends on `kit.py` constants (skia). Camera is module 9, not M2. Its design (shot-size table, depth-based parallax with a locked floor pivot, overscan clamp) is recorded as a reference in docs/MODULES.md. | M6, after licence clarification or a clean-room rewrite |
| `engine/timeline.py` (J/L-cuts, silent holds, voice→output clock, cue lookup) | A | Not copied | No licence. Imports `kit` (skia). Timeline is M6/M7 scope. | M6/M7 |
| `engine/timing.py` (sentence split, word normalisation, syllables, energy-based speech mask, Parakeet alignment) | A | Not copied | No licence. The alignment needs a 460 MB model download (blocked in CI). Alignment becomes the `asr` provider in M4. | M4 |
| `engine/audit.py` (static holds, jump cuts, hook pace, script lint) | A | Not copied | No licence. Depends on the shot model. Storyboard audits are module 8/15 scope. | M6/M8 |
| `engine/kit.py`, `shots.py`, `sets.py`, `props.py`, `fx.py`, `render.py`, `sheets.py` | A | Not reused | The puppet characters are explicitly **not** acceptable for the rig-based character system. The other files implement the old engine end to end. | Not planned |
| `captions.py` (ASS pop-word cards) | B | Only the timecode helpers taken | Hard-coded 1080×1920 vertical layout and 30 fps; module 13 scope | M7 |
| `pacing.py` (word-count and hook lint) | B | Not copied | Tied to the 58–65 s vertical-short format; story lint is module 1/15 scope | M8/M9 |
| `audio/finish_audio.py`, `mix.py`, `dsp.py` (loudness, true peak, LRA leveller) | B | Not copied | Needs scipy. Part of it is MIT third-party code. Audio mastering is module 12 scope. Good candidate: the loudness targets match `render_profiles.yaml`. | M7 |
| `refscan.py`, `camscan.py` (reference video analysis) | B | Not copied | Analysis tools for private reference videos. Useful once the reference files are shared privately. They need numpy, Pillow and FFmpeg. | When references are available |
| `web/*.js` (three.js PBR world, toon cards), `render.mjs`, `audit.mjs` | B | Not reused | 3D/PBR WebGL is not the approved direction | Not planned |
| Fonts | A | Not copied | Not needed yet | M7 (titles) |

## Milestone 3 update: Branch A is third-party and must not be reused

The repository owner confirmed that **"ReachMora 2D Long-Form" (Branch A) is third-party
code we do not own and have no permission to reuse.** Branch A is therefore strictly
reference-only: its code, modules, dependencies and internal architecture are not copied,
adapted, ported, translated or imported. Earlier "revisit" entries for Branch A in the
table above are cancelled. Those capabilities will only ever be implemented from scratch.

Milestone 3 (characters, rigging, FK/IK, turnarounds, consistency, previews) is **entirely
original code**:
- no Branch A or Branch B source was opened while writing it, beyond the Milestone 2
  inspection recorded above;
- no Branch B code was reused in Milestone 3;
- the only legacy-derived code in the repository remains `studio/core/timecode.py` (from
  Branch B's session-authored `captions.py`, Milestone 2).

Milestone 4 (faces, expressions, visemes, phoneme maps, lip-sync, alignment interface) is
also **entirely original code**. No Branch A or Branch B source was used.

Milestone 5 (animation engine, cycles, springs, meshes, evaluator) is **entirely original
code**. No Branch A or Branch B source was used.

## Open question for the repository owner (resolved in Milestone 3)

Branch A's engine has **no licence**, and part of it is adapted from another author's
skill. Before any Branch A code is adapted, please confirm one of:

1. you own or have permission to relicense "ReachMora 2D Long-Form" in this repository; or
2. later milestones should re-implement those ideas from scratch (clean-room), using only
   the documented behaviour.

Until then, Branch A is treated as **reference documentation only**.
