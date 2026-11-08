"""Back up live VPS databases, social vault, uploads, release and recovery settings."""
import fcntl
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess

os.umask(0o077)
lock = open('/opt/trendi/backups/backup.lock', 'w')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
stage = Path('/opt/trendi/backup-stage')
# A stable path lets restic deduplicate successive snapshots.
stage.mkdir(mode=0o700, exist_ok=True)

def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)

# Require the existing repository: never silently initialize an empty destination.
run(['restic', 'cat', 'config'], stdout=subprocess.DEVNULL)
for name, container, database in [
    ('concierge', 'trendi-postgres-1', 'concierge'),
    ('crm', 'trendi-crm-db-1', 'default'),
]:
    with (stage / (name + '.dump')).open('wb') as output:
        run(['docker', 'exec', container, 'pg_dump', '-U', 'postgres', '-d', database,
             '--format=custom', '--no-owner', '--no-acl'], stdout=output)
    assert (stage / (name + '.dump')).stat().st_size > 0

source = Path(subprocess.check_output(
    ['docker', 'volume', 'inspect', '--format', '{{.Mountpoint}}', 'trendi_social'],
    text=True).strip()) / 'social.db'
media = source.parent / 'media'
(stage / 'social-media').mkdir(mode=0o700, exist_ok=True)
if media.exists():
    shutil.copytree(media, stage / 'social-media', dirs_exist_ok=True)
with sqlite3.connect(str(source)) as src, sqlite3.connect(str(stage / 'social.db')) as dst:
    src.backup(dst)
    assert dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'

with (stage / 'crm-storage.tar.gz').open('wb') as output:
    run(['docker', 'run', '--rm', '--network', 'none', '--read-only',
         '-v', 'trendi_crm-storage:/source:ro', 'node:22-alpine',
         'tar', '-czf', '-', '-C', '/source', '.'], stdout=output)
run(['docker', 'exec', 'trendi-crm-redis-1', 'redis-cli', 'SAVE'], stdout=subprocess.DEVNULL)
run(['docker', 'cp', 'trendi-crm-redis-1:/data/dump.rdb', str(stage / 'crm-redis.rdb')],
    stdout=subprocess.DEVNULL)
# Preserve the inactive legacy voice service for recovery, without activating it.
for filename in ('voice-original.env', 'voice-data.tar.gz'):
    source = Path('/opt/trendi/backups') / filename
    if source.exists():
        shutil.copy2(source, stage / filename)

run(['restic', 'backup', str(stage), '/opt/trendi/shared',
     '/opt/trendi/releases/20261108-vps', '--host', 'trendi-vps', '--tag', 'trendi-vps', '--quiet'])
print('Encrypted VPS backup uploaded successfully.', flush=True)
# Only the temporary, already encrypted/uploaded stage is removed. Snapshots are retained.
shutil.rmtree(stage)
