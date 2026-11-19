"""Production audits that `plan` runs on the storyboard, and `script` runs on the script text.

Storyboard: static-frame gaps, same kind three in a row, jump cuts between near-identical shot sizes,
new places that don't open wide, the hook's pattern-interrupt rate, mini-chapter length, re-hook spacing,
dutch-angle overuse and overscan. Script: hook and outro throat-clearing, long sentences, digits, chapter
open loops and mini-chapter length."""
import re
from .camera import SIZE_RANK
from .timing import sentences

WORLD = ("wide", "dialogue", "walk", "closeup", "skyline", "crowd")
DEFAULT_SET = dict(wide="office", dialogue="office", walk="street", closeup="office", skyline="skyline", crowd="void")
REHOOK_KINDS = ("versus", "panels", "metaphor")


def mmss(t): return f"{int(t // 60)}:{int(t % 60):02d}"


def size_of(shot):
    sp = shot.spec; k = shot.kind
    if k not in ("wide", "dialogue", "closeup", "walk", "skyline", "crowd"): return None
    return sp.get("size") or ("cu" if k == "closeup" else "ws")


def subject_of(shot):
    sp = shot.spec
    if sp.get("who"): return sp["who"]
    ch = sp.get("chars") or []
    return ch[0]["id"] if ch else None


def change_times(shot):
    """Every moment the picture gets something new: the cut, cues, beats, timed camera moves."""
    ts = [shot.t0]
    ts += [e[1] for e in shot.events]
    for a in shot.actors: ts += [b["t"] for b in a.beats]
    if shot.camx:
        ts += [m["t"] for m in shot.camx.moves]
        if shot.camx.preset in ("push", "punch"): ts.append(shot.camx.pt)
    if shot.pol: ts.append(shot.pol["t"])
    for k in ("lower_third",):
        if shot.spec.get(k): ts.append(shot.cue(shot.spec[k].get("at"), .15))
    return sorted(t for t in ts if shot.t0 - 1e-6 <= t < shot.t1)


def storyboard(tl, built, story):
    """Returns (warnings, notes). built: list of Shot objects in order."""
    W, N = [], []
    # 1) static-frame audit: something new every 4-6 s
    allc = []
    for s in built:
        cs = change_times(s); allc += cs
        if s.t1 - s.t0 > 15 and len(cs) < 3:
            W.append(f"shot {s.sh['k']} ({mmss(s.t0)}): {s.t1 - s.t0:.0f} s with {len(cs) - 1} changes; long shots need 2+ beats, labels or moves")
    allc = sorted(set(round(t, 2) for t in allc)) + [tl.duration]
    worst = (0, 0)
    for a, b in zip(allc, allc[1:]):
        if b - a > worst[0]: worst = (b - a, a)
        if b - a > 6.5:
            k = next(s.sh["k"] for s in built if s.t0 - 1e-6 <= a < s.t1)
            W.append(f"static frame {mmss(a)}-{mmss(b)} ({b - a:.1f} s) in shot {k}: add a beat, label, prop or camera move (aim for one every 4-6 s)")
    # hook: pattern interrupt every 3-4 s in the first 45 s
    hook = [t for t in allc if t < 45]
    for a, b in zip(hook, hook[1:]):
        if b - a > 4.5: W.append(f"hook: {b - a:.1f} s without a change at {mmss(a)} (the first 45 s want a new picture or beat every 3-4 s)")
    if built and change_times(built[0])[1:2] and change_times(built[0])[1] - built[0].t0 > 1.5:
        N.append("hook: the first shot's first beat lands after 1.5 s; put the strongest visual on the first word")
    # 2) never three of the same kind in a row
    for i in range(2, len(built)):
        k = [built[j].kind for j in (i - 2, i - 1, i)]
        if k[0] == k[1] == k[2] and k[0] != "title":
            W.append(f"shots {built[i - 2].sh['k']}-{built[i].sh['k']}: three '{k[0]}' shots in a row; swap one for a graphic or a different size")
    # 3) jump cuts + establishing shots
    last_set = None
    for i, s in enumerate(built):
        if s.kind in WORLD:
            st = s.spec.get("set", DEFAULT_SET.get(s.kind)); sz = size_of(s)
            direct = i > 0 and built[i - 1].kind in WORLD  # a graphic in between already resets the geography
            if st != last_set and last_set is not None and direct and sz and SIZE_RANK.get(sz, 1) >= 3 and s.kind != "skyline":
                N.append(f"shot {s.sh['k']} ({mmss(s.t0)}): new place '{st}' opens on a {sz}; open on a wide (or skyline/walk) first, then cut in")
            last_set = st
        if i == 0: continue
        p = built[i - 1]; a, b = size_of(p), size_of(s)
        if a and b and subject_of(p) and subject_of(p) == subject_of(s) and abs(SIZE_RANK[a] - SIZE_RANK[b]) <= 1 and not s.spec.get("cut"):
            W.append(f"shots {p.sh['k']}->{s.sh['k']}: {a}->{b} on the same character reads as a jump cut; jump two sizes (wide -> close-up) or cut away")
    # 4) mini-chapters (silent title cards) every 2-3 min in long videos
    cards = [s.t0 for s in built if s.kind == "title" and s.sh["silent"]]
    marks = [0.0] + cards + [tl.duration]
    if tl.duration > 300:
        for a, b in zip(marks, marks[1:]):
            if b - a > 210: W.append(f"mini-chapter {mmss(a)}-{mmss(b)} runs {(b - a) / 60:.1f} min; add a chapter card (each mini-story 2-3 min)")
    # 5) re-hooks every 60-90 s (stamps, spoken titles, versus, panels, metaphors, punch-ins)
    rh = [0.0]
    for s in built:
        if s.kind in REHOOK_KINDS or (s.kind == "title" and not s.sh["silent"]): rh.append(s.t0)
        if s.stamp: rh.append(s.stamp["t"])
        if s.camx and (s.camx.preset in ("push", "punch") or any(m["type"] in ("punch", "dutch") for m in s.camx.moves)): rh.append(s.t0)
    rh = sorted(rh) + [tl.duration]
    for a, b in zip(rh, rh[1:]):
        if b - a > 100: W.append(f"no re-hook {mmss(a)}-{mmss(b)} ({b - a:.0f} s): add a stamp, spoken title, versus/panels/metaphor or a push-in (every 60-90 s)")
    # 6) dutch angle sparingly, overscan
    dutch = [s.sh["k"] for s in built if s.camx and (s.camx.angle == "dutch" or any(m["type"] == "dutch" for m in s.camx.moves))]
    if len(dutch) > max(2, int(tl.duration / 200)):
        W.append(f"dutch angle on {len(dutch)} shots {dutch}: keep it for panic or a sudden realisation (about 1 per 3-4 min)")
    for s in built:
        z = (s.spec.get("cam") or {}).get("zoom")
        if z and min(z) < 1.0: W.append(f"shot {s.sh['k']}: cam zoom {min(z)} < 1.0 would show the edge of the set; the engine clamps it to 1.0")
    # 7) colour moods
    grades = {str(s.sh.get("grade")) for s in built if s.kind != "title"}
    if tl.duration > 240 and len(grades) < 2:
        N.append("colour: one grade for the whole video; give acts a mood with act_grade (cool for the problem, warm for the payoff)")
    gaps = [b - a for a, b in zip(allc, allc[1:])]
    N.insert(0, f"pacing: {len(built)} shots, average {tl.duration / max(1, len(built)):.1f} s; a new visual every {sum(gaps) / max(1, len(gaps)):.1f} s on average, longest hold {worst[0]:.1f} s at {mmss(worst[1])}")
    return W, N


# ------------------------------------------------------------------ script
OPENERS = re.compile(r"\b(hey guys|hi guys|hello everyone|welcome back|welcome to (my|the) channel|in (today's|this) video|before we (start|begin|get started)|don't forget to subscribe)\b", re.I)
CLOSERS = re.compile(r"\b(thanks for watching|thank you for watching|like and subscribe|smash (that|the) like|see you (next time|in the next)|that's (it|all) for (today|this video)|comment below)\b", re.I)
LOOPS = re.compile(r"(\?|\bbut\b|\buntil\b|\bnobody\b|\bno one\b|\bnever\b|\byet\b|\bexcept\b|\bthat's when\b|\bwhat happened next\b|\bwasn't\b|\bdidn't\b|\bwrong\b|\bworse\b|\bstranger\b|\bsecret\b|\bproblem\b|\bmistake\b|\bcatch\b|\btwist\b)", re.I)


def script(text, wpm=145):
    W, N = [], []
    ss = sentences(text); words = sum(len(s.split()) for s in ss)
    if not ss: return ["script.txt is empty"], N
    first = " ".join(ss[:2])
    if OPENERS.search(first): W.append(f"hook: '{OPENERS.search(first).group(0)}' in the opening; start in the middle of the tension with the boldest line")
    if len(ss[0].split()) > 16: W.append(f"hook: the first sentence has {len(ss[0].split())} words; the opening line should land in under 5 s (about 12 words)")
    last = " ".join(ss[-3:])
    if CLOSERS.search(last): W.append(f"outro: '{CLOSERS.search(last).group(0)}' at the end; bridge straight into the next video instead (viewers click away on goodbyes)")
    for i, s in enumerate(ss):
        n = len(s.split())
        if n > 18: W.append(f"sentence {i}: {n} words; keep spoken sentences under 18 (split it)")
        if re.search(r"\d", s): N.append(f"sentence {i}: digits ('{re.search(r'[$]?[0-9][0-9,.%]*', s).group(0)}'); write numbers as spoken words so the alignment and the read match")
    # chapters: open loop before each card, 2-3 min per mini-chapter
    lines = [l.strip() for l in text.replace("\r", "").split("\n")]; chap = []; cur = []; titles = []
    for l in lines:
        if l.startswith("#"): chap.append(cur); cur = []; titles.append(l.lstrip("# ").strip())
        elif l: cur.append(l)
    chap.append(cur)
    for j, ch in enumerate(chap[:-1]):
        if not ch: continue
        tail = sentences(" ".join(ch))[-2:]
        if not LOOPS.search(" ".join(tail)):
            N.append(f"before chapter '{titles[j]}': the last lines don't plant an open loop; tease what's coming ('...until one tiny detail broke everything')")
    for j, ch in enumerate(chap):
        w = sum(len(x.split()) for x in ch); m = w / wpm
        if words / wpm > 6 and m > 3.6: W.append(f"mini-chapter {j + 1} is {w} words (~{m:.1f} min); split it with a chapter card (2-3 min each)")
    you = sum(len(re.findall(r"\byou(r|'re|rself)?\b", s, re.I)) for s in ss)
    if words / wpm > 3 and you < words / wpm * 1.2: N.append(f"'you' appears {you} times in ~{words / wpm:.0f} min; tie the story to the viewer about every 45 s")
    N.insert(0, f"{len(ss)} sentences, {words} words, about {words / 150:.1f}-{words / 140:.1f} min at 150-140 wpm, {len(titles)} chapter cards")
    return W, N
