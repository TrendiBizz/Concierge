"""The container health check must not page a healthy container on Podman.

Podman's compat API (`docker ps` through podman.sock) does not append "(healthy)" to the status, so
after the 2026-11-17 Docker→Podman move every healthy container paged once it passed the 10-minute
warmup, even though `docker inspect` still said healthy. clamav and rspamd define no HEALTHCHECK at
all, so "healthy" could never be true for them. The check now asks the daemon for health directly
and treats a running container with no health check as up.
"""
import importlib.util
import pathlib

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "vps" / "healthcheck.py"
_spec = importlib.util.spec_from_file_location("concierge_healthcheck_containers", SCRIPT)
healthcheck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(healthcheck)

# Every critical container, "Up" — the Podman ps string deliberately has no "(healthy)" suffix.
PS = "\n".join(f"{name}\tUp 2 hours" for name in healthcheck.CRITICAL_CONTAINERS)


def _run(ps=PS, healthy="true|healthy", started="2020-01-01T00:00:00Z"):
    def fake(cmd, timeout=15):
        if cmd[:2] == ["docker", "ps"]:
            return 0, ps
        if cmd[:2] == ["docker", "inspect"]:
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
