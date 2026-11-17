#!/usr/bin/env bash
# Install the Monday 09:45 LinkedIn poster for the Trendi company page.
# One-time prerequisite: scripts/social/linkedin-login.sh, then log in as Jo.
set -euo pipefail
[ "$(uname)" = "Darwin" ] || { echo "macOS only" >&2; exit 1; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LABEL="com.trendi.linkedin-weekly"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG="$HOME/Library/Logs/trendi-linkedin-weekly.log"
PY="/opt/homebrew/Caskroom/miniforge/base/bin/python"
DOMAIN="gui/$(id -u)"

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
  rm -f "$PLIST"
  echo "LinkedIn weekly schedule removed."
  exit 0
fi

[ -x "$PY" ] || { echo "missing $PY" >&2; exit 1; }
[ -d "$HOME/.trendi-linkedin-profile" ] || { echo "profile missing; run scripts/social/linkedin-login.sh first" >&2; exit 1; }
xml_escape() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }
ROOT_X="$(xml_escape "$ROOT")"; LOG_X="$(xml_escape "$LOG")"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PY}</string>
    <string>${ROOT_X}/scripts/social/linkedin_weekly_post.py</string>
  </array>
  <key>WorkingDirectory</key><string>${ROOT_X}</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>1</integer>
    <key>Hour</key><integer>9</integer>
    <key>Minute</key><integer>45</integer>
  </dict>
  <key>RunAtLoad</key><false/>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>${LOG_X}</string>
  <key>StandardErrorPath</key><string>${LOG_X}</string>
</dict>
</plist>
EOF
launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
echo "Installed. Mondays 09:45. Log: $LOG"
