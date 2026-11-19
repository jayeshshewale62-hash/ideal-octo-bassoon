"""Pre-production sheets.

cast  -> P/work/cast_sheet.jpg: every character in colour, the solid-black silhouette test (idle and an action
         pose), and an 8-expression sheet; plus checks: silhouettes too alike, more than 4 colours, look-alike outfits.
board -> P/storyboard.md: the two-column script (VO | VISUAL) with camera, cut, grade and sound per shot, for
         hand-off to an animator, an editor or the voice actor."""
import math, os
import numpy as np, skia
from .kit import *

EXPRESSIONS = [("neutral", "idle"), ("happy", "celebrate"), ("shocked", "stressed"), ("smug", "arms_crossed"),
               ("tired", "pockets"), ("angry", "hips"), ("thinking", "think"), ("worried", "facepalm")]


def _draw(c, x, y, s, look, emotion="neutral", pose="idle", face=-.3):
    eyes, mouth, brow, bt, ex = EMOTIONS[emotion]; arms = POSES[pose]
    draw_char(c, x, y, s, look, face=face, eyes='closed' if pose == 'facepalm' else eyes, mouth=mouth, brow=brow, brow_tilt=bt, arms=arms,
              sweat=.3 if ex.get('sweat') else -1, sparkle=.6 if ex.get('sparkle') else 0, pupil=ex.get('pupil', 0))


def silhouette(look, pose="idle", w=520, h=760):
    a, surf = np_surface(w, h); c = surf.getCanvas(); c.clear(C((0, 0, 0), 0)); _draw(c, w / 2, h - 40, 1.0, look, pose=pose, face=0)
    return a[..., 3] > 40


def colours(look):
    cs = {look["suit"].upper()}
    if look.get("hair") not in ("bald", "none"): cs.add(look["hair_col"].upper())
    if look.get("outfit") == "suit": cs.add(look["shirt"].upper()); cs.add(look["tie"].upper()) if look.get("tie") not in (None, "none") else None
    if look.get("accent"): cs.add(look["accent"].upper())
    if look.get("hat"): cs.add(look["hat_col"].upper())
    return cs


def cast_sheet(P, cast):
    ids = list(cast); warn = []
    masks = {k: silhouette(cast[k]) for k in ids}
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = masks[ids[i]], masks[ids[j]]; iou = (a & b).sum() / max(1, (a | b).sum())
            if iou > .9: warn.append(f"silhouette: '{ids[i]}' and '{ids[j]}' are {iou:.0%} identical in solid black; change hair, hat or build")
            ca, cb = rgb(cast[ids[i]]["suit"]), rgb(cast[ids[j]]["suit"])
            if math.dist(ca, cb) < 40: warn.append(f"colour: '{ids[i]}' and '{ids[j]}' wear near-identical {cast[ids[i]]['suit']} / {cast[ids[j]]['suit']}; give each a distinct base colour")
    for k in ids:
        n = len(colours(cast[k]))
        if n > 4: warn.append(f"palette: '{k}' uses {n} colours besides skin {sorted(colours(cast[k]))}; keep 3-4 (base, secondary, one bright accent)")
        if not cast[k].get("accent") and cast[k].get("outfit") != "suit": warn.append(f"palette: '{k}' has no accent; add one bright 'accent' (a scarf) to pull the eye to the face")
    builds = [cast[k].get("build", "round") for k in ids]
    if len(ids) >= 3 and len(set(builds)) == 1: warn.append("shape language: every character has the same build; use round (friendly), square (stubborn) and triangle (sharp/villain)")
    # draw the sheet
    cw, ew, rh = 330, 250, 470; cols_w = 2 * cw + len(EXPRESSIONS) * ew; Wd = cols_w + 40; Ht = 90 + len(ids) * rh
    surf = skia.Surface(Wd, Ht); c = surf.getCanvas(); c.clear(hx('#F3E6C8'))
    label(c, "CAST SHEET  ·  colour  ·  silhouette test  ·  expressions", 30, 60, 44, INK, skew=0)
    for r, k in enumerate(ids):
        y0 = 90 + r * rh; look = cast[k]
        c.drawRect(skia.Rect(20, y0, Wd - 20, y0 + rh - 16), fp('#FFFFFF', 120))
        _draw(c, 20 + cw / 2, y0 + rh - 70, .72, look, "neutral", "idle", -.3)
        label(c, f"{k}  [{look.get('build', 'round')}]", 30, y0 + rh - 26, 34, INK, skew=0)
        a, s2 = np_surface(cw, rh - 40); cc = s2.getCanvas(); cc.clear(C((0, 0, 0), 0))  # silhouette test: solid black
        _draw(cc, cw * .22, rh - 90, .56, look, "neutral", "idle", 0); _draw(cc, cw * .56, rh - 90, .56, look, "neutral", "point", .6)
        a[..., :3] = 0; c.drawImage(np_image(a), 20 + cw, y0 + 10)
        label(c, "silhouette", 20 + cw + 30, y0 + rh - 26, 30, '#5A5560', skew=0)
        for e, (emo, pose) in enumerate(EXPRESSIONS):
            x0 = 20 + 2 * cw + e * ew; c.save(); c.clipRect(skia.Rect(x0 + 6, y0 + 6, x0 + ew - 6, y0 + rh - 60))
            _draw(c, x0 + ew / 2, y0 + 150 + 419 * 1.0, 1.0, look, emo, pose, -.25); c.restore()
            label(c, emo, x0 + ew / 2, y0 + rh - 26, 32, INK, align='center', skew=0)
    pth = os.path.join(P, "work", "cast_sheet.jpg"); os.makedirs(os.path.dirname(pth), exist_ok=True)
    surf.makeImageSnapshot().save(pth, skia.kJPEG); return pth, warn


# ------------------------------------------------------------------ storyboard markdown
def _mmss(t): return f"{int(t // 60)}:{t % 60:04.1f}"


def _visual(sp):
    k = sp.get("kind", "wide"); bits = [f"**{k}**"]
    if sp.get("set"): bits.append(f"{sp['set']} ({sp.get('time', 'night')})")
    for d in sp.get("chars", []): bits.append(f"{d['id']}: {d.get('emotion', 'neutral')}/{d.get('pose', 'idle')}")
    if sp.get("who") and k != "chart": bits.append(f"{sp['who']}: {sp.get('emotion', 'neutral')}")
    if k == "metaphor": bits.append(f"metaphor: {sp.get('type', 'dominoes')}")
    if k == "panels": bits.append(" / ".join(p.get("caption", "?") for p in sp.get("panels", [])))
    if k == "title": bits.append(f"\"{sp.get('text', '')}\"")
    if k == "versus": bits.append(f"{sp.get('left', {}).get('title', '')} VS {sp.get('right', {}).get('title', '')}")
    if k == "counter": v = sp.get("value", {}); bits.append(f"{v.get('prefix', '')}{v.get('to', '')}{v.get('suffix', '')}")
    if k == "list": bits.append(f"#{sp.get('number', 1)} {sp.get('text', '')}")
    if k == "table": bits.append(", ".join(it.get("type", "newspaper") for it in sp.get("items", [])))
    if k == "icon": bits.append(", ".join(i.get("name", "") for i in sp.get("icons", [])))
    for L in sp.get("labels", []): bits.append(f"label \"{L['text']}\"" + (f" @{L['at']}" if isinstance(L.get('at'), str) else ""))
    if sp.get("stamp"): bits.append(f"STAMP \"{sp['stamp']['text']}\"")
    for b in sp.get("beats", []): bits.append(f"beat @{b.get('at')}: {b.get('emotion', '')} {b.get('pose', '')}".strip())
    if sp.get("polaroid"): bits.append(f"polaroid \"{sp['polaroid'].get('caption', '')}\"")
    return "; ".join(bits)


def _camera(sp, sh):
    cam = sp.get("cam") or {}; bits = []
    if sp.get("size"): bits.append(sp["size"].upper())
    if sp.get("angle") and sp["angle"] != "eye": bits.append(f"{sp['angle']} angle")
    bits.append(cam.get("preset", "creep" if not cam.get("zoom") else "keyframed"))
    for m in sp.get("moves", []): bits.append(f"{m['type']}@{m.get('at')}")
    if sp.get("fg"): bits.append(f"fg {sp['fg']}")
    g = sh.get("grade")
    if g: bits.append(f"grade {g if isinstance(g, str) else g.get('from', '') + '→' + g.get('to', '')}")
    return ", ".join(bits)


def board(P, tl, built, whips):
    from .audio import ambience_spans
    amb = ambience_spans(tl)
    rows = ["| # | time | VO (what is said) | VISUAL (what we see) | CAMERA / CUT | SOUND |", "|---|---|---|---|---|---|"]
    for i, (s, shot) in enumerate(zip(tl.shots, built)):
        sp = s["spec"]; vo = " ".join(tl.S[j]["text"] for j in s["sents"]) if s["sents"] else "*(silent)*"
        if len(s["sents"]) >= 4: vo += " ⚠ 4+ sentences on one picture: split or add beats"
        cut = tl.cuts.get(s["k"]) if hasattr(tl, "cuts") else None
        cam = _camera(sp, s) + (f"; {cut[0].upper()}-cut {abs(cut[1]):.1f}s" if cut else "") + ("; whip out" if whips[i] else "")
        snd = sorted({e[0] for e in shot.sfx_events()}); a = next((n for n, t0, t1 in amb if t0 - 1e-6 <= s["t0"] < t1), None)
        if a: snd.append(f"amb:{a}")
        rows.append(f"| {s['k']} | {_mmss(s['t0'])} | {vo.replace('|', '/')} | {_visual(sp).replace('|', '/')} | {cam} | {', '.join(snd)} |")
    md = f"# {tl.story.get('title', 'Storyboard')}\n\nRuntime {tl.duration / 60:.2f} min · {len(tl.shots)} shots · mood `{tl.story.get('mood', 'mystery')}`\n\n" + "\n".join(rows) + "\n"
    pth = os.path.join(P, "storyboard.md"); open(pth, "w", encoding="utf-8").write(md); return pth
