#!/usr/bin/env bash
# Store your Cloudflare R2 backup settings safely. Secrets are typed hidden and saved only to
# concierge-stack/backup.env (git-ignored, owner-only permissions). Nothing is printed except,
# once, the new backup password, so you can put it in a password manager.
# Run from a normal Terminal window:  ./concierge-stack/set-backup.sh
#
# In Cloudflare (dash.cloudflare.com > R2 Object Storage):
#   1. Create a bucket, for example trendi-concierge-backup.
#   2. On the R2 overview page, copy your Account ID.
#   3. Manage R2 API Tokens > Create API token > permission "Object Read & Write",
#      limited to that one bucket. Copy the Access Key ID and the Secret Access Key
#      (the secret is shown once).
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
FILE="$DIR/backup.env"

read -r -p "R2 Account ID: " ACCOUNT
read -r -p "Bucket name (e.g. trendi-concierge-backup): " BUCKET
read -r -p "R2 Access Key ID: " KEYID
read -r -s -p "R2 Secret Access Key (hidden), then press Return: " SECRET
echo
if [[ -z "${ACCOUNT// }" || -z "${BUCKET// }" || -z "${KEYID// }" || -z "${SECRET// }" ]]; then
  echo "A value was empty. Nothing changed." >&2
  exit 1
fi
if ! [[ "$ACCOUNT" =~ ^[0-9a-fA-F]{32}$ ]]; then
  echo "The Account ID should be exactly 32 letters and digits. You entered ${#ACCOUNT} characters." >&2
  echo "It is the code after dash.cloudflare.com/ in the address bar, or the part before" >&2
  echo ".r2.cloudflarestorage.com in the bucket's S3 API address. Nothing changed." >&2
  exit 1
fi
if [[ "$ACCOUNT" == "$KEYID" ]]; then
  echo "The Account ID and the Access Key ID are the same value, so one of them is wrong." >&2
  echo "The Account ID is the code in the address bar after dash.cloudflare.com/. Nothing changed." >&2
  exit 1
fi

# Keep an existing backup password: changing it would make older backups unreadable.
PASSWORD=""
NEW_PASSWORD="no"
if [[ -f "$FILE" ]]; then
  PASSWORD="$(grep '^RESTIC_PASSWORD=' "$FILE" | head -1 | cut -d= -f2- || true)"
fi
if [[ -z "$PASSWORD" ]]; then
  PASSWORD="$(openssl rand -base64 33 | tr -d '\n')"
  NEW_PASSWORD="yes"
fi

umask 077
cat > "$FILE" <<EOF
RESTIC_REPOSITORY=s3:https://${ACCOUNT}.r2.cloudflarestorage.com/${BUCKET}
AWS_ACCESS_KEY_ID=${KEYID}
AWS_SECRET_ACCESS_KEY=${SECRET}
AWS_DEFAULT_REGION=auto
RESTIC_PASSWORD=${PASSWORD}
# Backup snapshots older than this many days are deleted (the newest 3 are always kept). A transcript
# deleted from the Mac can still sit in older snapshots, so its longest life is the transcript retention
# plus this number of days.
BACKUP_KEEP_DAYS=30
EOF
chmod 600 "$FILE"
unset SECRET

echo "Saved R2 settings to $FILE (owner-only, git-ignored)."
if [[ "$NEW_PASSWORD" == "yes" ]]; then
  echo
  echo "BACKUP PASSWORD (shown once). Save it in your password manager NOW:"
  echo "  $PASSWORD"
  echo
  echo "Backups are encrypted with it. If you lose it AND this Mac, the backups cannot be read."
fi
echo "Next: ./concierge-stack/backup.sh   then   ./concierge-stack/restore-test.sh"
