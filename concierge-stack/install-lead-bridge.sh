#!/usr/bin/env bash
# Install the existing Twenty lead bridge as a per-user macOS launchd service.
# No secrets are embedded in the plist: start.sh reads the key from Keychain.
set -euo pipefail
LABEL="com.trendi.concierge-lead-bridge"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/integrations/twenty/bridge"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
  rm -f "$PLIST"
  echo "Lead bridge launch agent removed."
  exit 0
fi
[[ -f "$DIR/start.sh" ]] || { echo "Bridge start.sh not found." >&2; exit 1; }
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<PLIST_XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>$LABEL</string>
<key>ProgramArguments</key><array><string>/bin/bash</string><string>$DIR/start.sh</string></array>
<key>WorkingDirectory</key><string>$DIR</string>
<key>EnvironmentVariables</key><dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
<key>ThrottleInterval</key><integer>15</integer>
<key>StandardOutPath</key><string>$HOME/Library/Logs/trendi-lead-bridge.log</string>
<key>StandardErrorPath</key><string>$HOME/Library/Logs/trendi-lead-bridge-error.log</string>
</dict></plist>
PLIST_XML
chmod 600 "$PLIST"
plutil -lint "$PLIST"
echo "Launch agent prepared: $PLIST"
echo "To activate, stop the manually started bridge and bootstrap: launchctl bootstrap $DOMAIN $PLIST"
