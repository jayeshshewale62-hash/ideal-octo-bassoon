# story.json reference

`story.json` is the whole video. The engine turns it into frames, timed to the voiceover. You never write drawing code for a normal video: you pick shot kinds and fill in their fields.

```json
{
  "title": "The Man Who Sold the Eiffel Tower",
  "mood": "mystery",
  "cast": { "victor": {"skin": "tan", "outfit": "suit", "color": "#3B4660", "hair": "slick", "moustache": true, "hat": "fedora"} },
  "shots": [ {"kind": "skyline", "s": [0, 1], "time": "night", "tag": "PARIS · 1925"}, ... ]
}
```

- `grade` (optional) is the default colour mood for the whole video (see **Colour moods**).
- `title` names the output file. `mood` picks the music: `mystery` (sneaky, swing, money and crime stories), `upbeat` (pop, self-improvement and business wins), `dramatic` (slow and heavy, rise and fall, disasters), `calm` (soft, life lessons and psychology), `tense` (pulsing, scams, survival, countdowns).
- `s` is the sentence range a shot covers, using the numbers printed by `python3 -m engine sentences <P>`: `[4]` is one sentence, `[4, 6]` covers 4, 5 and 6. Shots must cover every sentence once, in order. The shot starts just before its first sentence and ends just before the next shot's.
- A shot **without** `s` is silent. It inserts a pause of `hold` seconds (default 1.6) into the timeline. Use this only for chapter cards (`title`), at most one every 2-3 minutes. The voice is shifted, never cut.

## Cues: `at`

Anything that happens mid-shot has an `at`:
- a **word or short phrase** from the shot's own sentences: `"at": "fortune"` fires when that word is spoken (exact match first, then a prefix match).
- a **fraction** of the shot: `"at": 0.5`.
- **seconds** after the shot start: `"at": "+1.2"`.

Use words wherever you can: that is what makes the picture land on the voice. `plan` warns when a word is not found.

## Cast

Every character is an original round-head puppet. Real people are generic puppets plus a name tag (`lower_third`), never a likeness.

| key | values |
|---|---|
| `skin` | `light`, `fair`, `tan`, `olive`, `brown`, `dark` or a hex colour |
| `outfit` | `suit`, `hoodie`, `tshirt`, `sweater`, `dress` |
| `color` | main clothing colour (hex) |
| `shirt`, `tie` | suit shirt and tie colours; `"tie": "none"` for an open collar; `bowtie: true` |
| `hair` | `short`, `slick`, `bun`, `long`, `curly`, `bald`, `none` |
| `hair_col` | hex |
| `glasses`, `moustache`, `beard` | true/false |
| `hat` | `fedora`, `cap` (with `hat_col`) |
| `build` | shape language of the torso: `round` (friendly, approachable; default), `square` (stubborn, reliable, heavy), `triangle` (broad-shouldered: sharp, high-energy or villainous) |
| `accent` | the one bright accent colour: a scarf on casual outfits; on a suit it becomes the tie and pocket square |

Give every main character a distinct silhouette and colour (hair shape, hat and `build`, plus outfit colour), so they read at a glance in wide shots. 2-4 recurring characters is the sweet spot. Keep each character to 3-4 colours besides skin: one dominant base (`color`), one secondary (hair or shirt), and one bright `accent` that pulls the eye to the face. Avoid patterns: the style is clean shapes and one ink line.

Run `python3 -m engine cast <P>` before writing shots. It draws `work/cast_sheet.jpg` (colour, the solid-black silhouette test in an idle and an action pose, and an 8-expression sheet) and warns when two silhouettes overlap more than 90 %, when two characters wear near-identical colours, when a character uses more than 4 colours or has no accent, and when every character shares one build. Kids use `"s": 0.75-0.85` in `chars`.

## Characters inside a shot (`chars`, `who`)

```json
{"id": "victor", "x": 1000, "s": 1.0, "face": -0.7, "emotion": "smug", "pose": "present",
 "talk": true, "enter": "left", "beats": [{"at": "sold", "pose": "celebrate", "emotion": "excited"}]}
```
- `x` is the feet position (0-1920), `s` the scale (1 = wide shot), `face` runs from -1 (looking left) to 1 (looking right).
- **emotion**: `neutral calm happy smile smug shocked nervous sad angry thinking excited tired confident worried embarrassed greedy`. Sweat drops and sparkles come with the emotion.
- **pose**: `idle present present_left explain think pockets celebrate shrug point hips hold tiphat wave arms_crossed facepalm stressed push`.
- **beats** change pose, emotion or face on a cue, with a snap-and-overshoot plus squash and a two-frame smear (motion arcs from the old hand position to the new one). Think in **key poses**: 2-3 strong, readable poses per shot beat smooth motion. Beats can also sit at shot level with `"who"`. Add `"hit": true` to a beat for an impact thud on the camera (a slam on the desk, a landing, a punchline).
- **talk**: `true` makes the mouth follow the voiceover during the shot's sentences; a list of sentence numbers limits it to those. Use it for dialogue lines and for a character "telling" the story to camera. Narration over a character usually looks better without it.
- `enter` / `exit`: `left` or `right` walks the character in or out. `walk: [x0, x1]` walks across the whole shot.
- Characters always idle-bob, blink and squash on cuts. You don't need to animate that.

## Shared fields (any shot)

| field | what it does |
|---|---|
| `labels` | `[{"text": "A FORTUNE", "at": "fortune", "color": "lime", "x": 1420, "y": 330, "size": 120, "font": "marker"}]`: hand-lettered pop-in words. Colours: `lime cream red gold sky pink white green orange` or hex. Positions default to the empty side of frame. Up to 3 per shot, 1-4 words each. |
| `stamp` | `{"text": "SOLD", "at": "sold", "x": .., "y": .., "color": "red", "size": 130}`: rubber stamp slam with camera shake and a thud. At most one per shot. |
| `tag` | `"PARIS · 1925"`: location/time tag, lower left, on the first shot in a new place or era. |
| `lower_third` | `{"name": "VICTOR LUSTIG", "sub": "CON MAN", "at": "lustig"}`: name card, the first time a person appears. |
| `props` | `[{"icon": "moneybag", "x": 1500, "y": 760, "s": 0.6, "at": "cash"}]`: world props that pop in (icons below). |
| `bubble` | `{"who": "sam", "text": "What if...?", "icon": "bulb", "at": "idea", "thought": true}`: a thought or speech bubble. |
| `time` | `night` (default, moody), `dusk`, `day`. |
| `size` | shot size, framed on the shot's subject (`who`, or the first character) with the eyes on the upper third and the subject on a side third: `ews` `ws` (default for world shots) `ms` (waist up) `mcu` (chest up) `cu` (head and shoulders) `ecu` (the eyes). See **Camera**. |
| `angle` | `eye` (default: neutral, conversational), `low` (looking up: imposing, heroic, overwhelming), `high` (looking down: small, isolated, out of their depth; adds vignette), `dutch` (tilted horizon: panic, confusion, a sudden realisation; sparingly). |
| `cam` | camera preset or keyframes; see **Camera**. `{"preset": "push", "at": "word"}` or `{"zoom": [1.0, 1.12], "focus": [[960, 545], [1100, 500]]}`. |
| `moves` | timed camera events: `[{"type": "punch", "at": "word"}, {"type": "thud", "at": "slam"}]`; see **Camera**. |
| `cut` | `"j"` or `"l"` (or `{"type": "j", "by": 1.4}`) on the shot you cut **into**; see **J-cuts and L-cuts**. |
| `grade`, `act_grade` | colour mood; see **Colour moods**. |
| `fg` | out-of-focus foreground layer for 2.5D depth: `plants`, `lamp`, `frame` (door/window edges: "watching from the next room"), `desk`, `heads` (an audience), `posts` (on glides). `fg_depth` (default 1.5) sets how much faster it moves than the characters. |
| `particles` | ambient motion that keeps a held frame alive: `dust` (default on night/dusk world shots), `snow`, `rain`, `embers`, `sparkle`, `bokeh`, or `"none"`. `particle_density` scales the count. |
| `ambience` | room tone under the shot: `room`, `street`, `night`, `rain`, `crowd`, `wind`, `clock`, `city`, `none`. Defaults come from the set (office/home = room, street = street, skyline = city, crowd = crowd); graphics shots keep the previous place's tone; silent chapter cards cut it. Each place's tone starts 1 s **before** its cut (J) and lingers 0.6 s after (L). |
| `whip` | `true`/`false`: force or stop a whip-pan out of this shot. By default whips happen only on a change of place between world shots. |
| `sfx` | `[{"name": "ding", "at": "idea"}]`: extra sounds: `pop thud whoosh tick shutter scribble boom ding paper step sting`. |
| `polaroid` | `{"at": "twice", "who": "victor", "caption": "SOLD IT... TWICE"}`: the ending. Camera flash, frame freezes into a tilted polaroid, red ring around the character, handwritten payoff. Put it on the last shot, cued 1-2 s before the end. |

## Camera

Every shot moves. With no `cam`, it eases in slowly (a 5-10 % push). Presets map camera behaviour to narrative beats:

| preset | what it does | use it for |
|---|---|---|
| `creep` | Ken Burns: 100 → 108 % (`to`), linear, no easing | exposition, history, calm narration over a held picture |
| `push` | dramatic push-in to ~135 % (`to`) over 1.5-2.5 s (`dur`, default 2), eased in and out, starting on the cue `at`, settling on the subject | the build-up to a realisation, a twist, a critical sentence |
| `punch` | snap zoom to 125 % (`to`) in 3 frames on `at`, held (with a pop) | punchlines, sudden shock, one absurd word |
| `reveal` | starts tight on the subject (`from`, default 1.5) and pulls out with a strong ease-out over 3.5 s (`dur`) | start on a misleading detail, pull back to the crowd, the danger, the chaos |
| `glide` | horizontal parallax travel (`dir` left/right, `dist` px); adds a foreground layer automatically (`plants` indoors, `posts` on the street) | new locations, journeys, moving across a diagram |
| `tilt_up` / `tilt_down` | vertical sweep over 3-5 s (`dur`), zoomed in (`to`, default 1.22) | up: scale, power, authority; down: hidden consequences beneath the surface |
| `hold` | almost still (100 → 102.5 %) | a deliberate beat of stillness, still not a frozen frame |

`cam.float` (`true`, or the drift in px) adds the handheld "breathing" float: a smooth 2-3 px drift that takes the sterile, locked-off feel away. It is on by default for close-ups and for wide shots with dialogue or two or more characters, and never runs during a glide. `"float": false` turns it off.

`moves` are timed camera events inside a shot, each on its own cue:

| move | fields | what it does |
|---|---|---|
| `punch` | `to` (1.22), `hold` (s, default: rest of the shot) | snap zoom in 3 frames, optional release |
| `push` / `pull` | `to`, `dur`, `who` (push toward a character) | eased zoom in or out from that moment |
| `thud` | `px` (22) | impact: a sharp downward jolt with a decaying bounce over ~10 frames, plus a thud. Footsteps, doors, objects dropping, text slapping down |
| `rumble` | `dur` (1.2), `px` (9) | high-frequency, low-amplitude jitter with a low rumble: explosions, machinery, mounting dread |
| `dutch` | `deg` (9) | tilt the horizon as tension peaks |
| `snap` | | snap the horizon straight again on the realisation |

`size` and `angle` set the framing the presets work from. `"angle": "dutch"` tilts the whole shot (`cam.deg`, default 9°); add `"cam": {"snap_at": "word"}` or a `snap` move to straighten it on the realisation. Rules the engine enforces or checks:
- **Overscan.** Sets are drawn 22 % wider and 24 % taller than the frame, and the camera is clamped inside that bleed, so zooms, pans and shakes never show an edge. Zooms below 1.0 are clamped.
- **One dominant motion at a time.** The float never stacks on a glide; don't put a rumble on a whip.
- **Easing matches tone.** `push`, `reveal` and `tilt` are eased (cinematic, deliberate); `creep` is linear (documentary); `punch` and `thud` are abrupt (comic or urgent).
- **Speed.** `dutch` and `cam.rot` rotate the full frame, which renders about 3x slower: keep them for the few shots that need them.

## 2.5D depth

World shots are layered: the set behind the characters moves at 50-85 % of the camera's speed (the floor stays locked under the feet), characters and props move at 100 %, and an optional `fg` silhouette layer moves at 150 %, blurred like a lens out of focus. On a `push` or `glide` this gives flat art real depth without frame-by-frame animation. `particles` drift on their own layer at 120 %.

## Colour moods

One palette per emotional beat, so the viewer feels a shift in tone before they understand it. Grades: `neutral`, `cool` (desaturated and blue: bleak, serious, the problem), `tense` (desaturated green-teal and contrasty: suspense, the investigation), `panic` (red, hard contrast: danger, alarm), `warm` (saturated and golden: breakthroughs, payoffs, humour), `nostalgic` (faded sepia: flashbacks, history).
- `"act_grade": "cool"` on a shot sets the grade for that shot **and every shot after it** until the next `act_grade`. Put it on the first shot of each act.
- `"grade": "panic"` overrides one shot only.
- `"grade": {"from": "cool", "to": "warm", "at": "solved", "dur": 2}` shifts the palette on a cue: the climax moment.
- A typical arc: hook `tense` → setup `neutral` or `nostalgic` → investigation `cool`/`tense` → payoff `from cool to warm` → aftermath `warm`.

## J-cuts and L-cuts

The voice never moves; the cut does. Put `"cut"` on the shot you cut **into**:
- `"cut": "j"`: the new sentence starts over the old picture and the cut lands 1 s later (`by` to change). It makes edits feel motivated by the sound.
- `"cut": "l"`: the cut lands 0.8 s early, so the end of the previous sentence lingers over the new picture.
Each shot keeps at least 1 s of picture; `plan` reports every J/L-cut and warns if there's no room. The ambience bed adds an audio J-cut at every change of place automatically (the next place's room tone starts 1 s before the cut).

## Shot kinds

### `wide`: a set with full-body characters
`set`: `office` (`era`: `modern`/`old`, `wall`, `calendar: "MAY 1925"`), `home` (living room, `wall`), `street` (`shop: "CAFE"`, `awning`), `board`, `void`.
`wall` colours: `green blue plum teal sand grey cream brick`. 1-3 characters (default positions spread out). `dialogue` is an alias.

### `closeup`: one character, big, over the blurred set
`who`, `side` (`left`/`right`), `set`, `time`, `emotion`, `pose`, `beats`, `talk`, `bubble`, `labels` (they go on the open side). Use it for reactions, a line of dialogue, the "you" moments, and after big claims.

### `walk`: a character walks across a set (default `street`)
`chars` with no `x`; they walk from left to right unless you give `walk: [x0, x1]`. Footsteps come automatically. Use it for transitions in time ("one month later"), journeys and endings.

### `skyline`: establishing city shot
`time`, `tag`. Use it for the first shot in a city or a time jump.

### `crowd`: many small people
`count` (9-30), `emotion`, `highlight` (cast id, ringed at `at`), `set` (`void` default, or `street`). Use it for "millions of people", "most people", "everyone".

### `table`: top-down desk with documents sliding in
`items` (1-3): `{"type": "newspaper", "title": "THE DAILY", "text": "HEADLINE", "ring_at": "word", "at": "word", "stamp": {"text": "FAKE", "at": "word"}}`.
Types: `newspaper`, `letter` (`title`, `text`), `contract`, `receipt` (`rows: [["Rent", "$1,200"], ...]`, `text` = total), `photo` (`text` caption), `cash` (`text`), `phone` (`messages: ["...", "..."]`). `hand`: cast id whose sleeve pushes the first item. This is the best shot for evidence, documents, bank balances and messages.

### `map`: dotted route between places
`places: [{"name": "PARIS", "x": 520, "y": 640}, {"name": "VIENNA"}]` (positions auto-spread if omitted), `vehicle`: `train plane ship car`, `at` starts the route.

### `chart`: chalkboard or whiteboard chart
`board`: `chalk`/`white`. `chart`: `{"type": "bar" | "line", "values": [..], "labels": [..], "title": "..", "unit": "$", "suffix": "%", "highlight": 1, "trend": "down", "show_values": true, "at": "word"}`. `who` adds a presenter pointing at it. Use real numbers or no numbers (`show_values: false`). Never invent data.

### `counter`: a big number counting up
`value: {"from": 0, "to": 244000, "prefix": "$", "suffix": "", "at": "word", "short": false}`, `caption`, `icon` (left), `compare: {"text": "THAT'S 6 YEARS OF RENT", "icon": "house", "at": "word"}`. Every big number in the script gets a counter or a label, ideally with an everyday comparison.

### `icon`: 1-3 big icons popping in on paper
`icons: [{"name": "bulb", "label": "THE IDEA", "at": "idea"}]`, optional small `chars` (one character at the side). Icons: `bulb brain clock moneybag coins house trophy heart lock hourglass warning laptop gift book phone chart_up chart_down calendar (top, text) target car money marshmallow shopping (text)`. Icons that take text (`calendar`, `laptop`, `book`, `shopping`) take `text` and `top`.

### `list`: numbered point for listicles
`number`, `text` (2-6 words), `who`, `emotion`, `badge` colour. One per list item, then show the item with other kinds.

### `versus`: split screen, A vs B
`left` / `right`: `{"who": "rex", "title": "SPENDS IT ALL", "emotion": "happy", "pose": "..", "at": "spends"}`, `colors: ["#BFD9F2", "#F6C7B6"]`. This shot is the workhorse for psychology and self-improvement comparisons.

### `metaphor`: an abstract visual metaphor
Break up a monologue or explain a mechanism with one picture. `type`:
- `dominoes`: `count` (7), `tags` (a label above each domino), `highlight` (index in red), `at` (the first one tips), `gap` (0.14 s between falls): chain reactions, "one thing led to another".
- `scale`: `left`/`right` `{"icon": "moneybag", "text": "FAMILY MONEY", "at": "family"}`, `heavy` (`left`/`right`), `at` (it tips): trade-offs, what outweighs what.
- `hourglass`: `label`, `flip_at` (optional cue to flip it): deadlines, time running out.
- `iceberg`: `top`, `top_at`, `bottom`, `bottom_at`; tilts down from the tip to the hidden mass by default: "what you see vs what's really going on".

### `panels`: comic-strip split (2-3 panels)
`panels: [{"who": "rex", "emotion": "happy", "pose": "celebrate", "caption": "EXPECTATION", "at": "thought", "color": "#BFD9F2", "icon": "trophy", "text": "EASY!", "beats": [...]}, ...]`. Each panel slides up on its cue. Use it for expectation vs reality, before/during/after, or three quick examples in one sentence. It is a pattern interrupt: a new picture every ~3.5 s.

### `title`: black card with typed handwriting
Spoken (`s` given): the words type in with the voice, which suits punchlines like "Here's the strange part." Silent (no `s`): a chapter card, with `text` plus `sub` (for example "CHAPTER TWO"). The music cuts out under it with a low boom.

## Pacing rules that make long videos watchable

`plan` checks most of these and prints a warning with the time code.

- **Something new every 4-6 s.** Never hold a picture while the voice runs on: a cut, a beat, a label, a prop or a camera move. `plan` flags any hold longer than 6.5 s and any shot over 15 s with fewer than two changes.
- **The hook (first 45 s):** a new picture or beat every 3-4 s, and the strongest visual on the first word.
- **Shot length:** 3-8 s. 3 min is about 30-40 shots, 5 min 50-65, 10 min 100-130, 15 min 150-190. If a sentence runs longer than about 9 s, give it two beats or labels.
- **Never more than two of the same kind in a row.** Rotate world shots (wide, closeup, walk) with graphics (icon, counter, chart, table, versus, list, metaphor, panels).
- **Establish the geography first.** Open each new place on a wide (or skyline/walk), then cut closer as the stakes rise.
- **Vary shot sizes.** Cutting `ms` → `mcu` on the same character reads as a jump cut. Jump two sizes (wide → close-up on the eyes) or cut away to a graphic.
- **Rule of thirds.** A lone character with labels or props stands on the left third by default, and labels fill the open two-thirds.
- **Break up monologues.** If three or more sentences sit on one character, cut to a `metaphor`, `panels`, `map` or a quick gag.
- **Every number on screen.** Use a counter, chart or label for each figure.
- **A reaction closeup after every big claim or twist.**
- **Re-hook moments** (spoken titles, stamps, versus, panels, metaphors, push-ins) every 60-90 s.
- **Colour:** an `act_grade` per act so the tone shift is felt.
- **Chapters:** a silent `title` card every 2-3 minutes in 10-15 min videos (3-6 in total), 1-2 in 5 min videos, 0-1 in 3 min videos.
- **Places:** `tag` the first shot in each new place or era. Give a `lower_third` the first time each person appears.
- **End** on a `polaroid` shot whose caption is the payoff line.
