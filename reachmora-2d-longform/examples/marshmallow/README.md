# Example: "The Marshmallow Test and Your Money" (about 2:27, 33 shots)

A tested project that uses every shot kind except `map`: wide, closeup, walk, skyline, crowd, panels, metaphor (scale), table, chart (bar and line), counter, icon, list, versus, spoken and silent titles, bubble, lower third, tag, stamp and polaroid.

It also shows the production layer:
- **Cast:** three builds (round Mia and Sam, square Doc, triangle Rex) with one accent colour each; `python3 -m engine cast <P>` passes except Doc vs Rex's near-identical idle silhouette, which is left in as a teaching example.
- **Camera:** `push` into the marshmallow (shot 0), a `punch` move on "two" (1), a `dutch` close-up (3), `tilt_down` over the skyline (5), a J-cut into the researchers (8), a `push` move on the counter (19), a `glide` with foreground posts (31), and a hit beat that thuds the camera (7).
- **Colour moods:** `nostalgic` for the 1960s study, `tense` for "here's the strange part", back to `neutral` for the money chapter, `warm` on the counter, and a neutral → warm shift on the polaroid ending.
- **Depth:** dust particles on night shots, a `frame` foreground on shot 23 ("watching from the next room").

To rebuild it, copy this folder to a project folder, add a `voice.wav` reading `script.txt`, and run from the skill folder:

```bash
python3 -m engine align <P>
python3 -m engine cast <P>
python3 -m engine plan <P>
python3 -m engine board <P>
python3 -m engine stills <P>
python3 -m engine all <P>
```

Facts note: the follow-up studies (Shoda et al. 1990) found that kids who waited longer had higher test scores on average. A 2018 replication (Watts, Duncan and Quan) found a much smaller effect once family background was controlled for. The compound-interest figure is $200/month at 7 % a year for 30 years ≈ $244,000, with $72,000 contributed.
