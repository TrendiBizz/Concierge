"""Restore the encrypted VPS snapshot into an isolated disposable database."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time

os.umask(0o077)
tmp = Path(tempfile.mkdtemp(prefix='trendi-restore-'))
name = 'trendi-restore-check-' + str(os.getpid())
created = False

def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)

try:
    run(['restic', 'check', '--quiet'])
    run(['restic', 'restore', 'latest', '--host', 'trendi-vps', '--tag', 'trendi-vps',
         '--target', str(tmp), '--quiet'])
    stage = tmp / 'opt/trendi/backup-stage'
    assert (stage / 'concierge.dump').stat().st_size > 0
    assert (tmp / 'opt/trendi/shared/social.env').stat().st_size > 0
    assert (stage / 'social-media').is_dir()
    for metadata in (stage / 'social-media').glob('*/*.json'):
        record = json.loads(metadata.read_text())
        assert metadata.with_suffix('.bin').stat().st_size == record['bytes']
    with sqlite3.connect(str(stage / 'social.db')) as database:
        assert database.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    run(['docker', 'run', '-d', '--rm', '--name', name, '--network', 'none',
         '--memory', '512m', '-e', 'POSTGRES_HOST_AUTH_METHOD=trust',
         'pgvector/pgvector:pg16'], stdout=subprocess.DEVNULL)
    created = True
    for attempt in range(30):
        if subprocess.run(['docker', 'exec', name, 'pg_isready', '-U', 'postgres'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Isolated restore database did not start')
    for label, database in [('concierge', 'concierge'), ('crm', 'default')]:
        run(['docker', 'exec', name, 'createdb', '-U', 'postgres', database])
        with (stage / (label + '.dump')).open('rb') as dump:
            run(['docker', 'exec', '-i', name, 'pg_restore', '-U', 'postgres',
                 '-d', database, '--no-owner', '--exit-on-error'], stdin=dump)
        count = subprocess.check_output(['docker', 'exec', name, 'psql', '-U', 'postgres',
            '-d', database, '-Atc', "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')"], text=True).strip()
        print(label, 'encrypted backup restored:', count, 'tables', flush=True)
    run(['tar', '-tzf', str(stage / 'crm-storage.tar.gz')], stdout=subprocess.DEVNULL)
    print('Encrypted backup restore test passed: both databases, social vault, uploads and settings.', flush=True)
finally:
    if created:
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(tmp)
