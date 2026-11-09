#!/usr/bin/env bash
# Installs two macOS launchd jobs for the current user:
#   - a backup every day at 03:15
#   - a restore test on the 1st of each month at 03:45
#
#   ./concierge-stack/install-backup-schedule.sh              install (or reinstall)
#   ./concierge-stack/install-backup-schedule.sh --uninstall  remove both jobs
#
# A job missed because the Mac was asleep or off runs when it next wakes. If the Mac is shut down for
# days there are no backups for those days. Results go to ~/Library/Logs/trendi-concierge-backup.log
# and a failure shows a macOS notification. Nothing here needs admin rights.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
BACKUP_LABEL="com.trendi.concierge-backup"
RESTORE_LABEL="com.trendi.concierge-restore-test"

unload() {
  launchctl bootout "gui/$UID_NUM/$1" >/dev/null 2>&1 || true
}

if [[ "${1:-}" == "--uninstall" ]]; then
  for label in "$BACKUP_LABEL" "$RESTORE_LABEL"; do
    unload "$label"
    rm -f "$AGENTS/$label.plist"
  done
  echo "Both scheduled jobs removed."
  exit 0
fi

if [[ ! -f "$DIR/backup.env" ]]; then echo "Run ./concierge-stack/set-backup.sh first." >&2; exit 1; fi
chmod +x "$DIR/scheduled-run.sh"
mkdir -p "$AGENTS"

write_plist() {  # label task calendar-xml
  cat > "$AGENTS/$1.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$1</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$DIR/scheduled-run.sh</string>
    <string>$2</string>
  </array>
  <key>StartCalendarInterval</key>
  $3
  <key>StandardOutPath</key><string>/dev/null</string>
  <key>StandardErrorPath</key><string>/dev/null</string>
</dict>
</plist>
EOF
  plutil -lint "$AGENTS/$1.plist" >/dev/null
}

write_plist "$BACKUP_LABEL" backup "<dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>15</integer></dict>"
write_plist "$RESTORE_LABEL" restore-test "<dict><key>Day</key><integer>1</integer><key>Hour</key><integer>3</integer><key>Minute</key><integer>45</integer></dict>"

for label in "$BACKUP_LABEL" "$RESTORE_LABEL"; do
  unload "$label"
  launchctl bootstrap "gui/$UID_NUM" "$AGENTS/$label.plist"
done

echo "Installed:"
echo "  daily backup at 03:15           ($BACKUP_LABEL)"
echo "  monthly restore test, 1st 03:45 ($RESTORE_LABEL)"
echo "Log: ~/Library/Logs/trendi-concierge-backup.log"
echo "Try it now without waiting: launchctl kickstart gui/$UID_NUM/$BACKUP_LABEL"
