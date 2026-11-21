#!/usr/bin/env bash
# Install the 07:45 morning report as a macOS LaunchAgent.
#
#   scripts/install-morning-brief-macos.sh              install (or update)
#   scripts/install-morning-brief-macos.sh --uninstall  remove
#
# The report is written to ~/.workwatch/reports/trendi-master/morning-latest.md
# (and a dated copy).
# Logs: ~/Library/Logs/trendi-morning-brief.log
set -euo pipefail

[ "$(uname)" = "Darwin" ] || { echo "This installer is for macOS (launchd)." >&2; exit 1; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.trendi.morning-brief"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG="$HOME/Library/Logs/trendi-morning-brief.log"
DOMAIN="gui/$(id -u)"

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Morning report schedule removed."
  exit 0
fi

xml_escape() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }
ROOT_X="$(xml_escape "$ROOT")"
LOG_X="$(xml_escape "$LOG")"

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>cd '${ROOT_X}' &amp;&amp; /usr/bin/python3 scripts/reports/morning_brief.py</string>
  </array>
  <key>WorkingDirectory</key><string>${ROOT_X}</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>7</integer>
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
echo "Installed. The morning report runs daily at 07:45."
echo "  Report: ~/.workwatch/reports/trendi-master/morning-latest.md"
echo "  Log:    $LOG"
echo "  Remove: scripts/install-morning-brief-macos.sh --uninstall"
