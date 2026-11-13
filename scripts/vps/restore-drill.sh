#!/bin/bash
set -e
LATEST=$(ls -t /opt/trendi/backups/trendi-backup-*.tar.gz | head -1)
echo "archive: $LATEST ($(du -h "$LATEST" | cut -f1))"
rm -rf /tmp/restoredrill && mkdir -p /tmp/restoredrill
tar xzf "$LATEST" -C /tmp/restoredrill
echo "contents:"; ls -1 /tmp/restoredrill
docker exec trendi-postgres-1 psql -U postgres -c 'DROP DATABASE IF EXISTS restore_drill' >/dev/null
docker exec trendi-postgres-1 psql -U postgres -c 'CREATE DATABASE restore_drill' >/dev/null
docker cp /tmp/restoredrill/concierge.dump trendi-postgres-1:/tmp/concierge.dump >/dev/null
docker exec trendi-postgres-1 pg_restore -U postgres -d restore_drill --no-owner --no-privileges /tmp/concierge.dump 2>&1 | tail -2 || true
echo "--- recovered ---"
docker exec trendi-postgres-1 psql -U postgres -d restore_drill -tAc "SELECT 'businesses='||(SELECT count(*) FROM tenants)||' enquiries='||(SELECT count(*) FROM leads)||' quotes='||(SELECT count(*) FROM quotations)||' messages='||(SELECT count(*) FROM messages)||' users='||(SELECT count(*) FROM tenant_users)"
docker exec trendi-postgres-1 psql -U postgres -c 'DROP DATABASE restore_drill' >/dev/null
rm -f /tmp/restoredrill/concierge.dump; rm -rf /tmp/restoredrill
echo "scratch database dropped, drill complete"
