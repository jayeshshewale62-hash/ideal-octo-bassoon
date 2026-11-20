#!/bin/bash
# finish.sh "Title": master audio = voiceover + SFX only, no music (-14.0 LUFS, LRA 2.4-2.9 LU, -1.0 dBTP; SFX stays locked at -6.0 dB under the
# untouched voice), burn 30 fps pop-word captions (work/words.json -> out/captions.ass; CAPTIONS=0 to skip), encode
# 1080x1920 H.264 CRF 17 at a strict constant 30.00 fps + AAC, then QA: format, freeze/black, loudness, qa_sheet.jpg.
set -e
cd "$(dirname "$0")"
TITLE="${1:-video}"
OUT="out/${TITLE}.mp4"
N=$(ls frames/f*.jpg | wc -l)
echo "frames: $N ($(python3 -c "print(round($N/30,2))") s)"
[ "$N" -ge 1750 ] && [ "$N" -le 1950 ] || echo "WARN: $N frames is outside 1750-1950 (58-65 s)"
(cd audio && python3 finish_audio.py mix.wav ../out/final_audio.wav) || echo "WARN: audio master outside spec (see above)"
VF="format=yuv420p"
if [ "${CAPTIONS:-1}" != "0" ] && [ -f work/words.json ]; then
  python3 captions.py work/words.json out/captions.ass ${CAPTION_FONT:+--font "$CAPTION_FONT"}
  VF="ass=out/captions.ass,format=yuv420p"
fi
ffmpeg -y -v error -framerate 30 -i frames/f%04d.jpg -i out/final_audio.wav -map 0:v:0 -map 1:a:0 -vf "$VF" \
  -r 30 -fps_mode cfr -c:v libx264 -preset veryfast -crf 17 -c:a aac -b:a 256k -ar 48000 -movflags +faststart -shortest "$OUT"
echo "--- format"
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate,avg_frame_rate,nb_frames:format=duration -of default=nw=1 "$OUT"
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate -of csv=p=0 "$OUT" | grep -q "^1080,1920,30/1$" || echo "WARN: not 1080x1920 @ 30/1"
echo "--- freeze / black"
ffmpeg -v info -i "$OUT" -vf "freezedetect=n=-60dB:d=0.4,blackdetect=d=0.05:pix_th=0.08" -an -f null - 2>&1 | grep -E "freeze_|black_" || echo "none"
echo "--- loudness (spec: I -14.0 LUFS, LRA 2.4-2.9 LU, true peak <= -1.0 dBFS)"
ffmpeg -nostats -i "$OUT" -filter_complex ebur128=peak=true -f null - 2>&1 | grep -A14 "Summary" | grep -E "I:|LRA:|Peak:"
mkdir -p out/qa && rm -f out/qa/*.jpg
for i in $(seq 0 30 $((N-1))); do ffmpeg -v error -y -ss "$(python3 -c "print($i/30)")" -i "$OUT" -frames:v 1 "out/qa/f$(printf %04d $i).jpg"; done
python3 sheet.py out/qa out/qa_sheet.jpg 10
