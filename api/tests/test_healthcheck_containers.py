"""The container health check must not page a healthy container on Podman.

Podman's compat API (`ps` through the compat socket) does not append "(healthy)" to the status, so
after the 2026-11-17 move to Podman every healthy container paged once it passed the 10-minute
warmup, even though `inspect` still said healthy. clamav and rspamd define no HEALTHCHECK at
all, so "healthy" could never be true for them. The check now asks the daemon for health directly
and treats a running container with no health check as up.
"""
import importlib.util
import pathlib
import re
from datetime import datetime, timedelta, timezone

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "vps" / "healthcheck.py"
_spec = importlib.util.spec_from_file_location("concierge_healthcheck_containers", SCRIPT)
healthcheck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(healthcheck)

# Every critical container, "Up" — the Podman ps string deliberately has no "(healthy)" suffix.
PS = "\n".join(f"{name}\tUp 2 hours" for name in healthcheck.CRITICAL_CONTAINERS)


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch):
    monkeypatch.setattr(healthcheck, "CONTAINER_RETRY_DELAY_S", 0.0)


def _run(ps=PS, healthy="true|healthy", started="2020-01-01T00:00:00Z"):
    def fake(cmd, timeout=15):
        if cmd[:2] == ["podman", "ps"]:
            return 0, ps
        if cmd[:2] == ["podman", "inspect"]:
            field = cmd[3] if len(cmd) > 3 else ""
            return (0, started) if "StartedAt" in field else (0, healthy)
        return 1, ""
    return fake


def test_a_healthy_container_does_not_page_when_ps_omits_the_marker(monkeypatch):
    monkeypatch.setattr(healthcheck, "run", _run())
    results = {item["check"]: item["status"] for item in healthcheck.check_containers()}
    assert results["container:trendi-postgres-1"] == "ok"
    assert results["container:trendi-api-1"] == "ok"
    assert all(status == "ok" for status in results.values()), results


def test_a_container_with_no_healthcheck_is_ok_while_running(monkeypatch):
    monkeypatch.setattr(healthcheck, "run", _run(healthy="true|"))
    results = {item["check"]: item["status"] for item in healthcheck.check_containers()}
    assert results["container:trendi-clamav-1"] == "ok"
    assert results["container:trendi-rspamd-1"] == "ok"


def test_a_really_unhealthy_container_still_fails(monkeypatch):
    monkeypatch.setattr(healthcheck, "run", _run(healthy="true|unhealthy"))
    results = {item["check"]: item["status"] for item in healthcheck.check_containers()}
    assert results["container:trendi-postgres-1"] == "fail"


def test_a_missing_container_still_fails(monkeypatch):
    monkeypatch.setattr(healthcheck, "run", _run(ps="trendi-postgres-1\tUp 2 hours"))
    results = {item["check"]: item["status"] for item in healthcheck.check_containers()}
    assert results["container:trendi-api-1"] == "fail"


def test_parse_container_timestamp_handles_podman_and_iso_formats():
    """Podman prints Go's `time.Time.String()` format, which previously broke `recently_started`."""
    ts_podman = healthcheck.parse_container_timestamp("2026-11-21 05:00:00.617192387 +0000 UTC")
    assert ts_podman == datetime(2026, 11, 21, 5, 0, 0, 617192, tzinfo=timezone.utc)

    ts_nzdt = healthcheck.parse_container_timestamp("2026-11-21 18:00:00.123456789 +1300 NZDT m=+1.5")
    assert ts_nzdt == datetime(2026, 11, 21, 5, 0, 0, 123456, tzinfo=timezone.utc)

    ts_iso = healthcheck.parse_container_timestamp("2026-11-21T05:00:00.617192387Z")
    assert ts_iso == datetime(2026, 11, 21, 5, 0, 0, 617192, tzinfo=timezone.utc)

    assert healthcheck.parse_container_timestamp("0001-01-01 00:00:00 +0000 UTC") is None
    assert healthcheck.parse_container_timestamp("not-a-timestamp") is None


def test_recently_started_recognises_podman_go_timestamp(monkeypatch):
    fresh = (datetime.now(timezone.utc) - timedelta(seconds=15)).strftime("%Y-%m-%d %H:%M:%S.%f000 +0000 UTC")
    stale = (datetime.now(timezone.utc) - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S.%f000 +0000 UTC")

    monkeypatch.setattr(healthcheck, "run", lambda cmd, timeout=15: (0, fresh))
    assert healthcheck.recently_started("trendi-api-1", minutes=10) is True

    monkeypatch.setattr(healthcheck, "run", lambda cmd, timeout=15: (0, stale))
    assert healthcheck.recently_started("trendi-api-1", minutes=10) is False


def test_starting_api_and_transient_missing_social_pass_after_retry(monkeypatch):
    """2026-11-21 18:00 NZDT incident: cron caught redeploy-api.sh mid-swap."""
    fresh = (datetime.now(timezone.utc) - timedelta(seconds=2)).strftime("%Y-%m-%d %H:%M:%S.%f000 +0000 UTC")
    ps_mid_swap = "\n".join(
        f"{name}\tUp 2 seconds (starting)" if name == "trendi-api-1"
        else f"{name}\tUp 2 hours"
        for name in healthcheck.CRITICAL_CONTAINERS
        if name != "trendi-social-1"
    )
    ps_recovered = "\n".join(
        f"{name}\tUp 12 seconds (healthy)" if name == "trendi-api-1"
        else f"{name}\tUp 10 seconds" if name == "trendi-social-1"
        else f"{name}\tUp 2 hours"
        for name in healthcheck.CRITICAL_CONTAINERS
    )
    calls = {"ps": 0}

    def fake(cmd, timeout=15):
        if cmd[:2] == ["podman", "ps"]:
            calls["ps"] += 1
            return 0, ps_mid_swap if calls["ps"] == 1 else ps_recovered
        if cmd[:2] == ["podman", "inspect"]:
            field = cmd[3] if len(cmd) > 3 else ""
            if "StartedAt" in field:
                return 0, fresh
            return (0, "true|starting") if calls["ps"] == 1 else (0, "true|healthy")
        return 1, ""

    monkeypatch.setattr(healthcheck, "run", fake)
    results = {item["check"]: item["status"] for item in healthcheck.check_containers()}
    assert calls["ps"] == 2
    assert results["container:trendi-api-1"] == "ok"
    assert results["container:trendi-social-1"] == "ok"
    assert all(status == "ok" for status in results.values()), results


def test_container_still_starting_within_grace_warns_not_fails(monkeypatch):
    fresh = (datetime.now(timezone.utc) - timedelta(seconds=10)).strftime("%Y-%m-%d %H:%M:%S.%f000 +0000 UTC")
    ps_starting = "\n".join(
        f"{name}\tUp 10 seconds (starting)" if name == "trendi-api-1"
        else f"{name}\tUp 2 hours"
        for name in healthcheck.CRITICAL_CONTAINERS
    )
    monkeypatch.setattr(healthcheck, "run", _run(ps=ps_starting, healthy="true|starting", started=fresh))
    results = {item["check"]: item["status"] for item in healthcheck.check_containers()}
    assert results["container:trendi-api-1"] == "warn"
    assert not any(status == "fail" for status in results.values()), results


def test_check_sidecar_checks_email_auth_and_social_reachability(monkeypatch):
    def fake_ok(cmd, timeout=20):
        script = cmd[-1]
        if "4390" in script:
            return 0, "405"
        return 0, "200"

    monkeypatch.setattr(healthcheck, "run", fake_ok)
    ok_results = {item["check"]: item["status"] for item in healthcheck.check_sidecar({})}
    assert ok_results == {"email-auth:health": "ok", "social:reachable": "ok"}

    def fake_detached(cmd, timeout=20):
        script = cmd[-1]
        if "4390" in script:
            return 1, "URLError: [Errno 111] Connection refused"
        return 0, "200"

    monkeypatch.setattr(healthcheck, "run", fake_detached)
    bad_results = {item["check"]: item["status"] for item in healthcheck.check_sidecar({})}
    assert bad_results == {"email-auth:health": "ok", "social:reachable": "fail"}


def test_main_exits_zero_during_deploy_grace_but_nonzero_with_no_alert(monkeypatch, tmp_path):
    """Scheduled cron runs must not trigger alert.sh during deploy grace; manual --no-alert must."""
    monkeypatch.setattr(healthcheck, "STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(healthcheck, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(healthcheck, "API_ENV", tmp_path / "missing-api.env")
    monkeypatch.setattr(healthcheck, "COMPOSE_ENV", tmp_path / "missing-compose.env")
    monkeypatch.setattr(healthcheck, "check_containers",
                        lambda: [healthcheck._fail("container:trendi-social-1", "container missing")])
    for fn in (
        "check_public_urls", "check_api_internal", "check_database", "check_host", "check_tls",
        "check_local_services", "check_crm_capture", "check_site_prices", "check_sms_inbound",
        "check_backups", "check_sip_firewall", "check_site_pages", "check_site_seo",
        "check_site_data", "check_email_auth", "check_deploy_manifest",
    ):
        monkeypatch.setattr(healthcheck, fn, lambda: [])
    for fn in ("check_cloudflare", "check_inbound", "check_sidecar", "check_outbound_guard"):
        monkeypatch.setattr(healthcheck, fn, lambda _env: [])
    monkeypatch.setattr(healthcheck, "deploying", lambda: "trendi-api-1")

    assert healthcheck.main([]) == 0
    assert healthcheck.main(["--no-alert"]) == 1


def test_no_script_recreates_or_restarts_api_without_redeploy_script():
    """Any script restarting api must go through redeploy-api.sh so social stays attached."""
    vps_dir = REPO / "scripts" / "vps"
    redeploy = (vps_dir / "redeploy-api.sh").read_text()
    assert "--no-build" in redeploy
    assert "rm -sf social" in redeploy
    assert "HostConfig.NetworkMode" in redeploy
    assert "social reachable" in redeploy

    restart = (vps_dir / "restart-api.sh").read_text()
    assert "redeploy-api.sh" in restart and "--no-build" in restart

    solo_api = re.compile(r"\b(?:compose\b[^\n]*\b(?:up|restart)\b[^\n]*\bapi\b|podman\s+restart\s+trendi-api-1)\b")
    offenders = []
    for path in sorted((REPO / "scripts").rglob("*.sh")):
        if path.name == "redeploy-api.sh":
            continue
        for lineno, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            if solo_api.search(line):
                offenders.append(f"{path.relative_to(REPO)}:{lineno}: {line.strip()}")
    assert not offenders, "api must be restarted through scripts/vps/redeploy-api.sh:\n" + "\n".join(offenders)
