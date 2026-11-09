#!/bin/zsh
# Turn a genuine macOS screen recording into a TikTok review-ready MP4.
# Never synthetically depict OAuth consent or a successful integration.
# Usage: ./scripts/prepare-tiktok-review-video.zsh "/path/to/real-recording.mov"
set -euo pipefail

if [[ "$#" -ne 1 || ! -f "$1" ]]; then
  print -u2 "Usage: $0 /absolute/path/to/your-actual-screen-recording.mov"
  exit 2
fi
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  print -u2 "ffmpeg and ffprobe must be installed"
  exit 2
fi

source_file="$1"
out_dir="/Users/jo/work-staging/concierge-integration/QA/verification/tiktok-review"
mkdir -p "$out_dir"
chmod 700 "$out_dir"
output="$out_dir/Trendi_Concierge_TikTok_LoginKit_Sandbox_Review.mp4"
tmp="$out_dir/.tiktok-review-render.mp4"
trap 'rm -f "$tmp"' EXIT

# Stay below the upload limit with room for metadata and variable content.
# 720p is clear enough to read the browser URL and OAuth prompts on a desktop.
duration="$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$source_file")"
if [[ -z "$duration" ]]; then
  print -u2 "Could not read the source duration"
  exit 1
fi
bitrate="$(python3 - "$duration" <<'PY'
import sys
length=float(sys.argv[1])
if length<=0 or length>1800:
    raise SystemExit("Expected a positive recording under 30 minutes")
# Approx. 45 MiB maximum including audio; cap video to preserve readability.
print(max(180, min(1900, int((45 * 1024 * 1024 * 8 / length / 1000) - 128))))
PY
)"

ffmpeg -hide_banner -loglevel warning -y -i "$source_file" \
  -map 0:v:0 -map '0:a:0?' \
  -vf "scale='min(1280,iw)':-2:flags=lanczos,fps=20" \
  -c:v libx264 -preset medium -b:v "${bitrate}k" \
  -maxrate "${bitrate}k" -bufsize "$((bitrate*2))k" \
  -pix_fmt yuv420p -c:a aac -b:a 96k -movflags +faststart \
  "$tmp"

bytes="$(stat -f%z "$tmp")"
if (( bytes >= 50000000 )); then
  print -u2 "Video exceeds TikTok 50 MB limit; shorten the recording or lower resolution"
  exit 1
fi
ffprobe -v error -show_entries stream=codec_name -of compact "$tmp"
mv "$tmp" "$output"
chmod 600 "$output"
print "Review video prepared: $output"
print "Size (MB): $(python3 - "$bytes" <<'PY'
import sys
print(round(int(sys.argv[1])/1_000_000,2))
PY
)"
print "Before uploading: confirm it shows the live sandbox account authorization and success, and contains no passwords, tokens, or secrets."
