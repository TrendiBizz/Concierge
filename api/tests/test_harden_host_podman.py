"""harden_host.sh must cap the journal (Podman logs to journald), not rotate dead docker json-file logs."""
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[2] / "scripts/vps/harden_host.sh").read_text()


def test_journal_cap_present():
    assert "SystemMaxUse=" in SCRIPT
    assert "journald.conf.d" in SCRIPT


def test_no_dead_docker_log_rotation():
    assert "docker-containers" not in SCRIPT
    assert "json-file" not in SCRIPT
    assert "/etc/docker/daemon.json" not in SCRIPT
