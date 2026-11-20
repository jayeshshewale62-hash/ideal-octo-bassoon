#!/bin/bash
# setup.sh <project dir>: copies the v2 engine into a new short's folder, installs three.js r160, builds toon.js,
# links Playwright, and checks the Python deps. Only the three.js / scipy installs need the network.
set -e
KIT="$(cd "$(dirname "$0")/.." && pwd)"; DST="${1:?usage: setup.sh ~/shorts/<slug>}"
mkdir -p "$DST"/{web,work,stills,frames,out,audio}
cpn() { local d="${@: -1}"; for f in "${@:1:$#-1}"; do [ -f "$f" ] && { [ -e "$d/$(basename "$f")" ] || cp "$f" "$d/"; }; done; return 0; } # copy, never overwrite
cpn "$KIT"/engine/web/* "$DST/web"
cpn "$KIT"/engine/{render.mjs,timing.py,sheet.py,finish.sh,captions.py,pacing.py,audit.mjs} "$DST"
cpn "$KIT"/engine/audio/*.py "$DST/audio"
chmod +x "$DST/finish.sh"
cd "$DST/web"
[ -f package.json ] || printf '{ "name": "short", "private": true, "type": "module" }\n' > package.json
[ -d node_modules/three ] || npm i three@0.160.0 --no-audit --no-fund >/dev/null
cat toonbase.js cast.js > toon.js
cd "$DST"
if [ ! -e node_modules ]; then G=$(npm root -g); [ -d "$G/playwright" ] && ln -s "$G" node_modules || echo "install playwright: npm i -g playwright && npx playwright install chromium"; fi
python3 -c "import numpy, scipy, PIL" 2>/dev/null || pip install -q numpy scipy pillow || echo "install python deps: pip install numpy scipy pillow"
ffmpeg -hide_banner -filters 2>/dev/null | grep -q " ass " || echo "WARN: ffmpeg lacks libass (captions cannot be burned in)"
for f in web/*.js; do node --check "$f" >/dev/null || echo "syntax error: $f"; done
python3 -m py_compile timing.py sheet.py captions.py pacing.py audio/*.py && echo "python ok"
echo "ready: $DST (web/story.js + web/layout.js are the 'Grocer's Rocket Cart' demo: replace layout, shots and audio cues)"
