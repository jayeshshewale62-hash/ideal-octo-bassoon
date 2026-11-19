# Production playbook: the rules, and the engine field for each

Read this before writing `script.txt` and `story.json`. Each rule comes with how to apply it here and whether `plan`, `script` or `cast` checks it.

## 1. Animation and visual pacing

| rule | how to do it in story.json | checked by |
|---|---|---|
| The screen changes every 4-6 s; never a static frame under the voice | One shot per 3-8 s, plus `beats`, `labels`, `props`, `stamp` or `moves` cued to words inside longer shots. Characters always blink, bob and breathe; `particles` (dust by default at night) and the `cam.float` drift keep held frames alive. | `plan`: holds > 6.5 s, shots > 15 s with fewer than 2 changes |
| 2.5D layering (parallax) | World shots already split background (slower), characters (1×) and an optional `fg` silhouette layer (faster, blurred). Use `"cam": {"preset": "glide"}` or `"push"` to show it off. | none |
| Key poses over smooth motion | 2-3 `beats` per shot, each a strong pose + emotion. Pose changes snap with overshoot and a 2-frame smear. Add `"hit": true` on a beat that should land (slam, punchline). | none |
| Break up monologues with visual metaphors | After 2-3 sentences on a talking character, cut to `metaphor` (dominoes, scale, hourglass, iceberg), `panels`, `map`, `chart` or a gag `closeup`. | `board` flags 4+ sentences on one picture |
| A colour-mood system | `act_grade` per act (`cool`, `tense`, `panic`, `warm`, `nostalgic`, `neutral`), `grade` for one shot, `{"from": "cool", "to": "warm", "at": "word"}` for the climax shift. | `plan` notes a single-grade video over 4 min |

## 2. Camera position and framing

| rule | how | checked by |
|---|---|---|
| Establish the geography first | The first shot in a new place is `wide` (`ws`/`ews`), `skyline` or `walk`; then cut closer with `size` or a `closeup`. | `plan` (direct world-to-world cuts) |
| Rule of thirds | A lone character with labels/props stands on the left third by default (`x` 640); labels default to the open side. `size` framing puts the subject on a third and the eyes on the upper third. | none |
| Angles carry power and emotion | `"angle": "eye"` (intros, direct commentary), `"low"` (imposing, heroic, a threat), `"high"` (vulnerable, isolated), `"dutch"` (panic, a sudden realisation; sparingly, straighten it with `snap`). | `plan`: more than about one dutch shot per 3-4 min |
| J-cuts and L-cuts | `"cut": "j"` on the shot you cut into (the next line starts over the old picture), `"cut": "l"` (the old line lingers over the new picture). Room tone always leads a change of place by 1 s. | `plan` lists every J/L-cut |
| Vary shot sizes back to back | Never `ms` → `mcu` on the same character. Go `ws` → `cu`/`ecu`, or cut away to a graphic in between. | `plan`: jump cuts |

### Camera preset library

| beat in the story | camera |
|---|---|
| exposition, history, calm narration | `"cam": {"preset": "creep"}` (100 → 108 %, linear) |
| building to a realisation or twist | `"cam": {"preset": "push", "at": "<the key word>"}` (to 135 %, eased, 2 s) |
| punchline, shock, one absurd word | `"cam": {"preset": "punch", "at": "<word>"}` or a `punch` move |
| start on a detail, reveal the scale | `"cam": {"preset": "reveal"}` (150 → 100 %, strong ease-out) |
| new location, travel, across a diagram | `"cam": {"preset": "glide", "dir": "right"}` (with automatic foreground) |
| power, scale, authority | `"cam": {"preset": "tilt_up"}`, often with `"angle": "low"` |
| what's hidden underneath | `"cam": {"preset": "tilt_down"}` (the `iceberg` metaphor does this by default) |
| two people arguing, cause and effect | consecutive world shots in different places whip-pan automatically; force with `"whip": true` |
| dialogue, standoffs | handheld float (default on close-ups and dialogue) |
| footsteps, doors, objects dropping, text slapping down | `{"type": "thud", "at": "<word>"}` move, or a `stamp` |
| explosion, machinery, mounting dread | `{"type": "rumble", "at": "<word>", "dur": 1.5}` |

Never stack competing movements: one dominant motion reads per moment (the engine drops the float during a glide). Every set has 22-24 % overscan bleed and the camera is clamped inside it.

## 3. Character design

| rule | how | checked by |
|---|---|---|
| Pass the silhouette test | Distinct hair (`bun`, `curly`, `slick`, `bald`...), `hat`, `build` and outfit (`dress`, `suit`, `hoodie`). | `cast`: two silhouettes > 90 % identical |
| 3-4 colours per character | `color` (base), hair or `shirt` (secondary), one bright `accent` (scarf, or tie on a suit). | `cast`: > 4 colours, no accent, look-alike base colours |
| Design for repeatable drawing | The puppets are built from clean shapes with one ink line; don't ask for patterns, plaid or armour. | none |
| An expression sheet before animating | `cast` renders 8 expressions (neutral, happy, shocked, smug, tired, angry, thinking, worried) with matching poses; all 16 emotions and 17 poses can be swapped per beat. | `cast` |
| Shape language | `"build": "round"` (friendly, harmless), `"square"` (stubborn, reliable, heavy), `"triangle"` (sharp, unpredictable, villainous, high-energy). | `cast`: every character has the same build |

## 4. Scriptwriting for long-form retention

| rule | how | checked by |
|---|---|---|
| The 15-second visual + verbal hook | The first sentence is the boldest claim, paradox or highest-stakes moment, under ~12 words, with no "hey guys / welcome back / in this video". Pair it with the strongest picture on the first word. | `script` (openers, length), `plan` (first beat, 3-4 s interrupts in the first 45 s) |
| Mini-chapters every 2-3 min | `# Chapter title` lines in `script.txt` become silent chapter cards; each chapter is a small story with its own setup and payoff. | `script` (chapters over ~3.6 min), `plan` (over 3.5 min between cards) |
| Open loops before transitions | The last line before each chapter card teases the next problem: "That solved it, but it set off a disaster nobody saw coming." | `script` (a chapter ending with no loop word) |
| Write for the eye | `python3 -m engine board <P>` writes the two-column storyboard (VO / VISUAL / CAMERA / SOUND). Any row with 4+ sentences and no visual action gets rewritten or split. | `board` |
| Cut throat-clearing | Start each scene as late as possible, leave once the point lands. No "thanks for watching / like and subscribe": end by bridging into the next video. | `script` (closers) |
