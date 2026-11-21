"""Tests for scripts/vps/remove_dev_leftovers.py and remove-dev-leftovers.sh."""
from __future__ import annotations

import importlib.util
import sys
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT_PY = REPO / "scripts" / "vps" / "remove_dev_leftovers.py"
SCRIPT_SH = REPO / "scripts" / "vps" / "remove-dev-leftovers.sh"

_spec = importlib.util.spec_from_file_location("remove_dev_leftovers", SCRIPT_PY)
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)


def _sample_containers():
    return [
        mod.ContainerInfo(
            name="trendi-postgres-1",
            cid="111111111111",
            status="running",
            image_id="img_pgvector_111111",
            image_name="docker.io/pgvector/pgvector:pg16",
            compose_project="trendi",
            volumes=["trendi_database"],
            networks=["trendi_default"],
        ),
        mod.ContainerInfo(
            name="trendi-gateway-1",
            cid="222222222222",
            status="running",
            image_id="img_caddy_222222",
            image_name="docker.io/library/caddy:2",
            compose_project="trendi",
            volumes=[],
            networks=["trendi_default"],
        ),
        mod.ContainerInfo(
            name="dev-concierge-twenty-db-1",
            cid="333333333333",
            status="running",
            image_id="img_pg16_333333",
            image_name="docker.io/library/postgres:16",
            compose_project="dev-concierge",
            volumes=["dev-concierge_twenty_db"],
            networks=["dev-concierge_default"],
        ),
        mod.ContainerInfo(
            name="dev-concierge-twenty-redis-1",
            cid="444444444444",
            status="running",
            image_id="img_redis_444444",
            image_name="docker.io/library/redis:7-alpine",
            compose_project="dev-concierge",
            volumes=["anon_redis_vol"],
            networks=["dev-concierge_default"],
        ),
        mod.ContainerInfo(
            name="dev-concierge-postgres-1",
            cid="555555555555",
            status="running",
            image_id="img_pgvector_111111",
            image_name="docker.io/pgvector/pgvector:pg16",
            compose_project="dev-concierge",
            volumes=["dev-concierge_pg_data"],
            networks=["dev-concierge_default"],
        ),
    ]


def test_parse_containers_ignores_env_secrets():
    inspect_rows = [
        {
            "Name": "/dev-concierge-twenty-db-1",
            "Id": "abcdef1234567890",
            "State": {"Status": "running"},
            "Image": "sha256:ba07bdb15f0f",
            "ImageName": "docker.io/library/postgres:16",
            "Config": {
                "Env": ["POSTGRES_PASSWORD=super-secret-value"],
                "Labels": {"com.docker.compose.project": "dev-concierge"},
            },
            "Mounts": [{"Type": "volume", "Name": "dev-concierge_twenty_db", "Source": "/var/lib/vol"}],
            "NetworkSettings": {"Networks": {"dev-concierge_default": {}}},
        }
    ]
    parsed = mod.parse_containers(inspect_rows)
    assert len(parsed) == 1
    assert parsed[0].name == "dev-concierge-twenty-db-1"
    assert "super-secret-value" not in repr(parsed[0])


def test_plan_targets_only_unshared_dev_resources():
    containers = _sample_containers()
    volumes = [
        mod.VolumeInfo("trendi_database", "/v/trendi_db", "trendi", 10, 1024),
        mod.VolumeInfo("dev-concierge_twenty_db", "/v/twenty_db", "dev-concierge", 20, 2048),
        mod.VolumeInfo("anon_redis_vol", "/v/anon_redis", "", 1, 89),
        mod.VolumeInfo("dev-concierge_pg_data", "/v/dev_pg", "dev-concierge", 30, 4096),
    ]
    networks = [
        mod.NetworkInfo("trendi_default", "n1", "bridge", "trendi", ["trendi-postgres-1", "trendi-gateway-1"]),
        mod.NetworkInfo(
            "dev-concierge_default",
            "n2",
            "bridge",
            "dev-concierge",
            ["dev-concierge-twenty-db-1", "dev-concierge-twenty-redis-1", "dev-concierge-postgres-1"],
        ),
    ]
    images = [
        mod.ImageInfo("img_pgvector_111111", ["docker.io/pgvector/pgvector:pg16"], 400_000_000),
        mod.ImageInfo("img_caddy_222222", ["docker.io/library/caddy:2"], 60_000_000),
        mod.ImageInfo("img_pg16_333333", ["docker.io/library/postgres:16"], 430_000_000),
        mod.ImageInfo("img_redis_444444", ["docker.io/library/redis:7-alpine"], 38_000_000),
    ]

    plan = mod.build_cleanup_plan(containers, volumes, networks, images)
    assert plan.conflicts == []
    assert [c.name for c in plan.dev_containers] == [
        "dev-concierge-postgres-1",
        "dev-concierge-twenty-db-1",
        "dev-concierge-twenty-redis-1",
    ]
    assert [v.name for v in plan.candidate_volumes] == [
        "anon_redis_vol",
        "dev-concierge_pg_data",
        "dev-concierge_twenty_db",
    ]
    assert [n.name for n in plan.candidate_networks] == ["dev-concierge_default"]
    assert [i.image_id for i in plan.candidate_images] == ["img_pg16_333333", "img_redis_444444"]
    assert "img_pgvector" in plan.skipped_images


def test_plan_flags_conflict_when_production_shares_volume_or_network():
    containers = _sample_containers()
    containers[0].volumes.append("dev-concierge_twenty_db")
    volumes = [
        mod.VolumeInfo("trendi_database", "/v/trendi_db", "trendi", 10, 1024),
        mod.VolumeInfo("dev-concierge_twenty_db", "/v/twenty_db", "dev-concierge", 20, 2048),
    ]
    networks = [
        mod.NetworkInfo(
            "dev-concierge_default",
            "n2",
            "bridge",
            "dev-concierge",
            ["trendi-postgres-1", "dev-concierge-twenty-db-1"],
        ),
    ]
    plan = mod.build_cleanup_plan(containers, volumes, networks, [])
    assert len(plan.conflicts) == 2
    assert plan.candidate_volumes == []
    assert plan.candidate_networks == []


def test_backup_volume_mountpoint_creates_verified_archive_and_skips_empty(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    backup_dir = tmp_path / "backups"
    assert mod.backup_volume_mountpoint("dev_empty", str(empty_dir), backup_dir) is None

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "dump.rdb").write_bytes(b"REDIS0011")
    archive = mod.backup_volume_mountpoint("dev-concierge_redis", str(data_dir), backup_dir)
    assert archive is not None and archive.exists()
    with tarfile.open(archive, "r:gz") as tf:
        assert "dump.rdb" in tf.getnames()


def test_evaluate_containerd_removes_only_when_independent():
    ok = mod.evaluate_containerd(
        installed_packages=["containerd"],
        service_active="active",
        service_enabled="enabled",
        podman_depends_text="conmon, crun | runc, netavark",
        rdepends_output="containerd\nReverse Depends:\n",
        apt_simulate_output="Remv containerd [1.7.28-0ubuntu1~24.04.1]\n",
        podman_info_text='{"host":{"ociRuntime":{"name":"crun"}}}',
        active_ctr_tasks=[],
    )
    assert ok.should_remove is True

    # Keeps containerd if podman depends on it
    dep = mod.evaluate_containerd(
        installed_packages=["containerd"],
        service_active="inactive",
        service_enabled="disabled",
        podman_depends_text="conmon, containerd (>= 1.6)",
        rdepends_output="containerd\nReverse Depends:\n  podman\n",
        apt_simulate_output="Remv containerd [1.7]\nRemv podman [4.9]\n",
        podman_info_text='{}',
        active_ctr_tasks=[],
    )
    assert dep.should_remove is False
    assert "podman" in dep.reason

    # Keeps containerd if active tasks exist
    busy = mod.evaluate_containerd(
        installed_packages=["containerd"],
        service_active="active",
        service_enabled="enabled",
        podman_depends_text="conmon, crun",
        rdepends_output="containerd\nReverse Depends:\n",
        apt_simulate_output="Remv containerd [1.7]\n",
        podman_info_text='{}',
        active_ctr_tasks=["default:some-task"],
    )
    assert busy.should_remove is False
    assert "active task" in busy.reason


def test_apply_cleanup_stops_backs_up_then_removes_in_order(tmp_path, monkeypatch):
    vol_dir = tmp_path / "vol_data"
    vol_dir.mkdir()
    (vol_dir / "pg_version").write_text("16\n")
    release_dir = tmp_path / "release"
    release_dir.mkdir()

    # Fake docker.sock check
    monkeypatch.setattr(mod.os.path, "islink", lambda p: p == "/var/run/docker.sock")
    monkeypatch.setattr(mod.os, "readlink", lambda p: "/run/podman/podman.sock")

    plan = mod.CleanupPlan(
        dev_containers=[
            mod.ContainerInfo("dev-concierge-twenty-db-1", "111", "running", "img1", "postgres:16", "dev-concierge", ["dev-concierge_twenty_db"], [], ["dev-concierge_default"]),
        ],
        non_dev_containers=[],
        candidate_volumes=[mod.VolumeInfo("dev-concierge_twenty_db", str(vol_dir), "dev-concierge", 1, 3)],
        candidate_networks=[mod.NetworkInfo("dev-concierge_default", "n1", "bridge", "dev-concierge", ["dev-concierge-twenty-db-1"])],
        candidate_images=[mod.ImageInfo("img1", ["docker.io/library/postgres:16"], 100)],
        skipped_volumes={},
        skipped_networks={},
        skipped_images={},
        conflicts=[],
    )
    cd = mod.ContainerdDecision(
        installed_packages=["containerd"],
        service_active="active",
        service_enabled="enabled",
        podman_depends=[],
        rdepends=[],
        simulated_removals=["containerd"],
        runtime_uses_containerd=False,
        should_remove=True,
        reason="independent",
    )

    calls: list[list[str]] = []

    def fake_run(cmd: list[str]):
        calls.append(cmd)
        # Ensure backup already exists when container/volume removal runs
        if cmd[:2] == ["podman", "rm"] or cmd[:3] == ["podman", "volume", "rm"]:
            archive = release_dir / "removed" / "20261121" / "dev-volumes" / "dev-concierge_twenty_db.tar.gz"
            assert archive.exists(), "volume backup must exist before removing container/volume"
        return 0, "", ""

    summary = mod.apply_cleanup(fake_run, plan, cd, str(release_dir), "20261121")
    assert summary["containers_stopped"] == ["dev-concierge-twenty-db-1"]
    assert "dev-concierge_twenty_db" in summary["volumes_backed_up"]
    assert summary["containers_removed"] == ["dev-concierge-twenty-db-1"]
    assert summary["volumes_removed"] == ["dev-concierge_twenty_db"]
    assert summary["networks_removed"] == ["dev-concierge_default"]
    assert summary["containerd"]["removed"] == ["containerd"]
    assert (release_dir / "removed" / "20261121" / "dev-cleanup-manifest.json").exists()

    # Check stop happens before rm, and rm before volume rm
    stop_idx = next(i for i, c in enumerate(calls) if c[:2] == ["podman", "stop"])
    rm_idx = next(i for i, c in enumerate(calls) if c[:2] == ["podman", "rm"])
    vrm_idx = next(i for i, c in enumerate(calls) if c[:3] == ["podman", "volume", "rm"])
    assert stop_idx < rm_idx < vrm_idx


def test_apply_cleanup_refuses_when_conflicts_present(tmp_path):
    plan = mod.CleanupPlan([], [], [], [], [], {}, {}, {}, ["volume shared with prod"])
    cd = mod.ContainerdDecision([], "inactive", "disabled", [], [], [], False, False, "not installed")
    with pytest.raises(RuntimeError, match="conflicts"):
        mod.apply_cleanup(lambda _: (0, "", ""), plan, cd, str(tmp_path), "20261121")


def test_shell_wrapper_defaults_to_dry_run():
    body = SCRIPT_SH.read_text()
    assert 'MODE="--dry-run"' in body
    assert "remove_dev_leftovers.py" in body
