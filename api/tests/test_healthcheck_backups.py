"""The health check must notice a backup that stopped running.

Measured 2026-11-15: encrypted backups had produced nothing since 12 Nov (the optional CRM
container was stopped and the dump failed), while the health report said ok with 39 checks — not
one of them looked at backups. A backup nobody verifies is a backup nobody has.
"""
import importlib.util
import os
import pathlib
import time

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "vps" / "healthcheck.py"
_spec = importlib.util.spec_from_file_location("concierge_healthcheck_backups", SCRIPT)
healthcheck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(healthcheck)


def _archive(directory, name, age_hours):
    path = pathlib.Path(directory) / name
    path.write_bytes(b"x")
    stamp = time.time() - age_hours * 3600
    os.utime(path, (stamp, stamp))
    return path


def _status(monkeypatch, tmp_path, age_hours, service="inactive"):
    _archive(tmp_path, "trendi-backup-20260101-000000.tar.gz", age_hours)
    monkeypatch.setattr(healthcheck, "BACKUPS_DIR", str(tmp_path))
    monkeypatch.setattr(healthcheck, "run", lambda *a, **k: (0, service + "\n"))
    return {item["check"]: item["status"] for item in healthcheck.check_backups()}


def test_a_fresh_backup_is_ok(monkeypatch, tmp_path):
    assert _status(monkeypatch, tmp_path, age_hours=3)["backup:age"] == "ok"


def test_a_missed_daily_run_warns(monkeypatch, tmp_path):
    assert _status(monkeypatch, tmp_path, age_hours=30)["backup:age"] == "warn"


def test_two_missed_days_fail(monkeypatch, tmp_path):
    statuses = _status(monkeypatch, tmp_path, age_hours=60)
    assert statuses["backup:age"] == "fail"


def test_no_archive_at_all_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(healthcheck, "BACKUPS_DIR", str(tmp_path))
    monkeypatch.setattr(healthcheck, "run", lambda *a, **k: (0, "inactive\n"))
    results = healthcheck.check_backups()
    assert any(r["check"] == "backup:age" and r["status"] == "fail" for r in results)


def test_a_failed_scheduled_run_is_reported_even_if_an_old_archive_exists(monkeypatch, tmp_path):
    statuses = _status(monkeypatch, tmp_path, age_hours=3, service="failed")
    assert statuses["backup:service"] == "fail"


def test_the_backup_check_is_part_of_the_report():
    assert "check_backups" in SCRIPT.read_text()
