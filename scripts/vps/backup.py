"""Back up live VPS databases, social vault, uploads, release and recovery settings.

The Twenty CRM (and its optional compose profile) was retired on 2026-11-17; it had never been used.
The backup now dumps only the core Concierge database plus the social vault. Only that core database
is allowed to fail the run — a backup that silently loses it is worse than one that fails loudly.
"""
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone

RELEASES = '/opt/trendi/releases/20261108-vps'
STAGE = Path(os.environ.get('BACKUP_STAGE', '/opt/trendi/backup-stage'))
BACKUPS = Path(os.environ.get('BACKUP_DIR', '/opt/trendi/backups'))


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def container_running(name):
    done = subprocess.run(
        ['podman', 'inspect', '--format', '{{.State.Running}}', name],
        capture_output=True, text=True)
    return done.returncode == 0 and done.stdout.strip() == 'true'


def dump_database(stage, container, database, required, skipped):
    if not container_running(container):
        if required:
            raise SystemExit(
                f"{container} is not running: the Concierge database cannot be skipped")
        skipped.append(f"database {database} skipped: {container} is not running")
        return
    with (stage / f"{database if database != 'default' else 'crm'}.dump").open('wb') as output:
        run(['podman', 'exec', container, 'pg_dump', '-U', 'postgres', '-d', database,
             '--format=custom', '--no-owner', '--no-acl'], stdout=output)
    size = (stage / f"{database if database != 'default' else 'crm'}.dump").stat().st_size
    if size == 0:
        raise SystemExit(f"pg_dump of {database} on {container} produced an empty file")


def main():
    os.umask(0o077)
    BACKUPS.mkdir(parents=True, exist_ok=True)
    lock = open(BACKUPS / 'backup.lock', 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('another backup is already running')

    # A stable path lets restic deduplicate successive snapshots.
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(mode=0o700)
    stage = STAGE
    skipped = []

    # Require the existing repository: never silently initialize an empty destination.
    run(['restic', 'cat', 'config'], stdout=subprocess.DEVNULL)

    dump_database(stage, 'trendi-postgres-1', 'concierge', required=True, skipped=skipped)

    source = Path(subprocess.check_output(
        ['podman', 'volume', 'inspect', '--format', '{{.Mountpoint}}', 'trendi_social'],
        text=True).strip()) / 'social.db'
    media = source.parent / 'media'
    (stage / 'social-media').mkdir(mode=0o700, exist_ok=True)
    if media.exists():
        shutil.copytree(media, stage / 'social-media', dirs_exist_ok=True)
    with sqlite3.connect(str(source)) as src, sqlite3.connect(str(stage / 'social.db')) as dst:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise SystemExit('the social vault copy failed its integrity check')

    # Preserve the inactive legacy voice service for recovery, without activating it.
    for filename in ('voice-original.env', 'voice-data.tar.gz'):
        legacy = BACKUPS / filename
        if legacy.exists():
            shutil.copy2(legacy, stage / filename)

    (stage / 'backup-manifest.json').write_text(json.dumps({
        'created_at': datetime.now(timezone.utc).isoformat(),
        'skipped': skipped,
    }, indent=1) + '\n')

    run(['restic', 'backup', str(stage), '/opt/trendi/shared', RELEASES,
         '--host', 'trendi-vps', '--tag', 'trendi-vps', '--quiet'])
    print(json.dumps({'ok': True, 'skipped': skipped}), flush=True)
    # Only the temporary, already encrypted/uploaded stage is removed. Snapshots are retained.
    shutil.rmtree(stage)


if __name__ == '__main__':
    main()
