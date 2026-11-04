#!/usr/bin/env bash
# Run scripts/start-concierge.sh automatically every time you log in to your Mac.
#
#   scripts/install-autostart-macos.sh              install (or update)
#   scripts/install-autostart-macos.sh --uninstall  remove
#
# Prerequisites: Docker Desktop installed, LM Studio installed with the `lms` CLI, and
# scripts/configure-lmstudio.sh already run. Logs: ~/Library/Logs/concierge-start.log
set -euo pipefail

[ "$(uname)" = "Darwin" ] || { echo "This installer is for macOS (launchd)." >&2; exit 1; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.concierge.autostart"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG="$HOME/Library/Logs/concierge-start.log"
DOMAIN="gui/$(id -u)"

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Autostart removed."
  exit 0
fi

[ -f "$ROOT/.env" ] || { echo ".env missing. Run scripts/gen-env.sh and scripts/configure-lmstudio.sh first." >&2; exit 1; }

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
    <string>${ROOT_X}/scripts/start-concierge.sh</string>
  </array>
  <key>WorkingDirectory</key><string>${ROOT_X}</string>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>${LOG_X}</string>
  <key>StandardErrorPath</key><string>${LOG_X}</string>
</dict>
</plist>
EOF

# Reload so an updated plist takes effect.
launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"

echo "Installed. The concierge will start automatically at login."
echo "  Log:    $LOG   (tail -f it to watch)"
echo "  Remove: scripts/install-autostart-macos.sh --uninstall"
echo "Tip: also enable 'Start Docker Desktop when you sign in' in Docker Desktop settings."
