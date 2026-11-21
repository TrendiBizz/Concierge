"""The nightly encrypted backup no longer has to know about a CRM profile.

Twenty was retired on 2026-11-17 (never used). The backup now dumps only the core database and the
social vault, so there is no optional CRM unit to skip. This keeps the earlier lesson (a backup must
never silently lose the core database) while asserting the CRM logic is actually gone.
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
    docker = fake_bin / "podman"
    docker.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        case "$1" in
          inspect)
            if [ "$2" = "--format" ]; then
              case "$4" in
                trendi-postgres-1) echo {'true' if postgres_running else 'false'} ;;
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


def test_the_backup_dumps_the_core_database_and_touches_no_crm(tmp_path):
    fake_bin, capture = _world(tmp_path)
    done = _run(tmp_path, fake_bin)
    assert done.returncode == 0, done.stderr
    manifest = json.loads((capture / "backup-manifest.json").read_text())
    assert "crm_included" not in manifest
    assert not any("crm" in item for item in manifest["skipped"])
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
    assert "required=True" in source
    assert "trendi-crm" not in source and "crm-storage" not in source
