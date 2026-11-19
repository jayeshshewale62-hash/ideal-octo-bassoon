# 10-minute template: five acts, beat by beat

About 1,400-1,500 spoken words (140-150 wpm). Scale it for other lengths: a 15-minute video stretches Act 3 into two investigations, a 5-minute video merges Acts 2 and 3. Each row gives the job of the beat, the words, and a story.json recipe for it. Write `script.txt` with the act and chapter breaks as `# ` lines (silent cards), then fill the recipes with real sentence numbers and cue words.

Before you start, fill in: **working title**, **target runtime**, **palette arc** (for example `tense` → `nostalgic` → `cool` → `cool→warm` → `warm`), **voice tone** (conversational, curious, slightly deadpan).

## Act 1: the hook (0:00-0:45, ~100 words)
Start in the middle of the tension. A new picture every 3-4 s.

| beat | VO | story.json |
|---|---|---|
| 0:00-0:08 cold open | The boldest claim, paradox or highest-stakes moment. No intro. | `closeup`, `"size": "ecu"` on the eyes (`emotion: shocked`), then `"whip": true` into a `wide`/`table` of the mystery object. 3-word `labels` on the beat, `"moves": [{"type": "punch", "at": "<word>"}]`. `"act_grade": "tense"`. |
| 0:08-0:25 the stakes | Why this matters now: the question the viewer needs answered. | `wide` with the character on the left third (`emotion: worried`, `pose: stressed`), a `chart`/`icon` or `labels` on the right two-thirds, `"cam": {"preset": "creep", "to": 1.1}`. |
| 0:25-0:45 the promise | The roadmap without sounding robotic, plus the first open loop. | `wide` or `closeup` at eye level, `pose: point` toward a `map` that follows with `"cut": "j"`. |

## Act 2: context and the inciting setup (0:45-3:00, ~315 words)
Ground the rules of the world, then the first complication.

| beat | VO | story.json |
|---|---|---|
| 0:45-1:30 the baseline | Foundational facts or backstory, sentences under 18 words. | First shot in the new place is `skyline`/`wide` with `tag`; then `map`, `table` or `chart` with labels under 4 words cued to the key nouns. `"act_grade": "nostalgic"` for history, `neutral` otherwise. |
| 1:30-2:15 the visual metaphor | Translate the data or history into one simple picture. | `metaphor` (`dominoes`, `scale`, `hourglass`, `iceberg`), `"grade": "cool"` or an accent shift, `"cam": {"preset": "tilt_down"}` following the action. |
| 2:15-3:00 payoff + open loop 1 | Resolve the setup, then: "That seemed logical, until one tiny detail broke everything." | `wide` `"angle": "low"` on the obstacle/antagonist with the hero small at the bottom; `stamp` on the hard beat. Then the silent chapter card. |

## Act 3: escalation and the investigation (3:00-6:30, ~490 words)
Beat the mid-video dip: change pace, size and format every 45-60 s.

| beat | VO | story.json |
|---|---|---|
| 3:00-4:15 complication 1 | The first twist or mechanism, in concrete specifics. | `closeup` `"size": "mcu"` with 3 key-pose `beats` (`thinking` → `shocked` → `worried`), cut to a `table` insert (letter, receipt, phone) with `ring_at`; `"moves": [{"type": "rumble", "at": "<reveal>", "dur": .8}]`. `"act_grade": "cool"`. |
| 4:15-5:30 the pattern interrupt | What people assumed vs what actually happened. | `panels` (EXPECTATION / REALITY, or three quick panels) and `versus`; a new picture every ~3.5 s. Music tempo can rise with `mood: tense`. |
| 5:30-6:30 the turning point | The biggest midpoint revelation; tease the consequence. | `closeup` `"angle": "dutch"` with `"cam": {"snap_at": "<realisation>"}`, a beat with `"hit": true` (slam on the desk), `stamp`; the next shot `"cut": "l"`. |

## Act 4: climax and resolution (6:30-9:00, ~350 words)
Deliver the payoff the title and thumbnail promised.

| beat | VO | story.json |
|---|---|---|
| 6:30-7:45 the payoff sequence | The answer or climactic event, clear cause and effect. | `wide` with `"cam": {"preset": "push", "at": "<key word>"}` (wide → medium), `"grade": {"from": "cool", "to": "warm", "at": "<turning word>", "dur": 2}`, `fg` for depth, `counter`/`chart` for the proof. `mood` music is at full arrangement here. |
| 7:45-9:00 the aftermath | The fallout, the proof it worked. | `wide` `"angle": "high"`, `"cam": {"preset": "reveal"}` pulling back, character in `tired`/`calm`, clean negative space. `"act_grade": "warm"`. |

## Act 5: the takeaway and the bridge (9:00-10:00, ~140 words)

| beat | VO | story.json |
|---|---|---|
| 9:00-9:40 the core insight | One memorable takeaway that distils the journey. | `closeup` at eye level, `"size": "mcu"`, holding the callback prop from 0:00 (`props` or `bubble` with the same icon), mirroring the cold open. |
| 9:40-10:00 the end-screen bridge | Bridge straight to the next video: "Of course, solving this only created an even stranger problem." No "thanks for watching". | `wide` with the character on the left third, `pose: point` at the right two-thirds (keep it empty for the end-screen card), `polaroid` with the payoff caption 1-2 s before the end. |

## Before rendering
- `python3 -m engine script <P>`: hook, outro, long sentences, open loops, chapter lengths.
- `python3 -m engine sentences <P>`: 1,300-1,500 words for 10:00.
- `python3 -m engine plan <P>`: no static holds over 6.5 s, no jump cuts, a re-hook every 60-90 s.
- `python3 -m engine board <P>`: read the VO | VISUAL table once; every row with 4+ sentences gets split or more beats.
