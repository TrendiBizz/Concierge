"""The nightly encrypted backup must survive an intentionally-stopped CRM profile.

Measured on the VPS 2026-11-15: the Twenty CRM stack runs under the compose `crm` profile and has
been stopped since 2026-11-13. backup.py dumped trendi-crm-db-1 unconditionally, so every run died
with `Error response from daemon: container ... is not running` before restic uploaded anything.
No snapshot was produced for two days while the health check reported ok.
"""
import json
import os
import pathlib
import sqlite3
import subprocess
import textwrap

REPO = pathlib.Path(__file__).resolve().parents[2]
BACKUP = REPO / "scripts" / "vps" / "backup.py"


def _world(tmp_path, *, postgres_running=True):
    social = tmp_path / "socialvol"
    social.mkdir()
    with sqlite3.connect(social / "social.db") as db:
        db.execute("create table posts(id integer)")
    (social / "media").mkdir()

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        case "$1" in
          inspect)
            if [ "$2" = "--format" ]; then
              case "$4" in
                trendi-postgres-1) echo {'true' if postgres_running else 'false'} ;;
                trendi-crm-*) echo false ;;
                *) echo true ;;
              esac
            fi ;;
          volume) echo {social} ;;
          exec)
            if [ "$3" = "pg_dump" ]; then printf 'PGDUMP'; fi ;;
        esac
        exit 0
    """))
    docker.chmod(0o755)

    capture = tmp_path / "captured"
    restic = fake_bin / "restic"
    restic.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        if [ "$1" = "cat" ]; then exit 0; fi
        if [ "$1" = "backup" ]; then
          cp -a "$2" {capture}
        fi
        exit 0
    """))
    restic.chmod(0o755)
    return fake_bin, capture


def _run(tmp_path, fake_bin):
    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["BACKUP_STAGE"] = str(tmp_path / "stage")
    env["BACKUP_DIR"] = str(tmp_path / "backups")
    return subprocess.run(["python3", str(BACKUP)], capture_output=True, text=True, env=env)


def test_a_stopped_crm_profile_is_skipped_not_fatal(tmp_path):
    fake_bin, capture = _world(tmp_path)
    done = _run(tmp_path, fake_bin)
    assert done.returncode == 0, done.stderr
    assert "skipped" in done.stdout.lower()
    manifest = json.loads((capture / "backup-manifest.json").read_text())
    assert manifest["crm_included"] is False
    assert any("crm" in item for item in manifest["skipped"])
    assert (capture / "concierge.dump").exists(), "the real database must always be dumped"
    assert sorted(p.name for p in (capture / "social-media").iterdir()) == []


def test_the_core_database_can_never_be_skipped_silently(tmp_path):
    fake_bin, capture = _world(tmp_path, postgres_running=False)
    done = _run(tmp_path, fake_bin)
    assert done.returncode != 0
    assert "cannot be skipped" in (done.stderr + done.stdout)
    assert not capture.exists(), "nothing may be uploaded when the core database is missing"


def test_the_manifest_says_exactly_what_is_missing():
    source = BACKUP.read_text()
    assert "backup-manifest.json" in source
    assert "required=True" in source and "required=False" in source
